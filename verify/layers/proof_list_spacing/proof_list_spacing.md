# K 层 — PROOF-LIST BLANK（proof_list_spacing）

> 本文件是 **K 层** 的唯一权威详情（SSOT）。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verify.md`](../verify.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。
> **注册机制**：本层脚本位于 `verify/layers/proof_list_spacing/script/proof_list_spacing.py`，由 `verify/script/register_all.py` 用 `importlib` 按裸名扫描 `verify/layers/*/script/` 自动发现并注册。`code = 'K'` 是稳定字母代号（被 SKILL.md 与 per-book 记忆广泛引用，**不可更改**）；新增层无需改 `register_all.py` / `VerifyManager` / CLI。

## 目的
编号列表后、证明块前需有空行。

## 步骤（语义与检查内容）
- **强制**：定理/定义的陈述含 4-空格缩进编号列表（`    N.`），且其后紧接 `> **证明**`/`> **证明思路**` 块引用时，列表末项与证明块之间**必须有一空行**。否则证明块渲染时视觉对齐编号项而非定理外层。可 `--fix` 自动插入空行。

## 本阶段规则（阻断性 / 可修复）
- `k_proof_list` 非空 → 阻断 FAIL。
- 可 `--fix`。

## 出口条件
`k_proof_list` 非空 → 整章 FAIL。

## 相关代码（`verify/layers/proof_list_spacing/script/proof_list_spacing.py`）
- `code = 'K'`，`order = 11`，`auto_fixable = True`，`fix_order = 8`，`fix_dict = {'k': ...}`。

## 子流程
无独立子脚本。

## 字节契约键
```contract-keys
k_proof_list
```
