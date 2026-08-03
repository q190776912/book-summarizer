# E 层 — FIGURE COMPLETENESS

> 本文件是 **E 层** 的唯一权威详情。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verification.md`](../verification.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。

## 一句话目的
图完整性：OCR 引用了图注但裁剪图缺失 → 可能漏检。

## 语义与检查内容
- 仅当 `_extract/figure_index.json` 存在且含本章 `chapter` 条目时运行。
- **MISSING FIGURE（阻断 FAIL）**：章内 OCR 引用了「图 X.X.X」但 `figure_index.json` 无对应 `chapter==N, label==X.X.X` → 重跑 `extract_figures.py`/`assign_figures.py` 刷新或手动补图。
- **EXTRA（仅 WARN）**：裁剪图 `label` 在本章 OCR 找不到对应图注，疑似误配对。
- 无 `figure_index.json`（未跑图片提取）的章节自动 SKIP，绝不阻断。
- 注入 `fig_skipped`（= `e_layer is None` 完整语义：文件缺失 **或** 本章无图条目，两种情况都 SKIP）。

## 阻断性 / 可修复
- 有图时 `fig_missing` 非空 → 阻断 FAIL。

## 字节契约键（legacy dict，供 `DEFAULT_RESULT` / `print_result` 同步）
```contract-keys
fig_missing
fig_extra
fig_skipped
```

## 实现（`verify/layers/e_layer.py`）
- `code = 'E'`，`order = 5`，`auto_fixable = False`。
- 底层返回 None 时必须 emit `fig_missing: []` / `fig_extra: []`（双保险，防 `e_layer['missing'] if e_layer else []` 路径崩）。
- `fig_skipped` 由 E 的 `metadata['skipped']` 携带，管理器据此注入（禁止窄化为 `ctx.figure_index is None`）。
