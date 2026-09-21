# ordinal_styles.py（ordinal 编号体例类层级）

把「书籍条目编号体例」从「一个 `type` 整数 + 一堆平行字典 + `keys_in_md` 里巨大的
`if t == …` 分发」改写成**类层级**：每一种编号体例是一个类，自己持有 `code`、
`depth`、正则判别式与判断方法。调用方拿到的是**风格实例**，可直接 `.extract()`，
不必再拿裸 int 反查字典。

## 定位与范围

- **pilot，未接管线**。本模块实现 **code 0 / 1 / 2 / 3 / 8 / 12 / 13 / 14**（type 12 = `OrdinalHum` Humphreys 字母序标，label 可在字母前后；见下「派生类」表与 `OrdinalHum` 小节）。
  `lib/key_parse.py::keys_in_md` 仍走旧的 `if t == …` 分发，`config/verify_config/make_config.py`
  的页扫探测也未改。其余 code（4、9–11）尚无对应子类，调用 `OrdinalStyle.get(code)`
  会抛 `KeyError`。
- **两套能力，来源不同、互不解耦混淆**：
  - **识别类型**（这本书是几级编号？）→ `judge(page=True)` / `classify` / `detect_style`，
    吃 **page 纯文本**形态；
  - **md 抽键**（已知类型，从 md 行抽规范键）→ `extract`，吃 **md 加粗**形态。
- 本模块**不**负责从整块 page 文本里定位条头（位置护栏、交叉引用过滤、计数器分组
  仍归 `make_config`）。它消费的是**已抽出的条头串**。

## 两套形态：page 纯文本 vs md 加粗

| 形态 | 正则属性 | 消费方 | 输入样例 |
|---|---|---|---|
| **page 纯文本**（无 `**`） | `page_entry_re` | `judge(page=True)` / `classify` / `detect_style` | `定义1.1.1`、`1.1 定义` |
| **md 加粗**（带 `**`） | `entry_re` | `extract` / `judge(page=False)` | `**定义1.1.1**`、`**1.1.1 引理**` |

- `match_entry(text, page=True)` 会**先剥掉文本里的 `**`** 再匹配，所以同一个
  `judge(page=True)` 既能吃 page OCR 纯文本、也能吃 md 加粗条头。
- 两套正则的**段数、双向、标签感知、后缀**规则完全一致，只有「是否要求 `**` 包裹」不同。
- `extract` **必须**喂 md 行（`**…**`）；喂裸文本恒返回 `None`。

## 基类 `OrdinalStyle`

### 子类必须声明的类属性

| 属性 | 含义 | 校验 |
|---|---|---|
| `code` | `ORDINAL_*` 整数 | 必须 ∈ `verify_config.ORDINAL_CODES` |
| `depth` | 数字分量段数 | 必须 == `lib.numbering.ORDINAL_DEPTH[code]` |
| `name` | 短风格名 | 必须 == `verify_config.ORDINAL_NAME[code]` |
| `entry_re` | md 加粗条头判别式（供 `extract`） | — |
| `page_entry_re` | page 纯文本判别式（供识别类型） | — |
| `prose_re` | 散文 / 交叉引用形态判别式（无加粗） | 预留；**本模块的方法当前不使用它** |

**定义即校验**：`__init_subclass__` 在类定义时就与权威表交叉校验上面三行
（`code` ∈ `ORDINAL_CODES`、`depth` == `ORDINAL_DEPTH[code]`、`name` == `ORDINAL_NAME[code]`），
任一不符立即抛 `ValueError`；重复注册同一 `code` 抛 `TypeError`。
→ **三张表（`ORDINAL_CODES` / `ORDINAL_DEPTH` / `ORDINAL_NAME`）与本层级永不允许漂移**。

**刻意不设的类属性**（见「规则」）：
- **没有 `language`** —— 「这个风格吃哪些标签」完全由正则词表决定，而词表本就中英
  混排，语言轴被判别式自然吸收。
- **没有 `scope`** —— 计数器重置窗口是**数据派生量**，不是 type 的属性。

### 实例属性

`__init__(self, scope=None)`：`scope` 为**实例属性**，`None` = 未绑定（待 `detect_scope`
从数据派生）；非 `None` = 调用方显式给定（`from_type_scope`）。

### 方法一览

| 方法 | 作用 | 返回 |
|---|---|---|
| `get(code)` | 工厂：取 `code` 的 fresh 实例（`scope=None`） | 实例；未实现 code → `KeyError` |
| `from_type_scope(type_code, scope)` | 配置驱动构造：绑定显式 `scope` | 实例；`scope`∉{1,2,3} → `ValueError`；type 未实现 → `KeyError` |
| `registered_codes()` | 已注册 code 列表 | `list[int]` |
| `match_entry(text, *, page=False)` | 底层匹配 | `re.Match` / `None` |
| `judge(text, *, page=False)` | 是否含本风格条头 | `bool`（**code 0 覆盖为 `judge(text)`，无 `page`**） |
| `extract(text)` | 抽首个条头的规范键（走 `entry_re`） | `str` / `None` |
| `canon_key(*parts)` | 由数字分量组规范键 | `str`（子类实现） |
| `classify(text)` | 单行判定风格（按 `depth` 降序，更具体优先） | 实例 / `None` |
| `detect_style(headings)` | 语料级判定主导风格（specificity-first 投票） | 实例 / `None` |
| `detect_scope(keys)` | 由规范键派生计数器重置窗口 | `1` / `2` / `3` |
| `analyze(headings, keys=())` | 形式 + scope 一次给出 | `OrdinalProfile(style, scope)` |

