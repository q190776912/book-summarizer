# P 层 — VERBOSE 闸门（反回归）（verbose_gates）

> 本文件是 **P 层** 的唯一权威详情（SSOT）。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verify.md`](../verify.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。
> **注册机制**：本层脚本位于 `verify/layers/verbose_gates/script/verbose_gates.py`，由 `verify/script/register_all.py` 用 `importlib` 按裸名扫描 `verify/layers/*/script/` 自动发现并注册。`code = 'P'` 是稳定字母代号（被 SKILL.md 与 per-book 记忆广泛引用，**不可更改**）；新增层无需改 `register_all.py` / `VerifyManager` / CLI。

## 目的
针对「照抄过度 / 自造结构 / OCR 噪声」的机器闸门，任一闸门非空即整章 FAIL。

## 步骤（语义与检查内容）
- **七道闸门**：
  1. `p_exer_block`：独立 `### 练习/习题/Exercises` 归拢块——专拦「无中生有新建归拢块」的违规（见 SKILL.md 🔴 规则与 [`../../flows/write-source/format/ref/formatting.md`](../../flows/write-source/format/ref/formatting.md) 习题规则）。策略为：**穿插在小节中的习题原位内联保留**（`**练习 N.M.X（Exercise N.M.X）：**`），**章末整块习题省略不写**；无论哪种，都禁止把原书穿插内容抽出来归拢成块。
  2. `p_noise`：OCR 噪声——页眉/页脚/版权行混进正文。
  3. `p_bare_item`：number-first 体例下条目标题缺失（裸 `**N.M.K**` 无标题）。
  4. `p_missing_sec`：缺节（md `## §` 数 < 骨架 SEC 数，骨架见 `book_structure.json` 书对象，由 `build_structure` 生成，SSOT 见 `flows/extract/structure/structure.md`）。
  5. `p_extra_item`：编造条目（md 出现骨架 ITEM 清单没有的编号条目）。
  6. `p_verbose`：顶层纯散文段（不含 `**` 标签条目/例/练习/注记的忠实内容、且**不含公式**）>450 字/段（`VERBOSE_PARA_CHARS`）且段数 ≥6（`VERBOSE_PARA_GATE`）即 FAIL。
  7. `p_proof_verbose`：单个 `> **证明/解答**` 块 >700 字且未分条枚举，且此类块 ≥2（`VERBOSE_PROOF_GATE`）即 FAIL。
- **关键豁免**：已用 `1. 2. 3. …` 分条枚举的证明【步数不限】不计入 `p_proof_verbose`；例（Example）题面与注记（Remark/Aside）按 Tier 1 忠实保留，不参与 verbose 判定。
- **🔴 含公式段落豁免 `p_verbose`（2026-08-06 新增，对应 SKILL.md Tier 2 修订）**：凡承载数学（`$...$` / `$$` / `\begin{}` / `\(`）的顶层段落，视为「忠实保留公式的描述性内容」（Tier 2 要求保留公式与概念），**不计入**长散文闸门。仅「纯散文（无公式）且 >450 字/段」仍受约束。此豁免确保忠实描述不会因段落较长被误杀，但仍拦得住真正整段照抄的纯散文 padding。
- **不可 `--fix`**（故意不让绕过），须回到写作阶段修正。

## 本阶段规则（阻断性 / 可修复）
- 任一闸门非空 → 整章 FAIL。
- **不可 `--fix`**。

## 出口条件
任一闸门非空 → 整章 FAIL。

## 相关代码（`verify/layers/verbose_gates/script/verbose_gates.py`）
- `code = 'P'`，`order = 16`，`auto_fixable = False`。
- 阈值 `VERBOSE_PARA_CHARS=450`（纯散文段长阈值，含公式段落豁免）/ `VERBOSE_PARA_GATE=6` / `VERBOSE_PROOF_GATE=2`（须与 `verbose_gates.py` 同步）。

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
  4. MISSING / FABRICATED SECTION vs CONTRACT：对照 `book_structure.json` 契约补回缺失条目，或删掉编造条目。
  5. VERBOSE TOP-LEVEL PROSE：顶层纯散文段 >450 字且 ≥6 段 → 精简为忠实要点，去掉照抄冗余描写（不丢关键内容）。
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
