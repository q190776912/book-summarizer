# Sub-flow: write-source / format / katex（KaTeX 问题识别与修复速查）

> 速查；**完整 KaTeX 规则与修复语法以 `formatting.md` 为准（SSOT）**。本文件来自原 SKILL.md「KaTeX 问题识别与修复」FAQ。

## 一站式修复（推荐）
```powershell
python format/fix_katex.py <book_dir>            # 处理模式 1–8
python format/fix_katex.py <book_dir> --dry-run  # 预览
python format/check_katex.py <file>              # 复验（不加 --fix）
```
> 该脚本处理模式 1–8，**不含** `check_katex --fix` 的级联破坏风险（`--fix` 只修格式，不插入 `$`）。

## 根因总览（来自实际修复经验）
| # | 问题模式 | 根因 |
|---|---------|------|
| 1 | **`$formula，` 未闭合 `$`** | 中文逗号/句号放在 `$` 内未补 `$`；缺闭合 `$` 会吞噬紧随的 `$$` |
| 2 | **`$$` 包裹非数学内容** | 自动脚本错误地在含中文 / `$...$` 的行外加 `$$...$$` |
| 3 | **断裂的命令（`\int` → `\int`）** | 修复脚本替换时破坏命令间距 |
| 4 | **`$$` 包裹 `## §` 节标题** | 自动脚本误把标题行包进 `$$` |
| 5 | **CD 交换图语法错误** | `@A\int A` 在 KaTeX CD 中无法解析；`@VV\text{RN} A` 尾字符应为 `V` |
| 6 | **集合符号 `{x` 花括号未转义** | `$A_n={x$` → 缺 `\{` / `\}` |
| 7 | **`$$\text{N}pt\]` 对齐参数** | `\\[\text{N}pt]` 被改写为 `$$\text{N}pt]` |
| 8 | **`$$` 块内空行** | 空白行插入 `$$` 内部，部分渲染器中断显示块 |

## 已知危险操作（❌ 禁止）
1. **`_extract/fix_cn_files.py` 的 `fix_dollar_count`**（已修复）：原把 `$formula$.` 误改为 `$formula.`，制造未闭合 `$` → 吞噬 `$$`。已修正为"插入 `$` 而非删除"。
2. **`mathify_plaintext.py`**：已暂停使用。会把已有 `\(...\)` 误当普通字符产生 `$\\(...$` 坏模式。已被 `fix_katex.py` 取代。
3. **多层 fix 脚本串联**：A→B→C 各自只修自己模式而未知模式被前一个破坏。→ 用 `fix_katex.py` 一站式修复。

## 手动修复模式
**模式 1（缺闭合 `$`）**：`记 $\langle h,\mu\rangle=\int_X h(x)\,\mu(dx).` ✅ vs `记 $\langle h,\mu\rangle=\int_X h(x)\,\mu(dx).` ❌（后跟 `$$` 会被吞噬）。诊断：搜"奇数个 `$` 的行"，查是否以 `$formula，` / `$formula.` 结尾且之后有 `$$`。
**模式 2（`$$` 包非数学）**：`上箭头表示积分算子, 下箭头表示 Radon–Nikodym 导数.` ✅ vs `$$ 上箭头表示积分算子, 下箭头表示 Radon–Nikodym 导数. $$` ❌。
**模式 5（CD 交换图）**：
```text
\begin{CD}
\mathcal M_a @>P>> \mathcal M_a\\
@V\int VV @VV\text{RN}V\\   ← 下箭头 + 积分标签
L^1_+ @>P>> L^1_+
\end{CD}
```
KaTeX CD 箭头速查：`@>>>` 右 / `@<<<` 左 / `@VVV` 下 / `@AAA` 上；带标签 `@>label>>` / `@VlabelV` / `@AlabelA`；方向标记字符（V/A/\>/<）必须**首尾匹配**；`\int` 作上箭头标签会失败，改用 `@V\int VV`。

## 验证通过后的残余警告
`check_katex` 报告的 "naked LaTeX command" / "raw Unicode math arrow" 是**外观警告**，不影响渲染（中文正文引用数学符号时不需全程数学模式）。需消除可给单符号加 `$` 包裹，非强制。
