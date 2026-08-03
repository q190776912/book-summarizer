# K 层 — PROOF-LIST BLANK

> 本文件是 **K 层** 的唯一权威详情。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verification.md`](../verification.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。

## 一句话目的
编号列表后、证明块前需有空行。

## 语义与检查内容
- **强制**：定理/定义的陈述含 4-空格缩进编号列表（`    N.`），且其后紧接 `> **证明**`/`> **证明思路**` 块引用时，列表末项与证明块之间**必须有一空行**。否则证明块渲染时视觉对齐编号项而非定理外层。可 `--fix` 自动插入空行。

## 阻断性 / 可修复
- `k_proof_list` 非空 → 阻断 FAIL。
- 可 `--fix`。

## 字节契约键（legacy dict，供 `DEFAULT_RESULT` / `print_result` 同步）
```contract-keys
k_proof_list
```

## 实现（`verify/layers/k_layer.py`）
- `code = 'K'`，`order = 11`，`auto_fixable = True`，`fix_order = 8`，`fix_dict = {'k': ...}`。
