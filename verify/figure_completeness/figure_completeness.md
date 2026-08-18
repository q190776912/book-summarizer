# E 层 — FIGURE（figure_completeness，图完整性 + 图有效性）

> 本文件是 **E 层（统一 figure 层）** 的唯一权威详情（SSOT）。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verify.md`](../verify.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。
> **注册机制**：本层脚本位于 `verify/figure_completeness/script/figure_completeness.py`，由 `verify/script/register_all.py` 用 `importlib` 按裸名扫描 `verify/*/script/` 自动发现并注册。`code = 'E'` 是稳定字母代号（被 SKILL.md 与 per-book 记忆广泛引用，**不可更改**）；新增层无需改 `register_all.py` / `VerifyManager` / CLI。

## 目的
图完整性（覆盖度）+ 图有效性（文件可解码性）：OCR 引用了图注但裁剪图缺失 → 可能漏检；以及裁剪图文件缺失 / 损坏 / 过小 / 近空白 → 嵌入后无图或误检。

## 步骤（语义与检查内容）
1. 仅当 `_extract/figure_index.json` 存在且含本章 `chapter` 条目时运行；否则 SKIP（绝不阻断）。无 `figure_index.json`（未跑图片提取）的章节亦自动 SKIP，绝不阻断。
2. 载入 `figure_index.json` **一次**，按 `chapter` 过滤出本章条目（无 `chapter` 字段的全书文件则不过滤）；随后做三类检查（完整性 / 有效性 / 归属），具体判定见下方「规则」。
3. 归属检查（ATTRIBUTION，覆盖「图悬在块外」盲区）：把 md 切成逻辑块、解析每条 `<img>` 的 `alt` 里的 item 指针、判定该图是否落在引用它的 item 块内。背景与判定逻辑见下方「规则 · 归属」。
4. 注入 `fig_skipped`（= `result is None` 完整语义：文件缺失 **或** 本章无图条目，两种情况都 SKIP）。

## 规则
### 完整性 COMPLETENESS（原 E）
- 用 `fig_cap_re`（每本书 `ordinal` 的 Figure 组 `name` 前缀、段数取该组 `type` 经 `ORDINAL_DEPTH` 派生的 `depth`）扫 `page_*.json` 的 OCR 文本，抽本章图注号集合；与索引 `extracted` 求差。
- **MISSING FIGURE（阻断 FAIL）**：章内 OCR 引用了「图 X.X.X」但 `figure_index.json` 无对应 `chapter==N, label==X.X.X` → 重跑 `extract_figures.py`/`assign_figures.py` 刷新或手动补图。
- **EXTRA（仅 WARN）**：裁剪图 `label` 在本章 OCR 找不到对应图注，疑似误配对。

### 有效性 VALIDITY（原 F）
- 对本章每条 index 条目，用 `np.fromfile`+`cv2.imdecode`（绕开 Windows 中文路径下 `cv2.imread` 静默失败）打开 `<ext>/<file>`。
- **INVALID（阻断 FAIL）**：缺失文件 / 无法解码 / 单边 <20px。
- **SUSPICIOUS（仅 WARN）**：近空白（灰度方差 <50，疑似误检文字块）。

### 归属 ATTRIBUTION（新增）
- 背景：原 E/F/H 层都不检查「图是否落在引用它的 item 块内」——这是 verifier 的覆盖盲区（Kreyszig §1.5-9 的图曾被嵌入脚本 `find_after` 保守地推出 `>` 块、悬在节末，长期无校验抓出）。由 `check_figure_attribution(md_file)` 实现。
- 逻辑块切分：`blockquote`（`>` 行）、`item_top`（顶层 `**N.M-K**`）、`section`（`## `）、`floating`（裸 `<div>`/`<img>` 无 `>` 前缀）。
- item 指针解析：`alt` 里的 `_ALT_ITEM_RE`（`Example|Theorem|Def.|Proof of Theorem … N.M-K`，大小写不敏感）。
- **fig_misattributed（仅 WARN，不阻断）**——嵌入脚本历史保守策略可能合法地把部分图放在块外，但盲区必须暴露而非隐藏：
  - `floating` 图且最近归属 item 是 `blockquote` → 报（应移入该 `>` 块）。
  - `blockquote` 块内图但其最近归属 item 与块标题 `ref` 不一致 → 报。
  - `item_top` 块内图且 `alt` 指向的 item 与块 `ref` 不一致 → 报。
- 正例基准：§1.3-4（fig7，在 `**1.3-4 Theorem**` 后的 `>` 块内）、§1.6-2（fig11，同）、§1.5-9（fig9/fig10，修复后已收进 `> **1.5-9 Example**` 块内）→ 均不报。

### 阻断性 / 可修复
- 有图时 `fig_missing` 或 `fig_invalid` 非空 → 阻断 FAIL。
- `fig_extra` / `fig_invalid_warn` / `fig_misattributed` 仅 WARN（不阻断）。
- `auto_fixable = False`。

## 相关代码（`verify/figure_completeness/script/figure_completeness.py`）
- `code = 'E'`，`order = 5`，`auto_fixable = False`。
- 底层返回 None 时必须 emit `fig_missing: []` / `fig_extra: []` / `fig_invalid: []` / `fig_invalid_warn: []`（双保险，防 `result['missing'] if result else []` 路径崩）。
- `fig_skipped` 由 E 的 `metadata['skipped']` 携带，管理器据此注入（禁止窄化为 `ctx.figure_index is None`）。
- 本层单次载入 `figure_index.json` 并单次按章过滤（原 E、F 各自独立载入 / 过滤）。

## 子流程
无独立子脚本；依赖图片抽取产出的 `_extract/figure_index.json`。

## 需 agent 手工修复（manual fix）
本层 `auto_fixable = False`。图缺失意味着 OCR 引用了图但裁剪/索引缺失，或图文件缺失/损坏/过小，须重跑图片提取或补图，脚本不臆造图、不修二进制。

- **触发门（report.py）**：
  - `E-LAYER FIGURE COMPLETENESS MISSING` → 整章 FAIL；`E-LAYER FIGURE EXTRA` → 仅 WARN（无 `figure_index.json` 的章节自动 SKIP，绝不阻断）。
  - `E-LAYER FIGURE VALIDITY ERRORS` → 整章 FAIL；`E-LAYER FIGURE SUSPICIOUS` → 仅 WARN。
- **修复步骤**：
  1. 看 `E-LAYER FIGURE COMPLETENESS MISSING` 列出的图号（如 `图3.2.1`）。
  2. 确认 `<book>/_extract/figure_index.json` 是否真缺；若属图片提取未跑/过期，重跑
  `extract_figures.py` / `assign_figures.py` 刷新索引。
  3. 若图确实存在但索引未含，手工补 `figure_index.json`（或 `figure_embed_overrides.json`）；
  若确为 OCR 幻影引用，加 `ignore_figure` 抑制。
  4. 看 `E-LAYER FIGURE VALIDITY ERRORS` 列出的图（缺失文件 / 无法解码 / 单边 <20px）：到 `<book>/_extract/figure/` 确认文件存在且可解码；缺失则重跑图片提取生成，损坏则在源 PDF 重新裁剪。
  5. `E-LAYER FIGURE EXTRA` / `E-LAYER FIGURE SUSPICIOUS` 仅 WARN，核对裁剪图 label 配对 / 近空白疑似文字块，必要时加 `ignore_figure`。
  6. 重跑 verify，确认 `E-LAYER FIGURE COMPLETENESS MISSING` 与 `E-LAYER FIGURE VALIDITY ERRORS` 清零。

修复后重跑 `verify_chapter.py --all`（或单章 `<ch> <start> <end> <md> <ext>`）确认上述门为空 / 转绿。

## 字节契约键
```contract-keys
fig_missing
fig_extra
fig_invalid
fig_invalid_warn
fig_misattributed
fig_skipped
```
