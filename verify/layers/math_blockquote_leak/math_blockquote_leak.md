# M 层 — DISPLAY-MATH `>`（math_blockquote_leak）

> 本文件是 **M 层** 的唯一权威详情（SSOT）。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verify.md`](../verify.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。
> **注册机制**：本层脚本位于 `verify/layers/math_blockquote_leak/script/math_blockquote_leak.py`，由 `verify/script/register_all.py` 用 `importlib` 按裸名扫描 `verify/layers/*/script/` 自动发现并注册。`code = 'M'` 是稳定字母代号（被 SKILL.md 与 per-book 记忆广泛引用，**不可更改**）；新增层无需改 `register_all.py` / `VerifyManager` / CLI。

## 目的
显示公式块内不得有 `>` 前缀。

## 步骤（语义与检查内容）
- **强制**：`$$...$$` 块内部每一行都不能以 `>`（块引用标记）开头。块引用上下文的 `>` 泄漏进公式块会导致 KaTeX 渲染失败（`>` 在数学模式非法）。可 `--fix` 自动剥离 `$$...$$` 内部的 `>` 前缀。

## 本阶段规则（阻断性 / 可修复）
- `m_dm_gt` 非空 → 阻断 FAIL。
- 可 `--fix`。

## 出口条件
`m_dm_gt` 非空 → 整章 FAIL。

## 相关代码（`verify/layers/math_blockquote_leak/script/math_blockquote_leak.py`）
- `code = 'M'`，`order = 13`，`auto_fixable = True`，`fix_order = 10`，`fix_dict = {'m': ...}`。

## 子流程
无独立子脚本。

## 字节契约键
```contract-keys
m_dm_gt
```
