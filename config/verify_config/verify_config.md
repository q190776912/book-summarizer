# `verify_config.json` 配置说明

> 书级配置文件，位于本书 `_extract/verify_config.json`。是 `verify_chapter.py` / `flows/extract/structure/script/scan_skeleton` 的**唯一配置源**（配置缺失时 verify 硬失败，见 `config_setting` 流程 规则1；scan 仅告警安全网）。半自动生成脚本见 [`./make_config.py`](./make_config.py)（**需人工核对**，不声称自动正确）。

## 字段总览

| 字段 | 类型 | 说明 |
|------|------|------|
| `ordinal` | `List[GroupConfig]` | 必填。**分组选择器**：数组里每个对象 = 一组**共用同一条计数器**的条目标签（见下方「分组语义」核心节）。数组首元素 `type` 即 `primary_type`，自动反推编号模式与小节层级。 |
| `language` | `str` | `'cn'` / `'en'`（默认 `'cn'`）。 |
| `strict` | `bool` | 默认 `true`。 |
| `ignore` | `List[str]` | 章节忽略列表（合并旧 `known_gaps` + `ignore_keys` + `ignore_fig` 语义）。 |
| `formula` | `object?` | **仅书含公式序标时存在**：`{type, scope:2, ignore:[]}`（`depth` 由 `type` 经 `ORDINAL_DEPTH` 派生，不单独配置；见 `config_setting` 流程 规则3）。 |
| `figure` | `object?`→🔴 **`config_setting` 流程强制必现** | 图序标体例 `{"labels": ["图", "Figure", "Fig"], "components": 2}`。列出**每本书自己的**图号前缀词（图 / Figure / Fig / Scheme / Illustration …）；驱动 `extract_figures.parse_fig_label`（检测阶段裁图是否带 caption）与 `assign_figures.gather_refs`（分配阶段扫 OCR 图号）。**不再写死**中英语词表——书的图号到底长什么样由这里决定。🔴 **两种语义严格区分**：`figure` 块/`labels` 键**缺失** → 回落 `FIGURE_LABELS_DEFAULT = ["图", "Figure", "Fig"]`（向后兼容）；`figure.labels` **显式为空数组 `[]`** → 这是"**无图序标**"的**标记号**，返回真正的零匹配集（不回落默认），避免无图号书被误匹配 `Figure`/`图` 等前缀。见 `lib/figure_io.load_fig_labels`。 |
| `section_types` | `List[int]` | **逐层级**列表，从**章层级（元素 0）**排到最深的 `## §` 层级；每个元素 = 该层级 `## §` 标题携带的数字段数（ordinal depth），**不是**"章/节/小节"角色名：`1`=一级序标 `## §N`、`2`=二级序标 `## §N.M`、`3`=三级序标 `## §N.M.K`、`4`=四级序标 `## §N.M.K.L`，`0`=**无序号标**（该层级 `## §` 无数字）。深度由段数经 `SECTION_TYPE_DEPTH` 派生，**不单独配置**。**列表长度必须等于章节层级总数（章计入）**——单层级书是 `[0]`、章+无序号标小节的书是 `[0, 0]`（两个层级，**不能合并成一个**）。多数由 `primary_type` 自动反推（见 `ORDINAL_SECTION_TYPES`，标准书会 prepend 章前缀 `1`）；仅四级子小节 `1.1.1.1` 需显式覆盖 `section_types`。「章=1/节=2」只是**标准书**（章/节/小节正常嵌套）下这些段数的*典型称呼*，并非硬语义——一本书完全可以 `section_types: [1, 1, 1]`（所有层级都用一级序标），或 `section_types: [0, 0]`（章是文件 `# 第N章` 且无 `## §` 数字、章下 `## § <标题>` 小节也无序号标，如 Silverman）。缺节闸门对含 `0` 的层级按「位置/数量」比对、绝不编造 `## §N`。 |

