# flows\write-source\format\script\README.md

> 真实代码已随本次重构迁入本 `script/` 目录。各包按名互相 import，
> 由 `../../../../lib/boot.py` 在入口处统一注入 `sys.path`（见 SKILL.md「代码位置」）。本文件为索引。

## format/
- `format/__init__.py`
- `format/_wrap_raw_math.py`
- `format/bq_core.py`
- `format/check_katex.py`
- `format/fix_bq_display_math.py`
- `format/fix_katex.py`
- `format/fmt_extras.py`
- `format/fmt_proofs.py`
- `format/katex_heuristics.py`
- `format/katex_render.py`
- `format/mathify_plaintext.py`
- `format/proof_steps.py`
- `format/split_chapters.py`
- `format/unwrap_blockquote_items.py`
- `format/wrap_examples_bq.py`

## node_modules/
- `node_modules/commander` — 子包
- `node_modules/katex` — 子包
