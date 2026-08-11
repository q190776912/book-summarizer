# `figure_manual_chN.json` 配置说明

> 每章一个的手动补图配置文件，位于本书 `_extract/figure_manual_chN.json`。当 DocLayout-YOLO 漏判某图（旋转 90° 全页图、文字密集分类树被当 `plain text` 等）导致 E 层报"图 X.X.X missing"时，手动声明该图的位置 / 旋转 / 图注，供 `apply_manual_figures.py` 渲染裁剪并写回 `figure_index.json`。

## 结构

JSON **字典**，键为图号（`"1.3.1"`），值为：

| 字段 | 类型 | 说明 |
|------|------|------|
| `page` | `int` | 该图被引用的页（以原文 / `../../flows/script/figure/inspect_tool.py` 定位）。 |
| `bbox` | `[int,int,int,int]` | 图的像素裁剪框 `[x0, y0, x1, y1]`，以 200-DPI 渲染图坐标为准。 |
| `rotate` | `int?` | 可选。PDF 旋转存放角度（如 `90`）。 |
| `caption` | `str` | 图注文本（如 `"图 1.3.1 动力系统分类框架（旋转 90° 存放）"`）。 |

## JSON 示例

```json
{
  "1.3.1": {
    "page": 27,
    "bbox": [35, 60, 1064, 1515],
    "rotate": 90,
    "caption": "图 1.3.1 动力系统分类框架（旋转 90° 存放）"
  }
}
```

## 执行

`python config/figure_manual_chN/apply_manual_figures.py <_extract> <ch> --pdf <pdf_path>`；重验 `../../verify/script/verify_chapter.py` → E 层看到图号已提供 → PASS。手动图在每次 assignment 重跑时保留（不删 `source="manual"` 条目）。
