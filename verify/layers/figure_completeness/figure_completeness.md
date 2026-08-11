# figure-completeness 层（E · `figure_completeness`）

> **公用子流程（Sub-flow）。** 本文件是该校验层的**单一权威（SSOT）**，
> 同时作为可被其他消费者独立引用的校验子流程。
> 稳定标识符：`code="E"`（字母代号，被 `SKILL.md` 与 per-book 记忆广泛引用，不可更改）；
> 语义名：`figure-completeness`（`figure_completeness`）。

## 目的

## 一句话目的
图完整性：OCR 引用了图注但裁剪图缺失 → 可能漏检。
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
- 仅当 `_extract/figure_index.json` 存在且含本章 `chapter` 条目时运行。
- **MISSING FIGURE（阻断 FAIL）**：章内 OCR 引用了「图 X.X.X」但 `figure_index.json` 无对应 `chapter==N, label==X.X.X` → 重跑 `extract_figures.py`/`assign_figures.py` 刷新或手动补图。
- **EXTRA（仅 WARN）**：裁剪图 `label` 在本章 OCR 找不到对应图注，疑似误配对。
- 无 `figure_index.json`（未跑图片提取）的章节自动 SKIP，绝不阻断。
- 注入 `fig_skipped`（= `e_layer is None` 完整语义：文件缺失 **或** 本章无图条目，两种情况都 SKIP）。
## 本阶段规则

## 阻断性 / 可修复
- 有图时 `fig_missing` 非空 → 阻断 FAIL。
## 出口

- 阻断层：对应字节契约键非空 → 该章 FAIL（exit 1）；不可 `--fix`，须回写作阶段修正。

## 相关代码

- 实现：`script/figure_completeness.py`
  - `code="E"`，`order=5`，`auto_fixable=False`。
- 注册：经 `../../script/register_all.py` 自动发现（`pkgutil` 扫描 `..` 子包），无需手动登记。

## 子流程

无独立子流程；本层为单一校验关注点。

## 字节契约键（legacy dict，供 `DEFAULT_RESULT` / `print_result` 同步）

```contract-keys
fig_missing
fig_extra
fig_skipped
```

## 实现备注

## 实现（`script/figure_completeness.py`）
- `code = 'E'`，`order = 5`，`auto_fixable = False`。
- 底层返回 None 时必须 emit `fig_missing: []` / `fig_extra: []`（双保险，防 `e_layer['missing'] if e_layer else []` 路径崩）。
- `fig_skipped` 由 E 的 `metadata['skipped']` 携带，管理器据此注入（禁止窄化为 `ctx.figure_index is None`）。
