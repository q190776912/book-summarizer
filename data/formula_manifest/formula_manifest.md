# `*_formulas.json`（章摘要公式 manifest）

每一章 `.md` 总结里每条数学公式抽出的结构化清单，用于与书源 `page_*.json`
做逐条保真对账。

## 生成脚本
- `formula_manifest.py`（构造器，留在 `..`）
- 输入：章 `.md`（`<book>/ChapterN_*.md` 或 `<book>/第N章_*.md`）
- 类与构造函数：`FormulaManifest`（+ `FormulaRecord`）—— `from formula import FormulaManifest`；
  `FormulaManifest.from_markdown(md, cmap, ch)` / `FormulaManifest.from_records(...)`，`.dump(path)`。
  模块级 `parse(md)` / `normalize(s)` 供 `reconcile_kreyszig` 复用。
- 落盘：`<book>/_extract/<ChapterN>_formulas.json`（EN / CN 各一份）

## 数据结构（每条公式）
```json
{ "ord": "2.6", "kind": "display", "summary_label": "(2.6)",
  "section": "2.3.2", "line": 12, "content": "f(x)=…" }
```
- `ord`：章内 1-based 出现序（display + inline 混排计数）。
- `kind`：`display`（`$$…$$`，含 blockquote `> $$`）| `inline`（`$…$`）。
- `summary_label`：`\tag{X}` 的值；未标号公式为 `null`。
- `section` / `line`：公式在总结中的位置（节号 / 行号）。

## 内联书侧锚点（可选）
可在公式上方加 HTML 注释直接记录书源真相：
```html
<!-- book:2.6 p62 y0.33 §2.3.2 Thm2.2 -->
```
- `book:2.6`=真实序标；`p62`=PDF 页；`y0.33`=页内纵坐标（0~1）；
- `§2.3.2`=书源小节；`Thm2.2`=最近上游书源标题。

> 书无号不编造；已标须正确、不重复、不跨章（公式序标铁律）。

## 关联
- 书源侧对照：`../build_book_manifest/build_book_manifest.md`（`book_chN_formulas.json`）。
- 对齐回填结果：`../fill_book_labels/fill_book_labels.md`（`*_filled.json`）。
- 详细对账流程：`../../verify/formula-manifest/formula-manifest.md`。
