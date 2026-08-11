# subitem-continuity 层（O · `subitem_continuity`）

> **公用子流程（Sub-flow）。** 本文件是该校验层的**单一权威（SSOT）**，
> 同时作为可被其他消费者独立引用的校验子流程。
> 稳定标识符：`code="O"`（字母代号，被 `SKILL.md` 与 per-book 记忆广泛引用，不可更改）；
> 语义名：`subitem-continuity`（`subitem_continuity`）。

## 目的

## 一句话目的
编号子项序列（`(1)(2)(3)` / `(a)(b)(c)` / `(i)(ii)(iii)`）缺口检查。
## 触发

由 `verify` 总流程（见 [`../../verify.md`](../../verify.md) 与注册表 [`..`](.)）
按 `order` 自动调度；亦可被其他消费者（如 `../../../flows/verify-source`、`../../../flows/derive-translate`
或外部 skill）单独引用本子流程，针对单章 / 单文件运行该校验层。

## 前置

- `<book>/_extract/verify_config.json` 完整合法（config_setting 流程 规则1）。
- 依赖数据的层需 EXTRACT 层已填充 `ctx.items / entry_keys / all_keys`
（见 [data_provider](../data_provider/data_provider.md)）。

## 步骤

## 语义与检查内容
- 仅当块内序号项 ≥3 才检测（避免把交叉引用误判为序列）。
- **HEAD/INTERNAL gap（阻断 FAIL）**：序列起始 >1 或 min–max 间缺号 → 视为真实遗漏，须补回（`x` 行，`problems += 1`）。
- **TAIL gap（仅告警）**：OCR 交叉引用显示更大编号（如 md 最大 `(3)`、OCR 出现 `(5)`）→ 打印 `~` 行提示复核，不阻断。
- 与 J 层互补：O 管「编号子项是否连续」，J 管「块内分隔线」。
## 本阶段规则

## 阻断性 / 可修复
- `o_subitem_gaps` 中以 `x` 开头的条目 → 阻断 FAIL；`~` 开头仅告警。
- **不可 `--fix`**，须手动补项或确认。
## 出口

- 部分阻断：以 `x` 开头的子项缺口 → 阻断 FAIL；以 `~` 开头的尾部缺口仅 WARN，不阻断。不可 `--fix`。

## 相关代码

- 实现：`script/subitem_continuity.py`
  - `code="O"`，`order=15`，`auto_fixable=False`。
- 注册：经 `../../script/register_all.py` 自动发现（`pkgutil` 扫描 `..` 子包），无需手动登记。

## 子流程

无独立子流程；本层为单一校验关注点。

## 字节契约键（legacy dict，供 `DEFAULT_RESULT` / `print_result` 同步）

```contract-keys
o_subitem_gaps
```

## 实现备注

## 实现（`script/subitem_continuity.py`）
- `code = 'O'`，`order = 15`，`auto_fixable = False`。
