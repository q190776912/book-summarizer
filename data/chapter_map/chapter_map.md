# chapter_map.json（章节映射）

## 目的
全书章节映射，作为后续"某章是否已可写"的**唯一**判定依据（规则1）。

## 生成脚本
- **`tools/build_chapter_map.py`（🔴 一步生成正确页码，主路径）**：agent 只填结构（章号 + 中/英章名 + 附录标记），本工具扫描 `page_*.json` 从 OCR 自动算出每章 `start`/`end` 写回，并产出 `chapter_map.build_report.md` 供 agent 判断。`cli.py build-chapter-map` 同义。
- `data/chapter_map/chapter_map.py`（模型/构造函数）：`ChapterMap.default()` / `.load(path)` / `.dump(path)`，仅供生成模板或程序化构造；**不负责页码计算**——页码一律交给 `build_chapter_map.py` 从证据算出。`cli.py write-chapter-map` 同义。

## 落盘位置
- `<book>/_extract/chapter_map.json`

## 数据结构
```json
{
  "chapters": [
    { "ch": 1, "name": "测度论", "name_en": "Measure Theory" },
    { "ch": 2, "name": "积分", "name_en": "Integration" }
  ]
}
```
- `ch`：章号（整数；附录用 `"A"`/`"E"` 等字母）。
- `name`：章名（中文书填中文，英文书可双语）。`name_en`：英文章名（检测引擎匹配标题用，英文书必填；中文书可空）。
  - 🔴 **附录章填裸标题，不带序标**：`"Appendix A"` 序标由 `ch` 字母承载（与数字章 name 不含 "Chapter N" 前缀同理）。契约章名由 `build_structure` 拼成 `"{ch} {name}"`，下游按此渲染 `# Appendix A: {name}` 与文件名 `AppendixA_{name}.md` / `附录A_{name}.md`——若 name 再填 "Appendix A"，会得到双前缀 `"A Appendix A"`（实测 Weibel《An Introduction to Homological Algebra》Appendix A：name 应为 `"Category Theory Language"` 而非 `"Appendix A"`）。`build_structure` 对 `"Appendix {ch}: …"` 形态的旧数据有剥前缀兜底，但登记时直接填裸标题。
- `start` / `end`：**PDF 文件页码**（1-based，与 `page_%03d.json` 文件名序号一致；即 `scan_skeleton.scan` 直接 `range(start, end+1)` 读取的页），**不是**原书印刷页码。🔴 **agent 不手写这两个字段**——由 `build_chapter_map.py` 从 OCR 证据算出后写回（authoring 时可省略或仅填 TOC 粗略值）。

## 关键规则（🔴）
- **规则1 — config 子流程统一生成、且只建一次**：chapter_map 在 extract 的 **config 子流程（MM Repair 完成后）** 一次性生成（见 `../../flows/write-source/config_setting/config_setting.md` 步骤 1），不在提取轮询期间早建；全书 `chapter_map` 只生成一份，后续不重复生成（除非用户明确要改章节划分）。
- 判定"某章可写"的硬标准：`info.end <= current_max_page`（该章末页已落盘）。
- 🔴 **chapter_map 一律以 PDF 页号存储，禁止存印刷页号**：`scan_skeleton` / `build_structure` 直接拿 `start`/`end` 当 `page_%03d.json` 序号去读，存印刷页号会导致整章错 15 个 PDF 页（本书实测前 15 页为封面/前言/目录，PDF 页 = 印刷页 + 15，双锚点确认）。**若从 TOC 读到的章节边界是印刷页号，必须加上前页偏移换算成 PDF 页号后再写入**（`_meta.pdf_offset` 仅作人读参考，但 `start`/`end` 本身必须是 PDF 页号）。

## 详细流程
- 子流程文档：`../../flows/write-source/config_setting/config_setting.md`（步骤 1）

## 一次性生成 + agent 判断（🔴 主路径）
`chapter_map.json` 的页码**一步从 OCR 算出**，不再"人填 TOC 印刷页号 → 再脚本校验"两步法——TOC 给的是印刷页号、边界常差几页、前言偏移极易算错（本书实测前 15 页为封面/前言/目录，PDF 页 = 印刷页 + 15），人抄必错。

- 工具：`tools/build_chapter_map.py`（经 `cli.py build-chapter-map` 调用）：
  ```bash
  python tools/build_chapter_map.py <book>/_extract
  # 或 dry-run 预览（只打印报告、不写盘）： python tools/build_chapter_map.py <book>/_extract --no-write
  ```
- 它扫描 `page_*.json`，把每章 `Chapter N` / 附录标题与其 `name_en` 比对（裸标题书走 Mode B 回退），定位真实起始 PDF 页，推断 `end`（下一章起点-1），写回 `chapter_map.json`，并产出 `chapter_map.build_report.md`。
- 🔴 **生成后 agent 判断（强制环节）**：读 `chapter_map.build_report.md`——
  - `CORRECTED` 值（检测值 ≠ 原 TOC 粗略值）→ 已自动写入，确认接受；
  - `UNDTECTED` 章（检测器未能从 OCR 定位起点，如花标题/特殊体例）→ agent **必须**在 `chapter_map.json` 手动补 `start`/`end` 后重跑本工具；
  - 全章 `start`/`end` 非 null 方可进入 write-source。
- 末章 `end` 无下一章可推断时，保留 agent 值或全书末页；属合理推断，非错误。
