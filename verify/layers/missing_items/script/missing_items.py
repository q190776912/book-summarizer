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

# 本层的语义 / 阈值 / --fix 范围 / 字节契约键 的权威说明见 verify/layers/missing_items/missing_items.md（SSOT）；本文件仅含实现，勿在此复述叙事。
"""
missing_items.py — A-LAYER (order 2): .md completeness.

Every item the extractor detected (minus confirmed-noise) must appear in the
written .md. Consumes ctx.extracted / ctx.all_keys / ctx.entry_keys populated by
the EXTRACT provider. Self-contained implementation (bodies relocated from verify_chapter.py during the per-layer split).
"""
from verify.layers.script.base import VerifyLayer, LayerResult
from verify.script.key_parse import sortkey


class ALayer(VerifyLayer):
    code = 'A'
    name = 'missing-items'
    order = 2
    auto_fixable = False

    def run(self, ctx):
        extracted = ctx.extracted or set()
        all_keys = ctx.all_keys or set()
        entry_keys = ctx.entry_keys or set()

        truly_missing = sorted(extracted - all_keys)
        mentioned_only = sorted((extracted & all_keys) - entry_keys, key=sortkey)
        extra = sorted(all_keys - extracted, key=sortkey)

        return LayerResult(code=self.code, metadata={
            'truly_missing': truly_missing,
            'mentioned_only': mentioned_only,
            'extra': extra,
        })
