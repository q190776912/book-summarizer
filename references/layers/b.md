# B 层 — 缺号检测（忠于原文）

> 本文件是 **B 层** 的唯一权威详情。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verification.md`](../verification.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。

## 一句话目的
检测 agent 写出的 .md 交付物里「条目编号缺号」，让 agent 来补；中段不存在合法跳号，漏了就是漏了。

## 宗旨（B 层本分）
对任意一组（per-type 下的某一类、按本书编号习惯分组）的编号序列必须完整：
- **首项检验**：序列应从 1 开始；不从 1 开始 => 首项缺失（在 `strict` 下 BLOCKING，否则 warning）。
- **连续性**：组内 `[first, last]` 必须连续；中间缺号 => 真漏项（在 `strict` 下 BLOCKING，否则 warning）。
- **尾部校验**：取 .md 组内最大号 `last`；若**提取契约（源, `ctx.items`）同组最大号 `smax > last`** 且中间号源有而 .md 无 => 疑似尾部漏项（**始终非阻断**，仅 `b_tail_warnings` 提示，请人工核实章/节是否即止）。

三类输出（见「字节契约键」）：
- `blocking`：严格模式下 md 内部首项/连续性缺口（硬 FAIL，auto_fixable=False）。
- `b_gap_warnings`：非严格模式（`strict:false`）下同样的缺口，降级为非阻断警示。
- `b_tail_warnings`：尾部校验，始终非阻断。

## 分组（按书的编号习惯，来自 `BNumberingConfig`）
配置由 B 层脚本**直接从 `<book_dir>/_extract/` 读 JSON**（不依赖任何编排层透传）。

**单一配置文件**：`<book_dir>/_extract/verify_config.json`（扁平，**同时**存放通用 `disable` 与 B 编号字段 `levels/scope/separate_types/strict/known_gaps`）。`<book_dir>/verify_config.json` 仅作为向后兼容的回退位置。不存在 `b_numbering.json` 这种独立文件，也没有 `b_numbering` 子键——一份文件，一种 schema，编号约定与层禁用共用同一真相源。

缺省/非法 → 默认 `levels=2, scope=chapter, separate_types=1, strict=True`。

`BNumberingConfig` 字段（用户框架）：
- `levels`：数字路径的总级数（1 / 2 / 3）。`5`=1，`4.1`=2，`4.11-5`=3。
- `scope`：末级序号的重置/连续性边界（`book` 全书 | `chapter` 章内 | `section` 节内）。对 k 级编号，有意义的前缀是前 `k-1` 级；其他取值被 `group_prefix_len()` 上限钳到 `levels-1`，错配不会崩溃。
- `separate_types`：编号粒度（**整数，非布尔**，预留更细分组）。判定必须用 `==` 对比具名常量 `SEP_COMBINED` / `SEP_PER_TYPE`，**严禁 `>=`**：`0`(SEP_COMBINED) → 各类共享一个计数器（combined，组键 = `前缀`）；`1`(SEP_PER_TYPE) → 每类（定理/定义/引理/…）独立计数器（per-type，组键 = `前缀:类型`）；`2+` 预留（更细分组），**当前未定义**——`from_dict` 拒绝未知值并回退 `SEP_COMBINED` + 报警，新增类别时必须显式写分支，绝不静默继承 per-type 行为。
- `strict`：`True`（默认）→ md 内部缺口成为 BLOCKING（不允许遗漏）；`False` → 降级为 `b_gap_warnings`。
- `known_gaps`：已核对确为书本身稀疏编号（非遗漏）的条目 token 列表，如 `["Theorem 12.3","Lemma 2.5"]`。`strict` 下这些被抑制，不误报 FAIL；其余缺口仍硬阻断。填表前须对照源 PDF 核实。

组间分隔符是**内置通配符** `_SEP = [.\-–·/．－〜]`（覆盖 `.`/`-`/en-dash/中点/斜杠及全角变体），故配置**无需**指定分隔符。不同书可混用 `4.11-5` / `4.11.5` / `4·11-5`。

## 权威检测落在 .md，而非 OCR 提取
- **MD 侧（权威）**：`_md_gap_blocking` 解析 .md 粗体 `**...**` 标题（跳过引用型如 `**见 4.11-5**`），按 `BNumberingConfig` 分组，直接做首项检验 + 连续性 BLOCKING/warn，及尾部校验 warning。
  - 正则 `_SPAN_RE = \*\*([^\n]*?)\*\*`：inner **允许出现 `*`**（如 `$X^*$` / `Weak*` 内的星号）；否则带数学的标题会被拆断、其编号解析不到 -> 误报「首项缺失 / 缺号」。
- **尾部校验的源**：提取契约 `ctx.items`（EXTRACT 层填，键形如 `定理1.1` / `4.1-5`）。`_source_item_comps_label` 用同一通配符把源条目对齐到 MD 分组方案，取每组 `smax` 与 md `last` 比对。`ctx.items` 为空（未跑提取）时尾部校验静默跳过。OCR 幻影可能抬高 `smax`：差距 `>5`（`_TAIL_GAP_CAP`）只给一条汇总提示而非逐号轰炸。
- **提取侧（辅助，不单独 hard-block）**：`extract_layer` 产出的 `ctx.extraction_blocking`（边界 / 内部序列缺口、整类首项缺失 = 并入 B 的 Q 逻辑、over-mark 守卫等）。
  - **OCR 误报过滤**：若提取侧报「缺 X」但 X 实际已在 .md 中存在（OCR 漏检、agent 已正确写出），则**抑制**该 BLOCKING（折叠进 `ignored_hit`），不阻断。
  - 仅当 .md 与提取契约**双重确认缺失**才保留为真漏项。理由：OCR 幻影匹配（如 stray `8.6-15` 引用）会虚抬 last_num 制造假缺口，提取侧不可信为权威。

## 阻断性 / 可修复
- `blocking` 非空 -> 阻断 FAIL。`auto_fixable = False`（缺号只能 agent 补写，不能脚本修）。
- 解决优先级：先尝试补真实项（并在 `manual_overrides_ch{N}.json` 登记）；仅当确认是 OCR 乱码 / 无法修复的交叉引用才进 `--ignore` / `known_gaps`。

## 字节契约键（legacy dict，供 `DEFAULT_RESULT` / `print_result` 同步）
```contract-keys
blocking
b_gap_warnings
b_tail_warnings
ignored_hit
```

## 实现（`verify/layers/b_layer.py`）
- `code = 'B'`，`order = 3`，`auto_fixable = False`。
- 数据源：`ctx.extraction_blocking`（EXTRACT 阶段填）+ MD 侧 `_md_gap_blocking` 结果 + 源 `ctx.items`（尾部校验）。
- 编号配置由 `lib.config.BookConfig` 经 `ConfigLoader` 从 `<book>/_extract/verify_config.json` 一次性读出，挂在 `ctx.config` 上；B 层与提取层都读 `ctx.config`，**不再各自读文件**（旧的 `load_for_md` 文件 IO 已删除）。编号级数由整数 `ordinal` 决定（见 `lib/config.py` 的 `ORDINAL_DEPTH`），JSON 里可不写。
- `BLayer.run`：
  1. `ignored_hit` **第二段** suppression：遍历 `blocking`，若某条引用键全部 ∈ `ignore_keys`，把 `bkeys` 并入 `ctx.ignored_hit` 并从 `blocking` 剔除（最终 `ignored_hit` 由 B 回写，覆盖 EXTRACT 的 stage1）。
  2. 算 MD 侧 `_md_gap_blocking` -> `(md_blocking, md_warnings, present_md, md_tail)`。
  3. 对提取侧 `blocking` 做「MD 存在性过滤」：被报缺的键 ∈ `present_md` 则抑制（消息号已带前导 `-`，拼接用 `sec + n`）。
  4. 合并 `blocking = filtered_extraction + md_blocking`；返回 `metadata={'blocking','b_gap_warnings','b_tail_warnings','ignored_hit'}`。
- `b_tail_warnings` 由 `report.py` 在 `B-LAYER TAIL CHECK` 段非阻断打印；`b_gap_warnings` 在 `B-LAYER NUMBERING GAP CHECK` 段打印。
