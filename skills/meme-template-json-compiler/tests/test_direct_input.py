"""Anonymous, offline intake-to-full-compiler regression tests; no live uploads."""
from copy import deepcopy
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

try:
    from PIL import Image
except ImportError:
    Image = None

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
import compiler
import current_registry
import direct_input as direct


class MemoryPublisher:
    def __init__(self):
        self.objects = {}
        self.writes = 0
        self.wrong_public_bytes = False

    def ensure_png(self, key, content):
        if key not in self.objects:
            self.objects[key] = content
            self.writes += 1
        if self.objects[key] != content:
            raise compiler.ContractError("fixture collision")

    def read_public(self, url, max_bytes):
        if self.wrong_public_bytes:
            return b"different"
        key = url.split("assets.memebuy.cn/", 1)[1]
        return self.objects[key][:max_bytes]


@unittest.skipIf(Image is None, "direct entry tests require requirements-direct.txt")
class DirectInputTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.image = self.root / "anonymous.png"
        stream = BytesIO()
        Image.new("RGB", (570, 1002), "blue").save(stream, format="PNG")
        self.content = stream.getvalue()
        self.image.write_bytes(self.content)
        self.sha = hashlib.sha256(self.content).hexdigest()
        self.state_path = self.root / "sidecars/direct-input.json"
        self.receipt_path = self.root / "sidecars/publication.json"

    def prepare(self):
        return direct.prepare_direct_input(self.image, self.state_path,
            approval_evidence="Anonymous fixture user explicitly approved this PNG",
            approved_sha256=self.sha)

    def test_local_approval_preserves_bytes_dimensions_and_stable_identity(self):
        state = self.prepare()
        self.assertEqual(state, self.prepare())
        self.assertEqual(state["status"], "approved_local")
        self.assertEqual(state["image"]["width"], 570)
        self.assertEqual(state["image"]["height"], 1002)
        self.assertEqual(state["generationImageSize"], "768x1344")
        self.assertEqual(self.image.read_bytes(), self.content)
        self.assertNotIn("uri", state["image"])
        self.assertFalse(self.receipt_path.exists())

    def test_approval_and_mutated_file_are_rejected_before_publication(self):
        for evidence, sha in [("", self.sha), ("approved", "0" * 64)]:
            with self.assertRaises(compiler.ContractError):
                direct.prepare_direct_input(self.image, self.state_path,
                    approval_evidence=evidence, approved_sha256=sha)
        self.assertFalse(self.state_path.exists())
        self.prepare()
        Image.new("RGB", (570, 1002), "red").save(self.image)
        publisher = MemoryPublisher()
        with self.assertRaises(compiler.ContractError):
            direct.publish_direct_input(self.image, self.state_path, self.receipt_path, publisher)
        self.assertEqual(publisher.writes, 0)
        self.assertFalse(self.receipt_path.exists())

    def test_corrupt_and_multiframe_images_are_rejected(self):
        for content in [b"not PNG", self.content[:50]]:
            self.image.write_bytes(content)
            with self.assertRaises(compiler.ContractError):
                direct.prepare_direct_input(self.image, self.state_path,
                    approval_evidence="approved", approved_sha256=hashlib.sha256(content).hexdigest())
        Image.new("RGB", (8, 8), "red").save(self.image, save_all=True,
            append_images=[Image.new("RGB", (8, 8), "blue")], format="PNG")
        with self.assertRaises(compiler.ContractError):
            direct.prepare_direct_input(self.image, self.state_path,
                approval_evidence="approved", approved_sha256=hashlib.sha256(self.image.read_bytes()).hexdigest())

    def test_publication_requires_public_bytes_and_retries_without_reupload(self):
        self.prepare()
        publisher = MemoryPublisher()
        publisher.wrong_public_bytes = True
        with self.assertRaises(compiler.ContractError):
            direct.publish_direct_input(self.image, self.state_path, self.receipt_path, publisher)
        self.assertFalse(self.receipt_path.exists())
        publisher.wrong_public_bytes = False
        envelope = direct.publish_direct_input(self.image, self.state_path, self.receipt_path, publisher)
        self.assertEqual(envelope["image"]["sha256"], self.sha)
        self.assertEqual(envelope["image"]["width"], 570)
        self.assertEqual(envelope, direct.publish_direct_input(
            self.image, self.state_path, self.receipt_path, publisher))
        self.assertEqual(publisher.writes, 1)
        publisher.wrong_public_bytes = True
        with self.assertRaises(compiler.ContractError):
            direct.publish_direct_input(self.image, self.state_path, self.receipt_path, publisher)

    def test_symlink_state_fails_closed(self):
        path = self.root / "state-target.json"
        path.write_text('{}')
        self.state_path.parent.mkdir()
        self.state_path.symlink_to(path)
        with self.assertRaises(compiler.ContractError):
            self.prepare()

    def test_direct_input_reaches_full_compilation_and_keeps_all_semantic_gates(self):
        self.prepare()
        envelope = direct.publish_direct_input(self.image, self.state_path,
                                               self.receipt_path, MemoryPublisher())
        # Contract-only anonymous fixture, not a claim about visual evidence of the solid PNG.
        fixture = json.loads((SKILL_ROOT / "examples/integration-input.json").read_text())
        draft, analysis = fixture["formalDraft"], fixture["analysis"]
        draft["imageSize"] = "768x1344"
        analysis["approvedImageSha256"] = self.sha
        analysis["selfReview"]["reviewedDraftSha256"] = compiler.sha256_json(draft)
        decision = current_registry.resolve_template_key(self.root / "template-data", draft["key"])
        formal = compiler.compile_final_json(envelope, analysis, draft, decision)
        self.assertEqual(formal["referenceImage"], envelope["image"]["uri"])
        self.assertEqual(formal["cover"], formal["referenceImage"])
        self.assertNotIn("imageUrl", formal)
        delivery = compiler.write_formal_json(self.root / "delivery", formal)
        self.assertEqual(json.loads(delivery.read_text()), formal)
        index = compiler.write_production_index(self.root, [{
            "itemId": self.prepare()["sourceIdentity"]["sourceAssetId"],
            "skill": "meme-template-json-compiler", "state": "delivered", "revision": 1,
            "stage": "json_compiler", "artifacts": {
                "formalJson": f"delivery://{formal['key']}/{formal['key']}.json",
                "publication": "sidecar://publication.json",
            },
        }], generated_at="2026-09-08T12:00:00Z")
        self.assertEqual(json.loads(index.read_text())["items"][0]["state"], "delivered")
        receipt = current_registry.publish_template(
            self.root / "template-data", formal, published_at="2026-09-08T12:00:00Z"
        )
        self.assertEqual(receipt["status"], "promoted")
        self.assertEqual(
            current_registry.locate_current_template(self.root / "template-data", formal["key"])["formal"],
            formal,
        )
        for mutate in [lambda a, d: d.update(title="changed"),
                       lambda a, d: a["selfReview"]["checks"].pop(next(iter(a["selfReview"]["checks"]))),
                       lambda a, d: d.update(imageSize="570x1002")]:
            bad_a, bad_d = deepcopy(analysis), deepcopy(draft)
            mutate(bad_a, bad_d)
            with self.assertRaises(compiler.ContractError):
                compiler.compile_final_json(envelope, bad_a, bad_d, decision)

    def test_generation_canvas_preserves_supported_sizes_and_transpose(self):
        for size in ["1024x1024", "1152x896", "896x1152", "768x1344", "1344x768"]:
            self.assertEqual(compiler.select_generation_image_size(*map(int, size.split("x"))), size)
        self.assertEqual(compiler.select_generation_image_size(1002, 570), "1344x768")
        for dimensions in [(0, 1), (1, -1), (True, 1), (1.5, 2)]:
            with self.assertRaises(compiler.ContractError):
                compiler.select_generation_image_size(*dimensions)

    def test_real_publisher_is_create_once_checks_bytes_and_redacts_failures(self):
        class Bucket:
            def __init__(self):
                self.data = None
                self.headers = None
            def object_exists(self, key): return self.data is not None
            def put_object(self, key, data, headers): self.data, self.headers = data, headers
            def get_object(self, key): return BytesIO(self.data)
        bucket = Bucket()
        publisher = direct.OssImagePublisher(bucket)
        publisher.ensure_png("fixture.png", self.content)
        self.assertEqual(bucket.headers["x-oss-forbid-overwrite"], "true")
        publisher.ensure_png("fixture.png", self.content)
        bucket.data = b"bad"
        with self.assertRaises(compiler.ContractError):
            publisher.ensure_png("fixture.png", self.content)
        with patch.object(bucket, 'object_exists', side_effect=RuntimeError("fixture-secret")):
            with self.assertRaises(compiler.ExternalAdapterError) as raised:
                publisher.ensure_png("fixture.png", self.content)
        self.assertNotIn("fixture-secret", str(raised.exception))
        with self.assertRaises(compiler.AdapterConfigurationError):
            direct.create_publisher_from_environment({})

    def test_public_readback_uses_the_packaged_ca_context(self):
        class Bucket:
            pass
        context = object()
        publisher = direct.OssImagePublisher(Bucket(), ssl_context=context)
        class Response(BytesIO):
            def __enter__(self): return self
            def __exit__(self, *args): return None
        with patch.object(direct, "urlopen", return_value=Response(self.content)) as opened:
            self.assertEqual(publisher.read_public("https://assets.memebuy.cn/example.png", 9999), self.content)
        self.assertIs(opened.call_args.kwargs["context"], context)


if __name__ == "__main__":
    unittest.main()
