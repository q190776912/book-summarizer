# O 层 — SUBITEM GAP（subitem_continuity）

> 本文件是 **O 层** 的唯一权威详情（SSOT）。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verify.md`](../verify.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。
> **注册机制**：本层脚本位于 `verify/subitem_continuity/script/subitem_continuity.py`，由 `verify/script/register_all.py` 用 `importlib` 按裸名扫描 `verify/*/script/` 自动发现并注册。`code = 'O'` 是稳定字母代号（被 SKILL.md 与 per-book 记忆广泛引用，**不可更改**）；新增层无需改 `register_all.py` / `VerifyManager` / CLI。

## 目的
编号子项序列（`(1)(2)(3)` / `(a)(b)(c)` / `(i)(ii)(iii)`）缺口检查。

## 步骤（语义与检查内容）
- 仅当块内序号项 ≥3 才检测（避免把交叉引用误判为序列）。
- **异质块跳过（🔴 2026-09-16 修复）**：一个块内混有**两条不同序列**时判 `'mixed'` 并跳过，
  不产出任何缺口——判据是相邻（阅读顺序）编号**跳幅 > `_MAX_ORDINAL_JUMP`(20)**。
  - 背景（statistical-inference 3.33/3.34 实测）：教材常见「罗马任务段 + 字母选项段」
    同处一块，如 `(i)(ii)(iii)` 任务 + `(a)(b)(c)(d)` 族。而 `c`/`d` 恰好也是合法罗马
    字符（100/500），旧逻辑只要**多字符**标签（ii/iii）是合法罗马就把**整块**过
    `_roman_to_int`，得 `[1,2,3,100,500]` → 凭空算出 4..499 一串**幽灵号**。
  - 真缺号是「中间少几个」（跳幅小），把另一条序列的头接进来才会「跳到很远」，
    故跳幅阈值可安全区分二者；20 足够宽松，不吞正常 roman / numeric / alpha 序列。
- **行内子项标记（🔴 2026-09-25 修复，专治「假 HEAD gap」）**：三条检测正则全部**行首锚定**，
  而教材常见版式把子项标记写在**行内**（标题冒号后、或粗体头之后），于是块内第一条
  真实出现的 `a)` 若在行内，就会被误判成「序列从 `b)` 开始」→ 凭空 `x` HEAD gap（缺 `(a)`）。
  - `_O_INLINE_BARE_RE`（`a)` / `b)` 裸式）、`_O_INLINE_PAREN_RE`（`(a)` / `（a）` 括号式），
    两者要求标记后紧跟空白 / 冒号 / `*`，且前面不是数字字母（防粘连交叉引用误伤）。
  - `_label_ordinals(lb)`：一个原始标签的**全部合理解读**序号集合（数字 / 字母 / 罗马）。
    如 `c` → `{3, 100}`、`ii` → `{2, 243}`。**异质块的 `ords` 由它按并集构造**——并集只会
    减少告警，不可能凭空造出告警。
  - `_o_inline_ordinals(line)`：先剥行内公式（`_INLINE_MATH_RE`）再扫两种行内式。
  - 🔴 **行内集合只喂 HEAD 抑制集**（`head_inline_ords` 窗口 → `_head_prev`），
    **绝不进块内序列本身**参与 INTERNAL/TAIL 计算：行内标记是「这一行开头有编号」的证据，
    不是「该子项独立成项」的证据，喂进序列会造出新的假缺口。
- **重启切段（🔴 2026-09-26 修复，专治「多清单并块 → 幽灵缺号」）**：
  `_o_split_restarts(ordinal_items)` 按**阅读顺序**在数值下降处（`v < 前一个值`）把块内序列
  切成若干段，**INTERNAL 只在段内求缺**。
  - 背景（Rosen《Discrete Mathematics》8e ch9 章末实测）：`Supplementary Exercises 42–50` 之后
    紧跟 `Computer Projects 1–15` + `Computations and Explorations 1–9` + `Writing Projects 1–12`
    ——**四条各自从 1 重启的独立清单**；标题行只把相邻题距撑开 2 行（≤4），于是全部并进同一块。
    旧实现按整块 min–max 求缺 → 凭空报 `missing: (16, …, 41)` 共 26 个**幽灵号**
    （那些号本就属于另一条清单，不该出现在这一条里）。
  - 判据：「数值下降」是换清单的证据；真缺号是「同一条清单中间少几个」，不会下降。
  - 配套把 INTERNAL 抑制集放宽为 `prev_ords | block_union`（同块其他段的号也算已见）——
    与切段配合后本次改动**只减少告警、绝不新增**（乱序块 `[1,2,4,3,5]` 切段也不新报）。
  - 🔴 **HEAD 判定口径不变**（仍按整块 `min_ord` 与既有宽抑制），切段只作用于 INTERNAL。
  - 切点二：**版式切换**（🔴 2026-10-03 新增，茆诗松《概率论与数理统计教程》ch3/ch5 实测）。
    一道大题的子项 `(1)(2)` 与**下一道大题号** `30.` 行距 ≤4 被并进同一块，而数值是**上升**的
    （2 → 30），「数值下降」切不到 → 整块按 1..30 求缺，凭空造出 `missing: (3,…,29)` 并判
    blocking（`x` 行）。子项清单与顶层大题号是**两条不同层级**的序列，绝不该并成一条求缺。
    - `_o_line_style(line)` 给出行首序号的版式：`'paren'`（`(1)` / `（2）`）、`'bold'`（`**1.**`）、
      `'dot'`（`1.` / `*5.`），非编号行返回 `None`；派发顺序与 `_o_match_line` 完全一致。
    - `_o_split_restarts` 的元素可携带第 3 位版式；**2 元组视为版式未知**（既有调用方与测试
      传 2 元组 → 行为与新增前完全一致）。
    - 切段只会把「整段求缺」收窄成「段内求缺」→ 缺号集合只可能变小，**绝不新增告警**。
- **难度星号条目（🔴 2026-09-26 修复，Rosen 8e ch10 实测）**：Rosen 在习题号**前**印
  `*` / `**` 标难度（`**27. Find the crossing number…`），三条行首锚定正则都不认这个前缀
  → 整条题面从序列里消失 → 凭空 HEAD/INTERNAL 缺号。
  - `_O_STAR_NUM_RE`（Pattern D）：`^\s{0,3}\*{1,2}([0-9]+)[.)]\s+\S` 只吃**最多两个**前导星号 +
    数字号，且要求点后跟空格与非空正文。
  - 负例必须仍然**不匹配**：`**3.1.4.**`（三级序标粗体头）、`**Note 3. …`（带标签粗体头）
    都不是条目；`*` 单独成行也不匹配。
- **组题声明行（🔴 2026-09-26 修复，Rosen 8e ch10 实测）**：每个 Exercise Set 常以
  `**Exercises 13-15.**` / `For Exercises 3-9, …` / `In Exercises 5-11` 声明「这几题共用下面
  那张图」——被声明的题**只有图、没有编号题面行**，因此序列里永远不会出现这些号 →
  旧版报整段幽灵缺号（`missing: (13, 14, 15)`）。
  - `_o_group_decl_ordinals(line)` 解析声明覆盖的号集合（`_O_GROUP_DECL_RE`，先剥行内公式）；
    区间跨度 > `_O_DECL_MAX_SPAN`(60) 视为误匹配（返回空集），`See Exercises 3-5 for …` 这类
    纯交叉引用不以 `For/In/Exercises` 起头，天然不匹配。
  - 声明行本身不是条目，故只作**抑制证据**：按阅读序附到**后序**最近的块（退路=前序块，
    窗口 `_O_DECL_ATTACH_WINDOW`=120 行），并进该块 `decl` 与 `ords`。
  - 🔴 抑制集因此扩为 HEAD `… | decl_here`、INTERNAL `prev_ords | block_union | decl_here`；
    与既往一致，**只减少告警、绝不新增**（负例：删掉声明行后同一份 md 必须照报该组号）。
  - 🔴 **中文版声明同样要认**（2026-09-27 Rosen 8e ch10 §10.1 中文版实测）：同一段落译成
    `对习题 3 至 9，判断…` 后版式分毫不差，却因 `_O_GROUP_DECL_RE` 的英文偏置（介词只列
    `For|In`、范围连接词只列 `[-–—]`）漏匹配 → 中文版凭空报出 3 条 `HEAD gap … missing (6, 7, 8, 9)`
    而英文版绿灯。现接受可选中文介词前缀（对/对于/针对/在/关于）与 `至|到|~|～` 连接词。
    判据语言中立化，**不改译文**（禁止为迎合判据删改忠实译文）。
    负向/正向测试：`verify/tests/test_o_layer_group_decl_bilingual.py`（EN 与 CN 两种措辞同为零告警，
    删掉声明行后两版都必须复现缺号）。
- **HEAD/INTERNAL gap（阻断 FAIL）**：序列起始 >1 或 min–max 间缺号 → 视为真实遗漏，须补回（`x` 行，`problems += 1`）。
  HEAD 的 `missing (...)` **只列未被抑制集合吃掉的号**（旧版把 `1..min-1` 整段列出，读者分不清
  哪些真缺；判定口径不变，仅收窄显示）。
- **TAIL gap（仅告警）**：OCR 交叉引用显示更大编号（如 md 最大 `(3)`、OCR 出现 `(5)`）→ 打印 `~` 行提示复核，不阻断。
  判据窗口是「本章页窗内**含同一上下文关键词的整页**」（`_o_tail_ocr_scan`，最多前 20 页），
  所以**同页另一张清单或证明里的公式回指**必然命中 → 结构性假阳高发。实测两类（Katok 2026-10-03）：
  Theorem 5.5.21 的 `Then: (1)(2)(3)` 被**章内另一页**习题 5.1.6 的 `(4)(5)` 判尾缺；
  补篇 Definition S.3.3 的 `Remarks (1)(2)(3)` 被同页 Theorem S.3.1 证明里的公式回指 `(4)` 判尾缺。
  因此 `~` 行**自带登记命令**（含章参与签名）。核对印面确无尾缺后，用
  `attest_o_tail.py` 把「签名 → 印面页码取证」登记进
  `<extract>/ignore_o_tail_{chapter_label}.json`，此后该行静默豁免（与 `ignore_fig_*` 同构：
  侧车本身就是取证记录）。签名 = `上下文标签|md最大号|OCR更大号`（标签去尾部冒号），
  **只有同号同清单的再次出现才被豁免**；🔴 **理由为空一律不生效**、**真尾缺禁止用本通道消音**
  （一律补写正文）；HEAD/INTERNAL 的 `x` 行**不受侧车影响**。
- 与 J 层互补：O 管「编号子项是否连续」，J 管「块内分隔线」。

## 本阶段规则（阻断性 / 可修复）
- `o_subitem_gaps` 中以 `x` 开头的条目 → 阻断 FAIL；`~` 开头仅告警。
- **不可 `--fix`**，须手动补项或确认。

## 出口条件
`o_subitem_gaps` 中含 `x` 行 → 整章 FAIL；`~` 行仅 WARN。

## 相关代码（`verify/subitem_continuity/script/subitem_continuity.py`）
- `code = 'O'`，`order = 15`，`auto_fixable = False`。
- TAIL 印面确证通道：`o_tail_signature` / `o_tail_ignore_path` / `load_o_tail_exemptions`
  （侧车文件名段与 `chapter_label` 同源，SSOT 标签取不到时按**磁盘物理证据**回退
  `ch/appendix/supplement` 三种章型同名文件——与 `resolve_chapter_json_path` 同一纪律，
  防进程级 kind 注册表未灌注让已登记豁免静默失效）；登记 CLI
  `verify/subitem_continuity/script/attest_o_tail.py`（`--list` 查看、`--sig/--reason` 登记，
  空理由 exit 2 拒绝，侧车非字典时拒绝改写而不是覆盖）。
- 负向测试：`verify/tests/test_o_tail_printed_attestation.py`（9 例：基线 `~` 行 + 签名形状 +
  登记后静默 + CLI 登记→复验静默，配三条「不得泛化」负例——空理由不生效、**别的签名不生效**
  （防一次登记关掉整章 TAIL 通道）、CLI 拒绝无取证登记；另含 HEAD/INTERNAL `x` 行不受侧车影响、
  侧车坏 JSON fail-open 到告警）。
- 负向测试：`verify/tests/test_subitem_continuity_inline_head.py`（行内标记版式三例 +
  粘连交叉引用负例 + `_label_ordinals` 语义 + 「真缺口仍须报」两类，防修复过度）。
- 负向测试：`verify/tests/test_subitem_continuity_star_decl.py`（难度星号条目 + 组题声明
  共九例：两种假阳消除各配一条「删掉星号行/声明行后必须照报」的负例，外加粗体序标头、
  `**Note 3.` 标签头、`See Exercises 3-5` 交叉引用、跨度过大声明四种「不得误认条目」负例）。

## 子流程
`verify/subitem_continuity/script/attest_o_tail.py`（TAIL 印面确证豁免登记，写
`<extract>/ignore_o_tail_{chapter_label}.json`；🔴 只登记「已核对印面确认无尾缺」的行，
不产出任何正文改动）。

### 跨语料普查（2026-10-04，51 书全量，只跑 O 层判据）
- 可加载 32 书中 TAIL 行共 **9 条**（Katok 3 条已登记豁免；其余 6 条分布在 4 本书：
  冯琦集合论两卷、概率论与数理统计教程、Lie 代数表示论），**无一例经印面证实为真尾缺**。
- 形态一致：上下文标签全是「上一非空行截断 30 字」的兜底散文（`那么` / `则有` /
  `是一条逻辑公理；` / `note`）或章内通用连接词，于是「含该关键词的整页」窗口几乎不受限，
  同页/同章另一张清单与公式回指必然命中。
- **为什么不改判据**（曾评估「候选号须在关键词之后且距离受限」的收窄）：Katok p216 的
  `(4)(5)` 距最后一个 `Then` 约 1000 字符，而其自身前导 `(1)(2)(3)` 与真清单的写法完全同形
  ——机械上无法区分「另一张清单」与「本清单延续」，任何距离/顺序阈值都会同时削掉真尾缺的检出
  （违反「放宽判据须跨 51 书普查校准」的前置条件）。故保持检出不变，只加**带印面取证的豁免通道**
  （签名不符 / 理由为空一律不生效，新形态的尾缺照常报）。

## 需 agent 手工修复（manual fix）
本层 `auto_fixable = False`。带括号子编号（如 `(1)(2)`）缺号 = 子项遗漏，须补写，脚本不编。

- **触发门（report.py）**：`O-LAYER SUBITEM GAPS`（`x` 行）→ 阻断 FAIL；
`O-LAYER SUBITEM TAIL`（`~` 行）→ 仅告警。
- **修复步骤**：
  1. 看 `O-LAYER SUBITEM GAPS` 列出的 `x` 行（如父项 `(3)` 缺失）。
  2. 回源 PDF 确认子项确实漏写；补写该编号子项（忠于原文），并在 `manual_overrides` 登记。
  3. `O-LAYER SUBITEM TAIL`（`~` 行）仅 WARN——OCR 显示更大编号时人工核对是否真漏尾部：
     回源看**该行自己的窗口**（章页窗内含该上下文关键词的页），确认更大号属于
     ①另一张清单 / ②证明或正文里的公式回指 / ③本清单真缺的第 N 项。
     ①② → 用告警行末给出的命令登记（`attest_o_tail.py … --sig --reason`，理由必须写**页码取证**）；
     ③ → 补写正文，**不得登记消音**。
  4. 重跑 verify，确认 `O-LAYER SUBITEM GAPS` 中无 `x` 行。

修复后重跑 `verify_chapter.py --all`（或单章 `<ch> <start> <end> <md> <ext>`）确认上述门为空 / 转绿。

## 字节契约键
```contract-keys
o_subitem_gaps
```
