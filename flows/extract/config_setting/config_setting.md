# Flow: config_setting（生成书级配置 / extract 子流程）

> 统一模板：目的 / 前置 / 步骤 / 本阶段规则 / 出口 / 相关代码 / 子流程

## 目的
在 extract 的 **MM Repair 全部完成**后（文本提取 100% 且全部稳定批次经模式 A+B 已 `mm_repair_apply` 写回 `page_*.json`；完成标记 `_extraction_done.json` 存在），依据**源 `page_*.json`** 一次性完成两件事：

1. **建章节映射** `_extract/chapter_map.json`（Step 1，统一在本阶段生成，不再轮询期间早建）；
2. **生成书级配置** `_extract/verify_config.json`（Step 2–3）——它是 `verify_chapter.py` / `flows/extract/structure/script/scan_skeleton` 的**唯一配置源**，也是后续批量校验的硬性前置。

图检测子流程依赖本书 `ordinal` 里的 **Figure 组**（`{"type":<段数>,"name":[图号前缀词],"scope":<段数>}`；`type` 经 `ORDINAL_DEPTH` 派生的 `depth` 即图号段数 components）来确定图号前缀与段数；缺 Figure 组时回落默认前缀 `["图","Figure","Fig"]`，自定义前缀书须在 Figure 组 `name` 显式列出。🔴 仅文本 100% 落盘但未完成 MM Repair（尤其模式 A 视觉审读）时不得跑本步——`chapter_map` 章边界与 `formula` map 都依赖校正后的页面。

## 前置
- **MM Repair 完成**（文本提取 100% 且全部稳定批次经模式 A+B 已 `mm_repair_apply` 写回 `page_*.json`；完成标记 `_extraction_done.json` 存在）。🔴 仅文本 100% 落盘、模式 A 视觉审读未做时，本步的配置会基于未修复页，属误用。
- 🔴 **翻译派生版不参与配置生成**。

## 步骤（有序）

1. **建章节映射（chapter_map，统一在本阶段生成）**
   - 从 `_extract/page_*.json` 的目录页（TOC 通常位于 `page_001~005` 附近，MM 修复后可用全文检索章名交叉确认）读每章**章名**与 **PDF 页码起止**，写 `_extract/chapter_map.json`：
     ```json
     { "chapters": [ {"ch": 1, "name": "Measure Theory", "start": 1, "end": 47}, ... ] }
     ```
   - 用 `../../../../data/chapter_map/chapter_map.py` 生成模板（数据结构见 [data/chapter_map/chapter_map.md](../../../../data/chapter_map/chapter_map.md)），或人工填入。
   - 🔴 `start`/`end` 是 **PDF 文件页码**（= `page_%03d.json` 序号，1-based），**不是**原书印刷页码；若 TOC 给的是印刷页号，须加前页偏移换算成 PDF 页号再写（详见 [data/chapter_map/chapter_map.md](../../../../data/chapter_map/chapter_map.md)）。全书落盘后可用正文首尾页与 TOC 交叉核对章边界。
   - 它是后续"某章是否已可写"、`make_config.py` 编号判定（罗马数字章号 / 每章 `ordinal` / `chapter_first`）、figure 按章分配与 `build_structure` 页区间读取的**唯一判定依据**。

