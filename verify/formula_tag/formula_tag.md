# Q 层 — FORMULA SEQUENCE-LABEL（公式序标层）（formula_tag）

> 本文件是 **Q 层** 的唯一权威详情（SSOT）。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verify.md`](../verify.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。
> **注册机制**：本层脚本位于 `verify/formula_tag/script/formula_tag.py`，由 `verify/script/register_all.py` 用 `importlib` 按裸名扫描 `verify/*/script/` 自动发现并注册。`code = 'Q'` 是稳定字母代号（被 SKILL.md 与 per-book 记忆广泛引用，**不可更改**）；新增层无需改 `register_all.py` / `VerifyManager` / CLI。

## 目的
总结里带 `\tag{X}` 的公式，其序标必须与**书源公式编号集合 S** 1:1 对应；编造/错位/跨章阻断 FAIL，遗漏（未在 `formula.ignore` 登记）阻断 FAIL，公式内容人工对账。除编号集合成员关系外，Q 层还校验**编号序列顺序（ORDER_MISMATCH）**与**小节定位（MISPLACED）**——二者均为 WARN（非阻断），使 Q 成为覆盖编号集合成员 + 序列顺序 + 小节定位的完整公式序标校验。

## ⚠️ 执行前置（Pre-flight，强制）
> **本层是 opt-in，配置缺失会静默 no-op**——若 `verify_config.json` 没有 `formula` 块，Q 层直接返回中性 `q_*` 元数据、不写报告、不计入 FAIL。**这会让执行者误以为"公式校验已通过"，实际根本没跑。** 因此运行本层前，agent 必须完成以下前置，缺一不可：

1. **先确认配置存在**：检查 `<extract_dir>/verify_config.json` 是否含 `"formula"` map。
2. **缺失则按书实际编号推导并写入**（agent 负责，不要跳过）：
   - **扫书实测**：遍历该书若干章的 `page_{start:03d}.json … page_{end:03d}.json` 的 `text[].text`，用公式标签正则（覆盖 `（C.N）`/`(C.N)`/`Eq. C.N`/`Equation C.N`/`式（C.N）`/裸 `C.N`）看实际编号长什么样。
   - **`depth`** = 编号数值段数，**由 `type` 经 `ORDINAL_DEPTH` 派生**（不要单独配置）：`C.N`（如 `2.6`）→ `type 2`（depth 2）；`C.S.N`/`C.S-N`（如 `11.1-1`）→ `type 3`（depth 3）；单分量 `(N)` → `type 1`（depth 1）。
   - **`scope`**：编号重置窗口，**必须从书中实测确定，无默认值**——`2`＝章级编号 `C.N`（开启跨章守卫：首分量 ≠ 当前章号判 INCONSISTENT）；`1`＝全书全局连续（关闭跨章守卫）；`3`＝每节重置（如 Kreyszig `(1)`）。🔴 已声明 `type` 的 formula 块若**缺 `scope`** 或取值越界（非 1/2/3），加载期 `verify_config.from_dict` 一律 `ConfigError`（exit 2），不再静默按章级处理。`make_config.detect_formula` 对两级数字 `(C.N)` 用**首分量重置证据**派生 scope（逐章重启→2 / 全书连续→1）；证据不足（整书仅见单一首分量、无从观测重置）时**省略 scope**，交由 agent 依书补定。
   - ⚠️ **scope:3 ⇒ depth 必为 1**：节级重置必为裸 `(N)`，不可能带 `C.N`（若出现 `C.N` 则必 scope:2）。
   - **`type`**：编号风格码，**唯一权威字段**；`depth` 由 `type` 经 `ORDINAL_DEPTH` 派生（2 段→`2`→depth 2，3 段→`3`→depth 3，单分量→`1`→depth 1）。不再单独写 `depth`。
   - **type 1 = 单分量 standalone `(N)`**：节级重置（Kreyszig 风格），`depth` 必为 1，`scope` 通常为 3。是单分量公式书唯一合法码。
   - `ignore`：先给空数组 `[]`；跑出 MISSING 且确认属合理省略时再加。
   - 写入示例（章级两段编号书）：
     ```json
     "formula": {"type": 2, "scope": 2, "ignore": []}
     ```
     ⚠️ 此示例为**章级两段编号书**，仅作章级参考；**不可照抄到节级单分量书**（Kreyszig 每节重置应为 `{"type":1,"scope":3}`）。
3. **配置错会降级**：若 `formula` 配了但 `depth` 不对导致书源抽不到编号（S 空），层只做结构检查并 WARN「书源公式编号未抽到，请检查 formula 配置」，**不判编造/遗漏 FAIL**——此时须回头修正 `formula` 的 `type`/`scope`（实为 `type` 派生错），不要当成"通过"。

- **代码护栏**：`formula_tag.py` 的 `run()` 网关已实现——当 `formula` 为 `None` **且**该章总结含 `\tag{...}` 时，会向 stderr 打印醒目的 `[Q-LAYER WARN]`，明确提示"公式序标未校验，不可报通过"。无 `\tag` 的书仍静默 no-op（合法）。agent 看到该 WARN 必须停下补全配置，禁止继续宣称公式校验通过。
- **稀疏编号书（2026-08 Fraleigh 案例）**：全书仅少数章有编号公式、且总结为扁平结构（无 `## §N.M`）时，plain 路径对单分量（ncomp==1）书源抽取施加与 build_sectioned 同源的门禁——只认①独立整行标签块 `(N)`；②含数学记号且以 `(N)` **结尾**的块，但**只提取块尾那一个匹配**（防阶乘因子 `(3)(2)(1)`、生成元 `H=(4)`、分解式末位因子等块内括号被误抽）。前置校验 check#1 仅在**本章总结确有 `\tag` 而 configured 抽取为空**时才报 ERROR；无 tag 的章按「S 为空降级」放行。
- **每章 ignore 形状**：`ignore_ch{N}.json` 同时接受 list（纯键列表）与 dict（键 -> 登记理由；B 层 / IGNORE-AUDIT 惯例形状），Q 层两者都合并进本章忽略集——登记公式噪声时优先用 dict 附理由以便人审。

## 步骤（语义与检查内容）
- **门控（opt-in）**：`BookConfig.formula` 为 `None`（默认）时整层 no-op——返回中性 `q_*` 元数据、不写报告、不计入 FAIL，确保既有全部校验层与已完工书目零变化。仅当某书在 `verify_config.json` 显式配置 `formula` map 后才启用。
- **配置形状**（与条目序标 `ordinal` 配置同构，非平铺字段）：
  ```json
  "formula": {"type": 3, "scope": 2, "ignore": []}
  ```
  - `type`：**digit 家族**沿用 ORDINAL_* 风格码 `1`/`2`/`3`（`depth`=分量段数由 `type` 经 `ORDINAL_DEPTH` 派生：单分量→`1`、两段→`2`、三段→`3`；弃用码 `4`/`9`/`10`/`11` 已退役）；**alpha 家族**用 formula-only 专用码 `15`（字母二级 `(A.3)`）/ `16`（罗马二级 `(II.5)`）/ `17`（字母三段 `(A.2.1)`）/ `18`（罗马三段 `(II.1.3)`），它们不进 `ORDINAL_CODES`/`ORDINAL_DEPTH`。**lead 与段数一律经 `resolve_formula_type(type, letter_ch)` 派生**，`depth`/lead 不再单独配置。legacy 字母书写 `type: 2 + "letter_ch": true` 亦可。`ORDINAL_SECTION_TYPES` 是小节层级反推，与 formula 的 `depth` 无关。
  - `scope`：1=book / 2=chapter / 3=section——编号重置窗口；**跨章守卫**（首分量 ≠ 当前章号判 INCONSISTENT）当且仅当 `scope == 2` 开启，book/section 作用域关闭该守卫。
  - `ignore`：要跳过 1:1 比对的归一化公式编号列表（既不判 FABRICATED 也不判 MISSING）。支持两种键形态：裸编号（全章生效）与 `'<sec>#<num>'` 作用域键（仅该节生效，见上）。
- **scope/depth 耦合不变量（`depth`/lead 由 `type` 经 `resolve_formula_type` 派生；`scope` 独立）**：scope:3⇒`type 1`(depth 1，节级裸`(N)`)；scope:2⇒章级带前缀的多段编号（digit `type 2`/`type 3` = depth 2/3，或字母章位 `(A.3)`/罗马章位 `(II.5)` 的 formula-only `type 15`/`type 16`，含 legacy `type 2 + letter_ch:true`）；scope:1 通常 `type 1` 全局连续。违反即非法，`require_complete` 应拒。（弃用码 4/9/10/11 早已退役，不存在「`type≥4`」。）
- **书源编号抽取**：`SourceFormulaIndex.build()` 遍历 `page_{start:03d}.json .. page_{end:03d}.json`，对每页 `text[].text` 用**由 `type` 派生的 `depth`** 正则抽编号（`build_formula_patterns(ncomp)` 覆盖 `（1.17）`/`(1.17)`/`Eq. 1.17`/`Equation 1.17`/`式（1.17）`/裸 `1.17` 六种变体，每式单捕获组），`norm()` 归一后归入本章集合 S。**只读 text**；`formulas[].latex` 仅在一条守卫下参与——latex **以括号包裹的 `(C.N)` 开头**（OCR 把显示公式连同其编号捕获为 latex 首 token 的形态，如 Han–Lin `(4.3) \quad …`，此时编号从未落进 `text[]`，漏收会使总结忠实的 `\tag` 被误判 FABRICATED）才交给同一 `_scan_text` 管线；普通数学不会以 `(\d+.\d+)` 开头，不会把代数噪声混进 S（2026-09-09）。
  - 🔴 **编号 token 的正则核属于 `lib.numbering.formula_num_core`（唯一真源）**：本层抽书源编号、`attach_content` 给公式挂 `tag`、`check_content_completeness` 做序标独立真值，三处共用同一套形态（段数由 `formula.type` 经 `ORDINAL_DEPTH` 派生；分隔符 `. - · ,`；可选字母后缀；`letter_ch` 时首段为单个大写字母）。**改形态只改 `lib/numbering.py`**，否则三处口径漂移会互相判对方"漏/编造"。
  - 实测形态差异极大，**不可假设 `(C.N)`**：约半数书右缘编号**不带括号**（Kreyszig / Evans SDE / PDE / Ross / 随机过程 / 解析数论），另有 `11.1-1` 连字符三段、`8.11a` 字母后缀、字母章位 `(A.3)`（Lee ISM 附录）等。编号还可能排在公式**左缘**（Kreyszig / 解析数论 / PDE）而非右缘。
  - 🔴 **字母章位编号（`formula.letter_ch: true`，2026-09-14 落地）**：`(A.3)` / `（B.12）` 形态（Lee 附录 B.1-B.15 / C.1-C.21 / D.1-D.21 实测）。patterns/norm 接受单个大写字母首段（`norm('（A.03）')`→`'A.3'`）；`scope==2` 跨章守卫用字母首分量对比章键（`'B'`）直接工作；**裸排变体在该模式下永不启用**（裸 `A.3` 与 `Fig. A.3` / 小节标题 `C.1` 无形态区别）。`make_config.detect_formula` 对页区间 letter-led 形态占优（≥30 次行尾命中且压过 digit）时自动写 `"letter_ch": true` 并按字母章回退判定 scope。
  - 🔴 **formula-only lead 命名空间（digit / letter / roman，2026-10-01 解耦）**：字母二级 `(A.3)` 除 legacy `type:2 + letter_ch:true` 外有专用码 **`type: 15`**；罗马二级 `(II.5)` / `(I.5)` 有专用码 **`type: 16`**（`lead='roman'`，`make_config.detect_formula` 见**多字母罗马证据**且**无非罗马字母头**时自动选）。这两个码**刻意不进** `ORDINAL_CODES` / `ORDINAL_DEPTH`——条目侧 `verify_config` 的 ordinal 组校验（`t not in ORDINAL_CODES` 即抛 ConfigError）**天然拒绝**它们，两套 type 空间互不知晓，故新增公式体例绝不污染条目体例判定。三个 lead 家族一律经**唯一入口** `lib.numbering.resolve_formula_type(type, letter_ch) → (lead, ncomp)` 取形态，消费方**禁止**各自再判 `letter_ch` 或反查 `ORDINAL_DEPTH`（口径漂移会互相判「漏挂/编造」）。**形态互斥**由 `formula_num_core` 保证：digit 核首段必 `\d`、letter 核首段恰**单个** `[A-Z]`（故 `II.5` 不被 letter 命中——首字母后紧跟的是字母不是分隔符）、roman 核首段 `[IVXLCDM]{1,5}`（故 `A.3` 不被 roman 命中——`A∉IVXLCDM`）；alpha-led（letter/roman）**永不**发裸排变体。唯一残留歧义是**单字母罗马头**（`I.`/`V.`/`X.`/`L.`/`C.`/`D.`/`M.` 既是字母又是罗马）——由**整本书只配一个 lead** + `detect_formula` 保守择族消解（只有多字母罗马证据才选 roman，否则保持 letter，宁缺勿滥）。判据测试 `config/verify_config/tests/test_formula_lead_decoupling.py`。仅**多字母词前缀**（`App.2` / `Ap.3`）无对应 lead 家族，仍 `q_letter_led` WARN。
  - 🔴 **三段章位 `(A.2.1)` / `(II.1.3)`（type 17 / 18，2026-10-03 Katok《现代动力系统导论》附录A/补篇S 根治）**：探测层的两段探针 `F_LETTER_RE` / `F_ROMAN_RE` 在**第一个数字段后**就要求闭括号，对三段体例**结构性零命中** → 该段配置丢 `formula` 键 → Q 层对 18 枚印面序标静默 no-op（只有 WARN，不 FAIL，极易被忽略）。修法三段式：① `lib/regexlib.py` 新增 `F_LETTER3_RE` / `F_ROMAN3_RE`（捕获 head/section/number 三元组）；② `make_config.detect_formula` 新增 `roman3`(18) → `letter3`(17) 择族分支，除**数量下限**（`_FORMULA3_MIN_COUNT=5`）与**形态可信**（`_alpha3_confident`：≥2 个 `(head, section)` 桶 + 桶内升连跑 ≥3 或双桶各 ≥2 号）外，还要求**三段命中压倒被扫描范围里其余各族**（`count3 > single + dotted + letter2 + roman2`）——实测同一本书整书扫描时正文右缘单段号 79 命中 vs 附录三段 21 命中，若只比两段对手，附录体例会**劫持**正文段选举把 `ch` 配置改写字母三段，19 章 Q 校验当场作废；③ 已存在却缺 `formula` 键的老配置走 `make_config._backfill_missing_formula_cfg` **增量补写**（只按该段自己的页区间探测、只填 `formula`，`ch` 段与既有 `formula` 一字不动）——因为这类书的 `--force` 整份重生成不安全（Katok 正文段是人工早期定下的 `type 3`，探测器只会给 `type 1`）。跨 51 本书普查（`tools/census_alpha3_formula.py`）：只有 Katok 触发，另 3 本书的 1–2 处孤立碰撞被数量/形态闸拒掉。判据测试 `config/verify_config/tests/test_detect_formula_alpha3_led.py`。注意：字母三段的 `md_sections` 扫描（`_MD_SEC_TWO` 只认数字）为空 → Q 走非分节路径，这是既有降级形态，不是漏检。
  - 🔴 **形态②「块尾标签」的唯一判据 = `tail_label_match`（`text[]` 与 `formulas[].latex` 共用，2026-09-29 落地）**：一个块算「以印刷编号收尾」必须同时满足 ① 剥掉尾随空白后以 `(N)`（可带句点）收尾；② 那对括号**不是函数/群的参数表**——由 `_tail_pre_guard(左邻原文)` 判定。判据**吃未剥空白的左邻**：「括号左边有没有空格」本身是判据（剥掉则 `a = 1 (1)` 与 `c_1(2)` 不可区分，一刀切拒数字会把整章右缘标签全判掉——Kreyszig 回归实测）。拒收：与括号**黏着**的左邻是字母/数字/CJK/`\`（`f(x)`、`c_1(2)`、`式(3)`、`SO(3)`、`\sin(2)`）；剥空白后以 **CJK 或 `\`** 收尾（`见式 (3)` 型中文交叉引用）；左侧 **≥2 个连续单大写字母 token**（`\boldsymbol { X }` 类字体壳按一个字母计）= `S O ( 3 )` / `T S O ( 3 )` 型李群记号（阿诺尔德 ch8+附录E 实测 33 条被收进 S，制造两处假 MISSING）。放行：隔空白的**单个** token（`f(x) \le M (9)` 单字母、`b = 2 (2)` 数字）。已知取舍：latex **命令名**隔空白（`\phi ( 2 )`）在放行侧——它与真空标签 `\quad (8)`、`\circ (3)` 形态不可分，实测噪声里无此形态，故不加函数名白名单（命令**黏着**括号时仍由 ① 拒收）。测试 `verify/tests/test_q_tail_label_space_glue.py`。
  - 🔴 **单段编号（`depth<=1`）不收字母后缀**（2026-09-28 Apostol《解析数论导引》ch11 根治）：子式后缀编号 `(8.11a)` 在实测语料里**只出现在多段体例**（Evans SDE/PDE、Koopman、Ross、A First Course in Numerical Methods、Chaos/Fractals/Noise 全部 `depth>=2`）；单段书里孤立的 `(2s)`/`(6s)`/`(9x)` 是**公式被截成独立块**的碎片（Apostol p243/p253/p259 的 `(2s)`/`(6s)` 与 ζ(2s) 同行，同型还有《数学分析》type=1 的 `0x/1D/2M/3w/4m/9x`）。收下它们＝契约多出一条不存在的 tag，而单元 tag 对账是硬闸 → 逼写手凭空造 `\tag{2s}`。判据在 `formula_num_core`（三处消费方同口径），测试 `lib/tests/test_formula_num_core_suffix.py`（含多段后缀书零回归正例 + 碎片负例）。`ncomp=None`（未配置）与 `letter_ch`（字母章位）分支不受影响。
- **序标校验（自动 FAIL）**：
  - `q_fabricated`(FABRICATED)：总结 `\tag` 编号归一后**不在 S**（编造/串号）→ 始终 FAIL。
  - `q_inconsistent`(INCONSISTENT)：编号**重复**，或**跨章**（`scope == 2` 时首分量 ≠ 当前章号）→ 始终 FAIL。
- **遗漏校验（未登记 `formula.ignore` 时阻断 FAIL）**：
  - `q_missing`(MISSING)：S 中属于本章、规范、前缀匹配的编号在总结无对应 `\tag` → **FAIL（阻断）**。writing-rules 硬性要求 7 规定书源所有带编号公式（含描述性散文中的推导式）都必须保留，故"未登记的遗漏"即"漏写公式"。书源确有该编号但属合法省略（如纯排版重复）时，把它加入 `formula.ignore` 跳过比对；未在 `ignore` 登记的遗漏一律阻断，以防漏写描述性推导公式。
  - 🔴 **章末集中习题块不入 S（`_in_exercise_tail`，2026-09-27 Strogatz 3e ch13 根治）**：`build` / `build_sectioned` 的页循环先读分章契约，取 `consolidated: true` 节点的**最小叶号**，该页及其后一律不扫。理由：writing-rules「有专门习题小标题的集中习题块一律省略」+ `unit_node_entries` 对 `consolidated` 节点**不出单元** → 该块内容按设计不进总结，而印面确实带右缘编号（实测题 13.6.5 Ott-Antonsen 有 `(13)`p553 y=250、`(14)`p553 y=507），旧行为把 `(14)` 收进 S 后 MISSING 硬闸反过来要求写手把习题解答写成正文公式（只能靠编造上下文满足）。契约无 `consolidated` 标记的书（节末习题、无集中块）行为逐字节不变，判据测试 `verify/tests/test_q_layer_consolidated_exercise_tail.py`（含正/反两向控制）。
  - 🔴 **本节判据依赖 `_load_sec_keys` 不被静默吞异常（2026-10-04 同书 ch13 复发根治）**：`_load_sec_keys` 末尾是 `except Exception` ——它本意只兜「契约文件缺失/坏 JSON」，于是**函数体内任何编程错误都会把 `_sec_keys` / `_tail_exer_page` / `_tail_exer_anchor_y` 一起打回 `None`**，即上面两节判据静默失效（fail-open），verify 表面照跑、报告一行 MISSING 了事。实测事故：新增的节起始页账本被写成裸名 `_ranges[...] = …`（应为 `self._sec_ranges`）→ 每个章的 `_load_sec_keys` 都 NameError → 习题块剔除整本书失效 → Strogatz 3e ch13 双版各报 `Q-LAYER FORMULA MISSING (14)` 阻断（该书架此前 26/26 PASS）。修法 = 绑定回 `self._sec_ranges`；🔴 **除危险本身入了回归锁**：`verify/tests/test_q_layer_sec_ledger_binding.py` 直接断言「给定结构正常的契约，三个属性必须按契约取值」，负向对照（把那行改回裸名）下 3 条立碎，另证明 `test_q_layer_consolidated_exercise_tail` 的 8 条正是被这个 NameError 打碎的。**新增本节类判据时的守则**：`_load_sec_keys` 里只允许对 `os`/`json` 失败降级，任何账本赋值都要在测试里有一条「属性非空」的正向断言，否则判据失效应等于隐形。
- **序列顺序校验（WARN，永不阻断）**：
  - `q_order_mismatch`(ORDER_MISMATCH)：总结文档序与书源阅读序不一致 → 仅 WARN。`scope==3`（节级重置，编号每节重复）时按 `## §N.M` 窗口独立判定，且比较用 **per-(sec,n) 节内首现位置**（`_pos_sec`）——重复编号的全局首现位置恒来自最早含 `(n)` 的节，跨节比较必产生噪声（2026-08 Kreyszig 实测）；某 tag 无节内位置记录（其独立标签被 OCR 并行/丢失）时**跳过该 tag 的顺序判定**（既不判倒挂也不更新游标）。`scope==2/1` 时窗口跨节、沿用全局首现位置。
  - 🔴 **「提及」不得冒充「标签」抢到定义位置（锚点证据分级，2026-10-02 Lasota-Mackey《Chaos, Fractals and Noise》根治）**：顺序/定位两支的比较基准都是书源为该号记下的 `(page, y)`，而 `page_*.json` 里**任何**含 `(N.M)` 字样的块都会命中——图注续行、散文回指、习题题干皆是「提及」。两处漏洞：
    ① `allow_bare`（默认 true）同时注册 `(N.M)` 与裸 `N.M` 两枚 pattern，裸号命中的左邻**永远是编号自己的开括号**，`_embedded_ref` 因此把 `Further, by (11.1.4),` 判成「行首独立标签」。修法 = 遇到开括号**跨过它再走同一谓词**（括号左边是文字/条目词 → 引用；是行首或运算符 → 标签）。实测 ch11 的 11.1.4、ch12 的 12.7.4（两枚都只以回指出现，且已在 `formula.known_book` 登记）据此失去伪锚点后，其后一号 11.1.5 / 12.7.5 的倒挂假阳一并消失。
    ② `keep_cross_refs=True` 下纯散文块里的括号命中**必须进 S**（否则总结里忠实转写的 `\tag` 被误判 FABRICATED），但「进 S」≠「是位置证据」；旧写法把「带括号」当无条件强信号，于是一处提及就能改写定义位置。修法 = `_scan_text` 的位置/定义节强度改为 `_is_strong_signal(span) and _label_grade`，其中 `_label_grade` = **整块就是一个编号**（standalone 标签块）**或**该块含数学记号——与 `build_sectioned` 的「standalone 或 `_block_has_math`」同一口径。🔴 只按 `_block_has_math` 分级会**反向**造假阳：其短块豁免只到 8 字符（为 Kreyszig 单分量 `(N)` 设的），多分量书的真标签块 `(11.1.15)` 长 10 字符且不含数学记号，会被降级、反倒输给一句含 `>` 的散文回指（实测本书 ch11 的 11.1.15/11.1.17 各被挪到更晚一页，多出 4 条假阳）。散文提及降级为**弱证据**而非剔除：无强证据时行为逐字节同旧写法（`_record_pos` 强弱分级），故本支只可能纠正锚点，不会把「无法判断」变成「报警」。判据测试 `verify/tests/test_q_anchor_label_evidence.py`（含 standalone 反向守卫与「纯回指不锚位」两向）。跨书 A/B 普查（23 本 Q-enabled 书 / 282 个章×语言单元，`<chaos>/_extract/_census_q_anchor.py` old/new 双跑 + `_diff_q_anchor.py`）：**ORDER_MISMATCH 净减 6 条、新增 0 条；MISPLACED 0/0；FABRICATED / MISSING 零漂移**（减掉的 6 条全为本书 1.2.11 / 11.1.5 / 12.7.5 ×中英两版）。
  - 🔴 **原书重印同一编号 → 第 2..limit 枚 `\tag` 不参与倒挂比较**（`_dup_beyond_source`/`label_limit` 同一账，2026-09-29 Apostol IANT ch3 §3.11 根治）：印面把已编号的恒等式在后续推导里**原样重排并再印一次右缘编号**（Apostol 页 78 印 `(16)(17)(18)`，页 79 Theorem 3.13 结尾又重排 identity 并印 `(17)`；`page_079.json` block 9 独立标签块 + fitz 300dpi 目视双证），总结忠实挂两枚 `\tag{17}`（重复检测早已由 `label_limit` 放宽）。旧顺序支拿第二枚 17 比**首次**位置（页 78），而游标已推进到 (18)（同页更后的块）→ 必判倒挂（假阳）。修法：出现次序 ≤ 书里印过该号的**不同页数**时跳过比较且**不回退游标**；`label_limit` 无记录返回 1，故未重印的书逐字节不变，超出印面次数的重复、以及无重复的真倒挂照旧报（判据测试 `verify/tests/test_q_layer_reprint_order.py`，含三条负向守卫）。**跨 51 书普查**（`<Apostol>/_extract/_census_q_reprint_tags.py` → `_census_q_reprint_tags.txt`）：全库只有 4 书的总结在同一顺序窗口内重用过同一 `\tag`、合计 16 处（Apostol 2 / Weibel 2 / 阿诺尔德 3 / 高等代数 9）——本支可能生效的上界即此 16 处，其余书零影响。
- **小节定位校验（WARN，永不阻断）**：
  - `q_misplaced`(MISPLACED)：总结公式所在 `## §N.M` 小节与书源定义小节非前缀兼容 → 仅 WARN。判定用"前缀兼容"；`scope==3` 下改走**证据驱动**三段式（2026-09-29 Apostol IANT ch5 / Lee ch7 根治）：
    1. **书趟自身同意**（最强证据）：`(sec, n) ∈ _pos_sec` —— 趟按块序推进节桶，能分辨「节在页中间起头」，书与总结把该号归到同一节即谈不上放错；
    2. **页跨回退**：仅当无节内位置记录时用整页跨度 `[start(sec), start(next)]`（**含**下一节起始页——页级粒度无法定位页内起点，Apostol 页顶书眉 `5.4: 节名` 早于本节末式，边界页必须算在跨内）核 `(n)` 的在册页；范围内任何命中 = 放置正确；
    3. 🔴 **无证据不判**：`start(sec)` 从未被记录（节头 OCR 不匹配 / 该页被判目录页 → 节游标卡在首节）**或**该号在全书无任何位置记录（只作回指出现，或来自 `formula.known_book` 白名单）→ **跳过不判**。旧写法把「证据缺失」当成 `not in_range` 直接开报，节游标一卡就整章刷屏（Apostol ch5 24/24、Lee ch7 16/16 全是此类假 MISPLACED）；plain 路径早就是同款「`book_section` 有值才判」约定，本节级路径是唯一的例外，现已对齐。判据测试 `verify/tests/test_q_layer_misplaced_evidence.py`。
    4. 🔴 **重启复用感知跳过**（`_reset_on_section_misplaced` 末段 + `_spanned_section_count`，2026-10-09 Evans 根治 + 全库 scope==3 普查）：前三段都过了（自述否、节内桶无记录、有节跨、该号在册、但**本节点跨内查无该号页**）时，仍有一类假阳——**裸号跨节复用**。`scope==3` 书每个 `## §N.M` 都把编号重启到 1，于是 `_n_pages['1']` 是全书**所有节**独立印出 `(1)` 的页之并集，页级粒度根本无法指认「总结这枚 `\tag{1}` 属于哪一节」。判据：若该号的独立标签页**横跨 ≥2 个不同的总结节页跨**（`_spanned_section_count(src, n) >= 2`）→ 页证据无法把归属缩到唯一节 = 又一个「无法证明放错」→ **跳过不判**。真放错在编号**唯一属于一个页跨**时照判：多分量号 `(2.5.12)`/`(8.11a)` 天然只落一节（count==1），恰好只出现在一节的裸号也 count==1，越界即报。**单调**：本段只在「OLD 会报」的前提上追加一道复用豁免，永不新增 MISPLACED；仅作用于 scope==3 节级路径，FABRICATED/MISSING/ORDER 三支与 plain 路径一字未动。跨书普查（20 本 scope==3 + 3 本 scope==2 控制）实测 helper 命中 6221 次、OLD 报 7 条 / NEW 报 0 条、ADDED=0、7 条被移除的全 spanned≥2、真错位吞 0 条、scope==2 控制调用 0 次——7 条全为 Evans 中文侧 ch2/ch4/ch5/ch6/ch8 的裸号假阳。判据测试 `verify/tests/test_q_layer_misplaced_recurrence_skip.py`。
- 🔴 **预检噪声门：agnostic 命中须有「标签位置证据」（`agnostic_label_evidence`，2026-09-29 阿诺尔德附录F/J 根治）**：配置预检（`_validate_formula_config`）的判据①「configured 抽不到 + agnostic 抽得到 = depth/scope 配错 → ERROR」依赖 agnostic **并集**模式，而该并集含裸 `N.M` 形态（`bare_number` 为 `true` 时），于是 OCR 粘连串（`p2j-1926-2+…`→`1926.2`）、坐标/参数表（`(1,0)`、`(5,9g`）都会被记成「书里确有公式编号」，把本该走「S 为空降级」的结构检查抬成阻断 ERROR。修法：仅当 `nums` 里**至少一枚号确实印在公式编号的位置上**（形态① 独立标签块，或形态② 数学块行尾、且行尾守卫与抽取侧**共用同一个** `_tail_pre_guard`）才保留 ERROR；块中间的括号数字一律不算证据；无位置证据 → 不阻断，交「S 为空降级」WARN 走人工对账。检测趟与修复趟同判据（判据只此一份）。
- 🔴 **目录页签名按「去重后的节号」计数**（`_is_toc_page`，2026-09-29 Apostol IANT ch5 p121 根治）：旧写法数**块**（`_titled_heads >= 4`），而 OCR 常把同一节头读成两遍（页顶书眉 `5.4: 节名` + 正文标题 `5.4 节名`）再混入两三行散文回指（`5.7 If` / `5.8 We`），于是**带 80 个显示公式块的纯正文页**被判成目录页整页跳过。真正的代价不是少收几枚编号，而是**节游标永远停在首节**——标题推进支只认「紧邻下一节」（防路线图页把 cur 提前，见 Ross Bug #23），错过唯一一次 0→1 推进后，其后每节都落回同一桶，`_sec_start_page` 只有首节 → 全章 MISPLACED 刷屏。真目录页列的是互不相同的节，去重后仍 ≥4，判据强度不降。跨书普查（15 本 scope==3 书 / 313 个旧签名页）只有 2 页翻转 = Apostol p121 与 Lee p312（`26.1/26.2` 习题头 + `26.3` 重影），Lee ch7 的 FABRICATED/INCONSISTENT/MISSING 三类阻塞行改前改后恒为 0，仅 16 条无证据 MISPLACED 消失。
- **build_sectioned 节推进信号（2026-08 收紧）**：`C.S-1` 推进标记只接受**剥离后行首**且后随空白的形态（真实条目标题形如 `9.3-1 Definition (Monotone sequence). ...`）；行中引用（`(cf. 9.9-1)`、`theorem 4.2-1 (variants`）与 OCR 断行残块（行首 `9.2-1), and ...`）一律不再触发。Strogatz 式标题路径（`_HEAD_RE` + 顺序 +1）排除 `N.M-K` 条目形态与行首 `N.M)` 括注断行，防止把条目续行当标题。
- **作用域化 ignore 键**：per-chapter ignore 文件的键可为裸编号或 `'<sec>#<num>'`（如 `'9.8#17'`）——后者只在该节内静默该编号。节级重置书中每个裸编号在全章各节复用，章级忽略会连累其他节的合法 `\tag{n}` 校验；浓缩省略类豁免一律优先用 scoped 键并附理由。
- **公式内容校验（人工对账）**：`verify_all` 末聚合各章 `q_rows` 写出 `<extract_dir>/formula_audit.md`，并排列出「总结 LaTeX / 书源文本片段」，机器**不判内容对错**。
- **S 为空降级**：若派生正则未抽到任何编号（S 空，绝大多数是 `formula` 的 `type`/`scope`/`lead` **配错**——例如把字母章位 `(A.3)` 或罗马章位 `(II.5)` 的书按纯数字家族配置，括号内核匹配不到首段），仅做结构检查（重复/章节前缀/规范），emit 一条 WARN，**不判编造/遗漏 FAIL**。字母章位 `(A.3)`（`letter_ch: true` 或 `type: 15`）与罗马章位 `(II.5)`（`type: 16` / `lead='roman'`）**均已支持**：书若正确配置对应 lead，这类编号照常机器校验、不进本降级支；只有当**数字家族**的书源里检出字母/罗马编号时，`_detect_letter_led_formulas` 才 emit 一条 mis-config WARN，提示按家族补 `letter_ch`/`type:15` 或 `type:16` 后重跑。🔴 **仅 `head` 不在本书章键集（书外附录交叉引用）才豁免**；**本书附录/补篇章键在册不豁免**——它恰是最可能漏配 `letter_ch` 的当事章，附录自己是数字家族配置、`(A.36)` 印面无人校验时，本提示正是唯一线索（2026-10-08 删除曾一度误加的「属本书附录/补篇章键即排除」分支；该分支会把探针判死到「字母头须是普通章键」，而字母头几乎只在附录出现）。**仅多字母词前缀（`App.2` / `Ap.3`）无对应 lead 家族**，仍作「暂不校验、须人工核对 formula_audit」的 WARN。**（探测正则已收紧：只认短字母/罗马前缀 + 点`·`分隔的真公式编号，不再误匹配 `(n-1)` 代数式与 `(Fig.)/(Chap.)/(Prob.)` 引用——旧正则曾使纯数字编号书（如 Kreyszig）每章被误 BLOCK。）**

## 本阶段规则（阻断性 / 可修复）
- FABRICATED / INCONSISTENT → 始终 FAIL（阻断）。
- MISSING（未在 `formula.ignore` 登记）→ FAIL（阻断）；已登记 ignore 的编号不计入 MISSING。
- ORDER_MISMATCH / MISPLACED → 仅 WARN，永不阻断（OCR 位置/标题噪声下不误 FAIL）。
- 不可 `--fix`（审计层，须回写作阶段修正编号）。

## 出口条件
FABRICATED / INCONSISTENT 非空 → 整章 FAIL；未在 `formula.ignore` 登记、MISSING 非空 → 整章 FAIL；ORDER_MISMATCH / MISPLACED 仅 WARN。

## 相关代码（`verify/formula_tag/script/formula_tag.py`）
- `code = 'Q'`，`order = 17`（当前最大层 P=16 之后），`auto_fixable = False`。
- 经 `verify/script/register_all.py` 用 `importlib` 按裸名扫描 `verify/*/script/` 自动发现注册，**无需改 register_all.py / VerifyManager / CLI**。
- `build_formula_patterns(ncomp)`：按 `depth`（由 `type` 经 `ORDINAL_DEPTH` 派生）生成源抽取正则（单捕获组、`depth` 决定分量数）。
- 行尾标签判据三件套（全库唯一真源，`text[]` / `formulas[].latex` / 预检噪声门共用）：`tail_label_match(txt)`（形态② 完整判据，返回 Match 或 None）→ 内部调 `_tail_pre_guard(raw_pre)`（左邻守卫，**入参须未剥尾随空白**）；`latex_tail_token` / `latex_label_candidates` 是其 latex 侧薄封装；`agnostic_label_evidence(ext_dir, ch, start, end, nums)` 是预检侧的位置证据门。改口径只改 `tail_label_match` + `_tail_pre_guard`，不要在调用方复制判据。
- `SourceFormulaIndex.norm()`：去空白/去外层 `（）()`/去 `Eq.`·`Equation`·`式` 前缀；把 `.\-·,` 任一分隔符归一为 `.`；**折叠末尾字母后缀(a)**（如 `5.1.3a`→`5.1.3`）。折叠后缀只为「书源子式 `(8a)`/`(8b)` 与汇总结点 `\tag{8}` 对齐」的 S 成员 / MISSING / FABRICATED 比对；**INCONSISTENT 重复检测另用 `norm_full()`（保留后缀）**，使 `(5.1.3a)`/`(5.1.3b)` 这类真实子式不被误判为重复 `\tag`。无字母后缀的书 `norm_full == norm`，故该改动对纯数字编号书零回归。例 `（11.1-1）`→`11.1.1`，`Eq. 2.3`→`2.3`，`2.3a`→`2.3`。
- `LayerResult` 返回的 5 个 `q_*` 键须与 `DEFAULT_RESULT`、本 `contract-keys`、以及 `report.py` 读取完全一致（由 `verify/tests/test_key_contract.py` 强制校验）。

## 子流程
无独立子脚本；`SourceFormulaIndex` 与 `build_formula_patterns` 在本层脚本内。

## 需 agent 手工修复（manual fix）
本层 `auto_fixable = False` 且 **opt-in**——总结里带 `\tag{X}` 的公式，其序标必须与
**书源公式编号集合 S** 1:1 对应；编造/错位/跨章须人工核对书源，脚本不臆造编号。

- **前置（缺一不可）**：`verify_config.json` 须配 `formula` map（`type`/`scope`），
否则 Q 层静默 no-op（见本层顶部警告）。看到 `[Q-LAYER WARN]` 必须补全配置，禁止宣称公式校验通过。附录字母章位编号须 `formula.letter_ch: true`（落在外层 map 的 `appendix` 段；`make_config` 重生成即自动写入——手写 config 无效）。
- **触发门（report.py）**：`Q-LAYER FORMULA FABRICATED` / `Q-LAYER FORMULA INCONSISTENT` → 始终 FAIL；
`Q-LAYER FORMULA MISSING`（未登记 ignore）→ FAIL（阻断）；`Q-LAYER FORMULA ORDER_MISMATCH` / `Q-LAYER FORMULA MISPLACED` / `Q-LAYER FORMULA TAG_MISMATCH` → 仅 WARN（非阻断）。
- **修复步骤**：
  1. `FABRICATED`（总结 `\tag` 编号不在 S → 编造/串号）→ 回源核对，删掉或改正 `\tag`。
  2. `INCONSISTENT`（重复/跨章）→ 修正 `\tag` 使其唯一且属本章。
  3. `MISSING`（FAIL，阻断）→ 书源确有该编号但属合法省略（如排版重复）时加入 `formula.ignore`；否则补写该公式并挂 `\tag`。未登记 ignore 的遗漏一律阻断以防漏写。
  4. `ORDER_MISMATCH`（WARN）→ 总结中公式列举顺序与书源阅读顺序不符（串位/偏移）→ 核对并调整 `\tag` 出现顺序使其与书源一致。
  5. `MISPLACED`（WARN）→ 公式 `\tag` 所在小节与书源定义小节**非前缀兼容**（标号挂错节）→ 把该 `\tag` 移到正确的 `## §N.M` 之下（注意：书源定义于更深子节如 §N.M.K、总结置于其祖先节 §N.M 视为正确，无需移动）。
  6. `TAG_MISMATCH`（WARN）→ **同号配错式**：`\tag{X}` 的正文与印面 (X) 的中式子不符，而与**另一号** (Y) 高度相符（成因：印面某展示式漏贴标签 → 后续 `\tag` 整体错位一格；或给印面无号展示式补了一枚号）。集合成员 / `ORDER_MISMATCH` / `MISPLACED` 与章级契约 tag 对账**都看不见这类缺陷**（号集合仍完整、顺序仍单调），故只由此配对探针报出。修复：按印面逐条把号挂回各自式子（含改写正文里的交叉引用），**源/译两套单元都要改**，改后重拼再 verify。判据实现在 `verify/formula_tag/script/tag_formula_pairing.py`（`norm_math` 归一 + `difflib` 相似度）；🔴 **fail-open 八支**（缺一即假阳，51 书普查逐条印面取证标定）：账本 <3 条 / 号在书侧无载体 / 正文归一化过短 / 两侧均配不上（内容改写）/ **箭头词表占比 ≥0.5**（交换图被 OCR 读成 `stackrel…longrightarrow` 一类的命令名串，账身没有可比内容）/**对手号一侧的账身下限与正文对称**（`min_body`，残段不能当「另一枚号的载体」）/**同式误读豁免**（`_containment(own, 正文) ≥ 0.90`）/**两格同式**（`_containment ≥ hi` 双向）；另有两支结构性豁免——**单分量编号书（`ncomp==1`）整族不判**（Arnold 7/7、Apostol 16/16 全假阳且无真缺陷可标定），以及**归属仲裁 + 账本判别力闸**（对手号那一格自己已配对，或对手号账身与别的号也高度相似 → 无证据不判）。
     - 🔴 **静音一律发生在判据侧，不得改账本归属**（2026-10-04 回退过一次实测）：`printed_tag_bodies` 保持「最近标签 Voronoi + 逐字去重」的书侧可核对原样；曾试过按 `\\` 拆行 / 聚类重复读取来「修正」多行 array 的归属，结果 Koopman (5.32) 照旧开报而 **Lee ch9 (9.25) 的真移位反而整条消失**（真移位的铁证正是「自己那号只剩残段 + 交付与邻号逐字相符」，动归属就把它一起抹掉）。
     - 🔴 **判假阳之前先做两侧字形转写对账**（同一轮实测）：Koopman 12 行与 Katok (9.3.2) 全部是**书侧转写差异**，不是配错号——① 旧式字体开关 `{\bf x}` vs `\mathbf{x}`、哥特体 `\mathfrak{p}` vs `\mathbf{p}`、定界符 `\lvert…\rvert`/`\lVert` vs 裸 `|`/`\|`（→ 补进 `_SHELL_CMDS`）；② `\varPhi`/`\varphi` 与 `\Phi`/`\phi` 是同一枚字母（→ `_VAR_GREEK` 折叠）；③ **印面 `x^{\prime}` vs 交付 `x'`**——裸 `'` 被 `_NON_ALNUM` 抹掉而 `prime` 留五个字母，把 r=1.00 的同一条式子压到 0.45（→ `\prime`/`\nolimits`/`\strut` 补齐）。Koopman 另有两类纯账本 artifact：OCR 切出的 <`min_body` 残段冒充邻号载体（(5.32)/(16.24)），以及同一行式子被读成不等长的两账（(16.40)/(16.41)、(2.4)/(2.5) 两行共用一个 array）→ 由「两格同式」包含度支静音。
     - **普查标定**（`tools/q_tag_mismatch_census.py`，hi=0.80 / min_body=12，51 书 / 519 章有账）：**34 行（2026-10-03 基线）→ 21 行（字形折叠 + 对手侧下限）→ 19 行（`\prime` 折叠）**。动力系统书架 9 书现 **0 行**（Koopman 12→0、Katok 2→0）。保留的 19 行分布：Elliptic PDE 8（ch4/ch5 整格移位链）、Lee ISM 4（ch4 (4.5)、ch9 (9.25)）、analytic-NT 4、概率论 2、数值分析 1——均为**其他书架**的真缺陷或待裁决，不是判据放宽的产物。包含度阈值 0.90 的下界由 Lee (9.25) 的印面残段（对交付整式包含度 0.818~0.800）钉住，上界由 Koopman (5.32)（同式误读 1.000）钉住；0.80~0.90 区间普查无第三方样本。判据测试 `verify/tests/test_q_tag_formula_pairing.py::TestBookSideArtifactGates`（每支都带「关掉它就必须复现原假阳」的反向钉）。
     - ⚠️ 普查/探针**崩溃时照样打印 0 行**：必须核对 footer 的「N 章实际有账」与 `[SKIP]`/`探针未跑成` 行，0 行 ≠ 判据通过。
  7. S 为空降级（配置错）→ 回头修正 `formula` 的 `type`/`scope`（实为 `type` 派生错）让书源抽到编号，不要当成"通过"。
  8. 重跑 verify，确认 FABRICATED / INCONSISTENT 为空（WARN 项按需清理）。

修复后重跑 `verify_chapter.py --all`（或单章 `<ch> <start> <end> <md> <ext>`）确认上述门为空 / 转绿。

## 字节契约键
```contract-keys
q_checked
q_fabricated
q_inconsistent
q_missing
q_order_mismatch
q_misplaced
q_tag_mismatch
q_letter_led
q_rows
```
