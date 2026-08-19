# Flow: write-source（写源语言初稿 / Stage 2）

> 统一模板：目的 / 前置 / 步骤 / 本阶段规则 / 出口 / 相关代码 / 子流程

## 目的
依据已修复的 `page_*.json`，按原书结构逐条写出**源语言**章节总结（英文书 = 英文 `ChapterN_*.md`；中文书 = 中文 `第N章_*.md`）。本阶段产出源语言初稿 + 嵌图，并在末尾（步骤 3）统一批量校验所有总结文件。
## 前置
- 🔴 **写源硬闸（不可绕过）**：该章页码区间对应的 `page_*.json` **必须已经过 `mm_repair_apply` 写回**（条目含 `mm_repaired`/`mm_reviewed` 标记、`_mm_repair/manifest.json` 中该章对应页的**每条目 `resolved == true`**），该章无未 resolved 的待修条目，否则**严禁写任何章节**。"`_mm_repair/repairs.json` 有 resolved 条目" ≠ "apply 已写回"——前者只是 agent 视觉补全的**中间产物**，后者才是出口。`manifest.status == "applied"` **不可信**（apply 无条件设置），验证须看 `page_*.json` 标记 + 条目级 resolved 计数，详见 [`extract/mm_repair/mm_repair.md`](../../extract/mm_repair/mm_repair.md) 出口条件。启动 write-source 前**必须先用**该文档的「如何验证 apply 已写回」命令确认写回真实发生。
- 已知该书的源语言（英文书源语言为英文版，中文书源语言为中文版）。
- **全书 `book_structure.json` 已通过 structure 第 4 步闸门**（结构契约前置，SSOT 见 `flows/extract/structure/structure.md`）：用于**辅助确认总结结构**——节数 / 顺序 / 编号项 `key` / 印刷标题（`name`）/ 页码区间（`page_start..page_end`）；⚠️ 其 `name` 仅含带序标的**纯印刷标题，不含任何条目正文**。

## 步骤（有序）
1. **逐节点双源写作 + 格式落地**：对每个结构节点一次性完成「锁骨架 → 取原文 → 套格式」单节点闭环：
   - **(a) 锁骨架与页码锚点**（结构契约 `book_structure.json`，前置已确认，SSOT 见 `flows/extract/structure/structure.md`）：书对象 `sub_sec` 内按章顺序嵌套——每个 `type:"section"` 节点对应一个 `## §N.M` 标题（`name` 即带序标的纯标题，顺序照抄）；每个编号项节点（`type∉{section,exercise,chapter}`：定义 / 定理 / 引理 / 推论 / 命题 / 例 / 评注 / uncat）必须落地；`type:"exercise"` 节点为练习（照下方「习题收录规则」决定省略或保留）。⚠️ 此契约**只定骨架 + 印刷标题 + 页码区间，不含正文**，用于确认"写哪些、按什么顺序、每条目标题是什么"。
   - **(b) 取正文内容**（原文回归 `page_*.json`，内容来源）：对每个节点，按其 `page_start..page_end` 经 `data/page_json/page_json.py` 适配器读取 OCR 原文——`page_json.PageJson.load(fp).page_text()`（整页文本）或 `.text_blocks`（分块）。**以此原文为唯一内容来源**，忠于原文写出陈述 / 证明梗概 / 例题 / 评注；剔除页眉页脚版权行等噪声。
   - **(c) 套格式规则写源语言文件**：书写严格遵循 [`docs/writing-rules.md`](../../docs/writing-rules.md)（格式约定 **SSOT**）定义的全部格式——标题体系（`# 第N章` / `## §N.M` / `### §N.M.K`）、粗体条目标签（`**Definition 1.1**` 禁 `###`）、块引用、分隔线、`$$` 公式、图片嵌入（见子流程 figures）、练习收录；并须满足 [`verify/format_verify/format_verify.md`](../../verify/format_verify/format_verify.md) 的 **F 层格式校验（15 项格式规则 + KaTeX 真渲染）**——该层是 writing-rules 各项约定的机器化强制实现，**write-source 的输出须 100% 通过其步骤 3 的 verify 校验，否则整章 FAIL**。两层关系：writing-rules 定规则、format_verify 强制规则，authoring 阶段即按二者共同约束落笔，不要依赖后处理 / `--fix` 兜底。
   - **配合流程（单节点闭环）**：先用 (a) 锁骨架与页码锚点 → 再对每节点用 (b) 取原文写正文 → 同时按 (c) 落地格式 → 写完回查 (a) 保证 1:1 同构（无遗漏、无自创层级、无重排）。
2. 跑 `flows/script/embed_figures <book_dir>` 嵌入本章图片（见子流程 figures，Step 3.5，强制）。
3. **使用 `verify/verify.md` 批量校验所有总结文件**（源语言全部章节初稿写完 + 已嵌图后执行，🚫 仍须遵守规则 2 的批量纪律，禁止逐章校验）：
   ```bash
   python verify/script/verify_chapter.py --all <extract_dir> <book_dir>   # exit 0 才算通过
   ```
   未过则用 `--fix` 自动修复其中可修复层（`fix_order` 升序），再不带 `--fix` 复验确认 `exit 0`；至多 2 次仍不过则继续修，**严禁停下来问用户**。校验层语义 / `--fix` 范围 / 字节契约键见 [`verify/verify.md`](../../verify/verify.md) 与各 `verify/<snake>/<snake>.md`（每层 SSOT）。

