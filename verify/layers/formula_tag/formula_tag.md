# formula-tag 层（Q · `formula_tag`）

> **公用子流程（Sub-flow）。** 本文件是该校验层的**单一权威（SSOT）**，
> 同时作为可被其他消费者独立引用的校验子流程。
> 稳定标识符：`code="Q"`（字母代号，被 `SKILL.md` 与 per-book 记忆广泛引用，不可更改）；
> 语义名：`formula-tag`（`formula_tag`）。

## 目的

## 一句话目的
总结里带 `\tag{X}` 的公式，其序标必须与**书源公式编号集合 S** 1:1 对应；编造/错位/跨章阻断 FAIL，遗漏默认 WARN，公式内容人工对账。
## 前置

- `<book>/_extract/verify_config.json` 完整合法。
- 依赖数据的层需 EXTRACT 层已填充 `ctx.items / entry_keys / all_keys`
（见 [data_provider](../data_provider/data_provider.md)）。

## 步骤

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
## 本阶段规则

## 阻断性 / 可修复
- FABRICATED / INCONSISTENT → 始终 FAIL（阻断）。
- MISSING → 仅 WARN，永不阻断。
- 不可 `--fix`（审计层，须回写作阶段修正编号）。
## 出口

- 部分阻断：FABRICATED / INCONSISTENT → 始终 FAIL；MISSING 仅 WARN，永不阻断。不可 `--fix`。

## 相关代码

- 实现：`script/formula_tag.py`
  - `code="Q"`，`order=17`，`auto_fixable=False`。
- 注册：经 `../../script/register_all.py` 自动发现（`pkgutil` 扫描 `..` 子包），无需手动登记。

## 子流程

位置 + 内容保真对账见子流程 [`../../formula-manifest`](../../formula-manifest/formula-manifest.md)。

## 字节契约键（legacy dict，供 `DEFAULT_RESULT` / `print_result` 同步）

```contract-keys
q_checked
q_fabricated
q_inconsistent
q_missing
q_rows
```

## 实现备注

## 实现（`script/formula_tag.py`）
- `code = 'Q'`，`order = 17`（当前最大层 P=16 之后），`auto_fixable = False`。
- 经 `register_all.py` 的 pkgutil 自动发现注册，**无需改 register_all.py / VerifyManager / CLI**。
- `build_formula_patterns(ncomp)`：按 `depth` 生成源抽取正则（单捕获组、`depth` 决定分量数）。
- `SourceFormulaIndex.norm()`：去空白/去外层 `（）()`/去 `Eq.`·`Equation`·`式` 前缀；把 `.\-·,` 任一分隔符归一为 `.`；保留末尾字母后缀(a)。例 `（11.1-1）`→`11.1.1`，`Eq. 2.3`→`2.3`。
- `LayerResult` 返回的 5 个 `q_*` 键须与 `DEFAULT_RESULT`、本 `contract-keys`、以及 `report.py` 读取完全一致（由 `../../tests/test_key_contract.py` 强制校验）。
