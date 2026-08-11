# `fig_noise.json`（图噪声 / 非图判定记录）

图生成器在检测 / 命名过程中判定的**噪声或误检**记录，作为辅助产物，
用于排查被错误识别为图的区域。

## 生成脚本
- **无 in-skill 构造器**：`fig_noise.json` 由外部图检测 / 噪声判定工具产出（或被 verify 阶段引用，
  见 `verify_chapter.py` 的 `--ignore-figure fig_noise.json`），本 skill 的 `..` 下
  **没有**对应构造脚本；它与 `figure_index.json` 的构造器 `build_figure_index.py` 无关。
- 落盘：`<book>/_extract/fig_noise.json`（外部工具 / verify 阶段写出，非本 skill 构造）。

## 内容
- 被模型以高置信判为"非图"或低质裁剪的区域；
- 可能含：文字块误检、装饰线、被截断的半幅图等。

## 用途
- 人工复核"漏检 / 误检"时对照；
- 不参与嵌入，仅作诊断辅助。

## 关联
- 主检测产物：`figure_detect.md`（`figure_detect.json`）。
- 命名索引：`figure_index.md`（`figure_index.json`）。

## JSON 示例（代表性）

```json
[
  {
    "chapter": 1,
    "page": 9,
    "det_id": 3,
    "bbox": [10, 20, 980, 1500],
    "conf": 0.92,
    "reason": "plain_text_block",
    "file": null
  },
  {
    "chapter": 2,
    "page": 33,
    "det_id": 1,
    "bbox": [10, 20, 980, 1500],
    "conf": 0.41,
    "reason": "truncated_half_figure",
    "file": null
  }
]
```

- 每条为被判定为「非图 / 低质」的检测区域；
- `reason` 记录误检类别（文字块误检、装饰线、被截断的半幅图等）；
- `file` 为 `null`（噪声不落裁剪图）；形状随外部检测工具版本而异，以上为代表性骨架。
