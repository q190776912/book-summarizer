# Sub-flow: write-source / figures（图片嵌入 SSOT · write-source 阶段）

> 统一模板：目的 / 前置 / 步骤 / 本阶段规则 / 出口 / 相关代码 / 子流程
> 🔴 **本文件是该领域规则的唯一权威详细说明（SSOT）。** `SKILL.md` 与代码注释只引用此处、不重复描述；新增/修改该领域规则只改本文件。工作流步骤见 `SKILL.md`，格式规则见 [`../../../docs/writing-rules.md`](../../../docs/writing-rules.md)，校验关卡见 [`../../../verify/verify.md`](../../../verify/verify.md)。

> 🔴 **嵌入是强制步骤，不是可选建议。** 图像未嵌入会导致校验阶段的图片完整性检查不过。

## 目的
把上游 `figure_detection` 子流程（extract 阶段）产出的 `figure_index.json` 中、被某条目（定义/定理/引理/命题/推论/例/证明）引用到的图，嵌入到该条目处；未引用的图不写入。本子流程（write-source 阶段）**只负责嵌图**；其上游的检测 / 命名由 extract 阶段的 `figure_detection` 子流程完成，产物 `figure_index.json` + `figure/*.png` 即本子流程的**输入契约**（检测 / 命名规则由 extract 阶段文档承载，本文件不重复）。手动补图作为命名环节的 remediation 也在此说明。

## 前置
- 图片流水线检测 / 命名已跑（或历史数据已补图）：上游产出 `figure_index.json` + `figure/*.png` 已存在（输入契约）。
- 该章 `.md` 初稿已写好。

## 步骤（有序，脚本自动化、幂等）

本子流程（write-source 阶段）只负责**嵌图**：把上游 `figure_detection` 子流程（extract 阶段）产出的 `figure_index.json` 中、被某条目引用到的图，嵌入到该条目处。上游的**检测（Detection）与命名（Assignment）**由 extract 阶段的 `figure_detection` 子流程统一执行，产物 `figure_index.json` + `figure/*.png` 即本子流程的**输入契约**：

- `figure/chNN_figX.X.X.png`（已命名图）
- `figure/chNN_unnamed_K.png`（已检测、无图号）
- `figure_index.json`：每条约 `chapter`/`page`/`fig_idx`/`label`/`bbox`/`conf`/`file`/`caption`/`source`

> 本子流程不重复描述检测 / 命名细节（不伸手进 extract 阶段），只消费其产物。

### 阶段 1：嵌入（Embedding，write-source / Step 3.5）
```bash
python flows/script/embed_figures "<book_dir>"            # 整本书（已嵌入自动跳过）
python flows/script/embed_figures "<book_dir>" --chapter 3 # 只嵌某章
python flows/script/embed_figures "<book_dir>" --dry-run   # 仅预览
```
脚本会：① 用 OCR 噪声容忍的"图注→条目锚点"启发式匹配；② 自动补 `_extract/` 路径前缀（不会写出坏链）；③ 嵌入后自动跑结构扫描——把落在 `> **证明/例**` 块内却写成顶层的图缩进进块（`> <img ...>`），并把块内裸空行转成 `> ` 保证引用块连续；④ 自动 flex 包装：所有 `<img>` 统一包裹 `<div style="display:flex; gap:6px; flex-wrap:wrap; justify-content:center">`，连续小图并排、单张居中。

### 手动补图
当 DocLayout-YOLO 漏判某图（典型：旋转 90° 的全页图、文字密集分类树被当 `plain text`），E 层会报"图 X.X.X missing"。**不要**靠改 `--conf` 或换模型救，**用 `figure_manual_chN.json` 声明 + `../../../config/figure_manual_chN/apply_manual_figures.py` 执行**（该步骤回写 `figure_index.json`，属 extract 阶段命名环节的 remediation）：

1. **定位图在哪页**。翻原文 / `figure/inspect_tool.py page <raw_dir> <page>` 找"图 X.X.X"被引用的页；用 fitz 渲染到 PNG 肉眼确认。
2. **读 bbox**。以**200-DPI 渲染图**的像素坐标为准 `[x0, y0, x1, y1]`。若 PDF 把图旋转 90° 存放，设 `rotate: 90`。
3. **写 `_extract/figure_manual_chN.json`**：其字段（`page` / `bbox` / `rotate` / `caption`）、JSON 示例与执行方式见公用配置文档 [`../../../config/figure_manual_chN/figure_manual_chN.md`](../../../config/figure_manual_chN/figure_manual_chN.md)。
4. **执行**：`python config/figure_manual_chN/apply_manual_figures.py <_extract> <ch> --pdf <pdf_path>`
5. **重验**：`../../../verify/script/verify_chapter.py` → E 层看到图号已提供 → PASS。

