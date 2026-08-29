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
UPLOADED_AT = "2026-08-29T12:00:00Z"


class FakeOss:
    def __init__(self, existing=None):
        self.existing = existing
        self.head_calls = []
        self.put_calls = []

    def head(self, object_key):
        self.head_calls.append(object_key)
        return self.existing

    def put_create_once(self, object_key, content, metadata):
        self.put_calls.append((object_key, content, dict(metadata)))
        self.existing = {"objectKey": object_key, **metadata}
        return dict(self.existing)


def source(asset_id="asset-1", digest=None):
    value = {"namespace": "workbench", "sourceAssetId": asset_id}
    if digest:
        value["sourceSha256"] = digest
    return value


def valid_approval(draft, png_bytes=PNG_BYTES, rule_version="0.1.0", revision=1):
    image_sha = hashlib.sha256(png_bytes).hexdigest()
    formal = compiler.project_formal_json(draft, image_sha)
    return {
        "decision": "APPROVED",
        "objectSha256": compiler.sha256_json(formal),
        "approvedImageSha256": image_sha,
        "reviewerRef": "reviewer://json/test",
        "decidedAt": "2026-08-29T11:00:00Z",
        "ruleVersion": rule_version,
        "revision": revision,
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


class GalleryAndOssTests(unittest.TestCase):
    def test_json_review_binds_complete_preview_and_approved_image_sha(self):
        image_sha = hashlib.sha256(PNG_BYTES).hexdigest()
        envelope = {
            "schemaVersion": 1,
            "status": "approved",
            "image": {
                "uri": "fixture://approved.png",
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
        package = compiler.build_json_review_package(
            envelope,
            valid_approved_analysis(image_sha),
            valid_formal_draft(),
            registry,
            rule_version="0.1.0",
            revision=1,
        )
        self.assertEqual(package["approvedImageSha256"], image_sha)
        self.assertEqual(package["objectSha256"], compiler.sha256_json(package["formalPreview"]))
        self.assertEqual(package["formalPreview"]["cover"], package["formalPreview"]["referenceImage"])
        analysis_schema = json.loads((
            ROOT / "skills/meme-template-json-compiler/references/contracts/approved-image-analysis.schema.json"
        ).read_text(encoding="utf-8"))
        review_schema = json.loads((
            ROOT / "skills/meme-template-json-compiler/references/contracts/template-json-review.schema.json"
        ).read_text(encoding="utf-8"))
        Draft202012Validator(analysis_schema).validate(valid_approved_analysis(image_sha))
        Draft202012Validator(review_schema).validate(package)

    def test_malformed_registry_response_cannot_reach_review(self):
        image_sha = hashlib.sha256(PNG_BYTES).hexdigest()
        envelope = {
            "schemaVersion": 1, "status": "approved",
            "image": {"uri": "fixture://approved.png", "sha256": image_sha,
                      "width": 1024, "height": 1024, "mime": "image/png"},
        }
        malformed = {"decision": "NEW", "resolvedKey": "hug-your-pet"}
        with self.assertRaises(compiler.ContractError):
            compiler.build_json_review_package(
                envelope, valid_approved_analysis(image_sha), valid_formal_draft(), malformed,
                rule_version="0.1.0", revision=1,
            )

    def test_independent_analysis_covers_every_formal_field(self):
        image_sha = hashlib.sha256(PNG_BYTES).hexdigest()
        envelope = {
            "schemaVersion": 1, "status": "approved",
            "image": {"uri": "fixture://approved.png", "sha256": image_sha,
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
            "schemaVersion": 1, "status": "approved",
            "image": {"uri": "fixture://approved.png", "sha256": image_sha,
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

    def test_dynamic_identity_group_requires_all_five_decisions(self):
        image_sha = hashlib.sha256(PNG_BYTES).hexdigest()
        envelope = {
            "schemaVersion": 1, "status": "approved",
            "image": {"uri": "fixture://approved.png", "sha256": image_sha,
                      "width": 1024, "height": 1024, "mime": "image/png"},
        }
        draft = valid_formal_draft()
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
            {"slotId": "subject", "componentId": "subject_group"}
        ]
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
        analysis["slotEvidence"]["subject"]["groupDecision"] = {
            "wholeGroupIdentityFidelity": True,
            "groupPhotoNaturalInput": True,
            "variableMemberCount": True,
            "sameMemberKind": True,
            "noIndividuallyAddressableRoles": True,
        }
        compiler.validate_authoring_contract(analysis, draft, envelope)
        invalid = copy.deepcopy(analysis)
        invalid["slotEvidence"]["subject"]["groupDecision"]["variableMemberCount"] = False
        with self.assertRaises(compiler.ContractError):
            compiler.validate_authoring_contract(invalid, draft, envelope)

    def test_open_subject_rejects_preserved_specific_identity_text(self):
        image_sha = hashlib.sha256(PNG_BYTES).hexdigest()
        envelope = {
            "schemaVersion": 1, "status": "approved",
            "image": {"uri": "fixture://approved.png", "sha256": image_sha,
                      "width": 1024, "height": 1024, "mime": "image/png"},
        }
        analysis = valid_approved_analysis(image_sha)
        analysis["textRegions"] = [{
            "regionId": "identity-name", "role": "identity", "action": "preserve",
            "language": "zh-CN", "exactText": "具体艺人名", "layout": "单行",
            "position": "左上角",
        }]
        with self.assertRaises(compiler.ContractError):
            compiler.validate_authoring_contract(analysis, valid_formal_draft(), envelope)

    def test_gallery_snapshot_and_v2_profile(self):
        draft = valid_formal_draft()
        digest = hashlib.sha256(PNG_BYTES).hexdigest()
        url = f"https://assets.memebuy.cn/gallery/templates/hug-your-pet/{digest}.png"
        formal = {**draft, "cover": url, "referenceImage": url}
        compiler.validate_formal_json(formal)
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
            "schemaVersion": 1,
            "status": "approved",
            "image": {
                "uri": "fixture://approved.png",
                "sha256": "a" * 64,
                "width": 1024,
                "height": 1024,
                "mime": "image/png",
            },
            "sourceIdentity": source(),
        }
        with self.assertRaises(compiler.ContractError):
            compiler.validate_approved_image_envelope(envelope)

    def test_oss_path_url_hash_and_same_cover_reference(self):
        draft = valid_formal_draft()
        approval = valid_approval(draft)
        oss = FakeOss()
        formal, receipt = compiler.finalize_approved_json(
            draft, approval, PNG_BYTES, oss, rule_version="0.1.0", revision=1,
            uploaded_at=UPLOADED_AT,
        )
        digest = hashlib.sha256(PNG_BYTES).hexdigest()
        expected_key = f"gallery/templates/hug-your-pet/{digest}.png"
        expected_url = f"https://assets.memebuy.cn/{expected_key}"
        self.assertEqual(receipt["objectKey"], expected_key)
        self.assertEqual(receipt["objectDigest"], digest)
        self.assertEqual(receipt["providerReceiptDigest"], compiler.sha256_json(receipt["providerReceipt"]))
        self.assertEqual(receipt["uploadedAt"], UPLOADED_AT)
        self.assertEqual(oss.put_calls[0][0], expected_key)
        self.assertIs(oss.put_calls[0][1], PNG_BYTES)
        self.assertEqual(formal["cover"], expected_url)
        self.assertEqual(formal["referenceImage"], expected_url)

    def test_stale_json_approval_has_zero_oss_calls(self):
        oss = FakeOss()
        with self.assertRaises(compiler.ContractError):
            compiler.finalize_approved_json(
                valid_formal_draft(),
                {"decision": "APPROVED", "objectSha256": "0" * 64, "approvedImageSha256": "0" * 64},
                PNG_BYTES,
                oss, rule_version="0.1.0", revision=1, uploaded_at=UPLOADED_AT,
            )
        self.assertEqual(oss.head_calls, [])
        self.assertEqual(oss.put_calls, [])

    def test_invalid_production_profile_has_zero_oss_calls(self):
        draft = valid_formal_draft()
        draft["runtimeSemantics"]["version"] = 1
        approval = valid_approval(draft)
        oss = FakeOss()
        with self.assertRaises(compiler.ContractError):
            compiler.finalize_approved_json(
                draft, approval, PNG_BYTES, oss, rule_version="0.1.0", revision=1,
                uploaded_at=UPLOADED_AT,
            )
        self.assertEqual(oss.head_calls, [])
        self.assertEqual(oss.put_calls, [])

    def test_json_approval_cannot_be_reused_for_different_png(self):
        draft = valid_formal_draft()
        approval = valid_approval(draft)
        changed_png = PNG_BYTES + b"changed"
        oss = FakeOss()
        with self.assertRaises(compiler.ContractError):
            compiler.finalize_approved_json(
                draft, approval, changed_png, oss, rule_version="0.1.0", revision=1,
                uploaded_at=UPLOADED_AT,
            )
        self.assertEqual(oss.head_calls, [])
        self.assertEqual(oss.put_calls, [])

    def test_remote_object_reuse_requires_all_three_identity_facts(self):
        draft = valid_formal_draft()
        approval = valid_approval(draft)
        intent = compiler.oss_intent(draft["key"], PNG_BYTES)
        matching = {
            "objectKey": intent["objectKey"],
            "sha256": intent["approvedImageSha256"],
            "byteLength": intent["byteLength"],
            "remoteIdentity": intent["remoteIdentity"],
            "requestIdentity": intent["requestIdentity"],
        }
        oss = FakeOss(matching)
        _, receipt = compiler.finalize_approved_json(
            draft, approval, PNG_BYTES, oss, rule_version="0.1.0", revision=1,
            uploaded_at=UPLOADED_AT,
        )
        self.assertTrue(receipt["providerReceipt"]["reused"])
        self.assertEqual(oss.put_calls, [])

        for field, bad_value in (
            ("objectKey", "other"), ("sha256", "0" * 64), ("byteLength", 1),
            ("remoteIdentity", "other"), ("requestIdentity", "0" * 64),
        ):
            with self.subTest(field=field):
                conflict = dict(matching)
                conflict[field] = bad_value
                bad_oss = FakeOss(conflict)
                with self.assertRaises(compiler.ContractError):
                    compiler.finalize_approved_json(
                        draft, approval, PNG_BYTES, bad_oss, rule_version="0.1.0", revision=1,
                        uploaded_at=UPLOADED_AT,
                    )
                self.assertEqual(bad_oss.put_calls, [])

    def test_json_approval_rule_and_revision_are_fresh_before_oss(self):
        draft = valid_formal_draft()
        for changed in ({"ruleVersion": "0.2.0"}, {"revision": 2}):
            approval = valid_approval(draft)
            approval.update(changed)
            oss = FakeOss()
            with self.assertRaises(compiler.ContractError):
                compiler.finalize_approved_json(
                    draft, approval, PNG_BYTES, oss, rule_version="0.1.0", revision=1,
                    uploaded_at=UPLOADED_AT,
                )
            self.assertEqual(oss.head_calls, [])

    def test_receipt_recovery_skips_remote_calls(self):
        draft = valid_formal_draft()
        approval = valid_approval(draft)
        first_oss = FakeOss()
        formal, receipt = compiler.finalize_approved_json(
            draft, approval, PNG_BYTES, first_oss, rule_version="0.1.0", revision=1,
            uploaded_at=UPLOADED_AT,
        )
        recovering_oss = FakeOss()
        recovered, recovered_receipt = compiler.finalize_approved_json(
            draft, approval, PNG_BYTES, recovering_oss,
            rule_version="0.1.0", revision=1, uploaded_at=UPLOADED_AT,
            existing_receipt=receipt,
        )
        self.assertEqual(recovered, formal)
        self.assertEqual(recovered_receipt, receipt)
        self.assertEqual(recovering_oss.head_calls, [])
        self.assertEqual(recovering_oss.put_calls, [])
        tampered = copy.deepcopy(receipt)
        tampered["providerReceiptDigest"] = "0" * 64
        with self.assertRaises(compiler.ContractError):
            compiler.finalize_approved_json(
                draft, approval, PNG_BYTES, recovering_oss,
                rule_version="0.1.0", revision=1, uploaded_at=UPLOADED_AT,
                existing_receipt=tampered,
            )
        self.assertEqual(recovering_oss.head_calls, [])

    def test_formal_writer_is_create_once_and_path_safe(self):
        draft = valid_formal_draft()
        formal = compiler.project_formal_json(draft, hashlib.sha256(PNG_BYTES).hexdigest())
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
                valid_formal_draft(), hashlib.sha256(PNG_BYTES).hexdigest()
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
