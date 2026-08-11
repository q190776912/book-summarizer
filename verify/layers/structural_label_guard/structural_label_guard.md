# structural-label-guard 层（H · `structural_label_guard`）

> **公用子流程（Sub-flow）。** 本文件是该校验层的**单一权威（SSOT）**，
> 同时作为可被其他消费者独立引用的校验子流程。
> 稳定标识符：`code="H"`（字母代号，被 `SKILL.md` 与 per-book 记忆广泛引用，不可更改）；
> 语义名：`structural-label-guard`（`structural_label_guard`）。

## 目的

## 一句话目的
结构标签（定义/定理/引理/…）不得被 `>` 块引用吞掉；条目陈述区的枚举/公式也不得裹进 `>`。
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
- **STRUCTURAL BQ（阻断 FAIL，可修）**：`> **<结构性标签>**` → 必须把标签移到顶层，证明另起 `> **证明**` 块。
- **STATEMENT-IN-BLOCKQUOTE（H扩展，阻断 FAIL，可修）**：条目陈述区内 `>` 包裹的 `（N）`/`**(N)**`/`$$`/`- （a）` → 解包顶层；示例块整体（含内部 `**(N)**`）合法保留在 `>` 内。
- 判定边界：陈述区 = `[标题行+1, 首个合法 `>` 块起点)`。
- 与 G 家族互补：G 保块内连续，H 保结构标签/陈述不被吞。
## 本阶段规则

## 阻断性 / 可修复
- `h_structural_bq` / `h_stmt_bq` / `h_ul_bq` / `h_mbq` 任一非空 → 阻断 FAIL。
- H 全部可 `--fix`。
## 出口

- 阻断层：对应字节契约键非空 → 该章 FAIL（exit 1）；`--fix` 流程按 `fix_order=1` 自动修复后复验。

## 相关代码

- 实现：`script/structural_label_guard.py`
  - `code="H"`，`order=8`，`auto_fixable=True`，`fix_order=1`。
- 注册：经 `../../script/register_all.py` 自动发现（`pkgutil` 扫描 `..` 子包），无需手动登记。

## 子流程

含 3 个扩展（stmt-in-bq / unlabeled-bq / missing-bq），均归属 `code="H"` 单层。

## 字节契约键（legacy dict，供 `DEFAULT_RESULT` / `print_result` 同步）

```contract-keys
h_structural_bq
h_stmt_bq
h_ul_bq
h_mbq
```

## 实现备注

## 实现（`script/structural_label_guard.py`）
- `code = 'H'`，`order = 8`，`auto_fixable = True`，`fix_order = 1`。
- `fix()` 内部子 fix 顺序钉死 `h → h_stmt → h_ul → h_mbq`；`fix_dict = {'h':..,'h_stmt':..,'h_ul':..,'h_mbq':..}`（与旧 `fix_all_layers` 键序一致）。
- H 的 3 个扩展（stmt-in-bq / unlabeled-bq / missing-bq）仍归属 `code='H'` 单层的 4 个子检查/子 fix。