`SCOPE_BOOK=1`、`SCOPE_CHAPTER=2`、`SCOPE_SECTION=3`（来自 `verify_config`）。

## 派生类

| code | 类 | depth | name | 条头形态 | 规范键 |
|---|---|---|---|---|---|
| 0 | `OrdinalUnnumbered` | 0 | `unnumbered` | 无数字 | 无（`extract` 恒 `None`） |
| 1 | `OrdinalSingle` | 1 | `single` | `**定理2**` / `**2 定理**` | `定理2` |
| 2 | `OrdinalTwoLevelCN` | 2 | `two_level` | `**定义1.1**` / `**1.1 定义**` | `定义1.1` |
| 3 | `OrdinalThreeLevelCN` | 3 | `three_level` | `**定理1.1.1**` / `**1.1.1 定理**` | `1.1-1` |
| 8 | `OrdinalVakil` | 3 | `vakil` | `**Exercise 2.3.A**` / `**Theorem 2.3.B**`（标签在前，第三维**字母**） | `练习2.3-A` / `定理2.3-B` |
| 12 | `OrdinalHum` | 2* | `hum` | `**Corollary A**` / `**A Corollary**`（label 可在字母前后，字母序标） | `推论 A` / `定理 A` |
| 13 | `OrdinalApp` | 3 | `app` | `**Definition A.1.1**` / `**A.1.1 Definition**` / 裸号 `**A.1.5**` | `定义A.1-1` / `A.1-5` |
| 14 | `OrdinalApp2` | 2 | `app2` | `**Theorem B.2**` / `**B.2 Theorem**` | `定理B.2` |

### `OrdinalUnnumbered`（code 0）
无数字判别式：`entry_re` / `page_entry_re` 均为 `None`，`judge` 恒 `False`、
`extract` 恒 `None`、`canon_key` 抛 `NotImplementedError`。
无编号条目靠「其它编号风格都不中」判定，`classify` / `detect_style` 跳过 code 0。
⚠️ 它**覆盖**了 `judge`，签名为 `judge(self, text)` —— **不接受 `page=` 关键字**
（基类 `judge(text, *, page=False)` 的唯一例外；因为无 `**` 可剥，两套形态对它等价）。

### `OrdinalSingle`（code 1）
单个数字分量。双向（标签在前 / 序标在前）。规范键 = 规范中文标签 + 数字。
标签经 `verify_config._canon_label` 归一（`示例`→`例`、`注释/注/注记/评注`→`评注`）。

### `OrdinalTwoLevelCN`（code 2）
节.项两段。双向。规范键 = 规范标签 + `.` 连接两段。
标签词表复用 `_LABEL_ALT`（= `COMBINED_LABEL_KINDS` 全集），不再用手写子集。

### `OrdinalThreeLevelCN`（code 3）
三段，**必须带条目标签**（定义/定理/引理…）。双向。
规范键 = `normkey(a.b.c)` → 纯数字 `1.3-4`，**不带标签前缀**（兼容中文三级书
「契约键纯数字、标签另存 `manifest.tags`」的现状）。
因此纯数字加粗行 `**1.1.1**` 是**节标题**，本类不匹配（`judge=False`、`extract=None`）。
⚠️ 🔴 标签词表 = `_LABEL_ALT`（= 全量 `COMBINED_LABEL_KINDS`，38 词），**与 type 1/2 完全相同**。
用户 2026-09-21 明确：type 3 与 type 2「按标签判断」的方式保持一致——三级条头必须带**条目标签**，
词表口径不做额外收窄。故 `**练习1.2.3**` / `**Exercise 2.3.1**`（选项 B 已进 `COMBINED`）与
`**Application 1.2.3**` / `**条件1.2.3**` / `**Variation 1.2.3**` / `**Porism 1.2.3**` **一并收**
（均落入 `COMBINED_LABEL_KINDS`）。仅**纯数字** `**1.2.3**` 与中文节号 `**第1.2.3节**` 在
label-aware redesign 下仍刻意不收（节标题非条目）；旧 `keys_in_md` 的 type 3 走**标签无关**的
`regexlib.ENTRY_RE`，这两类**也收**（`1.2-3`），故仍属**减法**，登记为「有意偏差」第 6 条（仅余标签无关真值）。
🔴 注：type 1/2/3/8/12/13/14 **全部共用同一 `_LABEL_ALT`（= `COMBINED_LABEL_KINDS`，38 词）**——2026-09-21「标签词统一」已废弃 `_LABEL_ALT_EX` / `_APP_LABEL_ALT` 两别名常量；仅附录类（13/14）在词表之上额外挂 `_APP_PLURAL`（`(?:es|s)?`）以收复数附录头（`Examples A.1.3`）。

### `canon_key` 各子类签名（基类是 `canon_key(*parts)`）

| 类 | 签名 |
|---|---|
| `OrdinalSingle` | `canon_key(label, num, suffix='')` |
| `OrdinalTwoLevelCN` | `canon_key(label, sec, num, suffix='')` |
| `OrdinalThreeLevelCN` | `canon_key(a, b, c, suffix='')` |
| `OrdinalVakil` | `canon_key(label, ch, sec, letter, suffix='')` |
| `OrdinalApp` | `canon_key(label, letter, sec, num, suffix='')` |
| `OrdinalApp2` | `canon_key(label, letter, num, suffix='')` |

`suffix` 原样追加到规范键末位（字母后缀 / `*`），默认空串。

### `OrdinalVakil`（code 8，EN 三级·第三维字母序标）

🔴 **用户口径**（覆盖 `verify_config` 里 `ORDINAL_VAKIL` 的旧描述）：