2. **探测编号形态**（用全书 `page_*.json`）：
   - `ordinal` 分组（`type` / `name` / `scope`）、`language`、章节层级（`section_types`，深度经 `SECTION_TYPE_DEPTH` 派生，多数由 `primary_type` 自动反推，仅四级子小节 `1.1.1.1` 需显式覆盖）；
   - **公式序标形态**：若书含公式编号，扫 `page_*.json` 的 `text[]` 实测段数（如 `C.N` → `type 4`(depth 2)、`C.S.N` → `type 3`(depth 3)、章级 → `scope 2`），推导 `formula` map 的 `type` / `scope`（`depth` 由 `type` 经 `ORDINAL_DEPTH` 派生，不单独配置）；
   - **图序标体例（🔴 在 `ordinal` 里放一个 Figure 组，不得留缺）**：无论书是否用自定义图号前缀，`verify_config.json` 的 `ordinal` **必须**含一个 Figure 组（见 [`../../../config/verify_config/verify_config.md`](../../../config/verify_config/verify_config.md)）；图号前缀词写进该组 `name`，图号段数（components）= 该组 `type` 经 `ORDINAL_DEPTH` 派生的 `depth`（`type:1`→全局整数、`type:2`→章.图、`type:3`→章.节.图），`scope` 同值：
     - 书以非默认前缀标注图（如 `Scheme` / `Illustration` / 仅 `图` / 仅 `Fig`）→ Figure 组 `name` 列出**本书全部**图号前缀词（如 `{"type":2,"name":["图","Fig"],"scope":2}`）；
     - 书**完全没有**图序标（正文不出现任何图号前缀）→ **不在 `ordinal` 放任何 Figure 组**即可（figure_io 回落默认前缀）；若需严格"零匹配"（禁止任何前缀，避免误匹配正文 `Figure`/`图`），保留过渡 `{"figure": {"labels": []}}` 由 figure_io 识别为标记号。
     - **图检测子流程严格依赖此 Figure 组（或其过渡 `figure` 标记）**。
   - **小节序标体例（🔴 尊重原书，禁止编造）**：`_extract/verify_config.json` 的 `section_types` 是**逐层级**列表（从**章层级**排到最深的 `## §` 层级），每个元素是该层级 `## §` 标题的序标段数（1=一级 `## §N`、2=二级 `## §N.M`、3=三级、4=四级、**0=无序号标**），深度经 `SECTION_TYPE_DEPTH` 派生。**列表长度必须 = 章节层级总数（章计入）**——单层级书 `[0]`、章+无序号标小节书 `[0, 0]`：
     - 原书小节**带序标**（如 `§3.2`、`3.1.4`）→ 默认 `[1, 2]`（或按实际层级），总结写 `## §N.M 节名`，verify 缺节闸门按数字逐一对齐 `book_structure.json` 契约；
     - 原书小节**无序号标**（如 Silverman《A Friendly Introduction to Number Theory》：章是文件 `# 第N章` 无 `## §` 编号、文件内 `## § <标题>` 小节也无编号）→ **章层级与小节层级都显式写为 `0`**，即 `"section_types": [0, 0]`（第一个 `0`=章、第二个 `0`=小节，两个层级都无序号标），总结写 `## § 描述性标题`（数字留空、仅保留 `§`），verify 缺节闸门改为按「位置/数量」比对（只查契约要求的节是否都在、不计 md 多出的小节），**不强求加回原书没有的序标**。该配置是 per-book 配置，仅改本书行为，其他带序标书保持 `[1,2]` 之类、零回归。
3. 生成配置：
   ```powershell
   python config/verify_config/make_config.py <extract_dir>   # 半自动探测 + 人工核对（公用配置脚本）
   # 或手填 _extract/verify_config.json
   ```

## 本阶段规则（🔴 内联）
- **规则0 — chapter_map 统一在本阶段生成、且只建一次**：不再在 extract 轮询期间早建（旧 extract/chapter_map 子流程已并入本步）；**全书的 chapter_map 只生成一份**，不重复生成（除非用户明确要改章节划分）。判定"某章可写"的硬标准：`info.end <= current_max_page`（该章末页已落盘；extract 出口时全书页必已齐）。
- **规则1 — 书级配置强制前置（最高优先级）**：`verify_chapter.py` 由 `ConfigLoader.require_complete()` 强制：
  - 文件缺失 → **不能用默认配置，必须重新配置**（`make_config --force` 或手填），不得静默沿用默认 `ordinal`；
  - 文件存在但缺 `ordinal` → 硬报错 `exit 2`；
  - 存在 `formula` 块但字段非法 → 强制校验并 `exit 2`（`type`∈1–9、`scope`∈{1,2,3}、与书实测编号对账；`depth` 由 `type` 派生不单独校验）。
