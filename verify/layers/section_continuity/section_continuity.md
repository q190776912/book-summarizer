# section-continuity 层（D · `section_continuity`）

> **公用子流程（Sub-flow）。** 本文件是该校验层的**单一权威（SSOT）**，
> 同时作为可被其他消费者独立引用的校验子流程。
> 稳定标识符：`code="D"`（字母代号，被 `SKILL.md` 与 per-book 记忆广泛引用，不可更改）；
> 语义名：`section-continuity`（`section_continuity`）。

## 目的

## 一句话目的
**节的层级**检测（BLOCKING），堵住 B 层只在已检出节之间重扫、看不到整节漏写/节序列断裂的盲区。D 取 B 的“节内条目连续性 + 尾部”逻辑，抬升到“节”这一粒度。

支持**任意嵌套深度（1–4 级：章 / 节 / 小节 / 子小节）**，由 `<book>/_extract/verify_config.json` 的 `section_types` / `section_depths` 驱动（详见 `../../verify.md` §6）。未显式声明时按 `ordinal` 反推（`ORDINAL_SECTION_TYPES`）：ordinal 2/4/6/7 仅校验章+节两级；ordinal 3/5 额外校验小节（1.1.1）层级（旧 `D_MD_NESTED_SEC_RE` 是死代码，本次首次真正生效）；ordinal 1 仅章级。

> 节的**条目级**尾部缺口（节在、末号丢了）仍由 **B 层** `_md_tail_warnings` 负责（md 末号 vs 抽取契约）。D 不重复做条目级尾部，只做“整节”层面的两件事。
## 触发

由 `verify` 总流程（见 [`../../verify.md`](../../verify.md) 与注册表 [`..`](.)）
按 `order` 自动调度；亦可被其他消费者（如 `../../../flows/verify-source`、`../../../flows/derive-translate`
或外部 skill）单独引用本子流程，针对单章 / 单文件运行该校验层。

## 前置

- `<book>/_extract/verify_config.json` 完整合法（config_setting 流程 规则1）。
- 依赖数据的层需 EXTRACT 层已填充 `ctx.items / entry_keys / all_keys`
（见 [data_provider](../data_provider/data_provider.md)）。

## 步骤

（见下）

## 本阶段规则

## 阻断性 / 可修复
- 两块均 → 阻断 FAIL；自动修复 `auto_fixable = False`（需人工补写整节）。
## 出口

- 阻断层：对应字节契约键非空 → 该章 FAIL（exit 1）；不可 `--fix`，须回写作阶段修正。

## 相关代码

- 实现：`script/section_continuity.py`
  - `code="D"`，`order=1`，`auto_fixable=False`。
- 注册：经 `../../script/register_all.py` 自动发现（`pkgutil` 扫描 `..` 子包），无需手动登记。

## 子流程

无独立子流程；本层为单一校验关注点。

## 字节契约键（legacy dict，供 `DEFAULT_RESULT` / `print_result` 同步）

```contract-keys
d_layer
levels
```

## 实现备注

## 实现（`script/section_continuity.py`）
- `code = 'D'`，`order = 1`（**运行顺序在 B 之前**），`auto_fixable = False`。
- 数据源：直接重扫原始 `_extract` 的 `page_*.json`，独立于 `extract_items`。
- `d_layer` 结构：`{'continuity_sections': [], 'missing_sections': [], 'levels': {}}`。
  - 顶层 `continuity_sections` / `missing_sections` 为**各层级合并列表**（相对章路径串，去章首分量，如 `(1,2,3)` → `"2.3"`），供 FAIL 门与旧行为兼容。
  - `levels` 为按层级拆分的明细字典：`{1: {'continuity': [...], 'missing': [...]}, 2: {...}, 3: {...}, ...}`，每级为相对章路径串列表，供 `report.py` 按级打印。
- 分区逻辑集中在 `_partition_sections_by_level(md_sections, raw_sec_header, raw_labeled_item, max_level)`；GM 变体 `check_d_layer_gm` 复用旧 `_partition_sections`（仅返回合并列表，无 `levels`）。
