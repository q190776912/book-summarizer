# F 层 — FORMAT（format_verify，合并 C/G/H/I/J/K/L/M/N 九层格式校验）

> 本文件是 **F 层（统一格式校验层）** 的唯一权威详情（SSOT）。语义 / 阈值 / `--fix` 范围 / 实现均只在此描述；汇总索引与全局架构见 [`../verify.md`](../verify.md)。
> **新增 / 修改本层只改此文件 + 汇总表加一行 + 必要代码**，不要在其他文档重复描述。
> **注册机制**：本层脚本位于 `verify/layers/format_verify/script/format_verify.py`，由 `verify/script/register_all.py` 用 `importlib` 按裸名扫描 `verify/layers/*/script/` 自动发现并注册。`code = 'F'` 是稳定字母代号（被 `SKILL.md` 与 per-book 记忆广泛引用，**不可更改**）；新增层无需改 `register_all.py` / `VerifyManager` / CLI。
> **合并说明（2026-08-13）**：原 C（katex-validation）、G（blockquote-continuity）、H（structural-label-guard）、I（item-separator）、J（intra-item-dash）、K（proof-list-spacing）、L（separator-spacing）、M（math-blockquote-leak）、N（blockquote-spacing）九层已**统一并入本层（代号 F）**。九层的检测函数已内联进 `format_verify.py`，原九层目录退役备份于 `verify/_retired_layers/format_verify_legacy_2026-08-13/`。`code='F'` 此前在 E/F 合并中曾被 figure_validity 临时占用，现正式归属 format-verify（详见 `verify.md` 注册表备注）。

## 目的
统一全部「格式」类校验：KaTeX 渲染校验 + 引用块连续性/嵌套/例证空隙 + 结构标签守卫（4 子项）+ 条目分隔符完整性/条目内分隔符 + 证明-列表间距 + 分隔符空行 + 数学块引用泄漏 + 引用块空行过多。任一子项非空即整章 FAIL（KaTeX 与结构类同阻断）。

## 步骤（语义与检查内容）
全部检测函数为内联实现（与退役九层逐字一致），`run()` 一次性返回下方 15 个字节契约键：

- **KaTeX（原 C 层，只读、阻断 FAIL）**：调用 `flows/write-source/format/script/check_katex.py` 子进程做真渲染校验；`katex_errors`(bool) / `katex_lines`(list)。子进程启动失败（缺失 node / katex JS 运行时）时降级为 `(False, [])`，绝不令 `verify_one` 崩溃（仅当 katex 运行时就绪时才真正校验）。
- **引用块连续性（原 G 层，阻断 FAIL）**：
  - `quote_gaps`：bare 空行切断 `> **证明/例**` 块 → 改 `> `（仅 `quote_gaps` 可 `--fix`）。
  - `nested_bq`：`> > **证明/例**` 嵌套 → 展平为单层 `>`（只读）。
  - `ex_proof_gaps`：`> **例**` 与 `> **证明**` 间裸空行/裸 `$$` 或同行的「例+证明」→ 拆成连续 `>` 块（元组 `([阻断], [警告])`，只读）。
- **结构标签守卫（原 H 层，4 子项，均阻断 FAIL）**：
  - `h_structural_bq`：定义/定理/… 结构标签在 `>` 内（须顶层）→ 去 `> ` 前缀（可 `--fix`）。
  - `h_stmt_bq`：定理/定义的陈述内容（`（N）`/`**（N）**`/`$$`/`- （a）`）误包进 `>` → 解包到顶层（可 `--fix`）。
  - `h_ul_bq`：无标签的 `>` 块（非 证明/证/例/注/说明/脚注）→ 去 `>` 前缀（可 `--fix`）。
  - `h_mbq`：须进 `>` 的标签（证明/证/例/注/…）在顶层 → 加 `> ` 前缀（可 `--fix`）。
