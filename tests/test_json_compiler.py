from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from helpers import PNG_BYTES, ROOT, load_module, valid_approved_analysis, valid_formal_draft


compiler = load_module(
    "json_compiler",
    "skills/meme-template-json-compiler/scripts/compiler.py",
)


def source(asset_id="asset-1", digest=None):
    value = {"namespace": "workbench", "sourceAssetId": asset_id}
    if digest:
        value["sourceSha256"] = digest
    return value


def valid_image_envelope(png_bytes=PNG_BYTES):
    image_sha = hashlib.sha256(png_bytes).hexdigest()
    return {
        "schemaVersion": 2,
        "status": "approved_uploaded",
        "image": {
            "uri": f"https://assets.memebuy.cn/gallery/template-images/{image_sha}.png",
            "sha256": image_sha,
            "width": 1024,
            "height": 1024,
            "mime": "image/png",
        },
    }


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = compiler.SnapshotKeyRegistryReader(
            "registry-r7",
            [{
                "key": "hug-your-pet",
                "sourceIdentity": source(),
                "legacySourceSha256Aliases": ["f" * 64],
            }],
        )

    def test_all_key_registry_decisions(self):
        new = self.registry.resolveTemplateKey({"proposedKey": "dance-together", "sourceIdentity": source("asset-2")})
        same = self.registry.resolveTemplateKey({"proposedKey": "hug-your-pet", "sourceIdentity": source()})
        collision = self.registry.resolveTemplateKey({"proposedKey": "hug-your-pet", "sourceIdentity": source("asset-2")})
        conflict = self.registry.resolveTemplateKey({"proposedKey": "other-hug", "sourceIdentity": source()})
        unavailable = compiler.SnapshotKeyRegistryReader("r", [], available=False).resolveTemplateKey(
            {"proposedKey": "dance-together"}
        )
        self.assertEqual(
            [new["decision"], same["decision"], collision["decision"], conflict["decision"], unavailable["decision"]],
            ["NEW", "EXISTING_SAME_SOURCE", "KEY_COLLISION", "SOURCE_CONFLICT", "REGISTRY_UNAVAILABLE"],
        )
        for response in (new, same, collision, conflict, unavailable):
            self.assertEqual(set(response), {"registryRevision", "decision", "resolvedKey", "matchedBy", "evidence"})

    def test_existing_key_must_be_registered(self):
        response = self.registry.resolveTemplateKey({
            "proposedKey": "unknown-key",
            "existingKey": "unknown-key",
            "sourceIdentity": source(),
        })
        self.assertEqual(response["decision"], "SOURCE_CONFLICT")

    def test_only_canonical_identity_or_registered_alias_can_match(self):
        alias = self.registry.resolveTemplateKey({
            "proposedKey": "hug-your-pet",
            "sourceIdentity": source("legacy-asset", "f" * 64),
        })
        self.assertEqual(alias["decision"], "EXISTING_SAME_SOURCE")
        self.assertEqual(alias["matchedBy"], ["legacySourceSha256Alias"])
        with self.assertRaises(compiler.ContractError):
            self.registry.resolveTemplateKey({
                "proposedKey": "hug-your-pet",
                "sourceIdentity": {"namespace": "workbench", "sourceAssetId": "x", "filename": "same.png"},
            })

    def test_registered_source_sha_is_an_integrity_check(self):
        registry = compiler.SnapshotKeyRegistryReader(
            "registry-r8",
            [{
                "key": "hug-your-pet",
                "sourceIdentity": source("asset-1", "a" * 64),
            }],
        )
        response = registry.resolveTemplateKey({
            "proposedKey": "hug-your-pet",
            "sourceIdentity": source("asset-1", "b" * 64),
        })
        self.assertEqual(response["decision"], "SOURCE_CONFLICT")
        self.assertIn("sourceSha256", response["matchedBy"])

    def test_registry_conflict_is_item_local_in_batch(self):
        items = [
            {"itemId": "bad", "proposedKey": "hug-your-pet", "sourceIdentity": source("other")},
            {"itemId": "good", "proposedKey": "dance-together", "sourceIdentity": source("new")},
        ]

        def process(item):
            response = self.registry.resolveTemplateKey(item | {})
            if response["decision"] not in {"NEW", "EXISTING_SAME_SOURCE"}:
                raise compiler.ContractError(response["decision"])
            return response

        # Keep the runtime-only itemId outside the registry protocol.
        def without_item_id(item):
            return process({key: value for key, value in item.items() if key != "itemId"})

        results = compiler.process_batch(items, without_item_id)
        self.assertEqual([result["state"] for result in results], ["paused", "completed"])


