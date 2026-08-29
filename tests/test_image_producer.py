from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from helpers import PNG_BYTES, ROOT, SOURCE_IMAGE, SOURCE_INPUT_BYTES, load_module, valid_strategy


producer = load_module(
    "image_producer",
    "skills/meme-template-image-producer/scripts/producer.py",
)


class FakeFal:
    def __init__(self):
        self.calls = []

    def submit_edit(self, model, payload):
        self.calls.append((model, payload))
        return {"request_id": "fake-request"}


def valid_request():
    return {
        "model": "openai/gpt-image-2/edit",
        "quality": "low",
        "num_images": 1,
        "output_format": "png",
        "image_size": "1152x896",
        "input_image_url": "fixture://source.png",
        "prompt": "Replace the subject and preserve the visible composition.",
    }


def valid_evidence(*, failed_gate=None):
    return [
        {
            "gate": gate,
            "passed": gate != failed_gate,
            "summary": f"machine evidence for {gate}",
        }
        for gate in producer.required_image_review_gates()
    ]


def valid_strategy_approval(strategy):
    package = producer.build_strategy_review_package(strategy)
    return {
        "decision": "APPROVED",
        "objectSha256": package["objectSha256"],
        "strategySha256": package["strategySha256"],
        "promptSha256": package["promptSha256"],
        "sourceImageSha256": package["sourceImageSha256"],
        "inputUriSha256": package["inputUriSha256"],
        "reviewerRef": "reviewer://strategy/test",
        "decidedAt": "2026-08-29T10:00:00Z",
        "ruleVersion": strategy["ruleVersion"],
        "revision": strategy["revision"],
    }


def valid_image_approval(package):
    return {
        "decision": "APPROVED",
        "objectSha256": package["generatedImage"]["sha256"],
        "reviewPackageSha256": producer.sha256_json(package),
        "reviewerRef": "reviewer://image/test",
        "decidedAt": "2026-08-29T10:30:00Z",
        "ruleVersion": package["ruleVersion"],
        "revision": package["revision"],
    }


