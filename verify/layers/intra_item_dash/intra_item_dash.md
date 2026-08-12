# J 层 — ITEM-HEADER DASH（intra_item_dash）

> 本文件是 **J 层** 的唯一权威详情（SSOT）。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verify.md`](../verify.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。
> **注册机制**：本层脚本位于 `verify/layers/intra_item_dash/script/intra_item_dash.py`，由 `verify/script/register_all.py` 用 `importlib` 按裸名扫描 `verify/layers/*/script/` 自动发现并注册。`code = 'J'` 是稳定字母代号（被 SKILL.md 与 per-book 记忆广泛引用，**不可更改**）；新增层无需改 `register_all.py` / `VerifyManager` / CLI。

## 目的
条目块（标题 → 全部子点）内部不得出现 `---`。

## 步骤（语义与检查内容）
- **ITEM-HEADER DASH（阻断 FAIL，可修）**：顶层条目块（标题行到其全部 `**(N)**` 子点）内部出现 `---` → 删除。
- 覆盖两种：标题↔首个子点之间、子点↔子点之间；`---` 上方即使是子点接续文本/`$$` 仍属块内。
- 实现用 `in_item` 跨行追踪：`**LABEL**`/`**(N)**` 置 True，`## `/`>` 行置 False；顶层 `---` 且 `in_item` 且其后首个非空非块引用行是 `**(N)**` → 违规。
- 与 I 层互补：`---` 只用于**不同**顶层条目之间。

## 本阶段规则（阻断性 / 可修复）
- `j_header_dash` 非空 → 阻断 FAIL（计入 `problems`，非零即 FAIL）。
- 可 `--fix`。

## 出口条件
`j_header_dash` 非空 → 整章 FAIL。

## 相关代码（`verify/layers/intra_item_dash/script/intra_item_dash.py`）
- `code = 'J'`，`order = 10`，`auto_fixable = True`，`fix_order = 7`，`fix_dict = {'j': ...}`。
- `--fix` 删条目块内所有 `---` 并合并其后单个空行（幂等）。

## 子流程
无独立子脚本。

## 字节契约键
```contract-keys
j_header_dash
```
