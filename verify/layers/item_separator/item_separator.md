# item-separator 层（I · `item_separator`）

> **公用子流程（Sub-flow）。** 本文件是该校验层的**单一权威（SSOT）**，
> 同时作为可被其他消费者独立引用的校验子流程。
> 稳定标识符：`code="I"`（字母代号，被 `SKILL.md` 与 per-book 记忆广泛引用，不可更改）；
> 语义名：`item-separator`（`item_separator`）。

## 目的

## 一句话目的
独立条目之间必须有 `---` 分隔线。
## 前置

- `<book>/_extract/verify_config.json` 完整合法。
- 依赖数据的层需 EXTRACT 层已填充 `ctx.items / entry_keys / all_keys`
（见 [data_provider](../data_provider/data_provider.md)）。

## 步骤

## 语义与检查内容
- **MISSING SEPARATOR（阻断 FAIL，可修）**：两个相邻条目行（`**定义N.N**`/`> **例N**` 等）之间无 `---`、且无节标题自然分隔 → 插入 `---`（前后空行）。
- 定理/定义与其**证明**之间**不应有 `---`**（证明是条目内部附属块，非独立条目）——I 层天然豁免，不报；由人工复核（Step 4 规则 #13）。
- 跳过分隔 >100 行的条目对（通常跨整个节）。
- `../../../flows/write-source/format/script/format/fmt_proofs.py` 可自动补齐缺失 `---`（幂等）。
## 本阶段规则

## 阻断性 / 可修复
- `i_sep_gaps` 非空 → 阻断 FAIL。
- 可 `--fix`。
## 出口

- 阻断层：对应字节契约键非空 → 该章 FAIL（exit 1）；`--fix` 流程按 `fix_order=6` 自动修复后复验。

## 相关代码

- 实现：`script/item_separator.py`
  - `code="I"`，`order=9`，`auto_fixable=True`，`fix_order=6`。
- 注册：经 `../../script/register_all.py` 自动发现（`pkgutil` 扫描 `..` 子包），无需手动登记。

## 子流程

无独立子流程；本层为单一校验关注点。

## 字节契约键（legacy dict，供 `DEFAULT_RESULT` / `print_result` 同步）

```contract-keys
i_sep_gaps
```

## 实现备注

## 实现（`script/item_separator.py`）
- `code = 'I'`，`order = 9`，`auto_fixable = True`，`fix_order = 6`，`fix_dict = {'i': ...}`。
- 与 G 家族互补：G 查块内连续，I 查独立条目间 `---`。
