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
   - **`depth`** = 编号数值段数，**由 `type` 经 `ORDINAL_DEPTH` 派生**（不要单独配置）：`C.N`（如 `2.6`）→ `type 4`（depth 2）；`C.S.N`/`C.S-N`（如 `11.1-1`）→ `type 3`（depth 3）；单分量 `(N)` → `type 1`（depth 1）。
   - **`scope`**：默认 `2`（章级编号 `C.N`，开启跨章守卫——首分量 ≠ 当前章号判 INCONSISTENT）；若全书为全局连续编号则用 `1`（关闭跨章守卫）；若每节重置（如 Kreyszig `(1)`）用 `3`。
   - ⚠️ **scope:3 ⇒ depth 必为 1**：节级重置必为裸 `(N)`，不可能带 `C.N`（若出现 `C.N` 则必 scope:2）。
   - **`type`**：编号风格码，**唯一权威字段**；`depth` 由 `type` 经 `ORDINAL_DEPTH` 派生（2 段→`4`→depth 2，3 段→`3`→depth 3，单分量→`1`→depth 1）。不再单独写 `depth`。
   - **type 1 = 单分量 standalone `(N)`**：节级重置（Kreyszig 风格），`depth` 必为 1，`scope` 通常为 3。是单分量公式书唯一合法码。
   - `ignore`：先给空数组 `[]`；跑出 MISSING 且确认属合理省略时再加。
   - 写入示例（章级两段编号书）：
     ```json
     "formula": {"type": 4, "scope": 2, "ignore": []}
     ```
     ⚠️ 此示例为**章级两段编号书**，仅作章级参考；**不可照抄到节级单分量书**（Kreyszig 每节重置应为 `{"type":1,"scope":3}`）。
3. **配置错会降级**：若 `formula` 配了但 `depth` 不对导致书源抽不到编号（S 空），层只做结构检查并 WARN「书源公式编号未抽到，请检查 formula 配置」，**不判编造/遗漏 FAIL**——此时须回头修正 `formula` 的 `type`/`scope`（实为 `type` 派生错），不要当成"通过"。

- **代码护栏**：`formula_tag.py` 的 `run()` 网关已实现——当 `formula` 为 `None` **且**该章总结含 `\tag{...}` 时，会向 stderr 打印醒目的 `[Q-LAYER WARN]`，明确提示"公式序标未校验，不可报通过"。无 `\tag` 的书仍静默 no-op（合法）。agent 看到该 WARN 必须停下补全配置，禁止继续宣称公式校验通过。
- **稀疏编号书（2026-08 Fraleigh 案例）**：全书仅少数章有编号公式、且总结为扁平结构（无 `## §N.M`）时，plain 路径对单分量（ncomp==1）书源抽取施加与 build_sectioned 同源的门禁——只认①独立整行标签块 `(N)`；②含数学记号且以 `(N)` **结尾**的块，但**只提取块尾那一个匹配**（防阶乘因子 `(3)(2)(1)`、生成元 `H=(4)`、分解式末位因子等块内括号被误抽）。前置校验 check#1 仅在**本章总结确有 `\tag` 而 configured 抽取为空**时才报 ERROR；无 tag 的章按「S 为空降级」放行。
- **每章 ignore 形状**：`ignore_ch{N}.json` 同时接受 list（纯键列表）与 dict（键 -> 登记理由；B 层 / IGNORE-AUDIT 惯例形状），Q 层两者都合并进本章忽略集——登记公式噪声时优先用 dict 附理由以便人审。

## 步骤（语义与检查内容）
- **门控（opt-in）**：`BookConfig.formula` 为 `None`（默认）时整层 no-op——返回中性 `q_*` 元数据、不写报告、不计入 FAIL，确保既有 16 层与已完工书目零变化。仅当某书在 `verify_config.json` 显式配置 `formula` map 后才启用。
- **配置形状**（与条目序标 `ordinal` 配置同构，非平铺字段）：
  ```json
  "formula": {"type": 3, "scope": 2, "ignore": []}
  ```
  - `type`：ORDINAL_* 风格码（1..9）；**`depth` 由 `type` 经 `ORDINAL_DEPTH` 派生**（2 段→`4`，3 段→`3`，单分量→`1`），不再单独配置。`ORDINAL_SECTION_TYPES` 是小节层级反推，与 formula 的 `depth` 无关。
  - `scope`：1=book / 2=chapter / 3=section——编号重置窗口；**跨章守卫**（首分量 ≠ 当前章号判 INCONSISTENT）当且仅当 `scope == 2` 开启，book/section 作用域关闭该守卫。
  - `ignore`：要跳过 1:1 比对的归一化公式编号列表（既不判 FABRICATED 也不判 MISSING）。