- **规则2 — 判定不清回归全部 json**：编号 / 小节层级判定不清时，**必须回归本书全部 `page_*.json` 依据上下文判断**，不得仅抽几页原文或只看 TOC 草率定稿，更不得依赖静默默认值。
- **规则3 — formula map 必含且由 `page_*.json` 推导**：书含公式序标时，`verify_config.json` **必须**含合法 `formula` map；缺失时按 `page_*.json` 实测编号推导写入，不得留空或跳过。
- **规则4 — 图序标配置强制显式（Figure 组必现，含"无图序标"标记号）**：`ordinal` **必须**含一个 Figure 组（见步骤 2），**不得因"懒得定"而留缺让下游静默回落默认**：
  - 有自定义图号前缀 → Figure 组 `name` 列出本书全部前缀词，`type`/`scope` 设对应段数（components）；
  - **无任何图序标** → 不在 `ordinal` 放 Figure 组（回落默认前缀）即可；若需严格零匹配，保留过渡 `{"figure": {"labels": []}}`（空数组标记号，figure_io 返回真正的零匹配，不回落默认）。
  - 反"隐藏问题"：无图号书若只因缺 Figure 组而静默用默认前缀，会把正文中碰巧出现的 `Figure`/`图` 等词误判为图号，污染图检测与 E 层（图引用 MISSING 检查）；故强制显式（或显式零匹配标记）。
- **规则5 — 序标类型不强制匹配、可增量扩展（🔴 强制）**：对定义/定理/引理/推论/命题/公式/图等带序标的类别，扫描 `page_*.json` 时若遇到一种**已知类型都匹配不上**的序标形态（新标签词、新编号体例、或新类别如"公理/Axiom""注记/Remark""练习/Exercise"等）：
  - **禁止强制匹配**：不得将陌生序标硬塞进已有 `ordinal` 组的 `name`/`type`，也不得凭"长得像"归入 `uncat` 或最近似类型——这会污染编号计数与跨章 `scope` 判定，等同"为通过校验而改被校验对象"（明确禁止）。
  - **允许增量扩展**：agent 找不到匹配时，**可以**增量式引入新类型：在 `verify_config.json` 的 `ordinal` 中新增一个 `type` 码（沿用既有 1–6 / 8 / 9 判定树，超出则顺延新码，如 `10`）+ 对应 `name` 标签；若该新类型需要新的抽取/匹配/校验脚本，agent **可增量添加相关脚本**（置于对应 flow 的 `script/` 下，并登记到 `../../../lib/boot.py` 注入路径与 `verify.md` 注册表），而非临时 hack 或强塞。
  - **判定不清仍须回归全书**：新类型的判定同样适用 规则2（回归全部 `page_*.json` 上下文），不得抽样定稿。
  - 补充：本规则与 `missing_label_policy.md` 互补——后者管"已识别类别但 OCR 漏抽的条目"（§2 凭知识库补写），本规则管"类别本身未知、需要扩展类型体系"的情形。
- **配置一次性生成**：配置**不是边写边填**，而是在文本提取全部完成后一次性生成（非增量）。`scan_skeleton` 对缺失配置仅告警、不阻断（安全网）；配置必须完整合法，且 `ordinal` 必须含 Figure 组（自定义前缀→`name` 非空、无图序标→不放 Figure 组或显式 `{"figure":{"labels":[]}}` 零匹配标记，二者皆不可"字段缺失而静默回落默认"）。
- **配置字段**见公用配置文档 [`../../../config/verify_config/verify_config.md`](../../../config/verify_config/verify_config.md)；`type` 为编号风格码（1–9，原 7 已并入 4）。

## 出口条件
- 出口：`_extract/chapter_map.json` 存在且含章节（作为 make_config 编号判定与下游页区间依据，先行产出）；`_extract/verify_config.json` 完整合法（含 `formula` map 若书有公式；**`ordinal` 含 Figure 组必现**——有自定义前缀则 Figure 组 `name` 非空、无图序标则不放 Figure 组或显式 `{"figure":{"labels":[]}}` 零匹配标记，二者皆不可"字段缺失而静默回落默认"）。

## 相关代码（路径相对 skill 根目录）
- `../../../../data/chapter_map/chapter_map.py`：chapter_map 模板工具（数据结构见 `../../../../data/chapter_map/chapter_map.md`）。
- `../../../config/verify_config/make_config.py`：半自动配置生成（**公用配置脚本**，与流程解耦，说明见 `../../../config/verify_config/verify_config.md`）。
- `../../../verify/script/verify_chapter.py`：消费配置做校验（`ConfigLoader.require_complete()`）。
- `../../../config/verify_config/verify_config.py`：`BookConfig` / `GroupConfig` 数据模型（schema 实现 SSOT）。

## 子流程
- [`extract/config_setting`](config_setting.md) 为 extract 的 config 子流程本体；chapter_map 建映射已并入本流程 Step 1，无独立子流程文档。