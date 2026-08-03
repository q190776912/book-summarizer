> 🔴 **本文件是该领域规则的唯一权威详细说明（SSOT）**。`SKILL.md` 与代码注释只引用此处、不重复描述；新增/修改该领域规则只改本文件。

# 图片流水线（Figure Pipeline）

> 本文档是 `book-summarizer` skill 的图片提取参考。工作流步骤见 `SKILL.md`，格式规则见 `formatting.md`，校验关卡见 `verification.md`。

---

## 目录

- [架构概览](#架构概览)
- [阶段 1：检测（Detection）](#阶段-1检测detection)
- [阶段 2：命名（Assignment）](#阶段-2命名assignment)
- [增量工作流](#增量工作流)
- [手动补图](#手动补图)
- [环境前提](#环境前提)
- [已知边界](#已知边界)
- [命令速查](#命令速查)

---

## 架构概览

识别流程里 DocLayout-YOLO 在**一遍**把文字、图片、公式都框出来（`figure` 用 class 3）。图片提取分成两段，**不再等全书提取完**，而是与提取流水线交错执行：

- **阶段 1 检测（detection，`figure/extract_figures.py`）**：每批页提取完成后立即对该批页做 detection，使用 `detect_pages_range()` 增量追加到 `figure_detect.json`（**不覆盖**已有记录）。文件用**位置/随机名** `figure/det_p{PAGE:03d}_{IDX:02d}.png`（**不带**"图6.1.1"这种语义名）。
- **阶段 2 命名（assignment，`figure/assign_figures.py`）**：检测完成后检查 `chapter_map.json`，对**页范围已全部检测完成**的章立即调用 `run_chapter()` 做 assignment——根据 **bbox 位置 + OCR 图注文本** 判断每张检测到的图对应哪个"图 X.X.X"，重命名为 `figure/chNN_figX.X.X.png`（匹配）或 `chNN_unnamed_K.png`（未匹配），写出 `figure_index.json`（`verify/verify_chapter.py` 的 E/F 层消费）。

这样 `figure_index.json` 在每章全部页面提取+检测完成后立即生成，与章节总结**并行**，agent 的轮询循环可以直接引用，**不用等全书收尾**。**确实不要图**才用 `--no-figures` 关掉（两段都跳过）。

**背景**：PDF-Extract-Kit 的 `layout_detection` 任务**只定位** figure 的边界框（画可视化叠加图），并不把图裁成单独文件。所以"把图 6.1.1 这类裁下来存 `figure/`"靠 `figure/extract_figures.py` 实现——用 PDF-Extract-Kit 的 DocLayout-YOLO 权重给出 figure 框，再用同一 200-DPI 渲染页把框内区域扣出来存 PNG。

---

## 阶段 1：检测（Detection）

### 入口

| 模式 | 函数 | 说明 |
|------|------|------|
| 全本 | `run_full_book()` | 检测全部页面，写入全局 `figure_detect.json`（覆盖重写） |
| 增量 | `detect_pages_range()` | 检测指定页码范围，**追加**到现有 `figure_detect.json`，返回 `(model, new_entries)` 以便跨批复用 layout 模型 |
| 单章 | `run_chapter()` | 重跑某章页面，合并入现有 `figure_detect.json`（幂等） |

### 产物（落到 `_extract\`）

- 检测：`figure/det_p{PAGE}_{IDX}.png`（位置名，无图号）
- `figure_detect.json`：每条约 `chapter`/`page`/`det_id`/`bbox`/`conf`/`file`/`cap_text`/`source`，`label` 为 null

### CLI

```bash
# 全本
"<python>" "C:/Users/ye190/.workbuddy/skills/book-summarizer/figure/extract_figures.py" \
  "<pdf>" --out "<extract>" --book

# 单章重跑
"<python>" "C:/Users/ye190/.workbuddy/skills/book-summarizer/figure/extract_figures.py" \
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
- `figure_index.md`：便于粘贴的 `![](...)` 列表

### CLI

```bash
# 全本
"<python>" "C:/Users/ye190/.workbuddy/skills/book-summarizer/figure/assign_figures.py" \
  "<pdf>" --out "<extract>" --book

# 单章
"<python>" "C:/Users/ye190/.workbuddy/skills/book-summarizer/figure/assign_figures.py" \
  "<pdf>" --out "<extract>" --ch N --start S --end E
```

---

## 增量工作流

`pipeline/extract_pipeline.py` 实现了增量 figure 流程：

1. 每批 MFD+MFR+OCR 提取完成后，立即调用 `detect_pages_range()` 对该批页做 detection，追加到 `figure_detect.json`（layout 模型跨批复用，避免重复加载）
2. 检测完成后检查 `chapter_map.json`，对**页范围已全部检测完**的章自动调用 `assign_figures.run_chapter()` 做 assignment
3. 这样 `figure_index.json` 按章增量产出，与章节总结**并行**

断点续跑时，如果所有页已提取完，会先补检测缺失页，再补 assignment。

### 与 E/F 校验的衔接

`figure_index.json` 落地后 `verify/verify_chapter.py` 启用 **E 层（图片完整性）** 与 **F 层（图片有效性）**：

- **E 层 MISSING（真漏检）**：章内 OCR 引用了"图 X.X.X"但 `figure_index.json` 无对应条目 → 该图**根本没被检测到** → 去对应页**重新识别**（降 `--conf` 重跑 `figure/extract_figures.py --ch N` 或手动补图）
- **未命名（已检测，无图号）**：`figure_index.json` 中有该图条目但 `label==null` → 它**被找到了**，只是 caption 没被识别成"图 X.X.X" → **不阻断**
- **F 层**：裁剪图缺失/无法解码/单边<20px → 阻断；近空白误检 → 仅警告
- 两层前提：`figure_index.json` 存在且含本章 `chapter` 条目；否则 SKIP

---

## 手动补图

当 DocLayout-YOLO 漏判某图（典型：旋转 90° 的全页图、文字密集分类树被当 `plain text`），E 层会报"图 X.X.X missing"。**不要**靠改 `--conf` 或换模型救，**用 `figure_manual_chN.json` 声明 + `figure/apply_manual_figures.py` 执行**：

1. **定位图在哪页**。翻原文 / `figure/inspect_tool.py page <raw_dir> <page>` 找"图 X.X.X"被引用的页；用 fitz 渲染到 PNG 肉眼确认。
2. **读 bbox**。以**200-DPI 渲染图**的像素坐标为准 `[x0, y0, x1, y1]`。若 PDF 把图旋转 90° 存放，设 `rotate: 90`。
3. **写 `_extract/figure_manual_chN.json`**：
   ```json
   {
     "1.3.1": {
       "page": 27,
       "bbox": [35, 60, 1064, 1515],
       "rotate": 90,
       "caption": "图 1.3.1 动力系统分类框架（旋转 90° 存放）"
     }
   }
   ```
4. **执行**：`python figure/apply_manual_figures.py <_extract> <ch> --pdf <pdf_path>`
5. **重验**：`verify/verify_chapter.py` → E 层看到图号已提供 → PASS。

手动图在**每次 assignment 重跑时都会被保留**（`figure/assign_figures.py` 不删 `source="manual"` 的条目/文件）。

---

## 环境前提

- 权重 `doclayout_yolo_ft.pt` 来自 **ModelScope `opendatalab/pdf-extract-kit-1.0`**
- 加载器必须用 **`doclayout_yolo.YOLOv10`**，不能用 `ultralytics.YOLO`（后者在 `predict()` 时会自动 fuse 把 `Conv.bn` 删掉，触发 doclayout_yolo 0.0.4 的 `'Conv' object has no attribute 'bn'`）
- `cv2`（opencv-python）用于读取；Windows 上 `cv2.imread` 读不了含中文路径的文件，`verify/verify_chapter.py` 的 F 层用 `np.fromfile`+`cv2.imdecode` 读；**`figure/extract_figures.py` 已改用 PIL 保存裁剪图**（见下方『已知边界』），避免中文路径静默失败

---

## 嵌入后处理

`figure/embed_figures.py`（Step 3.5）自动完成缩进进块、连续性修复、flex 包装。

### 自动锚点匹配的局限

`figure/embed_figures.py` 用启发式匹配图注（caption）与条目标签（`**定义X.X**`, `**定理X.X**` 等）。当 OCR 图注文本噪声大、或图无文字标注（如图1.1 Venn 图只有 "图1.1" 而无 "定义1.4" 字样）时，匹配会失败，脚本输出 `no item ref`。

**对此情况，必须创建 `_extract/figure_embed_overrides.json` 手动声明锚点**，格式如下：

```json
{
  "ch01_fig1.1.png": {"anchors": ["**定义1.4**", "**定义1.5**"]},
  "ch01_fig1.2.png": {"anchors": ["**定义1.5**"]}
}
```

- `anchors` 是该图应归属的条目标签列表，脚本按出现顺序取匹配到的第一个。
- 此文件在中文教材（Venn 图、拓扑示意图等无文字图注的图）中几乎是必选项。

### 嵌入后 C 层 "missing blank line after `</div>`"

顶层（非块引用内）图片的 `</div>` 后缺空行会导致 Markdown 解析器吞内容，C 层报错。详见 `formatting.md#已知遗留问题顶层-div-后缺空行`。

---

## 已知边界

- 跨页大图被 DocLayout-YOLO 各检出一个框，目前**不合并**，会得到两个文件名
- 只取 `figure`(class 3) 裁，**不裁表格/公式块**（模型另有 `table`(5)/`isolate_formula`(8) 类，脚本忽略）
- 图注为英文 "Figure X.X" / 中文 "图 X.X.X" 都能识别；caption 无图号且同页邻近无 "图 X.X.X" 时命名为 `chNN_unnamed_K.png`
- `--conf` 默认 0.25；觉得误检多就调高，漏检多就调低
- **Windows + 非 ASCII 路径的静默失败**：OpenCV 的 `cv2.imwrite` 在 Windows 上对含中文等非 ASCII 字符的路径会**静默返回 False**（已知 OpenCV 缺陷），导致检测阶段只生成 `figure_detect.json` / `figure_index.json` 元数据但 `figure/` 下没有 PNG。`figure/extract_figures.py` 已改为 PIL 保存，回跑即修复；若 `_extract/` 已是历史遗留数据没有 PNG，可写 `regen_figures.py` 用 fitz 渲染 + PIL 裁剪，按 `figure_index.json` 的 `page+bbox+file` 重建

---

## 命令速查

```bash
# 全本 detection（pdf_path 可省略，自动从 --out 上级目录发现 PDF）
"<python>" "C:/Users/ye190/.workbuddy/skills/book-summarizer/figure/extract_figures.py" --out "<extract>" --book
"<python>" "C:/Users/ye190/.workbuddy/skills/book-summarizer/figure/extract_figures.py" "<pdf>" --out "<extract>" --book

# 单章重跑 detection
"<python>" "C:/Users/ye190/.workbuddy/skills/book-summarizer/figure/extract_figures.py" --out "<extract>" --ch N --start S --end E
"<python>" "C:/Users/ye190/.workbuddy/skills/book-summarizer/figure/extract_figures.py" "<pdf>" --out "<extract>" --ch N --start S --end E

# 全本 assignment（pdf_path 可省略，自动发现；实际不读 PDF，仅作对称参数）
"<python>" "C:/Users/ye190/.workbuddy/skills/book-summarizer/figure/assign_figures.py" --out "<extract>" --book
"<python>" "C:/Users/ye190/.workbuddy/skills/book-summarizer/figure/assign_figures.py" "<pdf>" --out "<extract>" --book

# 单章重跑 assignment
"<python>" "C:/Users/ye190/.workbuddy/skills/book-summarizer/figure/assign_figures.py" --out "<extract>" --ch N --start S --end E
"<python>" "C:/Users/ye190/.workbuddy/skills/book-summarizer/figure/assign_figures.py" "<pdf>" --out "<extract>" --ch N --start S --end E

# 手动补图
"<python>" "C:/Users/ye190/.workbuddy/skills/book-summarizer/figure/apply_manual_figures.py" "<extract>" <ch> --pdf "<pdf>"
```
