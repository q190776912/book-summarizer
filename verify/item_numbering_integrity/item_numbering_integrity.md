# B 层 — 定义/定理/引理/推论/命题/例子 编号跳空（遗漏）检测（item_numbering_integrity）

> 本文件是 **B 层** 的唯一权威详情（SSOT）。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verify.md`](../verify.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。
> **注册机制**：本层脚本位于 `verify/item_numbering_integrity/script/item_numbering_integrity.py`，由 `verify/script/register_all.py` 用 `importlib` 按裸名扫描 `verify/*/script/` 自动发现并注册。`code = 'B'` 是稳定字母代号（被 SKILL.md 与 per-book 记忆广泛引用，**不可更改**）；新增层无需改 `register_all.py` / `VerifyManager` / CLI。

## 目的
检测 agent 写出的 `.md` 交付物里「条目编号缺号」，让 agent 来补；中段不存在合法跳号，漏了就是漏了。——本质是**忠于原文**地发现「定义/定理/引理/推论/命题/例子」等条目被整条漏写（首项缺失、序列断裂、或尾部比源少）。

## 宗旨（B 层本分）
对任意一组（per-type 下的某一类、按本书编号习惯分组）的编号序列必须完整：
- **首项检验**：序列应从 1 开始；不从 1 开始 => 首项缺失（在 `strict` 下 BLOCKING，否则 warning）。
- **连续性**：组内 `[first, last]` 必须连续；中间缺号 => 真漏项（在 `strict` 下 BLOCKING，否则 warning）。
- **尾部校验**：取 `.md` 组内最大号 `last`；若**提取契约（源, `ctx.items`）同组最大号 `smax > last`** 且中间号源有而 `.md` 无 => 疑似尾部漏项（**始终非阻断**，仅 `b_tail_warnings` 提示，请人工核实章/节是否即止）。

四类输出（见「字节契约键」）：
- `blocking`：严格模式下 md 内部首项/连续性缺口 + 提取侧查漏（整类首项缺失、OCR over-mark 守卫），（硬 FAIL，`auto_fixable=False`）。
- `truly_missing` / `mentioned_only` / `extra`：整章完整性（B 层职责）。`truly_missing`=书有而 md 全宇宙无 → 阻断；`mentioned_only`=仅正文/引用出现、非独立条目 → 仅复核；`extra`=md 有而提取未检出（多为合法交叉引用）→ 仅参考。
- `warnings`：非阻断（含 over-mark 守卫的误标提示、OCR 漏检复核等）。
- `b_gap_warnings`：非严格模式（`strict:false`）下 md 内部首项/连续性缺口，降级为非阻断警示。
- `b_tail_warnings`：尾部校验，始终非阻断。

## 步骤（语义与检查内容）

### 分组（按书的编号习惯，来自 `BookConfig` / `ctx.config.ordinal`）
配置由 `ConfigLoader`（`config/verify_config/verify_config.py`）从 `<book>/_extract/verify_config.json` 一次性读出，挂在 `ctx.config`；B 层与提取层都读 `ctx.config`（配置统一经 `ConfigLoader` 一次性加载）。

**单一配置文件**：`<book>/_extract/verify_config.json`（扁平，存放分组与抑制字段 `ordinal`（分组对象数组 `List[GroupConfig]`） / `language` / `strict` / `ignore`）。`<book>/verify_config.json` 仅作为向后兼容的回退位置。不存在 `b_numbering.json` 这种独立文件，也没有 `b_numbering` 子键——一份文件，一种 schema，编号约定与抑制集合共用同一真相源。分组由 `ordinal` 数组表达（多个具名 group = per-type，单个 uncat group = combined），无 `disable` / `separate_types` 字段；层不再被跳过，噪声一律经统一的 `ignore` 集合抑制（WARNING 门，非跳过）。

缺省/非法 → 默认 `ordinal=[{type:3, name:["uncat"], depth:3, scope:3}]`(三级CN), `strict=True`。旧整型 ordinal / `separate_types` 写法被 `from_dict` 拒绝（报 `make_config --force` 提示）。

`BookConfig` 字段（经 `ConfigLoader` 读入，挂在 `ctx.config`）：
- `ordinal`：**分组对象数组** `List[GroupConfig]`，每个元素 `{type, name, depth, scope}`（见 `config/verify_config/verify_config.py` 的 `GroupConfig`）。`type` 为编号风格码（`1`=单级，`2`=两级CN(章.号)，`3`=三级CN(章.节-号, 默认)，`4`=英文两级，`5`=罗马三级，`6`=GM(按节裸序号)，`7`=Fraleigh）；数组首元素 `type` 即 `primary_type`。`name` 为该组标签词（如 `["Theorem"]`，兜底组 `["uncat"]`）；`depth` 为编号层级数（由 `ORDINAL_DEPTH[type]` 推导，如 `4.11-5` 在 `type=3` 下为 3 级）；`group_for_label(label)` 把标签映射到其 group，匹配不到的回落 uncat 组。
- `scope`（**per-group，非顶层字段**）：末级序号的重置/连续性边界（`1`=book 全书 | `2`=chapter 章内 | `3`=section 节内）。`GroupConfig.group_prefix_len()` 取 `sp={1:0,2:1,3:2}[scope]` 并钳到 `min(sp, depth-1)`；错配不会崩溃。
- 分组粒度（per-type vs combined）：用多个具名 group（如 `Theorem`/`Lemma`/`Definition` 各一个）→ 每类独立计数器；单个 `uncat` group → 各类共享一个计数器。
- `strict`：`True`（默认）→ md 内部缺口成为 BLOCKING（不允许遗漏）；`False` → 降级为 `b_gap_warnings`。
- `ignore`：已核对确为书本身稀疏编号（非遗漏）或 OCR 噪声的条目 token 列表，如 `["Theorem 12.3","Lemma 2.5"]`。`strict` 下这些被抑制，不误报 FAIL；其余缺口仍硬阻断。填表前须对照源 PDF 核实。

组间分隔符是**内置通配符** `_SEP = [.\-–·/．－〜]`（覆盖 `.`/`-`/en-dash/中点/斜杠及全角变体），故配置**无需**指定分隔符。不同书可混用 `4.11-5` / `4.11.5` / `4·11-5`。

### 权威检测落在 .md，而非 OCR 提取
- **MD 侧（权威）**：`_md_gap_blocking` 解析 `.md` 粗体 `**...**` 标题（跳过引用型如 `**见 4.11-5**`），按 `ctx.config.ordinal` 决定的分组方案，直接做首项检验 + 连续性 BLOCKING/warn，及尾部校验 warning。
  - 正则 `_SPAN_RE = \*\*([^\n]*?)\*\*`：inner **允许出现 `*`**（如 `$X^*$` / `Weak*` 内的星号）；否则带数学的标题会被拆断、其编号解析不到 -> 误报「首项缺失 / 缺号」。
- **尾部校验的源**：提取契约 `ctx.items`（EXTRACT 层填，键形如 `定理1.1` / `4.1-5`）。`_source_item_comps_label` 用同一通配符把源条目对齐到 MD 分组方案，取每组 `smax` 与 md `last` 比对。`ctx.items` 为空（未跑提取）时尾部校验静默跳过。OCR 幻影可能抬高 `smax`：差距 `>5`（`_TAIL_GAP_CAP`）只给一条汇总提示而非逐号轰炸。
- **提取侧（辅助，不单独 hard-block）**：**由 B 自身计算**（不再依赖 `ctx.extraction_blocking`）。包含整类首项缺失检测（`_merged_category_first_missing`，仅 three-level 方案启用，扫 raw `page_*.json` 带 OCR 容错）+ over-mark 守卫（`_merged_ocr_overmark_guard`，md 标「OCR无法识别」但书已 OCR 识别 → 误标警告），均复用本层 `blocking` / `warnings` 键，不加新契约键。
  - **OCR 误报过滤**：若提取侧报「缺 X」但 X 实际已在 `.md` 中存在（OCR 漏检、agent 已正确写出），则**抑制**该 BLOCKING（折叠进 `ignored_hit`），不阻断。
  - 仅当 `.md` 与提取契约**双重确认缺失**才保留为真漏项。理由：OCR 幻影匹配（如 stray `8.6-15` 引用）会虚抬 last_num 制造假缺口，提取侧不可信为权威。

## 本阶段规则（阻断性 / 可修复）
- `blocking` 非空 -> 阻断 FAIL。`auto_fixable = False`（缺号只能 agent 补写，不能脚本修）。
- 解决优先级：先尝试补真实项（并在 `manual_overrides_ch{N}.json` 登记）；仅当确认是 OCR 乱码 / 无法修复的交叉引用才进 `ignore`(`verify_config.json`) 或用 `--ignore` CLI 标志。

## 出口条件
`blocking` 非空 → 整章 FAIL；`b_gap_warnings` / `b_tail_warnings` 仅 WARN（不阻断）。

## 相关代码（`verify/item_numbering_integrity/script/item_numbering_integrity.py`）
- `code = 'B'`，`order = 3`，`auto_fixable = False`。
- **与 EXTRACT 解耦**：B 不再消费 `ctx.extraction_blocking`；提取侧查漏 + 完整性 + `ignored_hit` 全部由 B 自行计算（数据源为 EXTRACT 供水集 `ctx.items` / `ctx.entry_keys` / `ctx.all_keys`）。EXTRACT 现仅供水、不做事。
- 编号配置由 `config/verify_config.BookConfig` 经 `ConfigLoader` 从 `<book>/_extract/verify_config.json` 一次性读出，挂在 `ctx.config` 上；B 层读 `ctx.config`，**不再各自读文件**（配置统一经 `ConfigLoader` 一次性加载）。分组由 `ordinal` 数组各 group 的 `type`/`depth`/`scope` 决定（见 `config/verify_config/verify_config.py` 的 `GroupConfig` / `ORDINAL_DEPTH`），JSON 里 `ordinal` 必填为数组。
- `ItemNumberingIntegrityLayer.run`（自包含，不依赖任何其他层）：
  1. 整章完整性（原 A 层）：`truly_missing = sorted(extracted - all_keys)`、`mentioned_only = sorted((extracted & all_keys) - entry_keys)`、`extra = sorted(all_keys - extracted)`，其中 `extracted = {it['key'] for it in ctx.items} - ignore_keys`；并算 `ignored_hit` stage1（噪声键 `extracted_raw & ignore_keys`）。
  2. 提取侧查漏（原 P2 的 Q+over-mark 逻辑）：`_merged_category_first_missing(ctx, all_keys, blocking)` + `_merged_ocr_overmark_guard(ctx, items, warnings)`（基于 raw `page_*.json` + `ctx.items` + md）。
  3. `ignored_hit` 第二段 suppression：遍历 `blocking`，若某条引用键全部 ∈ `ignore_keys`，把 `bkeys` 并入 `ctx.ignored_hit` 并从 `blocking` 剔除（最终 `ignored_hit` 完全由 B 层在本层内计算，EXTRACT 仅提供 `ctx.items` 数据源）。
  4. 算 MD 侧 `_md_gap_blocking` -> `(md_blocking, md_warnings, present_md, md_tail)`。
  5. 对提取侧 `blocking` 做「MD 存在性过滤」：被报缺的键 ∈ `present_md` 则抑制（消息号已带前导 `-`，拼接用 `sec + n`）。
  6. 合并 `blocking = filtered_extraction + md_blocking`；返回 `metadata={'blocking','warnings','b_gap_warnings','b_tail_warnings','ignored_hit','truly_missing','mentioned_only','extra'}`。
- `b_tail_warnings` 由 `report.py` 在 `B-LAYER TAIL CHECK` 段非阻断打印；`b_gap_warnings` 在 `B-LAYER NUMBERING GAP CHECK` 段打印；`truly_missing`/`mentioned_only`/`extra` 在 `TRULY MISSING` / `MENTIONED-ONLY` / `EXTRA` 段打印（B 层打印段）。

## 子流程
无独立子脚本；核心算法 `_md_gap_blocking` / `_source_item_comps_label` 在本层脚本内。

## 需 agent 手工修复（manual fix）
本层 `auto_fixable = False`（缺号只能 agent 补写，不能脚本修）。编号缺号 = 整条遗漏，
必须补写**真实项**，脚本不可臆造。

- **触发门（report.py）**：`B-LAYER BLOCKING`（strict 下硬 FAIL）/
`B-LAYER NUMBERING GAP CHECK`（非 strict 降级 WARN）/ `B-LAYER TAIL CHECK`（始终 WARN）。
- **修复步骤**：
  1. 看 `B-LAYER BLOCKING` 列出的缺口（如 `定理4.11-5` 缺失）。
  2. 回源 PDF 确认是否真漏；真漏则补写条目并在 `manual_overrides_chN.json` 登记；
确为书本身稀疏编号或 OCR 噪声则加入 `verify_config.json` 的 `ignore`（或 `--ignore`），而非编造。
  3. `B-LAYER TAIL CHECK` 仅 WARN——源尾部比 md 大属正常，除非确漏整条，否则不强行补号。
  4. 重跑 verify，确认 strict 下 `B-LAYER BLOCKING` 为空（或降级为仅 WARN）。

修复后重跑 `verify_chapter.py --all`（或单章 `<ch> <start> <end> <md> <ext>`）确认上述门为空 / 转绿。

## 字节契约键
```contract-keys
blocking
warnings
b_gap_warnings
b_tail_warnings
ignored_hit
truly_missing
mentioned_only
extra
```
