# O 层 — SUBITEM GAP（subitem_continuity）

> 本文件是 **O 层** 的唯一权威详情（SSOT）。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verify.md`](../verify.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。
> **注册机制**：本层脚本位于 `verify/subitem_continuity/script/subitem_continuity.py`，由 `verify/script/register_all.py` 用 `importlib` 按裸名扫描 `verify/*/script/` 自动发现并注册。`code = 'O'` 是稳定字母代号（被 SKILL.md 与 per-book 记忆广泛引用，**不可更改**）；新增层无需改 `register_all.py` / `VerifyManager` / CLI。

## 目的
编号子项序列（`(1)(2)(3)` / `(a)(b)(c)` / `(i)(ii)(iii)`）缺口检查。

## 步骤（语义与检查内容）
- 仅当块内序号项 ≥3 才检测（避免把交叉引用误判为序列）。
- **HEAD/INTERNAL gap（阻断 FAIL）**：序列起始 >1 或 min–max 间缺号 → 视为真实遗漏，须补回（`x` 行，`problems += 1`）。
- **TAIL gap（仅告警）**：OCR 交叉引用显示更大编号（如 md 最大 `(3)`、OCR 出现 `(5)`）→ 打印 `~` 行提示复核，不阻断。
- 与 J 层互补：O 管「编号子项是否连续」，J 管「块内分隔线」。

## 本阶段规则（阻断性 / 可修复）
- `o_subitem_gaps` 中以 `x` 开头的条目 → 阻断 FAIL；`~` 开头仅告警。
- **不可 `--fix`**，须手动补项或确认。

## 出口条件
`o_subitem_gaps` 中含 `x` 行 → 整章 FAIL；`~` 行仅 WARN。

## 相关代码（`verify/subitem_continuity/script/subitem_continuity.py`）
- `code = 'O'`，`order = 15`，`auto_fixable = False`。

## 子流程
无独立子脚本。

## 需 agent 手工修复（manual fix）
本层 `auto_fixable = False`。带括号子编号（如 `(1)(2)`）缺号 = 子项遗漏，须补写，脚本不编。

- **触发门（report.py）**：`O-LAYER SUBITEM GAPS`（`x` 行）→ 阻断 FAIL；
`O-LAYER SUBITEM TAIL`（`~` 行）→ 仅告警。
- **修复步骤**：
  1. 看 `O-LAYER SUBITEM GAPS` 列出的 `x` 行（如父项 `(3)` 缺失）。
  2. 回源 PDF 确认子项确实漏写；补写该编号子项（忠于原文），并在 `manual_overrides` 登记。
  3. `O-LAYER SUBITEM TAIL`（`~` 行）仅 WARN——OCR 显示更大编号时人工核对是否真漏尾部。
  4. 重跑 verify，确认 `O-LAYER SUBITEM GAPS` 中无 `x` 行。

修复后重跑 `verify_chapter.py --all`（或单章 `<ch> <start> <end> <md> <ext>`）确认上述门为空 / 转绿。

## 字节契约键
```contract-keys
o_subitem_gaps
```
