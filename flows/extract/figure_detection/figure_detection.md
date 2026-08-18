# Flow: figure_detection（图检测 + 分配 / extract 子流程）

> 统一模板：目的 / 前置 / 步骤 / 本阶段规则 / 出口 / 相关代码 / 子流程

## 目的
对全书做一次图检测（DocLayout-YOLO 版面检测）与图分配（语义命名 `图X.X.X`），产出 `figure_detect.json` + `figure_index.json`，供写章阶段的图嵌入消费。本子流程是 extract 阶段里**唯一读图序标（`ordinal` 的 Figure 组）** 的环节，图号前缀=该组 `name`、段数 components=该组 `type` 经 `ORDINAL_DEPTH` 派生的 `depth`，故执行前须确保 `ordinal` 含 Figure 组（或过渡 `{"figure":{"labels":[]}}` 零匹配标记）。
## 前置
- 全部 `page_*.json` 已落盘（文本提取阶段出口）。
- `chapter_map.json` 就绪（检测阶段需把每页归到章节；分配阶段按章命名）。
- `_extract/verify_config.json` 已存在且（若书图号前缀非默认）`ordinal` 含 Figure 组（`name` 列前缀词、`type` 设段数）。**缺 Figure 组则图号前缀退化为默认 `["图","Figure","Fig"]`**，自定义前缀书（Scheme / Illustration 等）会漏识 caption。

## 步骤（有序）
1. **检测（detection）**：`python extract_figures.py <pdf> --out <extract> --book`
   - 用 DocLayout-YOLO（`doclayout_yolo_ft.pt`）在全书每页框出 `figure`(class 3) / `figure_caption`(class 4)，裁图存 `figure/det_pNNN_KK.png`（**位置名，无图号**），写出 `figure_detect.json`。
   - 图号前缀由 `verify_config.json` 的 `ordinal` Figure 组决定（`lib.figure_io.load_fig_labels` 从 Figure 组 `name` 读取）；**带序标（图 X.X / Fig X.X / Scheme X.X 等）的图，会把其下方 caption（标号 + 说明）一并裁入同一张图；无标号 caption 的图只裁图本身**（"有标号才一起扣、没标号就算"）。
   - 公式 / 文本框**不裁**（extract 文本阶段已用 MFD + PaddleOCR 覆盖，模型不同）。
2. **分配（assignment）**：`python assign_figures.py <pdf> --out <extract> --book`
   - 读 `figure_detect.json` + 章内 OCR 图注，给每张检测到的图赋语义号：优先从 caption 文本提 `图X.X.X`，否则同页最近 `图X.X.X` 位置匹配；匹配到的重命名为 `figure/chNN_figX.X.X.png`，未匹配为 `figure/chNN_unnamed_K.png`，写出 `figure_index.json` + `figure_index.md`。

## 本阶段规则（🔴 内联）
- **规则1 — Figure 组必须显式配置（最高优先级）**：图号前缀由 `ordinal` 的 Figure 组 `name` 决定，因此该组**强制显式**——自定义前缀→Figure 组 `name` 非空、无图序标→不放 Figure 组（回落默认）或显式 `{"figure":{"labels":[]}}` 零匹配标记，二者皆不可"字段缺失而静默回落默认"。Figure 组 `name` 决定图号前缀识别：缺组则退化默认前缀，自定义前缀书的 caption 合并会漏；显式空数组 `[]` 标记则表示"本书确无图号"，下游返回零匹配、不会误匹配默认 `Figure`/`图` 等词。
- **规则2 — 图与公式模型不同**：检测用 DocLayout-YOLO（只取 `figure` 类），公式框由 extract 文本阶段的 MFD 给、文本由 PaddleOCR 给；三者分工不重叠。
- **规则3 — 带序标才合并 caption**：仅当配对 caption 含序标（`parse_fig_label` 命中 Figure 组 `name`）才把图 + caption 裁成一张；否则只裁图。若配置为显式空数组 `[]`（`{"figure":{"labels":[]}}` 过渡标记，本书无图序标），`parse_fig_label` 恒返回 `None`，所有图都只裁图本身，不会误把正文里的 `Figure`/`图` 当图号合并。
- **规则4 — 检测/分配异常不阻断**：任一脚本抛异常仅记日志，不影响已落盘产物；未命名图（`label==null`）仍由写章阶段以"图(未标号)"嵌入，不视为 FAIL。
- **跳过图检测**：若本书确实无图，直接跳过本子流程即可，`figure_index.json` 保持缺失/空，写章阶段按无图处理（无需开关）。
- **🔴 检测→分配只能顺序跑一次（det_ 裁图被消耗）**：步骤1 检测把裁图写成 `figure/det_pNNN_KK.png`，步骤2 分配会把这些 `det_*` 裁图**重命名**为 `figure/chNN_figX.X.X.png`。因此 `assign_figures.py` 每跑一次就消耗掉一批 `det_*` 源裁图；若想**重跑分配**（例如改了 Figure 组 `name`/`type`（段数 components）后重新命名），**必须先重跑检测**（重新生成 `det_*` 与 `figure_detect.json`）再分配一次，否则分配会因找不到 `det_*` 源文件而落空、产生"条目存在但裁图缺失"的不一致状态。调试时反复跑分配而不重检测，正是这种不一致的根源。

