# `book_chN_formulas.json`（书源序标索引）

从 OCR 提取产出的 `page_*.json` 中抽出的**书源侧**公式序标索引，作为
`*_formulas.json` 的"真值"对照集。

## 生成脚本
- `build_book_manifest.py`（构造器，留在 `..`）
- 输入：`<book>/_extract/page_*.json` + `chapter_map.json`
- 类与构造函数：`BookFormulaIndex`（+ `BookFormulaRecord`）—— `from formula import BookFormulaIndex`；
  `BookFormulaIndex.build(extract_dir, cmap, ch)`，`BookFormulaIndex(...).dump(path)`。
- 落盘：`<book>/_extract/book_chN_formulas.json`（每章一份）

## 抽取规则
对每章页面扫描 `text[]` 中的序标模式：`(C.N)` / `Eq. C.N` / `Equation C.N` /
`式（C.N）`（默认 `depth=2`；用 `--depth` 覆盖）。
- **按章号 C 限定作用域**，跨章引用（如 `(C'.N)`）被忽略；
- 必须实测段数推导 `depth`（不要抽样前几页，避免 TOC/前言误导）。

## 数据结构（每条书源序标）

每条 `formulas[]` 元素含：
- `label`：规范化序标 `"C.N"`（可选字母后缀，如 `"8.11a"`）；
- `page`：PDF 页码（首次出现处）；
- `pos_y`：该序标在页中的纵坐标（PDF 点，用于阅读顺序判定）；
- `book_section`：最近上游 OCR 标题（小节定位，如 `"2.3"`）；
- `context`：序标周围 OCR 文本上下文；
- `occ`：该序标在本章的全部出现 `[[page, pos_y], …]`（用于阅读顺序核对）。

文档顶层还含 `chapter` / `chapter_name` / `page_range` / `depth`。

## JSON 示例

```json
{
  "chapter": 2,
  "chapter_name": "Integration",
  "page_range": [48, 103],
  "depth": 2,
  "formulas": [
    {
      "label": "2.1",
      "page": 49,
      "pos_y": 312.5,
      "book_section": "2.1",
      "context": "Equation (2.1) defines the Lebesgue integral of a simple function.",
      "occ": [[49, 312.5], [51, 140.0]]
    },
    {
      "label": "2.11a",
      "page": 88,
      "pos_y": 120.0,
      "book_section": "2.7",
      "context": "... see (2.11a) for the refined bound ...",
      "occ": [[88, 120.0]]
    }
  ]
}
```

## 用途
- 供 `fill_book_labels.py` 回填对齐（见 `../fill_book_labels/fill_book_labels.md`）；
- 供 `diff_formula_manifest.py` 做集合成员 + 阅读顺序 + 小节定位三层校验
  （见 `../../verify/formula-manifest/formula-manifest.md`）。

> 书源 `formulas[].latex` 是 LaTeX-OCR 噪声，不可机比；内容保真须人工核对。
