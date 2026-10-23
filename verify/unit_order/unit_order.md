# U 层 — UNIT ORDER（unit_order）

> 本文件是 **U 层** 的唯一权威详情（SSOT）。语义 / 判据 / 阈值 / 实现只在此描述；汇总索引与全局架构见 [`../verify.md`](../verify.md)。
> **注册机制**：脚本 `verify/unit_order/script/unit_order.py`，由 `verify/script/register_all.py` 按裸名扫描 `verify/*/script/` 自动发现并注册。`code = 'U'`，`order = 18`，`auto_fixable = False`。

```contract-keys
unit_order_problems
md_order_problems
md_order_stats
```

## 目的
断言**合并后的总结单元**遵循原书**结构阅读顺序**——补上一类此前所有闸门都看不见的缺陷：
一本书各层可以**全绿**，但合并 md 里单元次序仍然错乱（读者看到晚页内容出现在早页之前），
读起来很奇怪。根因是**没有任何闸门断言「拼接顺序 == 结构阅读顺序」**：

- **B 层**（条目编号完整性）只在**同一节前缀**内比较序标单调；对以 U/D 结构锚为节、条目
  本身无统一数字前缀的书（如 Lee《光滑流形》）完全看不见跨节错乱。
- **gate_units 章级闸 ⑩**（契约→manifest 反向覆盖）是**集合**比较（分桶 + 序标归一），
  同一集合的任意**排列**都放行。
- **`subsection_order_problems`** 只查**契约里**小节数字键是否严格递增，跑在拆分**之前**，
  且只看逆序不看跨页。

U 层（与 gate_units 章级闸 ⑪）用**源书页码**这个共同真值把这条缝隙堵死。

## 判据（真值 = 契约节点 `page_start`，源书物理页序）
1. **锚点**：前序遍历分章契约树，`归一键 → 该键首次出现节点的 page_start`（同键取首见，保守）。
   页码是原书物理顺序，比契约节点的**列表顺序**更可靠——列表序可能被陈旧/错误的拆分排乱，
   但每个节点自带的 `page_start` 始终指向它在原书里的真实页。
2. **被测顺序**：该章**源单元 manifest 的 `units` 数组**（`merge_units` 严格以此顺序拼接，
   故 manifest 顺序 == 合并 md 阅读顺序）。译文由 `check_translate_parity` 保证与源 manifest
   索引逐条对齐，源有序 ⇒ 译有序，故统一以源 manifest 为准（同一章中/英两份 md 各报一次相同
   问题，属预期的双重呈现）。
3. **单调性**：按 `units` 顺序遍历，维护「迄今最大页码」；某单元页码 **严格小于** 迄今最大页码
   → 早页内容排到晚页之后 = 跨节/跨页错位 → 报告（阻断）。
4. **相等允许**：页码相等不算问题（同页多单元的正常形态，同页内序标单调由 B 层管）。
5. **章末 dash 习题豁免**：键形 `N-M`（原始键含连字符，**归一前**判定，因归一会把 `-`→`.`
   与点分习题号撞车）的 Problems 按设计汇总排到章末，其 `page_start` 指向正文首现页（早于章末
   正文），必然被页码单调误伤——一律跳过，不推进也不受限于页码游标。
6. **锚点缺失跳过**：契约无该键 / 幻影 / 老键形对不上 → 跳过（既不当问题也不重置游标），
   避免锚点缺失产生连锁误报。

## 第二条被测顺序：交付 md 自身（`md_order_problems`，缺陷① 根治，2026-10-23）

上面 1–6 条的被测顺序是**源 manifest**，隐含假设「`merge_units` 之后交付 md 不再被改」。
收官书的交付侧普遍在合并之后还做过内容级修订（整块搬移 / 单元换文件 / 按节拆文件后按节号
重排），该假设有实证反例：茆诗松《概率论与数理统计教程》本轮的门控 ⑪ 与 U 层全绿，而交付侧
次序是靠**镜像交付 md** 修好的——两道闸对交付文本的实际次序完全不可见。

