# B 层 — BLOCKING

> 本文件是 **B 层** 的唯一权威详情。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verification.md`](../verification.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。

## 一句话目的
抽取边界/尾部自动复查发现的疑似漏写候选项 → 必须解决。

## 语义与检查内容
- **BLOCKING（阻断 FAIL）**：真实项则补写并在 `extract_items` 用 `--manual` 登记；确为 OCR 乱码/无法修复交叉引用则记入 `--ignore`。
- 在产出 `blocking` 后做 `ignored_hit` **第二段**：遍历 `blocking` 消息，若某条引用的键全部 ∈ `ignore_keys`，把这些 `bkeys` 并入 `ctx.ignored_hit` 并从 `blocking` 剔除（最终 `ignored_hit` 由 B 回写，覆盖 EXTRACT 的 stage1）。

## 阻断性 / 可修复
- `blocking` 非空 → 阻断 FAIL。

## 字节契约键（legacy dict，供 `DEFAULT_RESULT` / `print_result` 同步）
```contract-keys
blocking
warnings
ignored_hit
```

## 实现（`verify/layers/b_layer.py`）
- `code = 'B'`，`order = 3`，`auto_fixable = False`。
- 数据源：`ctx.extraction_blocking` / `ctx.extraction_warnings`（EXTRACT 阶段填）。
