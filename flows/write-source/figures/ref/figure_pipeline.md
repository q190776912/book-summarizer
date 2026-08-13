> 🔴 **本文件是该领域规则的唯一权威详细说明（SSOT）**。`SKILL.md` 与代码注释只引用此处、不重复描述；新增/修改该领域规则只改本文件。

# 图片流水线（Figure Pipeline）

> 本文档是 `book-summarizer` skill 的图片提取参考。工作流步骤见 `SKILL.md`，格式规则见 `../../../../docs/writing-rules.md`，校验关卡见 `../../../../verify/verify.md`。

---

## 目录

- [架构概览](#架构概览)
- [阶段 1：检测（Detection）](#阶段-1检测detection)
- [阶段 2：命名（Assignment）](#阶段-2命名assignment)
- [工作流衔接（figure_detection 子流程）](#工作流衔接figure_detection-子流程)
- [手动补图](#手动补图)
- [环境前提](#环境前提)
- [已知边界](#已知边界)
- [命令速查](#命令速查)

---

## 架构概览

图片提取分成两段：**阶段 1 检测（detection）** 与 **阶段 2 命名（assignment）**。这两段**不再内联在文本提取流水线里**，而是由独立的 `figure_detection` 子流程统一执行——在 **`verify_config.json`（含 `figure.labels`）配置就绪**、全书文本落盘之后跑一次全本（SSOT 见 [`../../../extract/figure_detection/figure_detection.md`](../../../extract/figure_detection/figure_detection.md)）。

- **阶段 1 检测（detection，`flows/script/extract_figures`）**：`run_full_book()` 对全书每页做 DocLayout-YOLO 检测，裁图存 `figure/det_p{PAGE:03d}_{IDX:02d}.png`（**位置名，无图号**，不带"图6.1.1"这种语义名），写出 `figure_detect.json`。**只有带序标（`图 X.X` / `Fig X.X` / `Scheme X.X` 等）的图，才把其下方 caption（标号 + 说明）一并裁入同一张图**；无标号 caption 的图只裁图本身。
- **阶段 2 命名（assignment，`flows/script/assign_figures`）**：`run_book()` 读 `figure_detect.json` + 章内 OCR 图注，根据 **bbox 位置 + OCR 图注文本** 判断每张检测到的图对应哪个"图 X.X.X"，重命名为 `figure/chNN_figX.X.X.png`（匹配）或 `chNN_unnamed_K.png`（未匹配），写出 `figure_index.json`（`../../../../verify/script/verify_chapter.py` 的 figure 层(E)消费）。

**为什么拆出去**：图检测是 extract 阶段里**唯一读 `figure.labels`** 的环节。若在内联执行时 `figure.labels` 尚未配置，自定义前缀书（Scheme / Illustration 等）的 caption 会被漏识、退化成默认 `["图","Figure","Fig"]`。拆成独立子流程、待配置就绪后运行，从源头保证 `figure.labels` 先就位。本书确实无图时，直接跳过该子流程即可（`figure_index.json` 保持缺失，无需开关）。

**背景**：PDF-Extract-Kit 的 `layout_detection` 任务**只定位** figure 的边界框（画可视化叠加图），并不把图裁成单独文件。所以"把图裁下来存 `figure/`"靠 `extract_figures.py` 实现——用 PDF-Extract-Kit 的 DocLayout-YOLO 权重给出 figure 框，再用同一 200-DPI 渲染页把框内区域扣出来存 PNG。

---

## 阶段 1：检测（Detection）

### 入口

| 模式 | 函数 | 说明 |
|------|------|------|
| 全本（默认工作流） | `run_full_book()` | 检测全部页面，写入全局 `figure_detect.json`（覆盖重写）；被 `figure_detection` 子流程调用 |
| 区间重跑（修漏检） | `detect_pages_range()` | 检测指定页码范围，**追加合并**到现有 `figure_detect.json`，返回 `(model, new_entries)`；**非默认工作流**，仅用于修漏检 |
| 单章重跑（修漏检） | `run_chapter()` | 重跑某章页面，合并入现有 `figure_detect.json`（幂等） |

### 产物（落到 `_extract\`）

- 检测：`figure/det_p{PAGE}_{IDX}.png`（位置名，无图号）
- `figure_detect.json`：每条约 `chapter`/`page`/`det_id`/`bbox`/`conf`/`file`/`cap_text`/`source`，`label` 为 null

### CLI

```bash
# 全本
"<python>" "C:/Users/ye190/.workbuddy/skills/book-summarizer/flows/script/extract_figures" \
  "<pdf>" --out "<extract>" --book

# 单章重跑
"<python>" "C:/Users/ye190/.workbuddy/skills/book-summarizer/flows/script/extract_figures" \
  "<pdf>" --out "<extract>" --ch N --start S --end E
```

---

## 阶段 2：命名（Assignment）

读取 `figure_detect.json` + 章内 OCR 图注，给每张检测到的图赋予图号：

1. 优先从该图 caption 文本里的"图 X.X.X"提取
2. 否则用同页最近的"图 X.X.X"位置匹配（垂直距离优先）

匹配到的重命名为 `figure/chNN_figX.X.X.png`，匹配不到的命名为 `figure/chNN_unnamed_K.png`，写出 `figure_index.json`。

### 入口

| 模式 | 函数 | 说明 |
|------|------|------|
| 全本 | `run_book()` | 给 `figure_detect.json` 中所有章做 assignment |
| 单章 | `run_chapter()` | 给指定章做 assignment，合并到 `figure_index.json`（幂等，保留 manual 条目） |

### 产物

- `figure/chNN_figX.X.X.png`（匹配到图号）
- `figure/chNN_unnamed_K.png`（未匹配）
- `figure_index.json`：每条约 `chapter`/`page`/`fig_idx`/`label`/`bbox`/`conf`/`file`/`caption`/`source`
- `figure_index.md`：便于粘贴的 `![](...)` 列表（数据结构权威说明见 [data/figure_index/figure_index.md](../../../../data/figure_index/figure_index.md)）

### CLI

```bash
# 全本
"<python>" "C:/Users/ye190/.workbuddy/skills/book-summarizer/flows/script/assign_figures" \
  "<pdf>" --out "<extract>" --book

# 单章
"<python>" "C:/Users/ye190/.workbuddy/skills/book-summarizer/flows/script/assign_figures" \
  "<pdf>" --out "<extract>" --ch N --start S --end E
```

---

## 工作流衔接（figure_detection 子流程）

图检测 / 分配**不再是文本提取流水线的内联增量步骤**，而是 extract 阶段里待 `figure.labels` 配置就绪后运行的独立子流程 `figure_detection`（SSOT 见 [`../../../extract/figure_detection/figure_detection.md`](../../../extract/figure_detection/figure_detection.md)）。执行衔接：

1. **文本提取（pipeline 子流程）**：`extract_pipeline.py` 产出 `page_*.json`（公式 LaTeX + 正文），**不做任何图检测**。
2. **配置（`verify_config.json`）**：依据 `page_*.json` 生成，其中 `figure.labels` 决定图号前缀；该字段须先于图检测就绪。
3. **figure_detection 子流程**：对全书做一次 `run_full_book()`（检测，覆盖写 `figure_detect.json`）+ `run_book()`（分配，写 `figure_index.json`）。`figure.labels` 已就位，caption 合并不漏识。

**为什么需要配置先就绪（关键）**：图检测是 extract 阶段唯一读 `figure.labels` 的环节。若 `figure.labels` 尚未配置，自定义前缀书的 caption 退化成默认 `["图","Figure","Fig"]`。拆成独立子流程、待配置就绪后运行，从源头解决。

**断点 / 重跑（修漏检）**：默认是"全书一次跑完"。若某章 E 层报"图 X.X.X missing"（真漏检），用区间 / 单章重跑即可，不必重跑全书：
- 重跑检测区间：`detect_pages_range(pdf, out, start, end)`（追加合并，保留其他页结果）
- 重跑单章检测：`extract_figures.run_chapter(...)`
- 重跑单章分配：`assign_figures.run_chapter(...)`（保留 manual 条目）

### 与 figure 层(E) 校验的衔接

`figure_index.json` 落地后 `../../../../verify/script/verify_chapter.py` 启用 **figure 层(E)：图片完整性 + 图片有效性**：

- **E 层 MISSING（真漏检）**：章内 OCR 引用了"图 X.X.X"但 `figure_index.json` 无对应条目 → 该图**根本没被检测到** → 去对应页**重新识别**（降 `--conf` 重跑 `extract_figures.py --ch N` 或手动补图）
- **未命名（已检测，无图号）**：`figure_index.json` 中有该图条目但 `label==null` → 它**被找到了**，只是 caption 没被识别成"图 X.X.X" → **不阻断**
- **figure 层(E) 有效性**：裁剪图缺失/无法解码/单边<20px → 阻断；近空白误检 → 仅警告
- 两层前提：`figure_index.json` 存在且含本章 `chapter` 条目；否则 SKIP

---

## 手动补图

当 DocLayout-YOLO 漏判某图（典型：旋转 90° 的全页图、文字密集分类树被当 `plain text`），E 层会报"图 X.X.X missing"。**不要**靠改 `--conf` 或换模型救，**用 `figure_manual_chN.json` 声明 + `../../../../config/figure_manual_chN/apply_manual_figures.py` 执行**：

1. **定位图在哪页**。翻原文 / `figure/inspect_tool.py page <raw_dir> <page>` 找"图 X.X.X"被引用的页；用 fitz 渲染到 PNG 肉眼确认。
2. **读 bbox**。以**200-DPI 渲染图**的像素坐标为准 `[x0, y0, x1, y1]`。若 PDF 把图旋转 90° 存放，设 `rotate: 90`。
3. **写 `_extract/figure_manual_chN.json`**：其字段（`page` / `bbox` / `rotate` / `caption`）、JSON 示例与执行方式见公用配置文档 [`../../../../config/figure_manual_chN/figure_manual_chN.md`](../../../../config/figure_manual_chN/figure_manual_chN.md)。
4. **执行**：`python config/figure_manual_chN/apply_manual_figures.py <_extract> <ch> --pdf <pdf_path>`
5. **重验**：`../../../../verify/script/verify_chapter.py` → E 层看到图号已提供 → PASS。

手动图在**每次 assignment 重跑时都会被保留**（`assign_figures.py` 不删 `source="manual"` 的条目/文件）。

---

## 环境前提

- 权重 `doclayout_yolo_ft.pt` 来自 **ModelScope `opendatalab/pdf-extract-kit-1.0`**
- 加载器必须用 **`doclayout_yolo.YOLOv10`**，不能用 `ultralytics.YOLO`（后者在 `predict()` 时会自动 fuse 把 `Conv.bn` 删掉，触发 doclayout_yolo 0.0.4 的 `'Conv' object has no attribute 'bn'`）
- `cv2`（opencv-python）用于读取；Windows 上 `cv2.imread` 读不了含中文路径的文件，`../../../../verify/script/verify_chapter.py` 的 figure 层(E)用 `np.fromfile`+`cv2.imdecode` 读；**`extract_figures.py` 已改用 PIL 保存裁剪图**（见下方『已知边界』），避免中文路径静默失败

---

## 嵌入后处理

`../../../script/embed_figures.py`（Step 3.5）自动完成缩进进块、连续性修复、flex 包装。

### 自动锚点匹配的局限

`../../../script/embed_figures.py` 用启发式匹配图注（caption）与条目标签（`**定义X.X**`, `**定理X.X**` 等）。当 OCR 图注文本噪声大、或图无文字标注（如图1.1 Venn 图只有 "图1.1" 而无 "定义1.4" 字样）时，匹配会失败，脚本输出 `no item ref`。

**对此情况，必须创建 `_extract/figure_embed_overrides.json` 手动声明锚点**。其字段（`anchors` / `is_proof`）、JSON 示例与自动产出脚本见 [`../../../../data/figure_embed_overrides/figure_embed_overrides.md`](../../../../data/figure_embed_overrides/figure_embed_overrides.md)。

- 此文件在中文教材（Venn 图、拓扑示意图等无文字图注的图）中几乎是必选项。

### 嵌入后 C 层 "missing blank line after `</div>`"

顶层（非块引用内）图片的 `</div>` 后缺空行会导致 Markdown 解析器吞内容，C 层报错。详见 `../../../../docs/writing-rules.md#已知遗留问题顶层-div-后缺空行`。

---

## 已知边界

- 跨页大图被 DocLayout-YOLO 各检出一个框，目前**不合并**，会得到两个文件名
- 只取 `figure`(class 3) 裁，**不裁表格/公式块**（模型另有 `table`(5)/`isolate_formula`(8) 类，脚本忽略）
- 图注序标识别**跟随本书体例**：前缀词由 `_extract/verify_config.json` 的 `figure.labels` 决定（默认 `["图","Figure","Fig"]`，可扩成 `Scheme` / `Illustration` 等），不再写死中英语词表；caption 无图号且同页邻近无该书图号时命名为 `chNN_unnamed_K.png`
- `--conf` 默认 0.25；觉得误检多就调高，漏检多就调低
- **Windows + 非 ASCII 路径的静默失败**：OpenCV 的 `cv2.imwrite` 在 Windows 上对含中文等非 ASCII 字符的路径会**静默返回 False**（已知 OpenCV 缺陷），导致检测阶段只生成 `figure_detect.json` / `figure_index.json` 元数据但 `figure/` 下没有 PNG。`../../../script/extract_figures.py` 已改为 PIL 保存，回跑即修复；若 `_extract/` 已是历史遗留数据没有 PNG，可写 `regen_figures.py` 用 fitz 渲染 + PIL 裁剪，按 `figure_index.json` 的 `page+bbox+file` 重建

---

## 命令速查

```bash
# 全本 detection（pdf_path 可省略，自动从 --out 上级目录发现 PDF）
"<python>" "C:/Users/ye190/.workbuddy/skills/book-summarizer/flows/script/extract_figures" --out "<extract>" --book
"<python>" "C:/Users/ye190/.workbuddy/skills/book-summarizer/flows/script/extract_figures" "<pdf>" --out "<extract>" --book

# 单章重跑 detection
"<python>" "C:/Users/ye190/.workbuddy/skills/book-summarizer/flows/script/extract_figures" --out "<extract>" --ch N --start S --end E
"<python>" "C:/Users/ye190/.workbuddy/skills/book-summarizer/flows/script/extract_figures" "<pdf>" --out "<extract>" --ch N --start S --end E

# 全本 assignment（pdf_path 可省略，自动发现；实际不读 PDF，仅作对称参数）
"<python>" "C:/Users/ye190/.workbuddy/skills/book-summarizer/flows/script/assign_figures" --out "<extract>" --book
"<python>" "C:/Users/ye190/.workbuddy/skills/book-summarizer/flows/script/assign_figures" "<pdf>" --out "<extract>" --book

# 单章重跑 assignment
"<python>" "C:/Users/ye190/.workbuddy/skills/book-summarizer/flows/script/assign_figures" --out "<extract>" --ch N --start S --end E
"<python>" "C:/Users/ye190/.workbuddy/skills/book-summarizer/flows/script/assign_figures" "<pdf>" --out "<extract>" --ch N --start S --end E

# 手动补图
"<python>" "C:/Users/ye190/.workbuddy/skills/book-summarizer/config/figure_manual_chN/apply_manual_figures.py" "<extract>" <ch> --pdf "<pdf>"
```
