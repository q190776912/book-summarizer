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
- `truly_missing` / `mentioned_only` / `extra`：整章完整性（B 层职责）。`truly_missing`=书有而 md 全宇宙无 → 阻断；`mentioned_only`=仅正文/引用出现、非独立条目 → 仅复核；`extra`=md 有而提取未检出（多为合法交叉引用）→ 仅参考。EXTRACT 供水时经 `keys_in_md(..., chapter=ch)` 把「带显式异章限定词」（of Chap. X / 第X章…，X≠本章）的正文提及排除在 all_keys 之外，故此类跨章引用不再进入 EXTRA（条目标签不受影响；实现见 `lib/key_parse.py::_is_foreign_chapter_ref`）。
- 🔴 **`extra` 必须再分两桶打印**（`_split_extra`，2026-09-29 Apostol IANT ch9 例1 根治）：`extra_entry` = 并集 ∩ `entry_keys`，即 **md 里有独立加粗条头而契约无该条目** = 契约漏登记印面条目的信号；`extra_mention` = 其余，才是「正确过滤的交叉引用」。旧版两类混在一行、文案写着 "usually correctly-filtered cross-refs"，于是真漏登记被读成良性噪声（Apostol ch9 §9.6 印面确有 `EXAMPLE 1`，fitz 300dpi 目视物理页 199；OCR 把条头粘进句子 `ExAMPLE1Determinewhether219…` → 抽取器无条目 → 该行被一路判成「交叉引用，无需处置」）。**处置口径**：条目级逐条回印面判读 —— 印面确有条目 → 登记（契约节点 / `manual_overrides_ch{N}.json`；正文已在相邻 desc 单元里逐字交付时，登记**零内容节点**即可，`unit_node_entries` 只对 `node_content_count>0` 的节点索要单元，故不新增单元、不动翻译 1:1 同构）；无号体例条头（如 `**例**`）或契约用另一种键形 → 无需处置。**为何不升级为阻断**：跨 51 书普查（脚本 `Apostol 书 _extract/_census_entry_extra.py`）显示条目级 EXTRA 分布于 ≥6 书、数十章，绝大多数是体例（statistical-inference 契约两段键 vs md 三段条头；Lie 代数 ch1 无号 `**例**`/`**定义**`），一律阻断会打爆已收官书 → **只改可读性与判读文案，`extra` 仍是并集，pass/fail 逐字节不变**（判据测试 `verify/tests/test_b_layer_extra_bucketing.py`）。🔴 **已知最大假信号族已机械折掉**（2026-10-02）：契约登记为 exercise/problem 的键不再计为孤儿条头（见下「契约习题节点键计入 EXTRA 覆盖集」），`extra_entry` 剩下的一般才是真需要回印面判读的形态差异。
- `warnings`：非阻断（含 over-mark 守卫的误标提示、OCR 漏检复核等）。
- 🔴 **提及桶的「领域归属」收窄**（`domain_suppressed_mentions`，2026-10-02 Lasota-Mackey / Strogatz 根治）：`keys_in_md` 不区分号码属于哪个**领域**，于是三段号 `1.2.11` 作为**公式标签** `\tag{1.2.11}`、**图/表号** `图 1.1.2` / `ch01_fig1.1.2.png`、**括号公式回指** `(1.2.8)` 出现时，与条目号同形而一并落进 `extra_mention`。实测该桶绝大多数就是这三类：Lasota-Mackey《Chaos, Fractals and Noise》634 个提及键里 627 个、Strogatz 525 个里 389 个、Katok 134 个里 132 个。**后果不是难看，是判读失效**——上千行良性噪声把「契约漏登记条目」的真信号（上一条 Apostol 例1）淹掉。判据（只按**出现位置的上下文**判，不看配置）：某提及键在 md 里的**全部**出现都属于下列三域之一才剔除 —— ① `tag`：落在 `\tag{...}` 内（Q 层 formula_tag 辖域）；② `figref`：紧跟 图/圖/图例/插图/表 / Figure / Fig. / Plate / Table / Tab. 或 `…_fig` 图片文件名（图像域——writing-rules 规定图只作正文引用，`extracted` 亦按 `label=='uncat'` 剔除它们）；③ `eqref`：被 `()`/`（）` 包住（印刷公式回指形态），但**开括号前是条目词**（`Definition (5.6.5)` / `定理（5.6.5）`）时判 `real` 不剔除。任何一处出现在其他上下文（裸号散文提及、加粗条头）→ 照旧报；非纯数字键（`性质1`）、md 里一处都扫不到的键（跨语言/跨文件带进来的）→ 一律不判。前后守卫 `(?<![\d.])…(?![\d.])` 禁长号片段冒充（`1.2.115` 不构成 `1.2.11` 的出现）；`(?<![a-z])` 禁 `config 1.2` 里的 'fig' 子串被读成图号。🔴 **只改 `extra`/`extra_mention` 两个非阻断报告桶 + 新增 `extra_mention_domain`（`report.py` 以「EXTRA-MENTION · 领域归属豁免」单独打印豁免清单，不静默消失）**；`all_keys` 原样不动 → `truly_missing`、整类首项缺失等阻断判据逐字节不变。跨 53 书普查（脚本 `chaos(Lasota-Mackey) 书 _extract/_census_b_mention.py` → `_census_b_mention.json` + `_census_b_mention_samples.txt`，623 个章×语言单元）：提及 5699 → 3821，豁免 1878（33%），豁免集中在 chaos 1124/Strogatz 389/statistical-inference 227/Katok 132，而 Rising Sea 2781 个提及只豁免 6 个（Vakil 正文按「Theorem 4.3.2」条目式引用，照旧全部在账）——判据未把条目域引用一并扫掉。**逐书账（全书聚合，非单章）**：chaos《Lasota-Mackey》1268→144、Strogatz《Nonlinear Dynamics and Chaos (3rd ed.)》525→136、Katok 134→2，PASS 章数一章未动。判据测试 `verify/tests/test_b_layer_mention_domain.py`（含六条负向守卫：条目词+括号、tag 与裸号混现、非数字键、md 扫不到、长号片段、`config` 子串）。🔴 同一函数自 2026-10-02 起**也作用于条目桶**（`extra_entry`），辖域口径不变，见下「领域归属判据同样管辖条目桶」。
- 🔴 **裸号习题条头按「契约类型 + 同号二现」两步开窗**（`_exercise_window_routing` / `_resolve_bare_ex_candidates`，2026-10-02 Katok 根治）。印面把某些书的节后习题**不冠标签词**直接排成裸号条头（Katok 每节后段 `2.9.1.` / `3.1.6*.`，fitz 目视 + 契约 `book_structure/ch2.json` §2.9 三个 `type:"exercise"` 节点为证），而该书条目计数器跨类型共享且按节重启 → `**Definition 2.9.1**` 与 `**2.9.1.**` 是**两条并存的印刷序列**，旧的「按条头标签词路由 ex 窗」判据在裸号头上读不到标签，两序列并成一窗，报出 81 条「疑似幽灵重复节点」（同号二现 [1,2,3]）。**后果不是难看**：该 WARN 正是本层区分「重复节点伪影」与「真条目错位 BLOCKING」的那一支，把真序列碰撞说成伪影 = 错位信号被稀释。判据两步，缺一不可：① **候选** = 条头无标签词（`''`/`uncat`）且该键在**本章契约**里登记为 exercise/problem（`_contract_exercise_keys` 按磁盘物理证据 `resolve_chapter_json_path` 取真值，读不到 → 空集 → 行为逐字节回到改前）；② **开窗** 仅当同一条主窗里**另有具名条头占着同一个键**（`_resolve_bare_ex_candidates` 的碰撞判据）。🔴 第二步是普查逼出来的：只按契约类型抢先开窗，Weibel《Homological Algebra》那种「每节一条 1..N 共享计数器」的书里裸号头（`**10.2.3（疏解…）**`，契约把它登记成 exercise 也不改变它是序列成员）会被从主窗挖走 —— 跨 53 书普查里 Weibel ch1–10 一次 **BLOCKING 0→79**。另三条守卫：`demoted_word`（条头本写习题词、只是被行首难度标记 `\*` 挡住标签解析，Intro-to-Dyn-Systems ch3 `**\*习题 3.2.2.**` 实测——该头归两步法 `_resolve_demoted_entries` 按习题词所在组回补真习题窗，裸号腿抢先就把真习题窗挖成假缺号）、`is_uncat` 合并计数器（Vakil）、`exercise_shared_numbering` 及其 `stays_main`（Lee / Etingof），且 `prefix_str` 为空的 `gi:file` 窗一律不动。**同源副产**：`_bare_head_core` 剥裸号条头的**尾部转义星号**（印面 `3.1.6*` 写成 md 是 `**3.1.6\***.`，`_SPAN_RE` 非贪婪闭合吞掉 `\*` 的星号 → 该头此前整个不被 B 看见，Katok ch3 因此假报「缺号 6」BLOCKING）。跨 53 书 A/B 对拍（脚本 = chaos(Lasota-Mackey) 书 `_extract/_census_b_ab_routing.py`，623 个章×语言单元 × cn/en，old = 改前快照 `_bbase_old/`）：**regressing units = 0** —— `blocking`（0）、`truly_missing`(2)、`mentioned_only`(4)、`extra`(7752)、`extra_entry`(3931)、`extra_mention`(3821) 逐单元逐字节不变；唯一系统性变化是非阻断的幽灵 WARN **127 → 46**（Katok 81→2、statistical-inference 3→1，28 个单元受影响）。Katok 残留 2 条（EN/CN 各一）是**真二现**：§9.2 的 `Proposition 9.2.1` 与 `Example 9.2.1` 同号，另 Example 系列是否单独起号须回印面判读（不是判据问题）。判据测试 `verify/tests/test_b_layer_contract_exercise_routing.py`（含 Weibel 无碰撞不搬、两裸号头互不算碰撞、跨窗同号不搬、五条守卫逐个负例）与 `verify/tests/test_b_layer_starred_bare_head.py`。🔴 轻量 ctx 调用方须带 `ext_dir`/`ch`（`backfill_ordinals.py` 本轮已补，否则该判据静默失明）。
- 🔴 **契约习题节点键计入 EXTRA 覆盖集**（`run()` 里 `_ext_norm |= _contract_exercise_keys(ctx.ext_dir, ctx.ch)`，2026-10-02 Katok 264 行 / Intro-to-Dynamical-Systems 383 行根治）。`data_provider`（EXTRACT 供水层）的真相集 `ctx.items` 按设计**排除 exercise / problem 节点**（见该文件头注「非 exercise/chapter/section 节点」），于是 md 照印面写的习题条头（Katok 每节后段成排的 `**练习 2.9.1**` / `**Exercise 2.9.1**` / 裸号 `**2.9.1.**`）**永远落不进 `_covered`**，每一条都被 `_split_extra` 归成 `extra_entry` = 「md 有独立条头而契约无该条目」= 上一条明文规定的**契约漏登记真信号**。实测全书 `extra_entry` 3931 行里约 76% 是这一族（Intro-to-Dynamical-Systems 383、Weibel 313、Katok 264），**后果与 Apostol 例1 同源且更重**：真漏登记的判读通道被同形的假信号彻底淹没。修法 = 把**同一份磁盘契约真值**（`_contract_exercise_keys`，与上一条裸号开窗判据同源、`exercise_node_windows` 天然跳过 consolidated 与内容块节点，键形已按 md 侧 `_norm_ex_key_form` 归一）并入 `_ext_norm`。**判据边界（两条死线）**：① 🔴 **只进 `_ext_norm`，绝不进 `extracted`** —— 后者是 `truly_missing` 的书真相集，consolidated 成堆习题块按 writing-rules 从不进总结 md，把它塞进 `extracted` 就是拿放宽判据批量造「整条漏写」的假 BLOCKING；② 本行只声明「该键契约已登记、不是孤儿条头」，习题**内容**是否在账仍由步骤 5 闸门⑩（`unit_node_entries`）与 `check_structure_completeness` 负责，B 层不越权。注：`_ext_norm` 的匹配按 `_norm_path` **标签无关**（既有口径：契约裸键 `1.1-1` 与 md 条头 `定义1.1.1` 视为同一实体），故 md 标签词与契约 `type` 不一致（Weibel 共享计数器下 `定理10.8.2` 对契约 exercise 节点）也一并折掉——不是新增宽容，本层 EXTRA 覆盖集从不校验标签，类型对账在别处。跨 53 书 A/B 对拍（脚本 = chaos(Lasota-Mackey) 书 `_extract/_census_b_ab_routing.py`，623 个章×语言单元 × cn/en；A=`_ab_new3_all.json`（仅上一条开窗修复）、B=`_ab_new4_all.json`（加本行），隔离判据 `_extrafix_summary.py`）：**`blk`/`tm`/`mo` 逐单元逐字节不变（violations=0）、EXTRA 三桶零新增键（纯收窄）**；`extra_entry` 3931→3015（−916）、`extra` 7752→6792、`extra_mention` 3821→3777；逐书 `extra_entry`：Intro-to-Dynamical-Systems 383→**0**、Weibel 313→25、Katok 264→26、Arnold 23→18、Rising Sea 2031→2029。残留各有归属：Katok 26 行**全部**落在字母附录章 A（`A.2-1`…`A.2-7` / `定义A.1-15` / `命题A.1-2`，EN/CN 各 13），而 `appendixA.json` 里这些节点确实存在且该书零 exercise 节点 → 属「字母限定键的两侧形状不匹配」另一族（`_norm_path` 只折 `\d+\.\d+\.\d+`），与本行无关、另立任务（🔴 该族已随下一条「字母章位键归一」折掉，Katok 26→12、Weibel 25→8）。Arnold 18 行是 `**评注N**` 无号体例；Weibel/Cartan–Eilenberg 是两段/三段键形体例。判据测试 `verify/tests/test_b_layer_contract_exercise_coverage.py`（端到端过 `VerifyManager(EXTRACT+B)`：契约已登记的 `**练习 9.1.3**`/`**习题 9.1.4**` 离开 `extra_entry`；未登记的 `**例题 9.2.5**` 照旧报；无契约 = 行为回到改前；consolidated 节点不进覆盖集；🔴 monkeypatch 隔离本行——`_contract_exercise_keys` 置空后仅 EXTRA 桶移动，`truly_missing`/`mentioned_only`/`blocking`/`extra_mention` 逐字节不变）。
- 🔴 **字母章位键的「标签无关 + 字母槽」归一**（`_norm_path_labelfree` / `_LETTER_SLOT_RE`，2026-10-02 Katok 附录 A 12 行 / Weibel 附录 A 17 行根治；上一条把残留归给「字母限定键两侧形状不匹配」这一族，本条就是它的修法）。`_norm_path` 的正则只认 `^标签?(\d+)\.(\d+)\.(\d+)$`（三段纯数字）→ **字母章位键（附录 A / 补篇 S 下的 `A.2.1` 形态）从来不被归一**，于是同一实体在两侧长成两种形状：契约侧节点键是裸的 `A.2-1`（`build_structure` 按「章字母.节-序标」存），md 侧条头是带标签或带点分的 `**定义 A.2.1**` / `**A.2.1.**` / `**Proposition A.1.2**`。两侧都归不到同一形状 ⇒ **双向假信号**：`extra_entry` 报「md 有条头而契约无该条目」（Katok 附录 A 的 `A.2-1`…`A.2-7` 成排），同时 `truly_missing` 报「契约有而 md 全宇宙无」（同章 `定义A.1-2` 等，实测 `_probe_letter_fold.py` 关掉归一即复现两侧齐飞）。**后果与习题族同重**：附录章的「契约漏登记条目」判读通道整章失真。修法 = 既有 `_norm_path` 之后再接一层 `^(.*?)([A-Za-z])[.．](\d+)[.\-](\d+)$` → `"{字母}.{节}-{序标}"`，剥掉前导标签词并把字母章位统一到 `X.N-K` 形状；**四个 A 部分调用点同用此函数**（`_ext_norm` / `_all_norm` / `truly_missing` / `_covered`），两侧同函数 ⇒ 单调性由构造保证（不会一侧折得比另一侧狠）。🔴 **代价与边界**：本层 EXTRA 覆盖集**从不校验标签**（上一条已声明同一口径），字母键折完后 md 标签词与契约 `type` 不一致（`**命题 A.1.2**` vs 契约 `type:"definition"`）也不再surface 到 EXTRA —— 类型对账的权威在 `check_label_consistency` / `label_warns` 与步骤 5 闸门⑩（`unit_node_entries`），本层不越权；提及桶不受影响（`_mention_num_regex` 只认纯数字键，`定义A.2-1` 返回 `None` → 字母键**从不**进领域归属豁免，判据测试逐条断言）。跨 53 书 A/B 对拍（同一语料 623 个章×语言单元 × cn/en，old = 改前快照 `_bbase_b1/`，new = 出厂件；脚本 = chaos(Lasota-Mackey) 书 `_extract/_census_b_ab_routing.py`（本轮加 `OLD_B_MOD` 环境变量以切换快照模块）+ 隔离判据 `_diff_ab_fold.py`）：**`blocking`(0) / `truly_missing`(2) / `mentioned_only`(4) / `extra_mention`(3777) / 幽灵 WARN(46) 逐单元逐字节不变**；`extra_entry` 3015→2984、`extra` 6792→6761；🔴 **GAINED keys = 0**（纯收窄，无新键）且移动的 **62 个键 100% 是字母槽键**（非字母槽 = 0 个，即判据没有顺手折掉任何数字键）；逐书 `extra_entry`：Weibel《Homological Algebra》25→8、Katok 26→**12**，其余 51 书零移动。残留各有归属：Katok 12 行 = EN/CN 各 6 个真形状差异外的漏登记候选（`命题A.1-2` / `命题A.7-7` / `定理A.1-13` / `定义A.1-15` / `定义A.3-5` / `定义A.6-1`，须回印面判读后按 Apostol 口径登记零内容节点）；Weibel 8 行是两段/三段键形体例。判据测试 `verify/tests/test_b_layer_letter_slot_key_folding.py`（8 例：纯折叠正例、数字键零回归、六种负形（`Fig1.2-3` / `Corollary5.1-2` / `性质1` / `定理A.1` / `A.2` / `10.2-3`）不折、跨字母/跨节异体不合并、幂等、`_mention_num_regex` 对字母键为 `None`、端到端合成 `appendixA.json`（折叠开 = `truly_missing==[]` 且仅 `定义A.2-9` 落 `extra_entry`；折叠关 = 两侧假信号齐飞，逐条断言以证明测试确有东西可测））。
- 🔴 **领域归属判据同样管辖条目桶（假粗体跨度把公式回指读成条头）**（`run()` 里 `domain_suppressed_mentions(_md_txt, set(extra_mention) | set(extra_entry))`，2026-10-02 chaos(Lasota–Mackey) ch4/ch8/ch12 根治）。根因不在书数据而在解析器：`ENTRY_RE = \*\*[^*]*?(\d+SEP\d+SEP\d+)[^*]*\*+` 的收尾是 `\*+`（一个星号即算闭合），于是它会**在行内数学的星号上闭合**（`$f^{*}$` / `$\mu_*$` / `^{*}` 都是单个 `*`），把「从真条头的*闭合* `**` 起、跨到下一个数学星号止」的整段散文当成粗体条目跨度。实测四例（`_probe_entry_re_match.py` 逐条打印 match 偏移）：`> **证明**：1. 由 (4.2.6) 与定理 4.2.1 可知 $f^{*}$…` → 条目键 `4.2-6`（跨度 match[6:40]，在 `$f^{*}` 的星号上闭合）；`**性质4.** 若对某个 $f \in L^{1}$，极限 (8.5.8)，即 $f_{*} = …` → `8.5-8`；`**第一步**：由于 (12.7.3) … $\\mu_*$` → `12.7-3`；`**第二步**…方程 (12.7.17) … $r = 1$…` → `12.7-17`。🔴 **后果 = 最强信号桶被污染**：这些键直落 `extra_entry`「md 有独立条头而契约无该条目」= 契约漏登记印面条目，而全书 md 里根本不存在 `**4.2.6**` 条头（逐文件扫描 0 命中）——正是「Apostol 例1」那支判读通道被假信号占用的又一形态。**为什么不直接收紧 `ENTRY_RE`**：闭合改成 `\*{2,}` 会让跨度一路跑到**下一条真条头的开 `**`**（`**注1.** …见 (4.2.6)… **性质2.**` 这种相邻粗体极常见），把散文括号回指读成条头的面积反而更大；排除 `$` 则会把「条头内含行内数学」的真条目降级成 `mentioned_only`。故改在**分桶侧**复用提及域既有判据（同一函数、同一辖域口径），不动解析器。判据强度来自形状本身：某键在 md 里的**每一处**出现都属 `tag`/`figref`/`eqref` 才豁免，而真条头 `**定义 4.2.6**` 必然自己贡献一处 `real`（上一条已论证），**一处 real 即全盘照报** ⇒ 本行在构造上不可能洗掉真漏登记（测试逐条断言）。🔴 只动非阻断的 EXTRA 三桶（`extra`/`extra_entry` 收窄、豁免键照旧进 `extra_mention_domain` 留痕），`blocking`/`truly_missing`/`mentioned_only`/`extra_mention` 逐字节不变。跨 53 书 A/B 对拍（623 个章×语言单元 × cn/en，old = `_bbase_b2/`（仅回退本行的快照，由 `_mk_b2_snapshot.py` 三处 ASCII 替换生成），new = 出厂件；隔离判据 `_diff_ab_guard.py`）：**truth/mention 违例 0、GAINED keys 0、不可追溯的豁免 0**（每个从 `extra_entry` 出来的键都能在 `extra_mention_domain` 清单里查到）；`extra_entry` 2984→2976、`extra` 6761→6753、豁免清单 1878→1886；受影响单元 = chaos ch4/ch8/ch12 各 4 键（CN/EN 双版）+ Rising Sea ch12 `12.5-10` 1 键，其余 51 书零移动（判据不越界）。判据测试 `verify/tests/test_b_layer_entry_domain_eqref_guard.py`（8 例：端到端四负向 = 假跨度键离开条目桶且留痕豁免、契约无节点的**真**条头 `**定义 4.2.9**` 照旧报、同键既有括号回指又有真条头时不豁免、关掉判据只动 EXTRA 桶；另有 `_mention_occurrence_domain` 形状三例与一条**根因留证** = 断言 `keys_in_md` 确实把 `(4.2.6)` 收进 `entries`，防将来有人误以为本行在治别的东西）。
- 🔴 **「条目词 → real」表里不得放公式词**（`_LABEL_BEFORE_PAREN_RE` 删 `Equation|Eq.`，2026-10-02 chaos ch1–ch12 / statistical-inference ch3·ch11 / Katok ch2 根治，与上一条同窗落地）。上一条判据的 `eqref` 腿原本被这张表反杀：EN 散文写 `Equation (4.2.6) follows directly from (4.2.5)` 时，开括号前是「条目词」→ 出现域判 `real` → **该键永不豁免**；而同一句话的 CN 侧 `由 (4.2.6)` 判 `eqref` 照常被豁免 ⇒ **双语不对称**（实测 chaos EN 侧因此积压 119 个纯公式回指键，CN 侧 0）。判据：公式词不属于条目域——全链（`TYPE_TO_LABEL_CN` / `extract_items` / 契约 `type`）**从不把 equation 登记为条目类型**，编号公式一律是 `formula` 内容块 + `\tag{}`，其保真对账归 Q 层 `formula_tag`；`Figure` / `Table` 同理早已被 `_FIGREF_TAIL_RE` 归图像域。🔴 本行是**放宽**类改动（只把键移出报告桶），故按老规矩必须用跨书普查兜住而不是只看本书：跨 53 书 A/B 对拍（623 个章×语言单元 × cn/en，old = `_bbase_b3/`——由 `_mk_b3_snapshot.py` 三处 ASCII 替换**只回退这个词表**，new = 出厂件；隔离判据 `_diff_ab_eqword.py`）：**truth 违例 0（`blocking` / `truly_missing` / `mentioned_only` 逐单元逐字节不变）、GAINED keys 0、不可追溯的豁免 0**；`extra_entry` 2976→2974、`extra_mention` 3777→3655、`extra` 6753→6629、豁免清单 1886→2010（净移 124 键，逐键可在 `extra_mention_domain` 查到）；受影响单元仅 14 个（chaos EN 119 键、Katok ch2 `2.6-7`、statistical-inference ch3 `3.3-9`/`3.3-17` + ch11 `11.2-15`/`11.3-44`），其余 51 书零移动 = 判据不越界。**语义抽检**（`_probe_eqword_context.py`：对每个被移键打印其在 md 里的**全部**出现行 + 逐出现域）——被移键的出现域一律 ⊆ `{tag, eqref, figref}`，出现行全是 `\tag{}` 定义行 / `equation (N)` / `from (N)` / `Figure 1.2.2` 一类，**没有一条是粗体条头**；反向守卫仍在：同键若另有一处真条头出现，`real` 立即击败豁免（上一条第三例）。判据测试补 `verify/tests/test_b_layer_entry_domain_eqref_guard.py::test_formula_words_route_to_eqref_not_real`（全量 220 个测试文件 failures=0、`tools/check_undefined_names.py` 0 可疑名）。
- `b_gap_warnings`：非严格模式（`strict:false`）下 md 内部首项/连续性缺口，降级为非阻断警示。🔴 「疑似幽灵重复节点」WARN 也挂在本段（不在 `warnings`）——任何只读 `warnings` 的统计都会漏计它（本轮普查即因此先失明过一次）。
- `b_tail_warnings`：尾部校验，始终非阻断。

