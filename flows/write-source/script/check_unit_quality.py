"""check_unit_quality.py — 单元级「写对」质量校验（write-source 步骤 5 门控的一部分）

全部复用 verify 流程已有检测脚本，按 verify F 层校验顺序执行，不重新造轮子：
  F 层（按 verify 顺序）：
    1. 裸 Unicode 箭头：`katex_heuristics.find_raw_arrow_errors`
    2. 裸 LaTeX 命令：`katex_heuristics.find_naked_command_errors`
    3. `$` 吞噬前缀：`katex_heuristics.find_swallowed_prefix_errors`
    4. 裸数学/裸函数调用：`katex_heuristics.find_bare_math_errors`
    5. `$` 奇偶配对：内联计算
    6. `$$` 闭合：`check_katex.check_display_math_closure`
    7. 围栏形态（`_fence_issues`，移植 check_katex.py Pass 1 口径）：单行
       `$$...$$` 块（真实 Markdown 预览器不认，而 katex_validate.js 支持、
       closure 只查 EOF——两道渲染检查都看不见）/ `$$` 附着内容 / blockquote
       内 `> $$` 前缺空 `>` 行 / 顶层 `$$` 前缺空行 / `\tag` 在数学模式外
  P 层：
    7. 证明过长：`verbose_gates.check_verbose_proofs`
  H/G 层：
    8. 结构标签：`struct_labels.TOP_LEVEL_HEADER_RE`
    9. example blockquote：`format_verify.check_example_blockquote_lines`
    9b. 块引用/例/证明/列表结构（`_run_format_verify_unit_checks`，临时 .md
        复用 format_verify 原函数，不复制逻辑）：nested_bq / ex_proof_gaps /
        h_structural_bq / h_stmt_bq / h_ul_bq / h_mbq / k_proof_list /
        n_bq_empty / m_dm_gt；文档级专属（`---` 分隔线 / 标题上下文类：
        i_sep / j_header / l_sep / heading_* / quote_gaps）不搬——孤立单元
        无 `---`、标题即首行，搬了必误报。
  补充：
    10. OCR 残留模式（verify 不覆盖的 OCR 特有命令 / garbled / 编码损坏）
    11. 内容审阅类残留（「没审阅改好」的典型痕迹，writing-rules 明确须剔除）：
        QED 结尾框「口/□」独立行、OCR 乱码重复片段、单元内私造 `#` 标题行
    12. 单元级公式序标对账（`expected_tags` 提供时）：以内容化契约
        （`chapter_tag_map`）要求该单元携带的 `formula.tag` 为真值，缺失（漏写
        编号公式）与编造（多出编号）均判不通过——Q 层是章级末步，单元粒度提前拦
  🔴 本模块只做静态/启发式检测；**真实 KaTeX 渲染**（`katex_render.run_render_check`，
    katex_validate.js 按章批量跑、错误映射回单元）由 `gate_units.gate_chapter` 承担。
  🔴 调用方（gate_units / flow_runner 证据复核）必须 **fail-closed**：本函数抛异常时
    该单元按「质量未达标」处理，绝不放行。

用法：``check_unit_quality.check_body(utype, name, body) -> (ok, problems)``
"""
import os
import re
import sys
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[2])
for _p in (_ROOT, os.path.join(_ROOT, "lib"),
           os.path.join(_ROOT, "verify", "format_verify", "script"),
           os.path.join(_ROOT, "verify", "verbose_gates", "script"),
           os.path.join(_ROOT, "verify", "script")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

# ── 复用 verify 已有检测（全部 import，不重新实现）────────────────────────
from check_katex import check_display_math_closure   # F 层：$$ 闭合
from katex_heuristics import (                        # F 层：裸数学检测
    find_bare_math_errors,
    find_raw_arrow_errors,
    find_naked_command_errors,
    find_swallowed_prefix_errors,
)
from verbose_gates import check_verbose_proofs        # P 层：证明过长
from struct_labels import TOP_LEVEL_HEADER_RE         # H 层：结构标签
from format_verify import check_example_blockquote_lines  # G 层：example blockquote

# ── 复用 format_verify 文档级检查（块引用/例/证明/列表结构），单元级化 ──
# 这些检查在 verify 里以文件为输入；单元门控把单元正文写到临时 .md 后复用原函数，
# **不复制逻辑**（保持单一真相源，避免已踩过的「三份分叉」坑）。文档级专属的
# `---` 分隔线 / 标题上下文类检查（i_sep / j_header / l_sep / heading_* /
# quote_gaps）不搬——孤立单元里无 `---`、标题即首行，搬了会误报。
from format_verify import (
    check_nested_blockquotes,          # G: > > ** 嵌套块引用
    check_example_proof_gap,           # G: 例与证明间断裂 / 同行
    check_h_structural_blockquote,     # H: 结构标签误入 `>` / 孤儿空 `>`
    check_h_statement_in_blockquote,   # H: 陈述内容误包 `>`
    check_unlabeled_blockquotes,       # H: `>` 块无标签
    check_labels_missing_blockquote,   # H: 标签在顶层未包 `>`
    check_proof_after_list,            # K: 列表末项后直接接新块无空行
    check_excessive_bq_empty_lines,    # N: 连续空 `>` 行
    check_displaymath_gt,              # M: `$$` 块内泄 `>`
)

# ── 本模块专有：OCR 公式残留（verify 不覆盖）──────────────────────────────
_OCR_FORMULA_PATTERNS = [
    (r"\\ensuremath\s*\{", "OCR 残留 \\ensuremath（应改为直接 KaTeX）"),
    (r"\\pmb\s*\{", "OCR 残留 \\pmb（应改为 \\mathbf 或 \\boldsymbol）"),
    (r"\\boldsymbol\s*\{[^}]*\}\s*[A-Za-z]", "OCR 残留 \\boldsymbol 在数学模式外"),
    (r"[\u00e0-\u00ff]{3,}", "garbled Unicode 片段（OCR 编码错误）"),
    (r"\\sun\b", "OCR 残留 \\sun（应改为具体数学符号）"),
    (r"\\b\s*\{", "OCR 残留 \\b 命令"),
    (r"\\E\s*\{", "OCR 残留 \\E（应改为 \\operatorname{E} 或具体符号）"),
    (r"\ufffd", "replacement character（U+FFFD）残留（编码损坏，须回源修正）"),
]

# ── 本模块专有：内容审阅类残留（「没审阅改好」的典型痕迹）─────────────────
# QED 结尾框独立行（writing-rules「内容清理与保真」明确须剔除；∎ 同属裸 Unicode
# 数学字形，也不该以独立行形式出现）。
_QED_BOX_LINE_RE = re.compile(r"^[口□■◻◼∎]$")
# 单元内出现 ATX 标题行 = 自造层级 / 把标题并进条目（标题是独立 section 单元；
# writing-rules：不得自创层级、不得无中生有）。
_HEADING_LINE_RE = re.compile(r"\s{0,3}#{1,6}\s")


def _prose_text(line_list):
    """剥掉数学模式，只留散文段（OCR 残留模式只对数学模式外文本有意义）。

    按 `$` 配对剥除：
      - 先剥 blockquote 前缀 `>`（否则 `> $$` 围栏识别不到，块内公式被当散文）；
      - `$$` 围栏内的行整行跳过（含围栏行本身）；
      - 其余行按单个 `$` 分段，偶数段（数学外）保留。
    """
    out = []
    in_display = False
    for ln in line_list:
        content = re.sub(r"^\s*>\s?", "", ln)  # 剥一层 blockquote 前缀
        s = content.strip()
        if s == "$$" or (s.startswith("$$") and not s.endswith("$$")):
            in_display = not in_display
            continue
        if s.startswith("$$") and s.endswith("$$") and len(s) > 4:
            continue  # 单行 $$...$$ 整行是数学
        if in_display:
            continue
        parts = content.split("$")
        out.append("".join(parts[0::2]))  # 偶数段 = 数学外
    return "\n".join(out)


def _count_inline_dollars(line_list):
    """计算数学模式外的 `$` 总数，奇数 = 未配对。"""
    in_display = False
    count = 0
    for ln in line_list:
        s = ln.strip()
        if s == "$$" or (s.startswith("$$") and not s.endswith("$$")):
            in_display = not in_display
            continue
        if s.startswith("$$") and s.endswith("$$") and len(s) > 4:
            continue
        if in_display:
            continue
        # 剥掉转义的 \$
        content = re.sub(r"\\\$", "", ln)
        # 按 $ 分段，统计 $ 数量 = 段数 - 1
        count += content.count("$")
    return count


# ── F 层围栏形态（移植 check_katex.py Pass 1 的单元化轻量版）──────────────
# katex_validate.js 的状态机**显式支持单行 `$$...$$` 块**（渲染 OK 不报错），
# check_display_math_closure 只查 EOF 闭合——两者都看不见「一对 $$ 挤在一行」
# 这类形态违规，而真实 Markdown 预览器多数不认单行块（显示原文/渲染失败）。
# 故单元门控必须用与 F 层一致的 heuristic 把形态查住。

def _fence_issues(line_list):
    """`$$` 围栏形态检测（F 层口径）。返回问题列表。

    检测（与 verify F 层 check_katex.py Pass 1 同口径）：
      F7a) single-line display math：`$$...$$` 挤在一行（剥 `>` 后）——须拆行；
      F7b) $$ 附着内容：开围栏 `$$xxx` / 闭围栏 `xxx$$`（同行还有内容）——须拆行；
      F7c) blockquote 内 `> $$` 开围栏的上一非空行不是空 `>` 行（如紧接
           `> **证明**：` 文字）——须插一个空 `>` 行；
      F7d) 顶层开 `$$` 的上一非空行是普通文本（缺空行）；
      F7e) `\tag{` 出现在数学模式外（tag 必须在 `$$` 块内）。
    """
    problems = []
    in_math = False        # 顶层 $$ 块
    in_bq_math = False     # > $$ 块
    prev_raw = None        # 紧邻上一非空行（lstrip 原文；空行清空）
    for raw in line_list:
        is_bq = raw.lstrip().startswith(">")
        content = re.sub(r"^\s*>\s?", "", raw) if is_bq else raw
        s = content.strip().replace("\\$", "")
        if s == "$$":
            if is_bq:
                if in_bq_math:
                    in_bq_math = False
                else:
                    if in_math:  # 跨层错位：> $$ 关掉了顶层块
                        in_math = False
                    # F7c：上一非空行必须是空 `>` 行（`>` / `> `）
                    if prev_raw is not None:
                        prev_is_empty_bq = (
                            prev_raw.startswith(">")
                            and re.sub(r"^\s*>\s?", "", prev_raw).strip() == "")
                        if not prev_is_empty_bq:
                            problems.append(
                                "missing empty > line before > $$（blockquote 内 "
                                "`> $$` 前须插一个空 `>` 行，上一行：%s）"
                                % prev_raw.strip()[:30])
                    in_bq_math = True
            else:
                if in_math:
                    in_math = False
                elif in_bq_math:
                    in_bq_math = False
                else:  # F7d：顶层开围栏前须空行（上一非空行不能是普通文本）
                    if prev_raw is not None and not prev_raw.startswith(">"):
                        problems.append(
                            "missing blank line before opening $$（$$ 前须空行，"
                            "上一行：%s）" % prev_raw.strip()[:30])
                    in_math = True
            prev_raw = None
            continue
        if not in_math and not in_bq_math:
            # F7a / F7b：文本模式下的含 $$ 行（纯围栏行已在上面 continue）
            core = s
            if core.startswith("$$") and not core.endswith("$$") and len(core) > 2:
                problems.append(
                    "opening $$ attached to formula content — split onto its own "
                    "lines（%s）" % core[:40])
            elif core.endswith("$$") and not core.startswith("$$") and len(core) > 2 \
                    and "$$" not in core[:-2]:
                problems.append(
                    "closing $$ attached to formula content — split onto its own "
                    "lines（%s）" % core[:40])
            elif core.count("$$") >= 2:
                problems.append(
                    "single-line display math — split $$ onto separate lines（%s）"
                    % core[:40])
        if s:
            prev_raw = raw.lstrip()
        else:
            prev_raw = None  # 空行（含空 `>` 行）= 与上一非空行不再紧邻
    return problems


# ── 复用 format_verify 的单元级可查检查（块引用/例/证明/列表结构）────────────
# 这些检查在 verify 里以「文件」为输入；单元门控把单元正文写临时 .md 后复用原函数，
# 行号相对于单元正文（临时文件即 body 内容），与单元内行一致。文档级专属
# （`---` 分隔线 / 标题上下文）检查不入此列，避免孤立单元误报。
# 🔴 fail-closed：本函数内不吞掉子检查异常——任一子检查抛错会冒泡到 check_body，
#   由 gate_units 统一按「质量未达标」fail-closed 处理（绝不静默放行）。
_FV_UNIT_CHECKS = (
    check_nested_blockquotes,          # G: > > ** 嵌套
    check_example_proof_gap,           # G: 例与证明间断裂 / 同行（返回 (errors, warns)）
    check_h_structural_blockquote,     # H: 结构标签误入 `>` / 孤儿空 `>`
    check_h_statement_in_blockquote,   # H: 陈述内容误包 `>`
    check_unlabeled_blockquotes,       # H: `>` 块无标签
    check_labels_missing_blockquote,   # H: 标签在顶层未包 `>`
    check_proof_after_list,            # K: 列表末项后直接接新块无空行
    check_excessive_bq_empty_lines,    # N: 连续空 `>` 行
    check_displaymath_gt,              # M: `$$` 块内泄 `>`
)


def _run_format_verify_unit_checks(line_list):
    """把单元正文写临时 .md，复用 format_verify 的单元级检查，返回问题字符串列表。

    复用而非复制：与 verify FLayer 同一份逻辑，杜绝「三份分叉」。行号即单元内行号。
    """
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".md",
                                     encoding="utf-8", delete=False) as f:
        f.write("\n".join(line_list))
        tmp = f.name
    try:
        problems = []
        for fn in _FV_UNIT_CHECKS:
            res = fn(tmp)              # 任一异常向外冒泡 → fail-closed
            if isinstance(res, tuple):
                msgs = res[0] if res else []
            else:
                msgs = res or []
            for m in msgs:
                problems.append("[F/H-unit] " + m.strip())
        return problems
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