## 出口条件
- 出口：`figure_detect.json` 与 `figure_index.json` 均存在，且 `figure_index.json` 涵盖全部已建章节（或本书无图而跳过）。

## 环境前提
- 权重 `doclayout_yolo_ft.pt` 来自 **ModelScope `opendatalab/pdf-extract-kit-1.0`**
- 加载器必须用 **`doclayout_yolo.YOLOv10`**，不能用 `ultralytics.YOLO`（后者在 `predict()` 时会自动 fuse 把 `Conv.bn` 删掉，触发 doclayout_yolo 0.0.4 的 `'Conv' object has no attribute 'bn'`）
- `cv2`（opencv-python）用于读取；Windows 上 `cv2.imread` 读不了含中文路径的文件，verify 的 figure 层(E)（`../../../verify/script/verify_chapter.py`）用 `np.fromfile`+`cv2.imdecode` 读；**`extract_figures.py` 已改用 PIL 保存裁剪图**，避免中文路径静默失败

## 已知边界
- 跨页大图被 DocLayout-YOLO 各检出一个框，目前**不合并**，会得到两个文件名
- 只取 `figure`(class 3) 裁，**不裁表格/公式块**（模型另有 `table`(5)/`isolate_formula`(8) 类，脚本忽略）
- 图注序标识别**跟随本书体例**：前缀词由 `verify_config.json` 的 `ordinal` Figure 组 `name` 决定（默认 `["图","Figure","Fig"]`，可扩成 `Scheme` / `Illustration` 等），不再写死中英语词表；caption 无图号且同页邻近无该书图号时命名为 `chNN_unnamed_K.png`
- `--conf` 默认 0.25；觉得误检多就调高，漏检多就调低
- **Windows + 非 ASCII 路径的静默失败**：OpenCV 的 `cv2.imwrite` 在 Windows 上对含中文等非 ASCII 字符的路径会**静默返回 False**（已知 OpenCV 缺陷），导致检测阶段只生成 `figure_detect.json` / `figure_index.json` 元数据但 `figure/` 下没有 PNG。`extract_figures.py` 已改为 PIL 保存，回跑即修复；若 `_extract/` 已是历史遗留数据没有 PNG，可写 `regen_figures.py` 用 fitz 渲染 + PIL 裁剪，按 `figure_index.json` 的 `page+bbox+file` 重建

## 相关代码（路径相对 skill 根目录）
- `flows/script/extract_figures`（`run_full_book` / `run_chapter` / `detect_pages_range` / `parse_fig_label`）：DocLayout-YOLO 检测 + 裁图 + caption 合并。`run_full_book` 为全本书检测入口（被本子流程调用）。
- `flows/script/assign_figures`（`run_book` / `run_chapter` / `gather_refs`）：章内 OCR 图注 → 语义号分配。`run_book` 为全本书分配入口（被本子流程调用）。
- `../../../data/figure_detect/figure_detect.py`（`FigureDetect`）：`figure_detect.json` 数据结构。
- `../../../data/figure_index/figure_index.py`：`figure_index.json` 数据结构。
- `../../../lib/figure_io.py`（`load_fig_labels` / `load_fig_components` / `build_fig_label_re` / `FIGURE_LABELS_DEFAULT`）：图号前缀与段数（components = Figure 组 `depth`）的跨流程唯一读取点，现从 `ordinal` 的 Figure 组派生。
