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
  - `type`：**digit 家族**沿用 ORDINAL_* 风格码 `1`/`2`/`3`（`depth`=分量段数由 `type` 经 `ORDINAL_DEPTH` 派生：单分量→`1`、两段→`2`、三段→`3`；弃用码 `4`/`9`/`10`/`11` 已退役）；**alpha 家族**用 formula-only 专用码 `15`（字母二级 `(A.3)`）/ `16`（罗马二级 `(II.5)`），它们不进 `ORDINAL_CODES`/`ORDINAL_DEPTH`。**lead 与段数一律经 `resolve_formula_type(type, letter_ch)` 派生**，`depth`/lead 不再单独配置。legacy 字母书写 `type: 2 + "letter_ch": true` 亦可。`ORDINAL_SECTION_TYPES` 是小节层级反推，与 formula 的 `depth` 无关。
  - `scope`：1=book / 2=chapter / 3=section——编号重置窗口；**跨章守卫**（首分量 ≠ 当前章号判 INCONSISTENT）当且仅当 `scope == 2` 开启，book/section 作用域关闭该守卫。
  - `ignore`：要跳过 1:1 比对的归一化公式编号列表（既不判 FABRICATED 也不判 MISSING）。支持两种键形态：裸编号（全章生效）与 `'<sec>#<num>'` 作用域键（仅该节生效，见上）。
