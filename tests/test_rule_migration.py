from __future__ import annotations

import json
import re
import unittest

from helpers import ROOT


class RuleMigrationTests(unittest.TestCase):
    def test_every_rule_packet_has_a_real_owner_and_observable_test(self):
        implementation = json.loads(
            (ROOT / "contracts/rule-implementation-map.json").read_text(encoding="utf-8")
        )
        entries = implementation["rules"]
        self.assertTrue(entries)
        self.assertEqual(len({entry["ruleId"] for entry in entries}), len(entries))
        tests = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "tests").glob("test_*.py"))
        for entry in entries:
            owner = ROOT / entry["ownerFile"]
            self.assertTrue(owner.is_file(), entry["ruleId"])
            owner_text = owner.read_text(encoding="utf-8")
            symbol = entry["ownerSymbol"]
            self.assertRegex(owner_text, rf"(?:def|class)\s+{re.escape(symbol)}\b", entry["ruleId"])
            self.assertTrue(entry["tests"], entry["ruleId"])
            for test_name in entry["tests"]:
                self.assertIn(f"def {test_name}(", tests, f"{entry['ruleId']} -> {test_name}")

    def test_retired_paths_are_absent_from_both_skills(self):
        text = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for path in (ROOT / "skills").rglob("*")
            if path.is_file() and path.suffix in {".md", ".py", ".json", ".yaml"}
        )
        for retired in (
            "template-json-test",
            "contentRegenerationModel",
            "live shadow",
            "27-item qualification ledger",
            "authoring-handoff",
        ):
            self.assertNotIn(retired.casefold(), text.casefold())
        self.assertNotRegex(text, r"\bT1\b")


if __name__ == "__main__":
    unittest.main()
