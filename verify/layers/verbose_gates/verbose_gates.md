# verbose-gates 层（P · `verbose_gates`）

> **公用子流程（Sub-flow）。** 本文件是该校验层的**单一权威（SSOT）**，
> 同时作为可被其他消费者独立引用的校验子流程。
> 稳定标识符：`code="P"`（字母代号，被 `SKILL.md` 与 per-book 记忆广泛引用，不可更改）；
> 语义名：`verbose-gates`（`verbose_gates`）。

## 目的

## 一句话目的
针对「照抄过度 / 自造结构 / OCR 噪声」的机器闸门，任一闸门非空即整章 FAIL。
## 前置

- `<book>/_extract/verify_config.json` 完整合法。
- 依赖数据的层需 EXTRACT 层已填充 `ctx.items / entry_keys / all_keys`
（见 [data_provider](../data_provider/data_provider.md)）。

## 步骤

## 语义与检查内容
- **七道闸门**：
  1. `p_exer_block`：独立 `### 练习/习题/Exercises` 归拢块——专拦「无中生有新建归拢块」的违规（见 SKILL.md 🔴 规则与 `verbose_gates.md` 习题规则）。策略为：**穿插在小节中的习题原位内联保留**（`**练习 N.M.X（Exercise N.M.X）：**`），**章末整块习题省略不写**；无论哪种，都禁止把原书穿插内容抽出来归拢成块。
  2. `p_noise`：OCR 噪声——页眉/页脚/版权行混进正文。
  3. `p_bare_item`：number-first 体例下条目标题缺失（裸 `**N.M.K**` 无标题）。
  4. `p_missing_sec`：缺节（md `## §` 数 < 骨架 SEC 数，骨架见 `flows/extract/script/extract/scan_skeleton`）。
  5. `p_extra_item`：编造条目（md 出现骨架 ITEM 清单没有的编号条目）。
  6. `p_verbose`：顶层纯散文段（不含 `**` 标签条目/例/练习/注记的忠实内容、且**不含公式**）>450 字/段（`VERBOSE_PARA_CHARS`）且段数 ≥6（`VERBOSE_PARA_GATE`）即 FAIL。
  7. `p_proof_verbose`：单个 `> **证明/解答**` 块 >700 字且未分条枚举，且此类块 ≥2（`VERBOSE_PROOF_GATE`）即 FAIL。
- **关键豁免**：已用 `1. 2. 3. …` 分条枚举的证明【步数不限】不计入 `p_proof_verbose`；例（Example）题面与注记（Remark/Aside）按 Tier 1 忠实保留，不参与 verbose 判定。
- **🔴 含公式段落豁免 `p_verbose`（2026-08-06 新增，对应 SKILL.md Tier 2 修订）**：凡承载数学（`$...$` / `$$` / `\begin{}` / `\(`）的顶层段落，视为「忠实保留公式的描述性内容」（Tier 2 要求保留公式与概念），**不计入**长散文闸门。仅「纯散文（无公式）且 >450 字/段」仍受约束。此豁免确保忠实描述不会因段落较长被误杀，但仍拦得住真正整段照抄的纯散文 padding。
- **不可 `--fix`**（故意不让绕过），须回到写作阶段修正。
## 本阶段规则

## 阻断性 / 可修复
- 任一闸门非空 → 整章 FAIL。
- **不可 `--fix`**。
## 出口

- 阻断层：对应字节契约键非空 → 该章 FAIL（exit 1）；不可 `--fix`，须回写作阶段修正。

## 相关代码

- 实现：`script/verbose_gates.py`
  - `code="P"`，`order=16`，`auto_fixable=False`。
- 注册：经 `../../script/register_all.py` 自动发现（`pkgutil` 扫描 `..` 子包），无需手动登记。

## 子流程

含 7 道闸门（`p_exer_block/p_noise/p_bare_item/p_missing_sec/p_extra_item/p_verbose/p_proof_verbose`），全部归属 `code="P"`。

## 字节契约键（legacy dict，供 `DEFAULT_RESULT` / `print_result` 同步）

```contract-keys
p_exer_block
p_noise
p_bare_item
p_missing_sec
p_extra_item
p_verbose
p_proof_verbose
```

## 实现备注

## 实现（`script/verbose_gates.py`）
- `code = 'P'`，`order = 16`，`auto_fixable = False`。
- 阈值 `VERBOSE_PARA_CHARS=450`（纯散文段长阈值，含公式段落豁免）/ `VERBOSE_PARA_GATE=6` / `VERBOSE_PROOF_GATE=2`（须与 `p_layer.py` 同步）。
