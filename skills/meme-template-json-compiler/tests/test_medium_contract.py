"""Offline regression checks for visual fact validation and projection."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('medium_compiler', ROOT / 'scripts/compiler.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class MediumContractTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / 'examples/integration-input.json').read_text())
        self.schema = json.loads((ROOT / 'references/contracts/approved-image-analysis.schema.json').read_text())

    def compile(self, data):
        return c.compile_final_json(data['approvedImage'], data['analysis'], data['formalDraft'], data['registryResponse'])

    def test_invalid_fact_items_are_rejected_by_schema_and_compiler(self):
        for field in ('styleTraits', 'composition', 'colorAndLight'):
            for values in ([''], ['   '], [123], [None], [{}], ['x' * 501], ['重复', '重复']):
                with self.subTest(field=field, values=values):
                    data = copy.deepcopy(self.data)
                    data['analysis']['mediumComposition'][field] = values
                    self.assertTrue(list(Draft202012Validator(self.schema).iter_errors(data['analysis'])))
                    with self.assertRaises(c.ContractError):
                        self.compile(data)

    def test_invalid_medium_and_empty_required_arrays_are_rejected(self):
        for value in ('', '  ', 42, 'x' * 501):
            data = copy.deepcopy(self.data)
            data['analysis']['mediumComposition']['medium'] = value
            with self.subTest(value=value), self.assertRaises(c.ContractError):
                self.compile(data)
        for field in ('styleTraits', 'composition'):
            data = copy.deepcopy(self.data)
            data['analysis']['mediumComposition'][field] = []
            with self.subTest(field=field), self.assertRaises(c.ContractError):
                self.compile(data)

    def test_changed_analysis_medium_cannot_keep_old_contract(self):
        self.data['analysis']['mediumComposition']['medium'] = '真实摄影'
        with self.assertRaisesRegex(c.ContractError, 'match the analyzed medium'):
            self.compile(self.data)

    def test_fresh_review_does_not_allow_dropped_visual_facts(self):
        for field in ('styleTraits', 'composition', 'colorAndLight'):
            data = copy.deepcopy(self.data)
            # Both formal draft and semantic model agree, and the review SHA is fresh.
            data['formalDraft']['runtimeSemantics']['visualContract'][field] = ['无关的另一条约束']
            data['analysis']['semanticModel']['runtimeSemantics'] = copy.deepcopy(data['formalDraft']['runtimeSemantics'])
            data['analysis']['selfReview']['reviewedDraftSha256'] = c.sha256_json(data['formalDraft'])
            with self.subTest(field=field), self.assertRaisesRegex(c.ContractError, 'retain every selected'):
                self.compile(data)

    def test_empty_color_logic_and_additional_constraints_are_valid(self):
        data = self.data
        data['analysis']['mediumComposition']['colorAndLight'] = []
        data['formalDraft']['runtimeSemantics']['visualContract']['colorAndLight'] = []
        data['formalDraft']['runtimeSemantics']['visualContract']['styleTraits'].append('新身份沿用相同的轮廓处理方式')
        data['analysis']['semanticModel']['runtimeSemantics'] = copy.deepcopy(data['formalDraft']['runtimeSemantics'])
        data['analysis']['selfReview']['reviewedDraftSha256'] = c.sha256_json(data['formalDraft'])
        formal = self.compile(data)
        self.assertEqual(formal['runtimeSemantics']['visualContract']['colorAndLight'], [])
        self.assertEqual(len(formal['runtimeSemantics']['visualContract']['styleTraits']), 2)


if __name__ == '__main__':
    unittest.main()
