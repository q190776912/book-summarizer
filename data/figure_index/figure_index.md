# `figure_index.json`（图索引 / 命名阶段 2）

PDF 抽取阶段 2 的**命名索引**：把阶段 1 的检测框匹配到书源图号，按章产出。

## 生成脚本
- `figure_index.py`（构造器，留在 `..`）
- 输入：`page_*.json` + `chapter_map.json`（及可选 `figure_manual_chN.json`）
- 类与构造函数：`FigureIndex` / `FigureEmbedOverrides`（+ `Figure`）—— `from figure_index import FigureIndex, FigureEmbedOverrides`；
  `FigureIndex.from_figures(figs)` / `FigureEmbedOverrides.from_figures(figs)`，均 `.dump(path)`。
- 按章增量实例化：`FigureIndex.from_records(records).dump(path)`，由模块级 `merge_index(out_dir, ch, assigned)`
  提供——**被 `flows/script/assign_figures.py` 委托**（裸 `json.dump` 已移出流程脚本，实例化归本目录）。
- 落盘：`<book>/_extract/figure_index.json`

## 数据结构（每条约）
```json
{ "chapter": 1, "page": 5, "fig_idx": 0, "label": "1.2",
  "bbox": [10, 20, 980, 1500], "conf": 0.87,
  "file": "figure/ch01_fig1.2.png", "caption": "…", "source": "mfd" }
```
- `fig_idx`：该章内图序号；
- `label`：图号（如 `"1.2"`）；为 `null` 表示已检测但未匹配到图号
  （文件名落 `chNN_unnamed_K.png`）；
- `source == "manual"`：由 `figure_manual_chN.json` 手动补图，assignment 重跑时保留；
- `caption`：图注文本。

## 消费方
- `../../verify/script/verify_chapter.py` 的 **figure 层(E)：图片完整性 + 图片有效性**。
- 命名 / 嵌入：`assign_figures.py` / `embed_figures.py` / `../../config/figure_manual_chN/apply_manual_figures.py`。

## 关联
- 上游检测：`figure_detect.md`（`figure_detect.json`）。
- 噪声记录：`figure_noise.md`（`fig_noise.json`）。
- 手动补图配置：`../../config/figure_manual_chN/figure_manual_chN.md`；嵌入锚点覆盖：`../figure_embed_overrides/figure_embed_overrides.md`。
- 注意：`figure_embed_overrides.json` 由本生成器一并写出，属可手填覆盖的锚点配置，
  说明见 `../figure_embed_overrides/figure_embed_overrides.md`（与本生成器同目录 `..`）。