`figure.components`（可选，默认 2）控制图号**段数**，解决不同编号体例：
- `1` = **全局整数序列**（如 Kreyszig "Fig. 1" / "Fig. 23" … 全书连续编号到 ~270）。**此类书必须声明 `"components": 1`**，否则 "Fig. 23" 因只有 1 段被正则 `{1,2}` 判为非图号，全部图沦为未命名。
- `2` = 章.图（"Fig. 3.1"），**历史默认行为**，不声明即此值，已有书不回归。
- `3` = 章.节.图（"Fig. 3.1.2"），更严格。

`lib/figure_io.build_fig_label_re(labels, components)` 据此生成对应段数的捕获组；`load_fig_label_re(out_dir)` 一次性读取 `labels`+`components`。OCR 鲁棒性：`fig_label_alt` 对含 `i` 的前缀额外生成 `[il]` 变体，容忍 "Fig."→"Flg."（i 误读为 l）这类扫描噪声。

## `ordinal` 数组：分组语义（核心）

`ordinal` 之所以是**数组**而非单个对象，唯一的理由就是——**条目标签按"是否共用同一条计数器"分组**：

- **同一个对象（`name` 数组）里的标签 = 一同升序、共用一条计数器的标签**。例如 Kreyszig 的 `Definition / Theorem / Lemma / Corollary / Example` 共用同一条"节内连续号"，所以放进同一个 `name`：`["Definition","Theorem","Lemma","Corollary","Example"]`。
- **不是一同升序、各自独立计数的标签 = 新增一个对象**，绝不塞进别的组的 `name` 里。例如 Kreyszig 的 `Problem` 是节末独立编号（自己从 1 起号、不与主类交织），必须单独成组：`{"type":3,"name":["Problem"],...}`。
- 一句话判据：**"一同升序就放一起，不是就不能放一起。"**

### 为什么分组必须准确（与编号校验的因果）

B 层（`item_numbering_integrity`）的编号连续性/缺号检查**在组内部**进行，且**不同组永不合并**：

- 正确分组（每组 = 恰好一条真实计数器）：组内编号拼成一条连续升序序列，校验能找到**真正的**缺号。
- 把两条独立计数器误放进同一组 → 它们的编号拼不到一条连续序列 → 产生**假缺号**（误报缺号）。
- 把一条计数器误拆成两组 → 每组只见序列的一部分 → 同样产生**假缺号**。

⇒ **分组的唯一正确标准 = 标签是否共用同一条计数器**，与标签叫什么名字无关。

### `name` 匹配规则（中英双语规范化）

- `name` 里的字符串是"标签类别"，经 `_canon_label` 规范化后再与条目标签比对，所以**中英文自动对齐**：`定理`↔`Theorem`、`定义`↔`Definition`、`练习`↔`Exercise`/`习题`、`评注`↔`Remark`/`注`/`Note`、`例`↔`Example`、`命题`↔`Proposition`、`公理`↔`Axiom` 等。
- 某条目标签匹配不到任何具名组的 `name` → 落入 **`uncat` 兜底组**（`uncat_group()` 回退到 `ordinal[0]`）。
- 实践中两种合法用法：
  1. **整本书只用一个计数器**（最常见）：直接一个 `uncat` 组即可，B 层把全部条目当一条序列校验连续性。
  2. **书里有多个独立计数器**（如习题单独编号）：拆成多个具名组，并保留一个 `uncat` 组兜底未显式列出的标签。

### 主类与 Remark/Exercise 的判定约定

- **主类**（定义/定理/引理/推论/命题/例/公理）在绝大多数书里**共用同一条主计数器**，因此默认同组。`make_config` 也默认把主类视为同组，并通过扫描数据来确认。
- **Remark（评注/注/Note）与 Exercise（习题/练习/Problem）**是否进主组，唯一标准仍是"是否与主类一同升序"：
  - 若它们和主类交织共用一条号 → 进主组 `name`；
  - 若它们各自独立计数（如节末习题 `Problem 6.3-2` 与正文 `Definition 6.3-2` 在同一窗口各自从 1 起号、甚至同号碰撞）→ **独立成组**。
