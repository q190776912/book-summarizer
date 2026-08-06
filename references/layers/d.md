# D 层 — SECTION CONTINUITY + MISSING TAIL SECTION (连续节 + 尾节)

> 本文件是 **D 层** 的唯一权威详情。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verification.md`](../verification.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。

## 一句话目的
**节的层级**检测（BLOCKING），堵住 B 层只在已检出节之间重扫、看不到整节漏写/节序列断裂的盲区。D 取 B 的“节内条目连续性 + 尾部”逻辑，抬升到“节”这一粒度。

支持**任意嵌套深度（1–4 级：章 / 节 / 小节 / 子小节）**，由 `<book>/_extract/verify_config.json` 的 `section_types` / `section_depths` 驱动（详见 `../verification.md` §6）。未显式声明时按 `ordinal` 反推（`ORDINAL_SECTION_TYPES`）：ordinal 2/4/6/7 仅校验章+节两级；ordinal 3/5 额外校验小节（1.1.1）层级（旧 `D_MD_NESTED_SEC_RE` 是死代码，本次首次真正生效）；ordinal 1 仅章级。

> 节的**条目级**尾部缺口（节在、末号丢了）仍由 **B 层** `_md_tail_warnings` 负责（md 末号 vs 抽取契约）。D 不重复做条目级尾部，只做“整节”层面的两件事。

## 两块检查（均 BLOCKING）

D 把“源有而 md 没有的节”按其在 md 节序列中的**位置**切成两块，互不重叠：

### 1. 连续节校验（CONTINUITY，节序列内部断裂）
- 某节在 md 的节序列中处于**内部**（md 既有更小的 §、也有更大的 §），但这一节本身缺失 → 节序列有洞，等价于 B 层“缺号”的节级版本。
- 例：md 写了 `## §1.1`、`## §1.3`，源有 §1.2 → §1.2 落进 `continuity_sections`。
- 首节缺失（md 从 §1.2 起、源有 §1.1）同样归此类（§1.1 ≤ md_max）。

### 2. 尾节校验（MISSING TAIL SECTION，末尾缺节）
- 某节在源中存在（节标题 + 带标签条目），但落在 md **最后一个已写节之后** → 整节未写。
- 例：md 止步 `## §1.2`，源还有 §1.3 → §1.3 落进 `missing_sections`。

### 防误报
- 一个节只在**原始 JSON 同时具备“节标题特征”与“带标签条目”**时才算“源确认存在”（`raw_sec_header ∩ raw_labeled_item`），因此源本身合法跳号的书不会被误报。
- 两块经 `s <= md_max`（内部）vs `s > md_max`（末尾）天然互斥，无重复计数。

## 阻断性 / 可修复
- 两块均 → 阻断 FAIL；自动修复 `auto_fixable = False`（需人工补写整节）。

## 字节契约键（legacy dict，供 `DEFAULT_RESULT` / `print_result` 同步）
```contract-keys
d_layer
levels
```

## 实现（`verify/layers/d_layer.py`）
- `code = 'D'`，`order = 1`（**运行顺序在 B 之前**），`auto_fixable = False`。
- 数据源：直接重扫原始 `_extract` 的 `page_*.json`，独立于 `extract_items`。
- `d_layer` 结构：`{'continuity_sections': [], 'missing_sections': [], 'levels': {}}`。
  - 顶层 `continuity_sections` / `missing_sections` 为**各层级合并列表**（相对章路径串，去章首分量，如 `(1,2,3)` → `"2.3"`），供 FAIL 门与旧行为兼容。
  - `levels` 为按层级拆分的明细字典：`{1: {'continuity': [...], 'missing': [...]}, 2: {...}, 3: {...}, ...}`，每级为相对章路径串列表，供 `report.py` 按级打印。
- 分区逻辑集中在 `_partition_sections_by_level(md_sections, raw_sec_header, raw_labeled_item, max_level)`；GM 变体 `check_d_layer_gm` 复用旧 `_partition_sections`（仅返回合并列表，无 `levels`）。
