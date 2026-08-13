# Flow: verify（批量校验 / 通用校验关卡 / Stage 4）

> 统一模板：目的 / 前置 / 步骤 / 本阶段规则 / 出口 / 相关代码 / 子流程
> 本流程是**语言无关**的校验逻辑，源语言总结与翻译语言总结共用同一套。
> `verify-source`（源语言）与 `derive-translate`（翻译版）都引用本流程，区别仅在于被校验的是哪个语言目录。
>
> **本文件同时是「更大的公用子流程」**：它编排 `verify/layers/<snake>/script/` 下的全部 17 个校验层模块，
> 既可被 `verify_chapter.py` 批量驱动，也可被其他消费者（如 `../flows/verify-source`、`../flows/derive-translate`
> 或外部 skill）整体或按层引用。每层自身的语义 / 阈值 / `--fix` 范围 / 字节契约键是各自 `verify/layers/<snake>/<snake>.md` 的 SSOT。

## 目的
某语言全部初稿写完后，**一次性批量校验该语言全部章节**，未过则用 `--fix` 自动修复后重验，直至 `verify PASS + KaTeX OK`。
## 前置
- 待校验语言的全部章节初稿写完。
- `_extract/verify_config.json` 完整合法（含 `formula` map 若书有公式）。
- `ctx.language` 由 config 决定（`en` / `cn`），`verify_chapter.py` 据此切换标签类映射，无需为不同语言写两套逻辑。

## 校验层注册表（SSOT）
所有校验层脚本在 `verify/layers/<snake>/script/<snake>.py`，子流程文档 `<snake>.md` 在 `verify/layers/<snake>/` 目录内（与 `script/` 并列），
由 `script/register_all.py` 遍历 `verify/layers/*/script/` 用 `importlib` 按裸名 `import` 自动发现并注册（无 `__init__.py`，下划线前缀模块跳过）。`code` 为稳定字母代号（被 `SKILL.md` 与 per-book 记忆广泛引用，**不可更改**）；
`name` 为语义名。`order` 决定运行顺序，`auto_fixable` / `fix_order` 决定 `--fix` 修复顺序。

| code | 语义名 | 模块（snake） | order | auto_fixable | fix_order | 子流程文档 |
|------|--------|---------------|-------|--------------|-----------|------------|
| EXTRACT | data-provider | data_provider | 0 | 否 | — | [data_provider](layers/data_provider/data_provider.md) |
| D | section-continuity | section_continuity | 1 | 否 | — | [section_continuity](layers/section_continuity/section_continuity.md) |
| B | item-numbering-integrity | item_numbering_integrity | 3 | 否 | — | [item_numbering_integrity](layers/item_numbering_integrity/item_numbering_integrity.md) |

> **注（2026-08-13 重构）**：原 A 层（missing-items，整章完整性 `truly_missing`/`mentioned_only`/`extra`）与原独立 Q/R 的查漏逻辑（整类首项缺失 + over-mark 守卫，原 P2 收于 EXTRACT 层）已**统一并入 B 层**。B 现为「查漏」唯一权威：`truly_missing`（书有、md 全宇宙无 → 阻断）、`mentioned_only`（仅复核）、`extra`（仅参考）、以及提取侧查漏均由其产出。EXTRACT 层退化为纯数据供给（items / entry_keys / all_keys / label_warns），与 B 解耦。
| E | figure（图完整性+图有效性，原 E/F 合并） | figure_completeness | 5 | 否 | — | [figure_completeness](layers/figure_completeness/figure_completeness.md) |
| F | format-verify（合并格式校验，原 C/G/H/I/J/K/L/M/N 九层统一） | format_verify | 6 | 否 | — | [format_verify](layers/format_verify/format_verify.md) |

> **注（2026-08-13 重构）**：原 F 层（figure-validity，图有效性 / cv2 解码校验：文件缺失·无法解码·单边<20px 阻断、近空白低方差仅警告）已**并入 E 层**。figure 校验现为代号 `E` 的单层：一次性载入 `figure_index.json` 并按章过滤，既做 caption↔index 对账（`fig_missing` 阻断 / `fig_extra` 警告），又做裁剪图解码校验（`fig_invalid` 阻断 / `fig_invalid_warn` 警告）。
> 代号 `F` 本身已**复用**为 **format-verify** 合并格式校验层（见上表 F 行）：把原 `C`(katex) / `G`(blockquote-continuity) / `H`(structural-label-guard) / `I`(item-separator) / `J`(intra-item-dash) / `K`(proof-list-spacing) / `L`(separator-spacing) / `M`(math-blockquote-leak) / `N`(blockquote-spacing) 九个格式相关校验**合并为单一层**，统一输出为 `report.py` 的 `F-LAYER FORMAT` 段落。`format_verify` 层 `auto_fixable=False`，其可修复项由迁移至 `verify/layers/format_verify/script/fix_*.py` 的 8 个 fix 模块承担——它们仍以**原代号 H/G/I/J/K/L/M/N** 经 `register_fixer` 注册进 `FIXERS`（保留 `fix_order` 与 fix-dict 字节序），故 `--fix` 行为不变。九层旧目录备份于 `verify/_retired_layers/format_verify_legacy_2026-08-13/`，figure_validity 旧目录备份于 `verify/_retired_layers/figure_validity_2026-08-13/`。
| O | subitem-continuity | subitem_continuity | 15 | 否 | — | [subitem_continuity](layers/subitem_continuity/subitem_continuity.md) |
| P | verbose-gates | verbose_gates | 16 | 否 | — | [verbose_gates](layers/verbose_gates/verbose_gates.md) |
| Q | formula-tag | formula_tag | 17 | 否 | — | [formula_tag](layers/formula_tag/formula_tag.md) |

