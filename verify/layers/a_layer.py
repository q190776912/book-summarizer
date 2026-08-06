# 本层的语义 / 阈值 / --fix 范围 / 字节契约键 的权威说明见 references/layers/a.md（SSOT）；本文件仅含实现，勿在此复述叙事。
"""
a_layer.py — A-LAYER (order 2): .md completeness.

Every item the extractor detected (minus confirmed-noise) must appear in the
written .md. Consumes ctx.extracted / ctx.all_keys / ctx.entry_keys populated by
the EXTRACT provider. Self-contained implementation (bodies relocated from verify_chapter.py during the per-layer split).
"""
from verify.layers.base import VerifyLayer, LayerResult
from verify.key_parse import sortkey


class ALayer(VerifyLayer):
    code = 'A'
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
