from __future__ import annotations

import copy
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

from helpers import load_module, valid_formal_draft
from test_json_compiler import valid_image_envelope

compiler = load_module('safe_delivery_compiler', 'skills/meme-template-json-compiler/scripts/compiler.py')


class JsonDeliverySafetyTests(unittest.TestCase):
    def setUp(self):
        self.formal = compiler.project_formal_json(valid_formal_draft(), valid_image_envelope())

    def test_writer_rejects_image_only_and_third_stage_fields_before_writing(self):
        image_only = copy.deepcopy(self.formal)
        image_only['inputSchema']['slots'][0].pop('text')
        image_only['inputSchema']['slots'][0].pop('resolutionStrategy')
        for invalid in [image_only, {**self.formal, 'imageUrl': None},
                        {**self.formal, 'imageUrl': 'https://example.com/a.png'}]:
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / 'delivery'
                with self.assertRaises(compiler.ContractError):
                    compiler.write_formal_json(root, invalid)
                self.assertFalse(root.exists())

    def test_writer_rejects_six_slots_even_when_gallery_schema_accepts_them(self):
        invalid = copy.deepcopy(self.formal)
        prototype = invalid['inputSchema']['slots'][0]
        slots = [{**copy.deepcopy(prototype), 'id': f'subject{i}'} for i in range(6)]
        invalid['inputSchema']['slots'] = slots
        invalid['promptTemplate'] = ' '.join('{{ ' + slot['id'] + ' | "橘白猫" }}' for slot in slots)
        binding = invalid['runtimeSemantics']['inputBindings']['subject']
        invalid['runtimeSemantics']['inputBindings'] = {slot['id']: copy.deepcopy(binding) for slot in slots}
        with self.assertRaisesRegex(compiler.ContractError, 'at most five'):
            compiler.validate_formal_json(invalid)

    def test_concurrent_writers_preserve_winner_and_reuse_identical_content(self):
        for same in [False, True]:
            with self.subTest(same=same), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                other = copy.deepcopy(self.formal)
                if not same:
                    other['title'] = '另一个交付版本'
                barrier = Barrier(2)
                real_link = compiler.os.link
                def simultaneous_link(src, dst):
                    barrier.wait(timeout=5)
                    return real_link(src, dst)
                def write(value):
                    try:
                        return ('ok', compiler.write_formal_json(root, value))
                    except compiler.ContractError:
                        return ('conflict', None)
                with patch.object(compiler.os, 'link', side_effect=simultaneous_link):
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        results = list(pool.map(write, [self.formal, other]))
                self.assertEqual(sum(status == 'ok' for status, _ in results), 2 if same else 1)
                path = next(path for status, path in results if status == 'ok')
                winner = [self.formal, other][next(i for i, r in enumerate(results) if r[0] == 'ok')]
                self.assertEqual(json.loads(path.read_text()), winner)
                self.assertEqual(list(path.parent.iterdir()), [path])
                self.assertEqual(list(root.resolve().iterdir()), [path.parent])

    def test_dangling_target_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            item = root / self.formal['key']
            item.mkdir()
            target = item / (self.formal['key'] + '.json')
            outside = root / 'missing.json'
            target.symlink_to(outside)
            with self.assertRaises(compiler.ContractError):
                compiler.write_formal_json(root, self.formal)
            self.assertTrue(target.is_symlink())
            self.assertFalse(outside.exists())


if __name__ == '__main__':
    unittest.main()
