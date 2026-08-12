# G 层 — QUOTE CONTINUITY（+ G扩展 / EG 子检查）（blockquote_continuity）

> 本文件是 **G 层** 的唯一权威详情（SSOT）。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verify.md`](../verify.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。
> **注册机制**：本层脚本位于 `verify/layers/blockquote_continuity/script/blockquote_continuity.py`，由 `verify/script/register_all.py` 用 `importlib` 按裸名扫描 `verify/layers/*/script/` 自动发现并注册。`code = 'G'` 是稳定字母代号（被 SKILL.md 与 per-book 记忆广泛引用，**不可更改**）；新增层无需改 `register_all.py` / `VerifyManager` / CLI。

## 目的
引用块连续性：任何 `> **证明/例**` 块不得被裸空行切断；并覆盖嵌套块引用与例–证明空隙。

## 步骤（语义与检查内容）
- **QUOTE GAP（阻断 FAIL，可修）**：`> **证明/例**` 块激活态遇裸空行、且其后首个非空行仍是块内容 → 改为 `> `（空引用行）。
- **允许**作为「块间分隔」的裸空行：其后为 `> **证明/例**` / `---` / `## ` / 顶层 `**标签**`。
- **NESTED BQ（G扩展，阻断 FAIL，不修）**：`> > **证明/例**` 嵌套 → 必须展平为单层 `>`。
- **EXAMPLE-PROOF GAP（EG，阻断 FAIL，不修）**：`> **例**` 陈述与 `> **证明**` 间裸空行/裸 `$$`，或同行的「例+证明」→ 须拆成连续 `>` 块。
- 例/Example 图片必须嵌入例的 blockquote 内，否则视为破坏连续性 → FAIL。
- 结构性校验，始终运行（不依赖图片层）。

## 本阶段规则（阻断性 / 可修复）
- `quote_gaps` / `nested_bq` / `ex_proof_gaps` 任一非空 → 阻断 FAIL。
- 仅 `quote_gaps` 可 `--fix`。

## 出口条件
`quote_gaps` / `nested_bq` / `ex_proof_gaps` 任一非空 → 整章 FAIL。

## 相关代码（`verify/layers/blockquote_continuity/script/blockquote_continuity.py`）
- `code = 'G'`，`order = 7`，`auto_fixable = True`，`fix_order = 5`，`fix_dict = {'g': ...}`（仅修 `quote_gaps`）。
- G扩展（nested）/ EG（ex_proof）只读、不修，保持现有「只修 quote_gaps、其余仍阻塞」行为。

## 子流程
无独立子脚本；G扩展（nested）/ EG（ex_proof）为本层脚本内的只读子检查。

## 字节契约键
```contract-keys
quote_gaps
nested_bq
ex_proof_gaps
```