- ⚠️ **并行独立计数器的判别信号**：同一 scope 窗口内（如同一 `章.节`）候选标签与主类**出现相同的末位号**（数字碰撞），即二者并行编号、互不连续 → 必须分拆，不可因"没各自归 1"就误判为同组。`make_config` 的 `_shares_main_counter` 正是据此决定 Remark/Exercise 是否独立成组。

### `primary_type` 与默认派生

- `primary_type` = **第一个非 `uncat` 组**的 `type`（`primary_group()`，全 `uncat` 时回退 `ordinal[0]`）。它驱动小节层级（`ORDINAL_SECTION_TYPES`）与默认语言（`ORDINAL_LANGUAGE_DEFAULT`）的反推。
- `language` 默认由 `primary_type` 派生（CN 家族→cn，EN 家族→en），显式写 `language` 可覆盖。

## GroupConfig 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | `int` (1–9) | 编号风格码，**同时编码段数（depth）与结构风格**（见下「类型表」）。`depth` 由 `type` 经 `ORDINAL_DEPTH` 派生，不再作为独立字段。 |
| `name` | `List[str]` | 该组覆盖的**标签类别**（如 `["定理","定义"]`；可含中英文，靠规范化匹配）。同组标签共用一条计数器。写 `["uncat"]` 表示兜底组。 |
| `scope` | `int` | 计数器重置边界：`1`=全书（book）/`2`=章（chapter）/`3`=节（section）。 |

### `type` 类型表（1–9）

| code | 名称 | 段数(depth) | 编号样式 | 具体示例 | 代表书/风格 |
|------|------|----------|---------|---------|-----------|
| 1 | single | 1 | 单级（仅一个连续号，无章/节位） | `定义 1` / `Theorem 1` | 单级编号书 |
| 2 | two_level | 2 | CN 两级 `N.M`（节优先；无章过滤，定理族共用一条连续号） | `定义 1.1` / `定理 2.3` / `引理 4.5`（章.号） | 中文二级标签 |
| 3 | three_level | 3 | CN 三级 `N.M.K`（默认） | `定理 1.2.3` / `定义 3.2.1` / `引理 2.4.7`（章.节.号） | 多数中文教材（如 Kreyszig 中文版） |
| 4 | en | 2 | EN 两级 `N.M`（章优先；富英文标签词） | `Theorem 6.1` / `Lemma 2.4` / `Proposition 3.7`（章.号） | 英文两级书（如 Strogatz） |
| 5 | roman | 3 | 三级 + 罗马数字章号 | `Definition I.2.3` / `Theorem II.4.1` / `Lemma III.1.2`（章.节.号，章号为 I/II/III） | 罗马章号书 |
| 6 | gm | 2 | 两级，章内本地从 1 起号（无章过滤，每章重置计数器） | `Definition 1.1` / `Theorem 1.2` / `Remark 1.5`（章.号，章内从 1 起） | Gelfand–Manin |
| 8 | vakil | 3 | EN 三级、**数字在前**（`N.M.item`，习题用字母位 `N.M.A`） | `Theorem 1.2.3` / `Exercise 1.2.A` / `Proposition 4.5.B`（章.节.号） | Vakil《Foundations of Algebraic Geometry》 |
| 9 | en3 | 3 | EN 三级、**标签在前** `C.S.N`（显式英文标签词，天然排除图号/公式号） | `Remark 1.1.1` / `Definition 2.3.4` / `Theorem 3.2.1`（章.节.号） | Lasota & Mackey《Chaos, Fractals, and Noise》 |

> `depth`（段数）一律由 `type` 经 `ORDINAL_DEPTH` 派生，上表「段数(depth)」列即为其唯一来源；配置里**不要**再写 `depth` 字段。

## 如何选定每个 group 的 `type`（判定树）

> 判定树**只用于确定各组的 `type`**（即编号风格码）；分组（哪些标签同组）由上一节"是否共用计数器"决定。配置在源语言初稿全部完成后统一生成（`make_config.py` 可半自动探测，但判定不清时以此树为准、人工核对）。翻译派生版不参与配置生成。

读 TOC / 抽一页原文，看编号长什么样？

