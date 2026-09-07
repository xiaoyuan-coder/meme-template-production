#!/usr/bin/env python3
"""Upload one selected atmosphere image, backfill imageUrl, then prune candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import ssl
import tempfile
import urllib.request
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


class FinalizationError(RuntimeError):
    pass


ATMOSPHERE_URL_PREFIX = "https://assets.memebuy.cn/memebuy/template-atmosphere/sha256/"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FinalizationError(f"file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise FinalizationError(f"invalid JSON: {path}") from exc


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    if path.exists():
        if path.read_bytes() == encoded:
            return
        raise FinalizationError(f"create-once JSON conflict: {path}")
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def digest_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def require_https(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.startswith("https://"):
        raise FinalizationError(f"{label} must be an HTTPS URL")
    return value


def normalize_public_domain(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FinalizationError("OSS public base URL is missing")
    domain = value.strip().rstrip("/")
    if "://" not in domain:
        domain = "https://" + domain
    return require_https(domain, "OSS public base URL")


def public_ssl_context() -> ssl.SSLContext:
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


def environment_value(primary: str, fallback: str | None = None) -> str:
    value = os.environ.get(primary) or (os.environ.get(fallback) if fallback else None)
    if not value:
        raise FinalizationError(f"missing environment variable: {primary}")
    return value


def validate_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    required = {"templateKey", "imageUrl", "objectKey", "sha256", "byteLength", "status", "publicReadbackSha256"}
    if not required.issubset(receipt):
        raise FinalizationError("OSS receipt is incomplete")
    if receipt["status"] not in {"uploaded_verified", "reused_verified"}:
        raise FinalizationError("OSS receipt is not verified")
    image_url = require_https(receipt["imageUrl"], "imageUrl")
    if not image_url.startswith(ATMOSPHERE_URL_PREFIX):
        raise FinalizationError("imageUrl must use the Memebuy atmosphere-image path")
    if receipt["sha256"] != receipt["publicReadbackSha256"]:
        raise FinalizationError("public readback digest differs from selected image")
    if not isinstance(receipt["byteLength"], int) or receipt["byteLength"] <= 0:
        raise FinalizationError("OSS receipt byteLength is invalid")
    return dict(receipt)


def command_upload(args: argparse.Namespace) -> dict[str, Any]:
    image = Path(args.image).expanduser().resolve()
    if not image.is_file():
        raise FinalizationError(f"selected image does not exist: {image}")
    content = image.read_bytes()
    digest = digest_bytes(content)
    extension = image.suffix.lower()
    if extension not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise FinalizationError("selected image must be PNG, JPEG, or WebP")
    endpoint = environment_value("ALIYUN_OSS_ASSETS_ENDPOINT", "OSS_ENDPOINT")
    bucket_name = environment_value("ALIYUN_OSS_ASSETS_BUCKET", "OSS_BUCKET_NAME")
    access_key = environment_value("ALIYUN_OSS_ACCESS_KEY_ID", "OSS_ACCESS_KEY_ID")
    access_secret = environment_value("ALIYUN_OSS_ACCESS_KEY_SECRET", "OSS_ACCESS_KEY_SECRET")
    domain = normalize_public_domain(
        args.base_url or environment_value("ALIYUN_OSS_ASSETS_DOMAIN", "OSS_PUBLIC_BASE_URL")
    )
    object_key = f"{args.object_prefix.strip('/')}/{digest}{extension}"
    if f"{domain}/{args.object_prefix.strip('/')}/" != ATMOSPHERE_URL_PREFIX:
        raise FinalizationError("OSS domain and object prefix differ from the formal imageUrl contract")

    try:
        import oss2
    except ImportError as exc:
        raise FinalizationError("aliyun-oss2 dependency is unavailable") from exc
    bucket = oss2.Bucket(oss2.Auth(access_key, access_secret), endpoint, bucket_name)
    existed = True
    try:
        head = bucket.head_object(object_key)
    except oss2.exceptions.NoSuchKey:
        existed = False
        head = None
    except Exception as exc:
        raise FinalizationError("OSS metadata lookup failed") from exc
    if head is not None:
        if head.headers.get("x-oss-meta-sha256") != digest or int(head.headers.get("Content-Length", -1)) != len(content):
            raise FinalizationError("existing OSS object conflicts with selected bytes")
    else:
        mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}[extension]
        try:
            bucket.put_object(
                object_key,
                content,
                headers={
                    "x-oss-forbid-overwrite": "true",
                    "Content-Type": mime,
                    "x-oss-meta-sha256": digest,
                    "Cache-Control": "public, max-age=31536000, immutable",
                },
            )
            head = bucket.head_object(object_key)
        except Exception as exc:
            raise FinalizationError("OSS create-once upload failed") from exc
        if head.headers.get("x-oss-meta-sha256") != digest or int(head.headers.get("Content-Length", -1)) != len(content):
            raise FinalizationError("OSS object reconciliation failed")

    image_url = f"{domain}/{object_key}"
    try:
        with urllib.request.urlopen(
            image_url,
            timeout=args.readback_timeout,
            context=public_ssl_context(),
        ) as response:
            public = response.read()
    except Exception as exc:
        raise FinalizationError("public OSS readback failed") from exc
    public_digest = digest_bytes(public)
    if len(public) != len(content) or public_digest != digest:
        raise FinalizationError("public OSS readback differs from selected bytes")
    receipt = {
        "artifactType": "template_atmosphere_oss_receipt",
        "schemaVersion": "1.0.0",
        "templateKey": args.template_key,
        "imageUrl": image_url,
        "objectKey": object_key,
        "sha256": digest,
        "byteLength": len(content),
        "status": "reused_verified" if existed else "uploaded_verified",
        "publicReadbackSha256": public_digest,
        "verifiedAt": now_iso(),
    }
    atomic_json(Path(args.receipt).expanduser().resolve(), receipt)
    return receipt


def command_backfill(args: argparse.Namespace) -> dict[str, Any]:
    source_path = Path(args.source_json).expanduser().resolve()
    source = read_json(source_path)
    if not isinstance(source, dict):
        raise FinalizationError("formal template JSON must be one object")
    receipt = validate_receipt(read_json(Path(args.receipt).expanduser().resolve()))
    if source.get("key") != receipt["templateKey"]:
        raise FinalizationError("template key differs between JSON and OSS receipt")
    current = source.get("imageUrl")
    if current not in {None, receipt["imageUrl"]} and not args.allow_replacement:
        raise FinalizationError("formal JSON already contains a different imageUrl")
    revised = deepcopy(source)
    revised["imageUrl"] = receipt["imageUrl"]
    comparable = deepcopy(revised)
    comparable.pop("imageUrl", None)
    original = deepcopy(source)
    original.pop("imageUrl", None)
    if comparable != original:
        raise FinalizationError("backfill changed fields other than imageUrl")
    output_path = Path(args.output_json).expanduser().resolve()
    atomic_json(output_path, revised)
    return {
        "status": "backfilled",
        "templateKey": source["key"],
        "sourceJson": str(source_path),
        "outputJson": str(output_path),
        "imageUrl": receipt["imageUrl"],
    }


def within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def command_prune(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.batch_dir).expanduser().resolve()
    batch_path = root / "batch.json"
    batch = read_json(batch_path)
    if not isinstance(batch, dict) or not isinstance(batch.get("candidates"), list):
        raise FinalizationError("batch.json is invalid")
    receipt = validate_receipt(read_json(Path(args.receipt).expanduser().resolve()))
    current = read_json(Path(args.current_json).expanduser().resolve())
    if current.get("key") != args.template_key or current.get("imageUrl") != receipt["imageUrl"]:
        raise FinalizationError("current JSON readback does not contain the verified imageUrl")
    cleanup_path = Path(args.cleanup_receipt).expanduser().resolve()
    if cleanup_path.exists():
        prior = read_json(cleanup_path)
        if (
            isinstance(prior, dict)
            and prior.get("templateKey") == args.template_key
            and prior.get("selectedCandidateId") == args.selected_candidate_id
            and prior.get("imageUrl") == receipt["imageUrl"]
            and Path(prior.get("updatedBatch", "")).is_file()
        ):
            return prior
        raise FinalizationError("cleanup receipt conflicts with this finalization")
    candidates = [item for item in batch["candidates"] if item.get("templateKey") == args.template_key]
    selected = next((item for item in candidates if item.get("candidateId") == args.selected_candidate_id), None)
    if selected is None or selected.get("decision") not in {"approved", "good_case"}:
        raise FinalizationError("selected candidate is not approved")
    selected_path = Path(selected["imagePath"]).expanduser().resolve()
    if not within(selected_path, root):
        raise FinalizationError("selected final must be inside the batch directory")
    if not selected_path.is_file():
        raise FinalizationError("selected final image is missing")
    selected_bytes = selected_path.read_bytes()
    if digest_bytes(selected_bytes) != receipt["sha256"] or len(selected_bytes) != receipt["byteLength"]:
        raise FinalizationError("selected final differs from OSS receipt")

    deleted: list[str] = []
    already_missing: list[str] = []
    prune_targets: list[Path] = []
    for candidate in candidates:
        if candidate.get("candidateId") == args.selected_candidate_id:
            continue
        for field in ("imagePath", "generationSourcePath"):
            raw = candidate.get(field)
            if not isinstance(raw, str) or not raw:
                continue
            path = Path(raw).expanduser().resolve()
            if path == selected_path:
                continue
            if not within(path, root):
                raise FinalizationError(f"refusing to prune a path outside the batch: {path}")
            if path.exists() and (not path.is_file() or path.is_symlink()):
                raise FinalizationError(f"refusing to prune unsafe path: {path}")
            prune_targets.append(path)

    for path in dict.fromkeys(prune_targets):
        if path.exists():
            path.unlink()
            deleted.append(str(path))
        else:
            already_missing.append(str(path))

    for candidate in candidates:
        if candidate.get("candidateId") != args.selected_candidate_id:
            candidate["candidateFilesPruned"] = True
    selected["finalization"] = {
        "status": "verified_and_pruned",
        "imageUrl": receipt["imageUrl"],
        "receiptSha256": digest_bytes((json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":"))).encode()),
        "completedAt": now_iso(),
    }
    batch["updatedAt"] = now_iso()
    replacement = batch_path.with_name("batch.after-prune.json")
    atomic_json(replacement, batch)
    cleanup = {
        "artifactType": "template_atmosphere_candidate_cleanup_receipt",
        "schemaVersion": "1.0.0",
        "templateKey": args.template_key,
        "selectedCandidateId": args.selected_candidate_id,
        "selectedImagePath": str(selected_path),
        "imageUrl": receipt["imageUrl"],
        "deleted": sorted(set(deleted)),
        "alreadyMissing": sorted(set(already_missing)),
        "verifiedAt": now_iso(),
        "updatedBatch": str(replacement),
    }
    atomic_json(cleanup_path, cleanup)
    return cleanup


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    upload = commands.add_parser("upload")
    upload.add_argument("--image", required=True)
    upload.add_argument("--template-key", required=True)
    upload.add_argument("--receipt", required=True)
    upload.add_argument("--base-url")
    upload.add_argument("--object-prefix", default="memebuy/template-atmosphere/sha256")
    upload.add_argument("--readback-timeout", type=int, default=120)
    upload.set_defaults(handler=command_upload)

    backfill = commands.add_parser("backfill")
    backfill.add_argument("--source-json", required=True)
    backfill.add_argument("--receipt", required=True)
    backfill.add_argument("--output-json", required=True)
    backfill.add_argument("--allow-replacement", action="store_true")
    backfill.set_defaults(handler=command_backfill)

    prune = commands.add_parser("prune")
    prune.add_argument("--batch-dir", required=True)
    prune.add_argument("--template-key", required=True)
    prune.add_argument("--selected-candidate-id", required=True)
    prune.add_argument("--receipt", required=True)
    prune.add_argument("--current-json", required=True)
    prune.add_argument("--cleanup-receipt", required=True)
    prune.set_defaults(handler=command_prune)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = args.handler(args)
    except FinalizationError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