## 步骤（语义与检查内容）

### 分组（按书的编号习惯，来自 `BookConfig` / `ctx.config.ordinal`）
配置由 `ConfigLoader`（`config/verify_config/verify_config.py`）从 `<book>/_extract/verify_config.json` 一次性读出，挂在 `ctx.config`；B 层与提取层都读 `ctx.config`（配置统一经 `ConfigLoader` 一次性加载）。

**单一配置文件**：`<book>/_extract/verify_config.json`（扁平，存放分组与抑制字段 `ordinal`（分组对象数组 `List[GroupConfig]`） / `language` / `strict` / `ignore`）。`<book>/verify_config.json` 仅作为向后兼容的回退位置。不存在 `b_numbering.json` 这种独立文件，也没有 `b_numbering` 子键——一份文件，一种 schema，编号约定与抑制集合共用同一真相源。分组由 `ordinal` 数组表达（多个具名 group = per-type，单个 uncat group = combined），无 `disable` / `separate_types` 字段；校验层不被跳过，噪声一律经统一的 `ignore` 集合抑制（WARNING 门，非跳过）。

缺省/非法 → 默认 `ordinal=[{type:3, name:["uncat"], scope:3}]`(三级CN), `strict=True`。旧整型 ordinal / `separate_types` 写法被 `from_dict` 拒绝（报 `make_config --force` 提示）。

