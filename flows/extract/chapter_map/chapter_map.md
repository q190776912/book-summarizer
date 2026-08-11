# Sub-flow: extract / chapter_map（建章节映射 / 规则1）

> 统一模板：目的 / 触发 / 前置 / 步骤 / 本阶段规则 / 出口 / 相关代码 / 子流程

## 目的
从 PDF 目录页（TOC）读取每章的**章名**与**书页码起止**，生成 `_extract/chapter_map.json`，作为后续"某章是否已可写"的唯一判定依据。

## 触发
- 由父流程 `extract` 轮询循环调用：`current_max_page >= 5` 且 `chapter_map_ready == False` 时。

## 前置
- 提取已落盘至少 5 页（目录页通常在最前）。
- 父流程 `extract` 轮询循环正在运行。

## 步骤（有序）
1. 取 `_extract/page_*.json` 中目录页（通常 `page_001~005` 之内）。
2. 用 `../../../data/chapter_map/chapter_map.py` 生成模板（数据结构见 [data/chapter_map/chapter_map.md](../../../data/chapter_map/chapter_map.md)），或人工从 OCR 文本读章名 + 书页码填入：
   ```json
   { "chapters": [ {"ch": 1, "name": "Measure Theory", "start": 1, "end": 47}, ... ] }
   ```
3. 写 `_extract/chapter_map.json`，置 `chapter_map_ready = True`。

## 本阶段规则（🔴 内联）
- **规则1 — 尽早建、且只建一次**：目录页一提取到（`current_max_page >= 5`）立即建；**全书的 chapter_map 只生成一份**，后续轮询不再重建（除非用户明确要改章节划分）。
- 判定"某章可写"的硬标准：`info.end <= current_max_page`（该章末页已落盘）。
- 书页码是**原书印刷页码**，不是 PDF 文件页码；若原书页码与 PDF 页偏移，需在 chapter_map 中正确映射。

## 出口条件
- 出口：`_extract/chapter_map.json` 存在且 `chapter_map_ready = True`。

## 相关代码（路径相对 skill 根目录）
- `../../../data/chapter_map/chapter_map.py`：chapter_map 模板工具。

## 子流程
无。
