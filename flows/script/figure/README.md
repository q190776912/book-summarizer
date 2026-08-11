# flows\write-source\figures\script\README.md

> 真实代码已随本次重构迁入本 `script/` 目录。各包按名互相 import，
> 由 `../../../lib/boot.py` 在入口处统一注入 `sys.path`（见 SKILL.md「代码位置」）。本文件为索引。

## figure/
- `__init__.py`
- `../../../config/figure_manual_chN/apply_manual_figures.py`
- `assign_figures.py`
- `figure/build_figure_index.py`
- `build_precise_anchors.py`
- `embed_figures.py`
- `extract_figures.py`
- `inspect_tool.py`
- `strip_figure_embeds.py`
