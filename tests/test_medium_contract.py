"""Run the standalone medium contract regressions in the repository suite."""
from helpers import load_module

MediumContractTests = load_module(
    'standalone_medium_tests',
    'skills/meme-template-json-compiler/tests/test_medium_contract.py',
).MediumContractTests
