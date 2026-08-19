# chapter_map.json（章节映射）

## 目的
全书章节映射，作为后续"某章是否已可写"的**唯一**判定依据（规则1）。

## 生成脚本
- `chapter_map.py`
  （由 extract 的 config 子流程步骤 1 调用，或人工从 OCR 目录页读章名 + PDF 页码填入模板）。
- 类与构造函数：`ChapterMap`（+ `Chapter`）—— `from chapter_map import ChapterMap`；
  `ChapterMap.default()` / `ChapterMap.load(path)` / `ChapterMap(chapters=...).dump(path)`。
- 章节映射脚本：`chapter_map.py`（同目录；亦可由 `cli.py` 的 `write-chapter-map` 子命令调用）。

## 落盘位置
- `<book>/_extract/chapter_map.json`

## 数据结构
```json
{
  "chapters": [
    { "ch": 1, "name": "Measure Theory", "start": 1, "end": 47 },
    { "ch": 2, "name": "Integration",   "start": 48, "end": 103 }
  ]
}
```
- `ch`：章号（整数）。
- `name`：章名。
- `start` / `end`：**PDF 文件页码**（1-based，与 `page_%03d.json` 文件名序号一致；即 `scan_skeleton.scan` 直接 `range(start, end+1)` 读取的页），**不是**原书印刷页码。

## 关键规则（🔴）
- **规则1 — config 子流程统一生成、且只建一次**：chapter_map 在 extract 的 **config 子流程（MM Repair 完成后）** 一次性生成（见 `../../flows/extract/config_setting/config_setting.md` 步骤 1），不在提取轮询期间早建；全书 `chapter_map` 只生成一份，后续不重复生成（除非用户明确要改章节划分）。
- 判定"某章可写"的硬标准：`info.end <= current_max_page`（该章末页已落盘）。
- 🔴 **chapter_map 一律以 PDF 页号存储，禁止存印刷页号**：`scan_skeleton` / `build_structure` 直接拿 `start`/`end` 当 `page_%03d.json` 序号去读，存印刷页号会导致整章错 15 个 PDF 页（本书实测前 15 页为封面/前言/目录，PDF 页 = 印刷页 + 15，双锚点确认）。**若从 TOC 读到的章节边界是印刷页号，必须加上前页偏移换算成 PDF 页号后再写入**（`_meta.pdf_offset` 仅作人读参考，但 `start`/`end` 本身必须是 PDF 页号）。

## 详细流程
- 子流程文档：`../../flows/extract/config_setting/config_setting.md`（步骤 1）
