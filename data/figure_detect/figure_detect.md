# `figure_detect.json`（图检测阶段 1）

PDF 抽取阶段 1 的**原始检测**记录，由图检测模型（MFD）逐页产出，按章增量追加。

## 生成脚本
- **构造器**：`figure_detect.json` 由 in-skill `flows/script/extract_figures.py` 的检测阶段写出（底层用 PDF-Extract-Kit / MFD 权重），
  随后由 `build_figure_index.py` 读取它来合成 `figure_index.json`。
- 落盘：`<book>/_extract/figure_detect.json`（`extract_figures.py` 检测阶段写出）。

## 数据结构（每条约）
```json
{ "chapter": 1, "page": 5, "det_id": 0,
  "bbox": [10, 20, 980, 1500], "conf": 0.87,
  "file": "figure/det_p005_00.png", "cap_text": "", "source": "mfd", "label": null }
```
- `chapter` / `page`：所属章 / 页；
- `det_id`：该页内检测序号；
- `bbox`：检测框 `[x0,y0,x1,y1]`；
- `conf`：检测置信度（MFD `conf_thres`，当前 0.15）；
- `file`：裁剪图相对路径（阶段 1 仅检测框，未命名）；
- `cap_text` / `source`： caption 文本（阶段 1 通常空）/ 来源（`mfd`）；
- `label`：阶段 1 未命名，`null`。

## 关联
- 命名阶段产物：`../figure_index/figure_index.md`（`figure_index.json`）。
- 检测 / 命名 / 裁剪的**消费**脚本（`extract_figures.py` / `assign_figures.py` /
  `embed_figures.py`）属图流水线编排，**留 `../../flows`**；`apply_manual_figures.py`
  已归并到其 JSON 目录 `../../config/figure_manual_chN`。
- 流水线参考：`../../flows/write-source/figures/figures.md`。
