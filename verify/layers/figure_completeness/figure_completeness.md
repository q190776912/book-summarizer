# E 层 — FIGURE COMPLETENESS（figure_completeness）

> 本文件是 **E 层** 的唯一权威详情（SSOT）。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verify.md`](../verify.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。
> **注册机制**：本层脚本位于 `verify/layers/figure_completeness/script/figure_completeness.py`，由 `verify/script/register_all.py` 用 `importlib` 按裸名扫描 `verify/layers/*/script/` 自动发现并注册。`code = 'E'` 是稳定字母代号（被 SKILL.md 与 per-book 记忆广泛引用，**不可更改**）；新增层无需改 `register_all.py` / `VerifyManager` / CLI。

## 目的
图完整性：OCR 引用了图注但裁剪图缺失 → 可能漏检。

## 步骤（语义与检查内容）
- 仅当 `_extract/figure_index.json` 存在且含本章 `chapter` 条目时运行。
- **MISSING FIGURE（阻断 FAIL）**：章内 OCR 引用了「图 X.X.X」但 `figure_index.json` 无对应 `chapter==N, label==X.X.X` → 重跑 `extract_figures.py`/`assign_figures.py` 刷新或手动补图。
- **EXTRA（仅 WARN）**：裁剪图 `label` 在本章 OCR 找不到对应图注，疑似误配对。
- 无 `figure_index.json`（未跑图片提取）的章节自动 SKIP，绝不阻断。
- 注入 `fig_skipped`（= `e_layer is None` 完整语义：文件缺失 **或** 本章无图条目，两种情况都 SKIP）。

## 本阶段规则（阻断性 / 可修复）
- 有图时 `fig_missing` 非空 → 阻断 FAIL。
- `auto_fixable = False`。

## 出口条件
有图且 `fig_missing` 非空 → 整章 FAIL；`fig_extra` / `fig_skipped` 仅 WARN（不阻断）。

## 相关代码（`verify/layers/figure_completeness/script/figure_completeness.py`）
- `code = 'E'`，`order = 5`，`auto_fixable = False`。
- 底层返回 None 时必须 emit `fig_missing: []` / `fig_extra: []`（双保险，防 `e_layer['missing'] if e_layer else []` 路径崩）。
- `fig_skipped` 由 E 的 `metadata['skipped']` 携带，管理器据此注入（禁止窄化为 `ctx.figure_index is None`）。

## 子流程
无独立子脚本；依赖图片抽取产出的 `_extract/figure_index.json`。

## 需 agent 手工修复（manual fix）
本层 `auto_fixable = False`。图缺失意味着 OCR 引用了图但裁剪/索引缺失，须重跑图片提取或补图，
脚本不臆造图。

- **触发门（report.py）**：`E-LAYER FIGURE COMPLETENESS MISSING` → 整章 FAIL；
`E-LAYER FIGURE EXTRA` → 仅 WARN（无 `figure_index.json` 的章节自动 SKIP，绝不阻断）。
- **修复步骤**：
  1. 看 `E-LAYER FIGURE COMPLETENESS MISSING` 列出的图号（如 `图3.2.1`）。
  2. 确认 `<book>/_extract/figure_index.json` 是否真缺；若属图片提取未跑/过期，重跑
`extract_figures.py` / `assign_figures.py` 刷新索引。
  3. 若图确实存在但索引未含，手工补 `figure_index.json`（或 `figure_embed_overrides.json`）；
若确为 OCR 幻影引用，加 `ignore_figure` 抑制。
  4. `E-LAYER FIGURE EXTRA` 仅 WARN，核对裁剪图 label 配对即可。
  5. 重跑 verify，确认 `E-LAYER FIGURE COMPLETENESS MISSING` 清零。

修复后重跑 `verify_chapter.py --all`（或单章 `<ch> <start> <end> <md> <ext>`）确认上述门为空 / 转绿。

## 字节契约键
```contract-keys
fig_missing
fig_extra
fig_skipped
```
