# F 层 — FIGURE VALIDITY（figure_validity）

> 本文件是 **F 层** 的唯一权威详情（SSOT）。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verify.md`](../verify.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。
> **注册机制**：本层脚本位于 `verify/layers/figure_validity/script/figure_validity.py`，由 `verify/script/register_all.py` 用 `importlib` 按裸名扫描 `verify/layers/*/script/` 自动发现并注册。`code = 'F'` 是稳定字母代号（被 SKILL.md 与 per-book 记忆广泛引用，**不可更改**）；新增层无需改 `register_all.py` / `VerifyManager` / CLI。

## 目的
图有效性：裁剪图能否正常解码。

## 步骤（语义与检查内容）
- 用 `np.fromfile` + `cv2.imdecode` 逐一打开裁剪图。
- **INVALID（阻断 FAIL）**：缺失文件 / 无法解码 / 单边 <20px。
- **SUSPICIOUS（仅 WARN）**：近空白（灰度方差 <50，疑似误检文字块）。

## 本阶段规则（阻断性 / 可修复）
- 有图时 `fig_invalid` 非空 → 阻断 FAIL。
- `auto_fixable = False`。

## 出口条件
有图且 `fig_invalid` 非空 → 整章 FAIL；`fig_invalid_warn` 仅 WARN（不阻断）。

## 相关代码（`verify/layers/figure_validity/script/figure_validity.py`）
- `code = 'F'`，`order = 6`，`auto_fixable = False`。
- 与 E 同前提（无 `figure_index.json` 则 SKIP）。底层返回 None 必须 emit 空列表。

## 子流程
无独立子脚本；与 E 共用 `_extract/figure_index.json`。

## 需 agent 手工修复（manual fix）
本层 `auto_fixable = False`。图文件缺失/损坏/过小须重抽或替换源图，脚本不修二进制。

- **触发门（report.py）**：`F-LAYER FIGURE VALIDITY ERRORS` → 整章 FAIL；
`F-LAYER FIGURE SUSPICIOUS` → 仅 WARN。
- **修复步骤**：
  1. 看 `F-LAYER FIGURE VALIDITY ERRORS` 列出的图（缺失文件 / 无法解码 / 单边 <20px）。
  2. 到 `<book>/_extract/figures/` 确认文件存在且可解码；缺失则重跑图片提取生成，损坏则在源 PDF 重新裁剪。
  3. `F-LAYER FIGURE SUSPICIOUS`（近空白，疑似误检文字块）仅 WARN，核对必要时加 `ignore_figure`。
  4. 重跑 verify，确认 `F-LAYER FIGURE VALIDITY ERRORS` 清零。

修复后重跑 `verify_chapter.py --all`（或单章 `<ch> <start> <end> <md> <ext>`）确认上述门为空 / 转绿。

## 字节契约键
```contract-keys
fig_invalid
fig_invalid_warn
```
