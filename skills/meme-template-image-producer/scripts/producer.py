"""Deterministic gates for replacement image production.

Network credentials and concrete provider clients are injected by the caller. This
module is the only production location that knows how to submit an image edit.
"""

from __future__ import annotations

import base64
import hashlib
import importlib
import json
import os
import re
import tempfile
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, MutableMapping, Protocol, Sequence

import fcntl

from jsonschema import Draft202012Validator, FormatChecker


class ContractError(ValueError):
    """Raised before an external side effect when a contract is invalid."""

    code = "CONTRACT_INVALID"


class AdapterConfigurationError(ContractError):
    """Safe configuration failure for the explicit real-provider seam."""

    code = "ADAPTER_CONFIGURATION_INVALID"


class ExternalAdapterError(ContractError):
    """Redacted external-provider failure."""

    code = "EXTERNAL_ADAPTER_FAILURE"

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_type: str | None = None,
        outcome_known: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_type = error_type
        self.outcome_known = outcome_known


class InputHostingError(ContractError):
    """Provider input hosting failed before a generation POST was attempted."""

    code = "INPUT_HOSTING_FAILURE"


class FalEditAdapter(Protocol):
    def submit_edit(self, model: str, payload: Mapping[str, Any]) -> Mapping[str, Any]: ...