- 条头 = **标签在前**的 ``Label C.S.A`` —— 章 . 节 . **字母**序标；
- **第三维必须是字母，不能是数字**；
- 序标在前（`2.3.A Exercise`）**不属于**本类。

- 形态：`**Exercise 2.3.A**` / `**Theorem 2.3.B**` / `**Lemma 1.2.C**`；
  原书尾点（`**Exercise 2.3.A.**`）不影响；小写字母序标也收、归一为**大写**。
- 规范键 = 规范中文标签 + 章号 + `.` + 节号 + `-` + **大写**字母序标 → `练习2.3-A`。
  键里**保留标签**（同节的 `Theorem 2.3.A` 与 `Exercise 2.3.A` 是两条不同条目，
  纯数字键会碰撞），这与 type 3 的纯数字键 `1.3-4` 刻意不同。
- 标签词表用 **`_LABEL_ALT`**（= `COMBINED_LABEL_KINDS`，38 词）：Vakil 的
  字母序标条目绝大多数是 **Exercise**，而 `Exercise` 已在 2026-09-21「选项 B」并入 `COMBINED_LABEL_KINDS`，故无需独立词表。
  ⚠️ **复数 `Exercises` 刻意不收** —— `_canon_label('Exercises')` 无规范映射，收进来
  只会产出非规范键。
- 🔴 段数独立：只认「标签 + 数字 . 数字 . **字母**」。两级 `Exercise 2.3` → type 2、
  三段数字 `Theorem 2.3.4` → type 3、字母章位 `Exercise A.1.1` → type 13，
  本类**均不认**；反过来 `Exercise 2.3.A` 的**数字尾巴** `Exercise 2.3` 也不得被
  type 2 截走（靠 `_TAIL_GUARD` 的第三条断言 `(?!SEP[A-Za-z])`）。
- `_key_to_tuple` 覆写为 `_vakil_key_to_tuple`（见下）。

`_key_to_tuple(key)`（`@staticmethod`，供 `detect_scope` 用）把规范键折成纯数字分量元组
（`1.1-1` → `(1,1,1)`、`定义1.1` → `(1,1)`、`定理2` → `(2,)`）：忽略标签前缀与分隔符，
只 `re.findall(r'\d+')`；无数字则返回 `None`。**附录两类与 type 8 覆写它**（见下）。

### `OrdinalApp`（code 13，附录字母章位三级）

- 形态：字母章位 + 段.号两段数字。`Definition A.1.1` / `Theorem A.6.2`（Weibel 附录）；
  裸号条目（原书只印编号）`**A.1.5**`；序标在前 `**A.1.1 Definition**`。
- 规范键 = 规范标签 + **大写**字母章位 + `.` + 节号 + `-` + 条目号 → `定义A.1-1`；
  裸号键无标签前缀 → `A.1-5`。字母章位在键里**保留为字母**（与 type 3 的纯数字键
  `1.3-4` 刻意不同，避免与正文键碰撞）。
- 🔴 段数独立：**只认「字母 + 两段数字」**。两段体例（`Theorem B.2`）归 type 14。
  ⚠️ 旧 `keys_in_md` 的 type 13 分支有一段「两段宽容回退」（`ENTRY_RE_APP2_C`），
  那是 type 14 落地前的历史 config 兼容，**本层级刻意不继承**——它与「段数独立」
  硬要求直接冲突。
- `_key_to_tuple` 覆写为 `_app_key_to_tuple`（见下）。

### `OrdinalApp2`（code 14，附录字母章位两段）

- 形态：字母章位 + **一段**数字，无节段。`Theorem B.2` / `Example A.5` / `Exercise B.4`
  （Lee ISM 2e 附录 A–D 实测）；序标在前 `**A.1 Definition**`。
- 规范键 = 规范标签 + 大写字母章位 + `.` + 条目号 → `定理B.2`。
- 🔴 段数独立：只认「字母 + 一段数字」，靠 `(?!SEP\d)` 护栏把 `A.1.1` 排除给 type 13。
- 裸号两段（`**D.1**`）与公式号 / 小节标题同形，旧管线与本类**均不收**。

### 附录两类共享的 `_app_key_to_tuple`

`_key_to_tuple = staticmethod(_app_key_to_tuple)`。基类用 `re.findall(r'\d+')` 会把
**字母章位整个丢掉**（`定义A.1-1` 与 `定义B.1-1` 都折成 `(1,1)`）→ 「换字母章、号回 1」
这一重置信号消失 → scope 被误判成书级。附录体例的**首分量是字母**，折算成序号
（`A`→1、`B`→2…）后再参与重置判定：

- `定义A.1-1` → `(1,1,1)`；`定理B.2` → `(2,2)`；`定义C.2-3` → `(3,2,3)`。
- 对齐 make_config 的口径：首分量与章键 `'A'/'B'…` 比对。

### type 8 的 `_vakil_key_to_tuple`

同理但方向相反：**末位**是字母序标，基类的 `re.findall(r'\d+')` 会把它整个丢掉
（`练习2.3-A` 与 `练习2.3-B` 都折成 `(2,3)`）→ 「换条目、字母回 A」的重置信号消失。
折成序号后参与重置判定：`练习2.3-A` → `(2,3,1)`、`练习2.3-C` → `(2,3,3)`、
`练习10.2-B` → `(10,2,2)`。

### `OrdinalHum`（code 12，Humphreys 字母序标）

🔴 **用户口径（覆盖 legacy `ENTRY_RE_HUM`「只收 label 在前」）**：label + **单字母**序标，
label 可在字母前后 —— `**Corollary A**` ↔ `**A Corollary**` 归一为同一规范键 `推论 A`。

