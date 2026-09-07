#!/usr/bin/env python3
"""Deterministic batch, review, and workbench-registration helper."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "2.0.0"
PLAN_CONTRACT_VERSION = "2.0.0"
SUPPORTED_PLAN_CONTRACT_VERSIONS = {PLAN_CONTRACT_VERSION}
DECISIONS = {"approved", "good_case", "revise", "hold", "rejected"}
PET_ROUTES = {"real_pet_interaction", "partial_echo", "print_led"}
TOPIC_ROUTES = {
    "pet_relationship", "pet_product", "standalone_print", "couple", "family",
    "fandom_music", "character_anime", "occasion", "custom",
}
GENERATION_MODES = {"one_pass"}
VARIATION_DIMENSIONS = {"scene_topology", "subject_placement", "human_action", "camera_geometry", "set_design"}
STYLE_FINGERPRINT_FIELDS = (
    "whitePoint",
    "dominantColorArea",
    "midtoneSeparation",
    "shadowHue",
    "highlightRollOff",
    "textureDistribution",
    "humanState",
)
PHOTOGRAPHIC_TRUTH_FIELDS = (
    "ordinaryActivity",
    "subjectOwnIntent",
    "secondarySubjectOwnIntent",
    "momentBefore",
    "momentAfter",
)
LIVELINESS_GATE_FIELDS = ("photoBeforeProduct", "livedMoment", "subjectNatural", "secondarySubjectNatural")
COLOR_TEXTURE_GATE_FIELDS = ("whitePointReadable", "midtoneSeparated", "shadowHuePresent", "materialsDistinct")
MAX_GENERATION_PROMPT_CHARS = 1600
CANDIDATE_FIELDS = (
    "candidateId",
    "templateKey",
    "templateTitle",
    "templateDataPath",
    "templatePreviewUrl",
    "topicProfile",
    "productCategory",
    "styleCardId",
    "planPath",
    "imagePath",
)
BOUND_CANDIDATE_FIELDS = ("generationSourcePath", "templateReferencePath", "styleReferencePath")


class WorkflowError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WorkflowError(f"文件不存在：{path}") from exc
    except json.JSONDecodeError as exc:
        raise WorkflowError(f"JSON 无法解析：{path}: {exc}") from exc


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def png_size(path: Path) -> tuple[int, int] | None:
    with path.open("rb") as stream:
        header = stream.read(24)
    if len(header) >= 24 and header[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", header[16:24])
    return None


def jpeg_size(path: Path) -> tuple[int, int] | None:
    with path.open("rb") as stream:
        if stream.read(2) != b"\xff\xd8":
            return None
        while True:
            byte = stream.read(1)
            if not byte:
                return None
            if byte != b"\xff":
                continue
            while byte == b"\xff":
                byte = stream.read(1)
            marker = byte[0]
            if marker in {0xD8, 0xD9}:
                continue
            length_bytes = stream.read(2)
            if len(length_bytes) != 2:
                return None
            length = struct.unpack(">H", length_bytes)[0]
            if length < 2:
                return None
            if marker in {
                0xC0,
                0xC1,
                0xC2,
                0xC3,
                0xC5,
                0xC6,
                0xC7,
                0xC9,
                0xCA,
                0xCB,
                0xCD,
                0xCE,
                0xCF,
            }:
                payload = stream.read(5)
                if len(payload) != 5:
                    return None
                height, width = struct.unpack(">HH", payload[1:5])
                return width, height
            stream.seek(length - 2, 1)


def image_size(path: Path) -> tuple[int, int]:
    suffix = path.suffix.lower()
    size = png_size(path) if suffix == ".png" else jpeg_size(path) if suffix in {".jpg", ".jpeg"} else None
    if not size:
        raise WorkflowError(f"只支持可解析的 PNG/JPEG 图片：{path}")
    return size


def require_file(raw_path: str, label: str) -> Path:
    path = Path(raw_path).expanduser().resolve()
    if not path.is_file():
        raise WorkflowError(f"{label}不存在：{path}")
    return path


def require_directory(raw_path: str, label: str) -> Path:
    path = Path(raw_path).expanduser().resolve()
    if not path.is_dir():
        raise WorkflowError(f"{label}不存在：{path}")
    return path


def require_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkflowError(f"{label}必须是非空文本")
    return value.strip()


def require_true_fields(value: Any, fields: tuple[str, ...], label: str) -> None:
    if not isinstance(value, dict):
        raise WorkflowError(f"{label}必须是对象")
    for field in fields:
        if value.get(field) is not True:
            raise WorkflowError(f"{label}.{field} 必须为 true")


def require_text_fields(value: Any, fields: tuple[str, ...], label: str) -> None:
    if not isinstance(value, dict):
        raise WorkflowError(f"{label}必须是对象")
    for field in fields:
        require_text(value.get(field), f"{label}.{field}")


def validate_v2_plan(plan: dict[str, Any], require_visual_review: bool) -> str:
    require_text_fields(plan.get("styleFingerprint"), STYLE_FINGERPRINT_FIELDS, "styleFingerprint")

    truth = plan.get("photographicTruth")
    require_text_fields(truth, PHOTOGRAPHIC_TRUTH_FIELDS, "photographicTruth")
    if truth.get("productRemovedPhotoStillWorks") is not True:
        raise WorkflowError("photographicTruth.productRemovedPhotoStillWorks 必须为 true")
    if truth.get("cameraIgnored") is not True:
        raise WorkflowError("photographicTruth.cameraIgnored 必须为 true")

    strategy = plan.get("generationStrategy")
    if not isinstance(strategy, dict):
        raise WorkflowError("单图计划缺少 generationStrategy")
    mode = strategy.get("mode")
    if mode not in GENERATION_MODES:
        raise WorkflowError(f"generationStrategy.mode 必须是：{', '.join(sorted(GENERATION_MODES))}")
    prompt = require_text(strategy.get("generationPrompt"), "generationStrategy.generationPrompt")
    if len(prompt) > MAX_GENERATION_PROMPT_CHARS:
        raise WorkflowError(f"generationPrompt 超过 {MAX_GENERATION_PROMPT_CHARS} 字符，容易造成过度编排")

    topic_route = plan.get("topicRoute")
    if topic_route not in TOPIC_ROUTES:
        raise WorkflowError(f"topicRoute 必须是：{', '.join(sorted(TOPIC_ROUTES))}")
    product = plan.get("productDesign")
    require_text_fields(
        product,
        ("carrier", "carrierColor", "printSide", "backgroundTreatment", "relativeScale", "materialRendering", "visibilityGuard"),
        "productDesign",
    )
    scene = plan.get("sceneDirection")
    require_text_fields(scene, ("actorStructure", "livedEvent", "mainAction", "semanticEcho", "cameraDistance"), "sceneDirection")
    if scene.get("singleModelGender") not in {None, "male", "female", "not_applicable"}:
        raise WorkflowError("sceneDirection.singleModelGender 必须是 male、female、not_applicable 或省略")

    bindings = plan.get("referenceBindings")
    if not isinstance(bindings, dict):
        raise WorkflowError("单图计划缺少 referenceBindings")
    require_file(require_text(bindings.get("templateReferencePath"), "referenceBindings.templateReferencePath"), "模板参考图")
    require_file(require_text(bindings.get("styleReferencePath"), "referenceBindings.styleReferencePath"), "风格参考图")

    review = plan.get("visualReview")
    if require_visual_review or review is not None:
        if not isinstance(review, dict):
            raise WorkflowError("2.0 候选登记前必须填写 visualReview")
        if review.get("result") != "pass_for_user_review":
            raise WorkflowError("visualReview.result 必须为 pass_for_user_review")
        require_text(review.get("firstImpression"), "visualReview.firstImpression")
        evidence = review.get("observedStyleEvidence")
        if not isinstance(evidence, list) or len([item for item in evidence if isinstance(item, str) and item.strip()]) < 3:
            raise WorkflowError("visualReview.observedStyleEvidence 至少需要3项可见证据")
        require_true_fields(review.get("livelinessGate"), LIVELINESS_GATE_FIELDS, "visualReview.livelinessGate")
        require_true_fields(review.get("colorTextureGate"), COLOR_TEXTURE_GATE_FIELDS, "visualReview.colorTextureGate")
    return mode


def validate_plan_contract(
    path: Path,
    expected_candidate_id: str | None = None,
    expected_template_key: str | None = None,
    require_visual_review: bool = False,
) -> dict[str, Any]:
    plan = read_json(path)
    if not isinstance(plan, dict):
        raise WorkflowError(f"单图计划必须是 JSON 对象：{path}")
    plan_contract_version = plan.get("planContractVersion")
    if plan_contract_version not in SUPPORTED_PLAN_CONTRACT_VERSIONS:
        raise WorkflowError(
            f"单图计划 planContractVersion 必须是：{', '.join(sorted(SUPPORTED_PLAN_CONTRACT_VERSIONS))}：{path}"
        )
    candidate_id = require_text(plan.get("candidateId"), "candidateId")
    template_key = require_text(plan.get("templateKey"), "templateKey")
    if expected_candidate_id and candidate_id != expected_candidate_id:
        raise WorkflowError(f"计划 candidateId 与候选不一致：{candidate_id} != {expected_candidate_id}")
    if expected_template_key and template_key != expected_template_key:
        raise WorkflowError(f"计划 templateKey 与候选不一致：{template_key} != {expected_template_key}")

    style = plan.get("styleTranslation")
    if not isinstance(style, dict):
        raise WorkflowError("单图计划缺少 styleTranslation")
    invariants = style.get("styleInvariants")
    if not isinstance(invariants, list) or len([item for item in invariants if isinstance(item, str) and item.strip()]) < 3:
        raise WorkflowError("styleTranslation.styleInvariants 至少需要3项摄影DNA")
    variations = style.get("deliberateVariations")
    if not isinstance(variations, list):
        raise WorkflowError("styleTranslation.deliberateVariations 必须是数组")
    dimensions: set[str] = set()
    for item in variations:
        if not isinstance(item, dict):
            continue
        dimension = item.get("dimension")
        change = item.get("change")
        if dimension in VARIATION_DIMENSIONS and isinstance(change, str) and change.strip():
            dimensions.add(dimension)
    if len(dimensions) < 3:
        raise WorkflowError("deliberateVariations 至少需要3个不同维度的具体改写")

    distance = plan.get("referenceDistanceAudit")
    if not isinstance(distance, dict):
        raise WorkflowError("单图计划缺少 referenceDistanceAudit")
    for field in ("sceneTopologyChanged", "subjectSilhouetteChanged", "mainActionChanged"):
        if distance.get(field) is not True:
            raise WorkflowError(f"referenceDistanceAudit.{field} 必须为 true")
    require_text(distance.get("retainedSimilaritySource"), "referenceDistanceAudit.retainedSimilaritySource")

    topic_route = plan.get("topicRoute")
    pet = plan.get("petDirection")
    route = None
    if topic_route in {"pet_relationship", "pet_product"}:
        if not isinstance(pet, dict):
            raise WorkflowError("宠物路线的单图计划缺少 petDirection")
        route = pet.get("route")
        if route not in PET_ROUTES:
            raise WorkflowError(f"petDirection.route 必须是：{', '.join(sorted(PET_ROUTES))}")
        if not isinstance(pet.get("petVisible"), bool):
            raise WorkflowError("petDirection.petVisible 必须是布尔值")
        if route == "real_pet_interaction":
            if pet.get("petVisible") is not True:
                raise WorkflowError("real_pet_interaction 路线要求 petVisible=true")
            for field in (
                "interactionTrigger",
                "petMotivation",
                "petAction",
                "humanOrProductResponse",
                "capturedBeat",
                "relationshipCue",
                "naturalityCheck",
            ):
                require_text(pet.get(field), f"petDirection.{field}")
    elif pet is not None:
        raise WorkflowError("非宠物 topicRoute 不应携带 petDirection")
    generation_mode = validate_v2_plan(plan, require_visual_review)
    return {
        "status": "valid",
        "planPath": str(path),
        "candidateId": candidate_id,
        "templateKey": template_key,
        "variationDimensions": sorted(dimensions),
        "petRoute": route,
        "planContractVersion": plan_contract_version,
        "generationMode": generation_mode,
    }


def batch_paths(batch_dir: str) -> tuple[Path, Path, Path]:
    root = Path(batch_dir).expanduser().resolve()
    return root, root / "batch.json", root / "decisions.json"


def load_batch(batch_dir: str) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    root, batch_path, decisions_path = batch_paths(batch_dir)
    batch = read_json(batch_path)
    decisions = read_json(decisions_path)
    if batch.get("artifactType") != "template_atmosphere_image_batch":
        raise WorkflowError(f"批次合同错误：{batch_path}")
    if not isinstance(batch.get("candidates"), list):
        raise WorkflowError(f"批次 candidates 必须是数组：{batch_path}")
    return root, batch, decisions


def command_init(args: argparse.Namespace) -> dict[str, Any]:
    root, batch_path, decisions_path = batch_paths(args.batch_dir)
    if batch_path.exists() or decisions_path.exists():
        raise WorkflowError(f"批次已经存在，拒绝覆盖：{root}")
    for name in ("plans", "candidates", "references", "receipts", "reports"):
        (root / name).mkdir(parents=True, exist_ok=True)
    created_at = args.created_at or now_iso()
    batch = {
        "artifactType": "template_atmosphere_image_batch",
        "schemaVersion": SCHEMA_VERSION,
        "batchId": args.batch_id,
        "topicProfile": args.topic_profile,
        "createdAt": created_at,
        "updatedAt": created_at,
        "candidates": [],
    }
    decisions = {
        "artifactType": "template_atmosphere_image_decisions",
        "schemaVersion": SCHEMA_VERSION,
        "batchId": args.batch_id,
        "updatedAt": created_at,
        "current": {},
        "history": [],
    }
    atomic_json(batch_path, batch)
    atomic_json(decisions_path, decisions)
    return {"status": "initialized", "batchDir": str(root), "batchId": args.batch_id}


def validate_candidate(value: dict[str, Any]) -> dict[str, Any]:
    missing = [field for field in CANDIDATE_FIELDS if not isinstance(value.get(field), str) or not value[field].strip()]
    if missing:
        raise WorkflowError(f"候选缺少字段：{', '.join(missing)}")
    image_path = require_file(value["imagePath"], "候选图片")
    plan_path = require_file(value["planPath"], "候选计划")
    template_path = require_file(value["templateDataPath"], "正式模板数据")
    plan_result = validate_plan_contract(
        plan_path,
        value["candidateId"].strip(),
        value["templateKey"].strip(),
        require_visual_review=True,
    )
    plan = read_json(plan_path)
    bound_paths: dict[str, Path] = {}
    if plan_result["planContractVersion"] == PLAN_CONTRACT_VERSION:
        missing_bound = [
            field for field in BOUND_CANDIDATE_FIELDS if not isinstance(value.get(field), str) or not value[field].strip()
        ]
        if missing_bound:
            raise WorkflowError(f"2.0 候选缺少绑定字段：{', '.join(missing_bound)}")
        for field in BOUND_CANDIDATE_FIELDS:
            bound_paths[field] = require_file(value[field], field)
        if sha256(bound_paths["generationSourcePath"]) != sha256(image_path):
            raise WorkflowError("generationSourcePath 与 imagePath 内容哈希不一致，疑似候选错绑")
        bindings = plan["referenceBindings"]
        for field in ("templateReferencePath", "styleReferencePath"):
            planned = Path(bindings[field]).expanduser().resolve()
            if bound_paths[field] != planned:
                raise WorkflowError(f"{field} 与计划 referenceBindings 不一致")
    width, height = image_size(image_path)
    if width * 4 != height * 3:
        raise WorkflowError(f"候选图片必须严格为 3:4，当前为 {width}x{height}：{image_path}")
    normalized = {field: value[field].strip() for field in CANDIDATE_FIELDS}
    normalized.update({field: str(path) for field, path in bound_paths.items()})
    if isinstance(value.get("sourceId"), str) and value["sourceId"].strip():
        normalized["sourceId"] = value["sourceId"].strip()
    normalized.update(
        {
            "templateDataPath": str(template_path),
            "planPath": str(plan_path),
            "imagePath": str(image_path),
            "imageWidth": width,
            "imageHeight": height,
            "imageSize": f"{width}x{height}",
            "sha256": sha256(image_path),
            "decision": "pending",
            "registeredAt": now_iso(),
            "planContractVersion": plan_result["planContractVersion"],
            "generationMode": plan_result["generationMode"],
        }
    )
    return normalized


def template_urls(data_path: Path | None, preview_url: str | None) -> set[str]:
    urls = {preview_url.strip()} if isinstance(preview_url, str) and preview_url.strip() else set()
    if data_path and data_path.is_file():
        value = read_json(data_path)
        if isinstance(value, dict):
            for field in ("cover", "referenceImage", "templatePreviewUrl", "sourceTemplatePreviewUrl"):
                raw = value.get(field)
                if isinstance(raw, str) and raw.strip():
                    urls.add(raw.strip())
    return urls


def approval_records(registry_path: Path) -> list[tuple[str, dict[str, Any]]]:
    registry = read_json(registry_path)
    packages = registry.get("approvalPackages") if isinstance(registry, dict) else None
    if not isinstance(packages, list):
        raise WorkflowError(f"工作台注册表 approvalPackages 必须是数组：{registry_path}")
    records: list[tuple[str, dict[str, Any]]] = []
    for package in packages:
        if not isinstance(package, dict):
            continue
        index_path_raw = package.get("indexPath")
        if not isinstance(index_path_raw, str) or not index_path_raw.strip():
            continue
        index_path = Path(index_path_raw).expanduser().resolve()
        index = read_json(index_path)
        for record in index.get("records", []) if isinstance(index, dict) else []:
            if isinstance(record, dict):
                records.append((str(index_path), record))
    return records


def command_check_template(args: argparse.Namespace) -> dict[str, Any]:
    registry_path = require_file(args.registry, "工作台注册表")
    template_path = require_file(args.template_data_path, "正式模板数据") if args.template_data_path else None
    current_urls = template_urls(template_path, args.template_preview_url)
    current_data_path = str(template_path) if template_path else None
    matches: list[dict[str, Any]] = []
    for index_path, record in approval_records(registry_path):
        reasons: list[str] = []
        if record.get("templateKey") == args.template_key:
            reasons.append("template_key")
        approved_data_raw = record.get("sourceTemplateDataPath")
        approved_data_path = Path(approved_data_raw).expanduser().resolve() if isinstance(approved_data_raw, str) and approved_data_raw.strip() else None
        if current_data_path and approved_data_path and str(approved_data_path) == current_data_path:
            reasons.append("template_data_path")
        approved_urls = template_urls(approved_data_path, record.get("sourceTemplatePreviewUrl"))
        if current_urls.intersection(approved_urls):
            reasons.append("template_preview_identity")
        if reasons:
            matches.append(
                {
                    "source": "approval_registry",
                    "indexPath": index_path,
                    "candidateId": record.get("candidateId"),
                    "templateKey": record.get("templateKey"),
                    "reasons": sorted(set(reasons)),
                    "atmosphereImage": record.get("atmosphereImage"),
                }
            )

    if args.material_index:
        material_path = require_file(args.material_index, "工作台素材索引")
        material = read_json(material_path)
        records = material.get("records") if isinstance(material, dict) else None
        if not isinstance(records, list):
            raise WorkflowError(f"工作台素材索引 records 必须是数组：{material_path}")
        for record in records:
            if not isinstance(record, dict) or record.get("key") != args.template_key:
                continue
            paths = [item for item in record.get("atmosphereImagePaths", []) if isinstance(item, str) and item.strip()]
            if paths:
                matches.append(
                    {
                        "source": "material_index",
                        "templateKey": args.template_key,
                        "reasons": ["existing_atmosphere_paths"],
                        "atmosphereImagePaths": paths,
                    }
                )
    if args.batch_root:
        batch_root = require_directory(args.batch_root, "生产批次根目录")
        for batch_path in batch_root.rglob("batch.json"):
            try:
                batch = read_json(batch_path)
            except WorkflowError:
                continue
            if not isinstance(batch, dict) or batch.get("artifactType") != "template_atmosphere_image_batch":
                continue
            for candidate in batch.get("candidates", []):
                if not isinstance(candidate, dict) or candidate.get("decision", "pending") not in {"pending", "approved", "good_case", "hold"}:
                    continue
                reasons: list[str] = []
                if candidate.get("templateKey") == args.template_key:
                    reasons.append("prior_batch_template_key")
                candidate_data_raw = candidate.get("templateDataPath")
                candidate_data_path = Path(candidate_data_raw).expanduser().resolve() if isinstance(candidate_data_raw, str) and candidate_data_raw.strip() else None
                candidate_urls = template_urls(candidate_data_path, candidate.get("templatePreviewUrl"))
                if current_urls.intersection(candidate_urls):
                    reasons.append("prior_batch_template_preview_identity")
                if reasons:
                    matches.append(
                        {
                            "source": "production_batch",
                            "batchPath": str(batch_path),
                            "batchId": batch.get("batchId"),
                            "candidateId": candidate.get("candidateId"),
                            "templateKey": candidate.get("templateKey"),
                            "decision": candidate.get("decision", "pending"),
                            "reasons": sorted(set(reasons)),
                        }
                    )
    return {
        "status": "linked" if matches else "available",
        "eligible": not matches,
        "templateKey": args.template_key,
        "matches": matches,
    }


def command_validate_plan(args: argparse.Namespace) -> dict[str, Any]:
    return validate_plan_contract(require_file(args.plan, "单图计划"))


def command_add_candidate(args: argparse.Namespace) -> dict[str, Any]:
    root, batch, _ = load_batch(args.batch_dir)
    value = read_json(Path(args.candidate_json).expanduser().resolve())
    if not isinstance(value, dict):
        raise WorkflowError("候选描述必须是 JSON 对象")
    candidate = validate_candidate(value)
    if candidate["topicProfile"] != batch["topicProfile"]:
        raise WorkflowError("候选 topicProfile 与批次不一致")
    if any(item.get("candidateId") == candidate["candidateId"] for item in batch["candidates"]):
        raise WorkflowError(f"候选ID重复：{candidate['candidateId']}")
    batch["candidates"].append(candidate)
    batch["updatedAt"] = now_iso()
    atomic_json(root / "batch.json", batch)
    return {
        "status": "registered",
        "candidateId": candidate["candidateId"],
        "imageSize": candidate["imageSize"],
        "sha256": candidate["sha256"],
    }


def command_decide(args: argparse.Namespace) -> dict[str, Any]:
    root, batch, decisions = load_batch(args.batch_dir)
    candidate = next((item for item in batch["candidates"] if item.get("candidateId") == args.candidate_id), None)
    if not candidate:
        raise WorkflowError(f"找不到候选：{args.candidate_id}")
    decided_at = args.decided_at or now_iso()
    record = {
        "candidateId": args.candidate_id,
        "decision": args.decision,
        "reason": args.reason,
        "decidedAt": decided_at,
    }
    candidate["decision"] = args.decision
    candidate["decisionReason"] = args.reason
    candidate["decidedAt"] = decided_at
    decisions.setdefault("current", {})[args.candidate_id] = record
    decisions.setdefault("history", []).append(record)
    decisions["updatedAt"] = decided_at
    batch["updatedAt"] = decided_at
    atomic_json(root / "batch.json", batch)
    atomic_json(root / "decisions.json", decisions)
    return {"status": "decided", **record}


def summarize(batch: dict[str, Any]) -> dict[str, int]:
    counts = {"pending": 0, "approved": 0, "good_case": 0, "revise": 0, "hold": 0, "rejected": 0}
    for candidate in batch["candidates"]:
        state = candidate.get("decision", "pending")
        counts[state] = counts.get(state, 0) + 1
    return counts


def command_status(args: argparse.Namespace) -> dict[str, Any]:
    root, batch, decisions = load_batch(args.batch_dir)
    return {
        "status": "ok",
        "batchDir": str(root),
        "batchId": batch["batchId"],
        "topicProfile": batch["topicProfile"],
        "counts": summarize(batch),
        "candidates": [
            {
                "candidateId": item["candidateId"],
                "templateKey": item["templateKey"],
                "productCategory": item["productCategory"],
                "styleCardId": item["styleCardId"],
                "decision": item.get("decision", "pending"),
            }
            for item in batch["candidates"]
        ],
        "decisionHistoryCount": len(decisions.get("history", [])),
        "finalization": batch.get("finalization"),
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    subparsers = root.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="初始化独立生产批次")
    init.add_argument("--batch-dir", required=True)
    init.add_argument("--batch-id", required=True)
    init.add_argument("--topic-profile", required=True)
    init.add_argument("--created-at")
    init.set_defaults(handler=command_init)

    check = subparsers.add_parser("check-template", help="生成前检查模板是否已有氛围图关联")
    check.add_argument("--template-key", required=True)
    check.add_argument("--template-data-path")
    check.add_argument("--template-preview-url")
    check.add_argument("--registry", required=True)
    check.add_argument("--material-index")
    check.add_argument("--batch-root")
    check.set_defaults(handler=command_check_template)

    plan = subparsers.add_parser("validate-plan", help="生成前校验风格变奏与宠物关系计划")
    plan.add_argument("--plan", required=True)
    plan.set_defaults(handler=command_validate_plan)

    add = subparsers.add_parser("add-candidate", help="登记通过基础门禁的候选")
    add.add_argument("--batch-dir", required=True)
    add.add_argument("--candidate-json", required=True)
    add.set_defaults(handler=command_add_candidate)

    decide = subparsers.add_parser("decide", help="记录稳定候选ID的人工决策")
    decide.add_argument("--batch-dir", required=True)
    decide.add_argument("--candidate-id", required=True)
    decide.add_argument("--decision", required=True, choices=sorted(DECISIONS))
    decide.add_argument("--reason", required=True)
    decide.add_argument("--decided-at")
    decide.set_defaults(handler=command_decide)

    status = subparsers.add_parser("status", help="汇总批次与审核状态")
    status.add_argument("--batch-dir", required=True)
    status.set_defaults(handler=command_status)

    return root


def main() -> int:
    args = parser().parse_args()
    try:
        result = args.handler(args)
    except WorkflowError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
