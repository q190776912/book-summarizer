# U 层 — UNIT ORDER（unit_order）

> 本文件是 **U 层** 的唯一权威详情（SSOT）。语义 / 判据 / 阈值 / 实现只在此描述；汇总索引与全局架构见 [`../verify.md`](../verify.md)。
> **注册机制**：脚本 `verify/unit_order/script/unit_order.py`，由 `verify/script/register_all.py` 按裸名扫描 `verify/*/script/` 自动发现并注册。`code = 'U'`，`order = 18`，`auto_fixable = False`。

```contract-keys
unit_order_problems
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

## 本阶段规则（阻断性 / 可修复）
- `unit_order_problems` 非空 → 阻断 FAIL（`problems += 1`）。
- **不可 `--fix`**：顺序错乱的修复 = 重排单元（manifest 记录顺序），风险高，须人工/脚本按报告
  定位「谁不该出现在这里」后移动，不能盲目自动改。

## 出口条件
`unit_order_problems == []`。契约或源 manifest 任一缺失（旧书未产契约 / 非 write-source 产物）
→ 静默返回 `[]`（无从判真值不误报），不阻断。

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