## 本阶段规则（🔴 内联 + 核心原则）
- **🔴 规则0 — 写源硬闸（MM Repair `apply` 未完成 = 禁止写任何章节）**：启动 write-source 前，必须确认本书（或本批章节）的 MM Repair 已 `apply` 写回 `page_*.json`（验证法见 [`../extract/mm_repair/mm_repair.md`](../../extract/mm_repair/mm_repair.md) 出口条件）。**凡 `page_*.json` 仍无 `mm_repaired`/`mm_reviewed` 标记、或 manifest 中该章对应页仍有 `resolved != true` 条目的章节，一律不得动笔。**（`manifest.status` 因 `apply` 无条件设置而不可信，勿以它为放行依据。）宁可先补完 MM Repair（含模式 A 视觉审读——若用户拒绝视觉识别则按 [`../extract/mm_repair/mm_repair.md`](../../extract/mm_repair/mm_repair.md) Step 1 的 `VISION = no` 路径：仅模式 B / `MM_UNAVAILABLE`），也不要带着未修复的 OCR 噪声去写总结——写错源再返工的成本远高于先修数据。
- **规则1 — 源语言写作（硬底线）**：本步骤（write-source）只写**源语言**初稿——英文书每章写英文 `ChapterN_*.md`，中文书每章写中文 `第N章_*.md`。
- **规则2 — 写初稿期间禁止任何 per-chapter verify**：`verify` 统一在源语言全部初稿写完 + 已嵌图后、由步骤 3 用 `verify_chapter.py --all` 一次性批量进行。🚫 禁止"写完一章 verify 一章"，也禁止"第 1 章 pilot verify 后扇出"。
- **规则3 — 超大章按"节"拆分**（字符 > 60000 触发，中英文配对拆分）：`tools/split_chapters` 按节标题格式（`§N` 节标题式 / `N.M` 编号式）拆成每节一个文件；只拆到"节"一级，子节留父节内。幂等，拆分后默认删源合并文件（`--keep` 保留）。
- **核心原则（保真底线）**：OCR 噪声可修、表述可精简但**不得省略编号项 / 描述性内容中的公式概念**；**不编造**内容、**不编造结构**（不得新建原书没有的标题层级、不得重排条目顺序）；**严禁照抄 OCR 文本流**（页眉 / 页脚 / 版权行属噪声须剔除）；非核心内容须"摘要"而非整段照抄（Tier 1/2/3 分级见 `docs/writing-rules.md`）。
- **双源铁律（结构 ≠ 内容）**：正文**必须回归 `page_*.json` 原文**，禁止把结构契约的 `name` 当作正文来源、禁止脱离契约自创结构或重排顺序；契约只告诉你"有什么标题 / 在哪几页"，原文才告诉你"写什么内容"。
- **公式序标铁律**：书无号**不编造**；已标须**正确、不重复、不跨章**。

## 出口条件
- 出口：源语言全部章节初稿写完、已嵌图、且 `verify/script/verify_chapter.py --all` 对全书 `exit 0`（`verify PASS + KaTeX OK`）；格式修复经 verify 的 `--fix` 自动进行。

## 相关代码（路径相对 skill 根目录）
- `flows/extract/structure/script/build_structure`：统一结构契约生成器（产出 `book_structure.json` 书对象，内部调用 `scan_skeleton` / `extract_items` 系列，命令见 `flows/extract/extract.md`）。
- `flows/extract/structure/script/scan_skeleton`：结构骨架（章节标题扫描，仅被 `build_structure` 调用）。
- `flows/extract/structure/script/extract_items` + 变体（`_en` / `_gm` / `_vakil` / `_hom` / `_kt`）：编号项抽取，按 `ordinal` 被 `build_structure` 调用。
- `data/page_json/page_json.py`：`PageJson.load(fp).page_text()` / `.text_blocks` —— 写源时按节点 `page_start..page_end` 取 OCR 原文（双源 (b) 内容来源）。
- `tools/wrap_examples_bq` / `tools/fmt_proofs`：生产期格式变换脚本（可用 `cli.py` 的 `wrap-examples` / `fmt-proofs` 子命令单独调用，亦由 `derive-translate` 阶段对翻译版调用）。源版「顶层例/证包裹进 `>` + 连续性」已由 verify 的 **H 层 `h_mbq` + G 层** 在步骤 3 `verify --fix` 自动兜底，**无需** write-source 另行调用；其「证明步骤编号 / `$$` 形态归一」属编辑性生产变换，受 verify 字节契约（fix-dict 键 `{h,h_stmt,h_ul,h_mbq,c,g,i,j,k,l,m,n}` 不可扩）约束无法成为 verify fixer，故仍以 `tools/` 下的 CLI 工具形式保留，供翻译版 / 手动批处理使用。
- `../../verify/script/audit_counts.py`：逐节条数核对（原由 write-source 步骤 2 调用；该步骤取消后须在 cli 入口或 write-source 步骤 3 前另行挂接，否则源版缺失逐节条数核对）。
- `tools/split_chapters`：规则3 拆章（文件级结构拆分，非格式/校验，故归入 `tools/`）。
- `flows/script/embed_figures`：嵌图（Step 3.5）。
- `verify/script/verify_chapter.py`：步骤 3 批量校验（`--all` / `--fix`，语言无关，源/译共用）。

## 子流程
- [`写作规则`](../../docs/writing-rules.md) — 格式与保真规则（SSOT）
- [`write-source/figures`](figures/figures.md) — 嵌入图片（Step 3.5）
- [`verify`](../../verify/verify.md) — 批量校验关卡（步骤 3 引用）
