# C 层 — KATEX ERRORS（katex_validation）

> 本文件是 **C 层** 的唯一权威详情（SSOT）。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verify.md`](../verify.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。
> **注册机制**：本层脚本位于 `verify/layers/katex_validation/script/katex_validation.py`，由 `verify/script/register_all.py` 用 `importlib` 按裸名扫描 `verify/layers/*/script/` 自动发现并注册。`code = 'C'` 是稳定字母代号（被 SKILL.md 与 per-book 记忆广泛引用，**不可更改**）；新增层无需改 `register_all.py` / `VerifyManager` / CLI。

## 目的
运行 `flows/write-source/format/script/format/check_katex.py` 真实 KaTeX 渲染，抓出渲染失败。

## 步骤（语义与检查内容）
- 调用 `flows/write-source/format/script/format/check_katex.py`（内部 `katex_validate.js` 真实渲染），抓非法命令、括号不配对等真正语法错误。
- 具体禁忌清单（转义定界符 `$$`、缺空行、行内 `$` 未配对、不支持宏、嵌套块引用 `> > $$` 等）见 [`../../flows/write-source/format/ref/formatting.md`](../../flows/write-source/format/ref/formatting.md) 的 KaTeX 规则。
- `check_katex.py --fix` 可自动修正前几项（转义定界符、单行展示公式、缺空行、嵌套块引用展示公式）；其余需手动。

## 本阶段规则（阻断性 / 可修复）
- `katex_errors` 非空 → 阻断 FAIL。
- `auto_fixable = False`（KaTeX 修复由 `check_katex.py --fix` 单独做，不经 verify manager 的 `fix`）。

## 出口条件
`katex_errors` 非空 → 整章 FAIL。

## 相关代码（`verify/layers/katex_validation/script/katex_validation.py`）
- `code = 'C'`，`order = 4`，`auto_fixable = False`（KaTeX 修复由 `check_katex.py --fix` 单独做，不经 verify manager 的 `fix`）。
- 通过 `subprocess` 调 `flows/write-source/format/script/format/check_katex.py`。

## 子流程
无独立子脚本；委托 `flows/write-source/format/script/format/check_katex.py` 完成真实渲染。

## 需 agent 手工修复（manual fix）
本层 `auto_fixable = False`——KaTeX 渲染错误需**修正数学公式本身**，验证层只检测、不修复。
KaTeX 修复由 `check_katex.py --fix` 单独做，不经 verify manager 的 `fix`。

- **触发门（report.py）**：`C-LAYER KATEX ERRORS` → 整章 FAIL。
- **修复步骤**：
  1. 看 `C-LAYER KATEX ERRORS` 列出的行号与 KaTeX 报错（未闭合 `$`、非法命令、环境 `\begin{}`/`\end{}` 不匹配等）。
  2. 在 `第N章_*.md` 对应行修正 KaTeX 语法（补全 `$` 配对、替换不支持的命令、修正环境）。
  3. 可先用 `check_katex.py --fix` 自动修正可修复子集，剩余手工改。
  4. 重跑 verify（check_katex 也会在写入流程跑），确认 `C-LAYER KATEX ERRORS` 清零。

修复后重跑 `verify_chapter.py --all`（或单章 `<ch> <start> <end> <md> <ext>`）确认上述门为空 / 转绿。

## 字节契约键
```contract-keys
katex_errors
katex_lines
```
