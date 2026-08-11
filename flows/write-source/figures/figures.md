# Sub-flow: write-source / figures（嵌入图片 / Step 3.5）

> 统一模板：目的 / 触发 / 前置 / 步骤 / 本阶段规则 / 出口 / 相关代码 / 子流程
> 🔴 **这是强制步骤，不是可选建议。** 跳过它，Stage 4 的 E 层（图片嵌入）检查会判 FAIL。

## 目的
把 `_extract/figure/` 下被某条目（定义/定理/引理/命题/推论/例/证明）引用到的图，嵌入到该条目处；未引用的图不写入。

## 触发
- `write-source` 流程第 5 步：写完某章初稿 + 格式后处理之后、Stage 4 校验之前。
- 🔴 只要该书跑过图片流水线、且 `figure_index.json` 存在本章条目（对应 PNG 已生成），写章总结时就**必须**执行。

## 前置
- 图片流水线已跑（或历史数据已补图）：`figure_detect.json` + `figure_index.json` 存在，`figure/` 下有 PNG。
- 该章 `.md` 初稿已写好。

## 步骤（有序，脚本自动化、幂等）
```bash
python flows/script/figure/embed_figures "<book_dir>"            # 整本书（已嵌入自动跳过）
python flows/script/figure/embed_figures "<book_dir>" --chapter 3 # 只嵌某章
python flows/script/figure/embed_figures "<book_dir>" --dry-run   # 仅预览
```
脚本会：① 用 OCR 噪声容忍的"图注→条目锚点"启发式匹配；② 自动补 `_extract/` 路径前缀（不会写出坏链）；③ 嵌入后自动跑结构扫描——把落在 `> **证明/例**` 块内却写成顶层的图缩进进块（`> <img ...>`），并把块内裸空行转成 `> ` 保证引用块连续（直接满足 G 层要求）；④ 自动 flex 包装：所有 `<img>` 统一包裹 `<div style="display:flex; gap:6px; flex-wrap:wrap; justify-content:center">`，连续小图并排、单张居中。

## 本阶段规则（🔴 内联）
- **flex 容器格式铁律（2026-07-27 立）**：`<div style="display:flex; ...">` 与 `<img>`、`<img>` 与 `</div>` 之间**禁止出现空行**。合法形态：
  ```
  <div style="display:flex; gap:6px; flex-wrap:wrap; justify-content:center">
    <img src="_extract/figure/ch00_fig1.4.png" alt="图 Figure 1.4. ..." width="35.4%" height="auto">
  </div>
  ```
  根因：早期 `wrap_images_in_flex()` 给元素尾部追加 `\n` 而 `write_lines()` 又 `"\n".join`，双重换行 = 容器内空行。现已改为无尾换行行列表，重扫即净化。
- **书特有覆盖映射**：图注无明确条目编号但内容明显属某条目时，在该书 `_extract/figure_embed_overrides.json` 声明精确锚点（字段 `anchors` / `is_proof`、JSON 示例与生成脚本见 [`../../../data/figure_embed_overrides/figure_embed_overrides.md`](../../../data/figure_embed_overrides/figure_embed_overrides.md)）；无此文件则纯靠启发式。
- 本步是 Stage 4 校验的**前置依赖**：先嵌图，再跑 `verify_chapter.py`（其图片嵌入检查、G 层块连续性检查）。

## 出口条件
- 出口：本章（或全书）被引用图已嵌入、flex 格式合规。

## 相关代码（路径相对 skill 根目录）
- `flows/script/figure/embed_figures`：嵌图（幂等）。
- `flows/script/figure/extract_figures` / `flows/script/figure/assign_figures`：图片检测 / 命名（由 extract 的 figure_detection 子流程在 config 之后跑，产出 `figure_index.json`）。
- `../../../config/figure_manual_chN/apply_manual_figures.py`：E 层 FAIL 时手动补图。
- 完整图片流水线见 [`figure_pipeline.md`](ref/figure_pipeline.md)（SSOT）。

## 子流程
无。
