> 🔴 **本文件是该领域规则的唯一权威详细说明（SSOT）**。`SKILL.md` 与代码注释只引用此处、不重复描述；新增/修改该领域规则只改本文件。

# 格式与内容规则（Formatting & Content Rules）

> 本文档是 `book-summarizer` skill 的格式参考。工作流步骤见 `SKILL.md`，图片流水线见 `../../figures/ref/figure_pipeline.md`，校验关卡见 `../../../../verify/verify.md`。

---

## 目录

- [OCR 噪声处理原则](#ocr-噪声处理原则)
- [硬性要求 0–5](#硬性要求-05)
- [编号规范](#编号规范)
- [双语规则与输出语种](#双语规则与输出语种)
- [编号项格式模板](#编号项格式模板)
- [KaTeX 规则](#katex-规则)
- [提取流程（从 JSON 提取编号项）](#提取流程从-json-提取编号项)

---

## OCR 噪声处理原则

OCR on scanned mathematical textbooks produces **noisy text and severely corrupted LaTeX formulas**. This is expected and not a bug. The correct approach:

**OCR text → understand → correct → write, NOT OCR text → copy → paste.**

- **正文 (body text)**: Usually readable (70-95%). Use directly after correcting obvious encoding artifacts.
- **公式 (formulas)**: Usually severely garbled (e.g. `\pmb{\mathscr{R}}` for $\mathcal{R}$). **NEVER copy these directly.** Read the formula's semantic intent from the broken LaTeX + surrounding context, then rewrite it correctly from your knowledge of the subject.
- **定理/定义编号 (theorem/definition numbers)**: Usually legible. Use directly.
- **节标题 (section headings)**: Usually legible. Use directly.

**When in doubt** about a specific formula or concept, fall back to your knowledge of the textbook's subject matter.

## 核心原则

The summary must mirror the original book's content faithfully:

- **允许修正 OCR 噪声**：编号模糊时还原（`定? 2.?-1` → `定义2.8-1`），内容模糊时基于上下文 + 学科知识复原原意
- **允许适度精简**：精简的是表述不是内容——压缩冗余铺陈，但不得省略任何编号项，也**不得省略描述性内容（动机/直观/导语等）中的公式与概念**（详见 SKILL.md「Tier 2 描述性内容」）
- **不允许无中生有**：书本没讲的概念不要编进去，书本没出现的编号不要硬加
- **不允许统一风格**：不得为美观把原书的 `定义2.1.1` 改成 `定义2-1-1`
- **不允许创造编号**：无编号章节不强行编号

---

## 硬性要求 0–5

### 0. Never Trust OCR Formulas — Always Correct and Rewrite

This is the most frequently violated rule. OCR-produced LaTeX for formulas is **almost always wrong**. You MUST:

- Read the noisy formula to infer what the book intends
- Write the **correct** LaTeX from your knowledge of the textbook + contextual clues from surrounding OCR text
- **Never copy OCR formula output directly** into the markdown summary
- If unsure, reconstruct the formula from the surrounding text and your knowledge of the subject

**Bad** (copying OCR noise): `\| x _ { \mathfrak { n } } - x _ { \mathfrak { m } } \| ^ { 2 } = \int _ { 0 } ^ { 1 } [ x _ { \mathfrak { n } } ( t ) - x _ { \mathfrak { m } } ( t ) ] ^ { 2 } d t`

**Good** (writing correct known formula): $\|x_n - x_m\|^2 = \int_0^1 [x_n(t) - x_m(t)]^2 dt$

### 1. No Mojibake / Encoding Corruption

The Chinese text MUST be valid, readable UTF-8. Historically files were written with Chinese text double-encoded (UTF-8 bytes decoded as GBK then re-saved), producing unreadable garbage like `绗?绔?闅忔満鍙橀噺`.

- **Write the file as UTF-8** and verify it opens as readable Chinese. Never write through a toolchain that re-encodes (e.g. passing Chinese filenames through `cmd /c` or a non-UTF-8 shell mangles them).
- **After writing each file, spot-read the first few lines** (with the `read` tool) to confirm the Chinese is legible.
- When running `../script/check_katex.py` on Chinese-path files, pass the paths **directly** to the `pdfextract` Python executable, NOT through `cmd /c`.

### 2. Format — Bold Inline Labels for Items, Blockquote for Examples, NO Item-Headings

Definitions, theorems, propositions, corollaries, lemmas, axioms, and remarks MUST be written as **bold inline labels** (`**标签**：`). **Examples** use blockquote (`> **例...**：`). Using `### 定义 3.1` etc. is a format violation.

- Correct (Chinese): `**定义3.1（条件概率）**：` followed by the statement text.
- Correct (English): `**Definition 3.1 (Conditional Probability)**:` followed by the statement.
- Correct (example): `> **例3a（事故易发性）**：` / `> **Example 3a**:`.
- The ONLY `###` headings allowed are genuine **subsection dividers** under a `##` section, and they MUST carry the `§` prefix (e.g. `## §3.2 节名`, `### §4.8.1 小节名`).
- If a source file already uses the bold-inline style, match that exactly — do not introduce `###` headings for items.
- **gm 体例书例外（条目即小节标题，如 Gelfand-Manin《Methods of Homological Algebra》）**：这类书把条目印成小节标题、每节内从 1 起号（`1. Main Definitions`、`3. Proposition.`）。总结文件中这些**条目小节标题用 `### N. Title`**（不加粗、不加冒号、照原书标题文字原样，含句号），`## §N.` 节标题照旧。**`###` 子节标题下方不得紧接 `---` 分隔线**——标题本身就是条目分隔，其下直接接内容/子点；`---` 只允许在条目与条目之间（上一个条目内容与下一个 `###` 标题之间）。禁止写成 `**N. Title**` 内联加粗，也禁止拼造「节.条」编号。gm scheme 的 verify 工具（`GM_ENTRY_RE`）同时识别 `### N. Title` 与旧 `**N. Title**` 两种形式，机器键均为 `标签I.S-N`。条目内的结构性标签（Definition/Proposition/…）仍在 `###` 标题内，陈述顶层、证明/例进块引用的规则不变。

**⚠️ 结构性标签（定义/定理/引理/推论/命题/断言/公理）必须顶层，禁止进块引用**：这些「条目陈述」一律独立成行、写在块引用 `>` 之外。只有 **证明（思路/梗概/概要）** 与 **例/Example** 才用 `>` 包裹。把一个结构性标签写成 `> **引理X**` 是格式错误——它会把该条目吞进上一个 `> **证明**` 块引用，破坏章节结构。

- ❌ 错误（引理被裹进证明块引用）：
  ```
  > **证明概要**：… 由下列引理分类：
  > **引理33.5（高斯整除引理）**：设 α=a+bi 为高斯整数。
  > - (a) …
  ```
- ✅ 正确（引理顶层，证明另起块引用）：
  ```
  > **证明概要**：… 由下列引理分类。

  ---

  **引理33.5（高斯整除引理）**：设 α=a+bi 为高斯整数。
  - (a) …
  > **证明**：…（引理自身的证明，可进块引用）

  ---

  > **证明（定理 续）**：由引理 33.5 … 证毕。
  ```

> 此类「标签被吞进块引用」的缺陷，旧版 `../script/fmt_proofs.py` 的 `repair_leaked_bq` 也会自动制造（它曾把一书的 48 章中 34 处独立 `**定理**` 误包进前一个证明）。**当前版 `../script/fmt_proofs.py` 已修复**：默认只跑 stage1（补 `---`、把独立证明包进引用），不再运行会吞并标签的 repair 步骤，且把独立成行的结构性标签识别为硬边界，绝不吞并。写作时仍须主动遵守本规则，不要依赖后处理兜底。

### 2a. Theorems/Propositions and Their Proofs — No Separator Between

**A theorem/proposition/lemma/corollary (top-level) and its proof (in blockquote) MUST NOT have a `---` separator between them.** The proof is an internal attached block of the theorem, not a separate item.

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

The `---` separator is only used between **independent items** (theorem→theorem, theorem→definition, example→theorem, etc.). A proof sketch / proof is NOT an independent item — it belongs to the preceding theorem.

> This rule applies regardless of whether the theorem is top-level and the proof is in a blockquote, or both are in the same blockquote (as with Examples). In both cases, the theorem/statement and its proof form one continuous unit without `---` between.

### 2b. Blank Line Between Numbered List and Proof Blockquote

**When a theorem/definition contains a numbered list (4-space-indented `N.` items) followed by a `> **证明**` / `> **证明思路**` blockquote, there MUST be a blank line between the last list item and the proof blockquote.** Without it, the proof blockquote visually aligns with the numbered items rather than the theorem's outer level, breaking the structural layering.

- ❌ Wrong (proof aligns with numbered list):
  ```
  **定理5.8**：设 $X$ 是一个无限集合。
      1. $X$ 上的任意一个滤子都可以扩展成为 $X$ 上的一个超滤子；
      2. 如果 $E \subseteq \mathcal{P}(X)$ ...
      > **证明思路**：(1) 设 $F$ 是 $X$ 上的滤子...
  ```
- ✅ Correct (blank line separates list from proof):
  ```
  **定理5.8**：设 $X$ 是一个无限集合。
      1. $X$ 上的任意一个滤子都可以扩展成为 $X$ 上的一个超滤子；
      2. 如果 $E \subseteq \mathcal{P}(X)$ ...

      > **证明思路**：(1) 设 $F$ 是 $X$ 上的滤子...
  ```

This rule is enforced by the K-LAYER checker (`check_proof_after_list`) in the verification pipeline.

### 2c. Blank Lines Around `---` Separators

**Every `---` separator line MUST have a blank line immediately above AND below it.** Without blank lines, the `---` may be misparsed as a setext-style heading underline or inconsistently rendered across different markdown viewers.

- ❌ Wrong (no blank lines around `---`):
  ```
  **定义7.2（类型）**：...
  ---
  **定理7.1（覆盖定理）**：...
  ```
- ✅ Correct (blank lines around `---`):
  ```
  **定义7.2（类型）**：...

  ---

  **定理7.1（覆盖定理）**：...
  ```

This is enforced by the L-LAYER checker (`check_separator_blank_lines` / `fix_separator_blank_lines`) in the verification pipeline. `--fix` automatically inserts missing blank lines.

### 2d. No `>` Lines Inside Display Math (`$$...$$`)

Every line between `$$` opening/closing fences must be formula content only — **no `>` blockquote markers**. If a `>` leaks inside `$$...$$`, KaTeX treats it as a math-mode character and either fails to render or produces garbage.

- ❌ Wrong (blockquote `>` inside math):
  ```
  > $$
  > 
  > \mathcal{A} = \{c_0, F_s, P_<\}
  > 
  > $$
  ```
- ✅ Correct (clean display math):
  ```
  > $$

  \mathcal{A} = \{c_0, F_s, P_<\}

  > $$
  ```

This is enforced by the M-LAYER checker (`check_displaymath_gt` / `fix_displaymath_gt`). `--fix` automatically strips `>` from lines inside `$$...$$`.

### 2e. No Excessive Empty `>` Lines Inside Blockquotes

Within a blockquote (`> **证明**` / `> **例**` / `> **注**`), consecutive empty `>` lines (lines that are exactly `>` or `> ` with no other content) must be limited to at most 1 between content-bearing lines. Excessive empty `>` lines are extraction noise that bloats the file.

- ❌ Wrong (5 empty `>` lines between items):
  ```
  > (1) 第一个条件
  > 
  > 
  > 
  > 
  > 
  > (2) 第二个条件
  ```
- ✅ Correct (single empty `>` line between items):
  ```
  > (1) 第一个条件
  > 
  > (2) 第二个条件
  ```

This is enforced by the N-LAYER checker (`check_excessive_bq_empty_lines` / `fix_excessive_bq_empty_lines`). `--fix` automatically deletes excess empty `>` lines.

### 3. All Examples Must Be Retained

Do NOT trim or selectively keep examples. Every `例` / `Example` from the book must be included.

- **Keep ALL examples**, not just 0–3 per section.
- Preserve original example numbering (e.g. keep `例 3a` as `例 3a`).
- **习题/练习题（exercises）收录规则**（2026-07-31 修订）：判定标准是有无专门的习题小标题（「练习」「习题」「Exercises」「Problems」等）——**有标题归拢的集中习题块** → 一律省略（含整节习题的节）。**无专门标题、以穿插形式出现的习题**（散落在正文条目间，或虽在节末但无习题标题归拢）→ 保留，在原位写出（OCR 噪声需重写正确 LaTeX），可附提示。简言之：有标题归拢即省，无标题穿插即留。

### 4. All Labeled Items Must Be Included

教材中**带标签**的条目（定义/定理/命题/推论/引理/例）必须写入总结。

| 标签 | 编号格式 | 规则 |
|------|---------|------|
| 定义/定理/命题/推论/引理 | 任意级别（1级 `定理1`、2级 `定义1.1-1`、3级 `定义2.1.1`）或不编号 | **全部必录** |
| 无标签但有独立编号段（如 `2.8-4 Norm`） | 任意级别 | **全部必录** |
| 明确标"例"或"Example" | 任意级别 | **全部收录** |

关键原则：
- **有标签就有条目**：只要写了"定理""定义""命题""推论""引理"，无论带不带编号，都在总结中给出
- **无标签但有裸编号**（如 `2.8-4 Norm`）：同样必录（它不是"例"）
- **编号模糊时 → 基于上下文还原**
- **内容模糊时 → 基于原文修正**
- **不允许"统一风格"**：不得为了美观把原书的 `定义2.1.1` 改成 `定义2-1-1`，反之亦然
- **🔴 禁止「裸项」伪类别标签 + 类别词位置照书**：skills 没有任何"裸项"类别。`**N.S-N 裸项（…）**：` 是 agent 擅自发明的写法，必须清除。
  - **类别词位置 1:1 照搬原书印刷标题**：原书标题是「编号+类别」（如 `4·1-1定义`、`4·3-3定理`）就编号在前；是「类别+编号」（个别书把标题印成「定理 4.3-3」）就类别在前。**不要**把所有条目强行统一成「编号在前」或「类别在前」一种格式——书上怎么写就怎么写。
  - 书中该条目**有明确类别**→ 按其**真实类别**写标签（`定理`/`定义`/`引理`/`推论`/`命题`/`例`）。如 4.12-2 = 开映射定理 → `**4.12-2 定理（开映射定理）**`；10.5-3 标明「引理」→ `**10.5-3 引理（…）**`。
  - 书中该条目**本就无类别**、只是裸编号段（如 `2.8-4 Norm`）→ 照原书裸编号写（`**2.8-4 Norm**：…`），**不要**套「裸项」二字；也不要为"好看"硬塞一个类别。
- **🔴 禁止章末 `## 图片索引` 附录**：图片只做**内联嵌入**（见下方嵌入规则），数据来自 `_extract/figure_index.json`；`figure_index.md` 仅是便于粘贴的辅助文件，**不并入**章总结。章末不得追加图片清单/索引栏。

> **常见错误**：看到 `2.8-4 Norm` 这种裸编号就以为是"例子"而跳过。**这是错的**——它没有"例"标签，必须收录。

**每项单独列出，禁止合并**：每个编号项必须写成独立的 **粗体标签条目**，不得将多个编号项合并到同一段文字中。

### 5. Never Fabricate Item Numbers

**Every numbered item label MUST originate from the book's actual content.** You are strictly forbidden from inventing item numbers that do not appear in the source.

- Do NOT add a numbered label to narrative text that lacks one, even if the content "feels like" a definition.
- Do NOT create duplicate labels for the same number.
- If the book introduces a concept without a formal numbered label, write it as **narrative text** using bold for the term name (e.g. `**换位子 (Commutator)**：…`), NOT as a fabricated labeled item.

**Verification**: `../../../../verify/script/verify_chapter.py` checks that every extracted item key appears in the `.md`. Keys that appear in the `.md` but are not in the extraction are reported as **EXTRA** — review every EXTRA key.

### 6. Formula Content Must Be Faithful to the Original (No Semantic Substitution)

**The page JSON (`page_XXX.json` → `formulas[].latex`) is the ground truth for the original PDF's formula content.** While OCR LaTeX encoding noise (e.g., `\pmb{\mathscr{R}}` → `\mathcal{R}`) may be corrected, the **mathematical semantics** (operators, operands, relations, set symbols, constants) must be preserved exactly.

- ❌ **Wrong (semantic change)**: PDF shows `= \emptyset` (空集), summary writes `= 0` (数字零) — two mathematically distinct objects.
- ✅ **Correct**: PDF shows `= \emptyset`, summary writes `= \emptyset`.
- ✅ **Allowed**: PDF JSON has `{\cal L}_{A_c}`, summary writes `L_{A^c}` (same meaning, notation normalization allowed).
- ❌ **Wrong**: PDF shows `\cap`, summary writes `\cup` (operator change).

**Checking**: Before writing each display formula `$$...$$`, cross-reference with the corresponding page JSON's `formulas[].latex`. The formula's mathematical intention must match the original, even if the LaTeX encoding is cleaned up.

---

## 编号规范

Numbering in OCR output is often corrupted. Two-step approach:

1. **Decipher the original**: Look at broken OCR + surrounding context to infer what the book actually shows
2. **Restore the original**: Write the number as the book intended it

Common patterns (after correction):
- **Dash**: `N.S-N` (e.g. `定义1.1-1`)
- **Dot**: `N.S.N` (e.g. `定义2.1.1`)
- **Single-level**: `1`, `I`, `a` (e.g. `定理1`, `例a`)
- **No number**: Just `**定理（名称）**：` if the book really omits it

**Allowed**: Fix OCR noise to restore the intended number (`定?` → `定义`, `2.?-4` → `2.8-4`)
**Not allowed**: Inventing numbers or labels that don't appear in the book, or rebracketing for consistency.

---

## 双语规则与输出语种

### 输出语种（按你手上的书的语种决定）

"原书"指你正在总结的那本书（译本也算），不追查原始出版语言：

| 你手上的书的语种 | 输出 |
|---------|------|
| 中文书 | 仅中文总结（`第N章_章名.md`，N 用阿拉伯数字如`第1章`） |
| 英文书 | 两份：**`ChapterN_*.md` 纯英文源版（全文件禁止任何中文字符）** + **`第N章_*.md` 中文派生版（中文为主、保留英文术语标注）** |
| 其他语种（德/法/日/俄…） | 原语种 + 中英双份（共三份） |

### 英文标注原则（仅中文版需要）

中文版必须在每个章文件内首次出现重要概念时标注英文，**格式为 `中文 (English)`**。包括：
- 节标题：`## §N.1 节名 (English Section Title)`
- 定义/定理标签：`**定义N.S-N（名称 (English name))**`
- 裸编号项：`**N.S-N 中文名 (English name)**`
- 正文关键术语：该章内首次出现时括号标注。不同章之间独立

**英文来源规则**：
- 若**原书本身是英文**或原书在概念旁已给出英文术语，则标注的英文**基于原书原文**，不自行另译
- 若原书无对应英文，则按你的理解给出标准英文翻译

> 🔴 **铁律 — 英文源版 `ChapterN_*.md` 必须 100% 英文，禁止任何中文字符**：
> - 标签**只写英文**，如 `**Definition 1.1 (Joint Distribution Function)**`，**绝不**写成 `**联合分布函数 (Joint Distribution Function)**` 或 `**定义1.1**`。
> - 正文、节标题、图注 `alt="..."` 一律英文；**全角中文标点 `：` `（` `）` 也必须换成半角 `:` `(` `)`**。
> - 中文**只许**出现在 `第N章_*.md`（中文派生版）。在该文件里首次出现概念时用 `中文 (English)` 标注。
> - 违反此条 → 英文版既不像英文、又与中文版重复，整章作废重做。英文版内容与中文版**结构镜像**，但**语言纯英文**。

---

## 编号项格式模板

**带标签项**（定义/定理/命题/推论/引理）——中文版：
```
**定义1.1-1（名称 (English name)）**：定义内容。
**定理2.6-2（名称 (English name)）**：陈述内容。

> **证明思路**：1. 第一步。 2. 第二步。 … N. 最后一步。

> **证明梗概（别名）**：`**证明梗概**` 是 `**证明思路**` 的等价别名，两者适用完全相同的格式规则（均须 `>` 块引用包裹、多步骤须 `1. 2. … N.` 编号）。
```

**无标签裸编号项**——中文版：
```
**2.8-4 范数 (Norm)**：描述内容。
```

**明确标"例"的项**——中文版（例子用 `>` 包裹，例内证明与例子同一层 `>`，不用 `> >` 嵌套；陈述与证明必须在同一连续 blockquote 中，中间不得有空行或裸 `$$`）：
```
> **例1.1-2（名称 (English name)）**：简要描述。
> **证明思路**：1. 第一步。 2. 第二步。 … N. 最后步骤。
```

> **例块连续性规则**：例的陈述与它的证明必须在同一连续 blockquote 中，禁止出现裸空行（零内容且无 `>` 前缀的空行）或裸 `$$`（无 `>` 前缀的展示公式）。裸空行会打断 blockquote，使例子和证明被渲染为两个独立框。如需留白，用 `>`（空引用行）；如需 `$$` 公式，用 `> $$`。`format/fmt_proofs.py` 的 `merge_example_block()` 可自动合并遗漏的例-证明块。

英文版对应（**纯英文，绝不含中文、绝不用全角中文标点**）：
```
**Definition 1.1-1 (Name)**: Statement.
> **Proof sketch**: 1. Step one. 2. Step two. … N. Final step.
**2.8-4 Norm**: Description.
> **Example 1.1-2**: Brief description.
```

> 编号格式跟原书走。OCR 模糊时允许还原编号，但**不得无中生有**，也不得为统一风格而篡改原书的分隔符。
> 如果某节内容在书中是原理性描述（无编号也无标签），直接用带 `**` 的段落叙述，不强制编号。
> 正文中首次出现的关键术语也要标注英文。

### 习题（练习）收录规则

判定标准是有无**专门的习题小标题**把习题归拢成块：

- **带有专门习题小标题的集中习题块**（如 `### 练习`、`## §1.11 习题`、`**习题**`、`Exercises`、`Problems` 等标题下罗列的编号习题）→ **一律省略，不写入总结**，直接跳过，不写任何注记。整节都是习题的节（如 `## §1.11 练习`、`## §3.9 习题`）同理省略。
- **没有专门习题标题、以穿插形式出现的习题**（习题散落在定义/定理/例等正文条目之间，或虽出现在节末但没有用「练习/习题」之类标题归拢）→ **保留**（可以是一道或多道），在原位写出题目（OCR 噪声必须重写正确 LaTeX），可附一句提示或思路。

简言之：**有标题归拢即省，无标题穿插即留**。练习不计入 verifier 必备条目（`book_structure.json` 中虽含全量 `type:"exercise"` 节点，但 verify 仅核对 `type` 为定义/定理等编号项的节点，不核对练习）。

---

## 图片嵌入规则（强制，2026-07-26 立）

> 当一本书跑过图片流水线后，`_extract/figure_index.json` 中会列出该书所有图的位置、图号（若有）和裁剪文件 `figure/chNN_figX.X.X.png` 或 `figure/chNN_unnamed_K.png`（即 `figure_index.json` 的 `file` 字段值，**相对 `_extract/`**）。写章总结时**必须按本节规则决定每张图的取舍与位置**——这是「该书里把图嵌入到对应定理引理」的唯一判定方式。

### 核心判定

**每张图只嵌入一次，且必须紧贴「使用它的条目」**。具体映射：

| 图来自的部位 | 该图在 `.md` 中的归属 |
|--------------|----------------------|
| caption 明确指向某个条目编号（图注文本含 `定理N.S-N`、`例N.S-N`、`定义…`、`引理…`、`推论…` 等） | 嵌入到该条目的**条目陈述段后、证明块引用之前/之中**（见下表） |
| caption 是独立图号 `图N`、无明确条目编号，但与某个例/定义的语义配套 | 嵌入到对应的例或定义的陈述段后 |
| 仅作为某条证明中插图（caption 形如 `图M 定理X.X-X 的证明(a)`） | 嵌入到该证明的 `> **证明**：` 块引用**内**、与证明文字并列 |
| 与任何条目均无关联（纯装饰、章节开头导览图、章末示意图等） | **不嵌入** |

### 强制：图必须归属到正确的层级（重中之重）

> **判定口诀**：图在书里属于「证明 / 例子」→ 必须缩进进对应的 `>` 引用块；图属于「条目的陈述说明」（示意某公式、某定义、某方法）→ 留在条目下方**顶层**。

- 凡是 caption 含 `证明`、或含 `例N`/`例 N` 的图，其归属块是一个 `> **证明…**` 或 `> **例…**` 的引用块。**嵌入时必须写成 `> ![…](…)`，且位置落在该引用块内部**（可放在块首、块中或块尾，但必须带 `>` 前缀，绝不能是顶层行）。
- ❌ 绝不允许把证明/例子里的图写成顶层 `![…](…)` 而把它们原本所在的引用块「打断」——哪怕图行恰好插在 `> **例…**` 与后续的 `>` 行之间，也必须补 `>` 前缀，使其成为块的一部分。
- ❌ **引用块内不得出现「裸空行」**（既无 `>` 也无任何内容的纯空行）。很多预览器把裸空行当作引用块的断点，于是标题、图、正文被切成好几个独立引用框——这正是「图跟例子/证明断开了」的典型成因。块内的换行一律用 `> `（空的引用标记行）来留白；只有「例块结束、下一个证明块/下一条目开始」那种真正的块间分隔，才保留裸空行（其后通常紧跟 `---` 或另一个 `> **例/证明**`）。
- 陈述级配图（图注是「图N 公式(1)的说明」「图N 某某度量示意图」之类，无 `证明`/`例`）才放在条目陈述段之后的**顶层**，与 `> **证明**` 块并列、互不嵌套。

### 嵌入语法

图片用 **HTML `<img>`**（不要写 markdown `![…](…)`），并用百分比宽度属性按原书比例缩放。**所有图片（含单张）必须统一包裹在 flex 容器内**，使并排的连续小图同行显示、单张居中：

```
<div style="display:flex; gap:6px; flex-wrap:wrap; justify-content:center">
  <img src="_extract/figure/chNN_figX.X.X.png" alt="图N 简注" width="X%" height="auto">
</div>
```

多图并排时放在同一 flex 容器中：
```
<div style="display:flex; gap:6px; flex-wrap:wrap; justify-content:center">
  <img src="_extract/figure/ch01_unnamed_04.png" alt="图4 欧氏平面" width="30.2%" height="auto">
  <img src="_extract/figure/ch01_unnamed_03.png" alt="图3 欧氏平面" width="30.2%" height="auto">
  <img src="_extract/figure/ch01_unnamed_02.png" alt="图2 欧氏平面" width="36.2%" height="auto">
</div>
```

- `width="X%"` 是该图在原书 A4 页面（200 DPI 渲染 = 1653px 宽）上的**实际占比**：`X = (bbox_crop_w + 16) / 1653 × 100`（bbox 为 `figure_index.json` 中的检测框，+16 是 8px 裁剪余量）。这样每张图显示时占阅读列宽的**比例** = 原书页面上该图占页宽的**比例**，不会"小图被放大、大图溢出"。
- `height:auto` 锁定宽高比，任何预览器都不会变形。
- `图N` 与简注来自 caption（修正 OCR 噪声）。
- 路径相对 `.md` 所在的**书根目录**；`figure/` 实际位于 `_extract/` 下，故链接须写成 `_extract/figure/chNN_...png`（**不是** `<书根>/figure/...`）。注意 `figure_index.json` 的 `file` 字段值是相对 `_extract/` 的（`figure/chNN_...`），写 `.md` 时要补前缀 `_extract/`。
- 图块单独成行、放在条目后或证明内；**图块后接 `---`** 才算条目的正式收尾。
- 若图在 `> **例**` 或 `> **证明**` 块引用内，flex 容器的每一行均须带 `>` 前缀，使整个容器归属块引用内部。

### 放置位置的具体规则

所有 `<img>` 均须套 flex 容器。以下示例用 `...` 代替完整 flex 属性 `display:flex; gap:6px; flex-wrap:wrap; justify-content:center`。

1. **条目陈述后**（定义/定理/引理/命题/推论 —— 顶层行）的下一行插入图片块：
   ```
   **定理1.3-4（名称 (English)）**：陈述。

   <div style="...">
     <img src="_extract/figure/ch01_unnamed_06.png" alt="图7 定理1.3-4 的证明 (a)" width="69.0%" height="auto">
   </div>

   ---
   ```
2. **例/Example 块引用内**（图本身就是例子的一部分）：
   ```
   > **例1.5-9（名称 (English)）**：描述。
   >
   > <div style="...">
   >   <img src="_extract/figure/ch01_unnamed_08.png" alt="图9 例1.5-9" width="19.4%" height="auto">
   > </div>
   > ```
3. **证明块引用内**（图只在证明里用到）：
   ```
   > **证明思路**：1. 第一步 …
   >
   > <div style="...">
   >   <img src="_extract/figure/ch01_unnamed_06.png" alt="图N 证明 (a)" width="69.0%" height="auto">
   > </div>
   >
   > 2. 第二步 …
   > ```
4. **多图并排**：同一 flex 容器放入多个 `<img>`，自动并排显示：
   ```
   > <div style="display:flex; gap:6px; flex-wrap:wrap; justify-content:center">
   >   <img src="_extract/figure/ch01_unnamed_04.png" alt="" width="30.2%" height="auto">
   >   <img src="_extract/figure/ch01_unnamed_03.png" alt="" width="30.2%" height="auto">
   >   <img src="_extract/figure/ch01_unnamed_02.png" alt="" width="36.2%" height="auto">
   > </div>
   > ```

   当多图总宽度 ≤ 100% 时自动合并为并排组（由 `figure/embed_figures.py` 后处理自动完成）。

5. **章节首图 / 与条目无关的图**：不写进 `.md`，只在原始 PNG 中保留。

### caption → 条目编号的解析

`figure_index.json` 中 `caption` 字段是 OCR 抽取的图注文本，常带噪声。判定规则：

- 含 `定理N.S-N` / `引理N.S-N` / `命题N.S-N` / `推论N.S-N` / `例N.S-N` / `定义N.S-N` → 直接锚定到该条目的粗体标签（如 `**定理1.3-4**`）。
- 含 `例N` / `例a`（单级编号） → 锚定 `**例N**` / `**例a**`。
- 仅含 `图N` 且无条目编号 → 该图为「独立示意」，按页面位置（`page` 字段 + `chapter_map.json`）找到 `## §` 节，作为「节末尾补充图」插入该节最后一条之后，或直接放弃（如果节内确实没有合适的条目）。
- caption 完全无法解析 → 放弃嵌入，避免错放。

### 与现有规则的关系

- 图块**不算独立编号条目**，不触发「条目间用 `---` 分隔」的 item 计数；但插入图块后，**图块与下一条目之间仍需 `---`**。
- 图片占位符前的 `---` 与图片块之间的空行**不可省略**（KaTeX 校验关心 `$$` 前的空行；图片块虽非公式，保留空行利于阅读）。
- 不引用 `verify/script/verify_chapter.py` 的 figure 层(E)作为嵌入正确性的依据：figure 层(E)只检查「**书里有这张图且 `.md` 提到对应图号**」，它**不**验证嵌入位置是否正确——位置正确性由本节规则的 caption→条目映射保证。

### 反例

- ❌ 把与某例无关的图机械地堆在该节末尾（破坏「图属于某条目」的对应关系）。
- ❌ 把「独立示意」图放进与书中文本毫无关联的位置（用户会找不到出处）。
- ❌ 嵌入后未用 `---` 与下一条目分隔，导致相邻条目视觉合并。
- ❌ 在 `.md` 写成 `](figure/ch01_...png)`（漏了 `_extract/` 前缀）——相对书根解析为 `书根/figure/...`，那里没有图（图实际在 `_extract/figure/`），图片不显示且违反 figure 层(E)。

### 后处理：结构扫描与 flex 包装兜底（已由 Step 3.5 脚本自动执行）

`figure/embed_figures.py`（Step 3.5 的强制脚本）在嵌入后会**自动**跑三段后处理，无需手动再跑：

- **块内缩进**：从头扫描 `.md`；遇到 `> **证明` / `> **例` 行即进入「块区间」，直到遇到顶层 `---` / `## ` / 顶层 `**…**` 才退出；在块区间内、凡是**顶层**的 `<img ...>` 行，一律补 `>` 前缀缩进为 `> <img ...>`。
- **连续性修复**：块区间内的**裸空行**（无 `>` 也无内容的纯空行）一律转成 `> `，使引用块连续不被渲染器切断（即直接满足 verify 的 G 层）。
- **flex 包装**：所有 `<img>` 行（含单张和连续多张）统一包裹进 `<div style="display:flex; gap:6px; flex-wrap:wrap; justify-content:center">`。连续多张放在同一容器内并排显示，单张居中。自动保留 `>` 前缀以及 `$$` 之前的空引用行。
- 三步都**幂等**：已带 `>` 的图不会被重复缩进，已连续的块不会被改动，已包装的 flex 容器不会被重复嵌套。
- 跑完反向校验：再跑一次应当报告「块内遗漏 0、明确 proof/example 图非块内 0、G 层 0 违规」。

### 已知遗留问题：顶层 `</div>` 后缺空行

`figure/embed_figures.py` 的自动结构扫描只处理图片在 `>` 块引用内的情况（缩进进块 + 连续性修复），但**顶层图片**（放在 `---` 前或 `## §` 节标题前）的 `</div>` 后**不会自动补空行**。这会导致 Markdown 解析器把紧跟 `</div>` 的内容吞进 HTML 块，C 层报 "missing blank line after `</div>"。

**症状**：`verify/script/verify_chapter.py` 的 C 层报告类似 `line 42: missing blank line after </div>`。

**修复**：手动在顶层 `</div>` 后补一个空行即可（若后跟 `---` 则补在 `---` 之前）：
```
</div>

---
**定义1.5**：
```
即在 `</div>` 与 `---` 之间插入一个空行。若图片在 `> **例**` 或 `> **证明**` 块内（`> </div>` 缩进形态），块内的行尾换行机制自动满足连续性，无需处理。

---

---

## KaTeX 规则

0. **Encoding first (HARD REQUIREMENT #1)**: Before any math formatting, ensure the file is written as clean UTF-8.

1. **Blank line before `$$`**: Every opening `$$` must be preceded by a blank line, otherwise KaTeX ignores it.
   ```
   定理陈述文字。

   $$
   \int_a^b f(x)\,dx
   $$
   ```

2. **Blockquote `> $$`**: When a formula is inside a blockquote, insert an empty `>` line between the text and `> $$`:
   ```
   > **证明思路**：1. 由某某定理直接可得。 2. 代入已知条件得出结论。
   >
   > $$
   > F'(x)=f(x)
   > $$
   ```

3. **Avoid nested blockquote `> > $$`**: Display math `$$` inside a nested blockquote (`> > $$`) is **not** recognized by KaTeX as a math delimiter. Only the outermost `>` should be used on `$$` lines. If a formula appears inside a nested example/block, flatten it:
   ```
   > **例**：...
   >
   > $$              ← NOT > > $$
   > formula
   > $$
   >
   > 后续文字
   ```
   `format/check_katex.py --fix` 可自动修复此问题。

4. **Avoid `\bigl(\sup\{` / `\bigl(\inf\{`**: `\bigl(\sup\{...\}\bigr)` breaks KaTeX. Use `\sup\{...\}` or `\bigl(\sup_{...}` without the outer `\bigl(`...`\bigr)`.

5. **Avoid `\left.\frac{}{}\right|_{}`**: `\left.\frac{df}{dx}\right|_{x=x_0}` causes KaTeX cascade failure. Use `\dfrac{df}{dx}\bigr|_{x=x_0}` instead.

6. **Avoid `\\[` / `\\]`**: Use `$$...$$` for display math, never `\[...\]`.

7. **禁止用 ` ``` ` 代码围栏包裹公式或交换图表**：代码围栏会把数学渲染成等宽纯文本、非常难看。所有公式（含交换图表）都必须用真正的 KaTeX 书写：
   - 普通公式 → `$$ ... $$`（开头 `$$` 前必须有空行，见规则 #1）。
   - 交换图表（对象 + 箭头的格子）→ `$$ \begin{CD} ... \end{CD} $$`，采用 AMScd 语法。
   - ❌ 错误示例（代码围栏，等宽纯文本）：

         ```
         A' → A → A"
         α'↓   α↓   α"↓
         B' → B → B"
         ```

   - ✅ 正确示例（KaTeX CD）：

         $$
         \begin{CD}
         A' @>>> A @>>> A'' \\
         @V\alpha'VV @V\alpha VV @V\alpha''VV \\
         B' @>>> B @>>> B''
         \end{CD}
         $$

   AMScd 速查：`@>>>` 右箭头、`@<<<` 左箭头、`@VVV` 下箭头、`@AAA` 上箭头；右箭头上方标签 `@>f>>`、下箭头左侧标签 `@VfVV`；`@|` 竖直恒等、`@=` 水平恒等、`@.` 空格子。开头 `$$` 前仍须有空行（规则 #1）。本规则已由 `format/check_katex.py` 的 Pass 1b 强制校验：凡 ` ``` ` 围栏内的内容像公式/图表（含 `→↓←↑`、`─│╲` 等制表符或 `@>@V@|` 等 AMScd 记号），一律判 KaTeX 错误并阻断 `verify/script/verify_chapter.py` 的 C 层。

8. **禁止用原始 Unicode 数学箭头 / 关系符（如 `↪ ↠ ↦ → ⇒ ⇔ ≅`）**：这些是 OCR / 手敲留下的"回退字形"，必须与公式字体保持一致地改写成真正的 KaTeX。这是上一轮用户明确指出的问题（如 `Φ:A↪B` 应写作 `$\Phi:A\hookrightarrow B$`）。
   - 映射表（写在 `$...$` 内）：
     | 原始字形 | 含义 | KaTeX 命令 |
     |---------|------|------------|
     | `↪` | 单射 / 嵌入 | `\hookrightarrow` |
     | `↠` | 满射 | `\twoheadrightarrow` |
     | `↦` / `↣` | 映射 / maps to | `\mapsto` |
     | `→` | 函数箭头 | `\to` |
     | `⇒` | 推出 | `\implies` 或 `\Rightarrow` |
     | `⇔` | 当且仅当 | `\iff` |
     | `≅` | 同构 | `\cong` |
   - ❌ 错误（原始 Unicode，渲染成回退字形、与公式字体不一致）：`若 Φ:A↪B 为单射，记 Φ:A↠B 为满射，Φ:A≅B 为同构`
   - ✅ 正确（KaTeX）：`若 $\Phi:A\hookrightarrow B$ 为单射，记 $\Phi:A\twoheadrightarrow B$ 为满射，$\Phi:A\cong B$ 为同构`
   - 同理，原始 Unicode 数学运算符（`⊕` 直和、`Π` 积、`∈` 属于、`⊆` 包含等）也**建议**改为 KaTeX（`\oplus` / `\prod` / `\in` / `\subseteq`）；但为避免误伤，本规则**只强制拦截箭头 / 关系字形**（见上表），运算符暂仅作文档要求、不强制拦截。判断口诀：正文里只要出现 `↪↠↦→⇒⇔≅` 这类字形且不在 `$...$` / `$$...$$` 数学模式内，一律视为错误。
   - 本规则已由 `format/check_katex.py` 的 **Pass 1c** 强制校验：凡在「非数学模式」下出现上述箭头 / 关系字形，一律判 KaTeX 错误并阻断 `verify/script/verify_chapter.py` 的 C 层（与 Pass 1b 同级）。

9. **禁止「裸 LaTeX 命令」出现在数学模式之外**：`\mathrm{op}`、`\operatorname{Hom}`、`\mathbb Z`、`\varphi:A\to B` 这类写法如果**没有包在 `$...$` 或 `$$...$$` 里**，Markdown 会把它们当普通文本原样显示（读者看到的是代码而不是公式）。这是 2026-07 第 1 章中文版实际发生过的事故（82 行裸公式）。
   - ❌ 错误：`右 Λ-模是左 Λ^{\mathrm{op}}-模`（`\mathrm` 裸露，直接显示为代码）
   - ✅ 正确：`右 Λ-模是左 $\Lambda^{\mathrm{op}}$-模`
   - 判断口诀：**只要一行里出现反斜杠命令 `\xxx`，它就必须处于 `$...$` / `$$...$$` / 代码围栏之一的内部**。
   - 本规则已由 `format/check_katex.py` 的 **Pass 1d** 强制校验：数学模式外出现 `\命令` 一律判 KaTeX 错误（代码围栏内豁免）。
   - 高发场景提醒：写中文总结时，从 `$$` 块里"顺手"复制片段到正文叙述、或在定义句里内联小公式时，最容易忘掉 `$` 包裹——写完后务必跑一遍 `format/check_katex.py`。
   - **修复裸公式时的次生事故（Pass 1e 强制校验）**：给裸公式补 `$` 时，**绝不能把行首的结构前缀（块引用 `>`、列表符 `-`、编号 `(a)`/`1.`）一起包进公式**。如 `> - \mu_* 单` 修成 `$> - \mu_*$ 单` 就是错的——`>` 变成公式内可见字符、列表符和编号全部丢失；正确写法是 `> - $\mu_*$ 单`（前缀留在 `$` 外）。`format/check_katex.py` Pass 1e 会将行首 `$` 内含 `>`/`-`/`(a)`/`1.` 前缀的行判为 KaTeX 错误。

10. **公式编号必须用 `\tag{N.M}` 写在 `$$` 块内部**：当原书公式带有编号（如 (1.17)、(8.3) 等），总结中必须将编号以 `\tag{N.M}` 的形式附加在公式行末尾（闭合 `$$` 之前），使渲染后编号显示在公式右侧同一行。**禁止**将编号写成公式块外部的独立文字行（如 `（式 (1.17)）`）。
    - ✅ 正确：
      ```
      $$
      z(k+1) = Az(k), \quad A = U^T \tag{1.17}
      $$
      ```
    - ❌ 错误（编号脱出公式块，渲染后另起一行）：
      ```
      $$
      z(k+1) = Az(k), \quad A = U^T
      $$
      （式 (1.17)）
      ```
    - 若原书编号后紧跟解释性文字（如"（式 (1.17)）。连续时间情形类似…"），将编号移入 `\tag{}`，解释文字作为公式块后的正常段落保留。
    - 本规则由 `format/check_katex.py` 的 **Pass 1i** 校验：检测 `$$` 闭合行之后紧跟的以 `（式 (` 开头的独立行，判为格式错误。

### 公式序标（编号 1:1 真实性与 Q 层校验）

> 🔴 本小节是「公式序标」唯一权威规则（SSOT）。新增/修改公式编号相关规则只改此处；SKILL.md 仅链接本小节，不内联全文。

总结中带编号的公式（`$$ ... \tag{N.M} $$`）其序标必须与**原书公式编号 1:1 对应**：

1. **无编号不加 `\tag`**：原书公式本身无编号（纯展示 / 推导中间式），总结也**不要**加 `\tag`；机器只核对带 `\tag` 的公式，未编号公式不计入序标审计。
2. **有编号须 1:1 跟书**：原书带编号的公式，其 `\tag{X}` 编号必须来自书源真实编号集合 S（每章 `page_*.json` 的 `text[]` 抽出的编号），不得：
   - **编造（FABRICATED）**：`\tag` 编号不在 S 中（凭空捏造或串号）；
   - **错位 / 跨章（INCONSISTENT）**：同一章内 `\tag` 编号重复，或编号首分量 ≠ 当前章号（跨章抄公式）；
   - **遗漏（MISSING）**：S 中属于本章的编号在总结里无对应 `\tag`（默认仅 WARN，永不阻断；书源确有该编号但属合理省略时，把它加入 `formula.ignore` 列表跳过比对）。
3. **OCR 还原编号边界**：
   - 允许：编号因 OCR 模糊而基于上下文还原（如 `（1l.1）`→`(1.1.1)`、`(11.1-1)`→`(11.1.1)`），只要还原结果能在 S 中对应到真实编号；
   - 禁止**无中生有**：不得为「看着像应该有编号」而编造 `\tag`；S 中没有的编号，宁可不加 `\tag`（退化为无编号公式）也不许编造；
   - 禁止**为统一风格篡改分隔符**：S 用 `（11.1-1）`(短横) 就用 `-`，S 用 `（11.1.1）`(点) 就用 `.`，不得把原书分隔符统一改成另一种；`norm()` 会把 `.\-·,` 任一分隔符归一为 `.` 再比对，但**总结里的 `\tag` 应与书源书写一致**，机器只判归一后是否等价、不强制书写形式。

Q 层（`verify/layers/formula_tag/script/formula_tag.py`，`verify_config.json` 配置 `formula` map 时启用）仅做**序标结构**校验，公式**内容对错**由人核对 `formula_audit.md`（`verify --all` 末生成的对账报告）。

11. **`$` 必须成对闭合，尤其注意中文标点**：`$formula，` 是最常见的隐蔽 bug。中文逗号/句号前缺少闭合 `$`，导致数学模式延续到下一行的 `$$` 首字符，使显示公式失效。
    - ❌ 错误：`对 $t>0,[空行]$$...$$`（`$t>0,` 没有闭合 → `$` 吞掉 `$$` 的首 `$`）
    - ✅ 正确：`对 $t>0$，[空行]$$...$$`
    - **诊断**：搜索「奇数个 `$` 的行且其后紧跟 `$$`」。
    - `format/fix_katex.py` 自动修复此模式。

12. **`$$` 不得包裹非数学内容**：`$$` 内的内容须为纯数学 LaTeX，不能包含中文文本、`##` 标题或 `$...$` 内联数学。
    - ❌ 错误：`$$ ## §N.S 标题 $$`、`$$ text $formula$ more text $$`
    - ✅ 正确：去掉 `$$` 包裹，保留内容作为普通段落
    - `format/fix_katex.py` 自动修复此模式。

13. **断裂命令修复**：自动修复脚本有时会破坏命令间距，产生不可识别的控制序列：
    | 断裂写法 | 正确写法 |
    |---------|---------|
    | `\in t` | `\int` |
    | `\in fty` | `\infty` |
    | `\in f` | `\inf` |
    | `\qquadn` | `\qquad n` |
    | `\quadc` | `\quad c` |
    | `\widetildeP` | `\widetilde P` |
    | `\fracx3` | `\frac{x}{3}` |
    - `format/fix_katex.py` 自动修复此模式。

14. **交换图（CD）语法要点**：
    - 箭头方向标记字符必须**首尾匹配**：`@VlabelV`（首 V 尾 V）、`@AlabelA`（首 A 尾 A）
    - ❌ 错误：`@VV\text{RN} A`（尾符应为 V 而非 A）
    - ✅ 正确：`@VV\text{RN}V`
    - `@A\int A`（以 `\int` 作为上箭头标签）在 KaTeX 中解析失败，改用 `@V\int VV`（下箭头+积分标签）
    - `\begin{CD}` 和 `\end{CD}` 必须被 `$$` 包裹
    - `format/fix_katex.py` 自动修复此模式。

15. **集合符号花括号必须转义**：在 `$...$` 内使用集合 `{x : ...}` 时必须用 `\{` 和 `\}`。
    - ❌ 错误：`$A_n={x$ : 1 $\le x \le c}$`（花括号未被 LaTeX 识别为集合定界符）
    - ✅ 正确：`$A_n=\{x : 1 \le x \le c\}$`
    - `format/fix_katex.py` 自动修复此模式。

16. **`$$` 块内禁止空行**：`$$...$$` 内的空行可能被部分渲染器视为显示块中断。
    - `format/fix_katex.py` 自动移除。

17. **🔴 禁止「字符型公式」——所有数学必须走 KaTeX，不得写成字符（2026-08-04 立，C 层强制）**
    > 任何数学内容都**必须**用 KaTeX 渲染（`$...$` 行内 / `$$...$$` 显示），**绝不允许**以裸字符形式留在正文叙述里。这是 2026-08-04 第 7 章反复踩坑的根因：subagent 把行内数学写成 Unicode 数学字符或 ASCII 函数表达式、却没包 `$...$`，结果只是普通文本、不渲染。
    - **(A) 裸 Unicode 数学字形**（强制，由 `check_katex.py` 的 **Pass 1f** 拦截）：σ √ ∑ ∞ ≤ ≥ ≠ ≈ ≡ × ÷ ± ∓ ∂ ∇ ∏ ∪ ∩ ∈ ∉ ⊂ ⊆ ∀ ∃ ∅ ℝ ℕ ℤ ℂ，以及希腊字母 α β γ δ ε ζ η θ κ λ μ ν ξ π ρ σ τ φ χ ψ ω / Γ Δ Θ Λ Ξ Σ Φ Ψ Ω。这些在总结里几乎从不作为散文出现，一律视为错误：
        - ❌ 错误：`σ²t`、`√(2π t³)`、`∑_{n} B_n<∞`、`μ≠0`、`x∈ℝ`、`π 约等于 3.14`
        - ✅ 正确：`$\sigma^{2}t$`、`$\sqrt{2\pi t^{3}}$`、`$\sum_{n} B_n<\infty$`、`$\mu\neq 0$`、`$x\in\mathbb{R}$`、`$\pi$ 约等于 3.14`
        - 注：上标数字 ² ³ **暂不强制**（物理单位 km² 会误报），但数学里的 `n²` 仍应写作 `$n^{2}$`（仅作文档要求）。
    - **(B) ASCII 数学写成纯文本**（强制，Pass 1f 拦截）：概率/期望/方差算符 `Pr{`/`Pr(`/`E[`/`Var(`/`Cov(`，单字母函数调用 `X(t)`/`p_k(n)`/`f(x+y)`，以及变量+下标数字 `x0`/`t1`/`y2`（含义为带下标变量）。这些必须包进 `$...$`：
        - ❌ 错误：`设 p_k(n)=Pr{粒子在 n 步后位于右侧第 k 步}`、`X(t) is continuous`、`初始位置 x0`、`E[X]`
        - ✅ 正确：`设 $p_{k}(n)=\Pr\{\text{粒子…第 }k\text{ 步}\}$`、`$X(t)$ is continuous`、`初始位置 $x_{0}$`、`$\mathbb{E}[X]$`
    - **(C) 与既有规则的关系**：本规则与 rule #8（Unicode 箭头/关系字形）、rule #9（裸 LaTeX 命令）共同构成「数学必须渲染」三道防线；rule #8 只强制箭头/关系字形，本规则（#17）把**其余所有数学字形 + ASCII 数学表达式**一并强制，彻底堵死「字符型公式」。
    - **强制闸口**：`verify_chapter.py` 的 **C 层**会子进程调用 `check_katex.py`；Pass 1f 报出的「character-type formula」即计入 `katex_lines`，导致该章 `verify` 不通过。换言之，今后任何章节只要正文里残留字符型公式，就不会过校验——必须在 authoring 阶段就把所有数学包进 `$...$`/`$$...$$`。
    - **authoring 护栏**：写总结时，凡出现变量、函数、概率、集合、希腊字母、上下标，一律顺手加 `$`；写完后务必跑 `format/check_katex.py <file>`（或 `verify --all`），Pass 1f 会一次性把漏包的数学揪出来。

### 块引用与分隔线规则

- **块引用不得截断（硬规则）**：凡以 `> **例/证明/注**：` 开头的块引用条目（注意：**定义/定理/引理/推论/命题/断言/公理等结构性标签不进块引用，必须顶层**），其**全部内容**（含紧跟的 `$$` 展示公式块、续句、空行）都必须带 `>` 前缀、闭合在同一个块引用内。
- **条目间用 `---` 分隔**：每两个相邻编号 item 之间，在上一个 item 的完整内容块结束后，另起一行写 `---`、再空一行，再写下一个 item。
  - item 指定义/定理/命题/推论/引理/例/裸编号等所有独立编号条目
  - `**证明思路**` / `**注记**` 等属于某个 item 的**内部附属块**，不能用 `---` 与所属 item 分隔
  - **特例——定义/定理后接例**：定义/定理等顶层条目与紧跟的 `> **例**` 之间也必须用 `---` 分隔，即使两者间有空白行也不能省略 `---`。
  - **特例——例后接定义/定理**：`> **例**` 与紧跟的顶层 `**定义**`/`**定理**` 等之间也必须用 `---` 分隔。
- **标题紧邻下不加 `---`**：节标题的紧邻下一行不能是 `---`。但「标题 → 引子段落 → `---`」合法。
- **例与证明必须分处不同行**：一个 `> **例**` 行的内容只包含例子描述本身，其证明（`**证明梗概**` / `**证明思路**`）必须另起一行，用 `> **证明梗概**：` 开头。❌ 错误（例与证明在同一行）：
  ```
  > **例**：例子描述。**证明梗概**：第一步…第二步…
  ```
  ✅ 正确（例与证明分两行，同一块引用内）：
  ```
  > **例**：例子描述。
  > **证明梗概**：第一步…第二步…
  ```
  **原因**：例与证明在同一行导致块引用内换行困难，且后期修改/校验时难以定位问题。
- **连续例子必须在顶层用 `---` 分隔**：即使多个例子共享同一个 `>` 块引用（通过 `>` 续行符连接），也必须在每个 `> **例**` 之间用顶层 `---` 断开——即每个例子独占一个独立的块引用，中间用 `---` 和空行隔开。❌ 错误（连续例子在同一块引用内）：
  ```
  > **例**：第一个例子描述。
  > **例**：第二个例子描述。
  > **例**：第三个例子描述。
  ```
  ✅ 正确（每个例子独立块引用，`---` 分隔）：
  ```
  > **例**：第一个例子描述。

  ---

  > **例**：第二个例子描述。

  ---

  > **例**：第三个例子描述。
  ```
  **故障模式**：多例连续（`> **例**\n> \n> **例**` 或 `> **例**\n> **例**`）会使得阅读时看不出条目间的边界，verify/script/verify_chapter.py 的 I 层也会漏检（因为 I 层只检测相邻顶层 `---`，块引用内的续行不算）。
- **格式一致性由 `format/fmt_proofs.py` 兜底**：写完后运行 `python format/fmt_proofs.py <book_dir> --number` 自动修复。

---

## 提取流程（从 JSON 提取编号项）

写任何一章之前，先对该章页码范围内的 **JSON 页面文件** 直接做分析（不要依赖 chN_raw.txt，JSON 保留原始 OCR 文本块且不被模拟拼接破坏）。

> **核心策略**：不在图像预处理层面提升 OCR 质量。而是通过**脚本层三级兜底**——(1) 主正则 `N.S-N`、(2) 2-group fallback `(\d)(\d)...` 捡回 OCR 连写编号、(3) `--manual` 人工补漏应对完全不可读的碎片。

1. **确定页码范围**：从 `chapter_map.json` 获取该章的 start/end 页码。

2. **遍历该范围内所有 JSON page**，按页码顺序逐页读取。**JSON 中 `text` 数组的排列顺序不一定等于页面阅读顺序**；必须用每条 text 的 `poly` 坐标对同页内的 text 排序，然后全局按页顺序 + Y 坐标确定全部 text 的阅读流。

   **正则匹配编号**：每条 text 正文用 `(\d+)\s*[\.\-\·\，\s]\s*(\d+)\s*[\-\.\·\，\s]\s*(\d+)` 检测 `N.S-i` 模式（脚本中 `num_re`）。注意 OCR 可能把短横打成点，此时按上下文判断。

3. **放宽标点限制**：序号分隔符可能是 `.` `-` `·`（中文间隔号 U+00B7）`，` 甚至空格。统一还原为原书格式。

4. **区分"标签项"与"引用"**：每个匹配的编号需要判断是**原创条目**还是**交叉引用**。
   - **标签检测**（三级优先级）：
       1. **当前 text block**：看编号前后的文本（前60+后40字符）是否含标签词
       2. **整节标签**：若该页或之前某页有节标题，则该节内所有未显式标注的编号继承该标签
       3. **邻接 text block**：仅作为最后手段
   - **引用检测**：若编号前 25 个字符内有"见""由""根据""参考""参见""Cf."等词，则标记为引用，不收录。

5. **检查边界头丢失**：对每节，如果检测到的第一个编号 > 1，怀疑更小编号被页边界吞掉，回 JSON 上下页确认。

6. **检查内部密集性**：对每节编号进行跨度分析，空缺编号回 JSON 对应页确认是否存在。

7. **人工补漏**（针对 OCR 完全吃掉编号的条目）：在 `manual_overrides_ch{N}.json` 中写好漏项的 `key` / `label` / `page` / `text`（字段结构与示例见 [`config/manual_overrides_chN/manual_overrides_chN.md`](config/manual_overrides_chN/manual_overrides_chN.md)），运行 `flows/extract/structure/script/extract_items` 配合 `--manual` 合并输出。**尾部缺漏必须迭代检查**，直到 WARN 消失。

   此外脚本内置了**两级回退匹配**辅助还原：
   - **一级（3-group `num_re`）**：`N.S-N` 完整模式
   - **二级（2-group `fallback_re`）**：当 OCR 把 `2.1-7` 打成 `21_7`，尝试 `(\d)(\d)[\s_\-\·]\s*(\d+)` 回退匹配

8. 将确认后的条目录入清单，确认每条都有对应标签后，再动笔写正文。

9. 写完后对照清单检查一遍，确认无遗漏。