`BookConfig` 字段（经 `ConfigLoader` 读入，挂在 `ctx.config`）：
- `ordinal`：**分组对象数组** `List[GroupConfig]`，每个元素 `{type, name, scope}`（见 `config/verify_config/verify_config.py` 的 `GroupConfig`）。`type` 为编号风格码（`1`=单级，`2`=两级CN(章.号)，`3`=三级CN(章.节-号, 默认)，`4`=英文两级，`5`=罗马三级，`6`=GM(按节裸序号)；节基 EN 两级书如 Fraleigh 用 `4` 并设 `chapter_first:false` + `section_scoped:true`）。数组首元素 `type` 即 `primary_type`。`name` 为该组标签词（如 `["Theorem"]`，兜底组 `["uncat"]`）；`depth` 为编号层级数，由 `type` 经 `ORDINAL_DEPTH[type]` 派生（如 `4.11-5` 在 `type=3` 下为 3 级），非独立配置字段；`group_for_label(label)` 把标签映射到其 group，匹配不到的回落 uncat 组。
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

### 顺序校验 (ORDERING) — 始终 BLOCKING
- **目的**：抓"条目齐全却顺序错乱"这一类旧逻辑漏掉的真缺陷。旧 B 层把编号排序后只查缺号（存在性），所以"2.6-8 掉到 2.6-11 之后""§2.7 整节洗牌 `[9,1,2,3,6,7,8,5,10,11,4]`"这类 markdown 与（被污染的）契约都一致、却内容错位的怪象，22/22 也能 PASS。
- **判定**：同一「节前缀(prefix_str，如 `2.6`)」内，按阅读顺序收集编号，对**同编号去重（只保留最后一次真实定义出现）**后的序列必须单调不减；若出现 `seq[i] < seq[i-1]`（大号在前、小号在后）即判 **`WARN (BLOCKING)`**，且**不随 `strict` 降级**——"靠后的号跑到前面之后"属确定性错误，必须修（用户明确要求：不能要）。
- **为何只比对 `.md` 自身、不依赖契约 `page_start`**：只消费 markdown 的阅读顺序，所以即便契约 `page_start` 被习题/章首页污染导致排序错，markdown 的实际错序仍会被命中。代价：它只能发现 markdown 内的错序，**不能**发现"契约↔源书不一致、而 markdown 照契约错序写出"——后者属契约↔源书回检缺口（见下"已知缺口"）。
- **去重为何必要**：章首"四块基石"式摘要列表会把 `4.7-3 / 4.12-2 / 4.13-2` 列在节之前；证明标题 `4.12-2 的证明` 会被 `_parse_entry` 的 `_PROOF_RE` 过滤。同编号去重保留最后一次真实定义出现，章首 TOC 被节内真定义覆盖，避免伪回归（已实测：Ch4 CN 章首摘要曾造成 §4.7/§4.12/§4.13 假阳性，去重后归零）。
- **误报防护**：证明标题（`X.Y-Z 的证明` / `Proof.` / `Beweis`）在 `_parse_entry` 的 num-first 分支直接 `return None`，不计入条目序列；其余章节若编号本就单调递增（含稀疏跳号如 `1,2,3,5,6`）不会触发（跳号非逆序）。

