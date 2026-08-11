# numbering-gap 层（B · `numbering_gap`）

> **公用子流程（Sub-flow）。** 本文件是该校验层的**单一权威（SSOT）**，
> 同时作为可被其他消费者独立引用的校验子流程。
> 稳定标识符：`code="B"`（字母代号，被 `SKILL.md` 与 per-book 记忆广泛引用，不可更改）；
> 语义名：`numbering-gap`（`numbering_gap`）。

## 目的

## 一句话目的
检测 agent 写出的 .md 交付物里「条目编号缺号」，让 agent 来补；中段不存在合法跳号，漏了就是漏了。
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
- `blocking` 非空 -> 阻断 FAIL。`auto_fixable = False`（缺号只能 agent 补写，不能脚本修）。
- 解决优先级：先尝试补真实项（并在 `manual_overrides_ch{N}.json` 登记）；仅当确认是 OCR 乱码 / 无法修复的交叉引用才进 `ignore`(`verify_config.json`) 或用 `--ignore` CLI 标志。
## 出口

- 阻断层：对应字节契约键非空 → 该章 FAIL（exit 1）；不可 `--fix`，须回写作阶段修正。

## 相关代码

- 实现：`script/numbering_gap.py`
  - `code="B"`，`order=3`，`auto_fixable=False`。
- 注册：经 `../../script/register_all.py` 自动发现（`pkgutil` 扫描 `..` 子包），无需手动登记。

## 子流程

无独立子流程；本层为单一校验关注点。

## 字节契约键（legacy dict，供 `DEFAULT_RESULT` / `print_result` 同步）

```contract-keys
blocking
b_gap_warnings
b_tail_warnings
ignored_hit
```

## 实现备注

## 实现（`script/numbering_gap.py`）
- `code = 'B'`，`order = 3`，`auto_fixable = False`。
- 数据源：`ctx.extraction_blocking`（EXTRACT 阶段填）+ MD 侧 `_md_gap_blocking` 结果 + 源 `ctx.items`（尾部校验）。
- 编号配置由 `config.BookConfig` 经 `ConfigLoader` 从 `<book>/_extract/verify_config.json` 一次性读出，挂在 `ctx.config` 上；B 层与提取层都读 `ctx.config`，**不再各自读文件**（旧的 `load_for_md` 文件 IO 已删除）。分组由 `ordinal` 数组各 group 的 `type`/`depth`/`scope` 决定（见 `../../../config/verify_config/verify_config.py` 的 `GroupConfig` / `ORDINAL_DEPTH`），JSON 里 `ordinal` 必填为数组。
- `BLayer.run`：
  1. `ignored_hit` **第二段** suppression：遍历 `blocking`，若某条引用键全部 ∈ `ignore_keys`，把 `bkeys` 并入 `ctx.ignored_hit` 并从 `blocking` 剔除（最终 `ignored_hit` 由 B 回写，覆盖 EXTRACT 的 stage1）。
  2. 算 MD 侧 `_md_gap_blocking` -> `(md_blocking, md_warnings, present_md, md_tail)`。
  3. 对提取侧 `blocking` 做「MD 存在性过滤」：被报缺的键 ∈ `present_md` 则抑制（消息号已带前导 `-`，拼接用 `sec + n`）。
  4. 合并 `blocking = filtered_extraction + md_blocking`；返回 `metadata={'blocking','b_gap_warnings','b_tail_warnings','ignored_hit'}`。
- `b_tail_warnings` 由 `report.py` 在 `B-LAYER TAIL CHECK` 段非阻断打印；`b_gap_warnings` 在 `B-LAYER NUMBERING GAP CHECK` 段打印。
