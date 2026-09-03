"""check_unit_quality.py — 单元级「写对」质量校验（write-source 步骤 5 门控的一部分）

全部复用 verify 流程已有检测脚本，不重新造轮子：
  * **公式闭合**：`check_katex.check_display_math_closure`（同 verify F 层）
  * **裸数学 / 裸箭头**：`katex_heuristics.find_bare_math_errors` /
    `find_raw_arrow_errors`（同 verify F 层）
  * **证明过长**：`verbose_gates.check_verbose_proofs`（同 verify P 层）
  * **结构标签**：`struct_labels.TOP_LEVEL_HEADER_RE`（同 verify H 层）
  * **example blockquote**：`format_verify.check_example_blockquote_lines`（同 verify G 层）
  * **OCR 残留**：verify 不覆盖的 OCR 公式模式由本模块薄封装补充。

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
from check_katex import check_display_math_closure   # F 层：$$ 闭合（同 verify）
from katex_heuristics import (                        # F 层：裸数学（同 verify）
    find_bare_math_errors,
    find_raw_arrow_errors,
)
from verbose_gates import check_verbose_proofs        # P 层：证明过长（同 verify）
from struct_labels import TOP_LEVEL_HEADER_RE         # H 层：结构标签（同 verify）
from format_verify import check_example_blockquote_lines  # G 层：example blockquote（同 verify）

# ── 本模块专有：OCR 公式残留（verify 不覆盖）──────────────────────────────
_OCR_FORMULA_PATTERNS = [
    (r"\\ensuremath\s*\{", "OCR 残留 \\ensuremath（应改为直接 KaTeX）"),
    (r"\\pmb\s*\{", "OCR 残留 \\pmb（应改为 \\mathbf 或 \\boldsymbol）"),
    (r"\\boldsymbol\s*\{[^}]*\}\s*[A-Za-z]", "OCR 残留 \\boldsymbol 在数学模式外"),
    (r"[\u00e0-\u00ff]{3,}", "garbled Unicode 片段（OCR 编码错误）"),
    (r"\\sun\b", "OCR 残留 \\sun（应改为具体数学符号）"),
    (r"\\b\s*\{", "OCR 残留 \\b 命令"),
    (r"\\E\s*\{", "OCR 残留 \\E（应改为 \\operatorname{E} 或具体符号）"),
    (r"\ufffd{2,}", "replacement character 连续（编码损坏）"),
]


def _prose_text(line_list):
    """剥掉数学模式，只留散文段（OCR 残留模式只对数学模式外文本有意义）。

    🔴 2026-09-03 修复：此前把模式应用在全文（含 `$$` 块内部），导致
    ``\\boldsymbol{\\Gamma} f`` 这类**合法的显示公式**（算子作用于 f）被
    "boldsymbol 在数学模式外" 误报。现按 `$` 配对剥除：
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


# ── 主入口 ────────────────────────────────────────────────────────────────
def check_body(utype, name, body):
    """对单个单元正文做「写对」质量校验。返回 (ok, problems)。

    全部检测引用 verify 已有函数，无重复实现。
    """
    if utype not in ("item", "desc"):
        return True, []
    lines = body.splitlines(keepends=True)
    while lines and lines[0].startswith("<!--"):
        lines.pop(0)
    body_clean = "".join(lines)
    if len(body_clean) > 50000:
        errs = check_display_math_closure(body_clean.splitlines())
        return (len(errs) == 0, errs)

    all_problems = []
    line_list = body_clean.splitlines()

    # 1) $$ 闭合（复用 check_katex.check_display_math_closure）
    errs = check_display_math_closure(line_list)
    if errs:
        all_problems.extend(errs)

    # 2) 裸数学 / 裸箭头（复用 katex_heuristics）
    errs = find_bare_math_errors(line_list)
    if errs:
        all_problems.append(errs[0].strip())
    else:
        errs = find_raw_arrow_errors(line_list)
        if errs:
            all_problems.append(errs[0].strip())
        else:
            # 3) OCR 公式残留补充（verify 不覆盖的 OCR 特有模式）
            # 🔴 只对数学模式外的散文段匹配（_prose_text 剥除 $...$ / $$ 块），
            #    否则 `\boldsymbol{\Gamma} f` 这类合法显示公式被误报（2026-09-03）。
            joined = _prose_text(line_list)
            for pat, msg in _OCR_FORMULA_PATTERNS:
                if re.search(pat, joined):
                    all_problems.append(msg)
                    break

    # 4) 证明过长（复用 verbose_gates.check_verbose_proofs）
    errs = check_verbose_proofs(line_list)
    if errs:
        all_problems.append(errs[0].strip())

    # 5) 结构标签 + example blockquote（复用 struct_labels + format_verify）
    if utype == "item":
        has_bold = bool(TOP_LEVEL_HEADER_RE.search(body_clean)) or bool(re.search(r"\*\*", body_clean))
        if not has_bold:
            all_problems.append("编号项单元缺粗体标签（**name** 或 **定义/定理/…**）")
        if re.match(r"^例", (name or "")) or re.match(r"^Example", (name or ""), re.I):
            errs = check_example_blockquote_lines(line_list)
            if errs:
                all_problems.append(errs[0].strip())

    return (len(all_problems) == 0, all_problems)
