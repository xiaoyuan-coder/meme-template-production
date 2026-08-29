"""Deterministic Gallery v2, key-registry, and OSS finalization gates."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import tempfile
from datetime import datetime
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

import fcntl

from jsonschema import Draft202012Validator, FormatChecker


class ContractError(ValueError):
    """Raised before an external side effect when a contract is invalid."""

    code = "CONTRACT_INVALID"


class AdapterConfigurationError(ContractError):
    """Safe configuration failure at an explicitly selected real adapter."""

    code = "ADAPTER_CONFIGURATION_INVALID"


class ExternalAdapterError(ContractError):
    """Redacted external-provider failure."""

    code = "EXTERNAL_ADAPTER_FAILURE"


class KeyRegistryReader(Protocol):
    def resolveTemplateKey(self, request: Mapping[str, Any]) -> Mapping[str, Any]: ...


class OssAdapter(Protocol):
    def head(self, object_key: str) -> Mapping[str, Any] | None: ...

    def put_create_once(
        self, object_key: str, content: bytes, metadata: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...


class JsonHttpTransport(Protocol):
    def post_json(self, url: str, payload: Mapping[str, Any]) -> Mapping[str, Any]: ...


class UrllibJsonTransport:
    """Minimal no-auth transport for an explicitly supplied local meme-admin URL."""

    def post_json(self, url: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request = Request(url, data=encoded, headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=5) as response:
            value = json.loads(response.read())
        if not isinstance(value, Mapping):
            raise ContractError("key-registry endpoint returned a non-object response")
        return value


class MemeAdminKeyRegistryClient:
    """Portable client for meme-admin's local read-only key resolution endpoint."""

    ENDPOINT_PATH = "/api/v1/template-key-registry/resolve"

    def __init__(self, base_url: str, transport: JsonHttpTransport | None = None) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment:
            raise ContractError("meme-admin base URL is invalid")
        self._endpoint = urljoin(base_url.rstrip("/") + "/", self.ENDPOINT_PATH.lstrip("/"))
        self._transport = transport or UrllibJsonTransport()

    def resolveTemplateKey(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        _validate_registry_request(request)
        try:
            response = self._transport.post_json(self._endpoint, request)
        except ContractError:
            raise
        except Exception:
            raise ExternalAdapterError("key-registry request failed") from None
        _validate_registry_response(response)
        return deepcopy(dict(response))


class AliyunOssAdapter:
    """Create-once OSS adapter with SHA metadata and redacted provider responses."""

    def __init__(self, bucket: Any) -> None:
        self._bucket = bucket

    @staticmethod
    def _header(headers: Mapping[str, Any], name: str) -> Any:
        return headers.get(name) or headers.get(name.lower()) or headers.get(name.title())

    def head(self, object_key: str) -> Mapping[str, Any] | None:
        try:
            result = self._bucket.get_object_meta(object_key)
        except Exception as exc:
            status = getattr(exc, "status", None)
            if status == 404:
                return None
            raise ExternalAdapterError("OSS metadata lookup failed") from None
        headers = getattr(result, "headers", {}) or {}
        return {
            "objectKey": object_key,
            "sha256": self._header(headers, "x-oss-meta-sha256"),
            "byteLength": int(self._header(headers, "x-oss-meta-byte-length") or 0),
            "remoteIdentity": self._header(headers, "x-oss-meta-remote-identity"),
            "requestIdentity": self._header(headers, "x-oss-meta-request-identity"),
        }

    def put_create_once(
        self, object_key: str, content: bytes, metadata: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        headers = {
            "x-oss-forbid-overwrite": "true",
            "Content-Type": "image/png",
            "x-oss-meta-sha256": str(metadata["sha256"]),
            "x-oss-meta-byte-length": str(metadata["byteLength"]),
            "x-oss-meta-remote-identity": str(metadata["remoteIdentity"]),
            "x-oss-meta-request-identity": str(metadata["requestIdentity"]),
        }
        try:
            result = self._bucket.put_object(object_key, content, headers=headers)
        except Exception:
            raise ExternalAdapterError("OSS create-once upload failed") from None
        response = {
            "objectKey": object_key,
            "sha256": metadata["sha256"],
            "byteLength": metadata["byteLength"],
            "remoteIdentity": metadata["remoteIdentity"],
            "requestIdentity": metadata["requestIdentity"],
        }
        request_id = getattr(result, "request_id", None)
        if isinstance(request_id, str) and request_id:
            response["providerRequestId"] = request_id
        return response


def create_aliyun_oss_adapter_from_environment(
    environ: Mapping[str, str] | None = None,
    *,
    module_loader: Callable[[str], Any] = importlib.import_module,
) -> AliyunOssAdapter:
    env = os.environ if environ is None else environ
    names = (
        "OSS_ENDPOINT", "OSS_BUCKET_NAME", "OSS_ACCESS_KEY_ID", "OSS_ACCESS_KEY_SECRET"
    )
    if any(not isinstance(env.get(name), str) or not env[name].strip() for name in names):
        raise AdapterConfigurationError("OSS credentials or target configuration are unavailable")
    try:
        oss2 = module_loader("oss2")
    except (ImportError, ModuleNotFoundError):
        raise AdapterConfigurationError("aliyun-oss2 dependency is unavailable") from None
    try:
        auth = oss2.Auth(env["OSS_ACCESS_KEY_ID"], env["OSS_ACCESS_KEY_SECRET"])
        bucket = oss2.Bucket(auth, env["OSS_ENDPOINT"], env["OSS_BUCKET_NAME"])
    except Exception:
        raise AdapterConfigurationError("OSS adapter initialization failed") from None
    return AliyunOssAdapter(bucket)


_SKILL_ROOT = Path(__file__).resolve().parents[1]
_CONTRACT_PATH = _SKILL_ROOT / "references" / "machine-contract.json"


def _contract() -> dict[str, Any]:
    return json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))