- **scope/depth 耦合不变量（`depth`/lead 由 `type` 经 `resolve_formula_type` 派生；`scope` 独立）**：scope:3⇒`type 1`(depth 1，节级裸`(N)`)；scope:2⇒章级带前缀的多段编号（digit `type 2`/`type 3` = depth 2/3，或字母章位 `(A.3)`/罗马章位 `(II.5)` 的 formula-only `type 15`/`type 16`，含 legacy `type 2 + letter_ch:true`）；scope:1 通常 `type 1` 全局连续。违反即非法，`require_complete` 应拒。（弃用码 4/9/10/11 早已退役，不存在「`type≥4`」。）
- **书源编号抽取**：`SourceFormulaIndex.build()` 遍历 `page_{start:03d}.json .. page_{end:03d}.json`，对每页 `text[].text` 用**由 `type` 派生的 `depth`** 正则抽编号（`build_formula_patterns(ncomp)` 覆盖 `（1.17）`/`(1.17)`/`Eq. 1.17`/`Equation 1.17`/`式（1.17）`/裸 `1.17` 六种变体，每式单捕获组），`norm()` 归一后归入本章集合 S。**只读 text**；`formulas[].latex` 仅在一条守卫下参与——latex **以括号包裹的 `(C.N)` 开头**（OCR 把显示公式连同其编号捕获为 latex 首 token 的形态，如 Han–Lin `(4.3) \quad …`，此时编号从未落进 `text[]`，漏收会使总结忠实的 `\tag` 被误判 FABRICATED）才交给同一 `_scan_text` 管线；普通数学不会以 `(\d+.\d+)` 开头，不会把代数噪声混进 S（2026-09-09）。
  - 🔴 **编号 token 的正则核属于 `lib.numbering.formula_num_core`（唯一真源）**：本层抽书源编号、`attach_content` 给公式挂 `tag`、`check_content_completeness` 做序标独立真值，三处共用同一套形态（段数由 `formula.type` 经 `ORDINAL_DEPTH` 派生；分隔符 `. - · ,`；可选字母后缀；`letter_ch` 时首段为单个大写字母）。**改形态只改 `lib/numbering.py`**，否则三处口径漂移会互相判对方"漏/编造"。
  - 实测形态差异极大，**不可假设 `(C.N)`**：约半数书右缘编号**不带括号**（Kreyszig / Evans SDE / PDE / Ross / 随机过程 / 解析数论），另有 `11.1-1` 连字符三段、`8.11a` 字母后缀、字母章位 `(A.3)`（Lee ISM 附录）等。编号还可能排在公式**左缘**（Kreyszig / 解析数论 / PDE）而非右缘。
  - 🔴 **字母章位编号（`formula.letter_ch: true`，2026-09-14 落地）**：`(A.3)` / `（B.12）` 形态（Lee 附录 B.1-B.15 / C.1-C.21 / D.1-D.21 实测）。patterns/norm 接受单个大写字母首段（`norm('（A.03）')`→`'A.3'`）；`scope==2` 跨章守卫用字母首分量对比章键（`'B'`）直接工作；**裸排变体在该模式下永不启用**（裸 `A.3` 与 `Fig. A.3` / 小节标题 `C.1` 无形态区别）。`make_config.detect_formula` 对页区间 letter-led 形态占优（≥30 次行尾命中且压过 digit）时自动写 `"letter_ch": true` 并按字母章回退判定 scope。
  - 🔴 **formula-only lead 命名空间（digit / letter / roman，2026-10-01 解耦）**：字母二级 `(A.3)` 除 legacy `type:2 + letter_ch:true` 外有专用码 **`type: 15`**；罗马二级 `(II.5)` / `(I.5)` 有专用码 **`type: 16`**（`lead='roman'`，`make_config.detect_formula` 见**多字母罗马证据**且**无非罗马字母头**时自动选）。这两个码**刻意不进** `ORDINAL_CODES` / `ORDINAL_DEPTH`——条目侧 `verify_config` 的 ordinal 组校验（`t not in ORDINAL_CODES` 即抛 ConfigError）**天然拒绝**它们，两套 type 空间互不知晓，故新增公式体例绝不污染条目体例判定。三个 lead 家族一律经**唯一入口** `lib.numbering.resolve_formula_type(type, letter_ch) → (lead, ncomp)` 取形态，消费方**禁止**各自再判 `letter_ch` 或反查 `ORDINAL_DEPTH`（口径漂移会互相判「漏挂/编造」）。**形态互斥**由 `formula_num_core` 保证：digit 核首段必 `\d`、letter 核首段恰**单个** `[A-Z]`（故 `II.5` 不被 letter 命中——首字母后紧跟的是字母不是分隔符）、roman 核首段 `[IVXLCDM]{1,5}`（故 `A.3` 不被 roman 命中——`A∉IVXLCDM`）；alpha-led（letter/roman）**永不**发裸排变体。唯一残留歧义是**单字母罗马头**（`I.`/`V.`/`X.`/`L.`/`C.`/`D.`/`M.` 既是字母又是罗马）——由**整本书只配一个 lead** + `detect_formula` 保守择族消解（只有多字母罗马证据才选 roman，否则保持 letter，宁缺勿滥）。判据测试 `config/verify_config/tests/test_formula_lead_decoupling.py`。仅**多字母词前缀**（`App.2` / `Ap.3`）无对应 lead 家族，仍 `q_letter_led` WARN。
  - 🔴 **形态②「块尾标签」的唯一判据 = `tail_label_match`（`text[]` 与 `formulas[].latex` 共用，2026-09-29 落地）**：一个块算「以印刷编号收尾」必须同时满足 ① 剥掉尾随空白后以 `(N)`（可带句点）收尾；② 那对括号**不是函数/群的参数表**——由 `_tail_pre_guard(左邻原文)` 判定。判据**吃未剥空白的左邻**：「括号左边有没有空格」本身是判据（剥掉则 `a = 1 (1)` 与 `c_1(2)` 不可区分，一刀切拒数字会把整章右缘标签全判掉——Kreyszig 回归实测）。拒收：与括号**黏着**的左邻是字母/数字/CJK/`\`（`f(x)`、`c_1(2)`、`式(3)`、`SO(3)`、`\sin(2)`）；剥空白后以 **CJK 或 `\`** 收尾（`见式 (3)` 型中文交叉引用）；左侧 **≥2 个连续单大写字母 token**（`\boldsymbol { X }` 类字体壳按一个字母计）= `S O ( 3 )` / `T S O ( 3 )` 型李群记号（阿诺尔德 ch8+附录E 实测 33 条被收进 S，制造两处假 MISSING）。放行：隔空白的**单个** token（`f(x) \le M (9)` 单字母、`b = 2 (2)` 数字）。已知取舍：latex **命令名**隔空白（`\phi ( 2 )`）在放行侧——它与真空标签 `\quad (8)`、`\circ (3)` 形态不可分，实测噪声里无此形态，故不加函数名白名单（命令**黏着**括号时仍由 ① 拒收）。测试 `verify/tests/test_q_tail_label_space_glue.py`。
  - 🔴 **单段编号（`depth<=1`）不收字母后缀**（2026-09-28 Apostol《解析数论导引》ch11 根治）：子式后缀编号 `(8.11a)` 在实测语料里**只出现在多段体例**（Evans SDE/PDE、Koopman、Ross、A First Course in Numerical Methods、Chaos/Fractals/Noise 全部 `depth>=2`）；单段书里孤立的 `(2s)`/`(6s)`/`(9x)` 是**公式被截成独立块**的碎片（Apostol p243/p253/p259 的 `(2s)`/`(6s)` 与 ζ(2s) 同行，同型还有《数学分析》type=1 的 `0x/1D/2M/3w/4m/9x`）。收下它们＝契约多出一条不存在的 tag，而单元 tag 对账是硬闸 → 逼写手凭空造 `\tag{2s}`。判据在 `formula_num_core`（三处消费方同口径），测试 `lib/tests/test_formula_num_core_suffix.py`（含多段后缀书零回归正例 + 碎片负例）。`ncomp=None`（未配置）与 `letter_ch`（字母章位）分支不受影响。
- **序标校验（自动 FAIL）**：
  - `q_fabricated`(FABRICATED)：总结 `\tag` 编号归一后**不在 S**（编造/串号）→ 始终 FAIL。
  - `q_inconsistent`(INCONSISTENT)：编号**重复**，或**跨章**（`scope == 2` 时首分量 ≠ 当前章号）→ 始终 FAIL。
- **遗漏校验（未登记 `formula.ignore` 时阻断 FAIL）**：
  - `q_missing`(MISSING)：S 中属于本章、规范、前缀匹配的编号在总结无对应 `\tag` → **FAIL（阻断）**。writing-rules 硬性要求 7 规定书源所有带编号公式（含描述性散文中的推导式）都必须保留，故"未登记的遗漏"即"漏写公式"。书源确有该编号但属合法省略（如纯排版重复）时，把它加入 `formula.ignore` 跳过比对；未在 `ignore` 登记的遗漏一律阻断，以防漏写描述性推导公式。
  - 🔴 **章末集中习题块不入 S（`_in_exercise_tail`，2026-09-27 Strogatz 3e ch13 根治）**：`build` / `build_sectioned` 的页循环先读分章契约，取 `consolidated: true` 节点的**最小叶号**，该页及其后一律不扫。理由：writing-rules「有专门习题小标题的集中习题块一律省略」+ `unit_node_entries` 对 `consolidated` 节点**不出单元** → 该块内容按设计不进总结，而印面确实带右缘编号（实测题 13.6.5 Ott-Antonsen 有 `(13)`p553 y=250、`(14)`p553 y=507），旧行为把 `(14)` 收进 S 后 MISSING 硬闸反过来要求写手把习题解答写成正文公式（只能靠编造上下文满足）。契约无 `consolidated` 标记的书（节末习题、无集中块）行为逐字节不变，判据测试 `verify/tests/test_q_layer_consolidated_exercise_tail.py`（含正/反两向控制）。
- **序列顺序校验（WARN，永不阻断）**：
  - `q_order_mismatch`(ORDER_MISMATCH)：总结文档序与书源阅读序不一致 → 仅 WARN。`scope==3`（节级重置，编号每节重复）时按 `## §N.M` 窗口独立判定，且比较用 **per-(sec,n) 节内首现位置**（`_pos_sec`）——重复编号的全局首现位置恒来自最早含 `(n)` 的节，跨节比较必产生噪声（2026-08 Kreyszig 实测）；某 tag 无节内位置记录（其独立标签被 OCR 并行/丢失）时**跳过该 tag 的顺序判定**（既不判倒挂也不更新游标）。`scope==2/1` 时窗口跨节、沿用全局首现位置。
  - 🔴 **原书重印同一编号 → 第 2..limit 枚 `\tag` 不参与倒挂比较**（`_dup_beyond_source`/`label_limit` 同一账，2026-09-29 Apostol IANT ch3 §3.11 根治）：印面把已编号的恒等式在后续推导里**原样重排并再印一次右缘编号**（Apostol 页 78 印 `(16)(17)(18)`，页 79 Theorem 3.13 结尾又重排 identity 并印 `(17)`；`page_079.json` block 9 独立标签块 + fitz 300dpi 目视双证），总结忠实挂两枚 `\tag{17}`（重复检测早已由 `label_limit` 放宽）。旧顺序支拿第二枚 17 比**首次**位置（页 78），而游标已推进到 (18)（同页更后的块）→ 必判倒挂（假阳）。修法：出现次序 ≤ 书里印过该号的**不同页数**时跳过比较且**不回退游标**；`label_limit` 无记录返回 1，故未重印的书逐字节不变，超出印面次数的重复、以及无重复的真倒挂照旧报（判据测试 `verify/tests/test_q_layer_reprint_order.py`，含三条负向守卫）。**跨 51 书普查**（`<Apostol>/_extract/_census_q_reprint_tags.py` → `_census_q_reprint_tags.txt`）：全库只有 4 书的总结在同一顺序窗口内重用过同一 `\tag`、合计 16 处（Apostol 2 / Weibel 2 / 阿诺尔德 3 / 高等代数 9）——本支可能生效的上界即此 16 处，其余书零影响。
