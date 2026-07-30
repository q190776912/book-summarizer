# 校验关卡（Verification）

> 本文档是 `book-summarizer` skill 的校验参考。工作流步骤见 `SKILL.md`，格式规则见 `formatting.md`，图片流水线见 `figure_pipeline.md`。

---

## 目录

- [verify/verify_chapter.py 分层校验](#verify_chapterpy-分层校验)
- [编号体系（三级 vs 两级）](#编号体系三级-vs-两级)
- [--ignore 登记规则](#--ignore-登记规则)
- [M-LAYER：显示公式内无 `>` 前缀](#m-layer显示公式内无--前缀)
- [N-LAYER：块引用内空 `>` 行不超过 1 行](#n-layer块引用内空--行不超过-1-行)
- [常用校验命令](#常用校验命令)

---

## verify/verify_chapter.py 分层校验（D→…→N，含 G 扩展/EG）

`verify/verify_chapter.py` 是**统一强制关卡**，按 **D → A → B → C → E → F → G → G扩展 → EG → H → I → J → K → L → M → N** 顺序输出。**`<extract_dir>` 为必填参数**（该书 `_extract` 目录，无写死默认值，换书必须显式传入）。

> **⚠️ 前置依赖**：#9「图片嵌入正确」与 G 层「引用块连续」是由 **Step 3.5** 的 `figure/embed_figures.py` 生成的——**必须先嵌图、再跑本校验**。未嵌图时 #9 必 FAIL，含 `> **证明/例**` 块却未跑连续性扫描时 G 层必 FAIL。

### 用法

```bash
# 单章
python verify/verify_chapter.py <ch> <start> <end> <md_file> <extract_dir> \
  [--manual overrides.json] [--ignore ignore.json] [--ignore-figure fig_noise.json]

# 整书
python verify/verify_chapter.py --all <extract_dir> <book_dir> \
  [--ignore ignore.json] [--ignore-figure fig_noise.json]
```

**exit 0 的唯一条件**：无 D 层整节缺失、无 A 层 TRULY MISSING、无 B 层 BLOCKING、无 C 层 KATEX ERRORS、且无 E 层图缺失、无 F 层图无效、无 G 层引用块断裂、无 H 层结构标签包裹在块引用内、**无 H 层扩展（陈述进块引用）**、无 I 层条目间缺失分隔线、**无 J 层条目块内多余 `---`**。

### 各层详解

#### ⓪ D 层 — MISSING SECTION / TAIL ORDINAL

直接重扫原始 `_extract` 的 `page_*.json`，与 `.md` 的 `## §` 标题取差集。

- **MISSING SECTION**（阻断 FAIL）：某节在原始 JSON 中既有节标题特征、又有带标签的 `章.节-号` 条目，但 `.md` 无对应 `## §` → 必须补写整节
- **TAIL ORDINAL GAP**（非阻断 WARNING）：某节在 `.md` 中存在，但原始 JSON 里有编号更大的带标签项且缺口 ≤5 → 复核是否漏写尾部条目
- **SUSPECT**（仅提示）：缺口 >5，疑似 OCR 噪声

D 层专门用于堵住 B 层的盲区——B 层只在**已检出节之间**重扫，对**零检出整节不可见**。

> **中英文均受支持（2026-07-27 修复）**：D 层的标签关键词与 two-level 条目正则
> 现同时识别中文（定义/定理/…）与英文（Definition/Theorem/Lemma/Proposition/Corollary/…）。
> 英文标签在 two-level 键名中会归一为中文标签（`Theorem 6.1` ≡ `定理6.1`），
> 保证英文原文书籍 / 英文版总结与 `extract_items` 输出可比。
> 注意：three-level 的 `ENTRY_RE` 本就按**编号**匹配、与语言无关，
> 中英文 `.md` 各自独立对照原书 OCR 校验，任一版漏条目都会各自被 A 层抓到。

#### ① A 层 — TRULY MISSING

提取到了但 `.md` 里完全没有 → 必须补写对应条目，**FAIL**。

#### ② B 层 — BLOCKING

提取时边界/尾部自动复查发现了可能漏掉的候选项 → 必须解决，**FAIL**。
- 真实项则补写并在 `extract_items` 用 `--manual` 登记
- 确为 OCR 乱码/无法修复的交叉引用则记入 `--ignore`

#### ③ C 层 — KATEX ERRORS

运行 `format/check_katex.py` 发现 KaTeX 渲染失败。**具体禁忌清单（转义定界符 `\$\$`、缺空行、行内 `$` 未配对、不支持的宏、嵌套块引用 `> > $$` 等）见 [`references/formatting.md` 的 KaTeX 规则](references/formatting.md)；逐项必须修复，FAIL。**

`format/check_katex.py` 内部调用 `katex_validate.js` 做真实 KaTeX 渲染，能抓出 `\minimize` 这类非法命令、括号不配对等真正语法错误。

`format/check_katex.py --fix` 可自动修正以上第 1–3 项（转义定界符、单行展示公式、缺空行、嵌套块引用展示公式）；第 4–6 项需手动修复。

#### ④ MENTIONED-ONLY

在 `.md` 中只作正文/交叉引用出现，不是独立条目 → 复核，不 FAIL。

#### ⑤ EXTRA

在 `.md` 但提取未检出，通常是被正确过滤的交叉引用 → 仅供参考。

#### ⑥ E 层 — FIGURE COMPLETENESS（可选）

仅当 `_extract/figure_index.json` 存在且含本章 `chapter` 条目时运行。

- **MISSING FIGURE**（阻断 FAIL）：章内 OCR 引用了"图 X.X.X"图注但 `figure_index.json` 无对应 `chapter==N, label==X.X.X` 条目 → 图片提取可能漏检（真漏检），须重跑 `figure/extract_figures.py --ch N` + `figure/assign_figures.py --ch N` 刷新，或手动补图
- **EXTRA**（仅 WARN）：某裁剪图的 `label` 在本章 OCR 里找不到对应图注，疑似误配对

#### ⑦ F 层 — FIGURE VALIDITY（可选，同前提）

`verify/verify_chapter.py` 用 `np.fromfile`+`cv2.imdecode` 逐一打开裁剪图。

- **INVALID**（阻断 FAIL）：缺失文件 / 无法解码 / 单边 <20px
- **SUSPICIOUS**（仅 WARN）：近空白（灰度方差 <50，疑似误检文字块）

无 `figure_index.json`（未跑图片提取）的章节，E/F 两层自动 SKIP，绝不阻断。

#### ⑧ G 层 — QUOTE CONTINUITY（引用块连续性，始终运行）

**针对缺陷**：`> **证明` / `> **例` 引用块内出现**裸空行**（零内容、无 `>` 前缀的纯空行），多数渲染器会把它当成块结束符，于是块被切成好几个独立的引用框——典型症状就是「图/公式跟对应的例子或证明断开了，不是同一个框」。

**重要说明**：此层也用于检查**例/Example 图片是否正确嵌入**。例的图片必须放在例的 blockquote 内（带 `>` 前缀），否则会被视为破坏 blockquote 连续性的内容。

- **QUOTE GAP（阻断 FAIL）**：`> **证明/证/例` 块处于激活态时，遇一裸空行，且其后首个非空行仍是**块内容**（`>` 行，或既非新块起点、也非块边界的行）→ 必须将该裸空行改成 `> `（空引用行），使整段成为连续不断的 `>` 块。
- **允许作为「块间分隔」的裸空行**（不报）：其后紧接的是**新块起点**（`> **证明/例`）或**块边界**（`---` / `## ` / 顶层 `**标签**`）——这类裸空行是「例子块」与「紧随的证明块」之间的正当分隔，保留即可。
- **块内留白一律用 `> `（空引用行）**，不要用裸空行。
- **例/Example 图片必须嵌入到例的 blockquote 内**：若图片出现在例 blockquote 之外（顶层或其他位置），将被视为破坏 blockquote 连续性的内容，触发 G 层 FAIL。

> 该层是**结构性校验，始终运行**（不依赖图片层）。它把之前只能人工抽查的「块连续性」固化成强制关卡——任何书只要含 `> **证明/例**` 块就必须通过。

#### ⑨ G 层扩展 — NESTED BLOCKQUOTE（嵌套块引用检测）

**针对缺陷**：旧版规则要求例子内的证明用 `> > **证明**`（二级嵌套），但现版规则已改为同一层 `> **证明**`。嵌套块引用会导致 KaTeX 公式 `> > $$` 不被识别，且渲染上例子和证明被分割成两个独立框。

- **NESTED BQ（阻断 FAIL）**：检测到行首为 `> > **证明**` 或 `> > **例**` 等嵌套模式 → 必须展平为单层 `>`。
- 与 C 层已有的 `> > $$` 检测互补，确保整份文档的引用层级一致。

### E 层假阳性：OCR 噪声造成的"图 X.X.X"引用

OCR 有时会将正文中的图案/公式误识别为图注（如 Cantor 集构造步骤的图形标注被 OCR 读成"图1.5"），导致 E 层报 "caption(s) referenced in chapter OCR but no matching crop"。此时：

1. **确认页面上是否真有图**：检查该页 `page_XXX.json` 的 `images` 字段是否存在。若缺失 YOLO 也未检测到（`figure_detect.json` 无该页条目），则很可能是 OCR 噪声。
2. **登记豁免**：创建 `_extract/ignore_fig_ch{N}.json`（JSON 字符串数组），将噪声图号加入：
   ```json
   ["1.5"]
   ```
3. **重验**：`verify/verify_chapter.py` 加 `--ignore-figure <extract_dir>/ignore_fig_ch{N}.json` → E 层忽略该图号 → PASS。

> **判断依据**：被 YOLO 检测为 `figure` class 的实体才会存为裁剪 PNG。若 `figure_index.json` 中本章根本无此图号、且对应页面无 images 数据，基本可判定为 OCR 噪声。若检测到但未被命名（`figure_index.json` 有 `chNN_unnamed_K.png` 条目），则是漏配而非噪声，应手动补图（见 figure_pipeline.md#手动补图）。

---

#### ⑩ EG 层 — EXAMPLE-PROOF GAP（例与证明块间空隙检测 + 同行检测）

**针对缺陷**：例的陈述与它的证明之间若出现裸空行（零内容且无 `>` 前缀的空行）或裸 `$$`（无 `>` 前缀的展示公式），会打断 blockquote，使例子和证明被渲染为两个独立框。同时检测例与证明在同一行的问题（`> **例**：...**证明梗概**：...`）。

- **SAME-LINE EXAMPLE+PROOF（阻断 FAIL）**：`> **例**` 行内容同时包含 `**证明**` 标记——必须拆分为两行：`> **例**：描述。` 和 `> **证明梗概**：步骤。`。
- **EXAMPLE-PROOF GAP（阻断 FAIL）**：在 `> **例**` 块的陈述与证明之间检测到裸空行或裸 `$$`，且空隙后首个非空行仍是该例的证明（`> **证明思路**` 或 `> **证明**`）→ 必须将裸空行改为 `> `（空引用行），将裸 `$$` 改为 `> $$`，使例段成为连续 `>` 块。
- **允许**：块间分隔的裸空行（其后为 `---` / `## ` / 顶层 `**标签**` / 另一个 `> **例**` 的块首行）。
- 与 G 层（QUOTE GAP）互补：G 层覆盖所有 `> **证明/例**` 块的普遍连续性，EG 层专门针对「例的陈述→证明」之间的特定空隙。

#### ⑪ H 层 — 结构标签包裹块引用（STRUCTURAL LABEL IN BLOCKQUOTE，始终运行）

**针对缺陷**：定义/定理/引理/推论/命题/断言/公理等**结构性标签**若被写进 `>` 块引用内（如 `> **引理33.5**：…`），渲染时会被吞进前一个证明/例的块，造成标签丢失、层级错乱。

- **STRUCTURAL BLOCKQUOTE（阻断 FAIL）**：检测到 `> **<结构性标签>**` 形式（标签在 `>` 块引用前缀之后）→ 必须将标签移到顶层（`**引理33.5**：…`），其证明另起 `> **证明**：…` 块。
- **允许**：例/证明块（`> **例**` / `> **证明**`）本就在块引用内，不在此层范围（由 G 家族覆盖）。

> 与 G 家族互补：G 家族保证块内连续，H 层保证结构性标签不被块引用吞掉。

#### ⑪a H 层扩展 — STATEMENT IN BLOCKQUOTE（陈述内容包裹块引用，ISSUE1，始终运行）

**针对缺陷**：⑪ 只管「结构性标签本身」是否被 `>` 吞掉；但有些书把**条目陈述区里的枚举子句 / 展示公式 / 子点列表**也写进了 `>`（如 `> （N）` / `> **(N)**` / `> $$` / `> - （a）` / `> - (a)`），位于标题行到首个 `> **证明/例/注**` 之间。这些属于该条目的**陈述内容**，必须顶层书写——只有证明 / 例 / 注 / 脚注才进 `>`。错误写法会被渲染器当成上一个 `>` 块的延续，破坏层级（真实事故：冯琦《集合论导引 第三卷》`第3章` 引理 3.25 / 3.28、定义 3.13 的陈述公式与枚举子句曾被裹进 `>`）。

- **STATEMENT-IN-BLOCKQUOTE（阻断 FAIL）**：在某个结构性条目（定义/定理/引理/推论/命题/断言/公理/式）的**陈述区**内，检测到 `>` 包裹的 `（N）` / `**(N)**` / `$$` / `- （a）` / `- (a)` → 必须解包到顶层（`> （N）` → `**(N)**`、`> **(N)**` → `**(N)**`、`> $$` → `$$`、`> - （a）` → `- (a)`）。
- **不报**（合法保留在 `>` 内）：示例块 `> **例N**` 及其内部的 `> **(N)**` 子点——示例整体本就应在 `>` 内；脚注 `> ^{...}`；证明 / 注块 `> **证明...` / `> **注...`。
- **判定边界**：陈述区 = `[标题行+1, 第一个合法 `>` 块起点)`，合法块起点为 `> **证明` / `> **例` / `> **注` / `> ^{`。
- **自动修复**：`verify_chapter.py --fix` 的 `fix_h_statement_in_blockquote` 仅当某条目的陈述区含 structural 标记才整体 unwrap，避免误拆合法注记块。

> 与 ⑪ 互补：⑪ 管「标签是否被 `>` 吞」，⑪a 管「陈述内容是否被 `>` 吞」。两者皆由 H 家族覆盖，`--fix` 可一并自动修复（顺序：H 结构标签 → ⑪a 解包陈述 → G → I → J）。

#### ⑫ I 层 — MISSING SEPARATOR（条目间缺失 `---` 分隔线，始终运行）

**针对缺陷**：定义/定理/引理/推论/命题/断言/公理/例之间必须用 `---` 分隔。缺少 `---` 会使相邻条目在视觉上合并、阅读时无法区分边界。

**重要说明**：证明（思路/梗概/概要）是定理/定义等条目的**内部附属块**，**不是独立条目**，因此：
- 定理/定义与其证明**之间不应有 `---`** （因为证明属于该条目）
- `---` 仅用于分隔**独立条目**之间（如 定理→定理、定理→例、例→定理 等）

- **MISSING SEPARATOR（阻断 FAIL）**：两个相邻的条目行（`**定义N.N**`、`> **例N**` 等）之间没有 `---` 分隔线，且中间没有节标题（`##`）作为自然分隔 → 必须在两条目之间的空白区域插入一行 `---`（前空一行、后空一行）。
- **允许**：节标题（`## §`）分隔的条目对不报 — 标题本身充当视觉分隔。
- **跳过**：相隔超过 100 行的条目对（通常跨越整个节，节标题可能被透传逻辑漏检）。
- **自动修复**：运行 `format/fmt_proofs.py <book_dir>` 自动扫描并补齐缺失的 `---` 分隔线（幂等，已有则跳过）。

> 本层（I，条目分隔）与 G 家族互补：G 家族检查引用块连续性，I 层检查独立条目间的 `---` 分隔线。运行 `format/fmt_proofs.py` 可自动修复 I 层所有问题。

##### ⑫a 定理/证明间无 `---`（I 层行为与手动复核）

While there is no dedicated automated layer for checking `---` between a theorem and its proof, this is correctly handled by the I-layer's natural exemption:

1. **I-layer** (`check_i_separators`): Ensures `---` exists between independent items (theorem→theorem, theorem→example, etc.). Since a proof is **NOT** an independent item (it belongs to the preceding theorem), the I-layer will **NOT** flag a missing `---` between theorem and proof — which is correct.

2. **Manual verification** (per Step 4 rule #13): During manual review, confirm that theorems/propositions and their proofs do **not** have a `---` separator between them. The proof (whether `> **Proof sketch**` or `> **Proof**`) should directly follow the theorem statement without intervening `---`.

   - ❌ Wrong (extra `---` between theorem and proof):
     ```
     **Theorem 20.6**: ...

     ---

     > **Proof sketch**: ...
     ```
   - ✅ Correct (proof directly follows theorem):
     ```
     **Theorem 20.6**: ...

     > **Proof sketch**: ...
     ```

> This applies to all theorem-like items (定理/定义/命题/推论/引理) and their corresponding proof blocks. The rule holds regardless of whether the theorem is top-level and the proof is in a blockquote, or both are in the same blockquote (as with Examples).

##### ⑫b J 层 — 条目块内多余 `---`（始终运行，阻断）

**针对缺陷**：顶层条目（定义/定理/引理/推论/命题/断言/公理）的「块」内部不得出现 `---` 分隔线。块的范围 = 标题行 到 其全部 `**(N)**` 子点。具体覆盖两种情形：

- **标题 ↔ 首个子点**：`**引理3.1**` 与其 `**(1)**` 之间插了 `---`。
- **子点 ↔ 子点**：`**(i)**` 与 `**(i+1)**` 之间插了 `---`。

**关键**：`---` 只用于分隔两个*不同的顶层条目*（I 层语义）。条目块内部必须直接连写——标题 → 空行 → `**(1)**` →（接续文本 / `$$` 公式）→ `**(2)**` → …，全程无 `---`，参照 `**引理3.3**` 写法。`---` 上方即使是子点的接续文本或 `$$` 公式（而非 `**(i)**` 标签本身），它仍属条目内部，必须删除。

**实现（in_item 跨行追踪，`check_item_header_dash`）**：逐行扫描，维护 `in_item` 标志——
- 遇到 `**LABEL**` 标题行或 `**(N)**` 子点行 → `in_item = True`；
- 遇到 `## ` 节标题或 `>` 块引用行 → `in_item = False`（块结束）；
- 遇到顶层 `---` 且 `in_item == True` 且其后第一个非空、非块引用行是 `**(N)**` 子点 → 记为违规。

这样即使子点跨多行（接续文本 / 公式在 `---` 上方），也能准确识别，而两个不同顶层条目之间的 `---`（其后是另一个 `**LABEL**` 标题）不会被误报。

**自动修复**：`verify/verify_chapter.py --fix` 调用 `fix_item_header_dash` 删除条目块内所有 `---`（并合并其后的单个空行），幂等。

**阻断性**：J 层违规计入 `problems`，非零即 `FAIL`（exit 1），必须 `--fix` 或手动删除后重验。

### 图片嵌入位置（手动校验）

E/F 层**只校验图片的存在与文件有效性**，**不**校验「图是否放在引用它的条目处」。图片嵌入的位置正确性（即「对应定理引理等的图，放在对应位置」）由 `references/formatting.md#图片嵌入规则` 规定，写作时按 caption→条目编号的映射执行。verify 阶段人工抽查 `figure_index.json` 的 `caption` 与 `.md` 中图块前后文是否吻合即可。

> **块连续性已自动化**：图片是否「跟对应的例/证在同一个连续 `>` 框内」，现在由 **G 层**强制校验（裸空行切断块即 FAIL），无需人工抽查。人工只需确认「图放的是**哪个**条目」（映射正确性），这部分仍是 G 层不覆盖的。

### ⑬ 公式忠于原文（手动校验）

**`page_XXX.json` 的 `formulas[].latex` 是原始 PDF 公式内容的唯一凭据**。写公式时必须对照 JSON 确认数学语义一致。允许修正 OCR LaTeX 编码噪声（如 `\pmb{\mathscr{R}}` → `\mathcal{R}`），但**禁止篡改数学语义**（如把空集 `\emptyset` 改成数字 `0`）。

手动抽查每章 2–3 个展示公式，确认：
- 运算符（∩、∪、⊂ 等）与原书一致
- 数学常量/对象（0、∅、ℕ、ℝ 等）与原书一致
- 变量名与函数名与原书一致
- 仅 OCR LaTeX 编码噪声被纠正，**数学语义未改变**

**任何语义替换（如 `∅ → 0`、`∩ → ∪`）= FAIL**，必须修正。

---

## 编号体系（三级 vs 两级）

`extract/extract_items.py` 与 `verify/verify_chapter.py` 默认按**三级**编号 `章.节-号`（N.S-N）工作。**但部分中文教材用两级编号 + 双计数器**，默认三级正则会把公式碎片/集合枚举误读成幻影键，导致虚假 `TRULY MISSING`。

### 两级编号典型：周民强《实变函数论》第三版

- 定义：独立每章计数（`定义1.1`…`定义1.33`）
- 定理/引理/推论/命题：**共用一个连续计数器**（`定理1.1`、`引理1.2`…`命题`…，1.1–1.27 连续）
- 例：按节各自重编（`> **例1**：`）

### 启用方式

- 在 `chapter_map.json` 每章加 `"scheme": "two-level"`，`verify --all` 自动启用
- 或单章显式 `extract/extract_items.py ... --scheme two-level` / `verify/verify_chapter.py ... --scheme two-level`

### 判定与处理

详见 `references/book_patterns.md`（含 OCR 对 `§` 漏识为 `S`/`8` 的现象、`--ignore` 噪声键登记规范、判定树）。遇到新书先对照判定树选对 scheme。

> 两级书的**例完整性**不进 `extract_items`/`verify` 的 A/B 层（例按节重编、跨节重复），统一用 `extract/scan_items.py` 做独立连续性核验（权威）。

---

## `--ignore` 登记规则

`--ignore <extract_dir>/ignore_ch{N}.json` 用于登记**已确认**不必阻断校验的键。该文件**放在本书 `_extract` 目录下**，不进 skill 目录。

1. **作用域：每章一个文件**。`ignore_ch{N}.json`（JSON 字符串数组，如 `["1.7-0"]`），随章传入 `--ignore`。**禁止全局单一文件**。
2. **仅允许忽略两类键**：
   - **(a) OCR 乱码**：提取自破碎/无意义文本块，且全书无对应真实条目
   - **(b) 残留交叉引用**：书中对某条目的引用（"见3.3-1"之类），提取误判为条目
3. **禁止忽略真实条目**：书里确有、应独立成条的编号项，**绝不可进 ignore**。
4. **举证责任**：每条 ignore 必须能在 raw 页面文本中定位到来源块并确认是乱码/交叉引用。
5. **暂定性质**：ignore 非永久删除。若后续发现该键实为真实项，必须从 ignore 移除并补写。
6. **B 层 BLOCKING 解决优先级**：先尝试补真实项；仅当确认是 (a)/(b) 时才进 ignore。

### `--ignore-figure` 图片豁免

`--ignore-figure fig_noise.json`（JSON 数组 `["6.7.9"]` 或字典）登记 OCR 噪声图豁免。
脚本会自动合并 `_extract/ignore_ch{N}.json` 与 `_extract/ignore_fig_ch{N}.json`（存在即读）。

---

## K-LAYER：编号列表后证明块的空行检查

**强制规则**：当定理/定义的陈述含 4-空格缩进的编号列表（`    N.`），且其后紧接 `> **证明**` / `> **证明思路**` 块引用时，列表末项与证明块之间**必须有一空行**，否则证明块渲染时会视觉上对齐编号项而非定理外层。

- `--fix` 自动在列表末项与 `> **证明**` 之间插入空行。

## L-LAYER：分隔线 `---` 上下需有空行

**强制规则**：每个 `---` 分隔线上方和下方都必须紧邻一空白行（即 `正文\n\n---\n\n正文` 格式）。无空白行时 `---` 可能被误解为 setext 标题下划线，或被某些渲染器吞没，导致条目间的视觉分隔不一致。

- `--fix` 自动在 `---` 上下补缺失的空白行。

## M-LAYER：显示公式内无 `>` 前缀

**强制规则**：`$$...$$` 显示公式块内部的每一行都不能以 `>`（块引用标记）开头。若块引用上下文中的 `>` 泄漏进公式块，KaTeX 渲染会失败，因为 `>` 在数学模式中是一个非法字符。

- `--fix` 自动剥离 `$$...$$` 内部的 `>` 前缀。

## N-LAYER：块引用内空 `>` 行不超过 1 行

**强制规则**：在 `> **证明**` / `> **例**` / `> **注**` 等块引用内，连续的空 `>` 行（仅有 `>` 或 `> ` 无其他内容）不得超过 1 行。过多的空 `>` 行是提取噪声或视觉填充，会不必要地增大文件体积。

- `--fix` 自动删除多余的空 `>` 行（保留第 1 行）。

## 常用校验命令

```bash
# 单章校验（最常用）
"<python>" verify/verify_chapter.py <ch> <start> <end> <md_file> <extract_dir>

# 整书校验
"<python>" verify/verify_chapter.py --all <extract_dir> <book_dir>

# 单独跑 KaTeX 校验定位行号
"<python>" format/check_katex.py "<file_path>"

# 两级书完整性扫描（独立于 verify）
"<python>" extract/scan_items.py <ch> <start> <end> <extract_dir>

# 格式后处理（verify PASS 后美化；自动修复 I 层缺失分隔线 + 拆分同行例证明）
"<python>" format/fmt_proofs.py <book_dir>
"<python>" format/fmt_proofs.py <book_dir> --number  # + 证明步骤编号
"<python>" format/fmt_proofs.py <book_dir> --check   # 仅检测标题下分隔线，不改
```