class GalleryAndCompilationTests(unittest.TestCase):
    def test_compile_final_json_reuses_upstream_immutable_url(self):
        image_sha = hashlib.sha256(PNG_BYTES).hexdigest()
        envelope = {
            "schemaVersion": 2,
            "status": "approved_uploaded",
            "image": {
                "uri": f"https://assets.memebuy.cn/gallery/template-images/{image_sha}.png",
                "sha256": image_sha,
                "width": 1024,
                "height": 1024,
                "mime": "image/png",
            },
        }
        registry = {
            "registryRevision": "r1",
            "decision": "NEW",
            "resolvedKey": "hug-your-pet",
            "matchedBy": [],
            "evidence": [],
        }
        formal = compiler.compile_final_json(
            envelope,
            valid_approved_analysis(image_sha),
            valid_formal_draft(),
            registry,
        )
        self.assertEqual(formal["cover"], envelope["image"]["uri"])
        self.assertEqual(formal["referenceImage"], envelope["image"]["uri"])
        analysis_schema = json.loads((
            ROOT / "skills/meme-template-json-compiler/references/contracts/approved-image-analysis.schema.json"
        ).read_text(encoding="utf-8"))
        Draft202012Validator(analysis_schema).validate(valid_approved_analysis(image_sha))

    def test_malformed_registry_response_cannot_reach_delivery(self):
        image_sha = hashlib.sha256(PNG_BYTES).hexdigest()
        envelope = {
            "schemaVersion": 2, "status": "approved_uploaded",
            "image": {"uri": f"https://assets.memebuy.cn/gallery/template-images/{image_sha}.png", "sha256": image_sha,
                      "width": 1024, "height": 1024, "mime": "image/png"},
        }
        malformed = {"decision": "NEW", "resolvedKey": "hug-your-pet"}
        with self.assertRaises(compiler.ContractError):
            compiler.compile_final_json(
                envelope, valid_approved_analysis(image_sha), valid_formal_draft(), malformed
            )

    def test_independent_analysis_covers_every_formal_field(self):
        image_sha = hashlib.sha256(PNG_BYTES).hexdigest()
        envelope = {
            "schemaVersion": 2, "status": "approved_uploaded",
            "image": {"uri": f"https://assets.memebuy.cn/gallery/template-images/{image_sha}.png", "sha256": image_sha,
                      "width": 1024, "height": 1024, "mime": "image/png"},
        }
        analysis = valid_approved_analysis(image_sha)
        compiler.validate_authoring_contract(analysis, valid_formal_draft(), envelope)
        missing = copy.deepcopy(analysis)
        del missing["fieldEvidence"]["tags"]
        with self.assertRaises(compiler.ContractError):
            compiler.validate_authoring_contract(missing, valid_formal_draft(), envelope)

    def test_title_description_tags_slots_and_prompt_are_machine_gated(self):
        image_sha = hashlib.sha256(PNG_BYTES).hexdigest()
        envelope = {
            "schemaVersion": 2, "status": "approved_uploaded",
            "image": {"uri": f"https://assets.memebuy.cn/gallery/template-images/{image_sha}.png", "sha256": image_sha,
                      "width": 1024, "height": 1024, "mime": "image/png"},
        }
        analysis = valid_approved_analysis(image_sha)

        long_description = valid_formal_draft()
        long_description["description"] = "这是一段超过二十个字的描述用来验证硬门禁必须拒绝"
        with self.assertRaises(compiler.ContractError):
            compiler.validate_authoring_contract(analysis, long_description, envelope)

        missing_tags = valid_formal_draft()
        missing_tags["metadata"]["tags"] = ["拥抱", "宠物", "手绘", "温暖"]
        with self.assertRaises(compiler.ContractError):
            compiler.validate_authoring_contract(analysis, missing_tags, envelope)

        low_value = copy.deepcopy(analysis)
        low_value["slotEvidence"]["subject"]["userMotivation"] = False
        with self.assertRaises(compiler.ContractError):
            compiler.validate_authoring_contract(low_value, valid_formal_draft(), envelope)

        internal_prompt = valid_formal_draft()
        internal_prompt["promptTemplate"] += " 同时写入 runtimeSemantics。"
        with self.assertRaises(compiler.ContractError):
            compiler.validate_authoring_contract(analysis, internal_prompt, envelope)

    def test_prompt_requires_real_placeholders_and_matching_defaults(self):
        image_sha = hashlib.sha256(PNG_BYTES).hexdigest()
        envelope = {
            "schemaVersion": 2, "status": "approved_uploaded",
            "image": {"uri": f"https://assets.memebuy.cn/gallery/template-images/{image_sha}.png", "sha256": image_sha,
                      "width": 1024, "height": 1024, "mime": "image/png"},
        }
        for prompt in (
            "双臂紧紧抱住画面中央的橘白猫。",
            "双臂紧紧抱住画面中央的{{ subject | \"布偶猫\" }}。",
        ):
            with self.subTest(prompt=prompt):
                draft = valid_formal_draft()
                draft["promptTemplate"] = prompt
                analysis = valid_approved_analysis(image_sha)
                analysis["semanticModel"]["promptTemplate"] = prompt
                analysis["selfReview"]["reviewedDraftSha256"] = compiler.sha256_json(draft)
                with self.assertRaises(compiler.ContractError):
                    compiler.validate_authoring_contract(analysis, draft, envelope)

    def test_user_facing_copy_and_retrieval_tags_are_machine_gated(self):
        image_sha = hashlib.sha256(PNG_BYTES).hexdigest()
        envelope = {
            "schemaVersion": 2, "status": "approved_uploaded",
            "image": {"uri": f"https://assets.memebuy.cn/gallery/template-images/{image_sha}.png", "sha256": image_sha,
                      "width": 1024, "height": 1024, "mime": "image/png"},
        }
        draft = valid_formal_draft()
        analysis = valid_approved_analysis(image_sha)
        compiler.validate_authoring_contract(analysis, draft, envelope)

        weak_title = copy.deepcopy(analysis)
        weak_title["titleEvidence"]["userAppeal"] = False
        with self.assertRaises(compiler.ContractError):
            compiler.validate_authoring_contract(weak_title, draft, envelope)

        internal_description = copy.deepcopy(analysis)
        internal_description["descriptionEvidence"]["userFacing"] = False
        with self.assertRaises(compiler.ContractError):
            compiler.validate_authoring_contract(internal_description, draft, envelope)

        searchless_tag = copy.deepcopy(analysis)
        searchless_tag["tagEvidence"]["拥抱"]["searchIntent"] = ""
        with self.assertRaises(compiler.ContractError):
            compiler.validate_authoring_contract(searchless_tag, draft, envelope)

    def test_recognized_ip_identity_uses_specific_natural_default(self):
        image_sha = hashlib.sha256(PNG_BYTES).hexdigest()
        envelope = {
            "schemaVersion": 2, "status": "approved_uploaded",
            "image": {"uri": f"https://assets.memebuy.cn/gallery/template-images/{image_sha}.png", "sha256": image_sha,
                      "width": 1024, "height": 1024, "mime": "image/png"},
        }
        draft = valid_formal_draft()
        slot = draft["inputSchema"]["slots"][0]
        slot["text"]["defaultValue"] = "葛城美里"
        slot["text"]["suggestions"] = ["式波·明日香", "绫波丽", "五条悟"]
        draft["promptTemplate"] = "双臂紧紧抱住画面中央的{{ subject | \"葛城美里\" }}。"

        analysis = valid_approved_analysis(image_sha)
        evidence = analysis["slotEvidence"]["subject"]
        evidence["defaultValue"] = "葛城美里"
        evidence["identityRecognition"] = {
            "status": "recognized",
            "canonicalName": "葛城美里",
            "evidence": "角色身份可由 Approved Image 的稳定辨识特征确认",
        }
        evidence["suggestionChecks"] = [
            {"value": value, "sameAxis": True, "sameGranularity": True,
             "mechanismCompatible": True}
            for value in ("式波·明日香", "绫波丽", "五条悟")
        ]
        evidence["openVisualFacts"] = ["葛城美里", "式波·明日香", "绫波丽", "五条悟"]
        analysis["semanticModel"]["promptTemplate"] = draft["promptTemplate"]
        analysis["selfReview"]["reviewedDraftSha256"] = compiler.sha256_json(draft)
        compiler.validate_authoring_contract(analysis, draft, envelope)

        generic_draft = copy.deepcopy(draft)
        generic_draft["inputSchema"]["slots"][0]["text"]["defaultValue"] = "紫发红夹克角色"
        generic_draft["promptTemplate"] = "双臂紧紧抱住画面中央的{{ subject | \"紫发红夹克角色\" }}。"
        generic = copy.deepcopy(analysis)
        generic["slotEvidence"]["subject"]["defaultValue"] = "紫发红夹克角色"
        generic["slotEvidence"]["subject"]["identityRecognition"]["canonicalName"] = "紫发红夹克角色"
        generic["slotEvidence"]["subject"]["openVisualFacts"][0] = "紫发红夹克角色"
        generic["semanticModel"]["promptTemplate"] = generic_draft["promptTemplate"]
        generic["selfReview"]["reviewedDraftSha256"] = compiler.sha256_json(generic_draft)
        with self.assertRaises(compiler.ContractError):
            compiler.validate_authoring_contract(generic, generic_draft, envelope)

        overdescribed = copy.deepcopy(analysis)
        overdescribed["slotEvidence"]["subject"]["defaultLanguageReview"]["modifierMinimal"] = False
        with self.assertRaises(compiler.ContractError):
            compiler.validate_authoring_contract(overdescribed, draft, envelope)

    def test_slot_count_preference_is_two_to_four_and_caps_at_four(self):
        contract = json.loads((
            ROOT / "skills/meme-template-json-compiler/references/machine-contract.json"
        ).read_text(encoding="utf-8"))
        preference = contract["authoring"]["slotCountPreference"]
        self.assertEqual(preference, {
            "minimum": 2,
            "maximum": 4,
            "singleSlotRequiresCoverageReview": True,
        })

        image_sha = hashlib.sha256(PNG_BYTES).hexdigest()
        envelope = {
            "schemaVersion": 2, "status": "approved_uploaded",
            "image": {"uri": f"https://assets.memebuy.cn/gallery/template-images/{image_sha}.png", "sha256": image_sha,
                      "width": 1024, "height": 1024, "mime": "image/png"},
        }
        draft = valid_formal_draft()
        analysis = valid_approved_analysis(image_sha)
        compiler.validate_authoring_contract(analysis, draft, envelope)

        oversized = copy.deepcopy(draft)
        for index in range(4):
            oversized["inputSchema"]["slots"].append({"id": f"extra_{index}"})
        with self.assertRaisesRegex(compiler.ContractError, "at most four"):
            compiler.validate_authoring_contract(analysis, oversized, envelope)

    def test_play_decisions_slot_coverage_and_precision_are_machine_gated(self):
        image_sha = hashlib.sha256(PNG_BYTES).hexdigest()
        envelope = {
            "schemaVersion": 2, "status": "approved_uploaded",
            "image": {"uri": f"https://assets.memebuy.cn/gallery/template-images/{image_sha}.png", "sha256": image_sha,
                      "width": 1024, "height": 1024, "mime": "image/png"},
        }
        draft = valid_formal_draft()
        analysis = valid_approved_analysis(image_sha)
        compiler.validate_authoring_contract(analysis, draft, envelope)

        wrong_decision = copy.deepcopy(analysis)
        wrong_decision["playDecisionModel"]["coreUserDecisions"][0]["slotId"] = "headline"
        with self.assertRaisesRegex(compiler.ContractError, "one-to-one"):
            compiler.validate_authoring_contract(wrong_decision, draft, envelope)

        low_precision = copy.deepcopy(analysis)
        low_precision["slotEvidence"]["subject"]["independentUserChoice"] = False
        with self.assertRaisesRegex(compiler.ContractError, "high-value gate"):
            compiler.validate_authoring_contract(low_precision, draft, envelope)

        missed_candidate = copy.deepcopy(analysis)
        missed_candidate["slotCoverageReview"]["axes"]["subject"]["candidateComponentIds"] = []
        with self.assertRaisesRegex(compiler.ContractError, "omitted"):
            compiler.validate_authoring_contract(missed_candidate, draft, envelope)

    def test_distributed_text_regions_share_one_semantic_unit_and_slot(self):
        regions = [
            {
                "regionId": "comparison-top", "role": "content", "action": "open_slot",
                "semanticUnitId": "comparison-joke", "semanticUnitRole": "distributed_message",
                "editValue": "high", "routingEvidence": "对比句上半部分",
                "slotId": "comparison_copy", "language": "en", "exactText": "The more I know",
                "layout": "one line", "position": "top",
            },
            {
                "regionId": "comparison-bottom", "role": "content", "action": "open_slot",
                "semanticUnitId": "comparison-joke", "semanticUnitRole": "distributed_message",
                "editValue": "high", "routingEvidence": "对比句下半部分",
                "slotId": "comparison_copy", "language": "en",
                "exactText": "The more I love my cat", "layout": "one line", "position": "bottom",
            },
        ]
        compiler._validate_text_regions(regions)
        split = copy.deepcopy(regions)
        split[1]["slotId"] = "people_word"
        with self.assertRaisesRegex(compiler.ContractError, "one route, slot, and role"):
            compiler._validate_text_regions(split)

    def test_batch_identity_diversity_routes_repeated_ip_to_exception_review(self):
        image_sha = hashlib.sha256(PNG_BYTES).hexdigest()
        first = valid_approved_analysis(image_sha)
        second = valid_approved_analysis(image_sha)
        for analysis in (first, second):
            recognition = analysis["slotEvidence"]["subject"]["identityRecognition"]
            recognition.update({"status": "recognized", "canonicalName": "初音未来"})
            analysis["slotEvidence"]["subject"]["defaultValue"] = "初音未来"
        report = compiler.build_batch_identity_diversity_report([
            {"itemId": "anime-a", "analysis": first},
            {"itemId": "anime-b", "analysis": second},
        ])
        self.assertEqual(report["qualitySignal"], "identity_concentration")
        self.assertEqual(report["repeatedIdentities"][0]["canonicalName"], "初音未来")

    def test_suggestions_keep_the_default_language_and_copy_form(self):
        image_sha = hashlib.sha256(PNG_BYTES).hexdigest()
        envelope = {
            "schemaVersion": 2, "status": "approved_uploaded",
            "image": {"uri": f"https://assets.memebuy.cn/gallery/template-images/{image_sha}.png", "sha256": image_sha,
                      "width": 1024, "height": 1024, "mime": "image/png"},
        }
        draft = valid_formal_draft()
        slot = draft["inputSchema"]["slots"][0]
        slot["text"]["defaultValue"] = "How Cute"
        slot["text"]["suggestions"] = ["真可爱", "就这？", "有点意思"]
        draft["promptTemplate"] = '双臂紧紧抱住画面中央的{{ subject | "How Cute" }}。'

        analysis = valid_approved_analysis(image_sha)
        evidence = analysis["slotEvidence"]["subject"]
        evidence["defaultValue"] = "How Cute"
        evidence["suggestionChecks"] = [
            {"value": value, "sameAxis": True, "sameGranularity": True,
             "mechanismCompatible": True}
            for value in ("真可爱", "就这？", "有点意思")
        ]
        evidence["openVisualFacts"] = ["How Cute", "真可爱", "就这？", "有点意思"]
        analysis["semanticModel"]["promptTemplate"] = draft["promptTemplate"]
        analysis["selfReview"]["reviewedDraftSha256"] = compiler.sha256_json(draft)

        with self.assertRaisesRegex(compiler.ContractError, "language"):
            compiler.validate_authoring_contract(analysis, draft, envelope)

    def test_official_major_tag_and_frozen_image_profile_are_required(self):
        image_sha = hashlib.sha256(PNG_BYTES).hexdigest()
        envelope = {
            "schemaVersion": 2, "status": "approved_uploaded",
            "image": {"uri": f"https://assets.memebuy.cn/gallery/template-images/{image_sha}.png", "sha256": image_sha,
                      "width": 1024, "height": 1024, "mime": "image/png"},
        }
        no_major = valid_formal_draft()
        no_major["metadata"]["tags"][0] = "宠物"
        no_major_analysis = valid_approved_analysis(image_sha)
        no_major_analysis["tagEvidence"]["宠物"] = no_major_analysis["tagEvidence"].pop("动物")
        no_major_analysis["selfReview"]["reviewedDraftSha256"] = compiler.sha256_json(no_major)
        with self.assertRaises(compiler.ContractError):
            compiler.validate_authoring_contract(no_major_analysis, no_major, envelope)

        raised_minimum = valid_formal_draft()
        raised_minimum["inputSchema"]["slots"][0]["image"]["minWidth"] = 512
        raised_analysis = valid_approved_analysis(image_sha)
        raised_analysis["selfReview"]["reviewedDraftSha256"] = compiler.sha256_json(raised_minimum)
        with self.assertRaises(compiler.ContractError):
            compiler.validate_authoring_contract(raised_analysis, raised_minimum, envelope)

    def test_supporting_detail_and_open_values_are_semantically_gated(self):
        image_sha = hashlib.sha256(PNG_BYTES).hexdigest()
        envelope = {
            "schemaVersion": 2, "status": "approved_uploaded",
            "image": {"uri": f"https://assets.memebuy.cn/gallery/template-images/{image_sha}.png", "sha256": image_sha,
                      "width": 1024, "height": 1024, "mime": "image/png"},
        }
        supporting = valid_approved_analysis(image_sha)
        supporting["editableCandidates"][0]["selectionReason"] = "visible_supporting_meal"
        with self.assertRaises(compiler.ContractError):
            compiler.validate_authoring_contract(supporting, valid_formal_draft(), envelope)

        locked = valid_formal_draft()
        locked["runtimeSemantics"]["visualContract"]["styleTraits"].append("中央固定为橘白猫")
        locked_analysis = valid_approved_analysis(image_sha)
        locked_analysis["semanticModel"]["runtimeSemantics"] = copy.deepcopy(locked["runtimeSemantics"])
        locked_analysis["selfReview"]["reviewedDraftSha256"] = compiler.sha256_json(locked)
        with self.assertRaises(compiler.ContractError):
            compiler.validate_authoring_contract(locked_analysis, locked, envelope)

    def test_text_slot_routing_and_self_review_sha_cannot_be_stale(self):
        image_sha = hashlib.sha256(PNG_BYTES).hexdigest()
        envelope = {
            "schemaVersion": 2, "status": "approved_uploaded",
            "image": {"uri": f"https://assets.memebuy.cn/gallery/template-images/{image_sha}.png", "sha256": image_sha,
                      "width": 1024, "height": 1024, "mime": "image/png"},
        }
        unrouted = valid_approved_analysis(image_sha)
        unrouted["textRegions"] = [{
            "regionId": "left-label", "role": "content", "action": "open_slot",
            "semanticUnitId": "left-label-message", "semanticUnitRole": "independent_message",
            "editValue": "high", "routingEvidence": "关系标签是高价值文字",
            "slotId": "missing_label", "language": "ko", "exactText": "왼쪽",
            "layout": "单行箭头标签", "position": "左侧人物上方",
        }]
        with self.assertRaises(compiler.ContractError):
            compiler.validate_authoring_contract(unrouted, valid_formal_draft(), envelope)

        changed = valid_formal_draft()
        changed["description"] = "替换画面中央主角"
        stale = valid_approved_analysis(image_sha)
        with self.assertRaises(compiler.ContractError):
            compiler.validate_authoring_contract(stale, changed, envelope)

        mechanical = valid_approved_analysis(image_sha)
        mechanical["selfReview"]["checks"]["slotRecallComplete"] = True
        with self.assertRaisesRegex(compiler.ContractError, "concrete evidence"):
            compiler.validate_authoring_contract(mechanical, valid_formal_draft(), envelope)

    def test_quick_text_controls_enforce_short_copy_limits(self):
        limits = compiler._contract()["authoring"]["quickTextLimits"]
        regions = [{"action": "open_slot", "slotId": "headline"}]
        valid_slot = [{
            "id": "headline",
            "text": {
                "defaultValue": "EVERYTHING WILL BE OKAY",
                "suggestions": ["OH LA LA", "SUMMER IS HERE", "MAKE IT YOURS"],
            },
        }]
        compiler._validate_quick_text_slot_lengths(valid_slot, regions, limits)

        long_sentence = copy.deepcopy(valid_slot)
        long_sentence[0]["text"]["defaultValue"] = (
            "THIS SUPPORTING SENTENCE HAS TOO MANY WORDS FOR A QUICK CONTROL"
        )
        with self.assertRaisesRegex(compiler.ContractError, "whitespace-token"):
            compiler._validate_quick_text_slot_lengths(long_sentence, regions, limits)

        long_continuous = copy.deepcopy(valid_slot)
        long_continuous[0]["text"]["defaultValue"] = "这是一整段应该进入自由编辑层的陪衬说明文字"
        with self.assertRaisesRegex(compiler.ContractError, "continuous-character"):
            compiler._validate_quick_text_slot_lengths(long_continuous, regions, limits)

    def test_distinct_arrow_labels_compile_as_independent_text_slots(self):
        image_sha = hashlib.sha256(PNG_BYTES).hexdigest()
        envelope = {
            "schemaVersion": 2, "status": "approved_uploaded",
            "image": {"uri": f"https://assets.memebuy.cn/gallery/template-images/{image_sha}.png", "sha256": image_sha,
                      "width": 1024, "height": 1024, "mime": "image/png"},
        }
        draft = valid_formal_draft()
        labels = {
            "left_caption": ("左侧标签", "童年好友", ["我的姐姐", "最佳损友", "儿时玩伴"]),
            "right_caption": ("右侧标签", "同桌伙伴", ["我的哥哥", "隔壁同学", "青梅竹马"]),
        }
        for slot_id, (label, default, suggestions) in labels.items():
            draft["inputSchema"]["slots"].append({
                "id": slot_id, "label": label, "required": False,
                "text": {
                    "allowCustom": True, "placeholder": f"输入{label}",
                    "suggestions": suggestions, "defaultValue": default,
                    "presentation": "suggestions",
                },
            })
            target_id = slot_id.replace("caption", "label")
            draft["runtimeSemantics"]["targetInstances"].append({
                "id": target_id, "kind": "content_element", "role": label,
                "region": f"{label[:2]}人物上方的箭头文字区域",
            })
            draft["runtimeSemantics"]["inputBindings"][slot_id] = {
                "operation": "replace_content", "targetIds": [target_id],
                "distributionPolicy": "replace_as_unit",
            }
        draft["promptTemplate"] = (
            "{{ left_caption | \"童年好友\" }}标记左侧人物，"
            "{{ right_caption | \"同桌伙伴\" }}标记右侧人物；"
            "双臂紧紧抱住画面中央的{{ subject | \"橘白猫\" }}。"
        )
        draft["runtimeSemantics"]["visualContract"]["relations"].append(
            "两段箭头文字分别指向左右人物"
        )

        analysis = valid_approved_analysis(image_sha)
        analysis["counts"]["inputControlCount"] = 3
        analysis["textRegions"] = []
        for slot_id, (label, default, suggestions) in labels.items():
            target_id = slot_id.replace("caption", "label")
            analysis["componentGraph"].append({
                "componentId": target_id, "role": "arrow_label", "region": label,
            })
            analysis["editableCandidates"].append({
                "slotId": slot_id, "componentId": target_id, "selected": True,
                "selectionReason": "high_value_text", "exclusionReason": None,
            })
            analysis["textRegions"].append({
                "regionId": target_id, "role": "content", "action": "open_slot",
                "semanticUnitId": f"{slot_id}_message",
                "semanticUnitRole": "independent_message",
                "editValue": "high", "routingEvidence": "箭头关系标签是高价值文字",
                "slotId": slot_id, "language": "zh-CN", "exactText": default,
                "layout": "单行箭头标签", "position": label,
            })
            analysis["slotEvidence"][slot_id] = {
                "userMotivation": True, "independentUserChoice": True,
                "meaningfulVariation": True, "visuallyVisible": True,
                "modelControllable": True, "mechanismPreserved": True,
                "decisionId": f"choose_{slot_id}",
                "selectionReason": "high_value_text", "defaultValue": default,
                "semanticAxis": f"{label}内容", "granularity": "人物关系短标签",
                "defaultLanguageReview": {
                    "natural": True, "concise": True, "modifierMinimal": True,
                },
                "inputModeDecision": {
                    "modes": ["text"], "reason": "text_only",
                    "evidence": "文字内容可直接编辑，无需视觉素材",
                },
                "suggestionChecks": [
                    {"value": value, "sameAxis": True, "sameGranularity": True,
                     "mechanismCompatible": True} for value in suggestions
                ],
                "openVisualFacts": [default, *suggestions],
                "bindingKind": "replace_content",
                "visualEvidence": f"{label}通过箭头建立人物关系叙事",
            }
            analysis["semanticModel"]["componentCoverage"][target_id] = {
                "targetIds": [target_id], "visualContractFields": ["relations"],
            }
            analysis["semanticModel"]["dynamicFactSources"][slot_id] = f"inputSchema.slots.{slot_id}"
            analysis["playDecisionModel"]["coreUserDecisions"].append({
                "decisionId": f"choose_{slot_id}",
                "description": f"选择{label}的关系文字",
                "slotId": slot_id,
                "evidence": f"{label}独立指向一名人物",
            })
            analysis["slotCoverageReview"]["axes"]["text"]["candidateComponentIds"].append(target_id)
            analysis["slotCoverageReview"]["axes"]["text"]["selectedSlotIds"].append(slot_id)
        analysis["slotCoverageReview"]["selectedSlotIds"] = ["subject", *labels]
        analysis["promptCoverage"]["slotIds"] = ["subject", *labels]
        analysis["semanticModel"]["promptTemplate"] = draft["promptTemplate"]
        analysis["semanticModel"]["runtimeSemantics"] = copy.deepcopy(draft["runtimeSemantics"])
        analysis["selfReview"]["reviewedDraftSha256"] = compiler.sha256_json(draft)

        compiler.validate_authoring_contract(analysis, draft, envelope)

    def test_dynamic_identity_group_requires_all_five_decisions(self):
        image_sha = hashlib.sha256(PNG_BYTES).hexdigest()
        envelope = {
            "schemaVersion": 2, "status": "approved_uploaded",
            "image": {"uri": f"https://assets.memebuy.cn/gallery/template-images/{image_sha}.png", "sha256": image_sha,
                      "width": 1024, "height": 1024, "mime": "image/png"},
        }
        draft = valid_formal_draft()
        slot = draft["inputSchema"]["slots"][0]
        slot["text"]["defaultValue"] = "家庭成员"
        slot["text"]["suggestions"] = ["亲友团", "同事团队", "同学聚会"]
        draft["promptTemplate"] = "{{ subject | \"家庭成员\" }}围拢在画面中央并保持紧密互动。"
        draft["runtimeSemantics"]["targetInstances"] = [{
            "id": "subject_group", "kind": "identity_group", "role": "中央合照群组",
            "region": "画面中央", "memberKind": "person", "minMembers": 2, "maxMembers": 8,
        }]
        draft["runtimeSemantics"]["inputBindings"]["subject"] = {
            "operation": "replace_identity",
            "targetIds": ["subject_group"],
            "bindingPolicy": "preserve_group",
            "renderingMode": "illustration_redraw",
            "allowedSourceGrouping": ["group_photo"],
            "groupToSinglePolicy": "reject",
            "clothingOwnership": "source",
        }
        analysis = valid_approved_analysis(image_sha)
        analysis["componentGraph"] = [
            {"componentId": "subject_group", "role": "identity_group", "region": "center"}
        ]
        analysis["identityTopology"] = [
            {"identityUnitId": "subject", "instanceIds": ["subject_group"]}
        ]
        analysis["editableCandidates"] = [
            {
                "slotId": "subject", "componentId": "subject_group", "selected": True,
                "selectionReason": "identity_control", "exclusionReason": None,
            }
        ]
        analysis["slotCoverageReview"]["axes"]["subject"]["candidateComponentIds"] = ["subject_group"]
        analysis["semanticModel"]["promptTemplate"] = draft["promptTemplate"]
        analysis["semanticModel"]["runtimeSemantics"] = copy.deepcopy(draft["runtimeSemantics"])
        analysis["semanticModel"]["componentCoverage"] = {
            "subject_group": {
                "targetIds": ["subject_group"],
                "visualContractFields": [
                    "medium", "styleTraits", "composition", "relations", "colorAndLight"
                ],
            }
        }
        analysis["semanticModel"]["completeRedrawByTarget"] = {"subject_group": True}
        analysis["slotEvidence"]["subject"]["bindingKind"] = "preserve_group"
        analysis["slotEvidence"]["subject"]["defaultValue"] = "家庭成员"
        analysis["slotEvidence"]["subject"]["inputModeDecision"] = {
            "modes": ["text", "image"], "reason": "dynamic_group",
            "evidence": "用户自然拥有成员同框且人数可变的家庭合照",
        }
        analysis["slotEvidence"]["subject"]["suggestionChecks"] = [
            {"value": value, "sameAxis": True, "sameGranularity": True,
             "mechanismCompatible": True}
            for value in ("亲友团", "同事团队", "同学聚会")
        ]
        analysis["slotEvidence"]["subject"]["openVisualFacts"] = [
            "家庭成员", "亲友团", "同事团队", "同学聚会",
        ]
        analysis["slotEvidence"]["subject"].pop("identityRecognition")
        analysis["slotEvidence"]["subject"]["groupDecision"] = {
            "wholeGroupIdentityFidelity": True,
            "groupPhotoNaturalInput": True,
            "variableMemberCount": True,
            "sameMemberKind": True,
            "noIndividuallyAddressableRoles": True,
        }
        analysis["selfReview"]["reviewedDraftSha256"] = compiler.sha256_json(draft)
        compiler.validate_authoring_contract(analysis, draft, envelope)
        for failed_fact in (
            "wholeGroupIdentityFidelity", "groupPhotoNaturalInput", "variableMemberCount",
            "sameMemberKind", "noIndividuallyAddressableRoles",
        ):
            with self.subTest(failed_fact=failed_fact):
                invalid = copy.deepcopy(analysis)
                invalid["slotEvidence"]["subject"]["groupDecision"][failed_fact] = False
                with self.assertRaises(compiler.ContractError):
                    compiler.validate_authoring_contract(invalid, draft, envelope)

        pure_image_draft = copy.deepcopy(draft)
        del pure_image_draft["inputSchema"]["slots"][0]["text"]
        del pure_image_draft["inputSchema"]["slots"][0]["resolutionStrategy"]
        pure_image_analysis = copy.deepcopy(analysis)
        pure_image_analysis["slotEvidence"]["subject"]["inputModeDecision"]["modes"] = ["image"]
        pure_image_analysis["slotEvidence"]["subject"]["suggestionChecks"] = []
        pure_image_analysis["semanticModel"]["promptTemplate"] = pure_image_draft["promptTemplate"]
        pure_image_analysis["selfReview"]["reviewedDraftSha256"] = compiler.sha256_json(pure_image_draft)
        with self.assertRaisesRegex(compiler.ContractError, "every production slot requires text input"):
            compiler.validate_authoring_contract(pure_image_analysis, pure_image_draft, envelope)

    def test_open_subject_rejects_preserved_specific_identity_text(self):
        image_sha = hashlib.sha256(PNG_BYTES).hexdigest()
        envelope = {
            "schemaVersion": 2, "status": "approved_uploaded",
            "image": {"uri": f"https://assets.memebuy.cn/gallery/template-images/{image_sha}.png", "sha256": image_sha,
                      "width": 1024, "height": 1024, "mime": "image/png"},
        }
        analysis = valid_approved_analysis(image_sha)
        analysis["textRegions"] = [{
            "regionId": "identity-name", "role": "identity", "action": "preserve",
            "semanticUnitId": "identity-name", "semanticUnitRole": "fixed_context",
            "editValue": "fixed", "routingEvidence": "测试错误保留开放身份名",
            "language": "zh-CN", "exactText": "具体艺人名", "layout": "单行",
            "position": "左上角",
        }]
        with self.assertRaises(compiler.ContractError):
            compiler.validate_authoring_contract(analysis, valid_formal_draft(), envelope)

    def test_feature_authority_and_three_text_edit_layers_are_machine_gated(self):
        image_sha = hashlib.sha256(PNG_BYTES).hexdigest()
        envelope = {
            "schemaVersion": 2, "status": "approved_uploaded",
            "image": {"uri": f"https://assets.memebuy.cn/gallery/template-images/{image_sha}.png", "sha256": image_sha,
                      "width": 1024, "height": 1024, "mime": "image/png"},
        }
        draft = valid_formal_draft()
        draft["promptTemplate"] += " 画面中写着“今日也要开心”。"
        draft["runtimeSemantics"]["visualContract"]["relations"].append(
            "背景招牌固定保留“营业中”字样和原排版"
        )
        analysis = valid_approved_analysis(image_sha)
        analysis["textRegions"] = [
            {
                "regionId": "secondary-caption", "role": "content",
                "semanticUnitId": "secondary-caption", "semanticUnitRole": "supporting_copy",
                "action": "free_editable", "editValue": "secondary",
                "routingEvidence": "用户可能修改，但不需要占用快捷槽位",
                "language": "zh-CN", "exactText": "今日也要开心",
                "layout": "单行副文案", "position": "画面底部",
            },
            {
                "regionId": "shop-sign", "role": "content",
                "semanticUnitId": "shop-sign", "semanticUnitRole": "fixed_context",
                "action": "preserve", "editValue": "fixed",
                "routingEvidence": "招牌文字是环境语境和版式的固定组成",
                "language": "zh-CN", "exactText": "营业中",
                "layout": "招牌弧形字", "position": "背景上方",
            },
            {
                "regionId": "author-mark", "role": "watermark",
                "semanticUnitId": "author-mark", "semanticUnitRole": "noise",
                "action": "remove", "editValue": "none",
                "routingEvidence": "作者水印不属于模板内容",
                "language": "zh-CN", "exactText": "@原作者",
                "layout": "角落小字", "position": "右下角",
            },
        ]
        analysis["promptCoverage"]["freeEditableRegionIds"] = ["secondary-caption"]
        analysis["semanticModel"]["promptTemplate"] = draft["promptTemplate"]
        analysis["semanticModel"]["runtimeSemantics"] = copy.deepcopy(draft["runtimeSemantics"])
        analysis["selfReview"]["reviewedDraftSha256"] = compiler.sha256_json(draft)
        compiler.validate_authoring_contract(analysis, draft, envelope)

        missing_free_text = copy.deepcopy(draft)
        missing_free_text["promptTemplate"] = valid_formal_draft()["promptTemplate"]
        missing_analysis = copy.deepcopy(analysis)
        missing_analysis["semanticModel"]["promptTemplate"] = missing_free_text["promptTemplate"]
        missing_analysis["selfReview"]["reviewedDraftSha256"] = compiler.sha256_json(missing_free_text)
        with self.assertRaisesRegex(compiler.ContractError, "free-editable text"):
            compiler.validate_authoring_contract(missing_analysis, missing_free_text, envelope)

        maid_draft = copy.deepcopy(draft)
        maid_draft["runtimeSemantics"]["inputBindings"]["subject"]["clothingOwnership"] = "template"
        maid_draft["runtimeSemantics"]["visualContract"]["styleTraits"].append(
            "角色固定穿着承担反差笑点的女仆装"
        )
        maid_dress = copy.deepcopy(analysis)
        maid_subject = maid_dress["slotEvidence"]["subject"]
        maid_subject["featureAuthority"]["clothing"] = {
            "authority": "template", "basis": "core_mechanism",
            "evidence": "女仆装本身承担模板的反差玩法",
        }
        maid_subject["clothingOwnership"] = "template"
        maid_subject["inheritFromUpload"] = ["可辨认身份特征", "发型"]
        maid_subject["keepFromTemplate"] = ["女仆装", "拥抱动作"]
        maid_dress["semanticModel"]["runtimeSemantics"] = copy.deepcopy(
            maid_draft["runtimeSemantics"]
        )
        maid_dress["selfReview"]["reviewedDraftSha256"] = compiler.sha256_json(maid_draft)
        compiler.validate_authoring_contract(maid_dress, maid_draft, envelope)

        mismatched_clothing = copy.deepcopy(maid_dress)
        mismatched_clothing["slotEvidence"]["subject"]["featureAuthority"]["clothing"] = {
            "authority": "source", "basis": "appearance_continuity",
            "evidence": "错误地让女仆装跟随用户图",
        }
        with self.assertRaisesRegex(compiler.ContractError, "clothing feature authority"):
            compiler.validate_authoring_contract(mismatched_clothing, maid_draft, envelope)

    def test_gallery_snapshot_and_v2_profile(self):
        draft = valid_formal_draft()
        digest = hashlib.sha256(PNG_BYTES).hexdigest()
        url = f"https://assets.memebuy.cn/gallery/template-images/{digest}.png"
        formal = {**draft, "cover": url, "referenceImage": url}
        compiler.validate_formal_json(formal)
        backend_export = copy.deepcopy(formal)
        backend_export["id"] = "database-generated-template-id"
        with self.assertRaisesRegex(compiler.ContractError, "forbidden fields.*id"):
            compiler.validate_formal_json(backend_export)
        old = copy.deepcopy(formal)
        old["runtimeSemantics"]["version"] = 1
        with self.assertRaises(compiler.ContractError):
            compiler.validate_formal_json(old)
        missing_clothing = copy.deepcopy(formal)
        del missing_clothing["runtimeSemantics"]["inputBindings"]["subject"]["clothingOwnership"]
        with self.assertRaises(compiler.ContractError):
            compiler.validate_formal_json(missing_clothing)

    def test_approved_envelope_rejects_semantic_pollution(self):
        envelope = {
            "schemaVersion": 2,
            "status": "approved_uploaded",
            "image": {
                "uri": f"https://assets.memebuy.cn/gallery/template-images/{'a' * 64}.png",
                "sha256": "a" * 64,
                "width": 1024,
                "height": 1024,
                "mime": "image/png",
            },
            "sourceIdentity": source(),
        }
        with self.assertRaises(compiler.ContractError):
            compiler.validate_approved_image_envelope(envelope)

    def test_json_only_revision_reuses_the_same_image_url(self):
        envelope = valid_image_envelope()
        first = compiler.project_formal_json(valid_formal_draft(), envelope)
        revised_draft = valid_formal_draft()
        revised_draft["title"] = "抱紧你的毛孩子"
        revised = compiler.project_formal_json(revised_draft, envelope)
        self.assertEqual(first["cover"], revised["cover"])
        self.assertEqual(first["referenceImage"], revised["referenceImage"])

    def test_formal_writer_is_create_once_and_path_safe(self):
        draft = valid_formal_draft()
        formal = compiler.project_formal_json(draft, valid_image_envelope())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = compiler.write_formal_json(root, formal)
            self.assertEqual(path, root.resolve() / "hug-your-pet" / "hug-your-pet.json")
            self.assertEqual(compiler.write_formal_json(root, formal), path)
            (root / "hug-your-pet" / "sidecar.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(compiler.ContractError):
                compiler.write_formal_json(root, formal)
            (root / "hug-your-pet" / "sidecar.json").unlink()
            changed = copy.deepcopy(formal)
            changed["title"] = "冲突内容"
            with self.assertRaises(compiler.ContractError):
                compiler.write_formal_json(root, changed)

    def test_portable_index_is_sibling_to_pure_delivery(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            formal = compiler.project_formal_json(
                valid_formal_draft(), valid_image_envelope()
            )
            compiler.write_formal_json(root / "delivery", formal)
            index_path = compiler.write_production_index(
                root,
                [{
                    "itemId": "item-a",
                    "skill": "meme-template-json-compiler",
                    "state": "delivered",
                    "revision": 1,
                    "stage": "formal_json_written",
                    "artifacts": {"formalJson": "delivery://hug-your-pet/hug-your-pet.json"},
                }],
                generated_at="2026-08-29T12:00:00Z",
            )
            self.assertEqual(index_path, (root / "index" / "production-index.json").resolve())
            self.assertEqual(
                [path.name for path in (root / "delivery" / "hug-your-pet").iterdir()],
                ["hug-your-pet.json"],
            )

    def test_json_batch_bounds_are_one_to_one_hundred(self):
        with self.assertRaises(compiler.ContractError):
            compiler.process_batch([], lambda item: item)
        with self.assertRaises(compiler.ContractError):
            compiler.process_batch([{"itemId": str(i)} for i in range(101)], lambda item: item)


if __name__ == "__main__":
    unittest.main()
