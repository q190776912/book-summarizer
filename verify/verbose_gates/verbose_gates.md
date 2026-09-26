# P 层 — VERBOSE 闸门（反回归）（verbose_gates）

> 本文件是 **P 层** 的唯一权威详情（SSOT）。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verify.md`](../verify.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。
> **注册机制**：本层脚本位于 `verify/verbose_gates/script/verbose_gates.py`，由 `verify/script/register_all.py` 用 `importlib` 按裸名扫描 `verify/*/script/` 自动发现并注册。`code = 'P'` 是稳定字母代号（被 SKILL.md 与 per-book 记忆广泛引用，**不可更改**）；新增层无需改 `register_all.py` / `VerifyManager` / CLI。

## 目的
针对「照抄过度 / 自造结构 / OCR 噪声」的机器闸门，任一闸门非空即整章 FAIL。

## 步骤（语义与检查内容）
- **七道闸门**：
  1. `p_exer_block`：独立 `### 练习/习题/Exercises` 归拢块——专拦「无中生有新建归拢块」的违规（见 SKILL.md 🔴 规则与 [`../../docs/writing-rules.md`](../../docs/writing-rules.md) 习题规则）。策略为：**穿插在小节中的习题原位内联保留**（`**练习 N.M.X（Exercise N.M.X）：**`），**章末整块习题省略不写**；无论哪种，都禁止把原书穿插内容抽出来归拢成块。
  2. `p_noise`：OCR 噪声——页眉/页脚/版权行混进正文。
  3. `p_bare_item`：number-first 体例下条目标题缺失（裸 `**N.M.K**` 无标题）。
  4. `p_missing_sec`：缺节（md `## §` 数 < 骨架 SEC 数，骨架见分章契约 `book_structure/ch{N}.json`（经 `BookStructure.load` 聚合），由 `build_structure` 生成，SSOT 见 `flows/write-source/structure/structure.md`）。
     - `section_types` 不含 `0`（标准书，原书小节带序标）：该层级 `## §N[.M...]` 的数字须**逐一对齐**契约 `sub_sec` 编号（`present` 集合包含契约每个非习题节号）。
     - `section_types` 含 `0`（无序号标书，如 Silverman，对应 `type 0` / `depth 0`）：md 该层级写 `## § <标题>`（数字留空），闸门**不依赖数字**，改为按「位置/数量」比对——只查契约要求的每一节是否都在 md 中（按 `## §` 出现顺序位置对齐），**不报 md 多出契约未记的小节**（原书 subsection 可能多于稀疏契约，且 md 忠实于原书，多出的 `## §` 是合理的、不阻断）。仅当 md 的 `## §` 数**少于**契约必写节数时才报「缺节」。（`section_types` 是逐层级列表、**章层级计入元素 0**：Silverman 为 `[0, 0]`——元素 0 的 `0` 即「章无 `## §` 序号标」（章是文件 `# 第N章`，序号来自文件名），元素 1 的 `0` 才是「`## §` 小节无序号标」。两个 `0` 分别对应章与小节两个层级，不可合并。）
  5. `p_extra_item`：编造条目（md 出现骨架 ITEM 清单没有的编号条目）。
     - **两种形态同判据**（2026-09-23 Katok 实测：只认裸编号时，同一缺陷中文版报出、
       英文版静默）：裸编号头 `**13.3.3\***.` 与**标签式**头 `**Exercise 13.3.3\***` /
       `**习题 13.3.3**` / `**Corollary 6.2.5**` 都要查。取号用 `lib.util.sec_ordinals`，
       白名单 = 契约节点键的归一序标（`_load_contract` 对前缀词键「推论6.2.5」亦取其
       三级序标，dash 键 '6.1-5' 亦归一），单元门控第 23 项共用同一套判断。
     - 标签式形态额外要求首分量 == 本章章号，避免把正文里的跨章引用
       （`**Definition 3.2.1**（见第 3 章）`）误报成编造。
  6. `p_verbose`：顶层纯散文段在 >450 字/段（`VERBOSE_PARA_CHARS`）**且与源书 8-gram 重合率 ≥60%** 时违规；**>1200 字无条件违规**（硬顶）。`≥6 段`（`VERBOSE_PARA_GATE`）只是报告打印的聚合阈值，非判定条件（与 docs/writing-rules.md V-P 一致）。
  7. `p_proof_verbose`：单个 `> **证明/解答**` 块 >700 字且未分条枚举，且此类块 ≥2（`VERBOSE_PROOF_GATE`）即 FAIL。
- **关键豁免**：已用 `1. 2. 3. …` 分条枚举的证明【步数不限】不计入 `p_proof_verbose`；例（Example）题面与注记（Remark/Aside）按 Tier 1 忠实保留，不参与 verbose 判定。
- **🔴 段界（什么算「一段散文」）**：`>` 块引用、`#` 标题、`$$`、`---`、表格行 `|`、
  `<div>/<img>` 图块、``` 围栏代码块、以及 **`<!-- … -->` 机器注释行**（如单元首行
  `<!-- book-summarizer DONE unit: … -->`）都**不是**散文——它们只断开段落，不参与计量
  （2026-09-26 Rosen 实测：注释行曾被并进正文，虚增段长并把命中行号错报到 L1）。
  **列表项标号**（`- ` / `* ` / `1. ` / `(a) `）同样断段：一条条目 ≠ 一整段散文，否则术语表 /
  编号说明这类合法长列表会被合成一面「散文墙」误报（实测 Rosen ch3 §3.3 术语表 1913 字）。
- **🔴 Tier 1 题面标号豁免（`PROSE_GATE_STEM_RE`，两种模式都生效）**：段首是
  `58.` / `**5.** ` / `Exercise 62.` / `习题 6.` / `(a) ` 这类**条目号 / 题号**时放行——
  Rosen 每节末的集中习题块常被 OCR 灌进相邻 desc 节点（V-I 认可的归属），那里的题面是
  Tier 1 忠实内容，照抄是**正确**的；收紧 desc 决不能逼写手改写题面。
  `**Remark.**` / `**Historical Note.**` / `**A3.2 Assignments…**` 这类**印刷小标题**
  （run-in heading）不在豁免之列——它们就是被照抄的 Tier 2 散文。
- **🔴 两条 Tier-1 豁免由调用方按单元类型收紧（`label_exempt` / `math_exempt`）**：
  默认（合并 md 层、`item` / `exercise` 单元）仍豁免 ① `**粗体标签**` 起始的条目区域、
  ② 含公式（`$…$` / `$$` / `\begin{}` / `\(`）的段落——Tier 1 定理陈述与题面按原书忠实
  保留是**应该**的。但 **`desc` 单元按定义就是 Tier 2 散文**，写手只要在整段照抄前加一个
  段首粗体小标题、或让段内出现一个 `$x$`，就能拿到免检——Rosen 8e 附录 C 单元实测
  9286 B / 8 个粗体段全部照抄（重合率 0.88–1.00），单元门控与合并 md 两层全绿。
  故 `check_unit_quality` 第 19 项对 `utype == "desc"` 传
  `label_exempt=False, math_exempt=False`（旧豁免下 desc 全书命中 = **0 单元**，收紧后
  = **124 单元 / 195 段**，即整层此前完全失明）。
- **不可 `--fix`**（故意不让绕过），须回到写作阶段修正。

## 本阶段规则（阻断性 / 可修复）
- 任一闸门非空 → 整章 FAIL。
- **不可 `--fix`**。

## 出口条件
任一闸门非空 → 整章 FAIL。

## 相关代码（`verify/verbose_gates/script/verbose_gates.py`）
- `code = 'P'`，`order = 16`，`auto_fixable = False`。
- 阈值 `VERBOSE_PARA_CHARS=450` / `VERBOSE_PARA_HARD_CHARS=1200`（可读性硬顶，与重合率无关）/ `VERBOSE_OVERLAP_MIN=0.60` / `VERBOSE_PARA_GATE=6` / `VERBOSE_PROOF_GATE=2`（须与 `verbose_gates.py` 同步）。
- `check_verbose_paragraphs(lines, ext_dir=None, ch=None, label_exempt=True, math_exempt=True)`——**单元门控对 `desc` 单元传 `label_exempt=False, math_exempt=False`**；不传 `ext_dir`+`ch` 时退化为只拦硬顶长度（无源书上下文，不做重合率比对）。

## 子流程
无独立子脚本。

## 需 agent 手工修复（manual fix）
本层 `auto_fixable = False`——针对「照抄过度 / 自造结构 / OCR 噪声」的机器闸门，
须人工重写/精简，脚本不擅自动删（会破坏忠实性）。任一闸门非空即整章 FAIL。

- **触发门（report.py，P 层）**：
`P-LAYER EXERCISE CONSOLIDATION BLOCK` / `P-LAYER OCR/HEADER NOISE` /
`P-LAYER BARE ITEM NUMBER` / `P-LAYER MISSING SECTION vs CONTRACT` /
`P-LAYER FABRICATED ITEM vs CONTRACT` / `P-LAYER VERBOSE TOP-LEVEL PROSE` /
`P-LAYER VERBOSE PROOF/SOLUTION BLOCK`。
- **修复步骤**（逐项判断后在 `第N章_*.md` 修改）：
  1. EXERCISE CONSOLIDATION：练习须合并为单一 `> **练习**` 块，不要散落多处。
  2. OCR/HEADER NOISE：删掉误入的页眉/页脚/版权符（对照源 PDF 确认是 OCR 噪声）。
  3. BARE ITEM NUMBER：编号在前的条目须补 `**标签**`（如 `**4.2-1 例**`）。
  4. MISSING / FABRICATED SECTION vs CONTRACT：对照分章契约（`book_structure/ch{N}.json`）补回缺失条目，或删掉编造条目。
  5. VERBOSE TOP-LEVEL PROSE：顶层散文段 >450 字且 8-gram 重合率 ≥60%（或 >1200 字硬顶）→ **改写表述**（换句法与用词，把连续 8 词与原文相同的片段消掉），全部概念 / 公式 / 变量 / 例子 / 专名一律保留，**不是删内容**；>1200 字的墙式段另需拆成若干较短段落或用 `>` / 列表承载其中的枚举。
  6. VERBOSE PROOF/SOLUTION：单个证明/解答块 >700 字且未分条 → 拆成 numbered 子项。
  7. 修改后重跑 verify，确认 P-LAYER 各闸门为空。

修复后重跑 `verify_chapter.py --all`（或单章 `<ch> <start> <end> <md> <ext>`）确认上述门为空 / 转绿。

## 字节契约键
```contract-keys
p_exer_block
p_noise
p_bare_item
p_missing_sec
p_extra_item
p_verbose
p_proof_verbose
```
