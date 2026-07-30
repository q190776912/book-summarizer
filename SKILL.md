---
name: book-summarizer
description: Summarizes a textbook (from local PDF or the agent's knowledge base) into chapter-by-chapter markdown files. Output language follows the textbook's language: Chinese text→CN only; English text→CN+EN; other languages→original+CN+EN. Each chapter gets numbered definitions/theorems/examples, proof sketches, and KaTeX. HARD REQUIREMENTS: (0) Never copy OCR formulas directly — correct+rewrite; (1) NO mojibake; (2) ALL labeled/bare-numbered items AND all examples must be included; (3) bold inline labels NOT ### headings. CN version annotates key terms with (English) from the source text when available, else translated.
---

# Book Summarizer

This skill converts a textbook into structured chapter-by-chapter markdown summaries suitable for review, reference, or spaced repetition.

## When to Use

Use this skill when the user wants to:
- Summarize a textbook they have as a local PDF
- Create detailed chapter notes from a book in your knowledge base
- Produce structured markdown with definitions, theorems, and proofs
- Generate KaTeX-friendly math notes from a source

## Core Principle

Faithful to source, correct OCR noise, don't fabricate:

- **允许修正 OCR 噪声**：编号模糊时还原，内容模糊时基于上下文复原原意
- **允许适度精简**：但不得省略任何编号项
- **不允许无中生有**：书本没讲的概念不要编，没出现的编号不要硬加
- **不允许统一风格**：不得为美观更改原书分隔符格式
- **不允许创造编号**：无编号章节不强行编号

全部格式规则、编号规范、KaTeX 规则详见 **[`references/formatting.md`](references/formatting.md)**。

---

## 目录结构

```
D:\study\book\<书名>\       ← 每个书一个文件夹
  ├─ <书名>.pdf            ← 源 PDF
  ├─ _extract\              ← 提取目录：所有后台数据（JSON、日志、章节映射）
  │   ├─ page_001.json …    ← 全部原始 JSON（平放，不分子目录）
  │   ├─ batch_1-50.log …   ← 每批提取日志
  │   ├─ chapter_map.json   ← 章节起止页映射
  │   ├─ figure_detect.json ← 图片检测清单
  │   ├─ figure_index.json  ← 图片命名清单（E/F 层消费）
  │   └─ figure/            ← 裁剪图
  ├─ 第1章_章名.md           ← 中文版
  ├─ Chapter1_Name.md       ← 英文版（仅英文/他语种书时有）
  └─ ...
```

> **PDF 必须放在本书专属文件夹内**（即 `D:\study\book\<书名>\<书名>.pdf`），否则 `_extract` 会落到错误父目录。
> **临时文件隔离规则**：Agent 生成的所有临时脚本、日志等中间文件，**必须放入 `_extract\` 目录**。根目录只允许 `.pdf`、`.md`、`_extract\` 三类。

---

## Workflow

### ⚠️ 核心规则

**规则 A — 全书完成才结束，不准提前停**：唯一退出条件是 `已写章数 == chapter_map 中的总章数`。

**规则 B — 必须按批次增量总结（禁止等全书提取完）**：每一批提取完成就立即检查哪些章可写，即时写总结。增量总结是本 skill 的正确流程。

**规则 C — chapter_map 必须尽早建、且只建一次**：目录页一提取到（`current_max_page >= 5`），立即从目录页建立 `chapter_map.json`。

**规则 D — 超大章总结按「节」拆分（字符数 > 30000 触发）**：当某章总结（中文或英文，**任一**超过 30000 字符）过大时，把它拆成「每节一个文件」。拆分粒度 = 标题首部编号为 `N.M`（**恰好一个小数点**）的标题，不论 markdown 级数（## / ### 都算）也不论是否带 § 前缀；子节 `N.M.P`（两个小数点）留在父节文件内，不单独成文件。命名：中文 `第{N}章{M}{名称}.md`、英文 `Chapter{N}_{M}{名称}.md`（名称取自标题编号之后文本，剔除 Windows 非法字符与 `$...$` 数学块）。**章开头的引言/导语（第一个节标题之前的内容）归入第 1 节文件**。由 `format/split_chapters.py` 执行，幂等；**拆分成功后默认删除源合并文件**（加 `--keep` 可保留，因节文件已完整覆盖其内容）；重复运行会跳过已拆分的节文件（`第N章M.xxx` / `ChapterN_M.xxx`），不会二次拆分。

> ⚠️ 拆分判定只看「章」级阈值，不保证每个节文件 < 30000。若某节本身仍过大（如第3章 3.3 节约 18 万字符），需进一步按 `N.M.P` 子节拆分时，作为独立需求另议。

---

### Step 0：准备工作（首次）

```powershell
conda activate pdfextract
python -c "import torch; print(torch.cuda.is_available())"  # must be True
```

> 环境 / 模型绝对路径表详见 **`references/environment.md`**。

---

### Step 1：确定 PDF 路径 → 移动 → 启动后台提取

**在启动后台提取之前，禁止做任何其他操作。**

1. 找到 PDF，确认在 `D:\study\book\<书名>\` 下；不在则**移动**过去
2. **移动必须使用 `Move-Item`（而非 `Copy-Item`）**，否则原位置会残留副本
3. 移动后检查 `D:\study\book\<书名>\<书名>.pdf` 存在且目标文件夹中仅此一份
4. 立即启动后台提取，**然后直接转到 Step 2**

```powershell
# [PowerShell 直接调用，中文路径安全]
$env:Path = "D:\anaconda3\envs\pdfextract\lib\site-packages\torch\lib;D:\anaconda3\envs\pdfextract\Library\bin;D:\anaconda3\envs\pdfextract\Scripts;D:\anaconda3\envs\pdfextract;${env:Path}"

# 移动 PDF 到书籍专属目录（如已在则跳过）
if (-not (Test-Path -LiteralPath "D:\study\book\<书名>\<书名>.pdf")) {
    Move-Item -LiteralPath "<原路径>" -Destination "D:\study\book\<书名>\<书名>.pdf" -Force
}

$proc = Start-Process -WindowStyle Hidden -PassThru -FilePath "D:\anaconda3\envs\pdfextract\python.exe" -ArgumentList @(
    "C:\Users\ye190\.workbuddy\skills\book-summarizer\pipeline/extract_pipeline.py",
    "D:\study\book\<书名>\<书名>.pdf"
)
```

```bash
# [Git Bash 备选，仅 ASCII 路径]
bash "C:/Users/ye190/.workbuddy/skills/book-summarizer/launch_pipeline.sh" \
  "D:/study/book/<书名>/<书名>.pdf"
```

`pipeline/extract_pipeline.py` 参数：
- `<pdf路径>` + `[--force]`（从头重跑） + `[--no-figures]`（跳过图片）
- 自动断点续跑（扫描已有 `page_*.json` 取最大页 + 1）
- 每批 50 页，日志写到 `extract_pipeline.log` + `batch_{start}-{end}.log`
- **增量 figure 流程（默认开）**：每批提取后立即做 detection（追加到 `figure_detect.json`），对页范围已全部检测完的章自动运行 assignment（写 `figure_index.json`），与总结并行。详见 **[`references/figure_pipeline.md`](references/figure_pipeline.md)**
- 一批失败即停止

> **多册文档：强制逐册串行提取**（显存安全）：多册 PDF 禁止并发提取，必须逐册串行。前一册 `PIPELINE OK` + 显存回落后再启动下一册。

---

### Step 2：Agent 自动轮询循环（强制并行）

> **🔴 启动后台提取后立即进入此循环，不得等待。**

```
total_chapters = len(chapter_map)
chapter_map_ready = False

while True:
    1. current_max_page = max(现有 _extract/page_*.json 的页码)

    2. if not chapter_map_ready and current_max_page >= 5:
        从目录页读取章名和书页码，写 chapter_map.json
        chapter_map_ready = True

    3. 对 chapter_map 中每个未写章节：
       if info.end <= current_max_page → 该章可写

    4. 对每个可写章节：
        - 按提取流程从 JSON 提取编号项（详见 `references/formatting.md#提取流程`）
        - 按格式规则写文件（详见 `references/formatting.md`）
        - **写完后必须按 Step 3.5 嵌入本章图片（强制，在 Step 4 校验之前）**
        - 按 Step 4 校验，全部通过才标记完成

    5. if 已写章数 == total_chapters:  break

    6. if 没有新章节可写:  sleep 5s
```

> **增量 figure**：`figure_index.json` 也按章增量生成，与总结并行。写章总结时可直接引用该章的 `figure_index.json` 用于 E/F 校验。

#### 实用脚本

```powershell
# 检查已有数据
$pages = Get-ChildItem "_extract\page_*.json"; $pages.Count
($pages | ForEach-Object { [int]($_.Name -replace '\D','') } | Measure-Object -Maximum).Maximum

# 检查提取进程
Get-Process -Name python -ErrorAction SilentlyContinue

# 生成章节 raw text（辅助阅读）
python -c "
import json, os
d = r'D:\study\book\<书名>\_extract'
for p in range(start, end+1):
    data = json.load(open(os.path.join(d, f'page_{p:03d}.json')))
    print(f'=== PAGE {data[\"page\"]} ===')
    for t in data.get('text',[]): print(t.get('text',''))
"
```

---

### Step 3：写作格式

每章遵循以下格式规则，**全部细节详见 [`references/formatting.md`](references/formatting.md)**：

- 章标题：`# 第N章 章名 (English Name)`
- 节标题：`## §N.1 节名 (English Section Title)`（**必须带 `§`**）
- 子节标题：`### §N.1.1 小节名 (English Subsection Title)`（**必须带 `§`**）
- 定义/定理/命题/推论/引理/断言/公理 → `**粗体标签**：`（禁止用 `###`）
- **⚠️ 结构性标签禁止进块引用（硬规则）**：定义/定理/引理/推论/命题/断言/公理的「条目陈述」必须**独立成行（顶层）**，绝不能被 `>` 包裹。只有 **证明（思路/梗概/概要）**、**例/Example**、**注记**（含「**说明**」）、**脚注** 才进 `>` 块引用。把 `**引理X**` 写进 `>` 是错误的——它会把该条目吞进上一个 `> **证明**` 块引用、破坏章节结构（真实事故：`第33章_数论与虚数.md` 曾把 `引理33.5` 裹进定理 33.4 的证明引用里）。
  - ❌ 错误：`> **引理33.5（高斯整除引理）**：设 α=a+bi…`（引理被吞进证明块引用）
  - ✅ 正确：顶层写 `**引理33.5（高斯整除引理）**：设 α=a+bi…`，其证明另起 `> **证明**：…` 块引用
  - ⚠️ **陈述内容（不只是标签）也禁止进块引用**：在某个定义/定理/引理/推论/命题的**陈述区**（从标题行到其首个 `> **证明/例/注**` 之前）内，若出现了被 `>` 包裹的**枚举子句 / 展示公式 / 子点列表**（`> （N）` / `> **(N)**` / `> $$` / `> - （a）` / `> - (a)`），同样违规——这些必须解包到顶层（真实事故：冯琦《集合论导引 第三卷》`第3章` 曾把 引理3.25 / 引理3.28 / 定义3.13 的陈述公式与枚举子句裹进 `>`）。判定边界：示例块（`> **例3.x**` 及其内部的 `> **(N)**` 子点）整体合法保留在 `>` 内，不属于违规。
- 例/Example → `> **块引用包裹**：`（证明与例子同一层 `>`，不用 `> >` 嵌套）
- **例与证明必须在同一连续 blockquote 中**：例的陈述与它的证明之间不能有空行（空行会打断 blockquote），也不能有裸 `$$`；`$$` 也需加 `>` 前缀。工具 `format/fmt_proofs.py` 的 `merge_example_block()` 会自动合并。
- **块引用不得截断**：全部内容（含 `$$`）都必须在 `>` 内
- **块引用内 display 公式必须用单行空格 `> $$`**：`>` 与 `$$` 之间只允许**一个空格**（`> $$`），绝不能写 `>    $$`（额外缩进）。`>    $$` 在 CommonMark 下变成 `   $$` 内容，KaTeX 不识别为数学围栏，公式以纯文本渲染（不报错但显示破版）。单行 `> $$公式$$` 也必须拆成 `> $$` / `> 公式` / `> $$` 三行。`format/check_katex.py` 的 **Pass 1h** 会拦截 over-indented 块引用公式，`--fix` 自动归一化为 `> $$`。
- **条目间用 `---` 分隔**，但两种情况禁止 `---`：(a) 节标题紧邻下不能有 `---`；(b) **条目的「标题/描述行」与其自身的 `**(N)**` 子点之间，以及条目内部两个 `**(N)**` 子点（`**(i)**` 与 `**(i+1)**`）之间，都不能有 `---`**（`---` 只用于两个*不同顶层条目*之间，如 `**引理3.1**` 与 `**引理3.2**` 之间；条目内部应直接连写——标题→空行→`**(1)**`→（接续文本/公式）→`**(2)**`→…，不要插 `---`，参照 `**引理3.3**` 写法）。**即使是子点跨多行**（其接续文本或 `$$` 公式直接位于 `---` 上方、而非 `**(i)**` 标签本身），该 `---` 仍属条目内部、必须删除。`verify/verify_chapter.py` 的 **J 层**采用 `in_item` 跨行追踪，拦截条目块内一切 `---`（覆盖「标题↔子点」与「子点↔子点」两种情形），`--fix` 自动删除。
- **证明思路/梗概/概要** → `> **证明思路**：` 块引用内，多步骤用 `1. 2. … N.`
- **⚠️ 证明块引用以「证明结束」为界，不得吞并后继正文（硬规则）**：以 `> **证明思路/梗概/概要**：` 开头的块引用**只承载证明本身**。原书证明以 `□` 收尾；`□` 之后的内容（构造、定义、推论性陈述、引理前提等正文）**必须退出 `>`、作为顶层正文**，绝不能继续用 `>` 包裹。常见误写：把「证明思路」N 步之后紧接着的「设 κ 是可测基数…如下定义树 T…具备如下特点：(1)…(4)…」也裹进同一个 `>` 引用块——这是原书 `□` 之后的桥接性正文，不是证明。判定：只要某一 `>` 行之后不再是证明步骤（不以 `1.` / `（一）` / `首先` 等证明标记开头，而是另起一个构造/陈述），它就是越界，应解包到顶层。（真实事故：冯琦《集合论导引 第三卷》`第3章` 定理3.53 的「树 T 构造（含 (1)–(4) 性质）」被裹进证明块引用。）
- **⚠️ 嵌套子项与同级条目必须留空行（对齐硬规则）**：当某条目含子项（如 `- (i)` / `- (ii)` / `- (iii)`，或 `(a)` / `(b)`）时，下一个**同级顶层条目**（如 `(2)`）必须与上一个顶层条目（如 `(1)`）**并列**。若子项列表末尾与 `(2)` 之间**没有空行**，渲染器会把 `(2)` 误判为子项的并列项（与 `(iii)` 同层）。修复：在最后一个子项与 `(2)` 之间插一个空行；或干脆把子项写成**缩进的 `(i)` / `(a)` 段落**（不带 `- ` 项目符号，参考本书 `定义3.35` 的 `(a)(b)` 写法），从根上消除歧义。（真实事故：冯琦《集合论导引 第三卷》`第3章` `定义3.30` 的 `(2)` 因紧接 `- (iii)` 无空行而被误对齐到 `(iii)` 同级。）
- 重要公式用 `$$`（前必须有空行）
- **公式编号用 `\tag{N.M}` 写在 `$$` 块内公式行末尾**（渲染在公式右侧同行）。禁止将编号写成公式块外部的独立文字行（如 `（式 (1.17)）`）。详见 `references/formatting.md` KaTeX 规则 #10。
- **公式/交换图表禁止用 ` ``` ` 代码围栏包裹（强制规则）**：一律用 `$$`；交换图表用 `\begin{CD}...\end{CD}` 的 AMScd 语法。代码围栏会把公式渲染成等宽纯文本、极难看，且会触发 `format/check_katex.py` 的 Pass 1b 校验 → `verify/verify_chapter.py` 的 C 层直接 FAIL。详见 `references/formatting.md` 的 KaTeX 规则 #7。
- 首次出现的关键术语标注 `(English)`
- **不需要写习题/练习**：(a) 每章末尾的习题/练习题不写入总结；(b) **整小节都是练习/习题的节必须整体省略**——不写小节标题（如 `## §1.11 练习`、`## §3.9 练习`、`### §N.M.x 习题`）、不写任何练习条目、也不写「依规则略去」之类的注记。判断标准：若某个 `§N.M` 小节的内容全部为练习/习题，则该小节从总结中完全删除（即「有一个小节都是练习的，不需要写进总结里面」）。
- **图片嵌入（强制规则，2026-07-26 立）**：当 `_extract/figure/` 下存在本章的裁剪图（即 `figure_index.json` 有本章条目，且对应 PNG 已在 `_extract/figure/`）时，写章总结时必须**判断每张图是否被某个条目（定义/定理/引理/命题/推论/例/证明）引用**，把引用的图放在该条目处，未引用的图不写入总结。嵌入格式为 `<div style="display:flex; gap:6px; flex-wrap:wrap; justify-content:center">` 容器包裹 `<img>`，**所有图片（含单张）均套该容器**，使并排图组自然同行、单张图居中：，其中 `X` 基于原图裁剪框与 A4 页宽（1653px）的比例计算。映射方式与嵌入语法详见 **[`references/formatting.md#图片嵌入规则`](references/formatting.md#图片嵌入规则)**。

**写前必须先提取全部编号项**：按 [`references/formatting.md#提取流程`](references/formatting.md#提取流程) 的 9 步流程从 JSON 提取清单，逐项核对后写作。

**格式后处理**：写完后依次运行：
1. `python format/wrap_examples_bq.py <book_dir>` — 把**顶层**的 `**例/Example**` 条目整体包进 `>` 块引用（fmt_proofs 只合并「已在 `>` 内的例」与其证明，**不会**把顶层例包进块引用，这一步必须先跑）。注意中文「例2.1-3」不能用 `\b` 匹配（汉字与数字间无词边界）。
2. `python format/fmt_proofs.py <book_dir> --number` 统一修复块引用/分隔线格式（内含 `merge_example_block()` 合并例与证明的 blockquote，在 stage1 之前执行）。
3. `python format/fix_katex.py <book_dir>` — 综合修复已知 KaTeX 模式（未闭合 `$`、`$$` 包裹 `$`、断裂命令、CD 语法等）。
4. `python format/check_katex.py <file>` 逐文件复验（**不加 `--fix`**，尤其是中文文件）。

---

### Step 3.5：嵌入图片到总结（强制，位于 Step 4 校验之前）

> **🔴 这是强制步骤，不是可选建议。** 只要该书跑过图片流水线、且 `_extract/figure_index.json` 中存在本章条目（对应 PNG 已在 `_extract/figure/`），写章总结时就**必须**执行本步；跳过它，Step 4 的 #9「图片嵌入正确」会判 FAIL。

**做什么**：把 `_extract/figure/` 下、被某条目（定义/定理/引理/命题/推论/例/证明）引用到的图，嵌入到该条目处；未引用的图不写入。判定与放置规则见 **[`references/formatting.md#图片嵌入规则`](references/formatting.md#图片嵌入规则)**。

**怎么做（脚本自动化，幂等）**：

```bash
# 嵌入整本书（每章自动判断+插入；已嵌入的图自动跳过，不会重复）
python figure/embed_figures.py "<book_dir>"

# 只嵌某一章 / 只预览不落地
python figure/embed_figures.py "<book_dir>" --chapter 3
python figure/embed_figures.py "<book_dir>" --dry-run
```

- 脚本会：① 用 OCR 噪声容忍的「图注→条目锚点」启发式匹配；② 自动补 `_extract/` 路径前缀（不会写出 `figure/...` 这种坏链）；③ 嵌入后**自动跑结构扫描**——把落在 `> **证明/例**` 块内却写成顶层的图缩进进块（`> <img ...>`），并把块内裸空行转成 `> ` 保证引用块连续（即直接满足 G 层要求）；④ **自动 flex 包装**：所有 `<img>` 统一包裹在 `<div style="display:flex; gap:6px; flex-wrap:wrap; justify-content:center">` 内，连续小图并排、单张居中。各步均幂等。
- **🔴 flex 容器格式铁律（2026-07-27 立，图片嵌入排版 bug 修复）**：`<div style="display:flex; ...">` 与 `<img>`、`<img>` 与 `</div>` 之间**禁止出现空行**。`wrap_images_in_flex()` 产出的合法形态为（注意标签之间无回车空行）：
  ```
  <div style="display:flex; gap:6px; flex-wrap:wrap; justify-content:center">
    <img src="_extract/figure/ch00_fig1.4.png" alt="图 Figure 1.4. ..." width="35.4%" height="auto">
  </div>
  ```
  **错误形态（曾出现、已修）**：
  ```
  <div style="display:flex; gap:6px; flex-wrap:wrap; justify-content:center">

    <img src="..." ...>

  </div>
  ```
  根因：`wrap_images_in_flex()` 早期版本给每个元素尾部追加了 `\n`，而 `write_lines()` 又用 `"\n".join(...)` 拼接，导致**双重换行 = 容器内空行**。现已改为 `wrap_images_in_flex()` 返回无尾换行的行列表（与其余扫描函数一致），`write_lines()` 的拼接即正确。该修复同时让 `wrap_images_in_flex()` **重扫即净化**：对已嵌入文件重跑 `figure/embed_figures.py` 时，即便 `<img>` 已跳过，扫描阶段也会把既有坏 div 重写为紧凑形态。
- **书特有的覆盖映射**：若某图图注无明确条目编号、但内容明显属于某条目，可在该书 `_extract/figure_embed_overrides.json` 声明 `{"<fname.png>": {"anchors": ["**例1.5-9", ...], "is_proof": false}, ...}`；脚本优先用它能定位的锚点。无此文件则纯靠启发式。
- 这一步是 Step 4 校验的**前置依赖**：先嵌图，再跑 `verify/verify_chapter.py`（其 #9 检查图片是否按引用条目嵌入、G 层检查块连续性）。

---

### Step 4：逐条校验全部规则

**任何一条不通过都算失败，必须修正后重验。全部细节详见 [`references/verification.md`](references/verification.md)。**

> **快捷修复**：`verify/verify_chapter.py --fix` 可自动修复 G/H/I/J 层问题（引用块连续、结构标签出块、条目分隔线、条目块内多余 `---`（含标题↔子点 与 子点↔子点）），再手动确认余项即可。

| # | 规则 | 校验方法 |
|---|------|---------|
| 0 | **全标项必录 + 十三层强制校验（含 G 扩展/EG）** | **`verify/verify_chapter.py <ch> <start> <end> <md> <extract_dir>`** — 按 D→A→B→C→E→F→G→G扩展→EG→H→I→J→K→L→M→N 顺序输出，exit 0 才算通过。支持 `--fix` 自动修复 G/H/I/J/K/L/M/N 层问题 |
| 1 | **OCR 噪声已修正** | 抽 2–3 个公式，确认不是 OCR 照抄 |
| 2 | **UTF-8 无乱码** | `read` 前 5 行，无 `绗?` `闅忔` 等 mojibake |
| 3 | **粗体标签/块引用 + § 标识** | 确认无 `### 定义` 等违规，节标题均带 `§` |
| 4 | **KaTeX 格式（渲染必须成功）** | 已并入 C 层。零报错才放行。注意 `\$\$` 转义定界符（渲染为文本而非公式）也会被拦截 |
| 5 | **英文标注完整** | 首次出现处均标注 `(English)` |
| 6 | **输出语种正确** | 按原书语种匹配输出 |
| 7 | **一次性写齐** | 该章所有文件一次完成 |
| 8 | **文件命名正确** | N 用阿拉伯数字，禁止中文数字 |
| 9 | **图片嵌入正确** | `figure_index.json` 中本章每张图都已在 `.md` 中按「引用该图的条目」定位嵌入；**图必须放在引用它的条目的块引用内部**（例如：例的图必须在 `> **例...**` 块内，定理的图必须在定理陈述之后的 `> **Proof sketch**` 块内或定理陈述后的顶层，但必须与引用它的条目保持连续）；未引用的图不写入（详见 `references/formatting.md#图片嵌入规则`） |
| 10 | **证明/例子引用块连续（G 层）** | `verify/verify_chapter.py` 的 **G 层**零违规：`> **证明/例**` 块内不得有裸空行（须用 `> ` 空引用行留白），否则块被渲染器切断成多个框。块间分隔（例↔证明、`---`、`## `、顶层 `**标签**`）的裸空行允许保留 |
| 11 | **无嵌套引用（G 层扩展）** | `verify/verify_chapter.py` 的 **G 层**零嵌套违规：`> > **证明**` / `> > **例**` 等二级嵌套块引用必须展平为单层 `>`，否则 KaTeX 不识别且渲染断裂 |
| 12 | **例与证明块间无空隙（EG 层）** | `verify/verify_chapter.py` 的 **EG 层**零违规：例的陈述与证明之间不得有空行或裸 `$$`，须处于同一连续 `>` 块 |
| 13 | **定理/命题与证明间无多余分隔** | 定理/命题/命题/推论/引理（顶层陈述）与其证明（`> **Proof sketch**` 或 `> **Proof**` 块）之间**不得有 `---` 分隔线**——证明是定理的内部附属块，不是独立条目。间距仅用空白行（需加 `>` 前缀保持块连续）或直接相接。 |
| 13b | **条目块内无多余 `---`（J 层）** | 顶层条目（定义/定理/引理/推论/命题/断言/公理，如 `**引理3.1**`）的块（标题行到其全部 `**(N)**` 子点）内部**不得有任何 `---`**——既含「标题/描述行 ↔ 首个 `**(N)**` 子点」，也含「`**(i)**` ↔ `**(i+1)**` 子点之间」。`---` 只用于两个*不同顶层条目*之间。正确写法：标题 → 空行 → `**(1)**` →（接续文本/公式）→ `**(2)**` → …，全程无 `---`（参照 `**引理3.3**`）。**子点跨多行（接续文本/`$$` 公式在 `---` 上方）也照删**。`verify/verify_chapter.py` 的 **J 层**零违规（采用 `in_item` 跨行追踪）；`--fix` 自动删除条目块内所有 `---`。 |
| 13c | **陈述内容不进块引用（H 层扩展·ISSUE1）** | `verify/verify_chapter.py` 的 **H 层扩展**零违规：定义/定理/引理/推论/命题的**陈述区**（标题行到首个 `> **证明/例/注**` 之前）内，不得出现被 `>` 包裹的**枚举子句 / 展示公式 / 子点列表**（`> （N）` / `> **(N)**` / `> $$` / `> - （a）` / `> - (a)`）。这些必须解包到顶层。`>` 只用于**证明 / 例 / 注 / 脚注**。示例块（`> **例X**` 及其内部 `> **(N)**`）整体合法保留在 `>` 内，不在此层范围。`--fix` 自动 unwrap 陈述区的 `>` 行。 |
| 13d | **证明块引用不越界（证明边界）** | `> **证明思路/梗概/概要**` 块引用在证明结束后即终止；`□` 之后的构造/陈述正文不得留在 `>` 内（应解包顶层）。`format/check_katex.py` 的 **Pass 2b** 拦截「结构性条目被吞进 `>`」类最严重越界，`--fix` 自动 unwrap；构造性正文越界属硬规则，需人工核对原书 `□` 位置后解包。 |
| 13e | **嵌套子项对齐（列表）** | 含子项（`- (i)` / `(a)` 等）的条目，其下一个同级 `(n)` 与子项列表之间须有空行，否则与子项误并列。`format/check_katex.py` 的 **Pass 2a** 拦截并 `--fix` 自动在 `(n)` 前补空行；亦推荐用缩进 `(i)`/`(a)` 段落写法（如 `定义3.35`）根除歧义。 |
| 13f | **证明与编号列表间有空行（K 层）** | `verify/verify_chapter.py` 的 **K 层**零违规：当定理/定义的陈述含 4-空格缩进的编号列表（`    N.`），且其后紧接 `> **证明**` / `> **证明思路**` 块引用时，列表末项与证明块之间**必须有一空行**，否则证明块视觉上对齐编号项而非定理外层。`--fix` 自动插入空行。 |
| 13g | **分隔线上下有空行（L 层）** | `verify/verify_chapter.py` 的 **L 层**零违规：每个 `---` 分隔线上方**和**下方都必须紧邻一空白行（即 `正文\n\n---\n\n正文` 格式）。无空白行时 `---` 可能被误解为 setext 标题下划线或被渲染器吞没。`--fix` 自动在 `---` 上下补缺失的空白行。 |
| 13h | **显示公式内无 `>` 前缀（M 层）** | `verify/verify_chapter.py` 的 **M 层**零违规：`$$...$$` 显示公式块内部的每一行都不能以 `>`（块引用标记）开头。若块引用上下文中的 `>` 泄漏进公式块，KaTeX 渲染会失败。`--fix` 自动剥离 `$$...$$` 内部的 `>` 前缀。 |
| 13i | **块引用内空 `>` 行不超过 1 行（N 层）** | `verify/verify_chapter.py` 的 **N 层**零违规：在 `> **证明**` / `> **例**` / `> **注**` 等块引用内，连续的空 `>` 行（仅有 `>` 或 `> ` 无其他内容）不得超过 1 行。过多的空 `>` 行是提取噪声或视觉填充。`--fix` 自动删除多余的空 `>` 行（保留第 1 行）。 |
| 14 | **公式忠于原文（语义检查）** | 对照 `page_*.json` 的 `formulas[].latex` 抽检 2–3 个展示公式，确认数学语义一致（详见 `references/verification.md#⑪-公式忠于原文手动校验`）。**禁止语义替换**（如 `\emptyset` ↔ `0`、`∩` ↔ `∪`） |

---

## Skill Scripts Reference

> 目录精简记录：原 34 个 `.py` 经整理后保留约 22 个（主流程 + 辅助/特例脚本）。被取代的脚本（旧批量驱动器 `validate_phase*`、`fmt_proofs_legacy.py`、独立小工具 `dedent_display_math/normalize_display_math/split_displaymath/fix_quote_gaps`、`dump_page/mkraw/dump_raw/find_all_items`、`extract_items_en.py`、旧 `.bat` 启动器）已移入 `_retired/`，可回看但不参与主流程。

### 核心脚本（主流程）

| Script | Purpose |
|--------|---------|
| `pipeline/extract_pipeline.py` | 后台流水线驱动（自动断点续跑 + 增量 figure） |
| `pipeline/extract_book.py` | 单次手动提取引擎（MFD→MFR→OCR→JSON + figure 两段） |
| `figure/extract_figures.py` | 图片检测（阶段 1）：DocLayout-YOLO 检测+裁剪，写 `figure_detect.json` |
| `figure/assign_figures.py` | 图片命名（阶段 2）：据 OCR 图注匹配图号，写 `figure_index.json` |
| `figure/apply_manual_figures.py` | 手动补图：E 层 FAIL 时用 `figure_manual_chN.json` 声明+执行 |
| `figure/embed_figures.py` | **【强制步骤 Step 3.5】** 把 `figure_index.json` 中引用到的图嵌入对应条目；自带块内缩进 + 连续性扫描，幂等 |
| `verify/verify_chapter.py` | **统一强制校验关卡**（九层 D→A→B→C→E→F→G→G扩展→EG→H→I→J）；`--fix` 自动修复 G/H/I/J 层问题 |
| `format/check_katex.py` | KaTeX 格式校验（被 C 层内部调用）；`--fix` 仅修复格式问题（拆分单行 `$$`、补空行、修缩进等），**不碰 `$` 内容**。当前工作流已用 `fix_katex.py` 替代 `--fix`。 |
| `format/fix_katex.py` | **综合 KaTeX 修复脚本**：一行命令修复所有已知模式（未闭合 `$`、`$$`包裹`$`、断裂命令、CD 图表语法、集合花括号、`$$`内空行等），不含 `--fix` 级联破坏风险。详见下方「KaTeX 问题识别与修复」 |
| `extract/extract_items.py` | 从 JSON 提取全部编号项（中文书）；英文书加 `--lang en` 走英文正则 |
| `extract/scan_items.py` | 两级编号书的独立完整性扫描器 |
| `format/fmt_proofs.py` | 格式后处理：块引用/分隔线/证明格式修复 |
| ~~`format/mathify_plaintext.py`~~ | **已暂停使用**。原功能：裸写数学记号包进 `$...$`（Unicode 上/下标与符号→KaTeX）。停用原因：对已有 `\(...\)` 定界符的文件会造成严重破坏（会把 `\(` 误当作普通字符，产生 `$\\(...$` 坏模式，后续修复脚本连锁损坏）。已被 `format/fix_katex.py` 取代。 |
| `format/fmt_extras.py` | 显示公式/块引用后处理：`dedent` / `normalize` / `split` / `fixgap`（G 层修复）子命令 |
| `format/split_chapters.py` | **规则 D**：把超 30000 字符的章总结按「节」(N.M 单小数点编号) 拆成每节一个文件；`--threshold` 可调，`--dry-run` 只预览不写；拆分成功后默认删源文件，`--keep` 可保留 |
| `figure/inspect_tool.py` | 排查工具：`page`（看单页 OCR）、`raw`（合并某范围纯文本）、`find`（扫编号项）子命令 |
| `extract/write_chapter_map.py` | `chapter_map.json` 模板工具 |
| `launch_pipeline.sh` | 流水线启动器（bash，空格路径安全） |

### 单书特例 / 辅助工具

| Script | Purpose |
|--------|---------|
| `extract/extract_items_hom.py` + `verify/verify_hom.py` | Hilton & Stammbach《A Course in Homological Algebra》专用：罗马数字章 + section.item 两级编号（无章号位） |
| `pipeline/make_summary.py` | 生成全书级概要 |
| `verify/review_tool.py` | 总结复核辅助 |
| `verify/manage_ignore.py` | 维护校验忽略清单（ignore keys / figures） |

---

## 常见问题处理

| 问题 | 处理 |
|------|------|
| 中途退出后重启 | 先写已完成章节的总结，再启动 pipeline 续跑 |
| 后台提取卡住 | 杀 python 进程，删最后一个不完整 batch log，重启 |
| 提取时没跑图片（历史数据补图） | 分两阶段运行，`--out` 可选不传 pdf_path（自动从 _extract 上级发现 PDF）：<br>`python figure/extract_figures.py --out "_extract" --book`<br>`python figure/assign_figures.py --out "_extract" --book` |
| 某批提取失败 | 查看 `batch_{start}-{end}.log`，通常 VRAM OOM |
| Chinese mojibake | 写入用 `encoding='utf-8'`，写完后用 `read` 检查 |
| PDF 路径含空格启动静默失败 | 改用 `launch_pipeline.sh`（bash，空格路径安全） |
| **figure/ 目录生成 0 个 PNG（但 JSON 有数据）** | OpenCV 的 `cv2.imwrite` 在 Windows 上对含非 ASCII（中文）字符的路径会**静默失败**，所以检测阶段只写出了 `figure_detect.json` / `figure_index.json` 的元数据，但 `figure/` 下没有实际 PNG。本 skill 的 `figure/extract_figures.py` 已改为 PIL 保存，回跑即可生成；若 `_extract/` 已是历史遗留数据没有 PNG，可写一个 `regen_figures.py` 用 fitz 渲染 + PIL 裁剪，按 `figure_index.json` 的 `page+bbox+file` 重建（参考 `泛函分析导论及应用/_extract/regen_figures.py`） |

---

### KaTeX 问题识别与修复

> 以下模式来自《Chaos, Fractals, and Noise》实际修复经验，统计覆盖了 24 个 `.md` 文件中全部 KaTeX parse errors。

#### 根因总览

| # | 问题模式 | 出现频率 | 根因 |
|---|---------|---------|------|
| 1 | **`$formula，` 未闭合 `$`** | 极高 | 中文逗号/句号放在 `$` 内而未补 `$`。`$` 缺少闭合导致数学模式吞噬后续内容，**尤其会吞掉紧随的 `$$` 定界符** |
| 2 | **`$$` 包裹非数学内容** | 高 | `fix_v*.py` 错误地在包含中文或 `$...$` 的行外加了 `$$...$$` |
| 3 | **断裂的命令（`\in t` → `\int`）** | 中等 | `mathify_plaintext.py` 或后续修复脚本替换时破坏命令间距 |
| 4 | **`$$` 包裹 `## §` 节标题** | 中等 | 同上，自动脚本误把标题行也包进 `$$` |
| 5 | **CD 交换图语法错误** | 低 | `@A\int A` 在 KaTeX CD 中无法正确解析（`\int` 作为上箭头标签）；`@VV\text{RN} A` 尾字符应为 `V` |
| 6 | **集合符号 `{x` 花括号未转义** | 低 | `$A_n={x$` → 缺少 `\{` / `\}` |
| 7 | **`$$\text{N}pt\]` 对齐参数** | 低 | 换行对齐标记 `\\[\text{N}pt]` 被改写为 `$$\text{N}pt]` |
| 8 | **`$$` 块内空行** | 低 | 空白行插入 `$$` 内部，部分渲染器会中断显示块 |
| ~~9~~ | ~~`check_katex --fix` 级联破坏~~ | ~~已修复~~ | 经代码分析确认 `--fix` **不插入 `$`**，仅修格式（拆分单行 `$$`、补空行、修缩进）。实际级联破坏源是 `_extract/fix_cn_files.py` 的 `fix_dollar_count`：把 `$formula$.` 误改为 `$formula.`（删了闭合 `$`），制造未闭合 `$` 吞噬 `$$`。已修复。 |

#### 一站式修复（推荐）

```powershell
python format/fix_katex.py <book_dir>
python format/fix_katex.py <book_dir> --dry-run   # 预览
```

该脚本处理模式 1–8，**不含** `check_katex --fix` 的级联破坏风险。运行后用 `check_katex` 验证：

```powershell
python format/check_katex.py <file>
```

如果仍有 parse error，手动定位到具体公式修正。

#### 已知危险操作

1. **❌ `_extract/fix_cn_files.py` 的 `fix_dollar_count`**（已修复）：原实现把 `$formula$.` 误改为 `$formula.`（删了闭合 `$`），制造未闭合 `$` → 数学吞噬 `$$` → `"Can't use function '$' in math mode"` 级联。已在 `fix_cn_files.py` 中修正为「插入 `$` 而非删除」，且只影响确凿的「未闭合 + 后跟 `$$`」行。`check_katex --fix` 是清白的。

2. **❌ `mathify_plaintext.py`**：已暂停使用。原功能是把裸写记号包进 `$...$`，但对已有 `\(...\)` 定界符的文件会造成严重破坏（`\(` 被当作普通字符，产生 `$\\(...$` 坏模式）。已被 `format/fix_katex.py` 取代。

3. **❌ 多层 fix 脚本串联**：先跑 A 脚本再跑 B 脚本再跑 C 脚本，每个脚本只修自己的模式而未知模式被前一个脚本破坏。**修复**: 用 `fix_katex.py` 一站式修复。 |

#### 手动修复模式

##### 模式 1: `$formula，` 缺少 `$`

```
# ❌ 错误
记 $\langle h,\mu\rangle=\int_X h(x)\,\mu(dx).
# 缺少闭合 $ → 数学模式延续到下一个 $（可能是 $$ 的首字符）

# ✅ 正确
记 $\langle h,\mu\rangle=\int_X h(x)\,\mu(dx)$.

# ❌ 另一常见变体
对 $t>0,
[空行]
$$
...
# 未闭合 $ 吞掉了 $$ 的首个 $ 字符

# ✅ 正确
对 $t>0$，
[空行]
$$
...
```

**诊断**：在文件中搜索「奇数个 `$` 的行」，检查该行是否以 `$formula，` 或 `$formula.` 结尾，且之后有 `$$`。

##### 模式 2: `$$` 包裹非数学内容

```
# ❌ 错误
$$ 上箭头表示积分算子, 下箭头表示 Radon–Nikodym 导数. $$

# ✅ 正确
上箭头表示积分算子, 下箭头表示 Radon–Nikodym 导数.
```

##### 模式 5: CD 交换图

```
# ❌ 错误
\begin{CD}
\mathcal M_a @>P>> \mathcal M_a \\
@A\int A @VV\text{RN} A \\    ← @A\int A 不工作；@VV...A 尾符应为 V
L^1_+ @>P>> L^1_+
\end{CD}
# 额外的不匹配 $$
上箭头表示积分算子...

# ✅ 正确
\begin{CD}
\mathcal M_a @>P>> \mathcal M_a\\
@V\int VV @VV\text{RN}V\\    ← 改用 @V （下箭头），尾符匹配
L^1_+ @>P>> L^1_+
\end{CD}
```

KaTeX CD 箭头速查：
- `@>>>` 右箭头、`@<<<` 左箭头
- `@VVV` 下箭头、`@AAA` 上箭头
- 带标签：`@>label>>`、`@VlabelV`、`@AlabelA`
- 方向标记字符（V/A/\>/<）必须**首尾匹配**。`@VV\text{RN}V` 的首尾都是 `V`；`@A\int A` 首尾都是 `A`
- 标签 `\int` 在 KaTeX CD 中作为上箭头标签会解析失败；改用 `@V\int VV`（下箭头+积分标签）|

#### 验证通过后的残余警告

`check_katex` 报告的 "naked LaTeX command" 和 "raw Unicode math arrow" 是**外观警告**，不影响 KaTeX 渲染。它们提示某些命令（如 `\mu`、`\int`）或 Unicode 箭头出现在数学模式 `$...$` 之外。这在中文总结的正文叙述中是预期的（中文段落中引用数学符号时不需全程数学模式）。如需消除，给单个符号加 `$` 包裹即可，但非强制。|
