# D 层 — 节的连续性 + 尾节缺失（section_continuity）

> 本文件是 **D 层** 的唯一权威详情（SSOT）。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verify.md`](../verify.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。
> **注册机制**：本层脚本位于 `verify/section_continuity/script/section_continuity.py`，由 `verify/script/register_all.py` 用 `importlib` 按裸名扫描 `verify/*/script/` 自动发现并注册。`code = 'D'` 是稳定字母代号（被 SKILL.md 与 per-book 记忆广泛引用，**不可更改**）；新增层无需改 `register_all.py` / `VerifyManager` / CLI。

## 目的
**节的层级**检测（BLOCKING），堵住 B 层只在已检出节之间重扫、看不到整节漏写/节序列断裂的盲区。D 取 B 的“节内条目连续性 + 尾部”逻辑，抬升到“节”这一粒度。

支持**任意嵌套深度（1–4 级：章 / 节 / 小节 / 子小节）**，由 `<book>/_extract/verify_config.json` 的 `section_types` 驱动（深度经 `SECTION_TYPE_DEPTH` 派生；详见 `../verify.md` §6）。未显式声明时按 `ordinal` 反推（`ORDINAL_SECTION_TYPES`）：ordinal 2/4/6/7 仅校验章+节两级；ordinal 3/5 额外校验小节（1.1.1）层级（旧 `D_MD_NESTED_SEC_RE` 是死代码，本次首次真正生效）；ordinal 1 仅章级。

> 节的**条目级**尾部缺口（节在、末号丢了）仍由 **B 层** `_md_tail_warnings` 负责（md 末号 vs 抽取契约）。D 不重复做条目级尾部，只做“整节”层面的两件事。

## 步骤（语义与检查内容）

### 两块检查（均 BLOCKING）
D 把“源有而 md 没有的节”按其在 md 节序列中的**位置**切成两块，互不重叠：

#### 1. 连续节校验（CONTINUITY，节序列内部断裂）
- 某节在 md 的节序列中处于**内部**（md 既有更小的 §、也有更大的 §），但这一节本身缺失 → 节序列有洞，等价于 B 层“缺号”的节级版本。
- 例：md 写了 `## §1.1`、`## §1.3`，源有 §1.2 → §1.2 落进 `continuity_sections`。
- 首节缺失（md 从 §1.2 起、源有 §1.1）同样归此类（§1.1 ≤ md_max）。

#### 2. 尾节校验（MISSING TAIL SECTION，末尾缺节）
- 某节在源中存在（节标题 + 带标签条目），但落在 md **最后一个已写节之后** → 整节未写。
- 例：md 止步 `## §1.2`，源还有 §1.3 → §1.3 落进 `missing_sections`。

#### 防误报
- 一个节只在**原始 JSON 同时具备“节标题特征”与“带标签条目”**时才算“源确认存在”（`raw_sec_header ∩ raw_labeled_item`），因此源本身合法跳号的书不会被误报。
- 两块经 `s <= md_max`（内部）vs `s > md_max`（末尾）天然互斥，无重复计数。

## 本阶段规则（阻断性 / 可修复）
- 两块均 → 阻断 FAIL；自动修复 `auto_fixable = False`（需人工补写整节）。

## 出口条件
`d_layer.continuity_sections` 或 `d_layer.missing_sections` 非空 → 整章 FAIL。

## 相关代码（`verify/section_continuity/script/section_continuity.py`）
- `code = 'D'`，`order = 1`（**运行顺序在 B 之前**），`auto_fixable = False`。
- 数据源：直接重扫原始 `_extract` 的 `page_*.json`，独立于 `extract_items`。
- `d_layer` 结构：`{'continuity_sections': [], 'missing_sections': [], 'levels': {}}`。
  - 顶层 `continuity_sections` / `missing_sections` 为**各层级合并列表**（相对章路径串，去章首分量，如 `(1,2,3)` → `"2.3"`），供 FAIL 门与旧行为兼容。
  - `levels` 为按层级拆分的明细字典：`{1: {'continuity': [...], 'missing': [...]}, 2: {...}, 3: {...}, ...}`，每级为相对章路径串列表，供 `report.py` 按级打印。
- 分区逻辑集中在 `_partition_sections_by_level(md_sections, raw_sec_header, raw_labeled_item, max_level)`；GM 变体 `check_d_layer_gm` 复用旧 `_partition_sections`（仅返回合并列表，无 `levels`）。

## 子流程
无独立子脚本；分区算法 `_partition_sections_by_level` 在本层脚本内。

## 需 agent 手工修复（manual fix）
本层 `auto_fixable = False`（需人工补写整节）。章节序列断裂 / 整节缺失须由 agent 补写，
脚本不编。

- **触发门（report.py，D 层最先打印，最基础）**：`D-LAYER CONTINUITY GAP` /
`D-LAYER MISSING TAIL SECTION` / `D-LAYER LEVEL L CONTINUITY GAP` /
`D-LAYER LEVEL L MISSING TAIL SECTION` → 任一非空即整章 FAIL。
- **修复步骤**：
  1. 看 D-LAYER 各段列出的缺失节路径（如 `§2.3` 断裂、尾节 `§4.5` 缺失）。
  2. 回源 PDF 确认该节确实缺失；补写整节（标题 + 条目），并在 `manual_overrides` 登记。
  3. 若属 OCR 漏检（源其实有）或本书确无该节，检查 `chapter_map.json` / `book_structure.json` 是否准确，
必要时修正源契约，而不是改 md 掩盖。
  4. 重跑 verify，确认 D-LAYER 各段为空。

修复后重跑 `verify_chapter.py --all`（或单章 `<ch> <start> <end> <md> <ext>`）确认上述门为空 / 转绿。

## 字节契约键
```contract-keys
d_layer
```
> `d_layer` 为唯一返回键，其内部含 `continuity_sections` / `missing_sections` / `levels` 三个子结构（`levels` 是按层级拆分的明细，非顶层独立键）。
