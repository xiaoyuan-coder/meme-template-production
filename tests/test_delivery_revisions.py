from __future__ import annotations

import copy
import unittest

from helpers import load_module, valid_approved_analysis, valid_formal_draft
from test_json_compiler import valid_image_envelope


compiler = load_module("delivery_compiler", "skills/meme-template-json-compiler/scripts/compiler.py")


class DeliveryRevisionTests(unittest.TestCase):
    def setUp(self):
        self.envelope = valid_image_envelope()
        self.draft = valid_formal_draft()
        self.previous = compiler.project_formal_json(self.draft, self.envelope)
        self.scope = {
            "previousFormalSha256": compiler.sha256_json(self.previous),
            "requestEvidence": ["conversation://request/change-title-only"],
            "addedSlotIds": [], "removedSlotIds": [], "modifiedSlotIds": [],
            "changedFieldPaths": ["/title"],
        }

    def test_json_revision_compiles_with_fresh_review_and_exact_scope(self):
        draft = copy.deepcopy(self.draft)
        draft["title"] = "抱紧你的毛孩子"
        analysis = valid_approved_analysis(self.envelope["image"]["sha256"])
        registry = {
            "registryRevision": "r2", "decision": "EXISTING_SAME_SOURCE",
            "resolvedKey": draft["key"], "matchedBy": ["canonicalSourceIdentity"], "evidence": [],
        }
        with self.assertRaises(compiler.ContractError):
            compiler.compile_json_revision(self.previous, self.scope, self.envelope, analysis, draft, registry)
        analysis["selfReview"]["reviewedDraftSha256"] = compiler.sha256_json(draft)
        revised = compiler.compile_json_revision(self.previous, self.scope, self.envelope, analysis, draft, registry)
        self.assertEqual(revised["title"], draft["title"])
        self.assertEqual(revised["inputSchema"], self.previous["inputSchema"])
        self.assertEqual(revised["cover"], self.previous["cover"])
        wrong_scope = dict(self.scope, previousFormalSha256="0" * 64)
        with self.assertRaises(compiler.ContractError):
            compiler.compile_json_revision(self.previous, wrong_scope, self.envelope, analysis, draft, registry)
        with self.assertRaises(compiler.ContractError):
            compiler.compile_json_revision(self.previous, self.scope, self.envelope, analysis, draft, dict(registry, decision="NEW"))

    def test_json_revision_omits_third_stage_field_and_preserves_prior_object(self):
        self.previous["imageUrl"] = (
            "https://assets.memebuy.cn/memebuy/template-atmosphere/sha256/"
            + "a" * 64
            + ".png"
        )
        self.scope["previousFormalSha256"] = compiler.sha256_json(self.previous)
        draft = copy.deepcopy(self.draft)
        draft["title"] = "抱紧你的毛孩子"
        analysis = valid_approved_analysis(self.envelope["image"]["sha256"])
        analysis["selfReview"]["reviewedDraftSha256"] = compiler.sha256_json(draft)
        registry = {
            "registryRevision": "r2", "decision": "EXISTING_SAME_SOURCE",
            "resolvedKey": draft["key"], "matchedBy": ["canonicalSourceIdentity"], "evidence": [],
        }
        original = copy.deepcopy(self.previous)
        revised = compiler.compile_json_revision(
            self.previous, self.scope, self.envelope, analysis, draft, registry
        )
        self.assertNotIn("imageUrl", revised)
        self.assertEqual(self.previous, original)

    def test_title_revision_rejects_unrequested_slot_binding_and_topology_changes(self):
        mutations = [
            lambda value: value["inputSchema"]["slots"][0]["text"].update(suggestions=["白猫", "黑猫", "灰猫"]),
            lambda value: value["runtimeSemantics"]["inputBindings"]["subject"].update(clothingOwnership="template"),
            lambda value: value["runtimeSemantics"]["targetInstances"][0].update(region="左侧"),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                revised = copy.deepcopy(self.previous)
                revised["title"] = "抱紧你的毛孩子"
                mutate(revised)
                with self.assertRaises(compiler.ContractError):
                    compiler.validate_revision_scope(self.previous, revised, self.scope)

    def test_slot_removal_requires_explicit_scope_and_preserves_other_slots(self):
        previous = copy.deepcopy(self.previous)
        extra = copy.deepcopy(previous["inputSchema"]["slots"][0])
        extra["id"] = "companion"
        previous["inputSchema"]["slots"].append(extra)
        previous["runtimeSemantics"]["inputBindings"]["companion"] = copy.deepcopy(
            previous["runtimeSemantics"]["inputBindings"]["subject"]
        )
        previous["promptTemplate"] += '旁边站着{{ companion | "橘白猫" }}。'
        previous["runtimeSemantics"]["inputBindings"]["companion"]["targetIds"] = ["companion_main"]
        previous["runtimeSemantics"]["targetInstances"].append({
            "id": "companion_main", "kind": "identity_subject", "role": "旁边的伙伴", "region": "右侧",
        })
        scope = dict(self.scope, previousFormalSha256=compiler.sha256_json(previous),
                     changedFieldPaths=["/promptTemplate", "/runtimeSemantics/targetInstances"])
        with self.assertRaises(compiler.ContractError):
            compiler.validate_revision_scope(previous, self.previous, scope)
        scope["removedSlotIds"] = ["companion"]
        compiler.validate_revision_scope(previous, self.previous, scope)
        changed = copy.deepcopy(self.previous)
        changed["inputSchema"]["slots"][0]["label"] = "新的主体名称"
        with self.assertRaises(compiler.ContractError):
            compiler.validate_revision_scope(previous, changed, scope)
        addition = dict(scope, previousFormalSha256=compiler.sha256_json(self.previous),
                        addedSlotIds=["companion"], removedSlotIds=[])
        compiler.validate_revision_scope(self.previous, previous, addition)

    def test_declared_slot_edit_preserves_topology_and_other_fields(self):
        revised = copy.deepcopy(self.previous)
        revised["inputSchema"]["slots"][0]["text"]["suggestions"] = ["白猫", "黑猫", "灰猫"]
        scope = dict(self.scope, modifiedSlotIds=["subject"], changedFieldPaths=[])
        compiler.validate_revision_scope(self.previous, revised, scope)
        self.assertEqual(revised["runtimeSemantics"], self.previous["runtimeSemantics"])
        with self.assertRaises(compiler.ContractError):
            compiler.validate_revision_scope(self.previous, revised, dict(scope, modifiedSlotIds=["subject", "unused"]))

    def test_json_revision_cannot_change_key_or_approved_image(self):
        for field in ("key", "cover", "referenceImage"):
            revised = copy.deepcopy(self.previous)
            revised[field] = "another-key" if field == "key" else self.previous[field].replace(
                self.envelope["image"]["sha256"], "a" * 64
            )
            with self.subTest(field=field), self.assertRaises(compiler.ContractError):
                compiler.validate_revision_scope(self.previous, revised, self.scope)

    def observations(self, formal):
        identity = {
            "key": formal["key"], "chainId": "source-1/json", "revision": 2,
            "formalJsonRef": "delivery://revision-2/hug-your-pet/hug-your-pet.json",
            "formalJsonSha256": compiler.sha256_json(formal),
        }
        observations = {}
        for surface, fields in compiler._contract()["deliveryReadback"]["surfaceFields"].items():
            observations[surface] = {
                "deliveryIdentity": copy.deepcopy(identity),
                "observedAt": "2026-09-04T15:00:00+08:00",
                "evidenceRefs": [f"sidecar://readback/{surface}.json"],
                "content": copy.deepcopy(formal if fields == ["*"] else {f: formal[f] for f in fields if f in formal}),
            }
        return identity, observations

    def test_readback_rejects_stale_content_even_when_image_url_is_unchanged(self):
        revised = copy.deepcopy(self.previous)
        revised["title"] = "抱紧你的毛孩子"
        revised["inputSchema"]["slots"][0]["text"]["suggestions"] = ["白猫", "黑猫", "灰猫"]
        identity, observations = self.observations(revised)
        receipt = compiler.validate_delivery_readback(revised, identity, observations)
        self.assertEqual(receipt["status"], "verified_against_delivery")
        _, old = self.observations(self.previous)
        for surface in observations:
            stale = copy.deepcopy(observations)
            stale[surface]["content"] = old[surface]["content"]
            with self.subTest(surface=surface), self.assertRaises(compiler.ContractError):
                compiler.validate_delivery_readback(revised, identity, stale)

    def test_readback_requires_same_chain_revision_and_all_observed_surfaces(self):
        identity, observations = self.observations(self.previous)
        mutations = [
            lambda value: value.pop("export"),
            lambda value: value["detail"]["deliveryIdentity"].update(chainId="other-batch"),
            lambda value: value["export"]["deliveryIdentity"].update(revision=1),
            lambda value: value["list"].update(evidenceRefs=[]),
            lambda value: value["list"].update(observedAt="2026-09-04T15:00:00"),
        ]
        for mutate in mutations:
            changed = copy.deepcopy(observations)
            mutate(changed)
            with self.subTest(mutation=mutate), self.assertRaises(compiler.ContractError):
                compiler.validate_delivery_readback(self.previous, identity, changed)

    def test_readback_preserves_absence_of_optional_formal_fields(self):
        formal = copy.deepcopy(self.previous)
        formal.pop("preprocessSteps")
        identity, observations = self.observations(formal)
        compiler.validate_delivery_readback(formal, identity, observations)
        observations["editPreview"]["content"]["preprocessSteps"] = []
        with self.assertRaises(compiler.ContractError):
            compiler.validate_delivery_readback(formal, identity, observations)

    def test_readback_rejects_json_type_changes_in_nested_content(self):
        for surface in ("detail", "editPreview", "export"):
            for field, value in (("required", 0), ("allowCustom", 1), ("maxCount", "1")):
                identity, observations = self.observations(self.previous)
                slot = observations[surface]["content"]["inputSchema"]["slots"][0]
                if field == "required":
                    slot[field] = value
                elif field == "allowCustom":
                    slot["text"][field] = value
                else:
                    slot["image"][field] = value
                with self.subTest(surface=surface, field=field), self.assertRaises(compiler.ContractError):
                    compiler.validate_delivery_readback(self.previous, identity, observations)

    def test_readback_rejects_boolean_revision_on_every_surface(self):
        for surface in ("list", "detail", "editPreview", "export"):
            identity, observations = self.observations(self.previous)
            identity["revision"] = 1
            for observation in observations.values():
                observation["deliveryIdentity"]["revision"] = 1
            observations[surface]["deliveryIdentity"]["revision"] = True
            with self.subTest(surface=surface), self.assertRaises(compiler.ContractError):
                compiler.validate_delivery_readback(self.previous, identity, observations)

    def test_readback_ignores_object_key_order_but_preserves_array_order(self):
        def reorder_objects(value):
            if isinstance(value, dict):
                return {key: reorder_objects(value[key]) for key in reversed(value)}
            if isinstance(value, list):
                return [reorder_objects(item) for item in value]
            return value

        identity, observations = self.observations(self.previous)
        observations = reorder_objects(observations)
        receipt = compiler.validate_delivery_readback(self.previous, identity, observations)
        self.assertEqual(receipt["status"], "verified_against_delivery")
        observations["export"]["content"]["inputSchema"]["slots"][0]["text"]["suggestions"].reverse()
        with self.assertRaises(compiler.ContractError):
            compiler.validate_delivery_readback(self.previous, identity, observations)


if __name__ == "__main__":
    unittest.main()