手动图在**每次 assignment 重跑时都会被保留**（`assign_figures.py` 不删 `source="manual"` 的条目/文件）。

### 工作流衔接（上游 figure_detection 子流程）
图检测 / 命名由 extract 阶段的独立子流程 `figure_detection` 负责，待 `figure.labels` 配置就绪后运行一次全本，产出 `figure_index.json` + `figure/*.png`——即本子流程的**输入契约**。本子流程不重复描述检测 / 命名细节，只消费其产物并嵌图。本书确实无图时，`figure_index.json` 保持缺失，本子流程也随之跳过。

若某章 E 层报"图 X.X.X missing"（真漏检 / 漏命名），重跑或手动补图的处置见下方「手动补图」。

#### 与 figure 层(E) 校验的衔接（遵循 `../../../verify/figure_completeness/figure_completeness.md`）
`figure_index.json` 落地后 `../../../verify/script/verify_chapter.py` 启用 **figure 层(E)**，做三类检查（结构与判定以 figure_completeness.md 的「规则」节为唯一权威）：

- **完整性 COMPLETENESS**：章内 OCR 引用了「图 X.X.X」但 `figure_index.json` 无对应 `chapter==N, label==X.X.X` → **MISSING（阻断 FAIL）**，该图根本没被检测到 → 去对应页重新识别（降 `--conf` 重跑 `extract_figures.py --ch N` 或手动补图）；裁剪图 `label` 在本章 OCR 找不到对应图注 → **EXTRA（仅 WARN）**，疑似误配对。
- **有效性 VALIDITY**：裁剪图缺失文件 / 无法解码 / 单边 <20px → **INVALID（阻断 FAIL）**；近空白（灰度方差 <50，疑似误检文字块）→ **SUSPICIOUS（仅 WARN）**。
- **归属 ATTRIBUTION（新增，覆盖「图悬在块外」盲区）**：每个 `<img>` 须落在 caption/`alt` 所指 item 的块内（`> **证明/例**` 块的图带 `>` 前缀；陈述级配图在条目陈述段之后顶层）。图悬在块外（如历史嵌入脚本 `find_after` 对「`>` 块首行」锚点保守推出块）→ **fig_misattributed（仅 WARN，不阻断）**。这与 [`../../../docs/writing-rules.md`](../../../docs/writing-rules.md) 的图片嵌入规则（caption→条目映射 + 归属层级）形成「写作规范 ↔ 校验把关」闭环：writing-rules 规定图怎么放，figure 层(E) 验证放对了没。
- 前提：`figure_index.json` 存在且含本章 `chapter` 条目，否则 SKIP（绝不阻断）；无 `figure_index.json`（未跑图片提取）的章节亦 SKIP。

## 本阶段规则（🔴 内联）
- **flex 容器格式铁律（2026-07-27 立）**：`<div style="display:flex; ...">` 与 `<img>`、`<img>` 与 `</div>` 之间**禁止出现空行**。合法形态：
  ```
  <div style="display:flex; gap:6px; flex-wrap:wrap; justify-content:center">
    <img src="_extract/figure/ch00_fig1.4.png" alt="图 Figure 1.4. ..." width="35.4%" height="auto">
  </div>
  ```
  根因：早期 `wrap_images_in_flex()` 给元素尾部追加 `\n` 而 `write_lines()` 又 `"\n".join`，双重换行 = 容器内空行。现已改为无尾换行行列表，重扫即净化。
