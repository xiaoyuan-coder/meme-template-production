from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from helpers import (
    PNG_BYTES, ROOT, SOURCE_INPUT_BYTES, load_module, valid_approved_analysis,
    valid_formal_draft, valid_strategy,
)


producer = load_module(
    "audit_image_producer",
    "skills/meme-template-image-producer/scripts/producer.py",
)
compiler = load_module(
    "audit_json_compiler",
    "skills/meme-template-json-compiler/scripts/compiler.py",
)
release_tools = load_module("audit_release_tools", "scripts/release_tools.py")


class RecordingFal:
    def __init__(self):
        self.calls = []

    def submit_edit(self, model, payload):
        self.calls.append((model, dict(payload)))
        return {"request_id": "fake-request"}


class ReconcilingOss:
    def __init__(self, *, bad_put=False, bad_head=False):
        self.bad_put = bad_put
        self.bad_head = bad_head
        self.created = None
        self.head_calls = []
        self.put_calls = []

    def head(self, object_key):
        self.head_calls.append(object_key)
        if self.created is None:
            return None
        value = dict(self.created)
        if self.bad_head:
            value["sha256"] = "0" * 64
        return value

    def put_create_once(self, object_key, content, metadata):
        self.put_calls.append((object_key, content, dict(metadata)))
        self.created = {
            "objectKey": object_key,
            "sha256": metadata["sha256"],
            "byteLength": metadata["byteLength"],
            "remoteIdentity": metadata["remoteIdentity"],
            "requestIdentity": metadata["requestIdentity"],
        }
        response = dict(self.created)
        if self.bad_put:
            response["objectKey"] = "gallery/templates/wrong/object.png"
        return response


def image_envelope():
    digest = hashlib.sha256(PNG_BYTES).hexdigest()
    return {
        "schemaVersion": 1,
        "status": "approved",
        "image": {
            "uri": "fixture://approved.png",
            "sha256": digest,
            "width": 1024,
            "height": 1024,
            "mime": "image/png",
        },
    }


def json_approval(draft):
    digest = hashlib.sha256(PNG_BYTES).hexdigest()
    formal = compiler.project_formal_json(draft, digest)
    return {
        "decision": "APPROVED",
        "objectSha256": compiler.sha256_json(formal),
        "approvedImageSha256": digest,
        "reviewerRef": "reviewer://json/42",
        "decidedAt": "2026-08-29T12:00:00Z",
        "ruleVersion": "0.2.0",
        "revision": 1,
    }


