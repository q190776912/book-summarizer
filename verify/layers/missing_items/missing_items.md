# missing-items 层（A · `missing_items`）

> **公用子流程（Sub-flow）。** 本文件是该校验层的**单一权威（SSOT）**，
> 同时作为可被其他消费者独立引用的校验子流程。
> 稳定标识符：`code="A"`（字母代号，被 `SKILL.md` 与 per-book 记忆广泛引用，不可更改）；
> 语义名：`missing-items`（`missing_items`）。

## 目的

## 一句话目的
提取到了但 `.md` 里完全没有的条目 → 必须补写。
## 前置

- `<book>/_extract/verify_config.json` 完整合法。
- 依赖数据的层需 EXTRACT 层已填充 `ctx.items / entry_keys / all_keys`
（见 [data_provider](../data_provider/data_provider.md)）。

## 步骤

## 语义与检查内容
- **TRULY MISSING（阻断 FAIL）**：提取键在 `ctx.items` 但 `.md` 无对应 `**标签**` → 必须补写。
- **MENTIONED-ONLY（仅复核，不 FAIL）**：只在正文/交叉引用出现，不是独立条目。
- **EXTRA（仅供参考）**：在 `.md` 但提取未检出，通常是被正确过滤的交叉引用。
## 本阶段规则

## 阻断性 / 可修复
- `truly_missing` 非空 → 阻断 FAIL；`mentioned_only`/`extra` 不阻断。
## 出口

- 阻断层：对应字节契约键非空 → 该章 FAIL（exit 1）；不可 `--fix`，须回写作阶段修正。

## 相关代码

- 实现：`script/missing_items.py`
  - `code="A"`，`order=2`，`auto_fixable=False`。
- 注册：经 `../../script/register_all.py` 自动发现（`pkgutil` 扫描 `..` 子包），无需手动登记。

## 子流程

无独立子流程；本层为单一校验关注点。

## 字节契约键（legacy dict，供 `DEFAULT_RESULT` / `print_result` 同步）

```contract-keys
truly_missing
mentioned_only
extra
label_warns
```

## 实现备注

## 实现（`script/missing_items.py`）
- `code = 'A'`，`order = 2`，`auto_fixable = False`。
- 数据源：`ctx.items` + `ctx.all_keys`/`ctx.entry_keys`（来自 EXTRACT 层）。
- `label_warns`：标签识别告警（如标签词归一）。