- **条目分隔符完整性（原 I 层，阻断 FAIL）**：`i_sep_gaps`：连续 item 间缺 `---` → 插 `---`（可 `--fix`）。
- **条目内分隔符（原 J 层，阻断 FAIL）**：`j_header_dash`：`---` 落在条目块内部（标题↔子点 / 子点↔子点）→ 删除该 `---`（可 `--fix`）。
- **证明-列表间距（原 K 层，阻断 FAIL）**：`k_proof_list`：编号列表紧接 `> **证明**` 缺空行 → 补空行（可 `--fix`）。
- **分隔符空行（原 L 层，阻断 FAIL）**：`l_sep_blanks`：`---` 上下缺空行 → 补空行（可 `--fix`）。
- **数学块引用泄漏（原 M 层，阻断 FAIL）**：`m_dm_gt`：`$$...$$` 内有 `>` 行 → 去 `>` 前缀（可 `--fix`）。
- **引用块空行过多（原 N 层，阻断 FAIL）**：`n_bq_empty`：`>` 块内连续空 `>` 行超过 1 → 折叠为 1（可 `--fix`）。

> 上述所有阈值/形态与退役九层完全一致；`flows/write-source/format/format.md`（SSOT）定义的格式规则本来即由这九层 + katex 子进程 + 格式管线脚本共同强制，本合并**不新增任何检查**，仅把输出收敛为单一 `F-LAYER FORMAT` 段（见 `report.py`）。

## 本阶段规则（阻断性 / 可修复）
- 15 个键中任一非空（KaTeX 除外：仅 `katex_lines` 非空且 returncode≠0 时阻断）→ 整章 FAIL。
- 本检测层 `auto_fixable = False`：**自动修复不由本层完成**，改由下方 FIXERS 注册表（按原 fixer 代号）执行，字节兼容不变。

## 出口条件
任一格式子项非空 → 整章 FAIL（KaTeX 渲染错误亦阻断）。

## 相关代码（`verify/layers/format_verify/script/format_verify.py`）
- `code = 'F'`，`order = 6`，`auto_fixable = False`。
- `run()` 返回元数据含 15 个字节契约键（见下方）。`ex_proof_gaps` 为二元组 `([], [])`（阻断, 警告），其余为 list。

## 子流程（自动修复）
自动修复逻辑位于 `verify/layers/format_verify/script/fix_*.py`，各自在模块顶层调用 `register_fixer(code, fix_order, apply_fix)` 注册，**fixer 代号沿用原层字母**，fix-dict 键顺序字节兼容不变：

| fixer 代号 | 修复模块 | fix_order | fix_dict 键 | 修复对象 |
|-----------|----------|-----------|-------------|----------|
| H | fix_structural_label_guard.py | 1 | `h`, `h_stmt`, `h_ul`, `h_mbq`（硬约束顺序） | h_structural_bq / h_stmt_bq / h_ul_bq / h_mbq |
| G | fix_blockquote_continuity.py | 5 | `g` | quote_gaps |
| I | fix_item_separator.py | 6 | `i` | i_sep_gaps |
| J | fix_intra_item_dash.py | 7 | `j` | j_header_dash |
| K | fix_proof_list_spacing.py | 8 | `k` | k_proof_list |
| L | fix_separator_spacing.py | 9 | `l` | l_sep_blanks |
| M | fix_math_blockquote_leak.py | 10 | `m` | m_dm_gt |
| N | fix_blockquote_spacing.py | 11 | `n` | n_bq_empty |

> `--fix` 最终写回的变更字典顺序固定为 `{h, h_stmt, h_ul, h_mbq, g, i, j, k, l, m, n}`（与旧 `fix_all_layers` 完全一致）。KaTeX（原 C）不自动修复。

## 字节契约键
```contract-keys
katex_errors
katex_lines
quote_gaps
nested_bq
ex_proof_gaps
h_structural_bq
h_stmt_bq
h_ul_bq
h_mbq
i_sep_gaps
j_header_dash
k_proof_list
l_sep_blanks
m_dm_gt
n_bq_empty
```
