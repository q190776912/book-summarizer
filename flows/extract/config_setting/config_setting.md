# Flow: config_setting（生成书级配置 / extract 子流程）

> 统一模板：目的 / 前置 / 步骤 / 本阶段规则 / 出口 / 相关代码 / 子流程

## 目的
在 extract 的 **MM Repair 全部完成**后（文本提取 100% 且全部稳定批次经模式 A+B 已 `mm_repair_apply` 写回 `page_*.json`；完成标记 `_extraction_done.json` 存在），依据**源 `page_*.json`** 一次性生成 `<book>/_extract/verify_config.json`——它是 `verify_chapter.py` / `flows/extract/structure/script/scan_skeleton` 的**唯一配置源**，也是后续批量校验的硬性前置。图检测子流程依赖本书的 `figure.labels`（未配置会退化默认前缀、自定义前缀书漏识 caption），故 `figure` 块必须显式出现。🔴 仅文本 100% 落盘但未完成 MM Repair（尤其模式 A 视觉审读）时不得跑本步——`formula` map 依赖校正后的页面。
## 前置
- **MM Repair 完成**（文本提取 100% 且全部稳定批次经模式 A+B 已 `mm_repair_apply` 写回 `page_*.json`；完成标记 `_extraction_done.json` 存在）。🔴 仅文本 100% 落盘、模式 A 视觉审读未做时，本步的配置会基于未修复页，属误用。
- 🔴 **翻译派生版不参与配置生成**。

## 步骤（有序）
1. 用全书 `page_*.json` 探测编号形态：
   - `ordinal` 分组（`type` / `name` / `scope`）、`language`、章节层级（`section_types` / `section_depths`，多数由 `primary_type` 自动反推，仅四级子小节 `1.1.1.1` 需显式覆盖）；
   - **公式序标形态**：若书含公式编号，扫 `page_*.json` 的 `text[]` 实测段数（如 `C.N` → `type 4`(depth 2)、`C.S.N` → `type 3`(depth 3)、章级 → `scope 2`），推导 `formula` map 的 `type` / `scope`（`depth` 由 `type` 经 `ORDINAL_DEPTH` 派生，不单独配置）；
   - **图序标体例（🔴 强制显式生成，不得留缺）**：无论书是否用自定义图号前缀，`verify_config.json` **必须**显式包含 `figure` 块（见 [`../../../config/verify_config/verify_config.md`](../../../config/verify_config/verify_config.md)）：
     - 书以非默认前缀标注图（如 `Scheme` / `Illustration` / 仅 `图` / 仅 `Fig`）→ 写 `"figure": {"labels": [...]}` 列出**本书全部**图号前缀词；
     - 书**完全没有**图序标（正文不出现任何图号前缀）→ **显式写 `"figure": {"labels": []}`**（空数组即"无图序标"的**标记号**），与"`figure` 字段缺失→回落默认 `FIGURE_LABELS_DEFAULT`"严格区分：空数组表示"本书确无图号、禁止匹配任何前缀"，字段缺失才会静默用默认前缀（会误匹配无图号书里碰巧出现的 `Figure`/`图` 等词）。
     - **图检测子流程严格依赖此字段**。
2. 生成配置：
   ```powershell
   python config/verify_config/make_config.py <extract_dir>   # 半自动探测 + 人工核对（公用配置脚本）
   # 或手填 _extract/verify_config.json
   ```

## 本阶段规则（🔴 内联）
- **规则1 — 书级配置强制前置（最高优先级）**：`verify_chapter.py` 由 `ConfigLoader.require_complete()` 强制：
  - 文件缺失 → **不能用默认配置，必须重新配置**（`make_config --force` 或手填），不得静默沿用默认 `ordinal`；
  - 文件存在但缺 `ordinal` → 硬报错 `exit 2`；
  - 存在 `formula` 块但字段非法 → 强制校验并 `exit 2`（`type`∈1–9、`scope`∈{1,2,3}、与书实测编号对账；`depth` 由 `type` 派生不单独校验）。
