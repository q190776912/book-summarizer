# Flow: verify（批量校验 / 通用校验关卡）

> 统一模板：目的 / 前置 / 步骤 / 本阶段规则 / 出口 / 相关代码 / 子流程
> 本流程是**语言无关**的校验逻辑，源语言总结与翻译语言总结共用同一套。
> `write-source`（步骤 3，源语言）与 `derive-translate`（翻译版）都引用本流程，区别仅在于被校验的是哪个语言目录。
>
> **本文件同时是「更大的公用子流程」**：它编排 `verify/<snake>/script/` 下的全部 8 个校验层模块，
> 既可被 `verify_chapter.py` 批量驱动，也可被其他消费者（如 `../flows/write-source`、`../flows/derive-translate`
> 或外部 skill）整体或按层引用。每层自身的语义 / 阈值 / `--fix` 范围 / 字节契约键是各自 `verify/<snake>/<snake>.md` 的 SSOT。

## 目的
某语言全部初稿写完后，**一次性批量校验该语言全部章节**，未过则用 `--fix` 自动修复后重验，直至 `verify PASS + KaTeX OK`。
## 前置
- 待校验语言的全部章节初稿写完。
- `_extract/verify_config.json` 完整合法（含 `formula` map 若书有公式）。
- `ctx.language` 由 config 的 `language` 字段决定（`en` / `cn`），仅作记录与标签语言提示；**EN/CN 的实际校验目标由文件名约定决定**（`ChapterN_*.md` 为英文源版、`第N章_*.md` 为中文派生版），`--scheme en` 控制英文两级编号比对。各校验层不依赖 `language` 切换逻辑，故无需为不同语言写两套校验。

## 校验层注册表（SSOT）
所有校验层脚本在 `verify/<snake>/script/<snake>.py`，子流程文档 `<snake>.md` 在 `verify/<snake>/` 目录内（与 `script/` 并列），
由 `script/register_all.py` 遍历 `verify/*/script/` 用 `importlib` 按裸名 `import` 自动发现并注册（无 `__init__.py`，下划线前缀模块跳过）。`code` 为稳定字母代号（被 `SKILL.md` 与 per-book 记忆广泛引用，**不可更改**）；
`name` 为语义名。`order` 决定运行顺序，`auto_fixable` / `fix_order` 决定 `--fix` 修复顺序。

| code | 语义名 | 模块（snake） | order | auto_fixable | fix_order | 子流程文档 |
|------|--------|---------------|-------|--------------|-----------|------------|
| EXTRACT | data-provider | data_provider | 0 | 否 | — | [data_provider](data_provider/data_provider.md) |
| D | section-continuity | section_continuity | 1 | 否 | — | [section_continuity](section_continuity/section_continuity.md) |
| B | item-numbering-integrity | item_numbering_integrity | 3 | 否 | — | [item_numbering_integrity](item_numbering_integrity/item_numbering_integrity.md) |
| E | figure（图完整性 + 图有效性） | figure_completeness | 5 | 否 | — | [figure_completeness](figure_completeness/figure_completeness.md) |
| F | format-verify（统一格式校验：KaTeX + 引用块 + 结构标签 + 条目分隔 + 证明间距 + 分隔空行 + 数学泄漏 + 引用块空行） | format_verify | 6 | 否 | — | [format_verify](format_verify/format_verify.md) |
| O | subitem-continuity | subitem_continuity | 15 | 否 | — | [subitem_continuity](subitem_continuity/subitem_continuity.md) |
| P | verbose-gates | verbose_gates | 16 | 否 | — | [verbose_gates](verbose_gates/verbose_gates.md) |
| Q | formula-tag | formula_tag | 17 | 否 | — | [formula_tag](formula_tag/formula_tag.md) |

## 步骤（有序）
1. **🔴 Q 层前置（若书有公式）**：确认 `verify_config.json` 含 `"formula"` map；缺失则按书实际公式编号推导写入（扫 `page_*.json` 的 `text[]` 实测段数：`C.N`→`depth=2`，`C.S.N`/`C.S-N`→`depth=3`，章级 `scope=2`，再写 `{"type":<码>,"depth":<段数>,"scope":2,"ignore":[]}`）。严禁在 `formula` 为 `None` 的 no-op 状态下宣称"公式校验通过"。
2. 批量校验：
   ```powershell
   python verify/script/verify_chapter.py --all <extract_dir> <book_dir>   # exit 0 才算通过
   ```
