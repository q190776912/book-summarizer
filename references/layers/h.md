# H 层 — STRUCTURAL LABEL IN BQ（+ H扩展：陈述进块引用）

> 本文件是 **H 层** 的唯一权威详情。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verification.md`](../verification.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。

## 一句话目的
结构标签（定义/定理/引理/…）不得被 `>` 块引用吞掉；条目陈述区的枚举/公式也不得裹进 `>`。

## 语义与检查内容
- **STRUCTURAL BQ（阻断 FAIL，可修）**：`> **<结构性标签>**` → 必须把标签移到顶层，证明另起 `> **证明**` 块。
- **STATEMENT-IN-BLOCKQUOTE（H扩展，阻断 FAIL，可修）**：条目陈述区内 `>` 包裹的 `（N）`/`**(N)**`/`$$`/`- （a）` → 解包顶层；示例块整体（含内部 `**(N)**`）合法保留在 `>` 内。
- 判定边界：陈述区 = `[标题行+1, 首个合法 `>` 块起点)`。
- 与 G 家族互补：G 保块内连续，H 保结构标签/陈述不被吞。

## 阻断性 / 可修复
- `h_structural_bq` / `h_stmt_bq` / `h_ul_bq` / `h_mbq` 任一非空 → 阻断 FAIL。
- H 全部可 `--fix`。

## 字节契约键（legacy dict，供 `DEFAULT_RESULT` / `print_result` 同步）
```contract-keys
h_structural_bq
h_stmt_bq
h_ul_bq
h_mbq
```

## 实现（`verify/layers/h_layer.py`）
- `code = 'H'`，`order = 8`，`auto_fixable = True`，`fix_order = 1`。
- `fix()` 内部子 fix 顺序钉死 `h → h_stmt → h_ul → h_mbq`；`fix_dict = {'h':..,'h_stmt':..,'h_ul':..,'h_mbq':..}`（与旧 `fix_all_layers` 键序一致）。
- H 的 3 个扩展（stmt-in-bq / unlabeled-bq / missing-bq）仍归属 `code='H'` 单层的 4 个子检查/子 fix。
