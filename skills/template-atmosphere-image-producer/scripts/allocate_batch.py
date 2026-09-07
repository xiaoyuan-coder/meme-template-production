#!/usr/bin/env python3
"""Deterministically allocate atmosphere-image batch ratios."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping


class AllocationError(ValueError):
    pass


CARRIER_WEIGHTS = {
    "tshirt": 0.20,
    "long_sleeve": 0.20,
    "sweatshirt": 0.20,
    "canvas_bag": 0.20,
    "other": 0.20,
}
CAMERA_WEIGHTS = {"close": 0.20, "medium": 0.50, "environment": 0.30}
GENDER_WEIGHTS = {"male": 0.30, "female": 0.70}
PRINT_SIDE_WEIGHTS = {"front": 0.80, "back": 0.20}
PET_ROUTES = {"pet_relationship", "pet_product"}
CLOTHING_CARRIERS = {"tshirt", "long_sleeve", "sweatshirt"}


def largest_remainder(total: int, weights: Mapping[str, float]) -> dict[str, int]:
    if total < 0 or not weights or abs(sum(weights.values()) - 1.0) > 1e-9:
        raise AllocationError("weights must be non-empty, sum to one, and use a non-negative total")
    raw = {key: total * value for key, value in weights.items()}
    counts = {key: int(value) for key, value in raw.items()}
    remaining = total - sum(counts.values())
    ranked = sorted(weights, key=lambda key: (-(raw[key] - counts[key]), list(weights).index(key)))
    for key in ranked[:remaining]:
        counts[key] += 1
    return counts


def stable_order(items: list[dict[str, Any]], axis: str) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: hashlib.sha256(f"{axis}:{item['templateKey']}".encode()).hexdigest(),
    )


def assign(items: list[dict[str, Any]], axis: str, weights: Mapping[str, float]) -> dict[str, int]:
    counts = largest_remainder(len(items), weights)
    ordered = stable_order(items, axis)
    cursor = 0
    for value, count in counts.items():
        for item in ordered[cursor:cursor + count]:
            item[axis] = value
        cursor += count
    return counts


def allocate(records: Any, pet_visibility: float = 0.85) -> dict[str, Any]:
    if not isinstance(records, list) or not records:
        raise AllocationError("input must be a non-empty JSON array")
    if not 0.8 <= pet_visibility <= 0.9:
        raise AllocationError("pet visibility must stay between 0.80 and 0.90")
    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    for source in records:
        if not isinstance(source, dict):
            raise AllocationError("every input item must be an object")
        key = source.get("templateKey")
        route = source.get("topicRoute")
        if not isinstance(key, str) or not key or key in seen:
            raise AllocationError("templateKey must be a unique non-empty string")
        if not isinstance(route, str) or not route:
            raise AllocationError(f"{key} requires topicRoute")
        if source.get("singleModel") not in {True, False}:
            raise AllocationError(f"{key} requires explicit singleModel boolean")
        seen.add(key)
        items.append({
            "templateKey": key,
            "topicRoute": route,
            "singleModel": source["singleModel"],
        })

    actual: dict[str, dict[str, int]] = {}
    actual["carrier"] = assign(items, "carrier", CARRIER_WEIGHTS)
    actual["cameraDistance"] = assign(items, "cameraDistance", CAMERA_WEIGHTS)

    model_items = [item for item in items if item["singleModel"]]
    actual["singleModelGender"] = assign(model_items, "singleModelGender", GENDER_WEIGHTS)
    for item in items:
        if not item["singleModel"]:
            item["singleModelGender"] = "not_applicable"

    clothing = [item for item in items if item["carrier"] in CLOTHING_CARRIERS]
    actual["printSide"] = assign(clothing, "printSide", PRINT_SIDE_WEIGHTS)
    for item in items:
        if item["carrier"] not in CLOTHING_CARRIERS:
            item["printSide"] = "not_applicable"

    pet_items = [item for item in items if item["topicRoute"] in PET_ROUTES]
    pet_weights = {"visible": pet_visibility, "not_visible": 1 - pet_visibility}
    actual["petVisibility"] = assign(pet_items, "petVisibility", pet_weights)
    for item in items:
        if item["topicRoute"] not in PET_ROUTES:
            item["petVisibility"] = "not_applicable"

    return {
        "artifactType": "template_atmosphere_batch_allocation",
        "schemaVersion": "1.0.0",
        "policy": {
            "carrier": CARRIER_WEIGHTS,
            "cameraDistance": CAMERA_WEIGHTS,
            "singleModelGender": GENDER_WEIGHTS,
            "printSide": PRINT_SIDE_WEIGHTS,
            "petVisibility": pet_visibility,
            "rounding": "largest_remainder_with_declared_order_tiebreak",
        },
        "actualCounts": actual,
        "items": sorted(items, key=lambda item: item["templateKey"]),
    }


def write_create_once(path: Path, value: Any) -> None:
    encoded = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() == encoded:
            return
        raise AllocationError(f"output conflict: {path}")
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--pet-visibility", type=float, default=0.85)
    args = parser.parse_args()
    try:
        records = json.loads(Path(args.input).read_text(encoding="utf-8"))
        result = allocate(records, args.pet_visibility)
        write_create_once(Path(args.output).expanduser().resolve(), result)
    except (OSError, json.JSONDecodeError, AllocationError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": "allocated", "items": len(result["items"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