- **小节定位校验（WARN，永不阻断）**：
  - `q_misplaced`(MISPLACED)：总结公式所在 `## §N.M` 小节与书源定义小节非前缀兼容 → 仅 WARN。判定用"前缀兼容"；`scope==3` 下改走**证据驱动**三段式（2026-09-29 Apostol IANT ch5 / Lee ch7 根治）：
    1. **书趟自身同意**（最强证据）：`(sec, n) ∈ _pos_sec` —— 趟按块序推进节桶，能分辨「节在页中间起头」，书与总结把该号归到同一节即谈不上放错；
    2. **页跨回退**：仅当无节内位置记录时用整页跨度 `[start(sec), start(next)]`（**含**下一节起始页——页级粒度无法定位页内起点，Apostol 页顶书眉 `5.4: 节名` 早于本节末式，边界页必须算在跨内）核 `(n)` 的在册页；范围内任何命中 = 放置正确；
    3. 🔴 **无证据不判**：`start(sec)` 从未被记录（节头 OCR 不匹配 / 该页被判目录页 → 节游标卡在首节）**或**该号在全书无任何位置记录（只作回指出现，或来自 `formula.known_book` 白名单）→ **跳过不判**。旧写法把「证据缺失」当成 `not in_range` 直接开报，节游标一卡就整章刷屏（Apostol ch5 24/24、Lee ch7 16/16 全是此类假 MISPLACED）；plain 路径早就是同款「`book_section` 有值才判」约定，本节级路径是唯一的例外，现已对齐。判据测试 `verify/tests/test_q_layer_misplaced_evidence.py`。