- 编号形如 定义1.1 / 定理1.1 / 引理1.2 …（只有 章.号 两级，且 定理族共用一个连续号）→ 两级 + 双计数器（中文二级标签）→ `{"type":2,"name":["uncat"],"scope":2}`
- 编号形如 1.1-2 / 3.2-7（三级 章.节-号）→ 默认 three-level → `{"type":3,"name":["uncat"],"scope":3}`（CN 三级书通常设 `scope:3`，不要用 make_config 默认的 `scope:2`）
- 英文书编号形如 Theorem 1.2 / Lemma 3.4（EN 两级，无章号位）→ `{"type":4,"name":["uncat"],"scope":2}`
- 罗马数字章号 I.2.3 / II.1.1 …（章号是 I/II/III…）→ `{"type":5,"name":["uncat"],"scope":3}`
- Gelfand–Manin 风格 §2 标题 + 条目从 1 起号（gm，两级、章内本地）→ `{"type":6,"name":["uncat"],"scope":2}`
- 节基 EN 两级（如 Fraleigh：按节编号、首数是节号、无章号位）→ **并入 type 4**，并设 `"chapter_first": false` + `"section_scoped": true`：`{"ordinal":[{"type":4,"name":[...合并后的文本标签...],"scope":2}],"chapter_first":false,"section_scoped":true,"language":"en"}`。`chapter_first:false` 让抽取/结构/校验把 key 首数当作「节」而非「章」；`section_scoped:true` 让抽取器额外捕获「数字在前」标题（`26.4 Lemma`）与编号图表（`Table 1.20` / `Figure 3.6`）。
- Vakil 风格 EN 三级、数字在前（如 `1.2.3` 条目、`1.2.A` 习题）→ `{"type":8,"name":["uncat"],"scope":3}`
- 不确定 / 跑 verify 出现负偏移的 "1.x-y"（x、y 比真实条目小很多）→ 几乎肯定是三级正则误吃公式/枚举 → 先用 `verify_chapter.py`（消费 `book_structure.json`）或人工核对确认真实条目齐全；确为两级书设 `type:2`，确为三级书但有几个真·OCR 噪点用 `--ignore` 登记（写入 `_extract/ignore_ch{N}.json`，附 `ignore_ch{N}.md` 举证）

> 以上为单组（combined，单个 `uncat` group）最简写法。若某书每类条目独立计数（如 Koopman 的 Theorem/Lemma/Definition/… 各自从 1 起号），须把 `ordinal` 拆成多个具名 group（每个 label 一类），并保留一个 `uncat` 兜底组，例如 `{"ordinal":[{"type":4,"name":["Example"],"scope":2},{"type":4,"name":["Theorem"],"scope":2},…,{"type":4,"name":["uncat"],"scope":2}]}`（见 `verify/item_numbering_integrity/item_numbering_integrity.md`）。

## `from_dict` 严格校验

- 旧整型 `{"ordinal": int}` / 字符串 `ordinal` **直接拒绝**，提示重跑 `make_config --force`（`exit 2`）。
- 逐组校验：`type`∈{1,2,3,4,5,6,8,9}（`depth` 由 `type` 派生，不再单独校验；type 7 已并入 type 4 + `chapter_first:false`）、`scope`∈{1,2,3}，否则 `exit 2`。
- 无 `uncat` 组不自动追加、不警告（`uncat` 是显式决策；无 `uncat` 时 `uncat_group()` 回退 `ordinal[0]`）。

## 顶层字段：`chapter_first` / `section_scoped`

这两个字段**只在 EN 两级（type 4）书需要区分「章基 / 节基」时**才出现；其余书保持默认即可。

- **`chapter_first`（bool，默认 True）**：EN 两级编号下，条目 key 的首个数字究竟是**章**还是**节**。
  - `true`（默认，如 Strogatz / Koopman）：`"Theorem 6.1"` = 第 6 章第 1 条，段号取 `"6.1"`。
  - `false`（节基书，如 Fraleigh）：`"Theorem 8.1"` = §8 第 1 条，首数即「节号」，段号取 `"8"`。
  - 影响抽取（`extract_items_en` 的跨章前向引用过滤）、结构（`build_structure._section_of_key` 派生段号）、校验（`check_structure_completeness` 的 canon 解析）。
