---
name: book-summarizer
description: Summarizes a textbook (from local PDF or the agent's knowledge base) into chapter-by-chapter markdown files. Output language follows the textbook's language: Chinese text→CN only; English text→CN+EN; other languages→original+CN+EN. Each chapter gets numbered definitions/theorems/examples, proof sketches, and KaTeX. HARD REQUIREMENTS: (0) Never copy OCR formulas directly — correct+rewrite; (1) NO mojibake; (2) ALL labeled/bare-numbered items AND all examples must be included; (3) bold inline labels NOT ### headings (gm-体例书例外：条目标题按原书排印用 `###`，见 Step 3). CN version annotates key terms with (English) from the source text when available, else translated.
---

# Book Summarizer

This skill converts a textbook into structured chapter-by-chapter markdown summaries suitable for review, reference, or spaced repetition.

## When to Use

Use this skill when the user wants to:
- Summarize a textbook they have as a local PDF
- Create detailed chapter notes from a book in your knowledge base
- Produce structured markdown with definitions, theorems, and proofs
- Generate KaTeX-friendly math notes from a source

## 📌 文档架构（SSOT 约定 / Single Source of Truth）

本 skill 的**详细规则只写在一处（SSOT），其余文档与脚本注释只放一句话摘要 + 链接**，避免改一处漏多处：

- **校验层语义 / 顺序 / `--fix` 范围 / 字节契约** → [`references/verification.md`](references/verification.md)（**SSOT**；新增/修改校验层只改此文件，见其「同步清单」）
- **格式与内容规则**（OCR / 编号 / 块引用 / KaTeX / 图片嵌入）→ [`references/formatting.md`](references/formatting.md)（**SSOT**）
- **图片流水线** → [`references/figure_pipeline.md`](references/figure_pipeline.md)
- **环境与路径** → [`references/environment.md`](references/environment.md)
- **书目编号体系 / 判定树** → [`references/book_patterns.md`](references/book_patterns.md)

> 🔴 **新增/修改「规则、校验层、功能」时，只改对应的 `references/*.md`**，别处（本文件、代码注释）只更新链接或一句话摘要，绝不在多处重复描述细节。agent 需要时按链接点开详情。

---

## 🔴 语言模式铁律（最高优先级，2026-08-04 用户强调整顿）

> **英文 / 他语种原著书：必须先有「源语言总结」，中文总结只能由源语言派生。没有源语言总结就写中文 = 整批作废。**

- **输出语种（frontmatter 铁律）**：中文书 → 仅中文；**英文书 → 必须 CN+EN 双语（英文源版 + 中文派生版）**；他语种 → 原语种 + 中 + 英。
  - 🔴 **英文源版 `ChapterN_*.md` 必须 100% 英文**：标签只写英文（`**Definition 1.1 (Name)**`）、正文/节标题/图注 alt 全英文、**全角中文标点 `：` `（` `）` 一律换半角**。中文只许出现在 `第N章_*.md`。细则见 `references/formatting.md`「双语规则与输出语种」。
- **源语言优先（规则 F 硬底线）**：英文书每章 **先写 `ChapterN_*.md`（英文源版）→ 完全校验 / 修复至 `verify PASS + KaTeX OK` → 再据这份已校验英文版逐条翻译出 `第N章_*.md`（中文派生版）**。中文版是英文版的**翻译产物**，不是与英文平行、各写各的独立文件。
- **🔴 禁止「只有中文、没有英文」**：若目录下只有 `第N章_*.md` 而没有对应 `ChapterN_*.md`，说明流程从根上错了——中文并非源于源语言，该章（及依赖它的后续章）必须重做。中文总结的存在**以英文源版存在且校验通过为前提**。
- **中英两版必须 1:1 同构**：条目、编号、公式、图片位置逐一对应，不得增删或自行发挥；英文版修补后中文版须同步修补（单向：先英后中）。
- 自检：`ls` 本书目录，**英文书必须成对出现** `ChapterN_*.md` 与 `第N章_*.md`；缺英文版即视为「未开始」，不得上报完成。

## Core Principle

Faithful to source, correct OCR noise, don't fabricate:

- **允许修正 OCR 噪声**：编号模糊时还原，内容模糊时基于上下文复原原意
- **允许适度精简**：精简的是表述，不是内容——不得省略任何编号项，也**不得省略描述性内容（动机/直观/导语等）中的公式与概念**（见 Tier 2）
- **不允许无中生有**：书本没讲的概念不要编，没出现的编号不要硬加
- **不允许统一风格**：不得为美观更改原书分隔符格式
- **不允许创造编号**：无编号章节不强行编号
- **🔴 不允许无中生有的「结构」（2026-08-02 立）**：除了不能编造内容，同样**不能编造版面结构**——不得新建原书没有的标题层级、不得把原书穿插排布的内容抽出来归拢成块、不得重排条目顺序。总结文件的骨架（节的个数与顺序、条目与练习的先后位置）必须与原书页码顺序**逐条同构**。（真实事故：Vakil《The Rising Sea》全 24 个文件因自造节末 `### 练习` 归拢块而整批报废，见「练习/习题收录规则」。）
  - **🔴 严禁照抄 OCR 文本流（2026-08-02 立）**：`page_*.json` 是**原料**不是**成品**。必须逐条读懂数学含义后用自己的话重写，公式重写为正确 LaTeX。特别地，**页眉/页脚/版权行属于噪声，必须剔除干净**，一个字都不许进总结正文——典型形态：`November 18, 2017 draft`、`Early (out-of-date) version of The Rising Sea: Foundations of Algebraic Geometry`、`(c) 2024 Ravi Vakil. Published by Princeton University Press`、孤立的页码数字、书名重复行。判据：若你的输出里能搜到这些字符串，说明你在切片而不是在写作，该章必须重做。（真实事故：Vakil Ch1–4 每章混入 58–137 处页眉噪声。）
  - **🔴 非核心内容必须「摘要」而非「整段照抄」（2026-08-02 立，2026-08-02 细化，2026-08-06 修订 Tier 2）**：总结是**摘要**，不是书的副本，但**摘要不等于丢内容**。按内容类型分三档处理（详规见「保真分级与摘要策略」）：① **Tier 1 高保真**——定义/定理/引理/推论/命题/公理的**陈述**、**例子**的**陈述（题面）**、**练习**的**题目**、**注记（Remark/Aside）**，须原汁原味（注记**保留完整、少修改**，只修 OCR 噪声）、保留关键公式与精确术语；② **Tier 2 描述性内容**——动机/直观/背景/过渡/导语等描述性内容须**保留其中的公式与概念**（忠实重写、精简冗余表述，但**不得省略、不得一句话带过**）；禁止整段照抄原书文本流；③ **Tier 3 证明/解答只列核心步骤**——证明与例子的**解答/证明**不逐字重写，只列**核心步骤**：用 `1. 2. 3. …` 按序标号（**步数按实际需数，不限定 3 条**；「1,2,3」只是示意写法），每步一句话点出关键动作（关键引理 / 恒等式 / 归纳 / 构造 / 交换图），结尾给一句结论。**判据：某段散文只是在复述原书文字（整段照抄）才需压缩；若删掉了原段的公式或概念，则无论多短都是保真失败。**（真实事故：Vakil《The Rising Sea》前几章被写成书的逐段英文副本，丧失摘要价值；verify **P 层 `p_verbose` / `p_proof_verbose`** 会据此判 FAIL——但含公式的段落已豁免 `p_verbose`，忠实保留公式的描述不会因此被误杀。）

---

## 保真分级与摘要策略（Summary Fidelity Tiers, 2026-08-02 立）

逐条重写时，**不是每条都照原书原样写**。按内容类型分三档：

### Tier 1 — 高保真（原汁原味，忠实原文）
以下内容的**陈述 / 题目**必须忠实于原书，保留关键定义、精确措辞与 LaTeX 公式；**不得改写语义、不得省略条件、不得概括**：
- **核心概念陈述**：定义（Definition）、定理（Theorem）、引理（Lemma）、推论（Corollary）、命题（Proposition）、公理（Axiom）、断言（Claim）的**陈述句**及其中的关键公式。
- **例子（Example）的题面/描述**：例的**陈述与设定**（题面）必须忠于原文——例是读者最该照原书读的部分，保留原汁原味（OCR 噪声按语义重写为正确 LaTeX，但题面语义、条件、构造不得概括或删减）。
- **练习题（Exercise）**：**穿插在小节中的**练习的**题目陈述**——原样保留（OCR 噪声按语义重写为正确 LaTeX，但题意、条件、设问不得概括或删减）。**章末整块习题按 [`references/formatting.md` 的「习题收录规则」](references/formatting.md)省略，不计入本档必录。**
- **🔴 注记（Remark / Aside）——保留完整、少修改（2026-08-02 用户定）**：注记是原书内容，**完整保留、尽量少改**——只修 OCR 噪声与明显错字，**不压缩、不省略、不概括**。注记类条目（如 `N.M.K. Remark.`）本就是骨架 ITEM，本就该写；未编号的散见注记同样完整保留。

> ⚠️ **例子的「解答/证明」不属 Tier 1**：例子的题面高保真，但例子的**解答或证明**按 **Tier 3** 处理——只列核心步骤 `1. 2. 3. …`（见下），不要逐字翻译原书的解答段落。若例子本身很短、解答本就一句话即明，则一句带过即可。

### Tier 2 — 描述性内容（保留实质、精简表述，禁止丢公式/概念）

以下内容属于**描述性**：动机（Motivation）、直观（Intuition）、背景 / 历史讨论、一般性铺陈、连接性过渡段、章节导语、节首引言。处理原则（与 Tier 1 同源：**忠实 ≠ 照抄**）：

- **🔴 实质内容必须保留，不得省略**：描述性段落里出现的**每一个公式**（按语义重写为正确 LaTeX / KaTeX）、**每一个被引入或解释的概念 / 定义 / 关键关系**都必须保留。「一句话带过」「概括为 2–4 句就够」是**错误**做法——丢公式、丢概念 = 保真失败，与 Tier 1 同对待（verify 会据此判 FAIL）。
- **文字可精简，但不得失真**：删掉原书的冗余铺陈、重复表述、口语化填充，用更紧凑的话重述；但**重述后必须完整传达原段承载的技术信息**，不能靠省略来「精简」。
- **禁止整段照抄 OCR 文本流**：必须用自己的话重写（公式重写为正确 LaTeX），不得把原书段落整段搬来。注意：「用自己的话重写」≠「删内容」——它指保留全部公式与概念、只压缩表述。
- **判据（合格后应满足）**：① 原段的关键公式一个不少；② 关键概念一个不漏；③ 读起来是在把这件事讲清楚。若合格段落 > 350 字/段且全书出现 ≥6 段之多，通常说明在照抄而非重写，需压缩**表述**（压缩时仍不得丢公式/概念）。含公式的段落受 P 层 `p_verbose` 豁免（被视为内容而非 padding，见 `references/verification.md` P 层）。

### Tier 3 — 证明 / 例子解答（只列核心步骤，步数不限）
- 证明与例子的**解答/证明**都**不逐字重写**，只列**核心步骤**：每步一句话，点出该步的关键动作（关键引理 / 关键恒等式 / 关键归纳 / 关键构造 / 关键交换图）。
- 用 `1. 2. 3. …` 按序编号（**步数按证明实际需要，不限定 3 条**——「1,2,3」只是写法示意；几步就列几步，但必须分条标号、不得写成连续散文墙）。
- 结尾给一句结论（如「故得证」「综上 X ≅ Y」）。
- **禁止**把证明/解答写成连续多段散文、禁止逐句翻译原书 proof paragraph。
- 极短证明（一句话即明）可一句带过。

> ⚠️ 这与「禁止照抄 OCR 文本流」是同一精神的延伸：OCR 是原料不是成品，**非核心内容必须当成原料去消化、而不是当文本去搬运**。verify 的 **P 层 `p_verbose`（顶层长散文）/ `p_proof_verbose`（过长证明块）** 会据此统计，超标即判 FAIL（见 Step 4 / verify 层说明），即使写章 agent 无视本规则也会被闸门拦下。

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

**规则 E — 两阶段批量流程，禁止逐章校验（最高优先级）**：本 skill 将「写初稿」与「校验」彻底解耦为**四阶段批量流程**，**严禁「写完一章就校验一章」**：

- **阶段 1 — 写源语言全部初稿**：连续写完**源语言**的每一章初稿（源语言判定见 规则 F：英文原著书→`ChapterN_*.md` 为源；中文书→`第N章_*.md` 为源；其余语种以原始命名为源）。阶段 1 期间**不做任何 per-chapter verify**。任务一旦启动，Agent 必须连续跑完全书源语言初稿，**中间不得停下询问用户「是否继续 / 推进下一章吗」、不得逐章等待人工确认、不得将「单个章节完成」当成回合结束点**；唯一阶段结束信号是「源语言全部章节初稿写完」。章与章之间**无缝衔接**，全程不向用户发「继续？」之类的追问。
- **阶段 2 — 生成书级配置**：源语言初稿**全部完成**后，用**源语言** `.md` 生成 `<book>/_extract/verify_config.json`（规则 H）。可用 `python verify/make_config.py <extract_dir>` 半自动探测 + 人工核对，或手填；至少含 `ordinal`（+ `language`；四级及更深小节书需显式 `section_types` / `section_depths`）。**翻译派生版不参与配置生成**。
- **阶段 3 — 批量校验源语言**：`python verify/verify_chapter.py --all <extract_dir> <book_dir>` 一次性校验源语言全部章节；未过则用 `--fix` 自动修复后重验，至多 2 次仍不过则继续修，**严禁停下来问用户**。
- **阶段 4 — 派生翻译版并校验**：据已校验的源语言版派生翻译版，再对翻译版跑 `--all` 校验至 PASS。修复方向严格单向（先源后译，见 规则 F）。

🔴 **禁止逐章校验**：阶段 1 写初稿时不得穿插任何 `verify`；配置（阶段 2）与校验（阶段 3/4）都发生在**全部源语言初稿完成之后**，统一批量进行。全书完成后的最终汇报一次性给出。

**规则 F — 源语言优先（双语书：源语言版先写、先校验、先修复；翻译版后派生）**：
- **英文原著书**：先写**英文版** `ChapterN_*.md` 作为「源文件」→ **之后**才据这份已校验的英文版**翻译**出中文版 `第N章_*.md`。中文版是英文版的派生，不是与英文平行、各写各的独立文件。
- **中文原著书**：仅出中文版，无此顺序问题。
- **其他语种原著书**：先写**原著语种版**为源并校验修复，再派生 中文 + 英文两版（同英文书逻辑）。
- **🔴 校验时机（与 规则 E 一致）**：源语言「先校验、先修复」指的是**全部源语言初稿写完后**在 规则 E 阶段 3 **批量**校验 + 修复至 `verify PASS + KaTeX OK`，**不是写完一章英文就校验一章英文**。写初稿（阶段 1）与批量校验（阶段 3）解耦，禁止逐章校验。
- **🔴 修复方向严格单向（最高优先级）**：任何返工 / 修复（含后续全书收尾、补练习、嵌图后复验、或用户要求改某章）都遵循「**先修源语言（英文版）→ 源语言彻底修复完成（复验 PASS + KaTeX OK）→ 再据这份已修定的源语言同步更新翻译语言（中文版）**」。绝不允许翻译语言先于源语言动手，或两边各修各的导致条目 / 编号 / 公式 / 图片分叉。**翻译语言总结必须始终以源语言为唯一蓝本、保持一致。**

**规则 B — 必须按批次增量总结（禁止等全书提取完）**：每一批提取完成就立即检查哪些章可写，即时写总结。增量总结是本 skill 的正确流程。

**规则 C — chapter_map 必须尽早建、且只建一次**：目录页一提取到（`current_max_page >= 5`），立即从目录页建立 `chapter_map.json`。

**规则 D — 超大章总结按「节」拆分（字符数 > 60000 触发，中英文配对拆分）**：当某章总结（中文或英文，**任一**超过 60000 字符）过大时，把它拆成「每节一个文件」。**配对规则：只要该章任一语言超阈值，两种语言都拆**（即使另一语言未超阈值；若该章某语言已拆过而另一语言仍留合并文件，运行脚本会补拆以保持一致）。**只拆分到「节」一级**：子节（`N.M.P`，两个小数点）留在父节文件内，不单独成文件，也不做更细粒度拆分。拆分粒度 = **原书小节标题的格式**，按标题首部编号识别，支持两种书中实际格式：① **节标题式（`§N`，gm 风格）**——标题以 `§` 前缀 + 单个整数开头（如 `## §2. Derived Categories are Triangulated`，节内条目从 1 起号的书，如 Gelfand–Manin《Methods of Homological Algebra》）；② **`N.M` 编号式（Vakil 风格）**——标题首部编号为 `N.M`（**恰好一个小数点**），不论 markdown 级数（## / ### 都算）也不论是否带 § 前缀。两种格式可共存于同一文件，按各自匹配到的顺序拆分。命名：中文 `第{N}章{M}{名称}.md`、英文 `Chapter{N}_{M}{名称}.md`（`{M}` = 节号——`§N` 式即 `N`，`N.M` 式即 `N.M`；名称取自标题编号之后文本，剔除 Windows 非法字符与 `$...$` 数学块）。**章开头的引言/导语（第一个节标题之前的内容）归入第 1 节文件**。由 `format/split_chapters.py` 执行，幂等；**拆分成功后默认删除源合并文件**（加 `--keep` 可保留，因节文件已完整覆盖其内容）；重复运行会跳过已拆分的节文件（`第N章M.xxx` / `ChapterN_M.xxx`），不会二次拆分。

> ⚠️ 拆分判定只看「章」级阈值（任一语言触发即中英文配对拆分），不保证每个节文件 < 60000。若某节本身仍过大（如第3章 3.3 节约 18 万字符），需进一步按 `N.M.P` 子节拆分时，作为独立需求另议。**拆分后 `verify/verify_chapter.py --all` 自动识别节文件并临时合并回整章校验，无需改命令；KaTeX 检查直接对每个节文件跑 `--dir` 即可。**

**规则 G — 公式识别不清楚时，必须按参数路线逐级调参，直到最终识别出公式（禁止放弃、禁止猜测、禁止照抄乱码）**：
- 触发条件：pipeline OCR / `page_*.json` 的 `formulas[].latex` 对某公式产出低置信度、乱码（如 `?`、`v`、`ಊ`、`.notdef`）、或明显错读（如矩阵元素读成 `2` 而实际是 `2/3`、`8` 与分数混淆）时，**不得**直接照抄，也不得按「看不清」跳过，必须走下面的参数路线。
- 参数路线（按顺序升级，逐级尝试，直到多来源交叉验证一致）：
  1. **渲染分辨率升级**：用 fitz 按区域裁剪渲染 150 → 300 → 600 → 1200 DPI（`page.get_pixmap(matrix=fitz.Matrix(dpi/72, dpi/72), clip=fitz.Rect(...))`，坐标用 top-left 原点），配合二值化阈值变体 `th100 / th128 / th140 / th160 / th200 / otsu`（必要时 otsu+膨胀）。
  2. **OCR 引擎参数**：PaddleOCR（pdfextract 环境 2.7.3）须用 `use_gpu=False`（`device="cpu"` 参数无效），并设 `CUDA_VISIBLE_DEVICES=-1` 避免 GPU 初始化报错；识别参数 `det_db_thresh=0.3, text_score_thresh=0.3, use_angle_cls=False, use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False`。注意**检测框高度**：框高明显大于单字符（如 20 vs 15）时表示堆叠结构（如分数 `2/3`），据此判断元素形态。
  3. **区域逐级裁剪**：整页 → 整个公式块 → 单行 → 单个单元格，逐级裁剪识别；用 OCR 检测框坐标回映 PDF 坐标与文字层坐标对照。
  4. **上采样放大**：LANCZOS 2× / 4× / 8× 放大后再识别。
  5. **嵌入图像优先**：若 `page.get_image_info(xrefs=True)` 发现目标区域被嵌入图像覆盖（如修复补丁条），用 `doc.extract_image(xref)` 取**原生像素**处理识别，不要用页面渲染——页面上可能有旧文字层 / 垃圾字形（如 gid65533）覆盖其上。
  6. **字形模板比对**：文字层（texttrace/rawdict）glyph 无法解码时，用 fontTools 解析 CFF 字体（`CFFFontSet` + `BasePen`）把候选字形渲染成二值模板，与目标图像做归一化互相关（NCC）匹配定字形（如 gid48–57 = 0–9）。
  7. **语义自检 + 交叉验证**：识别结果必须满足上下文数学约束（如随机矩阵每行元素和 = 1、分数分子/分母/分数线结构、行和列数一致）；文字层 + OCR + 图像三层来源一致才算确认。
- 最终（**回写替换原 JSON**，先验证、后回写，禁止覆盖未知）：确认后的结果**不得**只写进 md——必须把修正数据**回写替换**进 `_extract/page_*.json` 对应 `text[]` / `formulas[]` 条目字段（如 `text` / `latex` / `conf`），使 `dump_chapter.py` 原样引用、`audit_counts.py` 条数核对、Step 4 校验及后续重写都读取到修正后的数据。要求：① 回写前完成语义自检 + 多来源交叉验证（同第 7 步），未确认的结果禁止覆盖；② 保持 schema 不变、不增删键、不动其他条目，文件保持合法 JSON + UTF-8（禁 mojibake）；③ 可在条目内追加来源标记（如 `"source": "ruleG-ocr-600dpi"`、`"image_xref": 554`）便于回溯，读取方要求纯 schema 则省略；④ 回写后立即 `json.load` 校验并抽查替换字段一致，再继续后续流程。仅「写法差异」而含义相同（如 `1/2` vs `\frac{1}{2}`）不视为修正，以更接近原书印刷的写法为准，无需回写。

---

**规则 H — 书级配置强制前置（最高优先级，校验硬性前置）**：`<book>/_extract/verify_config.json` 是 `verify_chapter.py` / `scan_skeleton.py` 的**唯一配置源**，由代码 `ConfigLoader.require_complete()` 强制：
- **文件缺失** → 仅 WARNING + 沿用默认 ordinal=3（`scan_skeleton` 写初稿可继续；存量书兼容，不阻断）。
- **文件存在但缺 `ordinal`** → 硬报错并退出（`exit 2`）。
- **`section_types` / `section_depths` 显式但非法**（长度不等 / 分量 <1 / 非法角色码 / 首分量 ≠1）→ 硬报错（`exit 2`）。
- 配置字段：`ordinal`（**必填，数组** `List[GroupConfig]`，每个元素 `{type, name, depth, scope}`，详见 `references/verification.md` §4.3 与 `references/layers/b.md`）、`language`、`strict`、`ignore`。`type` 为编号风格码（1–7，判定树见 `references/book_patterns.md` §4）；`name` 为该组标签词（如 `["Theorem"]`，兜底组用 `["uncat"]`）；`depth` 为编号层级数；`scope` 为编号作用域（1=全书 / 2=章 / 3=节）。数组首元素的 `type` 即 `primary_type`，由它自动反推编号模式与小节层级（`section_types`/`section_depths` 现由 primary_type 自动反推，仅四级子小节书 1.1.1.1 需显式覆盖）。
  > ⚠️ 旧格式（整型 `ordinal` 如 `3`，或 `separate_types`）已被 `from_dict` 拒绝，并报 `make_config --force` 迁移提示（exit 2）。分组（per-type / combined）现由多个具名 group（per-type）或单个 uncat group（combined）表达，不再有 `separate_types` 开关。

🔴 **配置是校验的硬性前置，但生成时机在「全部源语言初稿完成后」**：配置**不是边写边填**，而是等**源语言**全部章节初稿写完（规则 E 阶段 1 结束）后，由 agent 依据**源语言版** `.md` 一次性生成（规则 E 阶段 2）。**翻译派生版不参与配置生成**。即：**写初稿阶段（阶段 1）不要求配置就位**（scan_skeleton 遇缺失配置仅告警 + 默认 ordinal=3）；**但任何 `verify` 跑起来之前，配置必须完整**（规则 E 阶段 2 → 阶段 3 批量校验）。

🚫 **明确禁止「写完一章就校验一章」**：阶段 1 写源语言初稿期间**不做任何 per-chapter verify**；配置生成（阶段 2）与批量校验（阶段 3）统一在所有源语言初稿完成后进行。判定不清时，先抽一页原文 / 看 TOC 确定编号与小节层级，再生成文件，**不得依赖静默默认值**。

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

    4. 对每个可写章节（**仅写「源语言」初稿，禁止穿插 verify**）：
        - 按提取流程从 JSON 提取编号项（详见 `references/formatting.md#提取流程`）
        - 按格式规则写**源语言**文件（详见 `references/formatting.md`；源语言判定见 规则 F）
        - **写完后必须按 Step 3.5 嵌入本章图片（强制）**
        - 🚫 **本循环不做任何 per-chapter verify**（遵守 规则 E：禁止写完一章校验一章）。校验统一在源语言全部初稿完成后的 规则 E 阶段 3 批量进行。

    5. if 源语言已写章数 == total_chapters:  break   # 源语言全部初稿写完，转入 规则 E 阶段2/3

    6. if 没有新章节可写:  sleep 5s
```

> **增量 figure**：`figure_index.json` 也按章增量生成，与总结并行。写章总结时可直接引用该章的 `figure_index.json` 用于 E/F 校验。

> 🔴 **本循环是 规则 E 阶段 1（写源语言初稿）**：只产出源语言 `.md` 初稿 + 嵌图，**不跑任何 verify**。源语言初稿全部完成后，按 规则 E 阶段 2 生成 `verify_config.json`、阶段 3 批量校验源语言、阶段 4 再派生翻译版。

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

> 🔴 以下为写作要点**速览**；**强制完整规则以 [`references/formatting.md`](references/formatting.md) 为准（SSOT）**。新增/修改格式规则（编号、块引用、图片、KaTeX 等）只改 formatting.md，本处只更新链接与一句话摘要。

每章遵循以下格式规则，**全部细节详见 [`references/formatting.md`](references/formatting.md)**：

#### 双语书（英文原著）写作顺序：源语言优先

> 本 skill 对英文原著书默认产出「英文版 + 中文版」两文件。两文件**不是平行独立写作**，而是**英文版为源、中文版为派生**。每章严格按以下子流程推进：

1. **写英文源文件** `ChapterN_<Name>.md`：按 `ch<N>_items.txt` 与 `dump_chapter.py` 原文，逐条写出英文定义 / 定理 / 例 / 注 / 练习，套用本 Step 全部格式规则。
2. **英文版完全校验 + 完全修复**：运行格式后处理（见下文「格式后处理」）与 Step 4 校验，**循环修复至英文版 `verify PASS + KaTeX OK`**（首次可用 `verify_chapter.py ... --fix` 自动修格式，再不带 `--fix` 复验确认 exit 0）。**此阶段中文版尚不存在**，目录级脚本（如 `wrap_examples_bq.py`、`fmt_proofs.py`）只会命中英文版，天然实现「先英文」。
3. **据英文版翻译中文** `第N章_<名称>.md`：以第 2 步已校验定稿的英文版为唯一蓝本逐条翻译；条目 / 编号 / 公式 / 图片位置必须与英文版**一一对应**，不得增删或自行发挥。中文版首现术语照旧标 `(English)`。
4. **中文版完全校验 + 完全修复**：重跑格式后处理与 Step 4 校验，**循环修复至中文版 `verify PASS + KaTeX OK`**。
5. **嵌入图片**（Step 3.5）：中英文两版同步嵌入本章被引用的图。

> ⚠️ 若采用多 agent 并行（见 规则 E），目录级脚本（`wrap_examples_bq.py` / `fmt_proofs.py` / `embed_figures.py`）**禁止由各 agent 在并发期运行**（会互相改写半成品），改由主控制器在全书写完后**统一收尾运行**，运行后复验一次。各 agent 的逐章校验（`verify_chapter.py` / `check_katex.py` 均为单文件工具）仍严格按「英文先、中文后」的顺序完成。

- **写作格式规则完整定义见 [`references/formatting.md`](references/formatting.md)（SSOT，本 skill 唯一权威；新增 / 修改格式规则只改该文件）。** 写章时遵循以下大类（细节点开链接）：
- **标题体系**：章 `# 第N章 …`、节 / 子节 `## §N.M …` / `### §N.M.K …`（须带 `§`）
- **条目标签**：`**粗体标签**：`（禁 `###`），编号 1:1 照搬原书印刷号；number-first 体例、gm 体例等特例见 formatting.md
- **块引用**：例 / 证明 / 注进 `>`；条目陈述须顶层独立成行；块内 `$$` 用 `> $$`；引用块连续不截断
- **分隔线 `---`**：仅用于不同顶层条目之间，条目内部禁止
- **公式**：用 `$$`（前空行），编号 `	ag{N.M}`，禁止代码围栏包裹；KaTeX 渲染须成功
- **图片嵌入**：被引用图放引用条目处，未引用不写（见 [`references/formatting.md#图片嵌入规则`](references/formatting.md#图片嵌入规则)）
- **练习收录**：有专门习题标题归拢即省略，无标题穿插即原位保留（见 formatting.md 练习规则）

**写前必须先拿到两份清单（缺一不可）**：

1. **🔴 结构骨架（写作契约，2026-08-02 立为强制）**：
   ```
   python extract/scan_skeleton.py <extract_dir> <ch>
   # 编号模式（三级/两级/cn）由 <extract_dir>/verify_config.json 的 `ordinal` 自动判定，无需 --scheme
   # （规则 H：写初稿阶段 scan_skeleton 遇配置缺失仅 WARNING + 默认 ordinal=3（不阻断）；
   #  配置须在所有源语言初稿完成后生成（阶段 2），且任何 verify 跑起来前必须完整，否则 require_complete() 报 [CONFIG] 并 exit 2）
   ```
   产出 `<extract_dir>/ch<N>_skeleton.txt`，**按原书页码顺序**列出该章全部 `SEC`（节标题）/ `ITEM`（编号条目）/ `EXER`（练习），每条带页码与**印刷标题**。
   这份文件是**契约，不是参考**：
   - 骨架里有几个 `SEC` 就必须写几个 `## §N.M` 节，**顺序照抄**，一个都不能少、不能颠倒；
   - 每个 `ITEM` 都必须在总结里落地。**`EXER`（练习）按 [`references/formatting.md` 的「习题收录规则」](references/formatting.md)处理**：穿插在小节中的习题原位保留落地，章末整块习题（带专门习题小标题 / 整节都是习题）省略不写，故该类 `EXER` 不强制落地。落地的 `ITEM`/`EXER` 相对先后顺序须与骨架一致（骨架顺序 = 原书页码顺序 = 练习该待的「原位」）；
   - `ITEM` 行末的印刷标题必须写进条目标签（见「number-first 体例」规则），不得丢弃；
   - 骨架里没有的编号，不许出现在总结里（无中生有）。
   - 写完后自查：`grep -c '^## §' <md>` 应等于骨架 `SEC` 数；条目/练习编号集合应与骨架一致。
   > 为什么不能只靠 `ch<N>_items.txt`：它只含 verifier 的必备条目键，**不含节标题、不含练习、不含印刷标题**。只拿它写作，必然漏节、乱序、丢标题。（真实事故：Vakil《The Rising Sea》Ch1 漏掉 §1.1、Ch3 漏掉 §3.3/§3.5、Ch2 节序颠倒。）

2. **编号项清单**：按 [`references/formatting.md#提取流程`](references/formatting.md#提取流程) 的提取流程从 JSON 提取，与骨架交叉核对后写作。

**格式后处理**：写完后依次运行：
1. `python format/wrap_examples_bq.py <book_dir>` — 把**顶层**的 `**例/Example**` 条目整体包进 `>` 块引用（fmt_proofs 只合并「已在 `>` 内的例」与其证明，**不会**把顶层例包进块引用，这一步必须先跑）。注意中文「例2.1-3」不能用 `\b` 匹配（汉字与数字间无词边界）。
2. `python format/fmt_proofs.py <book_dir> --number` 统一修复块引用/分隔线格式（内含 `merge_example_block()` 合并例与证明的 blockquote，在 stage1 之前执行）。
3. `python format/fix_katex.py <book_dir>` — 综合修复已知 KaTeX 模式（未闭合 `$`、`$$` 包裹 `$`、断裂命令、CD 语法等）。
4. `python format/check_katex.py <file>` 逐文件复验（**不加 `--fix`**，尤其是中文文件）。
5. `python verify/audit_counts.py <ch> <start> <end> <md_file> <extract_dir>` **逐节核对条数**（强制，见编号规则「条数核对是强制收尾环节」）。报 `FAIL` 须补全条目后重跑至 `PASS`，该章才算写完。

---

### Step 3.5：嵌入图片到总结（强制，位于 Step 4 校验之前）

> **🔴 这是强制步骤，不是可选建议。** 只要该书跑过图片流水线、且 `_extract/figure_index.json` 中存在本章条目（对应 PNG 已在 `_extract/figure/`），写章总结时就**必须**执行本步；跳过它，Step 4 的 E 层（图片嵌入）检查会判 FAIL。

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
- 这一步是 Step 4 校验的**前置依赖**：先嵌图，再跑 `verify/verify_chapter.py`（其图片嵌入检查、G 层检查块连续性）。

---

### Step 4：逐条校验全部规则

**任何一条不通过都算失败，必须修正后重验。** 本 skill 的全部规则已解耦到 `references/` 下，SKILL.md 仅保留主流程与链接，不再内联任何规则细节 —— 新增 / 修改规则只改对应的 `references/*.md` 与必要代码，**本文件无需改动**：

- **🔴 书级配置校验（规则 H）**：`verify_chapter.py` 入口会先校验 `_extract/verify_config.json` 的完整性。若报 `[CONFIG]` 错误（文件在但缺 `ordinal` / `ordinal` 不是合法分组数组 / 首元素 `type` 不合法 / `scope` 不在 1–3），先回规则 H 补齐配置再跑 verify。文件缺失仅警告、沿用默认 ordinal=3（存量书兼容）。`ordinal` 现为分组对象数组，旧整型 / `separate_types` 写法会被拒绝。

- **结构性 / 格式校验层（统一强制关卡）**：由 `verify/verify_chapter.py` 执行，覆盖本 skill 定义的全部校验层。运行 `verify/verify_chapter.py --all <extract_dir> <book_dir>`，**exit 0 才算通过**；`--fix` 可自动修复其中标记为可修复的层，其余须手动确认。各层的顺序、语义、`--fix` 范围、字节契约键集合 —— 全部见 [`references/verification.md`](references/verification.md)（SSOT，唯一权威）。
- **内容保真 / 写作质量关卡**（OCR 噪声修正、UTF-8 无乱码、粗体标签与 `§` 标识、KaTeX 渲染成功、英文标注、输出语种、一次性写齐、文件命名、图片嵌入、公式忠于原文、非核心内容摘要等）：定义见 [`references/formatting.md`](references/formatting.md) 与 [`references/verification.md`](references/verification.md) 对应章节；顶层「核心原则」亦为本类总纲。
- **OCR 无法识别的遗漏标签**：书中确有但 OCR 漏识的条目，按两步法补写 + 标注 + 登记，查漏机制与 over-mark 守卫见 [`references/missing_label_policy.md`](references/missing_label_policy.md)。

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
| `verify/verify_chapter.py` | **统一强制校验关卡**（校验层列表、顺序与 `--fix` 可修复范围见 [`references/verification.md`](references/verification.md)（SSOT）；G 层内含 G扩展/EG 子检查）。`--all` 自动发现章节文件：合并文件（`第N章_*` / `ChapterN_*`）存在则直接校验，否则按规则 D 节文件（`第N章M...` / `ChapterN_M...`）每语言一组，**临时合并回整章再校验**（A 层完整性需整章一次通过），中英文各计一条结果；`--fix --all` 逐节文件单独修复 |
| `format/check_katex.py` | KaTeX 格式校验（被 C 层内部调用）；`--fix` 仅修复格式问题（拆分单行 `$$`、补空行、修缩进等），**不碰 `$` 内容**。当前工作流已用 `fix_katex.py` 替代 `--fix`。 |
| `format/fix_katex.py` | **综合 KaTeX 修复脚本**：一行命令修复所有已知模式（未闭合 `$`、`$$`包裹`$`、断裂命令、CD 图表语法、集合花括号、`$$`内空行等），不含 `--fix` 级联破坏风险。详见下方「KaTeX 问题识别与修复」 |
| `extract/extract_items.py` | 从 JSON 提取全部编号项（中文书）；英文书加 `--lang en` 走英文正则 |
| `extract/scan_items.py` | 两级编号书的独立完整性扫描器 |
| `format/fmt_proofs.py` | 格式后处理：块引用/分隔线/证明格式修复 |
| ~~`format/mathify_plaintext.py`~~ | **已暂停使用**。原功能：裸写数学记号包进 `$...$`（Unicode 上/下标与符号→KaTeX）。停用原因：对已有 `\(...\)` 定界符的文件会造成严重破坏（会把 `\(` 误当作普通字符，产生 `$\\(...$` 坏模式，后续修复脚本连锁损坏）。已被 `format/fix_katex.py` 取代。 |
| `format/fmt_extras.py` | 显示公式/块引用后处理：`dedent` / `normalize` / `split` / `fixgap`（G 层修复）子命令 |
| `format/split_chapters.py` | **规则 D**：把超 60000 字符的章总结按「节」拆成每节一个文件；节标题按两种格式识别：`§N` 节标题式（gm 风格）与 `N.M` 单小数点编号式（Vakil 风格）；`--threshold` 可调，`--dry-run` 只预览不写；拆分成功后默认删源文件，`--keep` 可保留 |
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
| **公式识别不清楚（低置信度 / 乱码 / 矩阵分数错读）** | 按 **规则 G** 参数路线逐级调参直至识别出公式：渲染 DPI 150→1200 → 二值化阈值变体 → PaddleOCR 参数（`use_gpu=False` + `CUDA_VISIBLE_DEVICES=-1`）→ 区域逐级裁剪 / LANCZOS 放大 → 嵌入图像原生像素（`extract_image`）→ fontTools 字形模板 NCC 比对 → 语义自检（如随机矩阵行和=1）+ 多来源交叉验证 |
| **识别出更好的 JSON 数据（规则 G / 嵌入图像 / 人工核对产出比 `page_*.json` 更正确的结果）** | 按 **规则 G 最终步**回写替换：验证确认后把修正数据写回 `_extract/page_*.json` 对应 `text[]` / `formulas[]` 字段（如矩阵 `2/3`、乱码还原），保持 schema 不变 + UTF-8 + JSON 合法，回写后 `json.load` 复验。实例：`page_093.json` 公式条目已按嵌入图像 xref 554 修正矩阵 (b) 的 `2/3`（与 `ch2_problem4_decoded.txt` 一致），后续识别修正均照此回写 |
| 提取时没跑图片（历史数据补图） | 分两阶段运行，`--out` 可选不传 pdf_path（自动从 _extract 上级发现 PDF）：<br>`python figure/extract_figures.py --out "_extract" --book`<br>`python figure/assign_figures.py --out "_extract" --book` |
| 某批提取失败 | 查看 `batch_{start}-{end}.log`，通常 VRAM OOM |
| Chinese mojibake | 写入用 `encoding='utf-8'`，写完后用 `read` 检查 |
| PDF 路径含空格启动静默失败 | 改用 `launch_pipeline.sh`（bash，空格路径安全） |
| **figure/ 目录生成 0 个 PNG（但 JSON 有数据）** | OpenCV 的 `cv2.imwrite` 在 Windows 上对含非 ASCII（中文）字符的路径会**静默失败**，所以检测阶段只写出了 `figure_detect.json` / `figure_index.json` 的元数据，但 `figure/` 下没有实际 PNG。本 skill 的 `figure/extract_figures.py` 已改为 PIL 保存，回跑即可生成；若 `_extract/` 已是历史遗留数据没有 PNG，可写一个 `regen_figures.py` 用 fitz 渲染 + PIL 裁剪，按 `figure_index.json` 的 `page+bbox+file` 重建（参考 `泛函分析导论及应用/_extract/regen_figures.py`） |

---

### KaTeX 问题识别与修复

> 🔴 本节「根因总览 / 模式 / 手动修复」为**速查**；**完整 KaTeX 规则与修复语法以 [`references/formatting.md` 的 KaTeX 规则](references/formatting.md) 为准（SSOT）**。修改 KaTeX 规则只改 formatting.md，本处只更新链接与一句话摘要。

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
