"""Standalone, offline integration checks using anonymous fixture evidence."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SKILL_ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('integration_compiler', SKILL_ROOT / 'scripts/compiler.py')
compiler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compiler)


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads((SKILL_ROOT / 'examples/integration-input.json').read_text())

    def compile(self, fixture):
        return compiler.compile_final_json(fixture['approvedImage'], fixture['analysis'],
                                           fixture['formalDraft'], fixture['registryResponse'])

    def test_compile_and_create_once_delivery(self):
        formal = self.compile(self.fixture)
        self.assertNotIn('imageUrl', formal)
        with tempfile.TemporaryDirectory() as directory:
            path = compiler.write_formal_json(Path(directory), formal)
            self.assertEqual(json.loads(path.read_text()), formal)
            self.assertEqual(compiler.write_formal_json(Path(directory), formal), path)
            with self.assertRaises(compiler.ContractError):
                compiler.write_formal_json(Path(directory), {**formal, 'title': '冲突交付'})

    def test_revision_from_enriched_baseline(self):
        previous = self.compile(self.fixture)
        previous['imageUrl'] = 'https://assets.memebuy.cn/memebuy/template-atmosphere/sha256/' + 'a' * 64 + '.png'
        original = copy.deepcopy(previous)
        draft = self.fixture['formalDraft']
        draft['title'] = '抱紧你的毛孩子'
        self.fixture['analysis']['selfReview']['reviewedDraftSha256'] = compiler.sha256_json(draft)
        registry = self.fixture['registryResponse']
        registry['decision'] = 'EXISTING_SAME_SOURCE'
        scope = {'previousFormalSha256': compiler.sha256_json(previous),
                 'requestEvidence': ['fixture://title-request'], 'addedSlotIds': [],
                 'removedSlotIds': [], 'modifiedSlotIds': [], 'changedFieldPaths': ['/title']}
        revised = compiler.compile_json_revision(previous, scope, self.fixture['approvedImage'],
                                                  self.fixture['analysis'], draft, registry)
        self.assertNotIn('imageUrl', revised)
        self.assertEqual(previous, original)
        self.assertEqual(revised['title'], draft['title'])

    def test_reject_stale_review_and_image_only_delivery(self):
        self.fixture['formalDraft']['title'] = '修改后的标题'
        with self.assertRaises(compiler.ContractError):
            self.compile(self.fixture)
        self.fixture['analysis']['selfReview']['reviewedDraftSha256'] = compiler.sha256_json(self.fixture['formalDraft'])
        formal = self.compile(self.fixture)
        formal['inputSchema']['slots'][0].pop('text')
        formal['inputSchema']['slots'][0].pop('resolutionStrategy')
        with self.assertRaises(compiler.ContractError):
            compiler.validate_formal_json(formal)


if __name__ == '__main__':
    unittest.main()
