# separator-spacing 层（L · `separator_spacing`）

> **公用子流程（Sub-flow）。** 本文件是该校验层的**单一权威（SSOT）**，
> 同时作为可被其他消费者独立引用的校验子流程。
> 稳定标识符：`code="L"`（字母代号，被 `SKILL.md` 与 per-book 记忆广泛引用，不可更改）；
> 语义名：`separator-spacing`（`separator_spacing`）。

## 目的

## 一句话目的
`---` 分隔线上下需有空行。
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
- **强制**：每个 `---` 上方和下方都必须紧邻一空白行（`正文\n\n---\n\n正文`）。无空白行时 `---` 可能被误解为 setext 标题下划线或被渲染器吞没。可 `--fix` 自动补缺失空白行。
## 本阶段规则

## 阻断性 / 可修复
- `l_sep_blanks` 非空 → 阻断 FAIL。
- 可 `--fix`。
## 出口

- 阻断层：对应字节契约键非空 → 该章 FAIL（exit 1）；`--fix` 流程按 `fix_order=9` 自动修复后复验。

## 相关代码

- 实现：`script/separator_spacing.py`
  - `code="L"`，`order=12`，`auto_fixable=True`，`fix_order=9`。
- 注册：经 `../../script/register_all.py` 自动发现（`pkgutil` 扫描 `..` 子包），无需手动登记。

## 子流程

无独立子流程；本层为单一校验关注点。

## 字节契约键（legacy dict，供 `DEFAULT_RESULT` / `print_result` 同步）

```contract-keys
l_sep_blanks
```

## 实现备注

## 实现（`script/separator_spacing.py`）
- `code = 'L'`，`order = 12`，`auto_fixable = True`，`fix_order = 9`，`fix_dict = {'l': ...}`。
