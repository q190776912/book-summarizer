# intra-item-dash 层（J · `intra_item_dash`）

> **公用子流程（Sub-flow）。** 本文件是该校验层的**单一权威（SSOT）**，
> 同时作为可被其他消费者独立引用的校验子流程。
> 稳定标识符：`code="J"`（字母代号，被 `SKILL.md` 与 per-book 记忆广泛引用，不可更改）；
> 语义名：`intra-item-dash`（`intra_item_dash`）。

## 目的

## 一句话目的
条目块（标题 → 全部子点）内部不得出现 `---`。
## 触发

由 `verify` 总流程（见 [`../../verify.md`](../../verify.md) 与注册表 [`..`](.)）
按 `order` 自动调度；亦可被其他消费者（如 `../../../flows/verify-source`、`../../../flows/derive-translate`
或外部 skill）单独引用本子流程，针对单章 / 单文件运行该校验层。

## 前置

- `<book>/_extract/verify_config.json` 完整合法（config_setting 流程 规则1）。
- 依赖数据的层需 EXTRACT 层已填充 `ctx.items / entry_keys / all_keys`
（见 [data_provider](../data_provider/data_provider.md)）。

## 步骤

## 语义与检查内容
- **ITEM-HEADER DASH（阻断 FAIL，可修）**：顶层条目块（标题行到其全部 `**(N)**` 子点）内部出现 `---` → 删除。
- 覆盖两种：标题↔首个子点之间、子点↔子点之间；`---` 上方即使是子点接续文本/`$$` 仍属块内。
- 实现用 `in_item` 跨行追踪：`**LABEL**`/`**(N)**` 置 True，`## `/`>` 行置 False；顶层 `---` 且 `in_item` 且其后首个非空非块引用行是 `**(N)**` → 违规。
- 与 I 层互补：`---` 只用于**不同**顶层条目之间。
## 本阶段规则

## 阻断性 / 可修复
- `j_header_dash` 非空 → 阻断 FAIL（计入 `problems`，非零即 FAIL）。
- 可 `--fix`。
## 出口

- 阻断层：对应字节契约键非空 → 该章 FAIL（exit 1）；`--fix` 流程按 `fix_order=7` 自动修复后复验。

## 相关代码

- 实现：`script/intra_item_dash.py`
  - `code="J"`，`order=10`，`auto_fixable=True`，`fix_order=7`。
- 注册：经 `../../script/register_all.py` 自动发现（`pkgutil` 扫描 `..` 子包），无需手动登记。

## 子流程

无独立子流程；本层为单一校验关注点。

## 字节契约键（legacy dict，供 `DEFAULT_RESULT` / `print_result` 同步）

```contract-keys
j_header_dash
```

## 实现备注

## 实现（`script/intra_item_dash.py`）
- `code = 'J'`，`order = 10`，`auto_fixable = True`，`fix_order = 7`，`fix_dict = {'j': ...}`。
- `--fix` 删条目块内所有 `---` 并合并其后单个空行（幂等）。
