# L 层 — SEP BLANKS（separator_spacing）

> 本文件是 **L 层** 的唯一权威详情（SSOT）。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verify.md`](../verify.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。
> **注册机制**：本层脚本位于 `verify/layers/separator_spacing/script/separator_spacing.py`，由 `verify/script/register_all.py` 用 `importlib` 按裸名扫描 `verify/layers/*/script/` 自动发现并注册。`code = 'L'` 是稳定字母代号（被 SKILL.md 与 per-book 记忆广泛引用，**不可更改**）；新增层无需改 `register_all.py` / `VerifyManager` / CLI。

## 目的
`---` 分隔线上下需有空行。

## 步骤（语义与检查内容）
- **强制**：每个 `---` 上方和下方都必须紧邻一空白行（`正文\n\n---\n\n正文`）。无空白行时 `---` 可能被误解为 setext 标题下划线或被渲染器吞没。可 `--fix` 自动补缺失空白行。

## 本阶段规则（阻断性 / 可修复）
- `l_sep_blanks` 非空 → 阻断 FAIL。
- 可 `--fix`。

## 出口条件
`l_sep_blanks` 非空 → 整章 FAIL。

## 相关代码（`verify/layers/separator_spacing/script/separator_spacing.py`）
- `code = 'L'`，`order = 12`，`auto_fixable = True`，`fix_order = 9`，`fix_dict = {'l': ...}`。

## 子流程
无独立子脚本。

## 字节契约键
```contract-keys
l_sep_blanks
```
