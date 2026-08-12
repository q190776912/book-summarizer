# math-blockquote-leak 层（M · `math_blockquote_leak`）

> **公用子流程（Sub-flow）。** 本文件是该校验层的**单一权威（SSOT）**，
> 同时作为可被其他消费者独立引用的校验子流程。
> 稳定标识符：`code="M"`（字母代号，被 `SKILL.md` 与 per-book 记忆广泛引用，不可更改）；
> 语义名：`math-blockquote-leak`（`math_blockquote_leak`）。

## 目的

## 一句话目的
显示公式块内不得有 `>` 前缀。
## 前置

- `<book>/_extract/verify_config.json` 完整合法。
- 依赖数据的层需 EXTRACT 层已填充 `ctx.items / entry_keys / all_keys`
（见 [data_provider](../data_provider/data_provider.md)）。

## 步骤

## 语义与检查内容
- **强制**：`$$...$$` 块内部每一行都不能以 `>`（块引用标记）开头。块引用上下文的 `>` 泄漏进公式块会导致 KaTeX 渲染失败（`>` 在数学模式非法）。可 `--fix` 自动剥离 `$$...$$` 内部的 `>` 前缀。
## 本阶段规则

## 阻断性 / 可修复
- `m_dm_gt` 非空 → 阻断 FAIL。
- 可 `--fix`。
## 出口

- 阻断层：对应字节契约键非空 → 该章 FAIL（exit 1）；`--fix` 流程按 `fix_order=10` 自动修复后复验。

## 相关代码

- 实现：`script/math_blockquote_leak.py`
  - `code="M"`，`order=13`，`auto_fixable=True`，`fix_order=10`。
- 注册：经 `../../script/register_all.py` 自动发现（`pkgutil` 扫描 `..` 子包），无需手动登记。

## 子流程

无独立子流程；本层为单一校验关注点。

## 字节契约键（legacy dict，供 `DEFAULT_RESULT` / `print_result` 同步）

```contract-keys
m_dm_gt
```

## 实现备注

## 实现（`script/math_blockquote_leak.py`）
- `code = 'M'`，`order = 13`，`auto_fixable = True`，`fix_order = 10`，`fix_dict = {'m': ...}`。
