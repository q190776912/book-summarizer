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
- **HEAD/INTERNAL gap（阻断 FAIL）**：序列起始 >1 或 min–max 间缺号 → 视为真实遗漏，须补回（`x` 行，`problems += 1`）。
  HEAD 的 `missing (...)` **只列未被抑制集合吃掉的号**（旧版把 `1..min-1` 整段列出，读者分不清
  哪些真缺；判定口径不变，仅收窄显示）。
- **TAIL gap（仅告警）**：OCR 交叉引用显示更大编号（如 md 最大 `(3)`、OCR 出现 `(5)`）→ 打印 `~` 行提示复核，不阻断。
- 与 J 层互补：O 管「编号子项是否连续」，J 管「块内分隔线」。

## 本阶段规则（阻断性 / 可修复）
- `o_subitem_gaps` 中以 `x` 开头的条目 → 阻断 FAIL；`~` 开头仅告警。
- **不可 `--fix`**，须手动补项或确认。

## 出口条件
`o_subitem_gaps` 中含 `x` 行 → 整章 FAIL；`~` 行仅 WARN。

## 相关代码（`verify/subitem_continuity/script/subitem_continuity.py`）
- `code = 'O'`，`order = 15`，`auto_fixable = False`。
- 负向测试：`verify/tests/test_subitem_continuity_inline_head.py`（行内标记版式三例 +
  粘连交叉引用负例 + `_label_ordinals` 语义 + 「真缺口仍须报」两类，防修复过度）。
- 负向测试：`verify/tests/test_subitem_continuity_star_decl.py`（难度星号条目 + 组题声明
  共九例：两种假阳消除各配一条「删掉星号行/声明行后必须照报」的负例，外加粗体序标头、
  `**Note 3.` 标签头、`See Exercises 3-5` 交叉引用、跨度过大声明四种「不得误认条目」负例）。

## 子流程
无独立子脚本。

## 需 agent 手工修复（manual fix）
本层 `auto_fixable = False`。带括号子编号（如 `(1)(2)`）缺号 = 子项遗漏，须补写，脚本不编。

- **触发门（report.py）**：`O-LAYER SUBITEM GAPS`（`x` 行）→ 阻断 FAIL；
`O-LAYER SUBITEM TAIL`（`~` 行）→ 仅告警。
- **修复步骤**：
  1. 看 `O-LAYER SUBITEM GAPS` 列出的 `x` 行（如父项 `(3)` 缺失）。
  2. 回源 PDF 确认子项确实漏写；补写该编号子项（忠于原文），并在 `manual_overrides` 登记。
  3. `O-LAYER SUBITEM TAIL`（`~` 行）仅 WARN——OCR 显示更大编号时人工核对是否真漏尾部。
  4. 重跑 verify，确认 `O-LAYER SUBITEM GAPS` 中无 `x` 行。

修复后重跑 `verify_chapter.py --all`（或单章 `<ch> <start> <end> <md> <ext>`）确认上述门为空 / 转绿。

## 字节契约键
```contract-keys
o_subitem_gaps
```
