# 提取流水线（extract / pipeline）

> 本文档是一份独立的书籍**文本**提取流程说明：描述 `extract_pipeline.py` 如何将归位后的书籍 PDF 批量转为结构化 `page_*.json`（公式 LaTeX + 正文文本），支持断点续跑。**图检测 + 分配已拆为独立子流程 `figure_detection`（见 `../figure_detection/figure_detection.md`），在 config 子流程之后单独跑**，不在本文档内。无需参考其他文档即可阅读。

## 目的
将书籍 PDF 批量提取为结构化 `page_*.json`（公式 LaTeX + 正文文本）；支持断点续跑。本流程只产出"原料"，不做任何校验（OCR 噪声修复等由 MM Repair 等后续阶段处理）。**图检测不在本流程内**——文本提取出口后，由父流程 `extract` 接续：先跑 **config 子流程**（生成 `verify_config.json`）→ 再跑 **figure_detection 子流程**（图检测 + 分配）。

## 运行方式
直接运行主程序：
```bash
python extract_pipeline.py <pdf> [--start N] [--end N] [--force] [--deskew auto|off|force]
```
- `<pdf>`：书籍 PDF 路径，约定为 `<书名>/<书名>.pdf`；`_extract` 输出目录自动建在其同级。
- `--start N` / `--end N`：提取范围。`--end` 省略时取 PDF 自动识别的总页数（全本）；`--end` 单独给出则开始页默认为 1；两者都给则为精确区间。脚本启动时用 PyMuPDF（`fitz.open(pdf).page_count`）识别总页。
- `--force`：从头重跑，忽略已落盘页。
- `--deskew auto|off|force`：扫描页纠斜（默认 auto）。
- 必须在 `pdfextract` conda 环境运行（含 torch / fitz / paddle / PDF-Extract-Kit）。

## 前置
- PDF 置于 `<书名>/<书名>.pdf`（`_extract` 输出目录将建在其旁）。
- `pdfextract` conda 环境可用，且 `D:\study\model\PDF-Extract-Kit` 权重就位（`extract_book.py` 内硬编码 MFD / MFR / OCR 权重路径）。
- 提取范围由 `--start` / `--end` 决定（见上「运行方式」）。

## 步骤（有序）

**Step 1 — 目录与日志准备**
- `EXTRACT_DIR = <pdf_parent>/_extract`，自动 `mkdir -p`。
- `LOG_FILE = <EXTRACT_DIR>/extract_pipeline.log`，所有日志 append 写入（同时 `print`）。
- 每批额外写 `<EXTRACT_DIR>/batch_{start}-{end}.log`，便于单批排查。

**Step 2 — 断点续跑判定（缺口优先，非最大页码+1）**
- 默认：扫描已落盘 `page_*.json` 得到 `existing_pages`，**从 1 起数第一个不连续缺口**作为续跑起点（`find_first_gap`），而非"最大页码+1"。例：已存在 1–10 与 15–20，则续跑点为 11（不是 21）。
- 把所有缺失页拆成连续区间 `missing_ranges`；提取阶段**循环遍历各缺失区间、逐个补提，直至覆盖到最后一页 END**（已存在页绝不重提）。例：1–10、15–20 已落盘，END=20 → 仅补 `[11,14]`，补完即到末页。
- 结束页判定同样遵循缺口逻辑：若 1..END 内已无缺口（`find_first_gap > END`）→ 跳过提取阶段，直接进入 figure 收尾（Step 5 / Step 6）。

**Step 3 — 模型单次初始化（跨批复用）**
- `init_models()` 一次性加载 MFD + MFR + OCR（GPU fp16，CUDA 可用时）。
- 返回的 `tasks / mfr_model / mfr_proc / device` 在整个分批循环里复用，避免每批重载。
- 日志打印 `INIT OK | device=…`；CUDA 下额外打印初始 VRAM 占用。