class AuditRegressionTests(unittest.TestCase):
    def test_real_fal_factory_is_explicit_one_shot_and_redacted(self):
        class Response:
            status_code = 202

            @staticmethod
            def json():
                return {"request_id": "provider-request-1"}

        class FakeHttpClient:
            def __init__(self):
                self.calls = []

            def post(self, url, *, json):
                self.calls.append((url, copy.deepcopy(json)))
                return Response()

        class FakeHttpxModule:
            def __init__(self):
                self.client = FakeHttpClient()
                self.client_options = None

            def Client(self, **options):
                self.client_options = dict(options)
                return self.client

        with self.assertRaises(producer.AdapterConfigurationError) as missing:
            producer.create_fal_adapter_from_environment({})
        self.assertNotIn("FAL_KEY", str(missing.exception))
        with self.assertRaises(producer.AdapterConfigurationError) as dependency:
            producer.create_fal_adapter_from_environment(
                {"FAL_KEY": "must-never-appear"},
                module_loader=lambda _: (_ for _ in ()).throw(ModuleNotFoundError("secret")),
            )
        self.assertNotIn("must-never-appear", str(dependency.exception))
        module = FakeHttpxModule()
        adapter = producer.create_fal_adapter_from_environment(
            {"FAL_KEY": "must-never-appear"}, module_loader=lambda _: module
        )
        response = adapter.submit_edit("openai/gpt-image-2/edit", {
            "image_urls": ["fixture://source.png"],
            "prompt": "safe replacement",
            "quality": "low",
            "num_images": 1,
            "output_format": "png",
            "image_size": {"width": 1024, "height": 1024},
        })
        self.assertEqual(response, {"request_id": "provider-request-1", "status": "submitted"})
        self.assertEqual(len(module.client.calls), 1)
        self.assertEqual(
            module.client.calls[0][0],
            "https://queue.fal.run/openai/gpt-image-2/edit",
        )
        self.assertNotIn("must-never-appear", json.dumps(module.client.calls))
        self.assertEqual(module.client_options["timeout"], 120.0)

        class FailingHttpxModule:
            class Client:
                def __init__(self, **options):
                    pass

                @staticmethod
                def post(url, *, json):
                    raise RuntimeError("FAL_KEY=provider-secret https://signed.invalid/?token=x")

        failing = producer.create_fal_adapter_from_environment(
            {"FAL_KEY": "provider-secret"}, module_loader=lambda _: FailingHttpxModule
        )
        with self.assertRaises(producer.ExternalAdapterError) as failure:
            failing.submit_edit("openai/gpt-image-2/edit", {
                "image_urls": ["fixture://source.png"], "prompt": "safe replacement",
                "quality": "low", "num_images": 1, "output_format": "png",
                "image_size": {"width": 1024, "height": 1024},
            })
        self.assertNotIn("provider-secret", str(failure.exception))
        self.assertNotIn("signed.invalid", str(failure.exception))

    def test_fal_http_status_is_allowlisted_without_response_text(self):
        class Response:
            def __init__(self, status_code):
                self.status_code = status_code

            @staticmethod
            def json():
                return {
                    "error_type": "validation_error",
                    "detail": "FAL_KEY=provider-secret https://signed.invalid/?token=x",
                }

        class Client:
            def __init__(self, status_code):
                self.status_code = status_code
                self.calls = []

            def post(self, url, *, json):
                self.calls.append((url, copy.deepcopy(json)))
                return Response(self.status_code)

        for status_code, outcome_known in ((422, True), (429, False), (503, False)):
            with self.subTest(status_code=status_code):
                client = Client(status_code)
                adapter = producer.FalHttpEditAdapter(client)
                with self.assertRaises(producer.ExternalAdapterError) as failure:
                    adapter.submit_edit("openai/gpt-image-2/edit", {
                        "image_urls": ["fixture://source.png"], "prompt": "safe replacement",
                        "quality": "low", "num_images": 1, "output_format": "png",
                        "image_size": {"width": 1024, "height": 1024},
                    })
                self.assertEqual(len(client.calls), 1)
                self.assertEqual(failure.exception.status_code, status_code)
                self.assertEqual(failure.exception.error_type, "validation_error")
                self.assertEqual(failure.exception.outcome_known, outcome_known)
                self.assertNotIn("provider-secret", str(failure.exception))
                self.assertNotIn("signed.invalid", str(failure.exception))

    def test_meme_admin_registry_client_uses_the_frozen_local_endpoint_contract(self):
        class Transport:
            def __init__(self):
                self.calls = []

            def post_json(self, url, payload):
                self.calls.append((url, copy.deepcopy(payload)))
                return {
                    "registryRevision": "registry-r9",
                    "decision": "NEW",
                    "resolvedKey": "new-template",
                    "matchedBy": [],
                    "evidence": [{"source": "meme-admin"}],
                }

        transport = Transport()
        client = compiler.MemeAdminKeyRegistryClient("http://127.0.0.1:4318", transport)
        request = {
            "proposedKey": "new-template",
            "sourceIdentity": {"namespace": "workbench", "sourceAssetId": "asset-9"},
        }
        response = client.resolveTemplateKey(request)
        self.assertEqual(response["decision"], "NEW")
        self.assertEqual(transport.calls, [(
            "http://127.0.0.1:4318/api/v1/template-key-registry/resolve", request
        )])

    def test_real_oss_factory_and_adapter_are_create_once_and_redacted(self):
        class Result:
            request_id = "oss-request-1"

        class Bucket:
            def __init__(self, *args):
                self.put_calls = []
                self.headers = None

            def put_object(self, key, content, *, headers):
                self.put_calls.append((key, content))
                self.headers = dict(headers)
                return Result()

            def get_object_meta(self, key):
                class Meta:
                    pass
                value = Meta()
                value.headers = self.headers
                return value

        class OssModule:
            class Auth:
                def __init__(self, access_key, secret):
                    self.access_key = access_key
                    self.secret = secret

        OssModule.Bucket = Bucket

        env = {
            "OSS_ENDPOINT": "https://oss-cn-example.aliyuncs.com",
            "OSS_BUCKET_NAME": "bucket",
            "OSS_ACCESS_KEY_ID": "access-id-secret",
            "OSS_ACCESS_KEY_SECRET": "access-secret",
        }
        with self.assertRaises(compiler.AdapterConfigurationError):
            compiler.create_aliyun_oss_adapter_from_environment({})
        with self.assertRaises(compiler.AdapterConfigurationError) as dependency:
            compiler.create_aliyun_oss_adapter_from_environment(
                env, module_loader=lambda _: (_ for _ in ()).throw(ModuleNotFoundError("secret"))
            )
        self.assertNotIn("access-secret", str(dependency.exception))
        adapter = compiler.create_aliyun_oss_adapter_from_environment(
            env, module_loader=lambda _: OssModule
        )
        metadata = {
            "sha256": "a" * 64, "byteLength": len(PNG_BYTES),
            "remoteIdentity": "gallery/templates/key/a.png", "requestIdentity": "b" * 64,
        }
        response = adapter.put_create_once("gallery/templates/key/a.png", PNG_BYTES, metadata)
        self.assertEqual(response["objectKey"], "gallery/templates/key/a.png")
        self.assertEqual(adapter._bucket.headers["x-oss-forbid-overwrite"], "true")
        self.assertEqual(adapter._bucket.headers["x-oss-meta-sha256"], "a" * 64)
        encoded = json.dumps(response)
        self.assertNotIn("access-id-secret", encoded)
        self.assertNotIn("access-secret", encoded)
        class FailingBucket:
            @staticmethod
            def put_object(key, content, *, headers):
                raise RuntimeError("OSS_ACCESS_KEY_SECRET=provider-secret")

        with self.assertRaises(compiler.ExternalAdapterError) as failure:
            compiler.AliyunOssAdapter(FailingBucket()).put_create_once(
                "gallery/templates/key/a.png", PNG_BYTES, metadata
            )
        self.assertNotIn("provider-secret", str(failure.exception))

    def test_fal_payload_is_exact_for_all_five_custom_sizes(self):
        expected_sizes = {
            "1024x1024": {"width": 1024, "height": 1024},
            "1152x896": {"width": 1152, "height": 896},
            "896x1152": {"width": 896, "height": 1152},
            "768x1344": {"width": 768, "height": 1344},
            "1344x768": {"width": 1344, "height": 768},
        }
        for name, dimensions in expected_sizes.items():
            adapter = RecordingFal()
            producer.submit_generation_request({
                "model": "openai/gpt-image-2/edit",
                "quality": "low",
                "num_images": 1,
                "output_format": "png",
                "image_size": name,
                "input_image_url": "fixture://source.png",
                "prompt": "replace subject",
            }, adapter)
            model, payload = adapter.calls[0]
            self.assertEqual(model, "openai/gpt-image-2/edit")
            self.assertEqual(set(payload), {
                "image_urls", "prompt", "quality", "num_images", "output_format", "image_size"
            })
            self.assertEqual(payload["image_urls"], ["fixture://source.png"])
            self.assertEqual(len(payload["image_urls"]), 1)
            self.assertEqual(payload["image_size"], dimensions)
            self.assertEqual(
                (payload["quality"], payload["num_images"], payload["output_format"]),
                ("low", 1, "png"),
            )

    def test_strategy_approval_binds_input_uri_bytes_prompt_and_human_facts(self):
        strategy = valid_strategy(producer)
        review_package = producer.build_strategy_review_package(strategy)
        approval = {
            "decision": "APPROVED",
            "objectSha256": review_package["objectSha256"],
            "strategySha256": review_package["strategySha256"],
            "promptSha256": review_package["promptSha256"],
            "sourceImageSha256": review_package["sourceImageSha256"],
            "inputUriSha256": review_package["inputUriSha256"],
            "reviewerRef": "reviewer://strategy/42",
            "decidedAt": "2026-08-29T11:00:00Z",
            "ruleVersion": strategy["ruleVersion"],
            "revision": strategy["revision"],
        }
        adapter = RecordingFal()
        with self.assertRaises(producer.ContractError):
            producer.submit_authorized_generation(
                strategy,
                approval,
                adapter,
                "fixture://swapped.png",
                input_image_bytes=SOURCE_INPUT_BYTES,
                attempt_state={},
            )
        self.assertEqual(adapter.calls, [])
        with self.assertRaises(producer.ContractError):
            producer.submit_authorized_generation(
                strategy,
                approval,
                adapter,
                strategy["inputImage"]["uri"],
                input_image_bytes=b"swapped-image-bytes",
                attempt_state={},
            )
        self.assertEqual(adapter.calls, [])

    def test_subject_continuity_and_asset_group_separation_are_cross_checked(self):
        strategy = valid_strategy(producer)
        producer.validate_replacement_strategy(strategy)
        stale_role = copy.deepcopy(strategy)
        stale_role["subjectContinuityEvidence"][0]["target"]["category"] = "dog"
        with self.assertRaises(producer.ContractError):
            producer.validate_replacement_strategy(stale_role)
        identity_asset_overlap = copy.deepcopy(strategy)
        identity_asset_overlap["assetUnitIds"] = ["cat-a"]
        identity_asset_overlap["assetBindingGroups"][0]["memberIds"] = ["cat-a"]
        with self.assertRaises(producer.ContractError):
            producer.validate_replacement_strategy(identity_asset_overlap)
        incomplete_asset_closure = copy.deepcopy(strategy)
        incomplete_asset_closure["assetBindingGroups"][0]["requiredComponentIds"] = ["missing"]
        with self.assertRaises(producer.ContractError):
            producer.validate_replacement_strategy(incomplete_asset_closure)

    def test_image_review_requires_frozen_machine_evidence_and_projects_package_facts(self):
        context = producer.build_revision_review_context([], 1, [])
        facts = {"uri": "fixture://approved.png", "width": 1024, "height": 1024}
        with self.assertRaises(producer.ContractError):
            producer.build_image_review_package(
                PNG_BYTES, {"uri": "fixture://source.jpg", "sha256": "a" * 64,
                            "width": 1024, "height": 1024, "mime": "image/jpeg"}, facts,
                item_id="item-a", rule_version="0.2.0", revision=1,
                evidence=[], hard_failures=[], warnings=[], revision_context=context,
            )
        evidence = [
            {"gate": gate, "passed": True, "summary": f"checked {gate}"}
            for gate in producer.required_image_review_gates()
        ]
        package = producer.build_image_review_package(
            PNG_BYTES, {"uri": "fixture://source.jpg", "sha256": "a" * 64,
                        "width": 1024, "height": 1024, "mime": "image/jpeg"}, facts,
            item_id="item-a", rule_version="0.2.0", revision=1,
            evidence=evidence, hard_failures=[], warnings=[], revision_context=context,
        )
        review = {
            "decision": "APPROVED",
            "objectSha256": hashlib.sha256(PNG_BYTES).hexdigest(),
            "reviewPackageSha256": producer.sha256_json(package),
            "reviewerRef": "reviewer://image/42",
            "decidedAt": "2026-08-29T11:30:00Z",
            "ruleVersion": "0.2.0",
            "revision": 1,
        }
        envelope = producer.approve_generated_png(
            PNG_BYTES, review, package, rule_version="0.2.0", revision=1
        )
        self.assertEqual(envelope["image"], package["generatedImage"])
        for field, value in (("uri", "fixture://swapped.png"), ("width", 2048), ("mime", "image/jpeg")):
            tampered = copy.deepcopy(package)
            tampered["generatedImage"][field] = value
            with self.assertRaises(producer.ContractError):
                producer.approve_generated_png(
                    PNG_BYTES, review, tampered, rule_version="0.2.0", revision=1
                )
        forged = copy.deepcopy(package)
        forged["evidence"] = []
        forged_review = dict(review)
        forged_review["reviewPackageSha256"] = producer.sha256_json(forged)
        with self.assertRaises(producer.ContractError):
            producer.approve_generated_png(
                PNG_BYTES, forged_review, forged, rule_version="0.2.0", revision=1
            )

    def test_batch_non_mapping_and_secret_errors_are_item_local_and_redacted(self):
        secret = "FAL_KEY=super-secret-token https://signed.example/path?token=abc"
        for module in (producer, compiler):
            results = module.process_batch([
                "not-an-object",
                {"itemId": "bad", "revision": 1},
                {"itemId": "good", "revision": 1},
            ], lambda item: (_ for _ in ()).throw(RuntimeError(secret))
               if item["itemId"] == "bad" else "ok")
            self.assertEqual([item["state"] for item in results], ["blocked", "paused", "completed"])
            encoded = json.dumps(results, ensure_ascii=False)
            self.assertNotIn("super-secret-token", encoded)
            self.assertNotIn("signed.example", encoded)
            self.assertNotIn("token=abc", encoded)
            self.assertEqual(results[1]["errorCode"], "UNEXPECTED_ITEM_FAILURE")

    def test_new_oss_upload_is_reconciled_before_receipt(self):
        draft = valid_formal_draft()
        for adapter in (ReconcilingOss(bad_put=True), ReconcilingOss(bad_head=True)):
            with self.assertRaises(compiler.ContractError):
                compiler.finalize_approved_json(
                    draft, json_approval(draft), PNG_BYTES, adapter,
                    rule_version="0.2.0", revision=1,
                    uploaded_at="2026-08-29T12:00:00Z",
                )

    def test_semantic_cross_checks_reject_manual_drift_and_stale_translation(self):
        envelope = image_envelope()
        analysis = valid_approved_analysis(envelope["image"]["sha256"])
        draft = valid_formal_draft()
        compiler.validate_authoring_contract(analysis, draft, envelope)

        cases = []
        missing_axis = copy.deepcopy(analysis)
        del missing_axis["singleSlotExhaustion"]["axes"]["scene"]
        cases.append(missing_axis)
        missing_component = copy.deepcopy(analysis)
        missing_component["semanticModel"]["componentCoverage"] = {}
        cases.append(missing_component)
        redraw_drift = copy.deepcopy(analysis)
        redraw_drift["semanticModel"]["completeRedrawByTarget"]["subject_main"] = False
        cases.append(redraw_drift)
        fact_source_drift = copy.deepcopy(analysis)
        fact_source_drift["semanticModel"]["dynamicFactSources"]["subject"] = "manual.value"
        cases.append(fact_source_drift)
        duplicate_axis = copy.deepcopy(analysis)
        duplicate_axis["singleSlotExhaustion"]["axes"]["scene"]["candidateSlotIds"] = ["subject"]
        cases.append(duplicate_axis)
        for invalid in cases:
            with self.assertRaises(compiler.ContractError):
                compiler.validate_authoring_contract(invalid, draft, envelope)

        prompt_drift = copy.deepcopy(draft)
        prompt_drift["promptTemplate"] += "手工漂移"
        with self.assertRaises(compiler.ContractError):
            compiler.validate_authoring_contract(analysis, prompt_drift, envelope)

        translated = copy.deepcopy(analysis)
        translated["textRegions"] = [
            {"regionId": "source", "role": "content", "action": "preserve",
             "language": "en", "exactText": "HUG ME", "layout": "one line", "position": "top"},
            {"regionId": "translated", "role": "content", "action": "preserve",
             "language": "zh-CN", "exactText": "抱抱我", "layout": "单行", "position": "下方",
             "translationSourceRegionId": "source"},
        ]
        translated["translationEquivalences"] = [{
            "sourceRegionId": "source",
            "targetRegionIds": ["translated"],
            "sourceTextSha256": hashlib.sha256("HUG ME".encode()).hexdigest(),
            "targetTextSha256": {
                "translated": hashlib.sha256("抱抱我".encode()).hexdigest()
            },
        }]
        compiler.validate_authoring_contract(translated, draft, envelope)
        translated["textRegions"][1]["exactText"] = "旧摘要"
        with self.assertRaises(compiler.ContractError):
            compiler.validate_authoring_contract(translated, draft, envelope)

    def test_index_merges_same_revision_and_appends_new_revision_atomically(self):
        base = {
            "itemId": "item-a", "skill": "meme-template-json-compiler",
            "state": "awaiting_review", "revision": 1, "stage": "review",
            "artifacts": {"review": "sidecar://item-a/review.json"},
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = compiler.write_production_index(
                root, [base], generated_at="2026-08-29T12:00:00Z"
            )
            updated = {**base, "state": "delivered", "stage": "formal_json_written"}
            compiler.write_production_index(
                root, [updated], generated_at="2026-08-29T12:01:00Z"
            )
            revision_two = {**updated, "revision": 2, "stage": "revision_two"}
            compiler.write_production_index(
                root, [revision_two], generated_at="2026-08-29T12:02:00Z"
            )
            value = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(value["generatedAt"], "2026-08-29T12:02:00Z")
            self.assertEqual([(x["revision"], x["stage"]) for x in value["items"]], [
                (1, "formal_json_written"), (2, "revision_two")
            ])

    def test_both_skills_merge_into_one_scanner_index(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            producer.write_production_index(
                root,
                [{
                    "itemId": "material-1631",
                    "skill": "meme-template-image-producer",
                    "state": "awaiting_strategy_approval",
                    "revision": 1,
                    "stage": "strategy_review",
                    "artifacts": {"review": "sidecar://material-1631/strategy.json"},
                }],
                generated_at="2026-08-29T12:00:00Z",
            )
            compiler.write_production_index(
                root,
                [{
                    "itemId": "material-1631",
                    "skill": "meme-template-json-compiler",
                    "state": "awaiting_json_approval",
                    "revision": 1,
                    "stage": "json_review",
                    "artifacts": {"review": "sidecar://material-1631/json-review.json"},
                }],
                generated_at="2026-08-29T12:01:00Z",
            )
            value = json.loads((root / "index/production-index.json").read_text(encoding="utf-8"))
            self.assertEqual(
                {(item["skill"], item["state"]) for item in value["items"]},
                {
                    ("meme-template-image-producer", "awaiting_strategy_approval"),
                    ("meme-template-json-compiler", "awaiting_json_approval"),
                },
            )

    def test_index_concurrency_corruption_and_symlink_guards(self):
        def item(number):
            return {
                "itemId": f"item-{number}", "skill": "meme-template-json-compiler",
                "state": "delivered", "revision": 1, "stage": "written",
                "artifacts": {"formalJson": f"delivery://item-{number}/item-{number}.json"},
            }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with ThreadPoolExecutor(max_workers=4) as executor:
                list(executor.map(
                    lambda number: compiler.write_production_index(
                        root, [item(number)], generated_at=f"2026-08-29T12:00:{number:02d}Z"
                    ),
                    range(8),
                ))
            value = json.loads((root / "index/production-index.json").read_text(encoding="utf-8"))
            self.assertEqual(len(value["items"]), 8)
            (root / "index/production-index.json").write_text("broken", encoding="utf-8")
            with self.assertRaises(compiler.ContractError):
                compiler.write_production_index(
                    root, [item(9)], generated_at="2026-08-29T12:01:00Z"
                )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real = root / "real"
            real.mkdir()
            alias = root / "alias"
            alias.symlink_to(real, target_is_directory=True)
            with self.assertRaises(compiler.ContractError):
                compiler.write_production_index(
                    alias, [item(1)], generated_at="2026-08-29T12:00:00Z"
                )

    def test_all_three_human_approval_schemas_require_fresh_human_facts(self):
        strategy = valid_strategy(producer)
        strategy_package = producer.build_strategy_review_package(strategy)
        strategy_approval = {
            "decision": "APPROVED",
            **{name: strategy_package[name] for name in (
                "objectSha256", "strategySha256", "promptSha256", "sourceImageSha256",
                "inputUriSha256", "ruleVersion", "revision",
            )},
            "reviewerRef": "reviewer://strategy/schema",
            "decidedAt": "2026-08-29T10:00:00Z",
        }
        image_schema_value = {
            "decision": "APPROVED", "objectSha256": "a" * 64,
            "reviewPackageSha256": "b" * 64, "reviewerRef": "reviewer://image/schema",
            "decidedAt": "2026-08-29T10:30:00Z", "ruleVersion": "0.2.0", "revision": 1,
        }
        values = [
            ("strategy-approval.schema.json", strategy_approval,
             ROOT / "skills/meme-template-image-producer/references/contracts"),
            ("image-approval.schema.json", image_schema_value,
             ROOT / "skills/meme-template-image-producer/references/contracts"),
            ("json-approval.schema.json", json_approval(valid_formal_draft()),
             ROOT / "skills/meme-template-json-compiler/references/contracts"),
        ]
        for filename, value, parent in values:
            schema = json.loads((parent / filename).read_text(encoding="utf-8"))
            Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)
            stale = dict(value)
            stale.pop("reviewerRef")
            self.assertTrue(list(Draft202012Validator(schema).iter_errors(stale)))

    def test_formal_release_build_fails_closed_in_current_unborn_dirty_repo(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(release_tools.ReleaseError):
                release_tools.build_skill_package(
                    ROOT, "meme-template-image-producer", Path(directory)
                )
            package, _ = release_tools.build_skill_package(
                ROOT, "meme-template-image-producer", Path(directory), allow_uncommitted=True
            )
            manifest, _ = release_tools._read_package(package)
            self.assertTrue(manifest["maintenanceOnly"])


if __name__ == "__main__":
    unittest.main()
