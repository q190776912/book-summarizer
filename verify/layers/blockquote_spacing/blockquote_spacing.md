# N 层 — BQ EMPTY LINES（blockquote_spacing）

> 本文件是 **N 层** 的唯一权威详情（SSOT）。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verify.md`](../verify.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。
> **注册机制**：本层脚本位于 `verify/layers/blockquote_spacing/script/blockquote_spacing.py`，由 `verify/script/register_all.py` 用 `importlib` 按裸名扫描 `verify/layers/*/script/` 自动发现并注册。`code = 'N'` 是稳定字母代号（被 SKILL.md 与 per-book 记忆广泛引用，**不可更改**）；新增层无需改 `register_all.py` / `VerifyManager` / CLI。

## 目的
块引用内连续空 `>` 行不超过 1 行。

## 步骤（语义与检查内容）
- **强制**：`> **证明**`/`> **例**`/`> **注**` 等块内，连续空 `>` 行（仅 `>` 或 `> `）不得超过 1 行。过多空 `>` 行是提取噪声/视觉填充，不必要增大文件体积。可 `--fix` 删多余空 `>` 行（保留第 1 行）。

## 本阶段规则（阻断性 / 可修复）
- `n_bq_empty` 非空 → 阻断 FAIL。
- 可 `--fix`。

## 出口条件
`n_bq_empty` 非空 → 整章 FAIL。

## 相关代码（`verify/layers/blockquote_spacing/script/blockquote_spacing.py`）
- `code = 'N'`，`order = 14`，`auto_fixable = True`，`fix_order = 11`，`fix_dict = {'n': ...}`。

## 子流程
无独立子脚本。

## 字节契约键
```contract-keys
n_bq_empty
```
