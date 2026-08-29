# EXTRACT 层 — 数据 provider（data_provider）

> 本文件是 **EXTRACT 层** 的唯一权威详情（SSOT）。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verify.md`](../verify.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。
> **注册机制**：本层脚本位于 `verify/data_provider/script/data_provider.py`，由 `verify/script/register_all.py` 用 `importlib` 按裸名扫描 `verify/*/script/` 自动发现并注册。`code = 'EXTRACT'` 是稳定字母代号（被 SKILL.md 与 per-book 记忆广泛引用，**不可更改**）；新增层无需改 `register_all.py` / `VerifyManager` / CLI。

## 目的
**纯数据供给层（provider 模式）**：从「书的真相集」(book_structure.json) 与「md 写入集」(keys_in_md) 取值，挂到 `ctx` 上供下游所有层使用。**本层不做任何缺失项比对 / 查漏**——那些职责已统一归 B 层 (item_numbering_integrity)：B 是查漏的唯一权威，EXTRACT 只供水、不做事。

## 步骤（语义与检查内容）
- 读统一结构 JSON（book_structure.json，SSOT 书对象，无旧书回退）→ `ctx.items`（非 exercise/chapter/section 节点）。
- 解析 md 得 `ctx.entry_keys`（加粗独立条目 `**标签N.N**`）与 `ctx.all_keys`（md 中出现过的一切键，含正文/交叉引用里的 mention）。
- EN 书分支（`ctx.config.ordinal == ORDINAL_EN`）：md 侧 `entry_keys`/`all_keys` 限制到当前章（`_first_num(k) == ctx.ch`）。
- 标签一致性检查 `check_label_consistency` → `ctx.label_warns`（标签(定义/定理)与正文前 60 字不符告警，report 打印、非阻断）。

## 本阶段规则（阻断性 / 可修复）
- 本身不是 pass/fail 判定层，但 `book_structure.json` 缺失 / 无 `page_*.json` → 数据缺失 → 下游 FAIL。
- **必跑**（Every layer ALWAYS runs；不存在 `code != 'EXTRACT'` 特判或 disable 机制）。

## 出口条件
本层不产出阻断性结论，仅向 `ctx` / 结果字典注入数据；若数据源缺失则经由下游层表现为整章 FAIL。

## 相关代码（`verify/data_provider/script/data_provider.py`）
- `code = 'EXTRACT'`，`order = 0`，`auto_fixable = False`。
- `ctx.items` / `ctx.entry_keys` / `ctx.all_keys` / `ctx.label_warns` 为本层唯一产出；其中 `all_keys` 为辅助键、**不进入字节级输出契约**（不影响 `print_result` 输出）。
- 缺失项比对、查漏、阻断（`truly_missing` / `mentioned_only` / `extra` / 提取侧 `blocking` / `warnings` / `ignored_hit`）**全部由 B 层计算并写 `ctx`**，本层不再参与——B 与 EXTRACT 解耦：EXTRACT 只供水，B 只查漏。

## 子流程
无独立子流程；依赖抽取管线产出的 `page_*.json` / `book_structure.json`（由 `flows/write-source/structure/script/` 下的抽取器生成）。

## 需 agent 手工修复（manual fix）
本层 `auto_fixable = False`，且本身不是 pass/fail 判定层——它是**数据供给层**
（`EXTRACT`，`code='EXTRACT'`，`order=0`），向 `ctx` / 结果字典注入
`ctx.items` / `entry_keys` / `all_keys` / `label_warns`。数据源缺失须由 agent 回到
抽取 pipeline 重跑，**脚本不修数据**。

- **触发门（report.py）**：`book_structure.json` 缺失或无 `page_*.json`（OCR 抽取产物）/
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
label_warns
```
> 本层**不**产出 `blocking` / `warnings` / `ignored_hit` / `extracted`（这些现由 B 层计算）。`all_keys` 为辅助 ctx 键（供 B 做完整性差集），**不进入字节级输出结果字典**，故不列入上方契约键。