- **`section_scoped`（bool，默认 False）**：节基 EN 书（即 `chapter_first:false` 的 type 4）开启；让抽取器额外捕获**数字在前**标题（`26.4 Lemma`、`24.2 Corollary`）与**编号图表**（`Table 1.20` / `Figure 3.6`），因为它们只在这种来源里成批出现。章基 EN 书保持 `false`（其来源不这么印，开启也不会多抓，但为明确语义不默认开）。

> `make_config.py` 在扫到 `chapter_map.json` 声明 `"chapter_first": false` 的 type-4 书时，会自动写出这两个字段（collapse 文本标签为单组合并计数器）。

## JSON 示例

**多独立计数器书（Kreyszig，正确分组范本）** — 主类共用一条节内计数器，`Problem` 独立成组；`Axiom/Note/Proposition/Remark` 无真实标题或纯噪声，不进配置：

```json
{
  "ordinal": [
    {"type": 3, "name": ["Definition", "Theorem", "Lemma", "Corollary", "Example"], "scope": 3},
    {"type": 3, "name": ["Problem"], "scope": 3}
  ],
  "strict": true,
  "language": "en",
  "formula": {"type": 1, "scope": 3, "ignore": []}
}
```

CN 三级（含公式序标，单组最简写法）：

```json
{
  "ordinal": [{"type": 3, "name": ["uncat"], "scope": 2}],
  "strict": true,
  "language": "cn",
  "formula": {"type": 4, "scope": 2, "ignore": []}
}
```

EN 两级：

```json
{
  "ordinal": [{"type": 4, "name": ["uncat"], "scope": 2}],
  "strict": true,
  "language": "en"
}
```

指定图序标体例（本书图号用 "Fig." / "图"）：

```json
{
  "ordinal": [{"type": 3, "name": ["uncat"], "scope": 2}],
  "language": "cn",
  "figure": {"labels": ["图", "Fig"], "components": 2}
}
```

全局整数图号书（如 Kreyszig，图号 "Fig. 1" … "Fig. 270" 连续）：

```json
{
  "ordinal": [{"type": 3, "name": ["uncat"], "scope": 2}],
  "language": "en",
  "figure": {"labels": ["Fig", "Figure"], "components": 1}
}
```

无图序标（🔴 显式标记号，禁止回落默认）：

```json
{
  "ordinal": [{"type": 3, "name": ["uncat"], "scope": 2}],
  "language": "cn",
  "figure": {"labels": []}
}
```

> 空数组 `[]` 是"本书确实没有任何图号前缀"的**标记号**：下游（`extract_figures` / `assign_figures` / E 层 `fig_cap_re`）据此返回真正的零匹配，而**不会**回落到默认 `["图","Figure","Fig"]` 去误匹配正文里碰巧出现的 `Figure`/`图` 等词。与"`figure` 字段缺失→回落默认"语义严格区分。

## 附录：小节标题 `§` 的 OCR 漏识诊断（D 层）

本项目实测到的现象（D 层 `section_continuity` 统一容忍，机制见 `verify/section_continuity/section_continuity.md`）：

| 真值 | OCR 误读 | 出现位置 | 处理 |
|---|---|---|---|
| §1.6 | `81.6` | Ch1 尾部 | D 层 `section_continuity`（`D_SEC_HEAD_A`）统一容忍 §/S/8 OCR 变形 |
| §2.5 | `S2.5` | Ch2 | D 层 `section_continuity`（`D_SEC_HEAD_A`）统一容忍 §/S/8 OCR 变形 |
| 普通 § | `§ 6.6`（中间有空格） | 多章 | D 层 `D_SEC_HEAD_C` 处理短块 |

> 注意：D 层 `section_continuity` 的 `sec_re`（`D_SEC_HEAD_A` 等）只容错 `§/S/8` 三种开头；若某节在 `book_structure.json` 扫描结果中缺失，先用 `--verbose` 看原始文本，再人工确认是否又是一种新的 OCR 变形。
