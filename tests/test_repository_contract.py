from __future__ import annotations

import hashlib
import json
import unittest

from helpers import ROOT


class RepositoryContractTests(unittest.TestCase):
    def test_each_skill_declares_its_real_adapter_dependency(self):
        image_requirements = (
            ROOT / "skills/meme-template-image-producer/requirements.txt"
        ).read_text(encoding="utf-8").splitlines()
        json_requirements = (
            ROOT / "skills/meme-template-json-compiler/requirements.txt"
        ).read_text(encoding="utf-8").splitlines()
        self.assertIn("fal-client>=1,<2", image_requirements)
        self.assertIn("httpx>=0.28,<1", image_requirements)
        self.assertIn("oss2>=2.19,<3", json_requirements)

    def test_release_points_to_exact_immutable_snapshot(self):
        release = json.loads((ROOT / "release.json").read_text(encoding="utf-8"))
        gallery = release["galleryContract"]
        snapshot = ROOT / gallery["relativePath"]
        self.assertNotIn("latest", gallery["relativePath"])
        self.assertNotIn("current", gallery["relativePath"])
        self.assertEqual(hashlib.sha256(snapshot.read_bytes()).hexdigest(), gallery["sha256"])
        self.assertEqual(gallery["sha256"], "317ed2444a8109722fd6bdafd00c1f43b66b59096aea8b29d6aecfb2a542f608")
        self.assertEqual(gallery["productionInputSchemaVersion"], 2)
        self.assertEqual(gallery["productionRuntimeSemanticsVersion"], 2)

    def test_t1_and_generation_provider_code_are_absent_from_wrong_places(self):
        executable = list((ROOT / "skills").glob("*/scripts/*.py"))
        for path in executable:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("T1", text, path)
            self.assertNotIn("contentRegenerationModel", text, path)
        compiler_code = (ROOT / "skills/meme-template-json-compiler/scripts/compiler.py").read_text(encoding="utf-8")
        self.assertNotIn("submit_edit", compiler_code)
        self.assertNotIn("openai/gpt-image", compiler_code)
        self.assertNotIn("fal_client", compiler_code.lower())

    def test_generic_runtime_files_have_no_personal_absolute_path(self):
        runtime_files = [
            *ROOT.glob("skills/*/SKILL.md"),
            *ROOT.glob("skills/*/scripts/*.py"),
            *ROOT.glob("skills/*/references/machine-contract.json"),
            *ROOT.glob("contracts/shared/*.json"),
            ROOT / "release.json",
        ]
        personal_prefix = "/" + "Users/"
        for path in runtime_files:
            self.assertNotIn(personal_prefix, path.read_text(encoding="utf-8"), path)

    def test_generated_noise_is_ignored(self):
        patterns = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn(".DS_Store", patterns)
        self.assertIn("__pycache__/", patterns)
        self.assertIn("*.pyc", patterns)

    def test_json_compiler_is_self_contained_when_installed_alone(self):
        skill = ROOT / "skills/meme-template-json-compiler"
        self.assertTrue((skill / "references/contracts/approved-template-image-envelope.schema.json").is_file())
        snapshot = skill / "references/contracts/gallery-template.schema.json"
        self.assertTrue(snapshot.is_file())
        self.assertEqual(
            set((skill / "requirements.txt").read_text(encoding="utf-8").splitlines()),
            {"jsonschema>=4.26,<5", "oss2>=2.19,<3"},
        )
        self.assertEqual(
            hashlib.sha256(snapshot.read_bytes()).hexdigest(),
            "317ed2444a8109722fd6bdafd00c1f43b66b59096aea8b29d6aecfb2a542f608",
        )
        self.assertEqual(
            (skill / "references/contracts/approved-template-image-envelope.schema.json").read_bytes(),
            (ROOT / "contracts/shared/approved-template-image-envelope.schema.json").read_bytes(),
        )

    def test_both_skills_bundle_their_portable_runtime_contracts(self):
        producer = ROOT / "skills/meme-template-image-producer/references/contracts"
        compiler = ROOT / "skills/meme-template-json-compiler/references/contracts"
        shared = ROOT / "contracts/shared"
        self.assertEqual(
            (producer / "approved-template-image-envelope.schema.json").read_bytes(),
            (shared / "approved-template-image-envelope.schema.json").read_bytes(),
        )
        self.assertEqual(
            (producer / "image-revision-review-context.schema.json").read_bytes(),
            (shared / "image-revision-review-context.schema.json").read_bytes(),
        )
        for skill_contract in (producer / "production-index.schema.json", compiler / "production-index.schema.json"):
            self.assertEqual(skill_contract.read_bytes(), (shared / "production-index.schema.json").read_bytes())
        self.assertEqual(
            (compiler / "key-registry.schema.json").read_bytes(),
            (shared / "key-registry.schema.json").read_bytes(),
        )
        self.assertEqual(
            (compiler / "data-workbench-runtime-envelope.schema.json").read_bytes(),
            (shared / "data-workbench-runtime-envelope.schema.json").read_bytes(),
        )


if __name__ == "__main__":
    unittest.main()
