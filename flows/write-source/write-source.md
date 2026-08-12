# Flow: write-source（写源语言初稿 / Stage 3）

> 统一模板：目的 / 前置 / 步骤 / 本阶段规则 / 出口 / 相关代码 / 子流程

## 目的
依据已修复的 `page_*.json`，按原书结构逐条写出**源语言**章节总结（英文书 = `ChapterN_*.md`；中文书 = `第N章_*.md`）。本阶段只产出初稿 + 嵌图，**不做任何校验**（校验由统一校验关卡在全部初稿完成后批量进行）。
## 前置
- 该章 `page_*.json` 已落盘且过 MM Repair。
- 已知该书的源语言（英文书源语言为英文版，中文书源语言为中文版）。
- **全书 `book_structure.json` 已通过 structure 第 4 步闸门**（结构契约前置，SSOT 见 `flows/extract/structure/structure.md`）：用于**辅助确认总结结构**——节数 / 顺序 / 编号项 `key` / 印刷标题（`name`）/ 页码区间（`page_start..page_end`）；⚠️ 其 `name` 仅含带序标的**纯印刷标题，不含任何条目正文**。

## 步骤（有序）
1. **双源写作，缺一不可**：
   - **(a) 结构契约 `book_structure.json`**（前置已确认，SSOT 见 `flows/extract/structure/structure.md`）：书对象 `sub_sec` 内按章顺序嵌套——每个 `type:"section"` 节点对应一个 `## §N.M` 标题（`name` 即带序标的纯标题，顺序照抄）；每个编号项节点（`type∉{section,exercise,chapter}`：定义 / 定理 / 引理 / 推论 / 命题 / 例 / 评注 / uncat）必须落地；`type:"exercise"` 节点为练习（照下方「习题收录规则」决定省略或保留）。⚠️ 此契约**只定骨架 + 印刷标题 + 页码区间，不含正文**，用于确认"写哪些、按什么顺序、每条目标题是什么"。
   - **(b) 原文回归 `page_*.json`**（内容来源）：对每个节点，按其 `page_start..page_end` 经 `data/page_json/page_json.py` 适配器读取 OCR 原文——`page_json.PageJson.load(fp).page_text()`（整页文本）或 `.text_blocks`（分块）。**以此原文为唯一内容来源**，忠于原文写出陈述 / 证明梗概 / 例题 / 评注；剔除页眉页脚版权行等噪声。
   - **配合流程**：先用 (a) 锁骨架与页码锚点 → 再对每个节点用 (b) 取原文写正文 → 写完回查 (a) 保证 1:1 同构（无遗漏、无自创层级、无重排）。
2. 按 `format/ref/formatting.md` 全部格式规则写**源语言**文件：标题体系（`# 第N章` / `## §N.M` / `### §N.M.K`）、粗体条目标签（`**Definition 1.1**` 禁 `###`）、块引用、分隔线、`$$` 公式、图片嵌入（见子流程 figures）、练习收录。
3. 写完后跑**格式后处理**（顺序固定）：
   ```powershell
   python flows/write-source/format/script/wrap_examples_bq <book_dir>   # 顶层例包进 > 块引用（须先跑）
   python flows/write-source/format/script/fmt_proofs <book_dir> --number # 块引用/分隔线/证明格式修复
   python flows/write-source/format/script/fix_katex <book_dir>           # 综合修复已知 KaTeX 模式
   python flows/write-source/format/script/check_katex <file>             # 逐文件复验（不加 --fix）
   python verify/script/audit_counts.py <ch> <start> <end> <md_file> <extract_dir>  # 逐节核对条数（强制）
   ```
4. 跑 `flows/script/embed_figures <book_dir>` 嵌入本章图片（见子流程 figures，Step 3.5，强制）。

## 本阶段规则（🔴 内联 + 核心原则）
- **规则1 — 源语言优先（硬底线）**：英文书每章先写 `ChapterN_*.md`（源）→ 完全校验 / 修复至 `verify PASS + KaTeX OK` → 再据已校验英文版逐条翻译 `第N章_*.md`。中文版是英文版的**翻译产物**，不是平行独立文件。🚫 **禁止"只有中文、没有英文"**：只有 `第N章_*.md` 而无对应 `ChapterN_*.md` = 流程从根上错，须重做。
- **规则2 — 写初稿期间禁止任何 per-chapter verify**：本阶段唯一产出是 `.md` 初稿 + 嵌图；`verify` 统一在源语言全部初稿完成后批量进行。🚫 禁止"写完一章 verify 一章"，也禁止"第 1 章 pilot verify 后扇出"。
- **规则3 — 超大章按"节"拆分**（字符 > 60000 触发，中英文配对拆分）：`flows/write-source/format/script/split_chapters` 按节标题格式（`§N` 节标题式 / `N.M` 编号式）拆成每节一个文件；只拆到"节"一级，子节留父节内。幂等，拆分后默认删源合并文件（`--keep` 保留）。
- **核心原则（保真底线）**：OCR 噪声可修、表述可精简但**不得省略编号项 / 描述性内容中的公式概念**；**不编造**内容、**不编造结构**（不得新建原书没有的标题层级、不得重排条目顺序）；**严禁照抄 OCR 文本流**（页眉 / 页脚 / 版权行属噪声须剔除）；非核心内容须"摘要"而非整段照抄（Tier 1/2/3 分级见 `format/ref/formatting.md`）。
- **双源铁律（结构 ≠ 内容）**：正文**必须回归 `page_*.json` 原文**，禁止把结构契约的 `name` 当作正文来源、禁止脱离契约自创结构或重排顺序；契约只告诉你"有什么标题 / 在哪几页"，原文才告诉你"写什么内容"。
- **公式序标铁律**：书无号**不编造**；已标须**正确、不重复、不跨章**。

## 出口条件
- 出口：源语言全部章节初稿写完、已嵌图、格式后处理跑过（此时仍未校验）。

## 相关代码（路径相对 skill 根目录）
- `flows/extract/structure/script/build_structure`：统一结构契约生成器（产出 `book_structure.json` 书对象，内部调用 `scan_skeleton` / `extract_items` 系列，命令见 `flows/extract/extract.md`）。
- `flows/extract/structure/script/scan_skeleton`：结构骨架（章节标题扫描，仅被 `build_structure` 调用）。
- `flows/extract/structure/script/extract_items` + 变体（`_en` / `_gm` / `_vakil` / `_hom` / `_kt`）：编号项抽取，按 `ordinal` 被 `build_structure` 调用。
- `data/page_json/page_json.py`：`PageJson.load(fp).page_text()` / `.text_blocks` —— 写源时按节点 `page_start..page_end` 取 OCR 原文（双源 (b) 内容来源）。
- `flows/write-source/format/script/wrap_examples_bq` / `flows/write-source/format/script/fmt_proofs` / `flows/write-source/format/script/fix_katex` / `flows/write-source/format/script/check_katex`：格式后处理。
- `../../verify/script/audit_counts.py`：逐节条数核对（强制收尾）。
- `flows/write-source/format/script/split_chapters`：规则3 拆章。
- `flows/script/embed_figures`：嵌图（Step 3.5）。

## 子流程
- [`write-source/format`](format/format.md) — 格式与保真规则（SSOT = `format/ref/formatting.md`）
- [`write-source/figures`](figures/figures.md) — 嵌入图片（Step 3.5）