**Step 4 — 按缺失区间分批提取（BATCH_SIZE = 50，已存在页不动）**
- 遍历 `missing` 中每个连续缺失区间 `(r_start, r_end)`，区间内再按 `BATCH_SIZE` 切块，逐一 `process_batch(...)`；区间之间不重提已落盘页（缺口续跑语义）。
- `process_batch` 三阶段：
  - **Phase 1 渲染 + deskew + MFD + OCR**：逐页渲染（DPI=200，`deskew_render_page` 按需纠斜）→ MFD 检测公式 bbox → `ocr.predict_image` 取正文 `text[]`；阶段结束即从显存卸载 MFD+OCR，释放 VRAM 给 Phase 2。
  - **Phase 2 MFR（公式识别）**：把本批所有公式裁图按面积分 small / medium / large 三层，各固定 32/批送入 MFR；低 VRAM（<1GB）时自动把批减半；OOM 时先逐张重试、再自动回退 CPU 并标记 `[MFR_ERR …]`，不中断整批。
  - **Phase 3 写盘**：每页组装
    `{"page", "formulas":[{"bbox","cls","conf","latex"}], "text":[{"poly","text","score"}], "deskew":{"angle_deg","mode"}}`，
    用 `PageJson.dump` 写 `page_{pno:03d}.json`（独立落盘）。
- 批次失败处理：单批抛异常 → 写 `batch_*.log` 的 TRACEBACK、清显存、`gc.collect()`，然后 `break` 停止整个循环（一批失败即停，不继续后续批）。

**Step 5 —（图检测已拆出，不在本流程）**
- 图检测 + 分配**不在本流程内**。文本提取（Step 1–4）全部完成后，由父流程 `extract` 接续：先跑 **config 子流程**（生成 `verify_config.json`，含 `figure.labels`）→ 再跑 **figure_detection 子流程**（见 [`../figure_detection/figure_detection.md`](../figure_detection/figure_detection.md)）做全本书 DocLayout-YOLO 检测 + `图X.X.X` 分配。这样图检测**必定读到本书图号前缀**，而非默认兜底——顺序由父流程保证，本脚本不负责图。

## 本阶段规则
- **规则1 — 失败即停**：任一批异常只记日志并 `break`，不继续下一批；需人工看 `batch_*.log` 定位（常见：CUDA OOM、PDF 损坏页）。后续可依赖断点续跑从失败批之后继续补提。
- **规则2 — 显存安全**：MFR 分层固定 32/批；VRAM<1GB 自动减半；OOM 自动降为逐张 / CPU。不要为提速盲目调大 `PEK_MFR_BS` / `PEK_OCR_BS` 环境变量。
- **规则3 — 幂等 / 缺口安全**：`--force` 从头重跑，覆盖请求的整段（从 `--start` 起所有页）；非 `--force` 续跑**只补 1..END 内缺失的区间**（含中间缺口），已存在页不动（安全可重复）。

## 出口条件
- 出口：1..END 内所有页 `page_*.json` 均已落盘（**无缺口**），`extract_pipeline.log` 末尾 `Pipeline finished.`。图产物（`figure_index.json` 等）由 figure_detection 子流程在其后生成。

## 相关代码（路径相对 skill 根目录）
- `flows/extract/pipeline/script/pipeline/extract_pipeline`：主程序（断点续跑 + 分批提取，文本 only）。
- `flows/extract/pipeline/script/pipeline/extract_book`：底层引擎（`init_models` + `process_batch` 三阶段 MFD→MFR→OCR）。Phase 1 的 MFD 用 `yolo_v8_ft.pt`（数学公式检测，只出公式框），文本另由 PaddleOCR 识别；权重路径硬编码于 `D:\study\model\PDF-Extract-Kit`。
- `../../../data/page_json/page_json.py`：`page_*.json` 数据结构（`PageJson`）。
- 图检测相关代码（DocLayout-YOLO 检测 / `图X.X.X` 分配）见 figure_detection 子流程文档 [`../figure_detection/figure_detection.md`](../figure_detection/figure_detection.md) 的「相关代码」。

## 产物去向（上下文说明，非阅读依赖）
- `page_*.json` 作为原料供 MM Repair（修 OCR 噪声）、config 子流程（探测编号形态）与写章阶段消费。
- 图产物（`figure_detect.json` / `figure_index.json` / `figure/`）由 figure_detection 子流程在 config 之后生成，供写章阶段的图嵌入 / 引用消费。