- 形态：`**Corollary A**` / `**A Corollary**` / `**Lemma B**` / `**B Lemma**` /
  `**定理 A**` / `**A 定理**`；规范键 = 规范中文标签 + 空格 + **大写**字母序标
  （`推论 A` / `定理 A` / `引理 B`），与 legacy `f"{label} {letter}"` 同形。
- 🔴 **段数独立**：只认「label + 单字母」。**数字序标**（`**Example 1**` → type 1）、
  **纯 label**（`**Theorem**`，零数字，留待 legacy type-12 配置分支）、**字母章位+数字**
  （`**Definition A.1.1**` → type 13/14）、**数字.数字+字母**（`**Exercise 2.3.A**`
  → type 8）**均不收**，避免 `classify` 把单级 EN 书误判成 type 12。
- `judge(page=True)` 与 `extract` **自洽**：`_ENTRY_RE_HUM` 终端用 `[^*]*\*+`
  （与 type 8 同），故 `**Corollary A.**` 这类尾点也能抽键；`extract` 不收裸号
  （无数字/字母序标则 `None`）。
- `_key_to_tuple` 覆写为 `_hum_key_to_tuple`：末位单字母折序号（A→1, B→2）→ `(1,)`，
  供 `detect_scope` 判重置（章级）。⚠️ 类声明 `depth = ORDINAL_DEPTH[12] = 1`（单字母单维，与 `_key_to_tuple` 单分量一致），
  但规范键实际只有「字母」一维，`_key_to_tuple` 折成**单分量**，`detect_scope` 按数据长度
  判定（不依赖类属性 `depth`）。Humphreys 同章内定理/引理/推论等通常共用一个字母序标序列，
  丢弃 label 后按字母判重置符合该书体例；若某书各 label 独立编号，则须在真值侧另行区分。
- 派生类表的 type 12 `depth` 声明为 1（单字母单维），有效维度即 1（仅字母），
  仅作元数据/投票 tiebreaker，不影响 `detect_scope`。

## 共享正则原语

| 原语 | 定义 | 作用 |
|---|---|---|
| `SEP_TIGHT` | `[.\-–·/．－〜_~]`（来自 `lib.regexlib`；2026-09-21 补 ASCII `~` 与 OCR 下划线 `_`） | 数字分量分隔符 |
| `_LABEL_ALT` | `COMBINED_LABEL_KINDS` 去重后**按长度降序**拼接 | 标签词表单一真源；降序保证 `示例`/`注记` 不被前缀 `例`/`注` 抢匹配 |
| `_SUFFIX_RE` | `r'(?:\s*([a-z]+)|(\*(?=\*\*)))?'` | 末位后缀 |
| `_LABEL_ALT` | `COMBINED_LABEL_KINDS` 去重后按长度降序 | **词表唯一真源**（type 1/2/3/8/12/13/14 全部共用，38 词） |
| `_APP_PLURAL` | `r'(?:es|s)?'` | 附录标签**复数**（`Examples A.1.3`），对齐 make_config 页扫 |
| `_TAIL_GUARD` | `r'(?!\d)'` + `r'(?!\s*' + SEP_TIGHT + r'\s*\d+)'` + `r'(?!' + SEP_TIGHT + r'[A-Za-z])'` | 段数独立性：末位后不能再接「数字 / 分隔符+数字 / **紧贴的分隔符+字母**」 |
| `_LEAD_GUARD` | `r'(?<!\d' + SEP_TIGHT + r')' + r'(?<!(?<![A-Za-z])[A-Za-z]' + SEP_TIGHT + r')'` | 段数独立性：首位前不能是「数字+分隔符」；**也不能是「独立单字母+分隔符」** |

**`_LEAD_GUARD` 的第二条断言（附录字母章位）**：原只拦「数字 + 分隔符」，拦不住附录
字母章位——`A.1.1 Definition` 的数字尾巴 `1.1 Definition` 会被 type 2 的序标在前分支
认成二级头、`B.2 Theorem` 的 `2 Theorem` 会被 type 1 认成一级头。追加的断言用内层
`(?<![A-Za-z])` 限定「**独立**单字母 + 分隔符」，故 `cf.` / `No.` / `Fig.` 这类多字母
缩写不受影响。

**`_TAIL_GUARD` 的第三条断言（type 8 的字母序标）**：前两条只拦「数字」，拦不住
字母尾巴 —— `Exercise 2.3.A` 的 `Exercise 2.3` 会被 type 2 认成二级头。追加
`(?!SEP[A-Za-z])` 后即被拦住。刻意**不允许分隔符与字母之间有空格**，故
`Definition 1.1. Some text`（句点 + 空格 + 大写词）这类普通句子不受影响。三条断言
均为**零宽**，不新增捕获组。

**末位后缀**：字母后缀 `[a-z]+`（允许前导空格，如 `12.1.1 a`）；星号后缀
`\*(?=\*\*)` —— **须后随 `**`（整体 `***`）才算后缀**，以此与加粗闭合的纯 `**` 区分。
`**定理12.1.1**` → `12.1-1`（无 `*`）；`**定理12.1.1***` → `12.1-1*`。
后缀原样追加到规范键末位；`detect_scope` 只读 `\d+`，后缀被忽略。

**十二个判别式**（`_PAGE_RE_*` 无 `**`，`_ENTRY_RE_*` 带 `**`）：
`_PAGE_RE_SINGLE` / `_PAGE_RE_TWO` / `_PAGE_RE_THREE` / `_PAGE_RE_VAKIL` /
`_PAGE_RE_APP` / `_PAGE_RE_APP2` /
`_ENTRY_RE_SINGLE` / `_ENTRY_RE_TWO` / `_ENTRY_RE_THREE` / `_ENTRY_RE_VAKIL` /
`_ENTRY_RE_APP` / `_ENTRY_RE_APP2`。

