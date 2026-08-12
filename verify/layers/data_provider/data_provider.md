# EXTRACT 层 — 数据 provider（data_provider）

> 本文件是 **EXTRACT 层** 的唯一权威详情（SSOT）。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verify.md`](../verify.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。
> **注册机制**：本层脚本位于 `verify/layers/data_provider/script/data_provider.py`，由 `verify/script/register_all.py` 用 `importlib` 按裸名扫描 `verify/layers/*/script/` 自动发现并注册。`code = 'EXTRACT'` 是稳定字母代号（被 SKILL.md 与 per-book 记忆广泛引用，**不可更改**）；新增层无需改 `register_all.py` / `VerifyManager` / CLI。

## 目的
提供原始 JSON 数据（提取条目 / 键集），是后续所有层的输入源；必跑、永不可禁用。

## 步骤（语义与检查内容）
- 扫描 `_extract` 的 `page_*.json`，填 `ctx.items` / `ctx.entry_keys` / `ctx.all_keys`。
- 算 `ignored_hit` **第一段（stage1）** 写入 `ctx`（最终值由 B 层第二段回写，见下）。
- 必须原样 port 英文书分支（`ctx.config.ordinal == ORDINAL_EN`：按章过滤前向引用、key 规范化成中文形式；md 侧 `entry_keys`/`all_keys` 限制到当前章）。
- 三段逻辑（three-level / two-level / en）必须完整搬运，否则 EN 书整体漂移。

## 本阶段规则（阻断性 / 可修复）
- 本身不是 pass/fail 判定层，但 `extract_dir` 缺失 / 无 `page_*.json` → 数据缺失 → FAIL。
- **永不可禁用**（manager 特判 `code != 'EXTRACT'`）。

## 出口条件
本层不产出阻断性结论，仅向 `ctx` / 结果字典注入数据；若数据源缺失则整章 FAIL。

## 相关代码（`verify/layers/data_provider/script/data_provider.py`）
- `code = 'EXTRACT'`，`order = 0`，`auto_fixable = False`。
- `all_keys` 为辅助键、**不进入 legacy 字节契约**（不影响 `print_result` 输出）。
- `ignored_hit` 两段式：EXTRACT 算 stage1 → B 层在产出 `blocking` 后做第二段 regex 抑制并回写最终 `ignored_hit`（manager 按 `order` 合并、B 覆盖 EXTRACT）。禁止只由 EXTRACT 一次性算完。

## 子流程
无独立子流程；依赖抽取管线产出的 `page_*.json`（由 `flows/extract/structure/script/` 下的抽取器生成）。

## 需 agent 手工修复（manual fix）
本层 `auto_fixable = False`，且本身不是 pass/fail 判定层——它是**数据供给层**
（`EXTRACT`，`code='EXTRACT'`，`order=0`），向 `ctx` / 结果字典注入
`ctx.items` / `entry_keys` / 提取 `blocking`/`warnings`。数据源缺失须由 agent 回到
抽取 pipeline 重跑，**脚本不修数据**。

- **触发门（report.py）**：`extract_dir` 缺失或无 `page_*.json`（OCR 抽取产物）/
无 `figure_index.json`（图片提取产物）→ 下游依赖数据的层整章 FAIL 或 SKIP；
本层不产出独立 BLOCKING，但数据缺失会经由各下游层表现为 FAIL。
- **修复步骤**：
  1. 确认 `<book>/_extract/` 存在且含 `page_*.json`、`figure_index.json`、`book_structure.json`。
  2. 若缺失：回到抽取 pipeline（PDF-Extract-Kit：MFD / UniMERNet / PaddleOCR，
且抽取后必须先跑 `mm修复` pre-step），重跑该章抽取补齐产物。
  3. 数据源齐备后再跑 verify；缺数据时空跑 verify 无意义。

修复后重跑 `verify_chapter.py --all`（或单章 `<ch> <start> <end> <md> <ext>`）确认上述门为空 / 转绿。

## 字节契约键
```contract-keys
items
entry_keys
blocking
warnings
label_warns
ignored_hit
```
> EXTRACT 另在 `ctx` 上挂 `all_keys` / `extracted`（辅助键，不进入 legacy 字节结果字典）；`blocking` 即提取侧 `extraction_blocking`、`warnings` 即 `extraction_warnings`，供 B 层在 md 侧做存在性过滤与尾部校验。
