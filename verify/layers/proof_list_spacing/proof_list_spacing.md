# proof-list-spacing 层（K · `proof_list_spacing`）

> **公用子流程（Sub-flow）。** 本文件是该校验层的**单一权威（SSOT）**，
> 同时作为可被其他消费者独立引用的校验子流程。
> 稳定标识符：`code="K"`（字母代号，被 `SKILL.md` 与 per-book 记忆广泛引用，不可更改）；
> 语义名：`proof-list-spacing`（`proof_list_spacing`）。

## 目的

## 一句话目的
编号列表后、证明块前需有空行。
## 前置

- `<book>/_extract/verify_config.json` 完整合法。
- 依赖数据的层需 EXTRACT 层已填充 `ctx.items / entry_keys / all_keys`
（见 [data_provider](../data_provider/data_provider.md)）。

## 步骤

## 语义与检查内容
- **强制**：定理/定义的陈述含 4-空格缩进编号列表（`    N.`），且其后紧接 `> **证明**`/`> **证明思路**` 块引用时，列表末项与证明块之间**必须有一空行**。否则证明块渲染时视觉对齐编号项而非定理外层。可 `--fix` 自动插入空行。
## 本阶段规则

## 阻断性 / 可修复
- `k_proof_list` 非空 → 阻断 FAIL。
- 可 `--fix`。
## 出口

- 阻断层：对应字节契约键非空 → 该章 FAIL（exit 1）；`--fix` 流程按 `fix_order=8` 自动修复后复验。

## 相关代码

- 实现：`script/proof_list_spacing.py`
  - `code="K"`，`order=11`，`auto_fixable=True`，`fix_order=8`。
- 注册：经 `../../script/register_all.py` 自动发现（`pkgutil` 扫描 `..` 子包），无需手动登记。

## 子流程

无独立子流程；本层为单一校验关注点。

## 字节契约键（legacy dict，供 `DEFAULT_RESULT` / `print_result` 同步）

```contract-keys
k_proof_list
```

## 实现备注

## 实现（`script/proof_list_spacing.py`）
- `code = 'K'`，`order = 11`，`auto_fixable = True`，`fix_order = 8`，`fix_dict = {'k': ...}`。