class ImageProducerTests(unittest.TestCase):
    def test_strategy_review_can_publish_portable_workbench_index(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = producer.write_production_index(
                root,
                [{
                    "itemId": "material-1631",
                    "skill": "meme-template-image-producer",
                    "state": "awaiting_strategy_approval",
                    "revision": 1,
                    "stage": "strategy_review",
                    "artifacts": {
                        "strategyReview": "sidecar://material-1631/replacement-strategy-review-r0001.json",
                    },
                }],
                generated_at="2026-08-29T12:00:00Z",
            )
            value = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(value["items"][0]["skill"], "meme-template-image-producer")
            self.assertEqual(value["items"][0]["state"], "awaiting_strategy_approval")
            self.assertEqual(target, (root / "index" / "production-index.json").resolve())

    def test_exact_fal_contract_and_custom_size(self):
        adapter = FakeFal()
        producer.submit_generation_request(valid_request(), adapter)
        self.assertEqual(len(adapter.calls), 1)
        model, payload = adapter.calls[0]
        self.assertEqual(model, "openai/gpt-image-2/edit")
        self.assertEqual(payload["quality"], "low")
        self.assertEqual(payload["num_images"], 1)
        self.assertEqual(payload["output_format"], "png")
        self.assertEqual(payload["image_size"], {"width": 1152, "height": 896})

    def test_every_generation_deviation_fails_before_api_request(self):
        changes = {
            "model": ["openai/gpt-image-2", "auto"],
            "quality": ["medium", "high", "auto"],
            "num_images": [2],
            "output_format": ["jpeg"],
            "image_size": ["auto", "landscape_4_3", "2048x2048"],
            "input_image_url": ["", None],
            "prompt": ["", "   ", None],
        }
        for field, invalid_values in changes.items():
            for invalid in invalid_values:
                with self.subTest(field=field, invalid=invalid):
                    request = valid_request()
                    request[field] = invalid
                    adapter = FakeFal()
                    with self.assertRaises(producer.ContractError):
                        producer.submit_generation_request(request, adapter)
                    self.assertEqual(adapter.calls, [])

        omitted_quality = valid_request()
        del omitted_quality["quality"]
        adapter = FakeFal()
        with self.assertRaises(producer.ContractError):
            producer.submit_generation_request(omitted_quality, adapter)
        self.assertEqual(adapter.calls, [])

        extra = valid_request()
        extra["provider_preset"] = "landscape_4_3"
        adapter = FakeFal()
        with self.assertRaises(producer.ContractError):
            producer.submit_generation_request(extra, adapter)
        self.assertEqual(adapter.calls, [])

    def test_replacement_and_strategy_approval_are_required(self):
        strategy = valid_strategy(producer)
        adapter = FakeFal()
        with self.assertRaises(producer.ContractError):
            producer.submit_authorized_generation(
                strategy, {}, adapter, "fixture://source.png",
                input_image_bytes=SOURCE_INPUT_BYTES, attempt_state={},
            )
        self.assertEqual(adapter.calls, [])
        approval = valid_strategy_approval(strategy)
        attempt = {}
        producer.submit_authorized_generation(
            strategy, approval, adapter, "fixture://source.png",
            input_image_bytes=SOURCE_INPUT_BYTES, attempt_state=attempt,
        )
        self.assertEqual(len(adapter.calls), 1)
        self.assertTrue(adapter.calls[0][1]["image_urls"][0].startswith("data:image/png;base64,"))
        self.assertNotIn("fixture://source.png", adapter.calls[0][1]["image_urls"])
        producer.submit_authorized_generation(
            strategy, approval, adapter, "fixture://source.png",
            input_image_bytes=SOURCE_INPUT_BYTES, attempt_state=attempt,
        )
        self.assertEqual(len(adapter.calls), 1)
        self.assertEqual(attempt["state"], "provider_pending")
        attempt_schema = json.loads((
            ROOT / "skills/meme-template-image-producer/references/contracts/generation-attempt.schema.json"
        ).read_text(encoding="utf-8"))
        Draft202012Validator(attempt_schema).validate(attempt)
        self.assertEqual(attempt["providerResponse"], {"request_id": "fake-request"})
        invalid = copy.deepcopy(strategy)
        invalid["replacementValue"] = ""
        with self.assertRaises(producer.ContractError):
            producer.validate_replacement_strategy(invalid)

    def test_submission_unknown_never_speculatively_resubmits(self):
        class UnknownFal(FakeFal):
            def submit_edit(self, model, payload):
                super().submit_edit(model, payload)
                raise TimeoutError("outcome unknown")

        strategy = valid_strategy(producer)
        approval = valid_strategy_approval(strategy)
        adapter, attempt = UnknownFal(), {}
        with self.assertRaises(TimeoutError):
            producer.submit_authorized_generation(
                strategy, approval, adapter, "fixture://source.png",
                input_image_bytes=SOURCE_INPUT_BYTES, attempt_state=attempt,
            )
        self.assertEqual(attempt["state"], "submission_unknown")
        with self.assertRaises(producer.ContractError):
            producer.submit_authorized_generation(
                strategy, approval, adapter, "fixture://source.png",
                input_image_bytes=SOURCE_INPUT_BYTES, attempt_state=attempt,
            )
        self.assertEqual(len(adapter.calls), 1)

    def test_input_hosting_failure_can_resume_same_approval_before_generation_post(self):
        class HostingFal(FakeFal):
            def __init__(self):
                super().__init__()
                self.hosting_ready = False

            def submit_edit(self, model, payload):
                self.calls.append((model, payload))
                if not self.hosting_ready:
                    raise producer.InputHostingError("input hosting failed")
                return {"request_id": "fake-request"}

        strategy = valid_strategy(producer)
        approval = valid_strategy_approval(strategy)
        adapter, attempt = HostingFal(), {}
        with self.assertRaises(producer.InputHostingError):
            producer.submit_authorized_generation(
                strategy, approval, adapter, "fixture://source.png",
                input_image_bytes=SOURCE_INPUT_BYTES, attempt_state=attempt,
            )
        self.assertEqual(attempt["state"], "input_hosting_failed")
        schema = json.loads((
            ROOT / "skills/meme-template-image-producer/references/contracts/generation-attempt.schema.json"
        ).read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(attempt)

        adapter.hosting_ready = True
        response = producer.submit_authorized_generation(
            strategy, approval, adapter, "fixture://source.png",
            input_image_bytes=SOURCE_INPUT_BYTES, attempt_state=attempt,
        )
        self.assertEqual(response, {"request_id": "fake-request"})
        self.assertEqual(attempt["state"], "provider_pending")
        self.assertEqual(len(adapter.calls), 2)

    def test_provider_http_failure_is_redacted_classified_and_not_resubmitted(self):
        class RejectedFal(FakeFal):
            def submit_edit(self, model, payload):
                super().submit_edit(model, payload)
                raise producer.ExternalAdapterError(
                    "FAL submission was rejected (HTTP 422)",
                    status_code=422,
                    error_type="validation_error",
                    outcome_known=True,
                )

        strategy = valid_strategy(producer)
        approval = valid_strategy_approval(strategy)
        adapter, attempt = RejectedFal(), {}
        with self.assertRaises(producer.ExternalAdapterError):
            producer.submit_authorized_generation(
                strategy, approval, adapter, "fixture://source.png",
                input_image_bytes=SOURCE_INPUT_BYTES, attempt_state=attempt,
            )
        self.assertEqual(attempt["state"], "provider_rejected")
        self.assertEqual(attempt["providerFailure"], {
            "statusCode": 422,
            "errorType": "validation_error",
        })
        with self.assertRaises(producer.ContractError):
            producer.submit_authorized_generation(
                strategy, approval, adapter, "fixture://source.png",
                input_image_bytes=SOURCE_INPUT_BYTES, attempt_state=attempt,
            )
        self.assertEqual(len(adapter.calls), 1)
        schema = json.loads((
            ROOT / "skills/meme-template-image-producer/references/contracts/generation-attempt.schema.json"
        ).read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(attempt)

    def test_complete_fal_history_can_close_unknown_without_restoring_approval(self):
        class UnknownFal(FakeFal):
            def submit_edit(self, model, payload):
                super().submit_edit(model, payload)
                raise TimeoutError("outcome unknown")

        strategy = valid_strategy(producer)
        approval = valid_strategy_approval(strategy)
        adapter, attempt = UnknownFal(), {}
        with self.assertRaises(TimeoutError):
            producer.submit_authorized_generation(
                strategy, approval, adapter, "fixture://source.png",
                input_image_bytes=SOURCE_INPUT_BYTES, attempt_state=attempt,
            )
        producer.record_no_request_reconciliation(attempt, {
            "source": "fal_request_history",
            "endpoint": "openai/gpt-image-2/edit",
            "windowStart": "2026-08-29T07:25:00Z",
            "windowEnd": "2026-08-29T07:35:00Z",
            "checkedAt": "2026-08-29T07:36:00Z",
            "queryComplete": True,
            "observedRequestIds": [],
        })
        self.assertEqual(attempt["state"], "provider_rejected")
        self.assertEqual(attempt["reconciliation"]["conclusion"], "no_request_created")
        with self.assertRaises(producer.ContractError):
            producer.submit_authorized_generation(
                strategy, approval, adapter, "fixture://source.png",
                input_image_bytes=SOURCE_INPUT_BYTES, attempt_state=attempt,
            )
        self.assertEqual(len(adapter.calls), 1)
        schema = json.loads((
            ROOT / "skills/meme-template-image-producer/references/contracts/generation-attempt.schema.json"
        ).read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(attempt)

    def test_revision_projection_is_read_only_and_does_not_inherit_verdict(self):
        history = [{
            "revision": 1,
            "generatedImage": {"uri": "fixture://r1.png", "sha256": "1" * 64},
            "reasonCodes": ["LEGACY_IDENTITY_REMAINS"],
            "humanNote": "仍保留旧主体。",
            "decidedAt": "2026-08-29T20:18:00+08:00",
            "reviewerRef": "reviewer://image/history",
            "visualReviewSha256": "2" * 64,
            "failureClass": "visual_rejection",
            "decision": "REJECTED",
        }]
        context = producer.build_revision_review_context(
            history,
            2,
            [{"reasonCode": "LEGACY_IDENTITY_REMAINS", "treatment": "redraw full identity closure"}],
        )
        self.assertTrue(context["previousRevision"]["readOnly"])
        self.assertEqual(context["previousVisualReviewSha256"], "2" * 64)
        self.assertEqual(context["previousFailedGates"], ["LEGACY_IDENTITY_REMAINS"])
        self.assertTrue(context["fullHistory"]["collapsedByDefault"])
        self.assertNotIn("decision", context["currentCorrectionPlan"])
        self.assertEqual(history[0]["decision"], "REJECTED")
        with self.assertRaises(producer.ContractError):
            producer.build_revision_review_context(history, 2, [])

    def test_only_fresh_human_image_review_creates_minimal_envelope(self):
        digest = producer.sha256_bytes(PNG_BYTES)
        context = producer.build_revision_review_context([], 1, [])
        package = producer.build_image_review_package(
            PNG_BYTES,
            SOURCE_IMAGE,
            {"uri": "fixture://approved.png", "width": 1024, "height": 1024},
            item_id="item-a", rule_version="0.2.0", revision=1,
            evidence=valid_evidence(),
            hard_failures=[], warnings=[], revision_context=context,
        )
        review = valid_image_approval(package)
        envelope = producer.approve_generated_png(
            PNG_BYTES,
            review,
            package,
            rule_version="0.2.0",
            revision=1,
        )
        self.assertEqual(set(envelope), {"schemaVersion", "status", "image"})
        self.assertEqual(set(envelope["image"]), {"uri", "sha256", "width", "height", "mime"})
        with self.assertRaises(producer.ContractError):
            producer.approve_generated_png(
                PNG_BYTES,
                {**review, "objectSha256": "0" * 64},
                package,
                rule_version="0.2.0",
                revision=1,
            )

    def test_image_approval_rule_and_revision_are_fresh(self):
        digest = producer.sha256_bytes(PNG_BYTES)
        facts = {"uri": "fixture://approved.png", "width": 1024, "height": 1024}
        package = producer.build_image_review_package(
            PNG_BYTES, SOURCE_IMAGE, facts, item_id="item-a", rule_version="0.2.0", revision=1,
            evidence=valid_evidence(), hard_failures=[], warnings=[],
            revision_context=producer.build_revision_review_context([], 1, []),
        )
        for changed in ({"ruleVersion": "0.3.0"}, {"revision": 2}):
            review = valid_image_approval(package)
            review.update(changed)
            with self.assertRaises(producer.ContractError):
                producer.approve_generated_png(
                    PNG_BYTES, review, package, rule_version="0.2.0", revision=1
                )

    def test_category_group_closure_and_marks_are_machine_gated(self):
        strategy = valid_strategy(producer)
        producer.validate_replacement_strategy(strategy)

        cross_species = copy.deepcopy(strategy)
        cross_species["selectedCategory"] = "dog"
        with self.assertRaises(producer.ContractError):
            producer.validate_replacement_strategy(cross_species)

        missing_member = copy.deepcopy(strategy)
        missing_member["sourceIdentityUnitIds"].append("cat-b")
        with self.assertRaises(producer.ContractError):
            producer.validate_replacement_strategy(missing_member)

        blanket_cleanup = copy.deepcopy(strategy)
        blanket_cleanup["markActions"][1]["action"] = "remove_with_reason"
        with self.assertRaises(producer.ContractError):
            producer.validate_replacement_strategy(blanket_cleanup)

    def test_prompt_sections_are_canonical_and_canvas_size_is_deterministic(self):
        strategy = valid_strategy(producer)
        package = producer.build_strategy_review_package(strategy)
        self.assertEqual(package["state"], "awaiting_strategy_approval")
        self.assertEqual(package["expectedFalCalls"], 1)
        self.assertEqual(strategy["prompt"].count("任务："), 1)
        changed = copy.deepcopy(strategy)
        changed["prompt"] += "\nextra"
        with self.assertRaises(producer.ContractError):
            producer.validate_replacement_strategy(changed)
        self.assertEqual(producer.select_image_size(1600, 900), "1344x768")

    def test_review_packages_validate_against_bundled_schemas(self):
        strategy_package = producer.build_strategy_review_package(valid_strategy(producer))
        strategy_schema = json.loads((
            ROOT / "skills/meme-template-image-producer/references/contracts/"
            "replacement-strategy-review.schema.json"
        ).read_text(encoding="utf-8"))
        Draft202012Validator(strategy_schema).validate(strategy_package)

        image_package = producer.build_image_review_package(
            PNG_BYTES, SOURCE_IMAGE,
            {"uri": "fixture://approved.png", "width": 1024, "height": 1024},
            item_id="item-a", rule_version="0.2.0", revision=1,
            evidence=valid_evidence(), hard_failures=[], warnings=[],
            revision_context=producer.build_revision_review_context([], 1, []),
        )
        image_schema = json.loads((
            ROOT / "skills/meme-template-image-producer/references/contracts/"
            "image-review-package.schema.json"
        ).read_text(encoding="utf-8"))
        Draft202012Validator(image_schema).validate(image_package)

    def test_batch_diversity_allocation_is_order_independent(self):
        first = producer.allocate_replacement_fingerprints({
            "item-b": ["ip-a", "ip-b"],
            "item-a": ["ip-a", "ip-b"],
            "item-c": ["ip-a", "ip-b"],
        })
        reordered = producer.allocate_replacement_fingerprints({
            "item-c": ["ip-b", "ip-a"],
            "item-a": ["ip-b", "ip-a"],
            "item-b": ["ip-b", "ip-a"],
        })
        self.assertEqual(first, reordered)
        self.assertEqual(set(first), {"item-a", "item-b", "item-c"})

    def test_visual_hard_failure_cannot_be_human_overridden(self):
        digest = producer.sha256_bytes(PNG_BYTES)
        facts = {"uri": "fixture://bad.png", "width": 1024, "height": 1024}
        package = producer.build_image_review_package(
            PNG_BYTES, SOURCE_IMAGE, facts, item_id="item-a", rule_version="0.2.0", revision=1,
            evidence=valid_evidence(failed_gate="identity_group_complete"),
            hard_failures=[{"code": "MEMBER_MISSING"}], warnings=[],
            revision_context=producer.build_revision_review_context([], 1, []),
        )
        review = valid_image_approval(package)
        with self.assertRaises(producer.ContractError):
            producer.approve_generated_png(
                PNG_BYTES, review, package, rule_version="0.2.0", revision=1
            )

    def test_image_batch_isolation_and_bounds(self):
        items = [{"itemId": "bad", "revision": 1}, {"itemId": "good", "revision": 1}]

        def process(item):
            if item["itemId"] == "bad":
                raise producer.ContractError("strategy_rejected")
            return "ok"

        results = producer.process_batch(items, process)
        self.assertEqual([result["state"] for result in results], ["paused", "completed"])
        with self.assertRaises(producer.ContractError):
            producer.process_batch([], process)
        with self.assertRaises(producer.ContractError):
            producer.process_batch([{"itemId": str(i)} for i in range(101)], process)


if __name__ == "__main__":
    unittest.main()