- **被测序列**：每条单元正文在**归一化交付文本**（去全部空白，含 `　`/NBSP）里的唯一偏移
  （`lib/unit_order.md_unit_positions`：逐行累加到 ≥12 字符且全篇唯一；仍不唯一则退回首行
  粗体条头/标题；都失败 = 定位不到）。按节拆分的章，文本取 verify 已在用的那份合并视图
  （`_merge_section_files` 的节号序 = 读者实际读到的序）。
- **单元身份**：仍按该语种 manifest 顺序解析，且与清单侧**共用同一段代码**
  `lib/unit_order.iter_judged_units`（出现序消费、`continuation` 复用父锚点、章末 dash 按
  `dash_exempt` 豁免、继承锚点的 `description` 容器跳过），**只有先后**换成文本偏移。
  🔴 豁免口径曾经写了两遍而分叉：交付侧拿「解析到的**节点**类型」判 `dash_exempt`（节点
  类型必然具体），清单侧拿「记录 `ntype`，缺失时回退**同键类型集**、混用即保守豁免」。
  Weibel ch5 实测 8 条假阳全部出在这条分叉上（`5.4-4` 同键挂 `definition`+`exercise`
  两个节点 → 清单侧豁免、游标停在 p143；交付侧不豁免 → 游标推到 p144，紧随的 `5.4-5`
  被契约误登记 p143 就判成倒退）。合写成一遍后 `lib/tests/test_unit_order.py::
  test_mixed_key_type_exemption_is_shared_by_both_calibers` 锁住两侧一致。
  🔴 语种必须配对：拿英文单元正文在中文交付 md 里找 = 整章定位失败 = 假绿，故按
  manifest 的 `language` 选 `units` / `units-translate`（译版单元顺序可以与源版不同，
  Kreyszig ch4 实测两侧先后差 26 位，中文交付 md 的真实拼接序是译版 manifest 顺序）。
  🔴 **语种要从文件名字读回来，而合并视图的名字不是交付名**：verify 交给各层的是
  `_merged_temp_path` 写出的 `._verify_merged_<章>_<lang>.md`，而 `_group_lang` 原本只认
  「第N章/附录/补篇」与「Chapter/Appendix/Supplement」两类真实交付前缀 → 视图名以 `.`
  起头返回 None → 配对回退源侧 `units`。Weibel ch10 中文视图实测 **1/152 定位（0.7%）、
  0 条问题**，而同一章英文视图 149/152、3 条问题——中文侧整章失明，却照样打印覆盖率行
  像个结论。修法 = `_group_lang` 认视图名末尾的语种（`_MERGED_VIEW_LANG`；老命名
  `._verify_merged_ch10.md` 仍返回 None，不猜），并配 `verify/tests/
  test_delivered_order_lang_pairing.py`：视图名 round-trip + 中/英视图各自定位到
  `units-translate`/`units` 并各报 1 条倒退（变异检验：摘掉语种分支 → 中文侧
  `located=0`、3 条点名测试转红）。修复后 Weibel 中文视图 148/152 + 3 条，与本层普查
  口径（普查驱动直接取组内真实首文件名，本来就是配对好的）一致。
- **口径只到页码**（`by_preorder=False`）：同页之内的先后，契约 `sub_sec` 列表序在交付侧
  **没有印面证据**。实测本书全书 6 处「前序倒退」，逐条解剖后 4 处是 `check_contract_anchors`
  文档里的已知契约缺陷（节习题块登记成父节第一个子节点：`习题6.1` 前序 15、`例6.1.6` 前序 16，
  印面在 §6.1 末 = 交付侧才对），2 处是同页三个条目加一个节头谁先谁后。拿它当阻断判据 =
  逼修书方按无证据的次序搬走已经正确的交付块。同页顺序要修的是**契约登记**，归
  `check_contract_anchors` / B 层节内序标管。
