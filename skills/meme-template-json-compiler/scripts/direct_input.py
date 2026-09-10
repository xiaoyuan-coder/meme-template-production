"""Approved local PNG intake and exact-byte publication.

This entry module performs no generation and imports no other Skill. Network
publication is explicit; local approval alone never creates an uploaded envelope.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import ssl
import tempfile
from typing import Any, Mapping, Protocol
from urllib.request import urlopen
from uuid import uuid4

import fcntl

from compiler import (
    AdapterConfigurationError, ContractError, ExternalAdapterError,
    _canonical_source, _contract, select_generation_image_size, sha256_json,
    validate_approved_image_envelope,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _locked(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ContractError("direct input state must not be a symlink")
    lock = path.with_name(path.name + ".lock")
    descriptor = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield


def _write(path: Path, value: Mapping[str, Any]) -> None:
    encoded = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _read(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise ContractError("direct input state must not be a symlink")
    try:
        value = json.loads(path.read_text())
        if not isinstance(value, dict):
            raise ValueError
        return value
    except (OSError, ValueError):
        raise ContractError("direct input state is unreadable or corrupt") from None


def _png(content: bytes) -> dict[str, Any]:
    try:
        from PIL import Image
    except ImportError:
        raise AdapterConfigurationError("direct input requires Pillow; see requirements-direct.txt") from None
    try:
        with Image.open(BytesIO(content)) as image:
            if image.format != "PNG" or getattr(image, "n_frames", 1) != 1:
                raise ValueError
            width, height = image.size
            image.verify()
        with Image.open(BytesIO(content)) as image:
            image.load()
    except Exception:
        raise ContractError("direct input requires a valid single-frame PNG") from None
    return {"sha256": hashlib.sha256(content).hexdigest(), "width": width,
            "height": height, "mime": "image/png"}


def prepare_direct_input(
    image_path: Path, state_path: Path, *, approval_evidence: str, approved_sha256: str,
) -> dict[str, Any]:
    """Bind a real user approval to bytes and persist a new source UUID once."""
    if not isinstance(approval_evidence, str) or not approval_evidence.strip():
        raise ContractError("direct input requires the user's approval evidence")
    content = Path(image_path).read_bytes()
    image = _png(content)
    if image["sha256"] != approved_sha256:
        raise ContractError("local image differs from the user-approved SHA-256")
    state_path = Path(state_path)
    with _locked(state_path):
        if state_path.exists():
            state = _read(state_path)
            _validate_state(state, content)
            return state
        state = {
            "schemaVersion": 1, "status": "approved_local", "image": image,
            "approval": {"evidence": approval_evidence.strip(), "imageSha256": approved_sha256,
                         "recordedAt": _now()},
            "sourceIdentity": {"namespace": "direct-template-image", "sourceAssetId": str(uuid4()),
                               "sourceSha256": approved_sha256},
            "generationImageSize": select_generation_image_size(image["width"], image["height"]),
        }
        _write(state_path, state)
        return state


def _validate_state(state: Mapping[str, Any], content: bytes) -> None:
    if state.get("schemaVersion") != 1 or state.get("status") != "approved_local":
        raise ContractError("invalid direct input state")
    image = _png(content)
    if state.get("image") != image:
        raise ContractError("direct input bytes changed after approval")
    approval = state.get("approval", {})
    if (not isinstance(approval, Mapping) or approval.get("imageSha256") != image["sha256"]
            or not isinstance(approval.get("evidence"), str) or not approval["evidence"].strip()
            or not approval.get("recordedAt")):
        raise ContractError("direct input approval evidence is incomplete")
    source = state.get("sourceIdentity")
    if (not isinstance(source, Mapping) or _canonical_source(source) is None
            or source.get("sourceSha256") != image["sha256"]):
        raise ContractError("direct input source identity is incomplete")
    if state.get("generationImageSize") != select_generation_image_size(image["width"], image["height"]):
        raise ContractError("direct input generation size is inconsistent")


class ImagePublisher(Protocol):
    def ensure_png(self, object_key: str, content: bytes) -> None: ...
    def read_public(self, url: str, max_bytes: int) -> bytes: ...


class OssImagePublisher:
    """Create-once OSS writes plus public byte verification; credentials stay in memory."""
    def __init__(self, bucket: Any, ssl_context: ssl.SSLContext | None = None):
        self.bucket = bucket
        self.ssl_context = ssl_context or _public_ssl_context()

    def ensure_png(self, object_key: str, content: bytes) -> None:
        try:
            if not self.bucket.object_exists(object_key):
                try:
                    self.bucket.put_object(object_key, content, headers={
                        "Content-Type": "image/png", "x-oss-forbid-overwrite": "true",
                    })
                except Exception as exc:
                    if getattr(exc, "status", None) != 409:
                        raise
            if self.bucket.get_object(object_key).read(len(content) + 1) != content:
                raise ContractError("stored image differs from approved bytes")
        except ContractError:
            raise
        except Exception:
            raise ExternalAdapterError("direct image OSS publication failed") from None

    def read_public(self, url: str, max_bytes: int) -> bytes:
        try:
            with urlopen(url, timeout=30, context=self.ssl_context) as response:
                return response.read(max_bytes)
        except Exception:
            raise ExternalAdapterError("direct image public readback failed") from None


def _public_ssl_context() -> ssl.SSLContext:
    try:
        import certifi
    except ImportError:
        raise AdapterConfigurationError(
            "direct input requires certifi; see requirements-direct.txt"
        ) from None
    return ssl.create_default_context(cafile=certifi.where())


def create_publisher_from_environment(environment: Mapping[str, str] | None = None) -> OssImagePublisher:
    env = os.environ if environment is None else environment
    required = ("OSS_ACCESS_KEY_ID", "OSS_ACCESS_KEY_SECRET", "OSS_ENDPOINT", "OSS_BUCKET_NAME")
    if not all(env.get(name) for name in required):
        raise AdapterConfigurationError("direct input requires OSS credentials and target configuration")
    try:
        import oss2
    except ImportError:
        raise AdapterConfigurationError("direct input requires oss2; see requirements-direct.txt") from None
    try:
        return OssImagePublisher(oss2.Bucket(
            oss2.Auth(env["OSS_ACCESS_KEY_ID"], env["OSS_ACCESS_KEY_SECRET"]),
            env["OSS_ENDPOINT"], env["OSS_BUCKET_NAME"],
        ))
    except Exception:
        raise AdapterConfigurationError("direct input OSS configuration is invalid") from None


def publish_direct_input(
    image_path: Path, state_path: Path, receipt_path: Path, publisher: ImagePublisher,
) -> dict[str, Any]:
    """Return a standard v2 envelope only after exact approved bytes read back publicly."""
    content = Path(image_path).read_bytes()
    state = _read(Path(state_path))
    _validate_state(state, content)
    image = state["image"]
    asset = _contract()["imageAsset"]
    object_key = asset["pathPrefix"].lstrip("/") + image["sha256"] + ".png"
    url = asset["baseUrl"] + "/" + object_key
    receipt_path = Path(receipt_path)
    with _locked(receipt_path):
        if receipt_path.exists():
            previous = _read(receipt_path)
            if previous.get("directInputSha256") != sha256_json(state):
                raise ContractError("publication receipt belongs to another direct input")
        publisher.ensure_png(object_key, content)
        if publisher.read_public(url, len(content) + 1) != content:
            raise ContractError("public image bytes differ from the user-approved image")
        envelope = {"schemaVersion": 2, "status": "approved_uploaded", "image": {**image, "uri": url}}
        validate_approved_image_envelope(envelope)
        if receipt_path.exists():
            if previous.get("approvedImage") != envelope:
                raise ContractError("publication receipt envelope is inconsistent")
        else:
            _write(receipt_path, {"schemaVersion": 1, "directInputSha256": sha256_json(state),
                                  "publicReadbackAt": _now(), "byteLength": len(content),
                                  "approvedImage": envelope})
        return envelope


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--image", type=Path, required=True)
    prepare.add_argument("--state", type=Path, required=True)
    prepare.add_argument("--approved-sha256", required=True)
    prepare.add_argument("--approval", required=True)
    publish = sub.add_parser("publish")
    publish.add_argument("--image", type=Path, required=True)
    publish.add_argument("--state", type=Path, required=True)
    publish.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        value = prepare_direct_input(args.image, args.state, approval_evidence=args.approval,
                                     approved_sha256=args.approved_sha256)
    else:
        value = publish_direct_input(args.image, args.state, args.receipt, create_publisher_from_environment())
    print(json.dumps(value, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except ContractError as error:
        raise SystemExit(f"{error.code}: {error}") from None
