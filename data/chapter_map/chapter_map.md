# chapter_map.json（章节映射）

## 目的
全书章节映射，作为后续"某章是否已可写"的**唯一**判定依据（规则1）。

## 生成脚本
- `chapter_map.py`
  （由 extract 父流程轮询调用，或人工从 OCR 目录页读章名 + 书页码填入模板）。
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
- `start` / `end`：**原书印刷页码**起止（非 PDF 文件页码）。

## 关键规则（🔴）
- **规则1 — 尽早建、且只建一次**：目录页一提取到（`current_max_page >= 5`）立即建；
  全书 `chapter_map` 只生成一份，后续轮询不再重建（除非用户明确要改章节划分）。
- 判定"某章可写"的硬标准：`info.end <= current_max_page`（该章末页已落盘）。
- 书页码与原书印刷一致；若原书页码与 PDF 页偏移，须在 `chapter_map` 中正确映射。

## 详细流程
- 子流程文档：`../../flows/extract/chapter_map/chapter_map.md`
