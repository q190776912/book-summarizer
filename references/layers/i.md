# I 层 — MISSING SEPARATOR（+ 定理/证明间无 `---`）

> 本文件是 **I 层** 的唯一权威详情。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verification.md`](../verification.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。

## 一句话目的
独立条目之间必须有 `---` 分隔线。

## 语义与检查内容
- **MISSING SEPARATOR（阻断 FAIL，可修）**：两个相邻条目行（`**定义N.N**`/`> **例N**` 等）之间无 `---`、且无节标题自然分隔 → 插入 `---`（前后空行）。
- 定理/定义与其**证明**之间**不应有 `---`**（证明是条目内部附属块，非独立条目）——I 层天然豁免，不报；由人工复核（Step 4 规则 #13）。
- 跳过分隔 >100 行的条目对（通常跨整个节）。
- `format/fmt_proofs.py` 可自动补齐缺失 `---`（幂等）。

## 阻断性 / 可修复
- `i_sep_gaps` 非空 → 阻断 FAIL。
- 可 `--fix`。

## 字节契约键（legacy dict，供 `DEFAULT_RESULT` / `print_result` 同步）
```contract-keys
i_sep_gaps
```

## 实现（`verify/layers/i_layer.py`）
- `code = 'I'`，`order = 9`，`auto_fixable = True`，`fix_order = 6`，`fix_dict = {'i': ...}`。
- 与 G 家族互补：G 查块内连续，I 查独立条目间 `---`。
