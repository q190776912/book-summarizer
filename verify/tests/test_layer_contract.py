"""
test_layer_contract.py — schema/contract test for the verify-layer registry.

Goal (Tessa / Testing Expert):
  Prove that every layer contributes ONLY result keys that already exist in
  `DEFAULT_RESULT` (so the byte-compatible `verify_one` contract in
  verify/script/base.py never breaks when a new layer is added), and that every
  auto-fixable layer's `fix_dict` uses ONLY the known fix-fict keys
  (`FIX_KEYS`, from verify/script/base.py).

Run with stdlib unittest (no pytest dependency, runs anywhere):
  python -m unittest verify/test_layer_contract.py -v
"""
import os
import sys
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[2])
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

import sys
import os


import unittest
from verify.script.register_all import LAYER_REGISTRY
from verify.script.base import DEFAULT_RESULT
from verify.script.base import VerifyContext
from verify_config import BookConfig, GroupConfig

# Fix-dict contract keys (verify/script/base.py): h, h_stmt, h_ul, h_mbq, c, g, i, j, k, l, m, n
FIX_KEYS = {'h', 'h_stmt', 'h_ul', 'h_mbq', 'c', 'g', 'i', 'j', 'k', 'l', 'm', 'n'}

# Allowed result-dict keys = the exact legacy contract mirrored by DEFAULT_RESULT.
ALLOWED = set(DEFAULT_RESULT.keys())

FIXTURE_DIR = os.path.join(
    'C:/Users/ye190/.agents/skills/book-summarizer', 'verify', 'tests', 'fixtures')
FIXTURE_PATH = os.path.join(FIXTURE_DIR, 'sample.md')

# Minimal valid markdown. Kept trivial on purpose: one heading, one paragraph,
# one blockquote, one display-math block. No numbered items / sub-items / `---`
# so every structural layer runs but emits empty findings (exercises the code
# paths without introducing spurious findings).
FIXTURE_MD = """# Chapter 1

A paragraph of sample text for the layer-contract test.

> quote

$$
x = 1
$$
"""


class LayerContractTest(unittest.TestCase):
    def setUp(self):
        os.makedirs(FIXTURE_DIR, exist_ok=True)
        # Rewrite the fixture fresh each test so fix-layer mutations from a
        # prior test method cannot leak into this one (unittest runs methods
        # in alphabetical order: test_fix_keys_subset precedes
        # test_metadata_keys_subset).
        with open(FIXTURE_PATH, 'w', encoding='utf-8') as f:
            f.write(FIXTURE_MD)

        # NOTE: the task baseline suggested ext_dir=None, but EXTRACT.run calls
        # extract_items(ext_dir, ...) which does range(start, end+1) — that
        # raises with ext_dir=None / start=None. Per the task's explicit
        # permission to "adjust the context fields until run executes", we
        # point ext_dir at the real (page-file-free) fixtures dir and pass
        # integer ch/start/end so EXTRACT.run returns a clean empty LayerResult.
        # The fixtures dir contains no page_*.json / figure_index.json, so every
        # extract/figure/OCR scan path short-circuits to empty output.
        self.ctx = VerifyContext(
            ch=1,
            start=1,
            end=2,
            md_file=FIXTURE_PATH,
            ext_dir=FIXTURE_DIR,
            config=BookConfig(ordinal=[GroupConfig(type=3)]),
        )

    def test_metadata_keys_subset(self):
        """Every layer's run() contributes ONLY keys already in DEFAULT_RESULT."""
        self.assertGreater(len(LAYER_REGISTRY.all_ordered()), 0,
                           "registry has no layers registered")
        for layer in LAYER_REGISTRY.all_ordered():
            res = layer.run(self.ctx)
            self.assertIsNotNone(
                res, f"layer {layer.code} run() returned None")
            unknown = set(res.metadata.keys()) - ALLOWED
            self.assertEqual(
                unknown, set(),
                f"layer {layer.code} contributes unknown result keys {unknown}")

    def test_fix_keys_subset(self):
        """Every registered fixer (FIXERS, the post-merge fix mechanism) emits
        ONLY known fix-dict keys (FIX_KEYS).

        Auto-correct logic lives on standalone `fix_<snake>.py` modules
        registered via `register_fixer` (codes H/G/I/J/K/L/M/N preserved),
        NOT on auto_fixable VerifyLayers. `VerifyManager.fix` consumes FIXERS
        directly, so we validate FIXERS here instead of LAYER_REGISTRY."""
        from verify.script.base import FIXERS, fixable_ordered_fixers
        self.assertGreater(len(FIXERS), 0, "FIXERS registry has no fixers")
        for code, (fix_order, fn) in fixable_ordered_fixers():
            fr = fn(self.ctx)
            if fr is None:
                continue
            unknown = set(fr.fix_dict.keys()) - FIX_KEYS
            self.assertEqual(
                unknown, set(),
                f"fixer {code} fixes unknown keys {unknown}")


if __name__ == '__main__':
    unittest.main()