# ── 主入口 ────────────────────────────────────────────────────────────────
def check_body(utype, name, body, expected_tags=None):
    """对单个单元正文做「写对」质量校验。返回 (ok, problems)。

    按 verify F 层校验顺序执行全部检测，报告所有错误（不只第一个）。
    ``expected_tags``：契约要求该单元携带的公式编号集合（裸编号字符串列表，
    来自内容化契约 formula.tag）——提供时做**单元级 tag 对账**：缺失（漏写
    编号公式）与多出（编造编号）均判不通过；None = 跳过（调用方无契约上下文）。
    """
    if utype not in ("item", "desc", "exercise"):
        return True, []
    lines = body.splitlines(keepends=True)
    while lines and lines[0].startswith("<!--"):
        lines.pop(0)
    body_clean = "".join(lines)

    all_problems = []
    line_list = body_clean.splitlines()

    # ── F 层：按 verify 校验顺序 ──────────────────────────────────────

    # exercise 单元的 $...$ 分隔符序列因 OCR 交错常有破损，
    # _strip_math_and_code 无法正确判断内外，跳过依赖它的 F 层检查
    if utype != "exercise":
        # F1) 裸 Unicode 箭头（→ ⇒ ↔ 等在 $...$ 外）
        errs = find_raw_arrow_errors(line_list)
        if errs:
            all_problems.extend(e.strip() for e in errs)

        # F2) 裸 LaTeX 命令（\mathbf \delta 等在 $...$ 外）
        errs = find_naked_command_errors(line_list)
        if errs:
            all_problems.extend(e.strip() for e in errs)

        # F3) $ 吞噬结构性前缀（blockquote/list 标记被吃进公式）
        errs = find_swallowed_prefix_errors(line_list)
        if errs:
            all_problems.extend(e.strip() for e in errs)

        # F4) 裸数学 / 裸函数调用（希腊字母 α β ε、函数 F(X) D(A) 等在 $...$ 外）
        errs = find_bare_math_errors(line_list)
        if errs:
            all_problems.extend(e.strip() for e in errs)

        # F5) $ 奇偶配对（奇数 = 未闭合，破坏后续所有公式）
        dollar_count = _count_inline_dollars(line_list)
        if dollar_count % 2 != 0:
            all_problems.append(f"inline $ 数量为奇数（{dollar_count}）——存在未配对的 $，破坏后续所有公式")

        # F6) $$ 闭合（display math 未关闭）
        errs = check_display_math_closure(line_list)
        if errs:
            all_problems.extend(errs)

    # F7) 围栏形态（单行 $$ 块 / $$ 附着内容 / 缺空行或缺空 > 行）
    # —— 对 exercise 单元同样执行：这些是纯行形态检测，不依赖 $ 内外判断
    errs = _fence_issues(line_list)
    if errs:
        all_problems.extend(errs)

    # F7e) \tag 在数学模式外：对全单元散文视图查（_prose_text 按跨行状态跳过
    # $$ 块内行，单行逐条看会漏块上下文误报）
    joined = _prose_text(line_list)  # 散文视图——F7e 与 OCR 残留检测共用
    if re.search(r"\\tag\s*\{", joined):
        all_problems.append(
            "\\tag 出现在 $$ 块外（编号必须随公式写在 $$ 块内，不得散落正文）")

    # ── P 层 ──────────────────────────────────────────────────────────

    # P1) 证明过长（>700 字符无步骤枚举）
    errs = check_verbose_proofs(line_list)
    if errs:
        all_problems.extend(e.strip() for e in errs)

    # ── H/G 层 ────────────────────────────────────────────────────────

    # H1) 结构标签 + G1) example blockquote
    if utype == "item":
        has_bold = bool(TOP_LEVEL_HEADER_RE.search(body_clean)) or bool(re.search(r"\*\*", body_clean))
        if not has_bold:
            all_problems.append("编号项单元缺粗体标签（**name** 或 **定义/定理/…**）")
        if re.match(r"^例", (name or "")) or re.match(r"^Example", (name or ""), re.I):
            errs = check_example_blockquote_lines(line_list)
            if errs:
                all_problems.extend(e.strip() for e in errs)

    # ── 补充：OCR 残留模式 ────────────────────────────────────────────
    # 只对数学模式外的散文段匹配（joined 已由 _prose_text 剥除 $...$ / $$ 块），
    # 否则 `\boldsymbol{\Gamma} f` 这类合法显示公式被误报。
    for pat, msg in _OCR_FORMULA_PATTERNS:
        if re.search(pat, joined):
            all_problems.append(msg)

    # ── 补充：内容审阅类残留（writing-rules「内容清理与保真」的机械落实）──
    # 11a) QED 结尾框「口/□」独立行（数学模式外逐行查，先剥 `>` 前缀再判围栏）
    in_display = False
    for ln in line_list:
        content = re.sub(r"^\s*>\s?", "", ln)
        s = content.strip()
        if s == "$$" or (s.startswith("$$") and not s.endswith("$$")):
            in_display = not in_display
            continue
        if s.startswith("$$") and s.endswith("$$") and len(s) > 4:
            continue
        if in_display:
            continue
        if _QED_BOX_LINE_RE.match(s):
            all_problems.append(
                "QED 结尾框「%s」残留（OCR 噪声，证明结尾须剔除）" % s)
            break

    # 11b) OCR 乱码重复片段（同一 ≥12 字符片段同行连续重复 = OCR 抽风复制）
    # 注意：必须在**原始行**（math 未剥除）上查。若先剥 $...$ 再查，合法并列句式
    # （如 "For n=2 … is a solution; note … / For n≥3 … is a solution; note …"）会坍缩成
    # 相同散文残桩被误报为重复。原始行里两段夹着不同数学，不会形成连续 12+ 字符重复，
    # 故改用 line_list（保留 math），既保留对真实 OCR 抽风复制的捕获，又避免误报。
    # 🔴 **数学感知强化（2026-09-09）**：PDE 文本里大量「合法数学重复」会被
    #   `(.{12,}?)\1+` 误伤，例如乘积空间 `\Omega\times\mathbb R\times\mathbb R^n`、
    #   不等式链 `w(x_0)\leq … \leq w(x_0)\leq …`、双侧估计
    #   `\varphi(x_0)…\leq \varphi(x)\leq \varphi(x_0)…`。这些重复单元都含 LaTeX
    #   命令（反斜杠）。故：**重复单元含 `\` 一律视为合法数学重复跳过**；仅对非数学
    #   的普通文本/乱码重复报警。本数据集全树 11b 命中仅 6 处，全部是此类合法数学，
    #   该强化后 6 处均放行，真实（无反斜杠的）OCR 乱码仍会被捕获。
    for pl in line_list:
        m_dup = re.search(r"(.{12,}?)\1+", pl)
        if not m_dup:
            continue
        unit = m_dup.group(1)
        # 重复单元含 LaTeX 命令（反斜杠）→ 数学符号的合法重复，跳过
        if "\\" in unit:
            continue
        # 重复单元含数学定界符（()|{}^_[]<>=）→ 合法公式片段（如
        # |P(0)|+|DP(0)|+|D^2P(0)|、Ω×ℝ×ℝⁿ、不等式链），非 OCR 抽风，跳过
        if any(c in unit for c in "()|{}^_[]<>"):
            continue
        all_problems.append(
            "疑似 OCR 乱码重复片段：「%s…」连续重复（须清理）"
            % unit[:20])
        break

    # 11c) 单元内私造标题行（标题应为独立 section 单元）
    if utype in ("item", "desc", "exercise"):
        for ln in line_list:
            if _HEADING_LINE_RE.match(ln):
                all_problems.append(
                    "单元内出现标题行（%r）——标题应为独立 section 单元，"
                    "不得并入条目（防自造层级）" % ln.strip()[:30])
                break

    # ── F/H 层：块引用 / 例 / 证明 / 列表结构（复用 format_verify，单元级左移）──
    # verify F 层原只在合并后的整章 md 才查这些 intra-unit 结构；现前移到单元门控，
    # 让「重修单元」时即暴露，而非漏到合并后才被 verify 抓（合并脚本不负责重排正文）。
    # 文档级专属（`---`/标题上下文）检查不在此列，孤立单元查会误报。
    errs = _run_format_verify_unit_checks(line_list)
    if errs:
        all_problems.extend(errs)

    # 12) 单元级公式序标对账（契约 tag 为唯一真值；Q 层是章级末步，单元门控
    #     必须提前拦「漏写编号公式」与「编造编号」）
    if expected_tags is not None:
        want = list(expected_tags)
        got = re.findall(r"\\tag\{([^}]*)\}", body_clean)
        missing = [t for t in want if t not in got]
        extra = [t for t in got if t not in want]
        if missing:
            all_problems.append(
                "缺编号公式 \\tag{%s}（契约要求该单元携带；漏写 = 书源编号公式"
                "缺失）" % "}{".join(missing[:6])
                + (" 等共 %d 个" % len(missing) if len(missing) > 6 else ""))
        if extra:
            all_problems.append(
                "编造编号 \\tag{%s}（契约中不存在；书无此编号严禁编造）"
                % "}{".join(extra[:6])
                + (" 等共 %d 个" % len(extra) if len(extra) > 6 else ""))

    return (len(all_problems) == 0, all_problems)
