# P 层 — VERBOSE 闸门（反回归）

> 本文件是 **P 层** 的唯一权威详情。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verification.md`](../verification.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。

## 一句话目的
针对「照抄过度 / 自造结构 / OCR 噪声」的机器闸门，任一闸门非空即整章 FAIL。

## 语义与检查内容
- **七道闸门**：
  1. `p_exer_block`：独立 `### 练习/习题/Exercises` 归拢块——专拦「无中生有新建归拢块」的违规（见 SKILL.md 🔴 规则与 `references/formatting.md` 习题规则）。策略为：**穿插在小节中的习题原位内联保留**（`**练习 N.M.X（Exercise N.M.X）：**`），**章末整块习题省略不写**；无论哪种，都禁止把原书穿插内容抽出来归拢成块。
  2. `p_noise`：OCR 噪声——页眉/页脚/版权行混进正文。
  3. `p_bare_item`：number-first 体例下条目标题缺失（裸 `**N.M.K**` 无标题）。
  4. `p_missing_sec`：缺节（md `## §` 数 < 骨架 SEC 数，骨架见 `extract/scan_skeleton.py`）。
  5. `p_extra_item`：编造条目（md 出现骨架 ITEM 清单没有的编号条目）。
  6. `p_verbose`：顶层长散文段（不含 `**` 标签条目/例/练习/注记的忠实内容）≥6 段（`VERBOSE_PARA_GATE`）即 FAIL。
  7. `p_proof_verbose`：单个 `> **证明/解答**` 块 >700 字且未分条枚举，且此类块 ≥2（`VERBOSE_PROOF_GATE`）即 FAIL。
- **关键豁免**：已用 `1. 2. 3. …` 分条枚举的证明【步数不限】不计入 `p_proof_verbose`；例（Example）题面与注记（Remark/Aside）按 Tier 1 忠实保留，不参与 verbose 判定。
- **不可 `--fix`**（故意不让绕过），须回到写作阶段修正。

## 阻断性 / 可修复
- 任一闸门非空 → 整章 FAIL。
- **不可 `--fix`**。

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

## 实现（`verify/layers/p_layer.py`）
- `code = 'P'`，`order = 16`，`auto_fixable = False`。
- 阈值 `VERBOSE_PARA_GATE=6` / `VERBOSE_PROOF_GATE=2`（须与 `p_layer.py` 同步）。
