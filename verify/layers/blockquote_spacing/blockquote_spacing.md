# blockquote-spacing 层（N · `blockquote_spacing`）

> **公用子流程（Sub-flow）。** 本文件是该校验层的**单一权威（SSOT）**，
> 同时作为可被其他消费者独立引用的校验子流程。
> 稳定标识符：`code="N"`（字母代号，被 `SKILL.md` 与 per-book 记忆广泛引用，不可更改）；
> 语义名：`blockquote-spacing`（`blockquote_spacing`）。

## 目的

## 一句话目的
块引用内连续空 `>` 行不超过 1 行。
## 前置

- `<book>/_extract/verify_config.json` 完整合法。
- 依赖数据的层需 EXTRACT 层已填充 `ctx.items / entry_keys / all_keys`
（见 [data_provider](../data_provider/data_provider.md)）。

## 步骤

## 语义与检查内容
- **强制**：`> **证明**`/`> **例**`/`> **注**` 等块内，连续空 `>` 行（仅 `>` 或 `> `）不得超过 1 行。过多空 `>` 行是提取噪声/视觉填充，不必要增大文件体积。可 `--fix` 删多余空 `>` 行（保留第 1 行）。
## 本阶段规则

## 阻断性 / 可修复
- `n_bq_empty` 非空 → 阻断 FAIL。
- 可 `--fix`。
## 出口

- 阻断层：对应字节契约键非空 → 该章 FAIL（exit 1）；`--fix` 流程按 `fix_order=11` 自动修复后复验。

## 相关代码

- 实现：`script/blockquote_spacing.py`
  - `code="N"`，`order=14`，`auto_fixable=True`，`fix_order=11`。
- 注册：经 `../../script/register_all.py` 自动发现（`pkgutil` 扫描 `..` 子包），无需手动登记。

## 子流程

无独立子流程；本层为单一校验关注点。

## 字节契约键（legacy dict，供 `DEFAULT_RESULT` / `print_result` 同步）

```contract-keys
n_bq_empty
```

## 实现备注

## 实现（`script/blockquote_spacing.py`）
- `code = 'N'`，`order = 14`，`auto_fixable = True`，`fix_order = 11`，`fix_dict = {'n': ...}`。