## 本阶段规则（阻断性 / 可修复）
- `blocking` 非空 -> 阻断 FAIL。`auto_fixable = False`（缺号只能 agent 补写，不能脚本修）。
- 解决优先级：先尝试补真实项（并在 `manual_overrides_ch{N}.json` 登记）；仅当确认是 OCR 乱码 / 无法修复的交叉引用才进 `ignore`(`verify_config.json`) 或用 `--ignore` CLI 标志。

## 出口条件
`blocking` 非空 → 整章 FAIL；`b_gap_warnings` / `b_tail_warnings` 仅 WARN（不阻断）。

## 相关代码（`verify/item_numbering_integrity/script/item_numbering_integrity.py`）
- `code = 'B'`，`order = 3`，`auto_fixable = False`。
- **与 EXTRACT 解耦**：B 不再消费 `ctx.extraction_blocking`；提取侧查漏 + 完整性 + `ignored_hit` 全部由 B 自行计算（数据源为 EXTRACT 供水集 `ctx.items` / `ctx.entry_keys` / `ctx.all_keys`）。EXTRACT 现仅供水、不做事。
- 编号配置由 `config/verify_config.BookConfig` 经 `ConfigLoader` 从 `<book>/_extract/verify_config.json` 一次性读出，挂在 `ctx.config` 上；B 层读 `ctx.config`，**不再各自读文件**（配置统一经 `ConfigLoader` 一次性加载）。分组由 `ordinal` 数组各 group 的 `type`/`scope` 决定（`depth` 由 `type` 派生）（见 `config/verify_config/verify_config.py` 的 `GroupConfig` / `ORDINAL_DEPTH`），JSON 里 `ordinal` 必填为数组。
- `ItemNumberingIntegrityLayer.run`（自包含，不依赖任何其他层）：
  1. 整章完整性（原 A 层）：`truly_missing = sorted(extracted - all_keys)`、`mentioned_only = sorted((extracted & all_keys) - entry_keys)`、`extra = sorted(all_keys - extracted)`，其中 `extracted = {it['key'] for it in ctx.items} - ignore_keys`；并算 `ignored_hit` stage1（噪声键 `extracted_raw & ignore_keys`）。`all_keys` 由 `keys_in_md(..., chapter=ch)` 供给：带显式异章限定词的正文提及已被剔除（见上）。
  2. 提取侧查漏（原 P2 的 Q+over-mark 逻辑）：`_merged_category_first_missing(ctx, all_keys, blocking)` + `_merged_ocr_overmark_guard(ctx, items, warnings)`（基于 raw `page_*.json` + `ctx.items` + md）。
  3. `ignored_hit` 第二段 suppression：遍历 `blocking`，若某条引用键全部 ∈ `ignore_keys`，把 `bkeys` 并入 `ctx.ignored_hit` 并从 `blocking` 剔除（最终 `ignored_hit` 完全由 B 层在本层内计算，EXTRACT 仅提供 `ctx.items` 数据源）。
  4. 算 MD 侧 `_md_gap_blocking` -> `(md_blocking, md_warnings, present_md, md_tail)`。
  5. 对提取侧 `blocking` 做「MD 存在性过滤」：被报缺的键 ∈ `present_md` 则抑制（消息号已带前导 `-`，拼接用 `sec + n`）。
  6. 合并 `blocking = filtered_extraction + md_blocking`；返回 `metadata={'blocking','warnings','b_gap_warnings','b_tail_warnings','ignored_hit','truly_missing','mentioned_only','extra','extra_entry','extra_mention'}`。
- `b_tail_warnings` 由 `report.py` 在 `B-LAYER TAIL CHECK` 段非阻断打印；`b_gap_warnings` 在 `B-LAYER NUMBERING GAP CHECK` 段打印；`truly_missing`/`mentioned_only`/`extra` 在 `TRULY MISSING` / `MENTIONED-ONLY` / `EXTRA-ENTRY`+`EXTRA-MENTION` 段打印（B 层打印段；`extra` 并集本身仍挂在 `r['extra']`，两桶为 `r['extra_entry']`/`r['extra_mention']`）。

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
extra_entry
extra_mention
extra_mention_domain
```
