# `*_filled.json`（对齐回填结果）

将书源真相（`book_chN_formulas.json`）回填到章摘要 manifest
（`*_formulas.json`）后的对齐结果，供 diff 校验消费。

## 生成脚本
- `fill_book_labels.py`（构造器，留在 `..`）
- 输入：`<ChapterN>_formulas.json` + `book_chN_formulas.json`
- 类与构造函数：`FormulaFill` —— `from formula import FormulaFill`；
  `FormulaFill.run(summary, book)` 构造，`FormulaFill(...).dump(path)`，`.counts()` 给 ok/label_not_in_book/unlabeled_summary。
- 落盘：`<book>/_extract/<ChapterN>_filled.json`（EN / CN 各一份）

## 数据结构（每条 display 公式的状态）
- `ok`：summary 标号在书源集中找到 → 回填 `book_label` / 页 / `pos_y` / 上下文；
- `label_not_in_book`：summary 标号不在书源集 → 编造 / 错章引用（`__UNMATCHED__`）；
- `unlabeled_summary`：summary 未标号，书源有号 → 漏标号（警告，需人工确认）。

## JSON 示例

```json
{
  "chapter_file": "Chapter2_Integration_CN.md",
  "formulas": [
    {
      "ord": "2.6",
      "kind": "display",
      "summary_label": "(2.6)",
      "section": "2.3.2",
      "line": 12,
      "content": "f(x)=…",
      "book_label": "2.6",
      "page": 49,
      "pos_y": 312.5,
      "book_section": "2.3.2",
      "context": "Equation (2.6) defines …",
      "book_occ": [[49, 312.5]],
      "status": "ok"
    },
    {
      "ord": "2.9",
      "kind": "display",
      "summary_label": "(2.9)",
      "section": "2.4.1",
      "line": 40,
      "content": "g(x)=…",
      "book_label": "__UNMATCHED__",
      "status": "label_not_in_book"
    },
    {
      "ord": "2.12",
      "kind": "inline",
      "summary_label": null,
      "section": "2.5.1",
      "line": 55,
      "content": "e^{iθ}",
      "status": "inline"
    }
  ]
}
```

- 顶层 `formulas` 与章摘要 manifest 同构（每条公式一个对象），并追加 `book_label` / `page` / `pos_y` / `book_section` / `context` / `book_occ` 与 `status`；
- `status`：`ok`（命中书源）/ `label_not_in_book`（书源无此号，`book_label="__UNMATCHED__"`）/ `unlabeled_summary`（summary 未标号）/ `inline`（行内公式，不参与标号对账）；
- `chapter_file`：来源章 `.md` 名（可选字段）。

## 校验判定
对 `filled` 跑 `diff_formula_manifest.py`（流程脚本，已归回
`../../verify/formula-manifest/script`）得到：
- `FABRICATED`：标号不在书源集；
- `MISSING`：书源标号未在 summary 出现（WARN 不阻断）；
- `ORDER_MISMATCH`：文档顺序 ≠ 书源阅读顺序（页,纵坐标）；
- `MISPLACED`：`section` 与 `book_section` 在 `C.N` 两级不一致；
- `OMITTED` / `UNLABELED`：summary 未标号（警告）。

> 上述仅保"标号集合 / 阅读顺序 / 小节定位"三层结构保真；公式内容保真
> 与"同小节内标号互换"仍需人工对照书源。完整判定语义见
> `../../verify/formula-manifest/formula-manifest.md`。

## 关联
- 上游：章摘要 `../formula_manifest/formula_manifest.md`、书源索引 `../build_book_manifest/build_book_manifest.md`。
