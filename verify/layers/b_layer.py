# 本层的语义 / 阈值 / --fix 范围 / 字节契约键 的权威说明见 references/layers/b.md（SSOT）；本文件仅含实现，勿在此复述叙事。
"""
b_layer.py — B-LAYER (order 3): extraction-completeness blocking.

The actual "re-scan" detection lives inside extract_items (which returns the
`blocking` list). This layer realises the documented --ignore behaviour: it
suppresses B-layer blocking entries whose referenced item keys are ALL registered
as confirmed noise, and folds those keys into `ignored_hit` (stage 2). The EXTRACT
provider already produced stage-1 `ignored_hit`; this layer is the second stage.

Self-contained implementation (bodies relocated from verify_chapter.py during the per-layer split).
"""
import re

from verify.registry import VerifyLayer, LayerResult
from verify.key_parse import sortkey


class BLayer(VerifyLayer):
    code = 'B'
    order = 3
    auto_fixable = False

    def run(self, ctx):
        blocking = list(ctx.extraction_blocking or [])
        ignored_hit = list(ctx.ignored_hit or [])
        ignore_keys = ctx.ignore_keys

        # Suppress B-layer blocking entries whose referenced item keys are ALL
        # registered as confirmed noise; fold those keys into ignored_hit.
        if ignore_keys and blocking:
            kept = []
            for msg in blocking:
                sec_m = re.search(r'(\d+\.\d+)', msg)
                nums = re.findall(r'-(\d+)', msg)
                if sec_m and nums:
                    sec = sec_m.group(1)
                    bkeys = {f"{sec}-{n}" for n in nums}
                    if bkeys <= ignore_keys:
                        ignored_hit = sorted(set(ignored_hit) | bkeys, key=sortkey)
                        continue
                kept.append(msg)
            blocking = kept

        ctx.ignored_hit = ignored_hit
        ctx.extraction_blocking = blocking

        return LayerResult(code=self.code, metadata={
            'blocking': blocking,
            'ignored_hit': ignored_hit,
        })
