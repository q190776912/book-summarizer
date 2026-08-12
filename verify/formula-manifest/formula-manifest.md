# Sub-flow: verify / formula-manifest（公? manifest 保真对账 / Step 3.6?

> 统一模板：目的 / 前置 / 步骤 / 本阶段规则 / 出口 / 相关代码 / 子流程

## 目的
`verify_chapter.py` ? Q 层只?"归一化编号的集合成员"匹配—?**不查编号落在哪一节、也不查公式内容**。本子流程记录每条公式的**书页 + 真实书标 + 页中位置（纵坐标?**，与书源 `page_*.json` 做逐条对账，补?"编号挂错公式 / 错位 / 内容被改?"的盲区?
## 前置
- 章节 `.md` 已写好（并过嵌图）；
- ? `_extract/` 已有该书 `page_*.json` + `chapter_map.json`?

## 步骤（有序）

**A. 新书写作时（推荐?**：写完章 `.md` 后跑提取器产? `formulas.json`；可在公式上方加 HTML 注释锚点直接记录书侧真相?
```bash
python data/formula_manifest/formula_manifest.py "<book>/ChapterN_*.md" \
    -o "<book>/_extract/ChapterN_formulas.json" \
    --chapter-map "<book>/_extract/chapter_map.json" --chapter N
```
可选内联注释：`<!-- book:2.6 p62 y0.33 §2.3.2 Thm2.2 -->`（`book:2.6`=真实序标；`p62`=PDF 页；`y0.33`=页内纵坐标；其余=上下文）?

**B. 已总结、无 manifest 的书（回填）**?
```bash
python verify/formula-manifest/script/backfill_all.py --book-root "<book>" --extract-dir _extract
```

**对账（单次）**?
```bash
python data/build_book_manifest/build_book_manifest.py --extract-dir _extract \
    --chapter-map _extract/chapter_map.json --chapter N -o _extract/book_chN_formulas.json
python data/fill_book_labels/fill_book_labels.py _extract/ChapterN_formulas.json \
    _extract/book_chN_formulas.json -o _extract/ChapterN_filled.json
python verify/formula-manifest/script/diff_formula_manifest.py _extract/ChapterN_filled.json \
    _extract/book_chN_formulas.json
```

## 本阶段规则（🔴 内联?
- **diff 判定（display 公式?**?
  - `FABRICATED`：summary 标号不在书源? ? 编? / 错章引用，修 summary?
  - `MISSING`：书源标号未? summary 出现 ? summary 漏写，修 summary?
  - `ORDER_MISMATCH`：summary 标号文档顺序 ? 书源阅读顺序（页,纵坐标）? 错位 / 漏插导致序列偏移?
  - `MISPLACED`：summary 公式 `section` 与书? `book_section` ? `C.N` 两级不一? ? 标号挂错节；
  - `OMITTED`：summary 未标号但书源有号 ? 漏标号；
  - `UNLABELED`（警告）：summary 未标? display，需人工确认书里也确无号?
- **自动化边?**：上述检查保"标号集合 / 阅读顺序 / 小节定位"三层结构保真，但**公式内容保真**?"同小节内标号互换"仍需人工对照书源（书? `formulas[].latex` ? LaTeX-OCR 噪声，不可机比）。这是回填时"人工核对"的真正对象?
- **公式序标铁律不变**：书无号不编造；已标须正确、不重复、不跨章。Q ? `FABRICATED`/`INCONSISTENT=0` 即满足前两条；余? `MISSING` ? WARN 不阻断（按用户旨意刻意不补）?

## 出口条件
- 出口：diff 无硬错（`FABRICATED`/`MISPLACED`/`ORDER_MISMATCH` 归零），或已人工核对内容保真?

## 相关代码（路径相? skill 根目录）
- 构造器（data/）：`formula_manifest.py` / `build_book_manifest.py` / `fill_book_labels.py`?
- 流程脚本（verify/formula-manifest/script/）：`diff_formula_manifest.py`（diff 判定?/ `backfill_all.py`（全书批量回填）/ `reconcile_kreyszig.py` · `renumber_kreyszig.py`（Kreyszig 专用内容级对账）/ `prep_content_check.py`（可视化核对准备）?
- JSON 数据结构权威说明? [`../../data/data_schema.md`](../../data/data_schema.md)（含 `../../data/formula_manifest/formula_manifest.md` / `../../data/build_book_manifest/build_book_manifest.md` / `../../data/fill_book_labels/fill_book_labels.md` 三篇）?

## 子流?
无?