def _sha_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_json(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return _sha_bytes(encoded)


def _validate_key(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(_contract()["keyPattern"], value):
        raise ContractError("key does not match the production pattern")
    return value


def _canonical_source(source: Mapping[str, Any] | None) -> tuple[str, str] | None:
    if source is None:
        return None
    allowed = {"namespace", "sourceAssetId", "sourceSha256"}
    if set(source) - allowed:
        raise ContractError("sourceIdentity contains forbidden heuristic fields")
    namespace, asset_id = source.get("namespace"), source.get("sourceAssetId")
    if not isinstance(namespace, str) or not namespace or not isinstance(asset_id, str) or not asset_id:
        raise ContractError("sourceIdentity requires namespace and sourceAssetId")
    digest = source.get("sourceSha256")
    if digest is not None and (not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest)):
        raise ContractError("sourceSha256 must be lowercase SHA-256")
    return namespace, asset_id


def _validate_registry_request(request: Mapping[str, Any]) -> None:
    allowed = {"proposedKey", "existingKey", "sourceIdentity"}
    if not isinstance(request, Mapping) or set(request) - allowed or "proposedKey" not in request:
        raise ContractError("invalid key-registry request fields")
    _validate_key(request["proposedKey"])
    if request.get("existingKey") is not None:
        _validate_key(request["existingKey"])
    _canonical_source(request.get("sourceIdentity"))


class SnapshotKeyRegistryReader:
    """Contract-compatible, read-only adapter for tests or portable snapshots."""

    def __init__(
        self,
        registry_revision: str,
        entries: Sequence[Mapping[str, Any]],
        *,
        available: bool = True,
    ) -> None:
        self.registry_revision = registry_revision
        self.entries = tuple(deepcopy(list(entries)))
        self.available = available

    def _response(
        self,
        decision: str,
        resolved_key: str | None,
        matched_by: Sequence[str],
        evidence: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        if decision not in _contract()["keyDecisions"]:
            raise AssertionError("adapter emitted an unknown registry decision")
        return {
            "registryRevision": self.registry_revision if self.available else None,
            "decision": decision,
            "resolvedKey": resolved_key,
            "matchedBy": list(matched_by),
            "evidence": [dict(item) for item in evidence],
        }

    def resolveTemplateKey(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        _validate_registry_request(request)
        proposed = _validate_key(request["proposedKey"])
        existing = request.get("existingKey")
        if existing is not None:
            existing = _validate_key(existing)
        source = request.get("sourceIdentity")
        canonical = _canonical_source(source)
        source_sha = source.get("sourceSha256") if source else None
        if not self.available:
            return self._response("REGISTRY_UNAVAILABLE", None, [], [{"reason": "registry unavailable"}])

        by_key = {entry["key"]: entry for entry in self.entries}
        canonical_matches = [
            entry for entry in self.entries
            if canonical is not None
            and _canonical_source(entry.get("sourceIdentity")) == canonical
        ]
        alias_matches = [
            entry for entry in self.entries
            if source_sha is not None and source_sha in entry.get("legacySourceSha256Aliases", [])
        ]

        if existing is not None:
            registered = by_key.get(existing)
            if registered is None:
                return self._response(
                    "SOURCE_CONFLICT", None, ["existingKey"],
                    [{"existingKey": existing, "registered": False}],
                )
            if canonical is not None and _canonical_source(registered.get("sourceIdentity")) != canonical:
                return self._response(
                    "SOURCE_CONFLICT", existing, ["existingKey", "sourceIdentity"],
                    [{"existingKey": existing, "reason": "registered source differs"}],
                )
            registered_sha = registered.get("sourceIdentity", {}).get("sourceSha256")
            if source_sha is not None and registered_sha is not None and source_sha != registered_sha:
                return self._response(
                    "SOURCE_CONFLICT", existing, ["existingKey", "sourceSha256"],
                    [{"existingKey": existing, "reason": "source integrity digest differs"}],
                )
            if proposed != existing:
                return self._response(
                    "SOURCE_CONFLICT", existing, ["existingKey"],
                    [{"existingKey": existing, "proposedKey": proposed}],
                )
            return self._response(
                "EXISTING_SAME_SOURCE", existing, ["existingKey"],
                [{"existingKey": existing, "registered": True}],
            )

        if canonical_matches:
            if len(canonical_matches) != 1:
                return self._response(
                    "SOURCE_CONFLICT", None, ["sourceIdentity"],
                    [{"reason": "source identity has multiple registry bindings"}],
                )
            registered = canonical_matches[0]
            registered_key = registered["key"]
            registered_sha = registered.get("sourceIdentity", {}).get("sourceSha256")
            if source_sha is not None and registered_sha is not None and source_sha != registered_sha:
                return self._response(
                    "SOURCE_CONFLICT", registered_key, ["sourceIdentity", "sourceSha256"],
                    [{"reason": "source integrity digest differs"}],
                )
            if registered_key == proposed:
                return self._response(
                    "EXISTING_SAME_SOURCE", registered_key, ["sourceIdentity"],
                    [{"namespace": canonical[0], "sourceAssetId": canonical[1]}],
                )
            return self._response(
                "SOURCE_CONFLICT", registered_key, ["sourceIdentity"],
                [{"registeredKey": registered_key, "proposedKey": proposed}],
            )

        if alias_matches:
            if len(alias_matches) != 1:
                return self._response(
                    "SOURCE_CONFLICT", None, ["legacySourceSha256Alias"],
                    [{"reason": "legacy alias has multiple registry bindings"}],
                )
            registered_key = alias_matches[0]["key"]
            if registered_key == proposed:
                return self._response(
                    "EXISTING_SAME_SOURCE", registered_key, ["legacySourceSha256Alias"],
                    [{"sourceSha256": source_sha, "registeredAlias": True}],
                )
            return self._response(
                "SOURCE_CONFLICT", registered_key, ["legacySourceSha256Alias"],
                [{"registeredKey": registered_key, "proposedKey": proposed}],
            )

        if proposed in by_key:
            return self._response(
                "KEY_COLLISION", None, ["proposedKey"],
                [{"proposedKey": proposed, "reason": "bound to another source"}],
            )
        return self._response("NEW", proposed, [], [{"proposedKey": proposed, "available": True}])


def validate_approved_image_envelope(envelope: Mapping[str, Any]) -> None:
    schema_path = _SKILL_ROOT / "references/contracts/approved-template-image-envelope.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(envelope), key=lambda e: list(e.path))
    if errors:
        raise ContractError("approved image envelope invalid: " + errors[0].message)


def _non_empty_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} must be non-empty text")
    return value.strip()


def _flatten_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return "\n".join(_flatten_text(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return "\n".join(_flatten_text(item) for item in value)
    return ""


_PROMPT_SLOT = re.compile(
    r'\{\{\s*([a-z][a-z0-9_]*)\s*\|\s*"([^"{}]*)"\s*\}\}'
)


def validate_approved_image_analysis(
    analysis: Mapping[str, Any], approved_image: Mapping[str, Any]
) -> None:
    """Validate the independent visual fact model used by every authored field."""

    validate_approved_image_envelope(approved_image)
    required = {
        "schemaVersion", "approvedImageSha256", "visualMechanism", "componentGraph",
        "templateValue",
        "identityTopology", "textRegions", "mediumComposition", "spatialRelations",
        "containers", "fixedStructure", "editableCandidates", "counts", "fieldEvidence",
        "titleEvidence", "tagEvidence", "slotEvidence", "promptCoverage",
        "translationEquivalences", "semanticModel", "selfReview",
        "warnings",
    }
    allowed = required | {"singleSlotExhaustion"}
    if not required.issubset(analysis) or not set(analysis).issubset(allowed):
        raise ContractError(
            f"approved image analysis fields mismatch; missing={sorted(required - analysis.keys())}, "
            f"extra={sorted(analysis.keys() - allowed)}"
        )
    if analysis["schemaVersion"] != 2:
        raise ContractError("approved image analysis schemaVersion must be 2")
    if analysis["approvedImageSha256"] != approved_image["image"]["sha256"]:
        raise ContractError("approved image analysis belongs to another image")
    _non_empty_text(analysis["visualMechanism"], "visualMechanism")
    template_value = analysis["templateValue"]
    if not isinstance(template_value, Mapping) or set(template_value) != {
        "whySelected", "templateHook", "fixedMechanism", "backendOnlyFacts"
    }:
        raise ContractError("templateValue must explain selection, hook, mechanism, and backend facts")
    _non_empty_text(template_value["whySelected"], "templateValue.whySelected")
    _non_empty_text(template_value["templateHook"], "templateValue.templateHook")
    for name in ("fixedMechanism", "backendOnlyFacts"):
        if not isinstance(template_value[name], list) or not template_value[name] or not all(
            isinstance(item, str) and item.strip() for item in template_value[name]
        ):
            raise ContractError(f"templateValue.{name} must contain concrete facts")
    for name in (
        "componentGraph", "identityTopology", "textRegions", "spatialRelations",
        "containers", "fixedStructure", "editableCandidates", "warnings",
    ):
        if not isinstance(analysis[name], list):
            raise ContractError(f"{name} must be an array")
    if not analysis["componentGraph"] or not analysis["fixedStructure"]:
        raise ContractError("componentGraph and fixedStructure must be non-empty")
    counts = analysis["counts"]
    count_fields = {"identityCount", "visualInstanceCount", "uploadAssetCount", "inputControlCount"}
    if not isinstance(counts, Mapping) or set(counts) != count_fields:
        raise ContractError("analysis counts must contain four independent quantities")
    if not all(isinstance(value, int) and value >= 0 for value in counts.values()):
        raise ContractError("analysis counts must be non-negative integers")
    medium = analysis["mediumComposition"]
    if not isinstance(medium, Mapping) or set(medium) != {
        "medium", "styleTraits", "composition", "colorAndLight"
    }:
        raise ContractError("mediumComposition is incomplete")
    _non_empty_text(medium["medium"], "mediumComposition.medium")
    for name in ("styleTraits", "composition", "colorAndLight"):
        if not isinstance(medium[name], list):
            raise ContractError(f"mediumComposition.{name} must be an array")
    if not medium["styleTraits"] or not medium["composition"]:
        raise ContractError("mediumComposition requires style and composition facts")
    evidence = analysis["fieldEvidence"]
    expected = set(_contract()["authoring"]["expectedEvidenceFields"])
    if not isinstance(evidence, Mapping) or set(evidence) != expected:
        raise ContractError("every formal field requires an independent analysis method and evidence")
    for field, facts in evidence.items():
        if not isinstance(facts, list) or not facts or not all(
            isinstance(item, str) and item.strip() for item in facts
        ):
            raise ContractError(f"fieldEvidence.{field} must contain image-grounded facts")
    title_evidence = analysis["titleEvidence"]
    gates = _contract()["authoring"]["titleGates"]
    if not isinstance(title_evidence, Mapping) or any(title_evidence.get(gate) is not True for gate in gates):
        raise ContractError("title must pass all four portability gates")
    _non_empty_text(title_evidence.get("evidence"), "titleEvidence.evidence")
    _validate_text_regions(analysis["textRegions"])
    _validate_translation_equivalences(analysis["textRegions"], analysis["translationEquivalences"])
    _validate_semantic_model(analysis)


def _validate_translation_equivalences(
    regions: Sequence[Mapping[str, Any]], equivalences: Any
) -> None:
    if not isinstance(equivalences, list):
        raise ContractError("translationEquivalences must be an array")
    by_id = {region.get("regionId"): region for region in regions}
    covered_targets: set[str] = set()
    for value in equivalences:
        if not isinstance(value, Mapping) or set(value) != {
            "sourceRegionId", "targetRegionIds", "sourceTextSha256", "targetTextSha256"
        }:
            raise ContractError("translation equivalence evidence is incomplete")
        source_id = value["sourceRegionId"]
        targets = value["targetRegionIds"]
        if source_id not in by_id or not isinstance(targets, list) or not targets:
            raise ContractError("translation equivalence references unknown regions")
        if len(set(targets)) != len(targets) or any(target not in by_id for target in targets):
            raise ContractError("translation equivalence target regions must be unique and known")
        source_sha = _sha_bytes(by_id[source_id]["exactText"].encode("utf-8"))
        target_sha = {
            target: _sha_bytes(by_id[target]["exactText"].encode("utf-8")) for target in targets
        }
        if value["sourceTextSha256"] != source_sha or value["targetTextSha256"] != target_sha:
            raise ContractError("translation equivalence text digests are stale")
        covered_targets.update(targets)
    declared_targets = {
        region["regionId"] for region in regions if region.get("translationSourceRegionId") is not None
    }
    if declared_targets != covered_targets:
        raise ContractError("translation-equivalent regions require exact equivalence evidence")
    for value in equivalences:
        for target in value["targetRegionIds"]:
            if by_id[target].get("translationSourceRegionId") != value["sourceRegionId"]:
                raise ContractError("translation equivalence source linkage differs from text region facts")


def _validate_semantic_model(analysis: Mapping[str, Any]) -> None:
    model = analysis["semanticModel"]
    required = {
        "promptTemplate", "runtimeSemantics", "componentCoverage", "dynamicFactSources",
        "completeRedrawByTarget", "sourceIsolationByInput",
    }
    if not isinstance(model, Mapping) or set(model) != required:
        raise ContractError("semanticModel is incomplete")
    _non_empty_text(model["promptTemplate"], "semanticModel.promptTemplate")
    if not isinstance(model["runtimeSemantics"], Mapping):
        raise ContractError("semanticModel.runtimeSemantics must be an object")
    component_ids: list[str] = []
    for component in analysis["componentGraph"]:
        if not isinstance(component, Mapping):
            raise ContractError("componentGraph entries must be objects")
        component_ids.append(_non_empty_text(component.get("componentId"), "componentId"))
    if len(set(component_ids)) != len(component_ids):
        raise ContractError("componentGraph IDs must be unique")
    coverage = model["componentCoverage"]
    if not isinstance(coverage, Mapping) or set(coverage) != set(component_ids):
        raise ContractError("componentGraph must be exhaustively projected into semantic coverage")
    allowed_visual_fields = {"medium", "styleTraits", "composition", "relations", "colorAndLight"}
    for component_id, projection in coverage.items():
        if not isinstance(projection, Mapping) or set(projection) != {
            "targetIds", "visualContractFields"
        }:
            raise ContractError(f"component coverage for {component_id} is incomplete")
        if not isinstance(projection["targetIds"], list):
            raise ContractError("component target coverage must be an array")
        fields = projection["visualContractFields"]
        if not isinstance(fields, list) or not fields or not set(fields).issubset(allowed_visual_fields):
            raise ContractError("component visual-contract coverage is invalid")
    for name in ("dynamicFactSources", "completeRedrawByTarget", "sourceIsolationByInput"):
        if not isinstance(model[name], Mapping):
            raise ContractError(f"semanticModel.{name} must be an object")


def compile_semantics_from_analysis(analysis: Mapping[str, Any]) -> dict[str, Any]:
    """Compile both prompt surfaces from the single approved-image semantic model."""

    _validate_semantic_model(analysis)
    return {
        "promptTemplate": analysis["semanticModel"]["promptTemplate"],
        "runtimeSemantics": deepcopy(analysis["semanticModel"]["runtimeSemantics"]),
    }


def _validate_single_slot_exhaustion(exhaustion: Any, slot_id: str) -> None:
    axes = {"subject", "text", "object", "clothing", "color", "prop", "scene", "nested_content"}
    if (
        not isinstance(exhaustion, Mapping)
        or set(exhaustion) != {"selectedSlotIds", "axes"}
        or exhaustion.get("selectedSlotIds") != [slot_id]
        or not isinstance(exhaustion.get("axes"), Mapping)
        or set(exhaustion["axes"]) != axes
    ):
        raise ContractError("single-slot exhaustion evidence must cover every candidate axis")
    occurrences = 0
    for axis, axis_evidence in exhaustion["axes"].items():
        if not isinstance(axis_evidence, Mapping) or set(axis_evidence) != {"candidateSlotIds", "evidence"}:
            raise ContractError(f"single-slot exhaustion axis {axis} is incomplete")
        _non_empty_text(axis_evidence["evidence"], f"single-slot exhaustion {axis}")
        candidates = axis_evidence["candidateSlotIds"]
        if not isinstance(candidates, list) or any(candidate != slot_id for candidate in candidates):
            raise ContractError("single-slot exhaustion names an unknown slot")
        if len(candidates) > 1:
            raise ContractError("single-slot exhaustion repeats its selected slot")
        occurrences += len(candidates)
    if occurrences != 1:
        raise ContractError("single-slot exhaustion must account for the selected slot exactly once")


def _validate_text_regions(regions: Sequence[Mapping[str, Any]]) -> None:
    authoring = _contract()["authoring"]
    seen: set[str] = set()
    for region in regions:
        if not isinstance(region, Mapping):
            raise ContractError("text regions must be objects")
        region_id = _non_empty_text(region.get("regionId"), "text regionId")
        if region_id in seen:
            raise ContractError("text region IDs must be unique")
        seen.add(region_id)
        if region.get("role") not in authoring["textRoles"]:
            raise ContractError("text region role is invalid")
        action = region.get("action")
        if action not in authoring["allowedTextActions"]:
            raise ContractError("text region action is invalid")
        if region["role"] == "watermark" and action != "remove":
            raise ContractError("watermark text can only be removed")
        if region["role"] == "ambiguous" and action != "review":
            raise ContractError("ambiguous text must remain under review")
        for field in ("language", "exactText", "layout", "position"):
            _non_empty_text(region.get(field), f"text region {field}")


def validate_authoring_contract(
    analysis: Mapping[str, Any], formal_draft: Mapping[str, Any], approved_image: Mapping[str, Any]
) -> None:
    """Apply Memebuy authoring rules that are stricter than the Gallery snapshot."""

    validate_approved_image_analysis(analysis, approved_image)
    authoring = _contract()["authoring"]
    title = _non_empty_text(formal_draft.get("title"), "title")
    description = _non_empty_text(formal_draft.get("description"), "description")
    if len(title) > authoring["titleMaxLength"]:
        raise ContractError("title exceeds the stable user-facing limit")
    if len(description) > authoring["descriptionMaxLength"]:
        raise ContractError("description exceeds 20 characters")
    expected_size = f"{approved_image['image']['width']}x{approved_image['image']['height']}"
    if formal_draft.get("imageSize") != expected_size:
        raise ContractError("imageSize must match the Approved Template Image dimensions")
    tags = formal_draft.get("metadata", {}).get("tags")
    if not isinstance(tags, list) or not authoring["tagMinimum"] <= len(tags) <= authoring["tagMaximum"]:
        raise ContractError("metadata.tags must contain 5–8 items")
    if len(set(tags)) != len(tags) or any(
        not isinstance(tag, str) or not tag or len(tag) > authoring["tagMaxLength"] for tag in tags
    ):
        raise ContractError("tags must be unique, non-empty, and at most 12 characters")
    tag_evidence = analysis["tagEvidence"]
    if not isinstance(tag_evidence, Mapping) or set(tag_evidence) != set(tags):
        raise ContractError("every tag requires image evidence")
    for tag, evidence in tag_evidence.items():
        if not isinstance(evidence, Mapping):
            raise ContractError(f"tag evidence for {tag} must be an object")
        _non_empty_text(evidence.get("visualEvidence"), f"tag evidence for {tag}")
        category = evidence.get("category")
        if category not in authoring["tagCategories"]:
            raise ContractError("tag category is invalid")
    if not set(tags).intersection(authoring["majorTagValues"]):
        raise ContractError("tags require at least one exact official major category")
    slots = formal_draft.get("inputSchema", {}).get("slots", [])
    if not isinstance(slots, list) or not slots:
        raise ContractError("inputSchema requires at least one slot")
    slot_ids = [slot.get("id") for slot in slots]
    if any(not isinstance(slot_id, str) or not slot_id for slot_id in slot_ids) or len(set(slot_ids)) != len(slot_ids):
        raise ContractError("slot IDs must be unique and non-empty")
    slot_evidence = analysis["slotEvidence"]
    if not isinstance(slot_evidence, Mapping) or set(slot_evidence) != set(slot_ids):
        raise ContractError("every slot requires independent high-value evidence")
    bindings = formal_draft.get("runtimeSemantics", {}).get("inputBindings", {})
    if not isinstance(bindings, Mapping) or set(bindings) != set(slot_ids):
        raise ContractError("every slot requires exactly one runtime input binding")
    compiled = compile_semantics_from_analysis(analysis)
    if (
        formal_draft.get("promptTemplate") != compiled["promptTemplate"]
        or formal_draft.get("runtimeSemantics") != compiled["runtimeSemantics"]
    ):
        raise ContractError("promptTemplate and runtimeSemantics must compile from one semantic model")
    semantic_model = analysis["semanticModel"]
    dynamic_sources = semantic_model["dynamicFactSources"]
    expected_dynamic_sources = {slot_id: f"inputSchema.slots.{slot_id}" for slot_id in slot_ids}
    if dynamic_sources != expected_dynamic_sources or len(set(dynamic_sources.values())) != len(dynamic_sources):
        raise ContractError("each open value requires one unique dynamic fact source")
    if set(semantic_model["sourceIsolationByInput"]) != {
        slot["id"] for slot in slots if slot.get("image") is not None
    } or any(value is not True for value in semantic_model["sourceIsolationByInput"].values()):
        raise ContractError("every image input requires source-isolation evidence")
    if len(slot_ids) == 1:
        _validate_single_slot_exhaustion(analysis.get("singleSlotExhaustion"), slot_ids[0])
    elif "singleSlotExhaustion" in analysis:
        raise ContractError("singleSlotExhaustion is only valid for a one-slot template")

    targets = formal_draft.get("runtimeSemantics", {}).get("targetInstances", [])
    target_ids = {target.get("id") for target in targets if isinstance(target, Mapping)}
    if len(target_ids) != len(targets) or None in target_ids:
        raise ContractError("runtime target IDs must be unique and non-empty")
    covered_targets: set[str] = set()
    covered_visual_fields: set[str] = set()
    for projection in semantic_model["componentCoverage"].values():
        if any(target_id not in target_ids for target_id in projection["targetIds"]):
            raise ContractError("component coverage references an unknown runtime target")
        covered_targets.update(projection["targetIds"])
        covered_visual_fields.update(projection["visualContractFields"])
    if covered_targets != target_ids:
        raise ContractError("componentGraph must cover every runtime target instance")
    visual_contract_fields = set(formal_draft["runtimeSemantics"]["visualContract"])
    if covered_visual_fields != visual_contract_fields:
        raise ContractError("componentGraph must cover every visualContract field")
    identity_units = analysis["identityTopology"]
    identity_instance_ids: list[str] = []
    for unit in identity_units:
        if (
            not isinstance(unit, Mapping)
            or not isinstance(unit.get("instanceIds"), list)
            or not all(isinstance(instance_id, str) and instance_id for instance_id in unit["instanceIds"])
        ):
            raise ContractError("identityTopology entries require instanceIds")
        identity_instance_ids.extend(unit["instanceIds"])
    image_slot_count = sum(1 for slot in slots if slot.get("image") is not None)
    expected_counts = {
        "identityCount": len(identity_units),
        "visualInstanceCount": len(set(identity_instance_ids)),
        "uploadAssetCount": image_slot_count,
        "inputControlCount": len(slots),
    }
    if analysis["counts"] != expected_counts:
        raise ContractError("analysis counts differ from the independently derived quantities")
    editable_slot_ids: list[str] = []
    component_ids = {component["componentId"] for component in analysis["componentGraph"]}
    for candidate in analysis["editableCandidates"]:
        if not isinstance(candidate, Mapping) or candidate.get("componentId") not in component_ids:
            raise ContractError("editableCandidates references an unknown component")
        if candidate.get("selected") is True:
            if (
                not isinstance(candidate.get("slotId"), str)
                or candidate.get("selectionReason") not in authoring["allowedSlotSelectionReasons"]
                or candidate.get("exclusionReason") is not None
            ):
                raise ContractError("selected editable candidate lacks a valid slot reason")
            editable_slot_ids.append(candidate["slotId"])
        elif candidate.get("selected") is False:
            if candidate.get("slotId") is not None or not isinstance(candidate.get("exclusionReason"), str):
                raise ContractError("excluded editable candidate requires an exclusion reason and no slot")
        else:
            raise ContractError("editable candidate must state whether it was selected")
    if set(editable_slot_ids) != set(slot_ids) or len(editable_slot_ids) != len(set(editable_slot_ids)):
        raise ContractError("editableCandidates must account for every compiled slot")
    has_open_identity = False
    for slot in slots:
        evidence = slot_evidence[slot["id"]]
        if not isinstance(evidence, Mapping) or any(
            evidence.get(name) is not True
            for name in ("userMotivation", "visuallyVisible", "modelControllable", "mechanismPreserved")
        ):
            raise ContractError(f"slot {slot['id']} failed the high-value gate")
        _non_empty_text(evidence.get("visualEvidence"), f"slot evidence {slot['id']}")
        if evidence.get("selectionReason") not in authoring["allowedSlotSelectionReasons"]:
            raise ContractError(f"slot {slot['id']} lacks an allowed selection reason")
        for name in ("defaultValue", "semanticAxis", "granularity"):
            _non_empty_text(evidence.get(name), f"slot evidence {slot['id']}.{name}")
        open_facts = evidence.get("openVisualFacts")
        if not isinstance(open_facts, list) or not open_facts or not all(
            isinstance(fact, str) and fact.strip() for fact in open_facts
        ):
            raise ContractError(f"slot {slot['id']} requires openVisualFacts")
        if slot.get("required") is not authoring["slotDefaults"]["required"]:
            raise ContractError("all production slots must remain optional")
        text_mode = slot.get("text")
        suggestions = text_mode.get("suggestions", []) if isinstance(text_mode, Mapping) else []
        suggestion_checks = evidence.get("suggestionChecks")
        if text_mode is not None:
            if len(suggestions) != 3 or len(set(suggestions)) != 3:
                raise ContractError("text-mode slots require exactly three unique suggestions")
            if text_mode.get("defaultValue") != evidence["defaultValue"]:
                raise ContractError("slot default differs from independent slot evidence")
            if not isinstance(suggestion_checks, list) or [item.get("value") for item in suggestion_checks] != suggestions:
                raise ContractError("suggestion checks must correspond to the authored recommendations")
            if any(
                not isinstance(item, Mapping)
                or any(item.get(name) is not True for name in (
                    "sameAxis", "sameGranularity", "mechanismCompatible"
                ))
                for item in suggestion_checks
            ):
                raise ContractError("recommendations must pass axis, granularity, and mechanism checks")
            if not {evidence["defaultValue"], *suggestions}.issubset(set(open_facts)):
                raise ContractError("openVisualFacts must include the default and all recommendations")
        elif suggestion_checks not in ([], None):
            raise ContractError("pure-image slots cannot carry text recommendation checks")
        image_mode = slot.get("image")
        actual_modes = [name for name, value in (("text", text_mode), ("image", image_mode)) if value is not None]
        mode_decision = evidence.get("inputModeDecision")
        if (
            not isinstance(mode_decision, Mapping)
            or mode_decision.get("modes") != actual_modes
            or mode_decision.get("reason") not in {
                "identity_subject", "dynamic_group", "text_only", "exact_content_asset"
            }
        ):
            raise ContractError("slot input modes require a matching explicit decision")
        _non_empty_text(mode_decision.get("evidence"), "slot input-mode evidence")
        binding = bindings.get(slot["id"])
        if not isinstance(binding, Mapping):
            raise ContractError("every slot requires a runtime input binding")
        binding_kind = (
            binding.get("bindingPolicy")
            if binding.get("operation") == "replace_identity"
            else "replace_content"
        )
        if evidence.get("bindingKind") != binding_kind:
            raise ContractError("slot evidence binding kind differs from runtime semantics")
        if image_mode is not None:
            defaults = authoring["slotDefaults"]
            if (
                image_mode.get("maxCount") != defaults["maxCount"]
                or image_mode.get("minWidth") != defaults["minWidth"]
                or image_mode.get("minHeight") != defaults["minHeight"]
                or set(image_mode.get("sourceOptions", [])) != set(defaults["sourceOptions"])
            ):
                raise ContractError("image slots must use the frozen upload profile")
            if text_mode is not None and slot.get("resolutionStrategy") != defaults["resolutionStrategy"]:
                raise ContractError("composite image/text slots require image_over_text")
            if binding.get("operation") == "replace_identity":
                has_open_identity = True
                if any(
                    semantic_model["completeRedrawByTarget"].get(target_id) is not True
                    for target_id in binding.get("targetIds", [])
                ):
                    raise ContractError("identity targets require complete-redraw evidence")
                inherited = evidence.get("inheritFromUpload")
                fixed = evidence.get("keepFromTemplate")
                if not isinstance(inherited, list) or not inherited or not isinstance(fixed, list):
                    raise ContractError("identity slots require explicit inheritance decisions")
                if set(inherited).intersection(fixed):
                    raise ContractError("identity inheritance and template-fixed traits must be disjoint")
                if evidence.get("sourceIsolation") is not True:
                    raise ContractError("identity images must not import their background or unrelated content")
                if evidence.get("clothingOwnership") != binding.get("clothingOwnership"):
                    raise ContractError("slot clothing ownership differs from its runtime binding")
                if binding_kind == "preserve_group":
                    if text_mode is not None or mode_decision.get("reason") != "dynamic_group":
                        raise ContractError("dynamic groups must use an image-only group-photo input")
                    if binding.get("allowedSourceGrouping") != ["group_photo"]:
                        raise ContractError("dynamic groups only accept a natural group photo")
                    group = evidence.get("groupDecision")
                    required_group_facts = {
                        "wholeGroupIdentityFidelity", "groupPhotoNaturalInput", "variableMemberCount",
                        "sameMemberKind", "noIndividuallyAddressableRoles",
                    }
                    if not isinstance(group, Mapping) or any(group.get(name) is not True for name in required_group_facts):
                        raise ContractError("preserve_group requires all five dynamic-group decisions")
                elif text_mode is None or mode_decision.get("reason") != "identity_subject":
                    raise ContractError("addressable identity subjects require text and image modes")
            elif evidence.get("selectionReason") != "exact_content_asset" or mode_decision.get("reason") != "exact_content_asset":
                raise ContractError("non-identity image inputs require exact-content-asset evidence")
        elif binding.get("operation") == "replace_identity":
            raise ContractError("identity replacement requires an image input")
        elif mode_decision.get("reason") != "text_only":
            raise ContractError("ordinary content slots should remain text-only")
    if has_open_identity and any(
        region.get("role") == "identity" and region.get("action") == "preserve"
        for region in analysis["textRegions"]
    ):
        raise ContractError("open identity slots cannot preserve specific identity text")
    text_slot_ids = {slot["id"] for slot in slots if slot.get("text") is not None}
    for region in analysis["textRegions"]:
        if region.get("action") == "open_slot":
            if region.get("slotId") not in text_slot_ids:
                raise ContractError("open text regions must name a text-capable slot")
    identity_target_ids = {
        target_id
        for binding in bindings.values()
        if isinstance(binding, Mapping) and binding.get("operation") == "replace_identity"
        for target_id in binding.get("targetIds", [])
    }
    if set(semantic_model["completeRedrawByTarget"]) != identity_target_ids:
        raise ContractError("complete-redraw evidence must map exactly to identity targets")
    prompt = _non_empty_text(formal_draft.get("promptTemplate"), "promptTemplate")
    for term in authoring["internalPromptTerms"]:
        if term.casefold() in prompt.casefold():
            raise ContractError("promptTemplate exposes internal backend terminology")
    placeholders = _PROMPT_SLOT.findall(prompt)
    if prompt.count("{{") != len(placeholders) or prompt.count("}}") != len(placeholders):
        raise ContractError("promptTemplate contains a malformed slot placeholder")
    placeholder_ids = [slot_id for slot_id, _ in placeholders]
    if len(placeholders) != len(slots) or sorted(placeholder_ids) != sorted(slot_ids):
        raise ContractError("promptTemplate must contain every slot exactly once")
    fallbacks = {slot_id: fallback for slot_id, fallback in placeholders}
    for slot in slots:
        expected_fallback = (
            slot["text"]["defaultValue"] if slot.get("text") is not None
            else slot_evidence[slot["id"]]["defaultValue"]
        )
        if fallbacks[slot["id"]] != expected_fallback:
            raise ContractError("promptTemplate fallback must equal the authored slot default")
    prompt_coverage = analysis["promptCoverage"]
    if not isinstance(prompt_coverage, Mapping) or prompt_coverage.get("allEditableContentCovered") is not True:
        raise ContractError("promptTemplate must cover every editable content item")
    covered_slots = prompt_coverage.get("slotIds")
    if not isinstance(covered_slots, list) or set(covered_slots) != {slot["id"] for slot in slots}:
        raise ContractError("promptTemplate coverage must name every slot")
    if not isinstance(prompt_coverage.get("freeEditableRegionIds"), list):
        raise ContractError("promptTemplate coverage must declare free-editable text regions")
    expected_free_regions = {
        region["regionId"] for region in analysis["textRegions"]
        if region.get("action") == "free_editable"
    }
    if set(prompt_coverage["freeEditableRegionIds"]) != expected_free_regions:
        raise ContractError("promptTemplate coverage differs from free-editable text regions")
    visual_contract = formal_draft["runtimeSemantics"]["visualContract"]
    visual_text = _flatten_text(visual_contract)
    for term in authoring["internalVisualContractTerms"]:
        if term.casefold() in visual_text.casefold():
            raise ContractError("visualContract exposes implementation terminology")
    for fact in analysis["templateValue"]["backendOnlyFacts"]:
        if fact not in visual_text or fact in prompt:
            raise ContractError("backend-only facts must appear only in runtime visual semantics")
    for slot_id, evidence in slot_evidence.items():
        for fact in evidence["openVisualFacts"]:
            if fact in visual_text:
                raise ContractError(f"visualContract locks back an open value from {slot_id}")
            if fact in title or fact in tags:
                raise ContractError(f"title or tags lock back an open value from {slot_id}")
    self_review = analysis["selfReview"]
    required_checks = set(authoring["selfReviewChecks"])
    if (
        not isinstance(self_review, Mapping)
        or set(self_review) != {
            "status", "reviewedDraftSha256", "checks", "issuesFound", "revisionsApplied"
        }
        or self_review.get("status") != "PASS"
        or self_review.get("reviewedDraftSha256") != sha256_json(formal_draft)
        or not isinstance(self_review.get("checks"), Mapping)
        or set(self_review["checks"]) != required_checks
        or any(value is not True for value in self_review["checks"].values())
        or not isinstance(self_review.get("issuesFound"), list)
        or self_review["issuesFound"]
        or not isinstance(self_review.get("revisionsApplied"), list)
    ):
        raise ContractError("a fresh passing self-review must bind the final formal draft")


def validate_formal_json(formal: Mapping[str, Any]) -> None:
    contract = _contract()
    gallery = contract["gallery"]
    if set(formal) - set(gallery["formalFields"]):
        forbidden = sorted(set(formal) - set(gallery["formalFields"]))
        raise ContractError(f"formal JSON contains forbidden fields: {forbidden}")
    if formal.get("inputSchema", {}).get("version") != gallery["inputSchemaVersion"]:
        raise ContractError("production inputSchema.version must be 2")
    if formal.get("runtimeSemantics", {}).get("version") != gallery["runtimeSemanticsVersion"]:
        raise ContractError("production runtimeSemantics.version must be 2")
    authoring = contract["authoring"]
    if not isinstance(formal.get("title"), str) or not 1 <= len(formal["title"]) <= authoring["titleMaxLength"]:
        raise ContractError("production title must be concise and user-readable")
    if not isinstance(formal.get("description"), str) or not 1 <= len(formal["description"]) <= authoring["descriptionMaxLength"]:
        raise ContractError("production description must contain 1–20 characters")
    tags = formal.get("metadata", {}).get("tags")
    if not isinstance(tags, list) or not authoring["tagMinimum"] <= len(tags) <= authoring["tagMaximum"]:
        raise ContractError("production tags must contain 5–8 items")
    if len(set(tags)) != len(tags) or any(
        not isinstance(tag, str) or not tag or len(tag) > authoring["tagMaxLength"] for tag in tags
    ):
        raise ContractError("production tags violate uniqueness or length limits")
    if not set(tags).intersection(authoring["majorTagValues"]):
        raise ContractError("production tags require an official major category")
    prompt = formal.get("promptTemplate")
    if not isinstance(prompt, str) or any(
        term.casefold() in prompt.casefold() for term in authoring["internalPromptTerms"]
    ):
        raise ContractError("production promptTemplate exposes internal terminology")
    slots = formal.get("inputSchema", {}).get("slots", [])
    slot_ids = [slot.get("id") for slot in slots if isinstance(slot, Mapping)]
    placeholders = _PROMPT_SLOT.findall(prompt)
    if len(placeholders) != len(slots) or sorted(slot_id for slot_id, _ in placeholders) != sorted(slot_ids):
        raise ContractError("production promptTemplate must contain every slot exactly once")
    defaults = authoring["slotDefaults"]
    for slot in slots:
        if slot.get("required") is not defaults["required"]:
            raise ContractError("production slots must remain optional")
        image = slot.get("image")
        if image is not None and (
            image.get("maxCount") != defaults["maxCount"]
            or image.get("minWidth") != defaults["minWidth"]
            or image.get("minHeight") != defaults["minHeight"]
            or set(image.get("sourceOptions", [])) != set(defaults["sourceOptions"])
        ):
            raise ContractError("production image slot profile is invalid")
        if image is not None and slot.get("text") is not None and slot.get("resolutionStrategy") != defaults["resolutionStrategy"]:
            raise ContractError("production composite slots require image_over_text")
    cover, reference = formal.get("cover"), formal.get("referenceImage")
    if cover != reference:
        raise ContractError("cover and referenceImage must be identical")
    if not isinstance(cover, str) or not cover.startswith(_contract()["oss"]["baseUrl"] + "/gallery/templates/"):
        raise ContractError("formal image URL must use the Memebuy production base")
    bindings = formal.get("runtimeSemantics", {}).get("inputBindings", {})
    for input_id, binding in bindings.items():
        if binding.get("operation") == "replace_identity" and binding.get("clothingOwnership") not in {
            "source", "template"
        }:
            raise ContractError(f"identity binding {input_id} requires clothingOwnership")

    schema_path = _SKILL_ROOT / "references/contracts/gallery-template.schema.json"
    schema_bytes = schema_path.read_bytes()
    if _sha_bytes(schema_bytes) != gallery["snapshotSha256"]:
        raise ContractError("vendored Gallery snapshot digest mismatch")
    schema = json.loads(schema_bytes)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(formal), key=lambda e: list(e.path))
    if errors:
        path = ".".join(str(part) for part in errors[0].path)
        raise ContractError(f"Gallery snapshot validation failed at {path}: {errors[0].message}")


def build_json_review_package(
    approved_image: Mapping[str, Any],
    analysis: Mapping[str, Any],
    formal_draft: Mapping[str, Any],
    registry_response: Mapping[str, Any],
    *,
    rule_version: str,
    revision: int,
) -> dict[str, Any]:
    validate_approved_image_envelope(approved_image)
    validate_authoring_contract(analysis, formal_draft, approved_image)
    if not isinstance(rule_version, str) or not rule_version or not isinstance(revision, int) or revision < 1:
        raise ContractError("JSON review binding is invalid")
    _validate_registry_response(registry_response)
    if registry_response.get("decision") not in {"NEW", "EXISTING_SAME_SOURCE"}:
        raise ContractError("key resolution pauses this item")
    if formal_draft.get("key") != registry_response.get("resolvedKey"):
        raise ContractError("formal key differs from registry resolution")
    approved_image_sha = approved_image["image"]["sha256"]
    formal_preview = project_formal_json(formal_draft, approved_image_sha)
    validate_formal_json(formal_preview)
    return {
        "state": "awaiting_json_approval",
        "approvedImage": deepcopy(approved_image),
        "frozenCandidateKey": registry_response["resolvedKey"],
        "registry": deepcopy(registry_response),
        "assetState": {
            "status": "planned_not_uploaded",
            "previewUri": approved_image["image"]["uri"],
            "plannedImmutableUrl": formal_preview["cover"],
        },
        "analysisSummary": {
            "visualMechanism": analysis["visualMechanism"],
            "counts": deepcopy(analysis["counts"]),
            "warnings": deepcopy(analysis["warnings"]),
        },
        "templateValue": deepcopy(analysis["templateValue"]),
        "titleEvidence": deepcopy(analysis["titleEvidence"]),
        "tagEvidence": deepcopy(analysis["tagEvidence"]),
        "slotCards": deepcopy(analysis["slotEvidence"]),
        "copy": {
            "title": formal_preview["title"],
            "description": formal_preview["description"],
            "tags": deepcopy(formal_preview["metadata"]["tags"]),
        },
        "slots": deepcopy(formal_preview["inputSchema"]["slots"]),
        "promptTemplate": formal_preview["promptTemplate"],
        "warnings": deepcopy(analysis["warnings"]),
        "promptCoverage": deepcopy(analysis["promptCoverage"]),
        "runtimeSummary": {
            "targetInstances": deepcopy(formal_preview["runtimeSemantics"]["targetInstances"]),
            "inputBindings": deepcopy(formal_preview["runtimeSemantics"]["inputBindings"]),
            "visualContract": deepcopy(formal_preview["runtimeSemantics"]["visualContract"]),
        },
        "selfReview": deepcopy(analysis["selfReview"]),
        "formalPreview": formal_preview,
        "objectSha256": sha256_json(formal_preview),
        "approvedImageSha256": approved_image_sha,
        "ruleVersion": rule_version,
        "revision": revision,
    }


def _validate_registry_response(response: Mapping[str, Any]) -> None:
    required = {"registryRevision", "decision", "resolvedKey", "matchedBy", "evidence"}
    if set(response) != required:
        raise ContractError("invalid key-registry response fields")
    if response["decision"] not in _contract()["keyDecisions"]:
        raise ContractError("invalid key-registry decision")
    if response["registryRevision"] is not None and not isinstance(response["registryRevision"], str):
        raise ContractError("invalid registry revision")
    resolved = response["resolvedKey"]
    if resolved is not None:
        _validate_key(resolved)
    if not isinstance(response["matchedBy"], list) or not all(isinstance(x, str) for x in response["matchedBy"]):
        raise ContractError("invalid registry matchedBy evidence")
    if len(set(response["matchedBy"])) != len(response["matchedBy"]):
        raise ContractError("registry matchedBy must be unique")
    if not isinstance(response["evidence"], list) or not all(isinstance(x, Mapping) for x in response["evidence"]):
        raise ContractError("invalid registry evidence")
    if response["decision"] in {"NEW", "EXISTING_SAME_SOURCE"} and resolved is None:
        raise ContractError("successful key decision requires resolvedKey")


def _validate_json_approval(
    formal: Mapping[str, Any], approved_image_sha256: str, approval: Mapping[str, Any],
    *, rule_version: str, revision: int,
) -> None:
    if set(approval) != {
        "decision", "objectSha256", "approvedImageSha256", "reviewerRef", "decidedAt",
        "ruleVersion", "revision",
    }:
        raise ContractError("JSON approval fields differ from the frozen schema")
    _validate_human_review_facts(approval)
    if (
        approval.get("decision") != "APPROVED"
        or approval.get("objectSha256") != sha256_json(formal)
        or approval.get("approvedImageSha256") != approved_image_sha256
        or approval.get("ruleVersion") != rule_version
        or approval.get("revision") != revision
    ):
        raise ContractError("JSON approval is missing or stale")


def _validate_human_review_facts(value: Mapping[str, Any]) -> None:
    _non_empty_text(value.get("reviewerRef"), "reviewerRef")
    decided_at = _non_empty_text(value.get("decidedAt"), "decidedAt")
    try:
        datetime.fromisoformat(decided_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError("decidedAt must be an ISO-8601 timestamp") from exc


def project_formal_json(formal_draft: Mapping[str, Any], approved_image_sha256: str) -> dict[str, Any]:
    """Create the exact human-reviewable formal object before any OSS mutation."""

    if "cover" in formal_draft or "referenceImage" in formal_draft:
        raise ContractError("formal draft must not pre-populate OSS URLs")
    if not isinstance(approved_image_sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", approved_image_sha256):
        raise ContractError("approved image SHA-256 is invalid")
    key = _validate_key(formal_draft.get("key"))
    oss = _contract()["oss"]
    object_key = oss["objectKeyTemplate"].format(
        key=key, approvedImageSha256=approved_image_sha256
    )
    url = f"{oss['baseUrl']}/{object_key}"
    formal = deepcopy(dict(formal_draft))
    formal["cover"] = url
    formal["referenceImage"] = url
    return formal


def oss_intent(key: str, png_bytes: bytes) -> dict[str, Any]:
    _validate_key(key)
    if not png_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ContractError("OSS input must be the exact approved PNG bytes")
    digest = _sha_bytes(png_bytes)
    contract = _contract()["oss"]
    object_key = contract["objectKeyTemplate"].format(key=key, approvedImageSha256=digest)
    public_url = f"{contract['baseUrl']}/{object_key}"
    parsed = urlparse(public_url)
    if parsed.scheme != "https" or parsed.netloc != "assets.memebuy.cn" or parsed.query or parsed.fragment:
        raise ContractError("Memebuy public URL policy mismatch")
    request_identity = sha256_json({
        "objectKey": object_key,
        "sha256": digest,
        "byteLength": len(png_bytes),
        "remoteIdentity": object_key,
    })
    return {
        "key": key,
        "approvedImageSha256": digest,
        "objectDigest": digest,
        "byteLength": len(png_bytes),
        "objectKey": object_key,
        "remoteIdentity": object_key,
        "requestIdentity": request_identity,
        "publicHttpsUrl": public_url,
    }


def validate_oss_receipt(receipt: Mapping[str, Any]) -> None:
    schema = json.loads((
        _SKILL_ROOT / "references/contracts/oss-receipt.schema.json"
    ).read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(receipt),
        key=lambda error: list(error.path),
    )
    if errors:
        raise ContractError("OSS receipt invalid: " + errors[0].message)
    if receipt["objectDigest"] != receipt["approvedImageSha256"]:
        raise ContractError("OSS object digest differs from the Approved Image SHA")
    if receipt["providerReceiptDigest"] != sha256_json(receipt["providerReceipt"]):
        raise ContractError("OSS provider receipt digest mismatch")


def finalize_approved_json(
    formal_draft: Mapping[str, Any],
    approval: Mapping[str, Any],
    approved_png_bytes: bytes,
    adapter: OssAdapter,
    *,
    rule_version: str,
    revision: int,
    uploaded_at: str,
    existing_receipt: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Perform the first remote mutation only after valid human JSON approval."""

    key = _validate_key(formal_draft.get("key"))
    _non_empty_text(uploaded_at, "uploadedAt")
    intent = oss_intent(key, approved_png_bytes)
    formal = project_formal_json(formal_draft, intent["approvedImageSha256"])
    validate_formal_json(formal)
    _validate_json_approval(
        formal, intent["approvedImageSha256"], approval,
        rule_version=rule_version, revision=revision,
    )

    if existing_receipt is not None:
        validate_oss_receipt(existing_receipt)
        receipt_identity = {
            name: existing_receipt.get(name)
            for name in (
                "key", "approvedImageSha256", "objectDigest", "byteLength", "objectKey",
                "remoteIdentity", "requestIdentity", "publicHttpsUrl",
            )
        }
        provider_receipt = existing_receipt.get("providerReceipt")
        if (
            receipt_identity != intent
            or not isinstance(provider_receipt, Mapping)
            or existing_receipt.get("providerReceiptDigest") != sha256_json(provider_receipt)
            or not isinstance(existing_receipt.get("uploadedAt"), str)
            or not existing_receipt["uploadedAt"]
        ):
            raise ContractError("existing OSS receipt does not match the approved upload intent")
        return formal, deepcopy(dict(existing_receipt))

    remote = adapter.head(intent["objectKey"])
    expected_remote = {
        "objectKey": intent["objectKey"],
        "sha256": intent["approvedImageSha256"],
        "byteLength": intent["byteLength"],
        "remoteIdentity": intent["remoteIdentity"],
        "requestIdentity": intent["requestIdentity"],
    }
    if remote is not None:
        if not isinstance(remote, Mapping):
            raise ContractError("OSS head response must be an object")
        actual = {name: remote.get(name) for name in expected_remote}
        if actual != expected_remote:
            raise ContractError("existing OSS object conflicts; overwrite prohibited")
        provider_receipt = {"reused": True, **actual}
    else:
        raw_put_response = adapter.put_create_once(
            intent["objectKey"],
            approved_png_bytes,
            {
                "sha256": intent["approvedImageSha256"],
                "byteLength": intent["byteLength"],
                "remoteIdentity": intent["remoteIdentity"],
                "requestIdentity": intent["requestIdentity"],
            },
        )
        if not isinstance(raw_put_response, Mapping):
            raise ContractError("OSS create response must be an object")
        put_response = dict(raw_put_response)
        if {name: put_response.get(name) for name in expected_remote} != expected_remote:
            raise ContractError("OSS create response differs from the approved upload intent")
        reconciled = adapter.head(intent["objectKey"])
        if not isinstance(reconciled, Mapping) or {
            name: reconciled.get(name) for name in expected_remote
        } != expected_remote:
            raise ContractError("OSS object reconciliation differs from the approved upload intent")
        provider_receipt = {
            "created": True,
            **expected_remote,
            **({"providerRequestId": put_response["providerRequestId"]}
               if isinstance(put_response.get("providerRequestId"), str) else {}),
        }

    receipt = {
        **intent,
        "providerReceipt": provider_receipt,
        "providerReceiptDigest": sha256_json(provider_receipt),
        "uploadedAt": uploaded_at,
    }
    validate_oss_receipt(receipt)
    return formal, receipt


def write_formal_json(delivery_root: Path, formal: Mapping[str, Any]) -> Path:
    """Atomically create one bare formal JSON, or reuse byte-identical content."""

    validate_formal_json(formal)
    key = _validate_key(formal.get("key"))
    raw_root = Path(delivery_root)
    if raw_root.exists() and raw_root.is_symlink():
        raise ContractError("delivery root must not be a symlink")
    root = raw_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    item_dir = root / key
    if item_dir.exists() and (item_dir.is_symlink() or not item_dir.is_dir()):
        raise ContractError("formal item directory is unsafe")
    item_dir.mkdir(exist_ok=True)
    if item_dir.resolve().parent != root:
        raise ContractError("formal path escapes delivery root")
    target = item_dir / f"{key}.json"
    unexpected = [entry.name for entry in item_dir.iterdir() if entry != target]
    if unexpected:
        raise ContractError(f"formal item directory contains extra files: {sorted(unexpected)}")
    encoded = (json.dumps(formal, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if target.exists():
        if target.is_symlink() or target.read_bytes() != encoded:
            raise ContractError("formal JSON content conflict")
        return target
    fd, temporary_name = tempfile.mkstemp(prefix=f".{key}.", suffix=".tmp", dir=item_dir)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        if target.exists():
            raise ContractError("formal JSON appeared during write")
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target


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
    """Keep contract and adapter failures local to each batch item."""

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
                "stage": "json_compiler",
                "result": process_item(item),
            })
        except Exception as exc:  # boundary converts adapter failures into item state
            error_code, summary = _safe_batch_failure(exc)
            results.append({
                "itemId": item_id,
                "state": "paused",
                "revision": item.get("revision"),
                "stage": "json_compiler",
                "errorCode": error_code,
                "evidence": summary,
                "recoveryAction": "resume only this item after correcting the reported stage",
            })
    return results