- **scope/depth 耦合不变量（由 `type` 决定，配置必守）**：scope:3⇒`type 1`(depth 1，节级裸`(N)`)；scope:2⇒`type≥4`(depth≥2，章级带 C. 前缀)；scope:1 通常 `type 1` 全局连续。违反即非法，`require_complete` 应拒。
- **书源编号抽取**：`SourceFormulaIndex.build()` 遍历 `page_{start:03d}.json .. page_{end:03d}.json`，对每页 `text[].text` 用**由 `type` 派生的 `depth`** 正则抽编号（`build_formula_patterns(ncomp)` 覆盖 `（1.17）`/`(1.17)`/`Eq. 1.17`/`Equation 1.17`/`式（1.17）`/裸 `1.17` 六种变体，每式单捕获组），`norm()` 归一后归入本章集合 S。**只读 text，不读被扫花的 `formulas[].latex`**。
- **序标校验（自动 FAIL）**：
  - `q_fabricated`(FABRICATED)：总结 `\tag` 编号归一后**不在 S**（编造/串号）→ 始终 FAIL。
  - `q_inconsistent`(INCONSISTENT)：编号**重复**，或**跨章**（`scope == 2` 时首分量 ≠ 当前章号）→ 始终 FAIL。
- **遗漏校验（未登记 `formula.ignore` 时阻断 FAIL）**：
  - `q_missing`(MISSING)：S 中属于本章、规范、前缀匹配的编号在总结无对应 `\tag` → **FAIL（阻断）**。writing-rules 硬性要求 7 规定书源所有带编号公式（含描述性散文中的推导式）都必须保留，故"未登记的遗漏"即"漏写公式"。书源确有该编号但属合法省略（如纯排版重复）时，把它加入 `formula.ignore` 跳过比对；未在 `ignore` 登记的遗漏一律阻断，以防漏写描述性推导公式。
- **序列顺序校验（WARN，永不阻断）**：
  - `q_order_mismatch`(ORDER_MISMATCH)：总结文档序与书源阅读序（按公式首次出现的 `page, y` 位置）不一致 → 仅 WARN。`scope==3`（节级重置，编号每节重复）时按 `## §N.M` 窗口独立判定（跨节重置避免重复编号误报）；`scope==2/1`（编号全局唯一）时窗口跨节，连跨节顺序偏移也捕获；仅对 S 中命中的编号判定，不与 FABRICATED/MISSING 重复计数。
- **小节定位校验（WARN，永不阻断）**：
  - `q_misplaced`(MISPLACED)：总结公式所在 `## §N.M` 小节与书源该公式定义所在小节**非前缀兼容**时 → 仅 WARN。判定用"前缀兼容"而非精确相等：书源定义于更深子节（如 §1.3.1）而总结置于其祖先节（§1.3）视为**正确**（子节是父节后代，不算挂错节）；仅当二者真正分叉（书源 §1.4 却放 §1.3、或书源 §1.3.5 却放 §1.3.2）才报 MISPLACED。捕获"标号挂错节"。
- **公式内容校验（人工对账）**：`verify_all` 末聚合各章 `q_rows` 写出 `<extract_dir>/formula_audit.md`，并排列出「总结 LaTeX / 书源文本片段」，机器**不判内容对错**。
- **S 为空降级**：若派生正则未抽到任何编号（S 空，通常是 `formula` 配置错，**或书源采用字母/罗马开头编号 `(A.3)`/`(I.2)` 这类 Q 层暂不支持的形态（预留待实现）**），仅做结构检查（重复/章节前缀/规范），emit 一条 WARN，**不判编造/遗漏 FAIL**。字母/罗马开头场景由 `_detect_letter_led_formulas` 提前探测并把 WARN 文案改为「该格式暂不校验、须人工核对 formula_audit」，避免误导成配置错。**（探测正则已收紧：只认短字母/罗马前缀 + 点`·`分隔的真公式编号，不再误匹配 `(n-1)` 代数式与 `(Fig.)/(Chap.)/(Prob.)` 引用——旧正则曾使纯数字编号书（如 Kreyszig）每章被误 BLOCK。）**

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
- `SourceFormulaIndex.norm()`：去空白/去外层 `（）()`/去 `Eq.`·`Equation`·`式` 前缀；把 `.\-·,` 任一分隔符归一为 `.`；**折叠末尾字母后缀(a)**（如 `5.1.3a`→`5.1.3`）。折叠后缀只为「书源子式 `(8a)`/`(8b)` 与汇总结点 `\tag{8}` 对齐」的 S 成员 / MISSING / FABRICATED 比对；**INCONSISTENT 重复检测另用 `norm_full()`（保留后缀）**，使 `(5.1.3a)`/`(5.1.3b)` 这类真实子式不被误判为重复 `\tag`。无字母后缀的书 `norm_full == norm`，故该改动对纯数字编号书零回归。例 `（11.1-1）`→`11.1.1`，`Eq. 2.3`→`2.3`，`2.3a`→`2.3`。
- `LayerResult` 返回的 5 个 `q_*` 键须与 `DEFAULT_RESULT`、本 `contract-keys`、以及 `report.py` 读取完全一致（由 `verify/tests/test_key_contract.py` 强制校验）。

## 子流程
无独立子脚本；`SourceFormulaIndex` 与 `build_formula_patterns` 在本层脚本内。

## 需 agent 手工修复（manual fix）
本层 `auto_fixable = False` 且 **opt-in**——总结里带 `\tag{X}` 的公式，其序标必须与
**书源公式编号集合 S** 1:1 对应；编造/错位/跨章须人工核对书源，脚本不臆造编号。

- **前置（缺一不可）**：`verify_config.json` 须配 `formula` map（`type`/`scope`），
否则 Q 层静默 no-op（见本层顶部警告）。看到 `[Q-LAYER WARN]` 必须补全配置，禁止宣称公式校验通过。
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
