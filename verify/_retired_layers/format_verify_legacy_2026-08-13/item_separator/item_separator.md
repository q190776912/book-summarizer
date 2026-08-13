# I 层 — MISSING SEPARATOR（+ 定理/证明间无 `---`）（item_separator）

> 本文件是 **I 层** 的唯一权威详情（SSOT）。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verify.md`](../verify.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。
> **注册机制**：本层脚本位于 `verify/layers/item_separator/script/item_separator.py`，由 `verify/script/register_all.py` 用 `importlib` 按裸名扫描 `verify/layers/*/script/` 自动发现并注册。`code = 'I'` 是稳定字母代号（被 SKILL.md 与 per-book 记忆广泛引用，**不可更改**）；新增层无需改 `register_all.py` / `VerifyManager` / CLI。

## 目的
独立条目之间必须有 `---` 分隔线。

## 步骤（语义与检查内容）
- **MISSING SEPARATOR（阻断 FAIL，可修）**：两个相邻条目行（`**定义N.N**`/`> **例N**` 等）之间无 `---`、且无节标题自然分隔 → 插入 `---`（前后空行）。
- 定理/定义与其**证明**之间**不应有 `---`**（证明是条目内部附属块，非独立条目）——I 层天然豁免，不报；由人工复核（Step 4 规则 #13）。
- 跳过分隔 >100 行的条目对（通常跨整个节）。
- `flows/write-source/format/script/format/fmt_proofs.py` 可自动补齐缺失 `---`（幂等）。

## 本阶段规则（阻断性 / 可修复）
- `i_sep_gaps` 非空 → 阻断 FAIL。
- 可 `--fix`。

## 出口条件
`i_sep_gaps` 非空 → 整章 FAIL。

## 相关代码（`verify/layers/item_separator/script/item_separator.py`）
- `code = 'I'`，`order = 9`，`auto_fixable = True`，`fix_order = 6`，`fix_dict = {'i': ...}`。
- 与 G 家族互补：G 查块内连续，I 查独立条目间 `---`。

## 子流程
无独立子脚本；缺失 `---` 的自动补齐亦可经 `flows/write-source/format/script/format/fmt_proofs.py` 完成（幂等）。

## 字节契约键
```contract-keys
i_sep_gaps
```
