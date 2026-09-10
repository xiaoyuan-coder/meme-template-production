from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

from helpers import ROOT, valid_formal_draft
from test_json_compiler import valid_image_envelope


SCRIPT_DIR = ROOT / "skills/meme-template-json-compiler/scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import compiler
import current_registry


class CurrentTemplateRegistryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.formal = compiler.project_formal_json(valid_formal_draft(), valid_image_envelope())

    def promotion(self, revision=1, previous=None, when="2026-09-10T10:00:00+08:00"):
        return {
            "chainId": "direct-source-1/json",
            "revision": revision,
            "formalJsonRef": f"delivery://revision-{revision}/hug-your-pet/hug-your-pet.json",
            "promotedAt": when,
            "expectedPreviousFormalJsonSha256": previous,
        }

    def test_promotion_materializes_one_current_view_and_authoritative_object(self):
        receipt = current_registry.promote_current_template(
            self.root, self.formal, self.promotion()
        )
        self.assertEqual(receipt["status"], "promoted")
        registry = current_registry.read_current_template_registry(self.root)
        record = registry["records"][0]
        self.assertEqual(record["key"], self.formal["key"])
        self.assertEqual(record["formalJsonSha256"], compiler.sha256_json(self.formal))
        self.assertEqual(json.loads((self.root / record["objectRef"]).read_text()), self.formal)
        self.assertEqual(json.loads((self.root / record["currentTemplateRef"]).read_text()), self.formal)
        self.assertEqual(
            current_registry.locate_current_template(self.root, self.formal["key"])["matchedBy"],
            "key",
        )
        self.assertEqual(
            current_registry.locate_current_template(self.root, self.formal["title"])["formal"],
            self.formal,
        )
        self.assertEqual(
            current_registry.promote_current_template(self.root, self.formal, self.promotion())["status"],
            "already_current",
        )

    def test_portable_publish_creates_and_replaces_by_key_without_a_workbench(self):
        decision = current_registry.resolve_template_key(self.root, self.formal["key"])
        self.assertEqual(decision["decision"], "NEW")
        first = current_registry.publish_template(
            self.root, self.formal, published_at="2026-09-10T10:00:00+08:00"
        )
        self.assertEqual(first["record"]["chainId"], self.formal["key"])
        self.assertEqual(first["record"]["revision"], 1)
        self.assertTrue((self.root / first["record"]["formalJsonRef"].replace("history://", "history/")).is_file())
        self.assertEqual(
            current_registry.resolve_template_key(
                self.root, self.formal["key"], existing_key=self.formal["key"]
            )["decision"],
            "EXISTING_KEY",
        )
        self.assertEqual(
            current_registry.resolve_template_key(self.root, self.formal["key"])["decision"],
            "KEY_COLLISION",
        )

        revised = copy.deepcopy(self.formal)
        revised["title"] = "抱紧你的毛孩子"
        with self.assertRaises(compiler.ContractError):
            current_registry.publish_template(
                self.root, revised, published_at="2026-09-10T10:01:00+08:00"
            )
        second = current_registry.publish_template(
            self.root,
            revised,
            published_at="2026-09-10T10:01:00+08:00",
            expected_previous_formal_sha256=first["record"]["formalJsonSha256"],
        )
        self.assertEqual(second["record"]["revision"], 2)
        self.assertEqual(current_registry.locate_current_template(self.root, self.formal["key"])["formal"], revised)
        self.assertEqual(len(list((self.root / "history" / self.formal["key"]).glob("*/*.json"))), 2)

    def test_key_identity_allows_a_replacement_image(self):
        first = current_registry.publish_template(
            self.root, self.formal, published_at="2026-09-10T10:00:00+08:00"
        )
        revised = copy.deepcopy(self.formal)
        replacement = "https://assets.memebuy.cn/gallery/template-images/" + "b" * 64 + ".png"
        revised["cover"] = replacement
        revised["referenceImage"] = replacement
        second = current_registry.publish_template(
            self.root,
            revised,
            published_at="2026-09-10T10:01:00+08:00",
            expected_previous_formal_sha256=first["record"]["formalJsonSha256"],
        )
        self.assertEqual(second["record"]["key"], self.formal["key"])
        self.assertEqual(second["record"]["sourceImageSha256"], "b" * 64)

    def test_portable_reader_rejects_tampered_or_redirected_history(self):
        receipt = current_registry.publish_template(
            self.root, self.formal, published_at="2026-09-10T10:00:00+08:00"
        )
        history = self.root / receipt["record"]["formalJsonRef"].replace("history://", "history/")
        history.write_text("{}", encoding="utf-8")
        with self.assertRaises(compiler.ContractError):
            current_registry.read_current_template_registry(self.root)
        history.unlink()
        history.parent.rmdir()
        outside = self.root / "outside"
        outside.mkdir()
        history.parent.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(compiler.ContractError):
            current_registry.read_current_template_registry(self.root)

    def test_compare_and_set_and_chain_revision_prevent_stale_current_overwrite(self):
        with self.assertRaises(compiler.ContractError):
            current_registry.promote_current_template(
                self.root, self.formal, self.promotion(2)
            )
        first = current_registry.promote_current_template(self.root, self.formal, self.promotion())
        previous = first["record"]["formalJsonSha256"]
        revised = copy.deepcopy(self.formal)
        revised["title"] = "抱紧你的毛孩子"
        with self.assertRaises(compiler.ContractError):
            current_registry.promote_current_template(
                self.root, revised, self.promotion(2, "0" * 64)
            )
        with self.assertRaises(compiler.ContractError):
            current_registry.promote_current_template(
                self.root, revised, dict(self.promotion(3, previous), revision=3)
            )
        receipt = current_registry.promote_current_template(
            self.root, revised, self.promotion(2, previous, "2026-09-10T10:01:00+08:00")
        )
        self.assertEqual(receipt["status"], "promoted")
        self.assertEqual(current_registry.read_current_template_registry(self.root)["records"][0]["revision"], 2)

    def test_reader_rejects_tampered_authoritative_object(self):
        receipt = current_registry.promote_current_template(self.root, self.formal, self.promotion())
        object_path = self.root / receipt["record"]["objectRef"]
        changed = copy.deepcopy(self.formal)
        changed["title"] = "被篡改"
        object_path.write_text(json.dumps(changed), encoding="utf-8")
        with self.assertRaises(compiler.ContractError):
            current_registry.read_current_template_registry(self.root)

    def test_reader_rejects_tampered_current_mirror(self):
        receipt = current_registry.promote_current_template(self.root, self.formal, self.promotion())
        mirror_path = self.root / receipt["record"]["currentTemplateRef"]
        mirror_path.write_text("{}", encoding="utf-8")
        with self.assertRaises(compiler.ContractError):
            current_registry.read_current_template_registry(self.root)

    def test_shared_and_bundled_registry_contracts_are_identical(self):
        shared = ROOT / "contracts/shared/current-template-registry.schema.json"
        bundled = ROOT / "skills/meme-template-json-compiler/references/contracts/current-template-registry.schema.json"
        self.assertEqual(shared.read_bytes(), bundled.read_bytes())

    def test_read_does_not_create_a_missing_registry_root(self):
        missing = self.root / "missing"
        with self.assertRaises(compiler.ContractError):
            current_registry.read_current_template_registry(missing)
        self.assertFalse(missing.exists())

    def test_bootstrap_discovery_deduplicates_content_without_selecting_a_winner(self):
        roots = []
        for name, formal, revision in (
            ("first", self.formal, 3),
            ("duplicate", self.formal, 7),
            ("different", dict(self.formal, title="抱紧你的毛孩子"), 2),
        ):
            root = self.root / name
            compiler.write_formal_json(root / "delivery", formal)
            compiler.write_production_index(root, [{
                "itemId": name,
                "skill": "meme-template-json-compiler",
                "state": "delivered",
                "revision": revision,
                "stage": "json_compiler",
                "artifacts": {
                    "formalJson": f"delivery://{formal['key']}/{formal['key']}.json"
                },
            }], generated_at="2026-09-10T10:00:00+08:00")
            roots.append(root)
        candidates = current_registry.discover_bootstrap_candidates(
            roots, self.formal["key"]
        )
        self.assertEqual(len(candidates), 2)
        self.assertEqual(sorted(len(item["historyRefs"]) for item in candidates), [1, 2])
        self.assertEqual({item["key"] for item in candidates}, {self.formal["key"]})


if __name__ == "__main__":
    unittest.main()