- 数字章位（1/2/3）：`(?: 标签在前 | 序标在前 )` 双向，序标在前分支前挂 `_LEAD_GUARD`、
  整体末尾挂 `_TAIL_GUARD`。
- type 8（vakil）：**只有标签在前一支**（用户口径），第三维固定 `([A-Za-z])`，
  末位挂 `_TAIL_GUARD`；md 形态以 `[^*]*\*+` 收尾（允许 `**Exercise 2.3.A.**` 这类
  尾点与括号标题）。page 与 md 同构，**序标在前不收**。
- 附录（13/14）：同样双向（**md 与 page 都双向**——page 认得出的形态 md 必须抽得出，
  否则 `classify → extract` 链路会断），末位挂 `_TAIL_GUARD`；type 14 额外挂
  `(?!SEP\d)`。
  - `_ENTRY_RE_APP` 三分支（按优先级）：标签在前 → 序标在前 → 裸号。
  - `_PAGE_RE_APP` 只有前两分支：**page 形态刻意不收裸号**（散文里 `A.1.5` 与矩阵元 /
    公式号 / 小节号同形，旧页扫与 `keys_in_md` 的 prose 分支同样不收）。
  - `_ENTRY_RE_APP2` / `_PAGE_RE_APP2` 两分支，**均无裸号**（裸号两段与公式号同形）。
- 另有 `_PROSE_RE_TWO` / `_PROSE_RE_THREE`（散文 / 交叉引用形态，无加粗），
  只挂在 `prose_re` 上，**当前方法不使用**。附录两类 `prose_re = None`。

## 规范键归一权威 `normalize_ordinal`（契约侧接入用）

`normalize_ordinal(num_raw, label='')` 把**任意分隔符**的裸序标数字路径归一为与 md 侧
（`OrdinalStyle` 各子类 `canon_key`）完全一致的规范键：

- 3（及更多）段 → 裸横线型 `N.S-N`（三级，无标签，对齐 `OrdinalThreeLevelCN`）；
- 2 段 → `<规范标签>.N.N`（两级，带标签，对齐 `OrdinalTwoLevelCN`）；
- 1 段 → `<规范标签>.N`（单级，对齐 `OrdinalSingle`）。

段数按 `SEP_SPLIT_RE`（含全部通配分隔符 `. - – · / ． － 〜 _ ~`）切分判定，**不依赖某个
固定分隔符**——故 `1.1.1` / `1-1-1` / `1·1·1` 被归一为同一键，契约侧↔md 侧在「标点可替换」
上成立。这是供 `verify/script/structure_io.read_structure_items` 通用分支接入时、**代替其
「`num_raw` 含 '-' 即判三级」的错误启发式 + 过窄的 `_normalize_threelevel` 切分集**的权威入口
（pilot 接入管线前的必要前提）。验证见 `lib/tests/test_ordinal_normalize.py`。

## scope：数据派生，与 type 解耦

`detect_scope(keys)` 吃**文档序的规范键**，看**末位分量**的重置行为：

- 末位全程单调不减（跨章/节从不回 1）→ `SCOPE_BOOK` (1)；
- 仅首分量（章）变化时回 1 → `SCOPE_CHAPTER` (2)；
- 次分量（节）变化时也回 1 → `SCOPE_SECTION` (3)；
- 取全书观察到的**最细**（值最大）重置层级为准；并列取出现次数最多者。
- 单级（depth=1）走同一套通用检测：末位回退只能归因章级；末位不减则书级。
- 零 `keys` 时兜底 `SCOPE_CHAPTER`。

⚠️ **scope 不是 type 的派生量**：三级（type 3）书完全可能让末位跨章连续
（第一章 1–20、第二章 21–40 …），此时真实 scope 是 **book 级(1)**，不是节级(3)。

- `analyze(headings, keys)` → `OrdinalProfile(style, scope)`，一次打包形式判定与 scope 判定。
- `from_type_scope(type_code, scope)` → 配置驱动（scope 由调用方显式给），与
  `analyze` 的数据派生互补。

## 规则

### 🔴 头号要求：各 type 的判断相互独立（不能互相判断成功）

**表述**：对任意一个属于 type `T` 的条头 `h`，在**已注册的全部 type** 上跑判定，
结果必须是「只有 `T` 判成功，其余全判失败」：

```
OrdinalStyle.get(T).judge(h, page=…) is True
OrdinalStyle.get(c).judge(h, page=…) is False    # 对一切 c != T（含 c == 0）
```

细则：

1. **两套形态都要成立**：md 加粗形态（`page=False`）与 page 纯文本形态（`page=True`）
   各跑一遍矩阵。**只验一种形态不算通过**——识别类型走 page、抽键走 md，两边都得独立。
2. **不只段数**：除「恰好 k 段数字分量」外，还要防**章位形态**、**标签位置**与
   **字母序标**的互相截走。实例：附录字母章位头 `A.1.1 Definition` 的数字尾巴
   `1.1 Definition` 曾被 type 2 认成二级、`B.2 Theorem` 的 `2 Theorem` 曾被 type 1
   认成一级（故 `_LEAD_GUARD` 追加了「独立单字母 + 分隔符」断言）；type 8 的头
   `Exercise 2.3.A` 的尾巴 `Exercise 2.3` 曾被 type 2 认成二级（故 `_TAIL_GUARD`
   追加了「紧贴的分隔符 + 字母」断言）。
3. **`classify` / `detect_style` 同样不许跨认**：`classify(h)` 的返回码必须等于 `T`；
   语料里混入其它类型的条头，不得把主导 type 翻转。