- **覆盖率与问题同屏**（`md_order_stats`：`located/expected/coverage/units_dir/unlocated`）：
  定位不到 = 跳过 = 不测，所以 `coverage` 低时「没有问题」不能作为证据；`merge:false`
  单元（V-I 章末集中习题省略）不进分母。`unlocated` 全量落 `verify_detail` 旁路（缺陷③ 出口）。
- **非阻断 WARN + 全语料普查（2026-10-23 出厂依据）**：晚生判据不得把已收官书永久刷红
  （`flow_runner audit` 口径），故先以 WARN 呈现、明细进旁路。普查 = 58 本 / 892 个
  (章,语种) 组 / 49075 条应定位单元，**定位率 99.04%**（未定位 472 条：desc 238 +
  section 205 + chapter 18 + item 7 + exercise 4——即「纯标题/导语容器单元」，正文太短或
  与交付条头不同形，宁可不测）；豁免口径合流后**问题 12 条，只落 2 本书**，逐条印面裁决
  后**全部是「账错、交付对」**，没有一条该动交付：
  - Weibel ch10（6 条）：印面 p397 是 `Proposition 10.4.1`，与同号 `Exercise 10.4.1` **撞键**；
    节末习题块在交付里正确地排在 Example 10.4.9（p401）之后（其内容引用引理 10.4.6），
    manifest 却把习题记录留在条目中间 = 清单陈旧。
  - Underactuated Robotics 附录 C（6 条）：印面 `C.1 OPTIMIZATION SOFTWARE` 在 **p323**、
    `C.2 GENERAL CONCEPTS` 在 p324；交付（C.1 先）对，契约页码（C.1=p325 / C.2=p324）与
    manifest 次序（C.2 先）都错。
  所以报告括注自带出口指令「先按印面定序，再决定搬交付块还是回写契约/清单」，防止把
  正确的交付块按错账搬走。**升阻断的前提**：这两本书的账回写完毕 + 普查复跑归零。

## 本阶段规则（阻断性 / 可修复）
- `unit_order_problems` 非空 → 阻断 FAIL（`problems += 1`）。
- **不可 `--fix`**：顺序错乱的修复 = 重排单元（manifest 记录顺序），风险高，须人工/脚本按报告
  定位「谁不该出现在这里」后移动，不能盲目自动改。

## 出口条件
`unit_order_problems == []`。契约或源 manifest 任一缺失（旧书未产契约 / 非 write-source 产物）
→ 静默返回 `[]`（无从判真值不误报），不阻断。
`md_order_problems == []` 属**非阻断**出口，且必须连同 `md_order_stats.coverage` 一起看
（低覆盖 = 没测，不等于测过且通过）。

## 相关代码
- 核心实现（门控与 verify 共用，杜绝逻辑漂移）：[`../../lib/unit_order.py`](../../lib/unit_order.py)
  的 `check_unit_order(contract, units)` / `build_page_anchor` / `is_dash_problem`。
- 合并前门控：`flows/write-source/script/gate_units.py` 章级闸 ⑪。
- 本层脚本：`verify/unit_order/script/unit_order.py`（`_locate` 定位契约 + 源 manifest 后调核心）。

## 误报校准（Lee《Introduction to Smooth Manifolds》实测）
24/26 章（含 4 附录）零误报；精确命中两处**真实**待修结构错位：
- **ch2**（2 处）：契约树把 section `U3` 连同其 2.1–2.11 内容块排在 section `U2`（页 47）之前，
  导致 `U2`/`D4`（页 47）出现在页 52 内容之后——Lee 原书 §2.1「Smooth Functions on Manifolds」
  应先于 §2.2「Smooth Maps Between Manifolds」，是契约 U2/U3 排序错误传导到 manifest/合并。
- **appendixB**（16 处）：此前手工补建 appendixB D 区单元时按内容而非页码插入，manifest 槽位
  顺序与 `page_start` 不一致。
两处均为**数据层**排序缺陷（真值页码无误），修法 = 按 `page_start` 重排 manifest（及对应契约树
`sub_sec`）单元记录；修后 U 层归零。
