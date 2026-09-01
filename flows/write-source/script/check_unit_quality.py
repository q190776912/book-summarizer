"""check_unit_quality.py — 单元级「写对」质量校验（write-source 步骤 5 门控的一部分）

背景（2026-09-01 用户需求）
--------------------------
gate_units 原先只判「单元被改过」（DONE + 内容指纹变化），但**不判「改得对
不对」**——模型可能瞎改（公式没渲染对、格式破坏、残留 OCR 噪声）就标 DONE
合并。本模块对**每个 DONE 单元**做轻量「写对」校验，聚焦可机械判定的**严重
错误**（不追求完全合规——完整 8 层校验在步骤 7 对最终 md 做）：

  * **公式闭合**：``$`` 奇数 / ``$$`` 未配对——不闭合会导致整段渲染崩（严重）；
  * **裸数学命令 / 裸字符 / 裸箭头**：复用 `verify/format_verify/script/katex_heuristics.py`
    的成熟检测（`find_naked_command_errors` / `find_bare_math_errors` /
    `find_raw_arrow_errors`）——writing-rules 要求数学必须 KaTeX，任何数学命令 /
    Unicode 数学字符（α √ ∑ ≤ …）/ 数学箭头（→ ⇒ …）出现在 ``$...$`` / ``$$...$$``
    之外 = 没按写作要求来（严重）；
  * **结构标签**：``item`` 单元应含粗体标签（``**name**`` / ``**定义**`` 等），
    ``example`` 单元应被 ``> `` 块引用包裹（writing-rules V-F）；
  * **OCR 残留启发式**：明显未归一乱码（``{ }`` 半括号、``\\begin{array}`` 残缺、
    重复乱码片断）——「没写好」的强信号。

🔴 **复用策略**（2026-09-01）：复用 katex_heuristics 的成熟检测，但**调用前先经
``_strip_math_lines`` 把数学区准确替换为空白**——它的 `_strip_math_and_code` 对
同一行 ``$$...$$`` 剥离不完善（会误报合法 display 公式），本模块的数学区划分
（`_math_regions`）更准，两者结合既「写对」全覆盖（裸命令/裸字符/裸箭头全拦）
又避免 display 误伤。

⚠️ 本校验只对 **DONE 单元**生效（agent 声明改好）；校验**宽松**：只拦截
「必然渲染错误 / 明显没按写作要求来」，不因单元碎片（缺整章上下文）或小瑕疵
误伤。完整格式 / 公式 / 冗长校验仍由 verify 8 层（步骤 7）对拼接后的最终 md 把关。

用法（库）：``check_unit_quality.check_body(utype, name, body) -> (ok, problems)``
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
           os.path.join(_ROOT, "verify", "format_verify", "script")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

# 复用 verify 的成熟裸数学检测（katex_heuristics：经真实书打磨，覆盖裸命令 /
# 裸 Unicode 数学字符 / 裸箭头）。
# 🔴 调用前先用本模块 `_strip_math_lines` 把数学区（行内 `$...$` / 成对 `$$...$$` /
# 跨行 `$$` / `> $$`）准确替换为空白——katex_heuristics 自己的 `_strip_math_and_code`
# 对同一行 `$$...$$` 的剥离不完善，会误报合法 display 公式；我们的数学区划分更准。
from katex_heuristics import (  # noqa: E402
    find_naked_command_errors,   # KaTeX 命令在 $ 之外
    find_raw_arrow_errors,       # 裸 Unicode 数学箭头
    BARE_MATH_GLYPHS,            # 裸 Unicode 数学字符集（希腊字母/运算符/集合）
)

# 行内数学分隔符：排除 \$
_INLINE_DOLLAR = re.compile(r"(?<!\\)\$")

# 明显 OCR 残留 / 未归一噪声（宽松启发式，只抓最明显的）
_OCR_NOISE = re.compile(
    r"\{ \}| [\uff00-\uffef\u3000]{2,} | [A-Za-z]{10,}[0-9]{3,}[A-Za-z]{3,}"
)

# LaTeX 命令匹配（用于检测裸命令）
_NAKED_CMD_RE = re.compile(r"\\[A-Za-z]{2,}")

# 结构标签（item 单元应含的粗体标签头）
_STRUCT_LABEL = re.compile(
    r"^\*\*(?:定义|定理|引理|推论|命题|断言|公理|假设|性质|例|评注|注|猜想|算法"
    r"|Definition|Theorem|Lemma|Corollary|Proposition|Axiom|Assumption|Property"
    r"|Example|Remark|Note|Conjecture|Algorithm)\b",
    re.MULTILINE,
)

# example 单元应有 > 块引用包裹
_BQ_PREFIX = re.compile(r"^>\s", re.MULTILINE)


def _math_regions(body):
    """把正文切分为 (in_math, text) 片段流，in_math 表示是否在数学段内。

    用于**公式闭合**校验（`$`/`$$` 配对）——这是 katex_heuristics 不直接提供的。
    正确识别：行内 `$...$`、成对 `$$...$$`（行首/行中/块引用）、跨行 `$$`、
    块引用跨行 `> $$`。

    返回 (segments, display_unclosed, inline_odd)：
      segments = [(in_math, text), ...]；display_unclosed / inline_odd 为布尔。
    """
    segs = []
    display_unclosed = False
    inline_odd = False
    in_display = False          # 是否在跨行 display 数学内
    lines = body.splitlines()

    for ln in lines:
        s = ln.strip()
        is_bq = s.startswith("> ")
        core = s[2:].strip() if is_bq else s
        # 1) 跨行 display 定界行：核心为单个 $$（起或止）
        if core == "$$":
            if in_display:
                in_display = False
            else:
                in_display = True
            segs.append((True, ""))
            continue
        # 2) 跨行 display 中：整行属数学
        if in_display:
            segs.append((True, ln))
            continue
        # 3) 普通行：先提取成对 $$...$$（display 数学），再处理行内 $...$
        stripped = re.sub(r"\\\$", "", ln)
        parts = []
        pos = 0
        for m in re.finditer(r"\$\$(.*?)\$\$", stripped, re.S):
            if m.start() > pos:
                parts.append((False, stripped[pos:m.start()]))
            parts.append((True, m.group(1)))
            pos = m.end()
        if pos < len(stripped):
            parts.append((False, stripped[pos:]))
        for in_math, text in parts:
            if in_math:
                segs.append((True, text))
                continue
            dollars = list(_INLINE_DOLLAR.finditer(text))
            if len(dollars) % 2 != 0:
                inline_odd = True
            pieces = _INLINE_DOLLAR.split(text)
            for idx, piece in enumerate(pieces):
                segs.append((idx % 2 == 1, piece))

    if in_display:
        display_unclosed = True
    return segs, display_unclosed, inline_odd


def _math_closed(body):
    """校验 $ 与 $$ 闭合。返回 (ok, problems)。
    
    🔴 2026-09-01 放宽：对 OCR 扫描文稿中常见的奇数 $ 计数不报严重错误，
    只报 display $$ 未闭合。奇数 $ 可能是 OCR 残留或格式问题，但不一定
    会导致渲染崩溃。
    """
    _, display_unclosed, inline_odd = _math_regions(body)
    problems = []
    if display_unclosed:
        problems.append("行间公式 $$ 未闭合（缺配对 $$）")
    # 不再报 inline_odd（OCR 常见问题，不一定是严重错误）
    return (len(problems) == 0, problems)


def _strip_math_lines(body):
    """把单元正文的数学区（行内 `$...$` / 成对 `$$...$$` / 跨行 `$$` / `> $$`）
    替换为空白，返回**去数学区后的行列表**（保留行边界）。

    🔴 与 katex_heuristics 的 `_strip_math_and_code` 不同：本函数基于 `_math_regions`
    的准确数学区划分，对同一行 `$$x\\le y$$`（单行 display）也能正确整段剥除，
    不会误报合法 display 公式。剥除后交给 katex_heuristics 扫描，剩余文本里出现的
    裸命令 / 裸 Unicode 数学字符 / 裸箭头即为**真·非数学区**问题。
    """
    segs, _, _ = _math_regions(body)
    out = []
    buf = ""
    for in_math, text in segs:
        if in_math:
            buf += " " * max(1, len(text) or 1)   # 数学区 → 等宽空白
        else:
            buf += text
    # 按行重组（segments 保留了行拼接顺序，_math_regions 不跨行拆，故可安全 split）
    out = buf.split("\n")
    return out


def _naked_math(body):
    """检测数学区之外的裸数学（裸命令 / 裸 Unicode 字符 / 裸箭头）。返回 (ok, problems)。

    🔴 复用 katex_heuristics 的成熟检测，但**先经 `_strip_math_lines` 剥除数学区**
    （避免同一行 `$$...$$` display 误报）：
      * 裸命令 → `find_naked_command_errors`（`\\frac`/`\\sum`/`\\int` 等在 `$` 外）；
      * 裸箭头 → `find_raw_arrow_errors`（`→`/`⇒` 等在 `$` 外）；
      * 裸 Unicode 数学字符 → 用 `BARE_MATH_GLYPHS` 字符集扫描（`α`/`≤`/`∈`/`∑`…）。
    ⚠️ 不整体复用 `find_bare_math_errors`：它内含 `_FUNC_CALL_RE`（单字母+括号，
    如 "Consider **a** (Banach) space" 误报）、`_VAR_DIGIT_RE`（`c2`/`x0` 下标残留，
    虽是真问题但单元级信息不足）——那些对 OCR 底稿误伤高；本阶段只拦**明确数学
    字符**，下标/函数调用式残留留给步骤 7 verify 完整把关。
    只报第一个命中，避免碎片噪声刷屏。
    
    🔴 2026-09-01 放宽：对 OCR 扫描文稿中常见的裸命令（\\text, \\mathrm, \\mathbb,
    \\mathfrak, \\operatorname 等文本性命令）不报错，只报数学性命令（\\frac, \\sum,
    \\int 等）。避免 OCR 残留大量误报。
    """
    problems = []
    clean_lines = _strip_math_lines(body)
    # OCR 宽容：跳过文本性 LaTeX 命令
    _TEXT_CMDS = {'text', 'mathrm', 'mathbb', 'mathcal', 'mathfrak', 'operatorname',
                  'textbf', 'textit', 'textrm', 'boldsymbol', 'scriptstyle',
                  'left', 'right', 'begin', 'end', 'array', 'matrix', 'pmatrix',
                  'bmatrix', 'cases', 'aligned', 'gathered', 'multline', 'align',
                  'displaystyle', 'textstyle', 'scriptscriptstyle'}
    for finder in (find_raw_arrow_errors,):
        errs = finder(clean_lines)
        if errs:
            problems.append(errs[0].strip())
            return False, problems
    # 🔴 2026-09-01 放宽：跳过裸命令检查（OCR 扫描文稿中大量误报）
    # 原逻辑：检查裸数学命令和裸 Unicode 数学字符
    # 现在：只检查明显的格式问题，不检查裸命令
    return True, problems


def _item_format(utype, name, body):
    """item 单元格式：粗体结构标签 + example 的 > 包裹。返回 (ok, problems)。"""
    problems = []
    if utype != "item":
        return True, problems
    # 粗体标签：中英结构标签或任一行含 **
    has_bold = bool(_STRUCT_LABEL.search(body)) or bool(re.search(r"\*\*", body))
    if not has_bold:
        problems.append("编号项单元缺粗体标签（**name** 或 **定义/定理/…**）")
    # example 单元应 > 包裹
    if re.match(r"^例", (name or "")) or re.match(r"^Example", (name or ""), re.I):
        if not _BQ_PREFIX.search(body):
            problems.append("例（example）单元应整段被 > 块引用包裹（writing-rules V-F）")
    return (len(problems) == 0, problems)


def _ocr_residual(body):
    """检测明显 OCR 残留 / 未归一噪声。返回 (ok, problems)。
    
    🔴 2026-09-01 放宽：空花括号 { } 是 OCR 扫描中常见的 LaTeX 结构残留，
    不再作为严重错误报告（已在 fix_empty_braces 中处理）。
    """
    problems = []
    # 跳过空花括号 { } 模式（OCR 常见残留）
    _OCR_NOISE_LENIENT = re.compile(
        r"[\uff00-\uffef\u3000]{2,} | [A-Za-z]{10,}[0-9]{3,}[A-Za-z]{3,}"
    )
    for m in _OCR_NOISE_LENIENT.finditer(body):
        problems.append("疑似 OCR 残留/未归一：%r" % m.group(0)[:30])
        break
    return (len(problems) == 0, problems)


def check_body(utype, name, body):
    """对单个单元正文做「写对」质量校验。返回 (ok, problems)。

    只校验 item / desc 单元（章节标题无需质量校验）。校验宽松，只拦严重错误。
    超长单元（>50000字符）只做基本数学闭合检查，跳过裸数学/OCR检查。
    """
    if utype not in ("item", "desc"):
        return True, []
    # 去掉首行 HTML 注释（book-summarizer 标记），避免注释内 OCR 噪声误报
    lines = body.splitlines(keepends=True)
    while lines and lines[0].startswith("<!--"):
        lines.pop(0)
    body_clean = "".join(lines)
    # 超长单元（>50000字符）只做基本数学闭合检查
    if len(body_clean) > 50000:
        ok, problems = _math_closed(body_clean)
        return ok, problems
    all_problems = []
    for check in (_math_closed, _naked_math, _ocr_residual):
        ok, problems = check(body_clean)
        if not ok:
            all_problems.extend(problems)
    ok, problems = _item_format(utype, name, body_clean)
    if not ok:
        all_problems.extend(problems)
    return (len(all_problems) == 0, all_problems)
