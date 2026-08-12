# blockquote-continuity 层（G · `blockquote_continuity`）

> **公用子流程（Sub-flow）。** 本文件是该校验层的**单一权威（SSOT）**，
> 同时作为可被其他消费者独立引用的校验子流程。
> 稳定标识符：`code="G"`（字母代号，被 `SKILL.md` 与 per-book 记忆广泛引用，不可更改）；
> 语义名：`blockquote-continuity`（`blockquote_continuity`）。

## 目的

## 一句话目的
引用块连续性：任何 `> **证明/例**` 块不得被裸空行切断；并覆盖嵌套块引用与例–证明空隙。
## 前置

- `<book>/_extract/verify_config.json` 完整合法。
- 依赖数据的层需 EXTRACT 层已填充 `ctx.items / entry_keys / all_keys`
（见 [data_provider](../data_provider/data_provider.md)）。

## 步骤

## 语义与检查内容
- **QUOTE GAP（阻断 FAIL，可修）**：`> **证明/例**` 块激活态遇裸空行、且其后首个非空行仍是块内容 → 改为 `> `（空引用行）。
- **允许**作为「块间分隔」的裸空行：其后为 `> **证明/例**` / `---` / `## ` / 顶层 `**标签**`。
- **NESTED BQ（G扩展，阻断 FAIL，不修）**：`> > **证明/例**` 嵌套 → 必须展平为单层 `>`。
- **EXAMPLE-PROOF GAP（EG，阻断 FAIL，不修）**：`> **例**` 陈述与 `> **证明**` 间裸空行/裸 `$$`，或同行的「例+证明」→ 须拆成连续 `>` 块。
- 例/Example 图片必须嵌入例的 blockquote 内，否则视为破坏连续性 → FAIL。
- 结构性校验，始终运行（不依赖图片层）。
## 本阶段规则

## 阻断性 / 可修复
- `quote_gaps` / `nested_bq` / `ex_proof_gaps` 任一非空 → 阻断 FAIL。
- 仅 `quote_gaps` 可 `--fix`。
## 出口

- 阻断层：对应字节契约键非空 → 该章 FAIL（exit 1）；`--fix` 流程按 `fix_order=5` 自动修复后复验。

## 相关代码

- 实现：`script/blockquote_continuity.py`
  - `code="G"`，`order=7`，`auto_fixable=True`，`fix_order=5`。
- 注册：经 `../../script/register_all.py` 自动发现（`pkgutil` 扫描 `..` 子包），无需手动登记。

## 子流程

含 G扩展（嵌套块引用）/ EG（例–证明空隙）两个子检查，归属本层 `code="G"`，不单独成层。

## 字节契约键（legacy dict，供 `DEFAULT_RESULT` / `print_result` 同步）

```contract-keys
quote_gaps
nested_bq
ex_proof_gaps
```

## 实现备注

## 实现（`script/blockquote_continuity.py`）
- `code = 'G'`，`order = 7`，`auto_fixable = True`，`fix_order = 5`，`fix_dict = {'g': ...}`（仅修 `quote_gaps`）。
- G扩展（nested）/ EG（ex_proof）只读、不修，保持现有「只修 quote_gaps、其余仍阻塞」行为。
