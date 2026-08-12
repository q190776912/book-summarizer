# A 层 — TRULY MISSING（missing_items）

> 本文件是 **A 层** 的唯一权威详情（SSOT）。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verify.md`](../verify.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。
> **注册机制**：本层脚本位于 `verify/layers/missing_items/script/missing_items.py`，由 `verify/script/register_all.py` 用 `importlib` 按裸名扫描 `verify/layers/*/script/` 自动发现并注册。`code = 'A'` 是稳定字母代号（被 SKILL.md 与 per-book 记忆广泛引用，**不可更改**）；新增层无需改 `register_all.py` / `VerifyManager` / CLI。

## 目的
提取到了但 `.md` 里完全没有的条目 → 必须补写。

## 步骤（语义与检查内容）
- **TRULY MISSING（阻断 FAIL）**：提取键在 `ctx.items` 但 `.md` 无对应 `**标签**` → 必须补写。
- **MENTIONED-ONLY（仅复核，不 FAIL）**：只在正文/交叉引用出现，不是独立条目。
- **EXTRA（仅供参考）**：在 `.md` 但提取未检出，通常是被正确过滤的交叉引用。

## 本阶段规则（阻断性 / 可修复）
- `truly_missing` 非空 → 阻断 FAIL；`mentioned_only`/`extra` 不阻断。
- `auto_fixable = False`（缺项只能 agent 补写，不能脚本修）。

## 出口条件
`truly_missing` 非空 → 整章 FAIL。

## 相关代码（`verify/layers/missing_items/script/missing_items.py`）
- `code = 'A'`，`order = 2`，`auto_fixable = False`。
- 数据源：`ctx.items` + `ctx.all_keys`/`ctx.entry_keys`（来自 EXTRACT 层）。
- ⚠️ `label_warns`（标签识别告警）由 **EXTRACT 层** 产出，本层不 emit；请勿在 A 的契约键中混入该键。

## 子流程
无独立子流程；依赖 EXTRACT 层填入的 `ctx.items` / `ctx.entry_keys`。

## 需 agent 手工修复（manual fix）
本层 `auto_fixable = False`（缺项只能 agent 补写，不能脚本修）。检测结果须对照源
PDF / 提取契约**手工补写或判定**。

- **触发门（report.py）**：`TRULY MISSING` → 整章 FAIL；`MENTIONED-ONLY` / `EXTRA` 仅复核，不阻断。
- **修复步骤**：
  1. 看 `TRULY MISSING` 列出的键（如 `定理3.2`），对照 `<book>/_extract/page_*.json` 源确认确实漏写。
  2. 回到 `第N章_*.md`，按本书编号体例补写该条目（题面 + 证明梗概/解答，忠于原文），并在 `manual_overrides_chN.json` 登记。
  3. 若确认是 OCR 误检（源里其实没有该条目）或合理的交叉引用，将其 token 加入 `verify_config.json` 的
`ignore` 字段（或 `--ignore` CLI），抑制误报，而非编造条目。
  4. 重跑 verify，确认 `TRULY MISSING` 清零。

修复后重跑 `verify_chapter.py --all`（或单章 `<ch> <start> <end> <md> <ext>`）确认上述门为空 / 转绿。

## 字节契约键
```contract-keys
truly_missing
mentioned_only
extra
```
