# Q 层 — FORMULA SEQUENCE-LABEL（公式序标层）

> 本文件是 **Q 层** 的唯一权威详情。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verification.md`](../verification.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。

## 一句话目的
总结里带 `\tag{X}` 的公式，其序标必须与**书源公式编号集合 S** 1:1 对应；编造/错位/跨章阻断 FAIL，遗漏默认 WARN，公式内容人工对账。

## ⚠️ 执行前置（Pre-flight，强制）
> **本层是 opt-in，配置缺失会静默 no-op**——若 `verify_config.json` 没有 `formula` 块，Q 层直接返回中性 `q_*` 元数据、不写报告、不计入 FAIL。**这会让执行者误以为"公式校验已通过"，实际根本没跑。** 因此运行本层前，agent 必须完成以下前置，缺一不可：

1. **先确认配置存在**：检查 `<extract_dir>/verify_config.json` 是否含 `"formula"` map。
2. **缺失则按书实际编号推导并写入**（agent 负责，不要跳过）：
   - **扫书实测**：遍历该书若干章的 `page_{start:03d}.json … page_{end:03d}.json` 的 `text[].text`，用公式标签正则（覆盖 `（C.N）`/`(C.N)`/`Eq. C.N`/`Equation C.N`/`式（C.N）`/裸 `C.N`）看实际编号长什么样。
   - **`depth`** = 编号数值段数（实测决定，不要用默认值猜）：
     - `C.N`（如 `2.6`）→ `depth = 2`
     - `C.S.N` 或 `C.S-N`（如 `11.1-1`）→ `depth = 3`
   - **`scope`**：默认 `2`（章级编号 `C.N`，开启跨章守卫——首分量 ≠ 当前章号判 INCONSISTENT）；若全书为全局连续编号则用 `1`（关闭跨章守卫）；若每节重置（如 Kreyszig `(1)`）用 `3`。
   - ⚠️ **scope:3 ⇒ depth 必为 1**：节级重置必为裸 `(N)`，不可能带 `C.N`（若出现 `C.N` 则必 scope:2）。
   - **`type`**：取与 `depth` 对应的 ORDINAL 风格码（2 段→`4`，3 段→`3`），作为 `depth` 的兜底默认值；显式给了 `depth` 时 `type` 仅作兜底。
   - **type 1 = 单分量 standalone `(N)`**：节级重置（Kreyszig 风格），`depth` 必为 1，`scope` 通常为 3。是单分量公式书唯一合法码。
   - `ignore`：先给空数组 `[]`；跑出 MISSING 且确认属合理省略时再加。
   - 写入示例（章级两段编号书）：
     ```json
     "formula": {"type": 4, "depth": 2, "scope": 2, "ignore": []}
     ```
     ⚠️ 此示例为**章级两段编号书**，仅作章级参考；**不可照抄到节级单分量书**（Kreyszig 每节重置应为 `{"type":1,"depth":1,"scope":3}`）。
3. **配置错会降级**：若 `formula` 配了但 `depth` 不对导致书源抽不到编号（S 空），层只做结构检查并 WARN「书源公式编号未抽到，请检查 formula 配置」，**不判编造/遗漏 FAIL**——此时须回头修正 `depth/scope`，不要当成"通过"。

- **代码护栏**：`q_layer.py` 的 `run()` 网关已实现——当 `formula` 为 `None` **且**该章总结含 `\tag{...}` 时，会向 stderr 打印醒目的 `[Q-LAYER WARN]`，明确提示"公式序标未校验，不可报通过"。无 `\tag` 的书仍静默 no-op（合法）。agent 看到该 WARN 必须停下补全配置，禁止继续宣称公式校验通过。

## 语义与检查内容
- **门控（opt-in）**：`BookConfig.formula` 为 `None`（默认）时整层 no-op——返回中性 `q_*` 元数据、不写报告、不计入 FAIL，确保既有 16 层与已完工书目零变化。仅当某书在 `verify_config.json` 显式配置 `formula` map 后才启用。
- **配置形状**（与条目序标 `ordinal` 配置同构，非平铺字段）：
  ```json
  "formula": {"type": 3, "depth": 3, "scope": 2, "ignore": []}
  ```
  - `type`：ORDINAL_* 风格码（1..8）；当未给 `depth` 时按 `ORDINAL_SECTION_TYPES` 取默认分量数。
  - `depth`：公式编号的数值分量数（2 → `1.17`，3 → `11.1-1`），驱动源抽取正则的分量数。
  - `scope`：1=book / 2=chapter / 3=section——编号重置窗口；**跨章守卫**（首分量 ≠ 当前章号判 INCONSISTENT）当且仅当 `scope == 2` 开启，book/section 作用域关闭该守卫。
  - `ignore`：要跳过 1:1 比对的归一化公式编号列表（既不判 FABRICATED 也不判 MISSING）。

- **scope/depth 耦合不变量（配置必守）**：scope:3⇒depth:1（节级裸`(N)`）；scope:2⇒depth≥2（章级带 C. 前缀）；scope:1 通常 depth:1 全局连续。违反即非法，`require_complete` 应拒。
- **书源编号抽取**：`SourceFormulaIndex.build()` 遍历 `page_{start:03d}.json .. page_{end:03d}.json`，对每页 `text[].text` 用**由 `depth` 派生**的正则抽编号（`build_formula_patterns(ncomp)` 覆盖 `（1.17）`/`(1.17)`/`Eq. 1.17`/`Equation 1.17`/`式（1.17）`/裸 `1.17` 六种变体，每式单捕获组），`norm()` 归一后归入本章集合 S。**只读 text，不读被扫花的 `formulas[].latex`**。
- **序标校验（自动 FAIL）**：
  - `q_fabricated`(FABRICATED)：总结 `\tag` 编号归一后**不在 S**（编造/串号）→ 始终 FAIL。
  - `q_inconsistent`(INCONSISTENT)：编号**重复**，或**跨章**（`scope == 2` 时首分量 ≠ 当前章号）→ 始终 FAIL。
- **遗漏校验（默认 WARN，永不阻断）**：
  - `q_missing`(MISSING)：S 中属于本章、规范、前缀匹配的编号在总结无对应 `\tag` → 仅 WARN；书源确有该编号但属合理省略时，把它加入 `formula.ignore` 跳过比对，而非升级为 FAIL。
- **公式内容校验（人工对账）**：`verify_all` 末聚合各章 `q_rows` 写出 `<extract_dir>/formula_audit.md`，并排列出「总结 LaTeX / 书源文本片段」，机器**不判内容对错**。
- **S 为空降级**：若派生正则未抽到任何编号（S 空，通常是 `formula` 配置错），仅做结构检查（重复/章节前缀/规范），emit 一条 WARN「书源公式编号未抽到，请检查 verify_config.json 的 formula 配置」，**不判编造/遗漏 FAIL**。

## 阻断性 / 可修复
- FABRICATED / INCONSISTENT → 始终 FAIL（阻断）。
- MISSING → 仅 WARN，永不阻断。
- 不可 `--fix`（审计层，须回写作阶段修正编号）。

## 字节契约键（legacy dict，供 `DEFAULT_RESULT` / `print_result` 同步）
```contract-keys
q_checked
q_fabricated
q_inconsistent
q_missing
q_rows
```

## 实现（`verify/layers/q_layer.py`）
- `code = 'Q'`，`order = 17`（当前最大层 P=16 之后），`auto_fixable = False`。
- 经 `register_all.py` 的 pkgutil 自动发现注册，**无需改 register_all.py / VerifyManager / CLI**。
- `build_formula_patterns(ncomp)`：按 `depth` 生成源抽取正则（单捕获组、`depth` 决定分量数）。
- `SourceFormulaIndex.norm()`：去空白/去外层 `（）()`/去 `Eq.`·`Equation`·`式` 前缀；把 `.\-·,` 任一分隔符归一为 `.`；保留末尾字母后缀(a)。例 `（11.1-1）`→`11.1.1`，`Eq. 2.3`→`2.3`。
- `LayerResult` 返回的 5 个 `q_*` 键须与 `DEFAULT_RESULT`、本 `contract-keys`、以及 `report.py` 读取完全一致（由 `verify/tests/test_key_contract.py` 强制校验）。