class FalHttpEditAdapter:
    """One-shot FAL queue adapter; the injected HTTP client must not retry POSTs."""

    def __init__(self, client: Any, uploader: Callable[[bytes, str, str], str] | None = None) -> None:
        self._client = client
        self._uploader = uploader

    def submit_edit(self, model: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        _validate_compiled_fal_payload(model, payload)
        queue_payload = dict(payload)
        queue_payload["image_urls"] = [self._host_input(payload["image_urls"][0])]
        try:
            response = self._client.post(
                f"https://queue.fal.run/{model}",
                json=queue_payload,
            )
        except Exception as exc:
            request_id = getattr(exc, "request_id", None)
            if isinstance(request_id, str) and request_id:
                return {"request_id": request_id, "status": "submission_timeout"}
            failure = _safe_provider_failure(exc)
            if failure is None:
                raise ExternalAdapterError("FAL submission failed with an unknown outcome") from None
            status_code, error_type = failure
            outcome_known = 400 <= status_code < 500 and status_code not in {408, 409, 425, 429}
            outcome = "was rejected" if outcome_known else "has an unknown outcome"
            raise ExternalAdapterError(
                f"FAL submission {outcome} (HTTP {status_code})",
                status_code=status_code,
                error_type=error_type,
                outcome_known=outcome_known,
            ) from None
        status_code = getattr(response, "status_code", None)
        if not isinstance(status_code, int):
            raise ExternalAdapterError("FAL submission returned no HTTP status")
        if not 200 <= status_code < 300:
            error_type = _safe_response_error_type(response)
            outcome_known = 400 <= status_code < 500 and status_code not in {408, 409, 425, 429}
            outcome = "was rejected" if outcome_known else "has an unknown outcome"
            raise ExternalAdapterError(
                f"FAL submission {outcome} (HTTP {status_code})",
                status_code=status_code,
                error_type=error_type,
                outcome_known=outcome_known,
            )
        try:
            body = response.json()
        except Exception:
            raise ExternalAdapterError("FAL submission returned an unreadable success response") from None
        request_id = body.get("request_id") if isinstance(body, Mapping) else None
        if not isinstance(request_id, str) or not request_id:
            raise ExternalAdapterError("FAL submission returned no request identity")
        return {"request_id": request_id, "status": "submitted"}

    def _host_input(self, value: str) -> str:
        if value.startswith(("https://", "http://")):
            return value
        match = re.fullmatch(r"data:(image/(?:png|jpeg|webp));base64,([A-Za-z0-9+/=]+)", value)
        if match is None or self._uploader is None:
            raise InputHostingError("FAL input hosting is unavailable")
        mime = match.group(1)
        try:
            content = base64.b64decode(match.group(2), validate=True)
            hosted = None
            for attempt in range(2):
                try:
                    hosted = self._uploader(content, mime, f"approved-input.{mime.split('/')[1]}")
                    break
                except Exception:
                    if attempt == 1:
                        raise
        except Exception:
            raise InputHostingError("FAL input hosting failed before generation submission") from None
        if not isinstance(hosted, str) or not hosted.startswith("https://"):
            raise InputHostingError("FAL input hosting returned no HTTPS URL")
        return hosted


def create_fal_adapter_from_environment(
    environ: Mapping[str, str] | None = None,
    *,
    module_loader: Callable[[str], Any] = importlib.import_module,
) -> FalHttpEditAdapter:
    """Create the real adapter only when a caller explicitly chooses this seam."""

    env = os.environ if environ is None else environ
    if not isinstance(env.get("FAL_KEY"), str) or not env["FAL_KEY"].strip():
        raise AdapterConfigurationError("FAL credentials are unavailable")
    try:
        httpx = module_loader("httpx")
    except (ImportError, ModuleNotFoundError):
        raise AdapterConfigurationError("httpx dependency is unavailable") from None
    try:
        fal_client = module_loader("fal_client")
    except (ImportError, ModuleNotFoundError):
        raise AdapterConfigurationError("fal-client storage dependency is unavailable") from None
    client_factory = getattr(httpx, "Client", None)
    if not callable(client_factory):
        raise AdapterConfigurationError("httpx dependency has no client seam")
    client = client_factory(
        headers={"Authorization": f"Key {env['FAL_KEY'].strip()}"},
        timeout=120.0,
        follow_redirects=True,
    )
    if not callable(getattr(client, "post", None)):
        raise AdapterConfigurationError("httpx client has no POST seam")
    storage_factory = getattr(fal_client, "SyncClient", None)
    if not callable(storage_factory):
        raise AdapterConfigurationError("fal-client storage dependency has no client seam")
    storage_client = storage_factory(key=env["FAL_KEY"].strip())
    upload = getattr(storage_client, "upload", None)
    if not callable(upload):
        raise AdapterConfigurationError("fal-client storage dependency has no upload seam")

    def uploader(content: bytes, mime: str, file_name: str) -> str:
        return upload(content, mime, file_name=file_name)

    return FalHttpEditAdapter(client, uploader)


_SKILL_ROOT = Path(__file__).resolve().parents[1]
_CONTRACT_PATH = _SKILL_ROOT / "references" / "machine-contract.json"


def _safe_provider_failure(exc: Exception) -> tuple[int, str | None] | None:
    """Extract allowlisted diagnostics without copying provider text or headers."""

    status_code = getattr(exc, "status_code", None)
    if not isinstance(status_code, int):
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
    if not isinstance(status_code, int) or not 400 <= status_code <= 599:
        return None
    error_type = getattr(exc, "error_type", None)
    if not isinstance(error_type, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", error_type):
        error_type = None
    return status_code, error_type


def _safe_response_error_type(response: Any) -> str | None:
    """Read only one allowlisted diagnostic value from a provider error body."""

    try:
        body = response.json()
    except Exception:
        return None
    error_type = body.get("error_type") if isinstance(body, Mapping) else None
    if isinstance(error_type, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", error_type):
        return error_type
    return None


def _contract() -> dict[str, Any]:
    return json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))


def _validate_compiled_fal_payload(model: str, payload: Mapping[str, Any]) -> None:
    generation = _contract()["generation"]
    required = {"image_urls", "prompt", "quality", "num_images", "output_format", "image_size"}
    if model != generation["model"] or set(payload) != required:
        raise ContractError("compiled FAL request differs from the fixed edit contract")
    if (
        payload["quality"] != generation["quality"]
        or payload["num_images"] != generation["num_images"]
        or payload["output_format"] != generation["output_format"]
        or not isinstance(payload["image_urls"], list)
        or len(payload["image_urls"]) != 1
        or not isinstance(payload["image_urls"][0], str)
        or not payload["image_urls"][0]
        or not isinstance(payload["prompt"], str)
        or not payload["prompt"].strip()
        or payload["image_size"] not in generation["sizes"].values()
    ):
        raise ContractError("compiled FAL payload violates the fixed edit contract")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_json(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return sha256_bytes(encoded)


def uri_sha256(uri: str) -> str:
    """Bind approval to the exact stable URI without persisting query details elsewhere."""

    return sha256_bytes(_non_empty_text(uri, "input image URI").encode("utf-8"))


def image_data_uri(content: bytes) -> str:
    """Encode approved local bytes for FAL without a separate upload request."""

    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
    elif content.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    elif content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        mime = "image/webp"
    else:
        raise ContractError("generation input must be PNG, JPEG, or WebP bytes")
    return f"data:{mime};base64,{base64.b64encode(content).decode('ascii')}"


def _validate_human_facts(value: Mapping[str, Any]) -> None:
    _non_empty_text(value.get("reviewerRef"), "reviewerRef")
    decided_at = _non_empty_text(value.get("decidedAt"), "decidedAt")
    try:
        datetime.fromisoformat(decided_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError("decidedAt must be an ISO-8601 timestamp") from exc


def required_image_review_gates() -> tuple[str, ...]:
    return tuple(_contract()["imageReview"]["requiredGates"])


def _non_empty_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} must be non-empty text")
    return value.strip()


def compile_replacement_prompt(prompt_sections: Mapping[str, Any]) -> str:
    """Compile the approved, structured strategy prompt in one canonical order."""

    replacement = _contract()["replacement"]
    if set(prompt_sections) != set(replacement["promptSections"]):
        raise ContractError("prompt sections must match the canonical section set")
    lines: list[str] = []
    for name in replacement["promptSections"]:
        value = prompt_sections[name]
        if isinstance(value, list):
            if not value or not all(isinstance(item, str) and item.strip() for item in value):
                raise ContractError(f"prompt section {name} must contain non-empty text")
            rendered = "；".join(item.strip() for item in value)
        else:
            rendered = _non_empty_text(value, f"prompt section {name}")
        lines.append(f"{replacement['promptLabels'][name]}：{rendered}")
    return "\n".join(lines)


def select_image_size(width: int, height: int) -> str:
    """Select the allowed canvas whose aspect ratio is closest to the target canvas."""

    if not isinstance(width, int) or width < 1 or not isinstance(height, int) or height < 1:
        raise ContractError("source canvas dimensions must be positive integers")
    ratio = width / height
    sizes = _contract()["generation"]["sizes"]
    return min(
        sizes,
        key=lambda name: (abs(sizes[name]["width"] / sizes[name]["height"] - ratio), name),
    )


def _validate_category_continuity(strategy: Mapping[str, Any]) -> None:
    replacement = _contract()["replacement"]
    source = strategy.get("sourceCategory")
    selected = strategy.get("selectedCategory")
    if source not in replacement["categories"] or selected not in replacement["categories"]:
        raise ContractError("replacement category is outside the contract")
    if source != selected and not _non_empty_text(
        strategy.get("crossCategoryMechanism"), "crossCategoryMechanism"
    ):
        raise ContractError("cross-category replacement requires an explicit visual mechanism")
    if source in {"ordinary_person", "public_figure", "anime_ip", "historical_figure", "cat", "dog"}:
        if source != selected:
            raise ContractError("identity and species categories must remain compatible")
    source_identity = _non_empty_text(strategy.get("sourceIdentityFingerprint"), "sourceIdentityFingerprint")
    selected_identity = _non_empty_text(strategy.get("selectedIdentityFingerprint"), "selectedIdentityFingerprint")
    if source_identity == selected_identity:
        raise ContractError("replacement identity must differ from the source identity")
    research = strategy.get("identityResearch")
    if not isinstance(research, Mapping) or set(research) != {
        "required", "conclusion", "confidence", "evidenceRefs", "alternatives"
    }:
        raise ContractError("identityResearch must record the recognition decision")
    if not isinstance(research["required"], bool):
        raise ContractError("identityResearch.required must be boolean")
    _non_empty_text(research["conclusion"], "identityResearch.conclusion")
    confidence = research["confidence"]
    if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        raise ContractError("identityResearch.confidence must be between 0 and 1")
    if not isinstance(research["evidenceRefs"], list) or not isinstance(research["alternatives"], list):
        raise ContractError("identityResearch evidence and alternatives must be arrays")
    if research["required"] and not research["evidenceRefs"]:
        raise ContractError("identity-sensitive routing requires evidence references")
    if research["required"] and confidence < 0.8 and not research["alternatives"]:
        raise ContractError("uncertain identity research must preserve alternatives for review")


def _validate_identity_groups(strategy: Mapping[str, Any]) -> None:
    groups = strategy.get("identityBindingGroups")
    asset_groups = strategy.get("assetBindingGroups")
    closure = strategy.get("dependencyClosure")
    if not isinstance(groups, list) or not groups:
        raise ContractError("identityBindingGroups must be non-empty")
    if not isinstance(asset_groups, list) or not asset_groups:
        raise ContractError("assetBindingGroups must be non-empty")
    if not isinstance(closure, list) or not closure:
        raise ContractError("dependencyClosure must be non-empty")
    closure_ids = set()
    for item in closure:
        if not isinstance(item, Mapping):
            raise ContractError("dependencyClosure entries must be objects")
        component_id = _non_empty_text(item.get("componentId"), "dependency componentId")
        _non_empty_text(item.get("type"), "dependency type")
        if component_id in closure_ids:
            raise ContractError("dependencyClosure componentIds must be unique")
        closure_ids.add(component_id)
    seen_members: set[str] = set()
    identity_group_ids: set[str] = set()
    identity_pairs: set[tuple[str, str]] = set()
    for group in groups:
        if not isinstance(group, Mapping):
            raise ContractError("identity binding groups must be objects")
        group_id = _non_empty_text(group.get("groupId"), "identity groupId")
        if group.get("kind") != "identity" or group_id in identity_group_ids:
            raise ContractError("identity groups require unique identity group IDs")
        identity_group_ids.add(group_id)
        source_members = group.get("sourceMemberIds")
        target_members = group.get("targetMemberIds")
        required_components = group.get("requiredComponentIds")
        if (
            not isinstance(source_members, list)
            or not source_members
            or not all(isinstance(member, str) and member for member in source_members)
            or len(set(source_members)) != len(source_members)
        ):
            raise ContractError("identity group source members must be unique and non-empty")
        if (
            not isinstance(target_members, list)
            or len(target_members) != len(source_members)
            or not all(isinstance(member, str) and member for member in target_members)
            or len(set(target_members)) != len(target_members)
        ):
            raise ContractError("identity group requires one target per source member")
        if not isinstance(required_components, list) or not required_components:
            raise ContractError("identity group required components must be non-empty")
        if not set(required_components).issubset(closure_ids):
            raise ContractError("identity group dependency closure is incomplete")
        overlap = seen_members.intersection(source_members)
        if overlap:
            raise ContractError("identity source members cannot belong to multiple groups")
        seen_members.update(source_members)
        identity_pairs.update(zip(source_members, target_members))
        _non_empty_text(group.get("relationship"), "identity relationship")
    declared_units = strategy.get("sourceIdentityUnitIds")
    if (
        not isinstance(declared_units, list)
        or not all(isinstance(member, str) and member for member in declared_units)
        or set(declared_units) != seen_members
    ):
        raise ContractError("every visible identity unit must belong to exactly one identity group")
    continuity = strategy.get("subjectContinuityEvidence")
    if not isinstance(continuity, list) or len(continuity) != len(identity_pairs):
        raise ContractError("every subject pair requires category continuity evidence")
    continuity_pairs: set[tuple[str, str]] = set()
    for item in continuity:
        if not isinstance(item, Mapping):
            raise ContractError("subject continuity evidence must be objects")
        pair = (
            _non_empty_text(item.get("sourceMemberId"), "continuity sourceMemberId"),
            _non_empty_text(item.get("targetMemberId"), "continuity targetMemberId"),
        )
        if pair in continuity_pairs:
            raise ContractError("subject continuity pairs must be unique")
        continuity_pairs.add(pair)
        source_facts, target_facts = item.get("source"), item.get("target")
        required_facts = {"roleFunction", "ageStage", "genderPresentation", "count", "category"}
        if (
            not isinstance(source_facts, Mapping)
            or not isinstance(target_facts, Mapping)
            or set(source_facts) != required_facts
            or set(target_facts) != required_facts
        ):
            raise ContractError("subject continuity facts are incomplete")
        for side, facts in (("source", source_facts), ("target", target_facts)):
            for field in ("roleFunction", "ageStage", "genderPresentation", "category"):
                _non_empty_text(facts[field], f"continuity {side}.{field}")
            if facts["count"] != 1:
                raise ContractError("per-subject continuity count must equal one")
        if source_facts["category"] != strategy["sourceCategory"]:
            raise ContractError("subject source category differs from strategy")
        if target_facts["category"] != strategy["selectedCategory"]:
            raise ContractError("subject target category differs from strategy")
        _non_empty_text(item.get("evidence"), "subject continuity evidence")
    if continuity_pairs != identity_pairs:
        raise ContractError("subject continuity evidence must cover every identity pair")

    asset_unit_ids = strategy.get("assetUnitIds")
    if (
        not isinstance(asset_unit_ids, list)
        or not asset_unit_ids
        or not all(isinstance(member, str) and member for member in asset_unit_ids)
        or len(set(asset_unit_ids)) != len(asset_unit_ids)
    ):
        raise ContractError("assetUnitIds must be unique and non-empty")
    if set(asset_unit_ids).intersection(seen_members):
        raise ContractError("identity units and asset units must remain separate")
    asset_members: set[str] = set()
    asset_group_ids: set[str] = set()
    for group in asset_groups:
        if not isinstance(group, Mapping):
            raise ContractError("asset binding groups must be objects")
        group_id = _non_empty_text(group.get("groupId"), "asset groupId")
        members = group.get("memberIds")
        required_components = group.get("requiredComponentIds")
        if group.get("kind") != "asset" or group_id in asset_group_ids or group_id in identity_group_ids:
            raise ContractError("asset groups require unique IDs separate from identity groups")
        if (
            not isinstance(members, list)
            or not members
            or not all(isinstance(member, str) and member for member in members)
            or len(set(members)) != len(members)
        ):
            raise ContractError("asset group members must be unique and non-empty")
        if asset_members.intersection(members):
            raise ContractError("asset units cannot belong to multiple groups")
        if not isinstance(required_components, list) or not required_components:
            raise ContractError("asset group dependency components must be non-empty")
        if not set(required_components).issubset(closure_ids):
            raise ContractError("asset group dependency closure is incomplete")
        asset_group_ids.add(group_id)
        asset_members.update(members)
    if asset_members != set(asset_unit_ids):
        raise ContractError("asset binding groups must cover the complete asset member set")


def _validate_region_actions(strategy: Mapping[str, Any]) -> None:
    replacement = _contract()["replacement"]
    mark_actions = strategy.get("markActions")
    text_actions = strategy.get("textActions")
    if not isinstance(mark_actions, list) or not isinstance(text_actions, list):
        raise ContractError("markActions and textActions must be arrays")
    seen_marks: set[str] = set()
    for mark in mark_actions:
        if not isinstance(mark, Mapping):
            raise ContractError("mark action must be an object")
        mark_id = _non_empty_text(mark.get("regionId"), "mark regionId")
        mark_type = mark.get("type")
        action = mark.get("action")
        if mark_id in seen_marks or action not in replacement["markActions"].get(mark_type, []):
            raise ContractError("mark action is duplicated or incompatible with its type")
        if action == "remove_with_reason":
            _non_empty_text(mark.get("reason"), "mark removal reason")
        seen_marks.add(mark_id)
    seen_text: set[str] = set()
    for region in text_actions:
        if not isinstance(region, Mapping):
            raise ContractError("text action must be an object")
        region_id = _non_empty_text(region.get("regionId"), "text regionId")
        role, action = region.get("role"), region.get("action")
        if region_id in seen_text or action not in replacement["textActions"]:
            raise ContractError("text action is duplicated or invalid")
        if role in {"watermark", "attribution"} and action != "remove":
            raise ContractError("watermark and attribution text must be removed")
        if role == "identity" and action not in {"synchronize_identity", "remove"}:
            raise ContractError("identity text must synchronize or be removed")
        if role in {"joke", "content"} and action != "preserve":
            if not region.get("explicitlyAuthorized") and not region.get("mechanismRequiresRewrite"):
                raise ContractError("content text changes require explicit authority or mechanism evidence")
        if action in {"preserve", "replace", "synchronize_identity"}:
            _non_empty_text(region.get("exactText"), "text exactText")
        seen_text.add(region_id)


def _validate_operations_and_visuals(strategy: Mapping[str, Any]) -> None:
    replacement = _contract()["replacement"]
    operations = strategy.get("operations")
    if not isinstance(operations, list) or not operations:
        raise ContractError("replacement operations must be non-empty")
    for operation in operations:
        if not isinstance(operation, Mapping) or operation.get("type") not in replacement["operations"]:
            raise ContractError("replacement operation is invalid")
        _non_empty_text(operation.get("id"), "operation id")
        _non_empty_text(operation.get("targetRegion"), "operation targetRegion")
        if operation.get("clearOldContent") is not True:
            raise ContractError("every replacement operation must clear old content")
        if not isinstance(operation.get("targetComponentIds"), list) or not operation["targetComponentIds"]:
            raise ContractError("replacement operation requires target components")
        if not isinstance(operation.get("stableAnchors"), list):
            raise ContractError("replacement operation requires stableAnchors")
    canvas = strategy.get("targetCanvas")
    if not isinstance(canvas, Mapping) or canvas.get("route") not in replacement["canvasRoutes"]:
        raise ContractError("targetCanvas route is invalid")
    _non_empty_text(canvas.get("targetRegion"), "targetCanvas targetRegion")
    if not isinstance(canvas.get("excludedRegions"), list):
        raise ContractError("targetCanvas excludedRegions must be an array")
    features = strategy.get("visualFeatures")
    if not isinstance(features, Mapping):
        raise ContractError("visualFeatures must be an object")
    if set(replacement["requiredVisualFeatures"]) - features.keys():
        raise ContractError("visualFeatures are incomplete")
    for name in replacement["requiredVisualFeatures"]:
        _non_empty_text(features[name], f"visualFeatures.{name}")
    if not isinstance(strategy.get("frozenSet"), list) or not strategy["frozenSet"]:
        raise ContractError("frozenSet must be non-empty")
    if not isinstance(strategy.get("spatialRelations"), list):
        raise ContractError("spatialRelations must be an array")


def validate_replacement_strategy(strategy: Mapping[str, Any]) -> None:
    required = {
        "itemId",
        "revision",
        "ruleVersion",
        "sourceImageSha256",
        "inputImage",
        "sourcePreview",
        "replacementTarget",
        "replacementValue",
        "sourceCategory",
        "selectedCategory",
        "sourceIdentityFingerprint",
        "selectedIdentityFingerprint",
        "identityResearch",
        "sourceIdentityUnitIds",
        "subjectContinuityEvidence",
        "identityBindingGroups",
        "assetUnitIds",
        "assetBindingGroups",
        "dependencyClosure",
        "textActions",
        "markActions",
        "operations",
        "targetCanvas",
        "frozenSet",
        "visualFeatures",
        "spatialRelations",
        "risks",
        "promptSections",
        "prompt",
        "image_size",
    }
    missing = required - strategy.keys()
    if missing:
        raise ContractError(f"replacement strategy missing: {sorted(missing)}")
    if not strategy["replacementTarget"] or not strategy["replacementValue"]:
        raise ContractError("replacement is mandatory")
    _non_empty_text(strategy["sourcePreview"], "sourcePreview")
    if not isinstance(strategy["risks"], list):
        raise ContractError("risks must be an array")
    if not isinstance(strategy["revision"], int) or strategy["revision"] < 1:
        raise ContractError("revision must be a positive integer")
    if not re_fullmatch_sha256(strategy["sourceImageSha256"]):
        raise ContractError("sourceImageSha256 must be lowercase SHA-256")
    input_image = strategy["inputImage"]
    if (
        not isinstance(input_image, Mapping)
        or set(input_image) != {"uri", "sha256"}
        or input_image.get("sha256") != strategy["sourceImageSha256"]
    ):
        raise ContractError("inputImage must bind the source URI and SHA-256")
    _non_empty_text(input_image.get("uri"), "inputImage.uri")
    _validate_category_continuity(strategy)
    _validate_identity_groups(strategy)
    _validate_region_actions(strategy)
    _validate_operations_and_visuals(strategy)
    compiled_prompt = compile_replacement_prompt(strategy["promptSections"])
    if strategy["prompt"] != compiled_prompt:
        raise ContractError("prompt must equal the canonical structured prompt compilation")
    if strategy["image_size"] not in _contract()["generation"]["sizes"]:
        raise ContractError("replacement strategy image_size is invalid")


def re_fullmatch_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(ch in "0123456789abcdef" for ch in value)


def build_strategy_review_package(strategy: Mapping[str, Any]) -> dict[str, Any]:
    """Return the complete pre-generation human review stop."""

    validate_replacement_strategy(strategy)
    strategy_sha = sha256_json(strategy)
    prompt_sha = sha256_bytes(strategy["prompt"].encode("utf-8"))
    input_uri_sha = uri_sha256(strategy["inputImage"]["uri"])
    return {
        "state": "awaiting_strategy_approval",
        "itemId": strategy["itemId"],
        "revision": strategy["revision"],
        "ruleVersion": strategy["ruleVersion"],
        "sourceImageSha256": strategy["sourceImageSha256"],
        "inputImage": dict(strategy["inputImage"]),
        "inputUriSha256": input_uri_sha,
        "sourcePreview": strategy["sourcePreview"],
        "replacementTarget": strategy["replacementTarget"],
        "replacementValue": strategy["replacementValue"],
        "categoryContinuity": {
            "sourceCategory": strategy["sourceCategory"],
            "selectedCategory": strategy["selectedCategory"],
            "crossCategoryMechanism": strategy.get("crossCategoryMechanism"),
        },
        "identityResearch": dict(strategy["identityResearch"]),
        "sourceIdentityUnitIds": list(strategy["sourceIdentityUnitIds"]),
        "subjectContinuityEvidence": deepcopy_list(strategy["subjectContinuityEvidence"]),
        "identityBindingGroups": deepcopy_list(strategy["identityBindingGroups"]),
        "assetUnitIds": list(strategy["assetUnitIds"]),
        "assetBindingGroups": deepcopy_list(strategy["assetBindingGroups"]),
        "dependencyClosure": deepcopy_list(strategy["dependencyClosure"]),
        "textActions": deepcopy_list(strategy["textActions"]),
        "markActions": deepcopy_list(strategy["markActions"]),
        "operations": deepcopy_list(strategy["operations"]),
        "targetCanvas": dict(strategy["targetCanvas"]),
        "frozenSet": list(strategy["frozenSet"]),
        "risks": deepcopy_list(strategy["risks"]),
        "promptSections": dict(strategy["promptSections"]),
        "prompt": strategy["prompt"],
        "imageSize": strategy["image_size"],
        "expectedFalCalls": 1,
        "objectSha256": strategy_sha,
        "strategySha256": strategy_sha,
        "promptSha256": prompt_sha,
    }


def deepcopy_list(value: Sequence[Any]) -> list[Any]:
    return json.loads(json.dumps(list(value), ensure_ascii=False))


def allocate_replacement_fingerprints(
    candidates_by_item: Mapping[str, Sequence[str]],
) -> dict[str, str]:
    """Allocate compatible fingerprints deterministically with minimal cross-item sharing."""

    if not candidates_by_item or len(candidates_by_item) > _contract()["batch"]["maximumItems"]:
        raise ContractError("replacement allocation requires 1–100 items")
    normalized: dict[str, tuple[str, ...]] = {}
    for item_id, candidates in candidates_by_item.items():
        _non_empty_text(item_id, "batch itemId")
        if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
            raise ContractError("replacement candidates must be a sequence")
        unique = tuple(sorted(set(candidates)))
        if not unique or any(not isinstance(value, str) or not value for value in unique):
            raise ContractError("every item requires compatible replacement fingerprints")
        normalized[item_id] = unique
    usage: dict[str, int] = {}
    allocations: dict[str, str] = {}
    for item_id in sorted(normalized):
        candidates = normalized[item_id]
        selected = min(
            candidates,
            key=lambda fingerprint: (
                usage.get(fingerprint, 0),
                sha256_bytes(f"{item_id}\0{fingerprint}".encode()),
                fingerprint,
            ),
        )
        allocations[item_id] = selected
        usage[selected] = usage.get(selected, 0) + 1
    return allocations


def compile_fal_request(request: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    """Validate the complete paid-request contract before returning adapter input."""

    expected_keys = {
        "model",
        "quality",
        "num_images",
        "output_format",
        "image_size",
        "input_image_url",
        "prompt",
    }
    if set(request) != expected_keys:
        missing = sorted(expected_keys - request.keys())
        extra = sorted(request.keys() - expected_keys)
        raise ContractError(f"generation fields mismatch; missing={missing}, extra={extra}")

    generation = _contract()["generation"]
    for field in ("model", "quality", "num_images", "output_format"):
        if request[field] != generation[field]:
            raise ContractError(f"generation contract mismatch: {field}")
    size_name = request["image_size"]
    if size_name not in generation["sizes"]:
        raise ContractError("generation contract mismatch: image_size")
    if not isinstance(request["input_image_url"], str) or not request["input_image_url"]:
        raise ContractError("input_image_url is required")
    if not isinstance(request["prompt"], str) or not request["prompt"].strip():
        raise ContractError("prompt is required")

    payload = {
        "image_urls": [request["input_image_url"]],
        "prompt": request["prompt"],
        "quality": generation["quality"],
        "num_images": generation["num_images"],
        "output_format": generation["output_format"],
        "image_size": dict(generation["sizes"][size_name]),
    }
    return generation["model"], payload


def submit_generation_request(
    request: Mapping[str, Any], adapter: FalEditAdapter
) -> Mapping[str, Any]:
    """Public adapter seam: preflight completes before any request is possible."""

    model, payload = compile_fal_request(request)
    return adapter.submit_edit(model, payload)


def submit_authorized_generation(
    strategy: Mapping[str, Any],
    approval: Mapping[str, Any],
    adapter: FalEditAdapter,
    input_image_url: str,
    *,
    input_image_bytes: bytes,
    attempt_state: MutableMapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    """Submit exactly once after a fresh, object-bound human strategy approval."""

    validate_replacement_strategy(strategy)
    strategy_sha = sha256_json(strategy)
    prompt_sha = sha256_bytes(strategy["prompt"].encode("utf-8"))
    input_uri_sha = uri_sha256(input_image_url)
    if not isinstance(input_image_bytes, bytes) or not input_image_bytes:
        raise ContractError("generation input bytes are required")
    input_image_sha256 = sha256_bytes(input_image_bytes)
    expected_input = strategy["inputImage"]
    expected_binding = {
        "objectSha256": strategy_sha,
        "strategySha256": strategy_sha,
        "promptSha256": prompt_sha,
        "sourceImageSha256": strategy["sourceImageSha256"],
        "inputUriSha256": input_uri_sha,
        "ruleVersion": strategy["ruleVersion"],
        "revision": strategy["revision"],
    }
    if set(approval) != {
        "decision", "objectSha256", "strategySha256", "promptSha256",
        "sourceImageSha256", "inputUriSha256", "reviewerRef", "decidedAt",
        "ruleVersion", "revision",
    }:
        raise ContractError("strategy approval fields differ from the frozen schema")
    _validate_human_facts(approval)
    if approval.get("decision") != "APPROVED" or any(
        approval.get(key) != value for key, value in expected_binding.items()
    ):
        raise ContractError("strategy approval is missing or stale")
    if (
        input_image_url != expected_input["uri"]
        or input_image_sha256 != expected_input["sha256"]
        or input_image_sha256 != strategy["sourceImageSha256"]
    ):
        raise ContractError("generation input differs from the approved image identity")
    provider_input = image_data_uri(input_image_bytes)
    if attempt_state is None:
        raise ContractError("durable generation attempt state is required")

    request_identity = sha256_json({
        "strategySha256": strategy_sha,
        "promptSha256": prompt_sha,
        "inputImageSha256": input_image_sha256,
        "inputUriSha256": input_uri_sha,
        "ruleVersion": strategy["ruleVersion"],
        "revision": strategy["revision"],
    })
    resume_after_hosting_failure = False
    if attempt_state:
        if attempt_state.get("requestIdentity") != request_identity:
            raise ContractError("generation attempt belongs to another approved strategy")
        if attempt_state.get("state") == "provider_pending":
            return dict(attempt_state["providerResponse"])
        if attempt_state.get("state") == "input_hosting_failed":
            resume_after_hosting_failure = True
        if attempt_state.get("state") in {"submitting", "submission_unknown"}:
            raise ContractError("submission outcome must be reconciled; resubmit prohibited")
        if not resume_after_hosting_failure:
            raise ContractError("generation attempt state cannot authorize another submit")

    generation = _contract()["generation"]
    request = {
        "model": generation["model"],
        "quality": generation["quality"],
        "num_images": generation["num_images"],
        "output_format": generation["output_format"],
        "image_size": strategy["image_size"],
        "input_image_url": provider_input,
        "prompt": strategy["prompt"],
    }
    if resume_after_hosting_failure:
        attempt_state["state"] = "submitting"
    else:
        attempt_state.update({
            "requestIdentity": request_identity,
            "strategySha256": strategy_sha,
            "promptSha256": prompt_sha,
            "inputImageSha256": input_image_sha256,
            "inputUriSha256": input_uri_sha,
            "ruleVersion": strategy["ruleVersion"],
            "revision": strategy["revision"],
            "state": "submitting",
            "model": generation["model"],
            "quality": generation["quality"],
            "num_images": generation["num_images"],
            "output_format": generation["output_format"],
            "image_size": strategy["image_size"],
            "expectedFalCalls": 1,
        })
    try:
        response = submit_generation_request(request, adapter)
    except InputHostingError:
        attempt_state["state"] = "input_hosting_failed"
        raise
    except ExternalAdapterError as exc:
        attempt_state["state"] = "provider_rejected" if exc.outcome_known else "submission_unknown"
        if exc.status_code is not None:
            attempt_state["providerFailure"] = {
                "statusCode": exc.status_code,
                **({"errorType": exc.error_type} if exc.error_type else {}),
            }
        raise
    except Exception:
        attempt_state["state"] = "submission_unknown"
        raise
    try:
        summary = summarize_provider_response(response)
    except ContractError:
        attempt_state["state"] = "provider_failed"
        raise
    attempt_state["state"] = "provider_pending"
    attempt_state["providerResponse"] = summary
    return response


def record_no_request_reconciliation(
    attempt_state: MutableMapping[str, Any],
    evidence: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Close an unknown submit only after complete, bounded FAL request-history evidence."""

    if attempt_state.get("state") != "submission_unknown":
        raise ContractError("only submission_unknown can be reconciled as no request created")
    expected_endpoint = _contract()["generation"]["model"]
    if set(evidence) != {
        "source", "endpoint", "windowStart", "windowEnd", "checkedAt",
        "queryComplete", "observedRequestIds",
    }:
        raise ContractError("submission reconciliation evidence fields differ from the frozen schema")
    if evidence.get("source") != "fal_request_history" or evidence.get("endpoint") != expected_endpoint:
        raise ContractError("submission reconciliation must use FAL history for the approved endpoint")
    for name in ("windowStart", "windowEnd", "checkedAt"):
        value = _non_empty_text(evidence.get(name), name)
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ContractError(f"{name} must be an ISO-8601 timestamp") from exc
    if evidence.get("queryComplete") is not True:
        raise ContractError("incomplete provider history cannot prove that no request was created")
    observed = evidence.get("observedRequestIds")
    if not isinstance(observed, list) or observed:
        raise ContractError("non-empty provider history requires request-level reconciliation")
    attempt_state["state"] = "provider_rejected"
    attempt_state["reconciliation"] = {
        **dict(evidence),
        "observedRequestCount": 0,
        "conclusion": "no_request_created",
    }
    return dict(attempt_state)


def summarize_provider_response(response: Mapping[str, Any]) -> dict[str, Any]:
    """Persist only the provider request identity and optional status."""

    request_id = response.get("request_id")
    if not isinstance(request_id, str) or not request_id:
        raise ContractError("provider response is missing request_id")
    summary = {"request_id": request_id}
    if isinstance(response.get("status"), str) and response["status"]:
        summary["status"] = response["status"]
    return summary


def build_revision_review_context(
    history: Sequence[Mapping[str, Any]],
    current_revision: int,
    reason_treatments: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    """Project immutable previous facts for the next human image review."""

    if current_revision < 1:
        raise ContractError("current revision must be positive")
    if not history:
        return {
            "currentRevision": current_revision,
            "previousRevision": None,
            "currentCorrectionPlan": {"reasonTreatments": list(reason_treatments)},
            "fullHistory": {"readOnly": True, "collapsedByDefault": True, "entries": []},
        }

    allowed_classes = set(_contract()["failureClasses"])
    prior = [dict(item) for item in history]
    for item in prior:
        required = {
            "revision",
            "generatedImage",
            "reasonCodes",
            "humanNote",
            "decidedAt",
            "reviewerRef",
            "visualReviewSha256",
            "failureClass",
        }
        if required - item.keys():
            raise ContractError("prior review is incomplete")
        if item["failureClass"] not in allowed_classes:
            raise ContractError("unknown failure class")
    previous = prior[-1]
    if previous["revision"] >= current_revision:
        raise ContractError("previous revision must precede current revision")
    treatments: dict[str, str] = {}
    for item in reason_treatments:
        if not isinstance(item, Mapping):
            raise ContractError("correction treatments must be objects")
        reason_code = _non_empty_text(item.get("reasonCode"), "correction reasonCode")
        treatment = _non_empty_text(item.get("treatment"), "correction treatment")
        if reason_code in treatments:
            raise ContractError("correction reason codes must be unique")
        treatments[reason_code] = treatment
    if set(treatments) != set(previous["reasonCodes"]):
        raise ContractError("every previous rejection reason requires one correction treatment")
    previous_projection = {key: previous[key] for key in (
        "revision",
        "generatedImage",
        "reasonCodes",
        "humanNote",
        "decidedAt",
        "reviewerRef",
        "visualReviewSha256",
        "failureClass",
    )}
    previous_projection["readOnly"] = True
    return {
        "currentRevision": current_revision,
        "previousVisualReviewSha256": previous["visualReviewSha256"],
        "previousFailedGates": list(previous["reasonCodes"]),
        "previousRevision": previous_projection,
        "currentCorrectionPlan": {"reasonTreatments": [dict(x) for x in reason_treatments]},
        "fullHistory": {"readOnly": True, "collapsedByDefault": True, "entries": prior},
    }


def build_image_review_package(
    png_bytes: bytes,
    source_image: Mapping[str, Any],
    image_facts: Mapping[str, Any],
    *,
    item_id: str,
    rule_version: str,
    revision: int,
    evidence: Sequence[Mapping[str, Any]],
    hard_failures: Sequence[Mapping[str, Any]],
    warnings: Sequence[Mapping[str, Any]],
    revision_context: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the post-generation evidence package without granting approval."""

    if not png_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ContractError("image review input must be PNG bytes")
    _non_empty_text(item_id, "itemId")
    _non_empty_text(rule_version, "ruleVersion")
    if not isinstance(revision, int) or revision < 1:
        raise ContractError("image review revision must be positive")
    if revision_context.get("currentRevision") != revision:
        raise ContractError("revision review context belongs to another revision")
    digest = sha256_bytes(png_bytes)
    source_required = {"uri", "sha256", "width", "height", "mime"}
    if set(source_image) != source_required or not re_fullmatch_sha256(source_image.get("sha256")):
        raise ContractError("source image review facts are invalid")
    _non_empty_text(source_image.get("uri"), "source image URI")
    if source_image.get("mime", "").split("/")[0] != "image":
        raise ContractError("source review input must be an image")
    if not isinstance(source_image.get("width"), int) or source_image["width"] < 1:
        raise ContractError("source image width is invalid")
    if not isinstance(source_image.get("height"), int) or source_image["height"] < 1:
        raise ContractError("source image height is invalid")
    if image_facts.get("sha256") not in {None, digest}:
        raise ContractError("image review facts contain a different image SHA")
    uri = _non_empty_text(image_facts.get("uri"), "generated image URI")
    width, height = image_facts.get("width"), image_facts.get("height")
    if not isinstance(width, int) or width < 1 or not isinstance(height, int) or height < 1:
        raise ContractError("generated image dimensions are invalid")
    for label, values in (("hardFailures", hard_failures), ("warnings", warnings)):
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes)) or not all(
            isinstance(item, Mapping) for item in values
        ):
            raise ContractError(f"{label} must contain objects")
    required_gates = set(required_image_review_gates())
    if not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes)):
        raise ContractError("image review evidence must be an array")
    evidence_by_gate: dict[str, Mapping[str, Any]] = {}
    for item in evidence:
        if not isinstance(item, Mapping):
            raise ContractError("image review evidence entries must be objects")
        gate = _non_empty_text(item.get("gate"), "image review evidence gate")
        if gate in evidence_by_gate or gate not in required_gates:
            raise ContractError("image review evidence gates must be unique and frozen")
        if not isinstance(item.get("passed"), bool):
            raise ContractError("image review evidence passed must be boolean")
        _non_empty_text(item.get("summary"), "image review evidence summary")
        evidence_by_gate[gate] = item
    if set(evidence_by_gate) != required_gates:
        raise ContractError("image review evidence must cover every required visual gate")
    machine_blocked = bool(hard_failures) or any(
        not item["passed"] for item in evidence_by_gate.values()
    )
    return {
        "state": "awaiting_image_approval",
        "itemId": item_id,
        "ruleVersion": rule_version,
        "revision": revision,
        "sourceImage": dict(source_image),
        "generatedImage": {
            "uri": uri,
            "sha256": digest,
            "width": width,
            "height": height,
            "mime": "image/png",
        },
        "evidence": deepcopy_list(evidence),
        "hardFailures": deepcopy_list(hard_failures),
        "warnings": deepcopy_list(warnings),
        "revisionContext": json.loads(json.dumps(revision_context, ensure_ascii=False)),
        "machineDecision": "blocked" if machine_blocked else "eligible_for_human_review",
    }


def approve_generated_png(
    png_bytes: bytes,
    review: Mapping[str, Any],
    image_review_package: Mapping[str, Any],
    *,
    rule_version: str,
    revision: int,
) -> dict[str, Any]:
    """Create the only downstream envelope after a fresh human image approval."""

    if not png_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ContractError("approved image must be PNG bytes")
    digest = sha256_bytes(png_bytes)
    if image_review_package.get("state") != "awaiting_image_approval":
        raise ContractError("image review package is not awaiting human approval")
    if image_review_package.get("hardFailures"):
        raise ContractError("visual hard failures cannot be overridden by approval")
    if image_review_package.get("machineDecision") != "eligible_for_human_review":
        raise ContractError("machine visual gates must pass before approval")
    evidence = image_review_package.get("evidence")
    if not isinstance(evidence, list) or len(evidence) != len(required_image_review_gates()):
        raise ContractError("reviewed machine evidence is incomplete")
    evidence_gates = set()
    for item in evidence:
        if not isinstance(item, Mapping):
            raise ContractError("reviewed machine evidence is invalid")
        gate = item.get("gate")
        if gate in evidence_gates or gate not in required_image_review_gates():
            raise ContractError("reviewed machine evidence roles are invalid")
        if item.get("passed") is not True:
            raise ContractError("reviewed machine evidence contains a failed gate")
        _non_empty_text(item.get("summary"), "reviewed evidence summary")
        evidence_gates.add(gate)
    if evidence_gates != set(required_image_review_gates()):
        raise ContractError("reviewed machine evidence does not cover every gate")
    package_image = image_review_package.get("generatedImage", {})
    review_package_sha = sha256_json(image_review_package)
    if set(review) != {
        "decision", "objectSha256", "reviewPackageSha256", "reviewerRef", "decidedAt",
        "ruleVersion", "revision",
    }:
        raise ContractError("image approval fields differ from the frozen schema")
    _validate_human_facts(review)
    if (
        review.get("decision") != "APPROVED"
        or review.get("objectSha256") != digest
        or review.get("reviewPackageSha256") != review_package_sha
        or review.get("ruleVersion") != rule_version
        or review.get("revision") != revision
        or package_image.get("sha256") != digest
        or image_review_package.get("ruleVersion") != rule_version
        or image_review_package.get("revision") != revision
    ):
        raise ContractError("image approval is missing or bound to another image")
    if not isinstance(rule_version, str) or not rule_version or not isinstance(revision, int) or revision < 1:
        raise ContractError("image review binding is invalid")
    width, height = package_image.get("width"), package_image.get("height")
    uri = package_image.get("uri")
    mime = package_image.get("mime")
    if not isinstance(width, int) or width < 1 or not isinstance(height, int) or height < 1:
        raise ContractError("approved image dimensions are invalid")
    if not isinstance(uri, str) or not uri or mime != "image/png":
        raise ContractError("approved image URI is required")
    return {
        "schemaVersion": 1,
        "status": "approved",
        "image": {
            "uri": uri,
            "sha256": digest,
            "width": width,
            "height": height,
            "mime": mime,
        },
    }


def write_production_index(
    runtime_root: Path,
    items: Sequence[Mapping[str, Any]],
    *,
    generated_at: str,
) -> Path:
    """Atomically merge scanner state by (skill, itemId, revision)."""

    limits = _contract()["batch"]
    if (
        not isinstance(items, Sequence)
        or isinstance(items, (str, bytes))
        or not limits["minimumItems"] <= len(items) <= limits["maximumItems"]
    ):
        raise ContractError("production index updates require 1–100 items")
    raw_root = Path(runtime_root)
    if raw_root.exists() and raw_root.is_symlink():
        raise ContractError("runtime root must not be a symlink")
    root = raw_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    index_dir = root / "index"
    if index_dir.exists() and (index_dir.is_symlink() or not index_dir.is_dir()):
        raise ContractError("production index directory is unsafe")
    index_dir.mkdir(exist_ok=True)
    schema_path = _SKILL_ROOT / "references/contracts/production-index.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    target = index_dir / "production-index.json"
    lock_path = index_dir / ".production-index.lock"
    if lock_path.exists() and lock_path.is_symlink():
        raise ContractError("production index lock path is unsafe")
    lock_flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    try:
        lock_fd = os.open(lock_path, lock_flags, 0o600)
    except OSError:
        raise ContractError("production index lock path is unsafe") from None
    with os.fdopen(lock_fd, "a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        existing_items: list[Mapping[str, Any]] = []
        if target.exists():
            if target.is_symlink() or not target.is_file():
                raise ContractError("production index target is unsafe")
            try:
                previous = json.loads(target.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ContractError("existing production index is corrupt") from exc
            previous_errors = sorted(
                Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(previous),
                key=lambda error: list(error.path),
            )
            if previous_errors:
                raise ContractError("existing production index violates its schema")
            existing_items = previous["items"]
        merged: dict[tuple[str, str, int], dict[str, Any]] = {}
        for item in [*existing_items, *items]:
            if not isinstance(item, Mapping):
                raise ContractError("production index items must be objects")
            identity = (item.get("skill"), item.get("itemId"), item.get("revision"))
            if not isinstance(identity[0], str) or not isinstance(identity[1], str) or not isinstance(identity[2], int):
                raise ContractError("production index item identity is incomplete")
            merged[identity] = deepcopy(dict(item))
        value = {
            "schemaVersion": 1,
            "generatedAt": generated_at,
            "items": [merged[key] for key in sorted(merged)],
        }
        errors = sorted(
            Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value),
            key=lambda error: list(error.path),
        )
        if errors:
            raise ContractError("production index invalid: " + errors[0].message)
        encoded = (
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode()
        fd, temporary_name = tempfile.mkstemp(
            prefix=".production-index.", suffix=".tmp", dir=index_dir
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
            directory_fd = os.open(index_dir, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if temporary.exists():
                temporary.unlink()
    return target


def _safe_batch_failure(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, AdapterConfigurationError):
        return exc.code, "external adapter configuration is unavailable"
    if isinstance(exc, ContractError):
        return exc.code, "current item failed a deterministic contract gate"
    return "UNEXPECTED_ITEM_FAILURE", "current item failed at an unexpected boundary"


def process_batch(
    items: Sequence[Mapping[str, Any]],
    process_item: Callable[[Mapping[str, Any]], Any],
) -> list[dict[str, Any]]:
    """Process 1–100 image items while keeping failures item-local."""

    limits = _contract()["batch"]
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
        raise ContractError("batch items must be a sequence")
    if not limits["minimumItems"] <= len(items) <= limits["maximumItems"]:
        raise ContractError("batch size must be between 1 and 100")
    results: list[dict[str, Any]] = []
    seen: set[Any] = set()
    for position, item in enumerate(items):
        if not isinstance(item, Mapping):
            results.append({
                "itemId": f"invalid-item-{position + 1}",
                "state": "blocked",
                "revision": None,
                "stage": "input",
                "errorCode": "ITEM_NOT_OBJECT",
                "evidence": "batch item must be an object",
                "recoveryAction": "replace only this item with a valid envelope",
            })
            continue
        item_id = item.get("itemId")
        if not isinstance(item_id, str) or not item_id or item_id in seen:
            results.append({
                "itemId": item_id,
                "state": "blocked",
                "revision": item.get("revision"),
                "stage": "input",
                "errorCode": "ITEM_ID_INVALID",
                "evidence": "itemId must be unique and non-empty",
                "recoveryAction": "correct the current item envelope",
            })
            continue
        seen.add(item_id)
        try:
            results.append({
                "itemId": item_id,
                "state": "completed",
                "revision": item.get("revision"),
                "stage": "image_producer",
                "result": process_item(item),
            })
        except Exception as exc:
            error_code, summary = _safe_batch_failure(exc)
            results.append({
                "itemId": item_id,
                "state": "paused",
                "revision": item.get("revision"),
                "stage": "image_producer",
                "errorCode": error_code,
                "evidence": summary,
                "recoveryAction": "resume only this item after correcting the reported stage",
            })
    return results
