# Flow: figure_detection（图检测 + 分配 / extract 子流程）

> 统一模板：目的 / 前置 / 步骤 / 本阶段规则 / 出口 / 相关代码 / 子流程

## 目的
对全书做一次图检测（DocLayout-YOLO 版面检测）与图分配（语义命名 `图X.X.X`），产出 `figure_detect.json` + `figure_index.json`，供写章阶段的图嵌入消费。本子流程是 extract 阶段里**唯一读 `figure.labels`** 的环节，图号前缀由该字段决定，故执行前须确保 `figure.labels` 已配置。
## 前置
- 全部 `page_*.json` 已落盘（文本提取阶段出口）。
- `chapter_map.json` 就绪（检测阶段需把每页归到章节；分配阶段按章命名）。
- `_extract/verify_config.json` 已存在且（若书图号前缀非默认）含 `figure.labels`。**未配置则图号前缀退化为默认 `["图","Figure","Fig"]`**，自定义前缀书（Scheme / Illustration 等）会漏识 caption。

## 步骤（有序）
1. **检测（detection）**：`python extract_figures.py <pdf> --out <extract> --book`
   - 用 DocLayout-YOLO（`doclayout_yolo_ft.pt`）在全书每页框出 `figure`(class 3) / `figure_caption`(class 4)，裁图存 `figure/det_pNNN_KK.png`（**位置名，无图号**），写出 `figure_detect.json`。
   - 图号前缀由 `verify_config.json` 的 `figure.labels` 决定（`lib.figure_io.load_fig_labels`）；**带序标（图 X.X / Fig X.X / Scheme X.X 等）的图，会把其下方 caption（标号 + 说明）一并裁入同一张图；无标号 caption 的图只裁图本身**（"有标号才一起扣、没标号就算"）。
   - 公式 / 文本框**不裁**（extract 文本阶段已用 MFD + PaddleOCR 覆盖，模型不同）。
2. **分配（assignment）**：`python assign_figures.py <pdf> --out <extract> --book`
   - 读 `figure_detect.json` + 章内 OCR 图注，给每张检测到的图赋语义号：优先从 caption 文本提 `图X.X.X`，否则同页最近 `图X.X.X` 位置匹配；匹配到的重命名为 `figure/chNN_figX.X.X.png`，未匹配为 `figure/chNN_unnamed_K.png`，写出 `figure_index.json` + `figure_index.md`。

## 本阶段规则（🔴 内联）
- **规则1 — `figure.labels` 必须显式配置（最高优先级）**：图号前缀由 `figure.labels` 决定，因此该字段**强制显式**——自定义前缀→`labels` 非空、无图序标→`labels` 显式空数组 `[]`，二者皆不可"字段缺失"。`figure.labels` 决定图号前缀识别：缺配置则退化默认前缀，自定义前缀书的 caption 合并会漏；显式空数组 `[]` 则表示"本书确无图号"，下游返回零匹配、不会误匹配默认 `Figure`/`图` 等词。
- **规则2 — 图与公式模型不同**：检测用 DocLayout-YOLO（只取 `figure` 类），公式框由 extract 文本阶段的 MFD 给、文本由 PaddleOCR 给；三者分工不重叠。
- **规则3 — 带序标才合并 caption**：仅当配对 caption 含序标（`parse_fig_label` 命中 `figure.labels`）才把图 + caption 裁成一张；否则只裁图。若配置为显式空数组 `[]`（本书无图序标），`parse_fig_label` 恒返回 `None`，所有图都只裁图本身，不会误把正文里的 `Figure`/`图` 当图号合并。
- **规则4 — 检测/分配异常不阻断**：任一脚本抛异常仅记日志，不影响已落盘产物；未命名图（`label==null`）仍由写章阶段以"图(未标号)"嵌入，不视为 FAIL。
- **跳过图检测**：若本书确实无图，直接跳过本子流程即可，`figure_index.json` 保持缺失/空，写章阶段按无图处理（无需开关）。

## 出口条件
- 出口：`figure_detect.json` 与 `figure_index.json` 均存在，且 `figure_index.json` 涵盖全部已建章节（或本书无图而跳过）。

## 相关代码（路径相对 skill 根目录）
- `flows/script/figure/extract_figures`（`run_full_book` / `run_chapter` / `detect_pages_range` / `parse_fig_label`）：DocLayout-YOLO 检测 + 裁图 + caption 合并。`run_full_book` 为全本书检测入口（被本子流程调用）。
- `flows/script/figure/assign_figures`（`run_book` / `run_chapter` / `gather_refs`）：章内 OCR 图注 → 语义号分配。`run_book` 为全本书分配入口（被本子流程调用）。
- `../../../data/figure_detect/figure_detect.py`（`FigureDetect`）：`figure_detect.json` 数据结构。
- `../../../data/figure_index/figure_index.py`：`figure_index.json` 数据结构。
- `../../../lib/figure_io.py`（`load_fig_labels` / `build_fig_label_re` / `FIGURE_LABELS_DEFAULT`）：图号前缀的跨流程唯一读取点。

## 子流程
- 无独立子流程。图流水线全部规则（手动补图、E/F 校验衔接、嵌入后处理等）的 SSOT 见 [`../../write-source/figures/ref/figure_pipeline.md`](../../write-source/figures/ref/figure_pipeline.md)；配置字段见 [`../../../config/verify_config/verify_config.md`](../../../config/verify_config/verify_config.md)。