4. **type 0（无编号）方向相反**：它 `judge` 恒 `False`，所以「无编号头」的正确结果是
   **所有 type 都判 False + `classify` 返回 `None`**，而不是「type 0 判 True」——
   无编号靠「所有编号风格都不中」判定。
5. **护栏必须零宽**：独立性由 `_TAIL_GUARD` / `_LEAD_GUARD` / `(?!SEP\d)` 等**零宽**
   断言实现 —— 零宽 ⇒ 不新增捕获组 ⇒ `extract` 的 group 索引不变。
6. **排查顺序**：一旦出现「互相判断成功」，先查该形态有没有对应护栏，
   **不要**去改 md 内容或加 ignore 掩盖（那是掩盖不是修复）。
7. **新增 type 的准入条件**：任何新派生类都必须先加进全类型矩阵并跑通，才算落地。

**验证**：demo **第 15 节**（全类型 × 全形态矩阵，**382 条断言**）必须为 `True`；
第 11 节（数字章位 1/2/3）与第 13 节（附录 ↔ 数字章位）是它的两个子集视角，
第 16 节（type 8）的 16a 是它的第三个子集视角。

### 体例判定
1. **段数必须相互独立**（头号要求的段数维度）：`type-k` 的 `judge` 只认**恰好 k 段**
   数字分量 —— type-3 不得把 1 级 / 2 级头认成 3 级，type-2 不得把 1 级头认成 2 级。
   由 `_TAIL_GUARD` + `_LEAD_GUARD` 两个**零宽**护栏保证（零宽 ⇒ 不新增捕获组
   ⇒ `extract` 的 group 索引不变）。type 14 另用 `(?!SEP\d)` 与 type 13 分流。
2. **识别类型必须走 page 纯文本形态**：`classify` / `detect_style` /
   `judge(page=True)` 用 `page_entry_re`，对齐 `make_config._detect_ordinal_from_pages`
   的页扫。不得用 md 加粗形态识别类型。
3. **md 抽键必须走 `entry_re`**：`extract` 与旧 `keys_in_md` 对应分支**逐字节等价**，
   零行为漂移（「与 legacy 的有意偏差」6 条除外，每一条都必须在本文件列明）。
4. **type 3 必须标签感知**：纯数字加粗行是节标题，不得判为条目。
   ⚠️ 副作用：旧 `regexlib.ENTRY_RE` 标签无关 ⇒ 纯数字 `**1.2.3**` / 中文节号
   `**第1.2.3节**` 在 label-aware redesign 下仍被刻意丢弃（节标题非条目），见「有意偏差」第 6 条。
   🔴 2026-09-21「选项 B」：`**练习1.2.3**` / `**Exercise 2.3.1**` 已进 `COMBINED`，type 3 收之，与 legacy 一致。
   🔴 2026-09-21「按正确标签判断」：type 3 与 type 2 共用全量 `_LABEL_ALT`（= `COMBINED` 38 词），
   不做额外收窄——`**Application 1.2.3**` / `**条件1.2.3**` 等随 `COMBINED` 一并收（偏差表已无第 7 条）。
5. **双向**：type 1/2/3/13/14 的标签在前与序标在前两种顺序都要支持，**md 与 page
   两套形态都必须支持**——`judge(page=True)` 认得出的条头，`extract` 必须抽得出键，
   否则「识别类型 → 抽键」链路断裂。
   ⚠️ **type 8 是唯一例外**：按用户口径**只收标签在前**（`2.3.A Exercise` 不收），
   这是「识别↔抽键自洽」的**单向**版本——它认什么就抽什么，不认的就不抽。
6. **type 8 的第三维必须是字母**：`Label C.S.A` 的第三维只收 `A–Z`（IGNORECASE 下
   小写也命中并归一为大写），**数字第三维不属本类**（归 type 3 / 数字三级体例）。
   两级（`Exercise 2.3`）归 type 2、字母章位（`Exercise A.1.1`）归 type 13。
   ⚠️ 复数 `Exercises` 不收（`_canon_label` 无规范映射）。
7. **附录严格按段数分流**：字母章位 + 两段数字 → 13，字母章位 + 一段数字 → 14。
   🔴 绝不把两段书误判成 13 再靠下游宽容解析兜底（旧 type 13 分支的「两段宽容回退」
   是历史遗留，本层级不继承）。
8. **裸号不对称是刻意的**：裸号三级 `**A.1.5**` 只在 **md** 形态被 13 收（对齐
   `keys_in_md`）；**page 形态不收**（对齐 make_config 的 label-driven 页扫与
   `keys_in_md` 不收裸号 prose）。裸号两段 `**D.1**` 13/14 都不收。

### 类契约
9. **三表交叉校验**：`code` / `depth` / `name` 必须同时与 `ORDINAL_CODES` /
   `ORDINAL_DEPTH` / `ORDINAL_NAME` 一致，定义即校验。
10. **不得新增 `language` 类属性**：语言轴由正则词表吸收。
11. **不得新增 `scope` 类属性**：scope 只能是实例属性（显式入参）或 `detect_scope`
    的数据派生量，**绝不**由 type 反查。
12. **标签词表单一真源**：**所有类型**（1/2/3/8/12/13/14）统一用 `_LABEL_ALT`（`COMBINED_LABEL_KINDS`，38 词），
    都**必须按长度降序**；附录类（13/14）仅在 `_LABEL_ALT` 之上额外挂 `_APP_PLURAL`（`(?:es|s)?`）收复数头；
    禁止各类型各写一份手写子集。