3. 未过则用 `--fix` 自动修复其中可修复层（`fix_order` 升序），再不带 `--fix` 复验确认 `exit 0`；至多 2 次仍不过则继续修，**严禁停下来问用户**。
4. 校验层顺序、语义、`--fix` 范围、字节契约键集合见上方注册表表格与本文件各子流程文档链接（每层脚本 `verify/<snake>/script/<snake>.py`，文档 `verify/<snake>/<snake>.md`，各自 SSOT）。
5. 公式序标保真（序列顺序 `ORDER_MISMATCH` + 小节定位 `MISPLACED`）已由 Q 层（`verify/formula_tag/`，opt-in `formula` 配置）覆盖；公式**内容**保真仍靠人工核对（机器不判内容对错）。

## 本阶段规则（🔴 内联）
- **规则1 批量纪律（最高优先级）**：🚫 **禁止逐章校验**（含"用第 1 章做 pilot 提前 verify"的变体）。唯一正确顺序：**先写完全书某语言初稿 → 全书配置定型 → 本阶段用 `verify_chapter.py --all` 一次性批量校验**。全书完成后最终汇报一次性给出。
  - 原因：书级配置需待全书编号形态定型后，D 层 `section_depths` / Q 层 `formula` 序标映射 / ordinal 分组都依赖全书编号形态，单章 verify 结果失真、属无效功；B–Q 若干判定需整章 / 整书上下文。
- **`--all` 自动发现章节文件**：合并文件（`第N章_*` / `ChapterN_*`）存在直接校验；否则按节拆分文件（`第N章M...` / `ChapterN_M...`）每语言一组，临时合并回整章校验（B 层完整性需整章一次通过），中英文各计一条结果；`--fix --all` 逐节文件单独修复。
- **失败处理**：任何一条不通过都算失败，必须修正后重验；修正方向严格单向（先源后译）。

## 出口条件
- 出口：`verify/script/verify_chapter.py --all` 对**该语言全部章节 `exit 0`**（`verify PASS + KaTeX OK`）。

## 相关代码（路径相对 skill 根目录）
- `script/verify_chapter.py`：统一强制校验关卡（`--all` / `--fix`）。
- `script/register_all.py`：遍历 `verify/*/script/` 自动发现并注册校验层模块。
- `script/base.py`：`VerifyLayer` / `LayerRegistry` / `VerifyManager` / `DEFAULT_RESULT` / `VerifyContext`（所有层的基类与编排入口）。
- `script/report.py`：`print_result` 字节输出（与 `DEFAULT_RESULT` 键集同步）。
- `../config/verify_config/make_config.py`：配置生成。
- `../config/ignore_chN/manage_ignore.py`：维护忽略清单（ignore keys / figures）。

## 子流程
- **各校验层**：`verify/<snake>/<snake>.md`（脚本在 `verify/<snake>/script/<snake>.py`，见上方注册表表格链接）——每层一个可独立引用的公用子流程。

## 新增一个校验层（模块约定）
1. 在 `verify/<snake>/script/` 下新建 `<snake>.py` 模块（`<snake>` 为小写蛇形语义名）。
2. 在 `<snake>.py` 中定义 `VerifyLayer` 子类，设 `code='<唯一大写字母或 EXTRACT>'`、`name='<语义名>'`、`order=<整数>`、`auto_fixable=<bool>`（可修复再设 `fix_order`）；无需 `__init__.py`，`register_all` 遍历 `verify/<snake>/script/` 发现该模块。
   共用 helper 放 `verify/script/`（如 `base.py`、`fig_common.py`、`struct_labels.py`）；`register_all` 仅扫描 `verify/<snake>/script/` 形式的层包，故 `script/` 下的模块不会被当作层注册。
3. 写入 `<snake>.md`：按统一模板（目的 / 前置 / 步骤 / 本阶段规则 / 出口 / 相关代码 / 子流程）写本层 SSOT；若声明字节契约键，用 ```` ```contract-keys ```` 块。
4. `script/register_all.py` 经 `importlib` 扫描 `verify/*/script/` 自动发现（按裸名 `import`；无 `__init__.py`，下划线前缀模块跳过），**无需手动登记**；将本层加入上方注册表表格。
5. 如需被其他消费者单独引用，在入口脚本跑过 `lib.boot.setup()` 后直接 `from <snake> import <Class>` 即可（裸名 import，boot 已将 `**/script` 注入 sys.path）。
