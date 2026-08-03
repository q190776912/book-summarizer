# O 层 — SUBITEM GAP

> 本文件是 **O 层** 的唯一权威详情。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verification.md`](../verification.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。

## 一句话目的
编号子项序列（`(1)(2)(3)` / `(a)(b)(c)` / `(i)(ii)(iii)`）缺口检查。

## 语义与检查内容
- 仅当块内序号项 ≥3 才检测（避免把交叉引用误判为序列）。
- **HEAD/INTERNAL gap（阻断 FAIL）**：序列起始 >1 或 min–max 间缺号 → 视为真实遗漏，须补回（`x` 行，`problems += 1`）。
- **TAIL gap（仅告警）**：OCR 交叉引用显示更大编号（如 md 最大 `(3)`、OCR 出现 `(5)`）→ 打印 `~` 行提示复核，不阻断。
- 与 J 层互补：O 管「编号子项是否连续」，J 管「块内分隔线」。

## 阻断性 / 可修复
- `o_subitem_gaps` 中以 `x` 开头的条目 → 阻断 FAIL；`~` 开头仅告警。
- **不可 `--fix`**，须手动补项或确认。

## 字节契约键（legacy dict，供 `DEFAULT_RESULT` / `print_result` 同步）
```contract-keys
o_subitem_gaps
```

## 实现（`verify/layers/o_layer.py`）
- `code = 'O'`，`order = 15`，`auto_fixable = False`。
