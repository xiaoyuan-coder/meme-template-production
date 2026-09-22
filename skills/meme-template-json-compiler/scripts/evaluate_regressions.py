#!/usr/bin/env python3
"""Evaluate template outputs against an immutable regression-suite contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from compiler import ContractError, evaluate_template_regression_suite


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--suite", required=True, type=Path)
    args = parser.parse_args()
    try:
        dataset = _load_json(args.dataset)
        suite = _load_json(args.suite)
        templates = dataset.get("templates") if isinstance(dataset, dict) else dataset
        report = evaluate_template_regression_suite(templates, suite)
    except (OSError, json.JSONDecodeError, ContractError) as exc:
        print(json.dumps({"passed": False, "contractError": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