## 步骤（有序）
1. **🔴 Q 层前置（若书有公式）**：确认 `verify_config.json` 含 `"formula"` map；缺失则按书实际公式编号推导写入（扫 `page_*.json` 的 `text[]` 实测段数：`C.N`→`depth=2`，`C.S.N`/`C.S-N`→`depth=3`，章级 `scope=2`，再写 `{"type":<码>,"depth":<段数>,"scope":2,"ignore":[]}`）。严禁在 `formula` 为 `None` 的 no-op 状态下宣称"公式校验通过"。
2. 批量校验：
   ```powershell
   python verify/script/verify_chapter.py --all <extract_dir> <book_dir>   # exit 0 才算通过
   ```
3. 未过则用 `--fix` 自动修复其中可修复层（`fix_order` 升序），再不带 `--fix` 复验确认 `exit 0`；至多 2 次仍不过则继续修，**严禁停下来问用户**。
4. 校验层顺序、语义、`--fix` 范围、字节契约键集合见上方注册表表格与本文件各子流程文档链接（每层脚本 `verify/layers/<snake>/script/<snake>.py`，文档 `verify/layers/<snake>/<snake>.md`，各自 SSOT）。
5. （可选，位置+内容保真）跑公式 manifest 对账（见子流程 `formula-manifest`）。

## 本阶段规则（🔴 内联）
- **规则1 批量纪律（最高优先级）**：🚫 **禁止逐章校验**（含"用第 1 章做 pilot 提前 verify"的变体）。唯一正确顺序：**先写完全书某语言初稿 → 全书配置定型 → 本阶段用 `verify_chapter.py --all` 一次性批量校验**。全书完成后最终汇报一次性给出。
  - 原因：书级配置需待全书编号形态定型后，D 层 `section_depths` / Q 层 `formula` 序标映射 / ordinal 分组都依赖全书编号形态，单章 verify 结果失真、属无效功；B–Q 若干判定需整章 / 整书上下文。
- **`--all` 自动发现章节文件**：合并文件（`第N章_*` / `ChapterN_*`）存在直接校验；否则按节拆分文件（`第N章M...` / `ChapterN_M...`）每语言一组，临时合并回整章校验（B 层完整性需整章一次通过），中英文各计一条结果；`--fix --all` 逐节文件单独修复。
- **失败处理**：任何一条不通过都算失败，必须修正后重验；修正方向严格单向（先源后译）。

## 出口条件
- 出口：`verify/script/verify_chapter.py --all` 对**该语言全部章节 `exit 0`**（`verify PASS + KaTeX OK`）。

## 相关代码（路径相对 skill 根目录）
- `script/verify_chapter.py`：统一强制校验关卡（`--all` / `--fix`）。
- `script/register_all.py`：遍历 `verify/layers/*/script/` 自动发现并注册校验层模块。
- `layers/script/base.py`：`VerifyLayer` / `LayerRegistry` / `VerifyManager` / `DEFAULT_RESULT` / `VerifyContext`（所有层的基类与编排入口）。
- `script/report.py`：`print_result` 字节输出（与 `DEFAULT_RESULT` 键集同步）。
- `../config/verify_config/make_config.py`：配置生成。
- `../config/ignore_chN/manage_ignore.py`：维护忽略清单（ignore keys / figures）。

## 子流程
- **各校验层**：`verify/layers/<snake>/<snake>.md`（脚本在 `verify/layers/<snake>/script/<snake>.py`，见上方注册表表格链接）——每层一个可独立引用的公用子流程。
- [`formula-manifest`](formula-manifest/formula-manifest.md) — 公式 manifest 保真对账（Step 3.6）。

## 新增一个校验层（模块约定）
1. 在 `verify/layers/<snake>/script/` 下新建 `<snake>.py` 模块（`<snake>` 为小写蛇形语义名）。
2. 在 `<snake>.py` 中定义 `VerifyLayer` 子类，设 `code='<唯一大写字母或 EXTRACT>'`、`name='<语义名>'`、`order=<整数>`、`auto_fixable=<bool>`（可修复再设 `fix_order`）；无需 `__init__.py`，`register_all` 遍历 `verify/layers/<snake>/script/` 发现该模块。
   共用 helper 放 `layers/script/_fig_common.py` / `_struct_labels.py`（下划线前缀，自动跳过注册）。
3. 写入 `<snake>.md`：按统一模板（目的 / 前置 / 步骤 / 本阶段规则 / 出口 / 相关代码 / 子流程）写本层 SSOT；若声明字节契约键，用 ```` ```contract-keys ```` 块。
4. `script/register_all.py` 经 `importlib` 扫描 `verify/layers/*/script/` 自动发现（按裸名 `import`；无 `__init__.py`，下划线前缀模块跳过），**无需手动登记**；将本层加入上方注册表表格。
5. 如需被其他消费者单独引用，在入口脚本跑过 `lib.boot.setup()` 后直接 `from <snake> import <Class>` 即可（裸名 import，boot 已将 `**/script` 注入 sys.path）。
