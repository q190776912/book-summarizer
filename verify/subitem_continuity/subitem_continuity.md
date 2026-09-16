# O 层 — SUBITEM GAP（subitem_continuity）

> 本文件是 **O 层** 的唯一权威详情（SSOT）。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verify.md`](../verify.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。
> **注册机制**：本层脚本位于 `verify/subitem_continuity/script/subitem_continuity.py`，由 `verify/script/register_all.py` 用 `importlib` 按裸名扫描 `verify/*/script/` 自动发现并注册。`code = 'O'` 是稳定字母代号（被 SKILL.md 与 per-book 记忆广泛引用，**不可更改**）；新增层无需改 `register_all.py` / `VerifyManager` / CLI。

## 目的
编号子项序列（`(1)(2)(3)` / `(a)(b)(c)` / `(i)(ii)(iii)`）缺口检查。

## 步骤（语义与检查内容）
- 仅当块内序号项 ≥3 才检测（避免把交叉引用误判为序列）。
- **异质块跳过（🔴 2026-09-16 修复）**：一个块内混有**两条不同序列**时判 `'mixed'` 并跳过，
  不产出任何缺口——判据是相邻（阅读顺序）编号**跳幅 > `_MAX_ORDINAL_JUMP`(20)**。
  - 背景（statistical-inference 3.33/3.34 实测）：教材常见「罗马任务段 + 字母选项段」
    同处一块，如 `(i)(ii)(iii)` 任务 + `(a)(b)(c)(d)` 族。而 `c`/`d` 恰好也是合法罗马
    字符（100/500），旧逻辑只要**多字符**标签（ii/iii）是合法罗马就把**整块**过
    `_roman_to_int`，得 `[1,2,3,100,500]` → 凭空算出 4..499 一串**幽灵号**。
  - 真缺号是「中间少几个」（跳幅小），把另一条序列的头接进来才会「跳到很远」，
    故跳幅阈值可安全区分二者；20 足够宽松，不吞正常 roman / numeric / alpha 序列。
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
