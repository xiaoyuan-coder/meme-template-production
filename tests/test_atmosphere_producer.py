from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from helpers import ROOT, load_module


allocator = load_module(
    "atmosphere_allocator",
    "skills/template-atmosphere-image-producer/scripts/allocate_batch.py",
)
finalizer = load_module(
    "atmosphere_finalizer",
    "skills/template-atmosphere-image-producer/scripts/finalize_atmosphere.py",
)
workflow = load_module(
    "atmosphere_workflow",
    "skills/template-atmosphere-image-producer/scripts/atmosphere_workflow.py",
)


class AtmosphereProducerTests(unittest.TestCase):
    def test_public_oss_domain_normalizes_to_https(self):
        self.assertEqual(
            finalizer.normalize_public_domain("assets.memebuy.cn/"),
            "https://assets.memebuy.cn",
        )
        with self.assertRaises(finalizer.FinalizationError):
            finalizer.normalize_public_domain("http://assets.memebuy.cn")

    def valid_plan(self, root: Path) -> dict:
        template = root / "template.png"
        style = root / "style.jpg"
        template.write_bytes(b"template")
        style.write_bytes(b"style")
        return {
            "planContractVersion": "2.0.0",
            "candidateId": "candidate-a",
            "templateKey": "template-a",
            "topicRoute": "standalone_print",
            "styleTranslation": {
                "styleInvariants": ["soft daylight", "clean midtones", "natural posture"],
                "deliberateVariations": [
                    {"dimension": "scene_topology", "change": "new room"},
                    {"dimension": "human_action", "change": "walking"},
                    {"dimension": "camera_geometry", "change": "medium view"},
                ],
            },
            "styleFingerprint": {
                "whitePoint": "neutral", "dominantColorArea": "warm wall",
                "midtoneSeparation": "clear", "shadowHue": "cool neutral",
                "highlightRollOff": "soft", "textureDistribution": "fabric and wall",
                "humanState": "unposed",
            },
            "photographicTruth": {
                "ordinaryActivity": "walking", "subjectOwnIntent": "leaving home",
                "secondarySubjectOwnIntent": "none", "momentBefore": "picked up bag",
                "momentAfter": "opens door", "productRemovedPhotoStillWorks": True,
                "cameraIgnored": True,
            },
            "generationStrategy": {"mode": "one_pass", "generationPrompt": "Natural lifestyle photo."},
            "productDesign": {
                "carrier": "tshirt", "carrierColor": "cream", "printSide": "front",
                "backgroundTreatment": "remove exterior white", "relativeScale": "restrained",
                "materialRendering": "ink follows folds", "visibilityGuard": "readable thumbnail",
            },
            "sceneDirection": {
                "actorStructure": "single model", "singleModelGender": "female",
                "livedEvent": "leaving home", "mainAction": "walking",
                "semanticEcho": "one color echo", "cameraDistance": "medium",
            },
            "referenceBindings": {
                "templateReferencePath": str(template), "styleReferencePath": str(style),
            },
            "referenceDistanceAudit": {
                "sceneTopologyChanged": True, "subjectSilhouetteChanged": True,
                "mainActionChanged": True, "retainedSimilaritySource": "light and texture only",
            },
        }

    def test_hundred_item_batch_hits_locked_ratios(self):
        records = [
            {
                "templateKey": f"template-{index:03d}",
                "topicRoute": "pet_product" if index < 20 else "standalone_print",
                "singleModel": True,
            }
            for index in range(100)
        ]
        result = allocator.allocate(records, 0.85)
        self.assertEqual(
            result["actualCounts"]["carrier"],
            {"tshirt": 20, "long_sleeve": 20, "sweatshirt": 20, "canvas_bag": 20, "other": 20},
        )
        self.assertEqual(result["actualCounts"]["singleModelGender"], {"male": 30, "female": 70})
        self.assertEqual(result["actualCounts"]["cameraDistance"], {"close": 20, "medium": 50, "environment": 30})
        self.assertEqual(result["actualCounts"]["printSide"], {"front": 48, "back": 12})
        self.assertEqual(result["actualCounts"]["petVisibility"], {"visible": 17, "not_visible": 3})

    def test_backfill_changes_only_image_url_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.json"
            receipt = root / "receipt.json"
            output = root / "output.json"
            formal = {"key": "template-a", "title": "A"}
            url = "https://assets.memebuy.cn/memebuy/template-atmosphere/sha256/abc.png"
            source.write_text(json.dumps(formal), encoding="utf-8")
            receipt.write_text(json.dumps({
                "templateKey": "template-a", "imageUrl": url, "objectKey": "abc.png",
                "sha256": "a" * 64, "byteLength": 10, "status": "uploaded_verified",
                "publicReadbackSha256": "a" * 64,
            }), encoding="utf-8")
            finalizer.command_backfill(SimpleNamespace(
                source_json=str(source), receipt=str(receipt), output_json=str(output),
                allow_replacement=False,
            ))
            revised = json.loads(output.read_text())
            self.assertEqual(revised, {**formal, "imageUrl": url})

            source.write_text(json.dumps({**formal, "imageUrl": "https://example.com/old.png"}), encoding="utf-8")
            with self.assertRaises(finalizer.FinalizationError):
                finalizer.command_backfill(SimpleNamespace(
                    source_json=str(source), receipt=str(receipt), output_json=str(root / "other.json"),
                    allow_replacement=False,
                ))

    def test_plan_requires_one_pass_and_keeps_pet_fields_on_pet_routes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = self.valid_plan(root)
            path = root / "plan.json"
            path.write_text(json.dumps(plan), encoding="utf-8")
            self.assertEqual(workflow.validate_plan_contract(path)["generationMode"], "one_pass")

            plan["generationStrategy"]["mode"] = "two_stage"
            path.write_text(json.dumps(plan), encoding="utf-8")
            with self.assertRaises(workflow.WorkflowError):
                workflow.validate_plan_contract(path)

            plan["generationStrategy"]["mode"] = "one_pass"
            plan["petDirection"] = {"route": "print_led", "petVisible": False}
            path.write_text(json.dumps(plan), encoding="utf-8")
            with self.assertRaises(workflow.WorkflowError):
                workflow.validate_plan_contract(path)

    def test_prune_keeps_selected_and_removes_other_candidates_after_readback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selected = root / "candidates" / "selected.png"
            rejected = root / "candidates" / "rejected.png"
            generated = root / "candidates" / "rejected-source.png"
            selected.parent.mkdir()
            selected.write_bytes(b"selected-final-bytes")
            rejected.write_bytes(b"rejected")
            generated.write_bytes(b"generation-source")
            url = "https://assets.memebuy.cn/memebuy/template-atmosphere/sha256/final.png"
            digest = hashlib.sha256(selected.read_bytes()).hexdigest()
            (root / "batch.json").write_text(json.dumps({
                "candidates": [
                    {"templateKey": "template-a", "candidateId": "selected", "decision": "good_case", "imagePath": str(selected)},
                    {"templateKey": "template-a", "candidateId": "other", "decision": "rejected", "imagePath": str(rejected), "generationSourcePath": str(generated)},
                ]
            }), encoding="utf-8")
            receipt = root / "receipt.json"
            receipt.write_text(json.dumps({
                "templateKey": "template-a", "imageUrl": url, "objectKey": "final.png",
                "sha256": digest, "byteLength": selected.stat().st_size,
                "status": "uploaded_verified", "publicReadbackSha256": digest,
            }), encoding="utf-8")
            current = root / "current.json"
            current.write_text(json.dumps({"key": "template-a", "imageUrl": url}), encoding="utf-8")
            args = SimpleNamespace(
                batch_dir=str(root), template_key="template-a", selected_candidate_id="selected",
                receipt=str(receipt), current_json=str(current), cleanup_receipt=str(root / "cleanup.json"),
            )
            first = finalizer.command_prune(args)
            second = finalizer.command_prune(args)
            self.assertEqual(first, second)
            self.assertTrue(selected.is_file())
            self.assertFalse(rejected.exists())
            self.assertFalse(generated.exists())

    def test_prune_refuses_candidate_paths_outside_batch(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside_directory:
            root = Path(directory)
            selected = root / "selected.png"
            selected.write_bytes(b"selected")
            outside = Path(outside_directory) / "do-not-delete.png"
            outside.write_bytes(b"outside")
            internal = root / "also-do-not-delete.png"
            internal.write_bytes(b"internal")
            digest = hashlib.sha256(selected.read_bytes()).hexdigest()
            url = "https://assets.memebuy.cn/memebuy/template-atmosphere/sha256/final.png"
            (root / "batch.json").write_text(json.dumps({"candidates": [
                {"templateKey": "template-a", "candidateId": "selected", "decision": "approved", "imagePath": str(selected)},
                {"templateKey": "template-a", "candidateId": "internal", "decision": "rejected", "imagePath": str(internal)},
                {"templateKey": "template-a", "candidateId": "other", "decision": "rejected", "imagePath": str(outside)},
            ]}), encoding="utf-8")
            receipt = root / "receipt.json"
            receipt.write_text(json.dumps({
                "templateKey": "template-a", "imageUrl": url, "objectKey": "final.png",
                "sha256": digest, "byteLength": selected.stat().st_size,
                "status": "reused_verified", "publicReadbackSha256": digest,
            }), encoding="utf-8")
            current = root / "current.json"
            current.write_text(json.dumps({"key": "template-a", "imageUrl": url}), encoding="utf-8")
            with self.assertRaises(finalizer.FinalizationError):
                finalizer.command_prune(SimpleNamespace(
                    batch_dir=str(root), template_key="template-a", selected_candidate_id="selected",
                    receipt=str(receipt), current_json=str(current), cleanup_receipt=str(root / "cleanup.json"),
                ))
            self.assertTrue(outside.is_file())
            self.assertTrue(internal.is_file())


if __name__ == "__main__":
    unittest.main()
