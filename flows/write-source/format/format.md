# Sub-flow: write-source / format（格式与保真规则）

> 统一模板：目的 / 前置 / 步骤 / 本阶段规则 / 出口 / 相关代码 / 子流程
> 📌 **本子流程的强制完整规则以同目录 [`formatting.md`](ref/formatting.md) 为准（SSOT）**。本文件只给大类速览与入口；新增 / 修改格式规则只改 `formatting.md`，不在此重复。

## 目的
定义章节总结的格式与保真规则：标题体系、条目标签、块引用、分隔线、公式、图片嵌入、练习收录、双语规则、KaTeX 规则、保真分级（Tier 1/2/3）。
## 前置
- 写作对象为源语言初稿（章节 `.md` 文件）。

## 步骤（有序）
写作时遵循以下大类（细节点开 `formatting.md`）：
1. **标题体系**：章 `# 第N章 …`、节 / 子节 `## §N.M …` / `### §N.M.K …`（须带 `§`）。
2. **条目标签**：`**粗体标签**：`（禁 `###`）；编号 1:1 照搬原书印刷号；number-first 体例、gm 体例等特例见 `formatting.md`。
3. **块引用**：例 / 证明 / 注进 `>`；条目陈述须顶层独立成行；块内 `$$` 用 `> $$`；引用块连续不截断。
4. **分隔线 `---`**：仅用于不同顶层条目之间，条目内部禁止。
5. **公式**：用 `$$`（前空行），编号 `\tag{N.M}`，禁止代码围栏包裹；KaTeX 渲染须成功；公式序标（编号真实性 / 编造·错位·跨章·遗漏）规则见 `formatting.md#公式序标`。
6. **图片嵌入**：被引用图放引用条目处，未引用不写（见 `figures` 子流程 / `formatting.md#图片嵌入规则`）。
7. **练习收录**：有专门习题标题归拢即省略，无标题穿插即原位保留（见 `formatting.md` 习题规则）。
8. **双语规则**：英文书源版 `ChapterN_*.md` 必须 100% 英文（全角中文标点换半角），中文派生版仅出现在 `第N章_*.md`（见 `formatting.md`「双语规则与输出语种」）。
9. **保真分级**：Tier 1 高保真（定义/定理/例题面/练习题目/注记原汁原味）、Tier 2 描述性内容（保留公式与概念、精简表述、禁丢）、Tier 3 证明/解答（只列核心步骤 `1. 2. 3.`，步数不限）。

## 本阶段规则（🔴 内联，指向 SSOT）
- **禁止照抄 OCR 文本流**：页眉 / 页脚 / 版权行属噪声，须剔除干净，一个字都不许进正文。
- **不编造结构**：骨架（节个数 / 顺序、条目与练习先后位置）必须与原书页码顺序逐条同构。
- **公式序标铁律**：书无号不编造；已标须正确、不重复、不跨章。
- **KaTeX 模式修复**速查见同目录 [`katex.md`](ref/katex.md)；完整 KaTeX 规则见 `formatting.md`。

## 出口条件
- 出口：写作与格式后处理完成，章节符合 `formatting.md` 全部规则。

## 相关代码（路径相对 skill 根目录）
- `flows/write-source/format/script/wrap_examples_bq` / `flows/write-source/format/script/fmt_proofs`：格式后处理；KaTeX 检测/修复已并入 verify（`verify/format_verify/script/check_katex.py` 与 `fix_katex.py`，`verify --fix` 自动修复）。
- 同目录支撑文档：`ref/formatting.md`（SSOT）、`ref/separator_regexlib.md`（分隔符正则库）、`ref/book_patterns.md`（书目编号体系判定树）。

## 子流程
- [`write-source/figures`](../figures/figures.md) — 嵌入图片（见 `figures` 子流程）
- [`write-source/format/katex`](ref/katex.md) — KaTeX 问题识别与修复速查
