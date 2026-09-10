"""Canonical current-version publication for formal Gallery template JSON."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping

import fcntl
from jsonschema import Draft202012Validator, FormatChecker

from compiler import ContractError, _validate_key, sha256_json, validate_formal_json


_SKILL_ROOT = Path(__file__).resolve().parents[1]
_SCHEMA_PATH = _SKILL_ROOT / "references/contracts/current-template-registry.schema.json"
_PORTABLE_REF = re.compile(r"(?:artifact|delivery|history)://\S+")
_SHA256 = re.compile(r"[a-f0-9]{64}")


def _parse_time(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ContractError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ContractError(f"{field} must be an ISO-8601 timestamp") from None
    if parsed.utcoffset() is None:
        raise ContractError(f"{field} requires a timezone")
    return value


def _safe_root(registry_root: Path, *, create: bool) -> Path:
    raw = Path(registry_root)
    if raw.exists() and (raw.is_symlink() or not raw.is_dir()):
        raise ContractError("current registry root is unsafe")
    root = raw.resolve()
    if create:
        root.mkdir(parents=True, exist_ok=True)
    return root


def _atomic_replace(path: Path, value: Mapping[str, Any]) -> None:
    encoded = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


def _history_directory(root: Path, key: str, revision: int, *, create: bool) -> Path:
    history = root / "history"
    key_directory = history / key
    revision_directory = key_directory / f"revision-{revision:04d}"
    for directory in (history, key_directory, revision_directory):
        if directory.exists() and (directory.is_symlink() or not directory.is_dir()):
            raise ContractError("template history directory is unsafe")
        if create:
            directory.mkdir(exist_ok=True)
        elif not directory.exists():
            raise ContractError("template history directory is missing")
    return revision_directory


def _load_schema() -> Mapping[str, Any]:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def _validate_registry(value: Any) -> dict[str, Any]:
    errors = sorted(
        Draft202012Validator(_load_schema(), format_checker=FormatChecker()).iter_errors(value),
        key=lambda error: list(error.path),
    )
    if errors:
        raise ContractError("current template registry invalid: " + errors[0].message)
    keys = [record["key"] for record in value["records"]]
    if keys != sorted(keys) or len(keys) != len(set(keys)):
        raise ContractError("current template registry keys must be unique and sorted")
    return deepcopy(dict(value))


def _read_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ContractError(f"{label} is unsafe")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise ContractError(f"{label} is unreadable or corrupt") from None
    if not isinstance(value, dict):
        raise ContractError(f"{label} must contain one JSON object")
    return value


def read_current_template_registry(registry_root: Path) -> dict[str, Any]:
    """Read the authoritative registry and verify objects plus current mirrors."""
    root = _safe_root(registry_root, create=False)
    target = root / "current-template-registry.json"
    if not target.exists():
        raise ContractError("current template registry does not exist")
    lock_path = root / ".current-template-registry.lock"
    if lock_path.is_symlink() or not lock_path.is_file():
        raise ContractError("current registry lock path is unsafe")
    try:
        lock_fd = os.open(lock_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        raise ContractError("current registry lock path is unsafe") from None
    with os.fdopen(lock_fd, "rb") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_SH)
        registry = _validate_registry(_read_json(target, "current template registry"))
        for record in registry["records"]:
            object_path = root / record["objectRef"]
            mirror_path = root / record["currentTemplateRef"]
            if object_path.resolve().parent != (root / "objects").resolve():
                raise ContractError("current template object escapes registry root")
            formal = _read_json(object_path, "current template object")
            mirror = _read_json(mirror_path, "current template mirror")
            validate_formal_json(formal)
            if (
                formal.get("key") != record["key"]
                or sha256_json(formal) != record["formalJsonSha256"]
                or sha256_json(mirror) != record["formalJsonSha256"]
            ):
                raise ContractError("current template content does not match registry record")
            formal_ref = record["formalJsonRef"]
            if formal_ref.startswith("history://"):
                expected_ref = f"history://{record['key']}/revision-{record['revision']:04d}/{record['key']}.json"
                if formal_ref != expected_ref:
                    raise ContractError("template history reference does not match key and revision")
                history_path = _history_directory(
                    root, record["key"], record["revision"], create=False
                ) / f"{record['key']}.json"
                history = _read_json(history_path, "template history object")
                if sha256_json(history) != record["formalJsonSha256"]:
                    raise ContractError("template history does not match registry record")
        return registry


def resolve_template_key(
    data_root: Path, proposed_key: str, *, existing_key: str | None = None
) -> dict[str, Any]:
    """Resolve a key from the portable template data root, with key as identity."""
    proposed = _validate_key(proposed_key)
    if existing_key is not None:
        existing_key = _validate_key(existing_key)
    root = Path(data_root)
    target = root / "current-template-registry.json"
    if target.exists():
        registry = read_current_template_registry(root)
        revision = "sha256:" + sha256_json(registry)
        by_key = {record["key"]: record for record in registry["records"]}
    else:
        if root.exists() and (root.is_symlink() or not root.is_dir()):
            raise ContractError("template data root is unsafe")
        revision = "empty"
        by_key = {}
    if existing_key is not None:
        if existing_key != proposed or existing_key not in by_key:
            return {
                "registryRevision": revision,
                "decision": "KEY_CONFLICT",
                "resolvedKey": None,
                "matchedBy": ["existingKey"],
                "evidence": [{"existingKey": existing_key, "proposedKey": proposed}],
            }
        return {
            "registryRevision": revision,
            "decision": "EXISTING_KEY",
            "resolvedKey": existing_key,
            "matchedBy": ["key"],
            "evidence": [{"key": existing_key, "registered": True}],
        }
    if proposed in by_key:
        return {
            "registryRevision": revision,
            "decision": "KEY_COLLISION",
            "resolvedKey": None,
            "matchedBy": ["proposedKey"],
            "evidence": [{"proposedKey": proposed, "reason": "key already identifies a template"}],
        }
    return {
        "registryRevision": revision,
        "decision": "NEW",
        "resolvedKey": proposed,
        "matchedBy": [],
        "evidence": [{"proposedKey": proposed, "available": True}],
    }


def locate_current_template(registry_root: Path, identifier: str) -> dict[str, Any]:
    """Resolve one current formal JSON by exact key or exact user-facing title."""
    if not isinstance(identifier, str) or not identifier.strip():
        raise ContractError("current template lookup requires a key or title")
    root = _safe_root(registry_root, create=False)
    registry = read_current_template_registry(root)
    key_match = [record for record in registry["records"] if record["key"] == identifier]
    candidates: list[tuple[dict[str, Any], dict[str, Any], str]] = []
    records = key_match or registry["records"]
    for record in records:
        formal = _read_json(root / record["objectRef"], "current template object")
        if key_match or formal.get("title") == identifier:
            candidates.append((record, formal, "key" if key_match else "title"))
    if not candidates:
        raise ContractError("no current template matches the supplied key or title")
    if len(candidates) != 1:
        raise ContractError("current template title is ambiguous; use the stable key")
    record, formal, matched_by = candidates[0]
    return {
        "matchedBy": matched_by,
        "record": deepcopy(record),
        "formal": formal,
    }


def discover_bootstrap_candidates(
    runtime_roots: list[Path], identifier: str
) -> list[dict[str, Any]]:
    """Collect distinct formal JSON candidates from explicitly supplied history roots."""
    if (
        not isinstance(runtime_roots, list)
        or not runtime_roots
        or any(not isinstance(root, Path) for root in runtime_roots)
        or not isinstance(identifier, str)
        or not identifier.strip()
    ):
        raise ContractError("bootstrap discovery requires history roots and a key or title")
    index_schema = json.loads(
        (_SKILL_ROOT / "references/contracts/production-index.schema.json").read_text(
            encoding="utf-8"
        )
    )
    candidates: dict[str, dict[str, Any]] = {}
    for supplied_root in runtime_roots:
        if supplied_root.is_symlink() or not supplied_root.is_dir():
            raise ContractError("bootstrap history root is missing or unsafe")
        root = supplied_root.resolve()
        index_path = root / "index" / "production-index.json"
        if not index_path.exists():
            continue
        index = _read_json(index_path, "production index")
        errors = sorted(
            Draft202012Validator(index_schema, format_checker=FormatChecker()).iter_errors(index),
            key=lambda error: list(error.path),
        )
        if errors:
            raise ContractError("bootstrap production index violates its schema")
        for item in index["items"]:
            if (
                item["skill"] != "meme-template-json-compiler"
                or item["state"] != "delivered"
            ):
                continue
            formal_ref = item["artifacts"].get("formalJson")
            if not isinstance(formal_ref, str) or not formal_ref.startswith("delivery://"):
                continue
            relative = Path(formal_ref.removeprefix("delivery://"))
            formal_path = root / "delivery" / relative
            if formal_path.resolve().is_relative_to((root / "delivery").resolve()) is False:
                raise ContractError("bootstrap formal JSON reference escapes its history root")
            formal = _read_json(formal_path, "bootstrap formal JSON")
            if formal.get("key") != identifier and formal.get("title") != identifier:
                continue
            validate_formal_json(formal)
            digest = sha256_json(formal)
            candidate = candidates.setdefault(digest, {
                "key": formal["key"],
                "formalJsonSha256": digest,
                "formal": formal,
                "historyRefs": [],
            })
            candidate["historyRefs"].append({
                "formalJsonRef": formal_ref,
                "itemId": item["itemId"],
                "historyRevision": item["revision"],
                "runtimeRoot": str(root),
            })
    result = [candidates[digest] for digest in sorted(candidates)]
    for candidate in result:
        candidate["historyRefs"].sort(
            key=lambda value: (
                value["runtimeRoot"], value["historyRevision"], value["itemId"]
            )
        )
    return result


def promote_current_template(
    registry_root: Path,
    formal: Mapping[str, Any],
    promotion: Mapping[str, Any],
) -> dict[str, Any]:
    """CAS-promote one delivered formal JSON into the canonical current registry."""
    validate_formal_json(formal)
    key = _validate_key(formal.get("key"))
    expected_fields = {
        "chainId", "revision", "formalJsonRef", "promotedAt",
        "expectedPreviousFormalJsonSha256",
    }
    if not isinstance(promotion, Mapping) or set(promotion) != expected_fields:
        raise ContractError("current promotion fields are incomplete")
    chain_id = promotion["chainId"]
    if not isinstance(chain_id, str) or not chain_id.strip():
        raise ContractError("current promotion requires chainId")
    revision = promotion["revision"]
    if type(revision) is not int or revision < 1:
        raise ContractError("current promotion revision must be a positive integer")
    formal_ref = promotion["formalJsonRef"]
    if not isinstance(formal_ref, str) or not _PORTABLE_REF.fullmatch(formal_ref):
        raise ContractError("current promotion requires a portable formal JSON reference")
    promoted_at = _parse_time(promotion["promotedAt"], "promotedAt")
    expected_previous = promotion["expectedPreviousFormalJsonSha256"]
    if expected_previous is not None and (
        not isinstance(expected_previous, str) or not _SHA256.fullmatch(expected_previous)
    ):
        raise ContractError("expected previous formal digest must be lowercase SHA-256 or null")

    root = _safe_root(registry_root, create=True)
    objects = root / "objects"
    mirrors = root / "current" / "templates"
    for directory in (objects, root / "current", mirrors):
        if directory.exists() and (directory.is_symlink() or not directory.is_dir()):
            raise ContractError("current registry directory is unsafe")
        directory.mkdir(exist_ok=True)
    formal_sha = sha256_json(formal)
    source_match = re.search(r"/([a-f0-9]{64})\.png$", formal["referenceImage"])
    if source_match is None:
        raise ContractError("current promotion cannot derive the approved image digest")
    object_ref = f"objects/{formal_sha}.json"
    mirror_ref = f"current/templates/{key}.json"
    record = {
        "key": key,
        "chainId": chain_id,
        "revision": revision,
        "formalJsonRef": formal_ref,
        "formalJsonSha256": formal_sha,
        "sourceImageSha256": source_match.group(1),
        "objectRef": object_ref,
        "currentTemplateRef": mirror_ref,
        "promotedAt": promoted_at,
    }
    lock_path = root / ".current-template-registry.lock"
    if lock_path.exists() and lock_path.is_symlink():
        raise ContractError("current registry lock path is unsafe")
    try:
        lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except OSError:
        raise ContractError("current registry lock path is unsafe") from None
    with os.fdopen(lock_fd, "a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        target = root / "current-template-registry.json"
        if target.exists():
            registry = _validate_registry(_read_json(target, "current template registry"))
        else:
            registry = {"schemaVersion": 1, "updatedAt": promoted_at, "records": []}
        by_key = {item["key"]: item for item in registry["records"]}
        previous = by_key.get(key)
        if previous is not None and previous == record:
            return {"status": "already_current", "record": deepcopy(record)}
        if previous is None:
            if expected_previous is not None:
                raise ContractError("first current promotion requires a null previous digest")
            if revision != 1:
                raise ContractError("first current promotion starts at revision one")
        else:
            if expected_previous != previous["formalJsonSha256"]:
                raise ContractError("current promotion lost the compare-and-set race")
            if chain_id != previous["chainId"] or revision != previous["revision"] + 1:
                raise ContractError("current promotion must advance the same chain by one revision")

        object_path = root / object_ref
        if object_path.exists():
            if sha256_json(_read_json(object_path, "current template object")) != formal_sha:
                raise ContractError("content-addressed current template object conflicts")
        else:
            _atomic_replace(object_path, formal)
        if formal_ref.startswith("history://"):
            expected_ref = f"history://{key}/revision-{revision:04d}/{key}.json"
            if formal_ref != expected_ref:
                raise ContractError("template history reference does not match key and revision")
            history_path = _history_directory(root, key, revision, create=True) / f"{key}.json"
            if history_path.exists():
                if sha256_json(_read_json(history_path, "template history object")) != formal_sha:
                    raise ContractError("template history revision conflicts")
            else:
                _atomic_replace(history_path, formal)
        _atomic_replace(root / mirror_ref, formal)
        by_key[key] = record
        next_registry = {
            "schemaVersion": 1,
            "updatedAt": promoted_at,
            "records": [by_key[item_key] for item_key in sorted(by_key)],
        }
        _validate_registry(next_registry)
        _atomic_replace(target, next_registry)
        return {"status": "promoted", "record": deepcopy(record)}


def publish_template(
    data_root: Path,
    formal: Mapping[str, Any],
    *,
    published_at: str,
    expected_previous_formal_sha256: str | None = None,
) -> dict[str, Any]:
    """Create or replace one key in a portable template data root."""
    validate_formal_json(formal)
    key = _validate_key(formal.get("key"))
    root = Path(data_root)
    target = root / "current-template-registry.json"
    previous = None
    if target.exists():
        registry = read_current_template_registry(root)
        previous = next((record for record in registry["records"] if record["key"] == key), None)
    formal_sha = sha256_json(formal)
    if previous is not None and previous["formalJsonSha256"] == formal_sha:
        return {"status": "already_current", "record": deepcopy(previous)}
    if previous is None:
        revision = 1
        chain_id = key
    else:
        if expected_previous_formal_sha256 is None:
            raise ContractError("replacing an existing key requires the previous current digest")
        revision = previous["revision"] + 1
        chain_id = previous["chainId"]
    formal_ref = f"history://{key}/revision-{revision:04d}/{key}.json"
    return promote_current_template(root, formal, {
        "chainId": chain_id,
        "revision": revision,
        "formalJsonRef": formal_ref,
        "promotedAt": published_at,
        "expectedPreviousFormalJsonSha256": expected_previous_formal_sha256,
    })