- **规则2 — 判定不清回归全部 json**：编号 / 小节层级判定不清时，**必须回归本书全部 `page_*.json` 依据上下文判断**，不得仅抽几页原文或只看 TOC 草率定稿，更不得依赖静默默认值。
- **规则3 — formula map 必含且由 `page_*.json` 推导**：书含公式序标时，`verify_config.json` **必须**含合法 `formula` map；缺失时按 `page_*.json` 实测编号推导写入，不得留空或跳过。
- **规则4 — 图序标配置强制显式生成（含"无图序标"标记号）**：`figure` 块**必须**在配置中显式出现（见步骤 1），**不得因"懒得定"而留缺让下游静默回落默认**：
  - 有自定义图号前缀 → `figure.labels` 列出本书全部前缀词；
  - **无任何图序标** → `figure.labels` 显式置空数组 `[]`（**这就是"标记号"**：明确告知"本书无图号、禁止匹配任何前缀"）。空数组与字段缺失语义不同——缺失→回落 `FIGURE_LABELS_DEFAULT`（`["图","Figure","Fig"]`，可能误匹配）；空数组→真正的"零匹配"。
  - 反"隐藏问题"：无图号书若只因 `figure` 缺失而静默用默认前缀，会把正文中碰巧出现的 `Figure`/`图` 等词误判为图号，污染图检测与 E 层（图引用 MISSING 检查）；故强制显式标记。
- **规则5 — 序标类型不强制匹配、可增量扩展（🔴 强制）**：对定义/定理/引理/推论/命题/公式/图等带序标的类别，扫描 `page_*.json` 时若遇到一种**已知类型都匹配不上**的序标形态（新标签词、新编号体例、或新类别如"公理/Axiom""注记/Remark""练习/Exercise"等）：
  - **禁止强制匹配**：不得将陌生序标硬塞进已有 `ordinal` 组的 `name`/`type`，也不得凭"长得像"归入 `uncat` 或最近似类型——这会污染编号计数与跨章 `scope` 判定，等同"为通过校验而改被校验对象"（明确禁止）。
  - **允许增量扩展**：agent 找不到匹配时，**可以**增量式引入新类型：在 `verify_config.json` 的 `ordinal` 中新增一个 `type` 码（沿用既有 1–7 判定树，超出则顺延新码，如 `8`）+ 对应 `name` 标签；若该新类型需要新的抽取/匹配/校验脚本，agent **可增量添加相关脚本**（置于对应 flow 的 `script/` 下，并登记到 `../../../lib/boot.py` 注入路径与 `verify.md` 注册表），而非临时 hack 或强塞。
  - **判定不清仍须回归全书**：新类型的判定同样适用 规则2（回归全部 `page_*.json` 上下文），不得抽样定稿。
  - 补充：本规则与 `missing_label_policy.md` 互补——后者管"已识别类别但 OCR 漏抽的条目"（§2 凭知识库补写），本规则管"类别本身未知、需要扩展类型体系"的情形。
- **配置一次性生成**：配置**不是边写边填**，而是在文本提取全部完成后一次性生成（非增量）。`scan_skeleton` 对缺失配置仅告警、不阻断（安全网）；配置必须完整合法，且 `figure` 块必须显式出现（自定义前缀→`labels` 非空、无图序标→`labels` 显式空数组 `[]`，二者皆不可"字段缺失"）。
- **配置字段**见公用配置文档 [`../../../config/verify_config/verify_config.md`](../../../config/verify_config/verify_config.md)；`type` 为编号风格码（1–7）。

## 出口条件
- 出口：`_extract/verify_config.json` 完整合法（含 `formula` map 若书有公式；**`figure` 块必现**——有自定义前缀则 `labels` 非空、无图序标则 `labels` 显式空数组 `[]`，二者皆不可"字段缺失"）。

## 相关代码（路径相对 skill 根目录）
- `../../../config/verify_config/make_config.py`：半自动配置生成（**公用配置脚本**，与流程解耦，说明见 `../../../config/verify_config/verify_config.md`）。
- `../../../verify/script/verify_chapter.py`：消费配置做校验（`ConfigLoader.require_complete()`）。
- `../../../config/verify_config/verify_config.py`：`BookConfig` / `GroupConfig` 数据模型（schema 实现 SSOT）。