- **书特有覆盖映射**：图注无明确条目编号但内容明显属某条目时，在该书 `_extract/figure_embed_overrides.json` 声明精确锚点（字段 `anchors` / `is_proof`、JSON 示例与生成脚本见 [`../../../data/figure_embed_overrides/figure_embed_overrides.md`](../../../data/figure_embed_overrides/figure_embed_overrides.md)）；无此文件则纯靠启发式。
- **自动锚点匹配的局限**（嵌入后处理）：`../../script/embed_figures.py` 用启发式匹配图注（caption）与条目标签（`**定义X.X**`, `**定理X.X**` 等）。当 OCR 图注文本噪声大、或图无文字标注（如图1.1 Venn 图只有 "图1.1" 而无 "定义1.4" 字样）时，匹配会失败，脚本输出 `no item ref`。**对此情况，必须创建 `_extract/figure_embed_overrides.json` 手动声明锚点**（字段 `anchors` / `is_proof`、JSON 示例与自动产出脚本见 [`../../../data/figure_embed_overrides/figure_embed_overrides.md`](../../../data/figure_embed_overrides/figure_embed_overrides.md)）。此文件在中文教材（Venn 图、拓扑示意图等无文字图注的图）中几乎是必选项。
- **嵌入后 C 层 "missing blank line after `</div>`"**：顶层（非块引用内）图片的 `</div>` 后缺空行会导致 Markdown 解析器吞内容，C 层报错。详见 [`../../../docs/writing-rules.md#已知遗留问题顶层-div-后缺空行`](../../../docs/writing-rules.md#已知遗留问题顶层-div-后缺空行)。
- **图归属层级铁律（与 verify figure 层(E) attribution 对应）**：图的归属层级由 caption 决定（详见 [`../../../docs/writing-rules.md`](../../../docs/writing-rules.md) 图片嵌入规则「强制：图必须归属到正确的层级」）：caption 含 `证明` / `例N` 的图 → 必须缩进进对应 `> **证明/例**` 块引用内（带 `>` 前缀，绝不可写成顶层行打断块）；陈述级配图（无 `证明`/`例`）→ 放在条目陈述段之后的**顶层**，与 `> **证明**` 块并列、互不嵌套。图悬在块外会被 verify figure 层(E) 报 `fig_misattributed`（仅 WARN）。嵌入脚本 `embed_figures.py` 的 `find_after()` 对「`>` 块首行」锚点会保守地把图推到块外——写作/嵌图后须确认图确实落在引用它的 item 块内，而非依赖脚本默认位置。
- 本步是校验的**前置依赖**：先嵌图，再跑 `verify_chapter.py`（其图片嵌入检查、块引用连续性检查、figure 层(E) 归属校验）。

## 上游环境前提 / 已知边界（检测 + 命名阶段）
本子流程只做嵌图，不涉及图检测 / 命名的运行环境。检测阶段的权重、加载器、OpenCV/PIL 路径陷阱、`--conf`、跨页不合并、只取 `figure` 类、caption 序标跟随 `figure.labels` 等**环境前提与已知边界**由 extract 阶段的 `figure_detection` 子流程承载（属上游文档范畴，本文件不重复）。本子流程只需确认输入契约 `figure_index.json` + `figure/*.png` 已就绪。

## 出口条件
- 出口：本章（或全书）被引用图已嵌入、flex 格式合规；`figure_index.json` 已落地且本章 E 层可 PASS（或本书确实无图、`figure_index.json` 缺失）。

## 相关代码（路径相对 skill 根目录）
- `flows/script/embed_figures`：嵌图（幂等，含缩进进块 / 连续性修复 / flex 包装）——本子流程核心脚本。
- `flows/script/extract_figures` / `flows/script/assign_figures`：图片检测 / 命名，属 extract 阶段 `figure_detection` 子流程（产出本子流程的输入契约 `figure_index.json`）。
- `../../../config/figure_manual_chN/apply_manual_figures.py`：E 层 FAIL 时手动补图。
- `figure/inspect_tool.py`：定位图所在页的可视化检查工具。

## 命令速查
```bash
# 嵌入（write-source / Step 3.5）——本子流程核心命令
python flows/script/embed_figures "<book_dir>"
python flows/script/embed_figures "<book_dir>" --chapter 3
python flows/script/embed_figures "<book_dir>" --dry-run

# 手动补图（命名环节 remediation，回写 figure_index.json）
"<python>" "C:/Users/ye190/.workbuddy/skills/book-summarizer/config/figure_manual_chN/apply_manual_figures.py" "<extract>" <ch> --pdf "<pdf>"
```
> 检测 / 命名（`extract_figures` / `assign_figures`）属 extract 阶段的 `figure_detection` 子流程，命令见 `flows/script/extract_figures` / `flows/script/assign_figures`。

## 上游子流程
- **figure_detection（extract 阶段）**：图片检测 / 命名，产出本子流程的输入契约 `figure_index.json` + `figure/*.png`；其规则与命令由 extract 阶段文档承载，本文件不重复。