- 🔴 **预检噪声门：agnostic 命中须有「标签位置证据」（`agnostic_label_evidence`，2026-09-29 阿诺尔德附录F/J 根治）**：配置预检（`_validate_formula_config`）的判据①「configured 抽不到 + agnostic 抽得到 = depth/scope 配错 → ERROR」依赖 agnostic **并集**模式，而该并集含裸 `N.M` 形态（`bare_number` 默认开），于是 OCR 粘连串（`p2j-1926-2+…`→`1926.2`）、坐标/参数表（`(1,0)`、`(5,9g`）都会被记成「书里确有公式编号」，把本该走「S 为空降级」的结构检查抬成阻断 ERROR。修法：仅当 `nums` 里**至少一枚号确实印在公式编号的位置上**（形态① 独立标签块，或形态② 数学块行尾、且行尾守卫与抽取侧**共用同一个** `_tail_pre_guard`）才保留 ERROR；块中间的括号数字一律不算证据；无位置证据 → 不阻断，交「S 为空降级」WARN 走人工对账。检测趟与修复趟同判据（判据只此一份）。
- 🔴 **目录页签名按「去重后的节号」计数**（`_is_toc_page`，2026-09-29 Apostol IANT ch5 p121 根治）：旧写法数**块**（`_titled_heads >= 4`），而 OCR 常把同一节头读成两遍（页顶书眉 `5.4: 节名` + 正文标题 `5.4 节名`）再混入两三行散文回指（`5.7 If` / `5.8 We`），于是**带 80 个显示公式块的纯正文页**被判成目录页整页跳过。真正的代价不是少收几枚编号，而是**节游标永远停在首节**——标题推进支只认「紧邻下一节」（防路线图页把 cur 提前，见 Ross Bug #23），错过唯一一次 0→1 推进后，其后每节都落回同一桶，`_sec_start_page` 只有首节 → 全章 MISPLACED 刷屏。真目录页列的是互不相同的节，去重后仍 ≥4，判据强度不降。跨书普查（15 本 scope==3 书 / 313 个旧签名页）只有 2 页翻转 = Apostol p121 与 Lee p312（`26.1/26.2` 习题头 + `26.3` 重影），Lee ch7 的 FABRICATED/INCONSISTENT/MISSING 三类阻塞行改前改后恒为 0，仅 16 条无证据 MISPLACED 消失。
- **build_sectioned 节推进信号（2026-08 收紧）**：`C.S-1` 推进标记只接受**剥离后行首**且后随空白的形态（真实条目标题形如 `9.3-1 Definition (Monotone sequence). ...`）；行中引用（`(cf. 9.9-1)`、`theorem 4.2-1 (variants`）与 OCR 断行残块（行首 `9.2-1), and ...`）一律不再触发。Strogatz 式标题路径（`_HEAD_RE` + 顺序 +1）排除 `N.M-K` 条目形态与行首 `N.M)` 括注断行，防止把条目续行当标题。
- **作用域化 ignore 键**：per-chapter ignore 文件的键可为裸编号或 `'<sec>#<num>'`（如 `'9.8#17'`）——后者只在该节内静默该编号。节级重置书中每个裸编号在全章各节复用，章级忽略会连累其他节的合法 `\tag{n}` 校验；浓缩省略类豁免一律优先用 scoped 键并附理由。
- **公式内容校验（人工对账）**：`verify_all` 末聚合各章 `q_rows` 写出 `<extract_dir>/formula_audit.md`，并排列出「总结 LaTeX / 书源文本片段」，机器**不判内容对错**。
- **S 为空降级**：若派生正则未抽到任何编号（S 空，绝大多数是 `formula` 的 `type`/`scope`/`lead` **配错**——例如把字母章位 `(A.3)` 或罗马章位 `(II.5)` 的书按纯数字家族配置，括号内核匹配不到首段），仅做结构检查（重复/章节前缀/规范），emit 一条 WARN，**不判编造/遗漏 FAIL**。字母章位 `(A.3)`（`letter_ch: true` 或 `type: 15`）与罗马章位 `(II.5)`（`type: 16` / `lead='roman'`）**均已支持**：书若正确配置对应 lead，这类编号照常机器校验、不进本降级支；只有当**数字家族**的书源里检出字母/罗马编号时，`_detect_letter_led_formulas` 才 emit 一条 mis-config WARN，提示按家族补 `letter_ch`/`type:15` 或 `type:16` 后重跑。**仅多字母词前缀（`App.2` / `Ap.3`）无对应 lead 家族**，仍作「暂不校验、须人工核对 formula_audit」的 WARN。**（探测正则已收紧：只认短字母/罗马前缀 + 点`·`分隔的真公式编号，不再误匹配 `(n-1)` 代数式与 `(Fig.)/(Chap.)/(Prob.)` 引用——旧正则曾使纯数字编号书（如 Kreyszig）每章被误 BLOCK。）**

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
`Q-LAYER FORMULA MISSING`（未登记 ignore）→ FAIL（阻断）；`Q-LAYER FORMULA ORDER_MISMATCH` / `Q-LAYER FORMULA MISPLACED` → 仅 WARN（非阻断）。
- **修复步骤**：
  1. `FABRICATED`（总结 `\tag` 编号不在 S → 编造/串号）→ 回源核对，删掉或改正 `\tag`。
  2. `INCONSISTENT`（重复/跨章）→ 修正 `\tag` 使其唯一且属本章。
  3. `MISSING`（FAIL，阻断）→ 书源确有该编号但属合法省略（如排版重复）时加入 `formula.ignore`；否则补写该公式并挂 `\tag`。未登记 ignore 的遗漏一律阻断以防漏写。
  4. `ORDER_MISMATCH`（WARN）→ 总结中公式列举顺序与书源阅读顺序不符（串位/偏移）→ 核对并调整 `\tag` 出现顺序使其与书源一致。
  5. `MISPLACED`（WARN）→ 公式 `\tag` 所在小节与书源定义小节**非前缀兼容**（标号挂错节）→ 把该 `\tag` 移到正确的 `## §N.M` 之下（注意：书源定义于更深子节如 §N.M.K、总结置于其祖先节 §N.M 视为正确，无需移动）。
  6. S 为空降级（配置错）→ 回头修正 `formula` 的 `type`/`scope`（实为 `type` 派生错）让书源抽到编号，不要当成"通过"。
  7. 重跑 verify，确认 FABRICATED / INCONSISTENT 为空（WARN 项按需清理）。

修复后重跑 `verify_chapter.py --all`（或单章 `<ch> <start> <end> <md> <ext>`）确认上述门为空 / 转绿。

## 字节契约键
```contract-keys
q_checked
q_fabricated
q_inconsistent
q_missing
q_order_mismatch
q_misplaced
q_letter_led
q_rows
```