13. **规范键形态**：type 1/2 为「规范标签 + 数字」，type 3 为纯数字（`normkey`），
    type 8 为「规范标签 + 章号 + `.` + 节号 + `-` + **大写字母序标**」，
    附录 13 为「规范标签 + 大写字母章位 + `.` + 节号 + `-` + 条目号」（裸号则无标签
    前缀），附录 14 为「规范标签 + 大写字母章位 + `.` + 条目号」。
14. **字母序标必须参与 scope 判定**：字母出现在哪一维，那一维就必须折成序号——
    附录两类（**首**分量是字母章位）覆写为 `_app_key_to_tuple`，type 8（**末**分量
    是字母序标）覆写为 `_vakil_key_to_tuple`；用基类的 `re.findall(r'\d+')` 会丢掉
    字母维，把「换字母回 1」误判成书级连续。

### 工程约束
15. 🔴 **正则片段变量必须「拼接」引用**：
    `r'|' + _LEAD_GUARD + r'(\d+)'` ✅；
    写进字符串字面量 `r'|_LEAD_GUARD(\d+)'` ❌ —— 字面量里 `_LEAD_GUARD` 只是普通文本，
    正则会去匹配字面 `_LEAD_GUARD`，该分支永不命中。判据：片段名出现在 `r'…'` 内部即错。
16. 🔴 **改本文件必须「内存构建 + exec 校验 + 一次写盘」**：沙箱对该路径**读有 jitter**
    （同一 inode 相邻两次 open 可能返回不同版本），多轮增量 Edit 会静默丢失、
    「读→改→写」往返会把正确版本覆盖成坏版本。做法：先 `shutil.copyfile` 出稳定副本 →
    内存里 `str.replace` 改造 → 直接 `exec(src)` 校验 → 通过才一次性写回。
    （派生 13/14 由 `_build_app.py` 一次跑完：187 条断言全过才写盘；派生 8 由
    `_build_vakil.py` 一次跑完：279 条断言全过才写盘。）
17. **与 legacy 的偏差必须逐条列明**：新层级刻意不同于 `keys_in_md` 之处，一律写进
    demo 第 12b / 16d 节（说明 + 新值 + 旧值 + 理由），**不得静默漂移**。当前 6 条见下。
18. **改正则后必须重跑全量验证**（见下）。
19. **用户口径优先于 `verify_config` 的旧 type 描述**：表里的注释是历史实测归纳，
    用户明确给出某 type 的判定形态时（如 type 8 = 标签在前 + 第三维字母），
    按用户口径实现，并在本文件「有意偏差」里写清覆盖了哪条旧描述。

## 与 legacy 的有意偏差（6 条：12b 节 4 条 + 16d 节 1 条 + 16e 节 1 条）

| md 输入 | type | 新层级 | 旧 `keys_in_md` | 理由 |
|---|---|---|---|---|
| `**Examples A.1.3**` | 13 | `例A.1-3` | `None`（漏收） | 复数标签：make_config 页扫支持 `(?:es|s)?`，旧 md 词表无复数会漏收 |
| `**A.1.1 Definition**` | 13 | `定义A.1-1` | `A.1-1`（裸号键） | 序标在前：旧无序标在前分支，只能靠裸号正则抽成无标签键 |
| `**A.1 Definition**` | 14 | `定义A.1` | `None`（漏收） | 序标在前：旧两段分支完全不认（裸号两段又不收，无兜底） |
| `**Theorem D.1**` | 13 | `None` | `定理D.1` | 旧「两段宽容回退」违反段数独立；两段体例归 type 14 |
| `**Exercise 2.3.A**` | 8 | `练习2.3-A` | `None`（**无 type 8 分支**） | 🔴 **用户口径覆盖旧描述**：`ORDINAL_VAKIL` 旧注释是「序标在前 N.M.item + N.M.A exercises」，`extract_items_vakil` 的 `VAKIL_ITEM` / `VAKIL_EXER` 也都是序标在前；用户口径 = 标签在前的 `Label C.S.A`。本类是**新定义**，无等价基线可对拍 |
| `**1.2.3**` / `**第1.2.3节**` | 3 | `None` | `1.2-3` / `1.2-3` | 旧 `regexlib.ENTRY_RE` **标签无关**（任何「数字 SEP 数字 SEP 数字」加粗行都收，含中文节号 `第N.N.N节`）；本类 label-aware redesign 刻意不收纯数字/中文节号（节标题非条目）。🔴 2026-09-21「选项 B」后 `**练习1.2.3**`/`**Exercise 2.3.1**` 已进 `COMBINED`，type 3 收 `练习1.2-3`/`练习2.3-1`，与 legacy 一致，本偏差仅余标签无关真值 |

前三条是**加法**（legacy 漏收/丢标签，新层级补全）；第四条、第六条是**减法**
（第四条刻意不继承历史兼容；第六条是「标签感知」改造的连带代价，仅余纯数字
`**1.2.3**` / 中文节号 `**第1.2.3节**` 这类真值仍被刻意丢弃——节标题非条目，属设计内；
`**练习1.2.3**` / `**Exercise 2.3.1**` 已由 2026-09-21「选项 B」闭合，不再计入代价）；
第五条是**重新定义**（用户口径覆盖，非迁移）。
🔴 2026-09-21「按正确标签判断」已落地为「type 3 与 type 2 共用全量 `_LABEL_ALT`（38 词）、不收窄词表」，
故 `Application` / `Variation` / `Porism` / `条件` 等与 type 2 一致收为条目，偏差表无第 7 条。

## 验证

**正式验证（留存、随仓库提交）**：`lib/tests/test_ordinal_hum.py`（`OrdinalHum` 双向归一 /
负向不误吞 / `classify` 不误判单级 EN 书 / 字母折序号 / `detect_scope` / judge↔extract 自洽）
与 `lib/tests/test_ordinal_normalize.py`（段数判定 + 分隔符容错 + 契约↔md 一致）。全量
`pytest --basetemp=C:/tmp/pytest_bt` 基线 **241 passed**（含这两条的 16 条）。

**临时验证入口（工作区临时产物，不留存）**：`D:/study/.workbuddy/_tmp_20260920_ordinal_pilot/demo.py`
（16 节，全类型 × 全形态矩阵 382 条断言 + 等价性 + 偏差对齐）。⚠️ 该临时脚本写于 type 12
落地**之前**，**未覆盖 type 12 的全类型相互独立矩阵**；type 12 的相互独立已由
`test_ordinal_hum.py` 锁定。正式接管线前，须把 type 12 并入该矩阵，或仅依赖上面的 pytest 测试。

下表为 demo 关键节（临时脚本）：

| 节 | 断言 |
|---|---|
| **第 15 节** | 🔴 **头号要求：全类型 × 全形态矩阵，各 type 判断相互独立、互不判成功**（含 `classify` 返回码、混入他型头的 `detect_style`、无编号头全 False），**382 条断言** |
| 第 16 节 | **type 8（vakil）**：标签在前 + 第三维字母；相邻形态归位（2 / 3 / 13 / 14 / 不收）；page 识别 + `classify`/`detect_style`；字母序标 scope（换节→3、跨节连续→1、换章→2）；**无 legacy 基线**（16d）；16e **type 3 标签无关三段头**与 legacy 对拍
（`**1.2.3**` / `**第1.2.3节**`：**legacy 收、本类不收**，偏差第 6 条；🔴 选项 B 后
`**练习1.2.3**` / `**Exercise 2.3.1**` 已收、与 legacy 一致） |
| 第 3 节 | 等价性：`extract` 与旧 `keys_in_md` 分支逐条一致，**失败条数必须为 0** |
| 第 10 节 | page 纯文本识别（含 `1.5-3 Definition`→3、`1.1 定义`→2、`1.1.1`→None） |
| 第 11 节 | **type 间校验相互独立**（互不跨认）必须为 `True` |
| 第 12 节 | 附录 13/14：与 legacy 等价 + **4 条有意偏差逐条对齐** |
| 第 13 节 | **附录 ↔ 数字章位全矩阵互不跨认**（含字母章位头的数字尾巴不被 type 1/2 截走）、裸号不对称、classify/detect_style 识别附录 |
| 第 14 节 | 字母章位 scope 派生（首分量折成字母序号：换字母章→2、换节→3） |

## 相关代码

- `lib/ordinal_styles.py`：本模块。
- `config/verify_config/verify_config.md`：`ORDINAL_CODES` / `ORDINAL_NAME` /
  `_canon_label` / `SCOPE_*` 权威定义与 `type` 判定树；`ORDINAL_APP=13` /
  `ORDINAL_APP2=14` 的体例定义（Weibel / Lee ISM 实测来源）。
  ⚠️ `ORDINAL_VAKIL=8` 的**旧注释（序标在前）已被用户口径覆盖**，见「有意偏差」第 5 条。
- `lib/numbering.py`：`ORDINAL_DEPTH`（depth 唯一真源，12→1、13→3、14→2）。
- `lib/key_parse.py`：`keys_in_md`（md 抽键的当前权威实现）、`COMBINED_LABEL_KINDS`、
  `APP_LABEL_KINDS`、`ENTRY_RE_APP_C` / `_APP_BARE_` / `_APP2_C`、`normkey`。
  🔴 2026-09-21「选项 B」变更（影响 legacy `keys_in_md` 与本模块 type 1/2/3，须全书回归）：
  `CN_LABEL_KINDS` 补 `练习`、`EN_LABEL_KINDS` 补 `Exercise`；`ENTRY_RE_2` / `PROSE_RE_2`
  的硬编码词表同步加 `练习|Exercise`；`APP_LABEL_KINDS` 退化为 `COMBINED` 去重（Exercise 已在
  `COMBINED`）。此后 `**练习N.N**` / `**Exercise N.N**` 头会被 type 2/3 正常抽取（与 vakil type 8
  的 `练习N.N-A` 字母序标互不冲突）。
  ⚠️ 该补词表已在 2026-09-21「选项 B」完成（`CN_LABEL_KINDS` 补 `练习`、
  `EN_LABEL_KINDS` 补 `Exercise`），故 `**练习N.N**` / `**Exercise N.N**` 头现被
  type 1/2/3 正常抽取；且 2026-09-21「标签词统一」后 type 8/12/13/14 与 type 1/2/3
  **共用同一 `_LABEL_ALT`**（= `COMBINED_LABEL_KINDS`，38 词），旧 `_LABEL_ALT_EX`
  / `_APP_LABEL_ALT` 别名已废弃，「CN 的 `练习` 漏收」问题不再存在。
- `lib/regexlib.py`：`SEP_TIGHT`。
- `flows/write-source/structure/script/extract_items_vakil.py`：legacy 的 type 8 抽取器
  （`VAKIL_ITEM` 三段数字 / `VAKIL_EXER` 字母序标，**均为序标在前**），本类按用户
  口径改为标签在前，故**不作为对齐对象**（见「有意偏差」第 5 条）。
- `config/verify_config/make_config.py`：`_detect_ordinal_from_pages`（页扫识别类型的
  当前入口）、`_build_label_heading_regexes(letter_chapter=True)`（附录双臂页扫，
  本模块 page 形态的对齐对象）、`_SEC_HEAD_APP_RE`。
