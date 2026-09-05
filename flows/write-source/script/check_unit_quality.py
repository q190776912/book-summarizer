"""check_unit_quality.py — 单元级「写对」质量校验（write-source 步骤 5 门控的一部分）

全部复用 verify 流程已有检测脚本，按 verify F 层校验顺序执行，不重新造轮子：
  F 层（按 verify 顺序）：
    1. 裸 Unicode 箭头：`katex_heuristics.find_raw_arrow_errors`
    2. 裸 LaTeX 命令：`katex_heuristics.find_naked_command_errors`
    3. `$` 吞噬前缀：`katex_heuristics.find_swallowed_prefix_errors`
    4. 裸数学/裸函数调用：`katex_heuristics.find_bare_math_errors`
    5. `$` 奇偶配对：内联计算
    6. `$$` 闭合：`check_katex.check_display_math_closure`
  P 层：
    7. 证明过长：`verbose_gates.check_verbose_proofs`
  H/G 层：
    8. 结构标签：`struct_labels.TOP_LEVEL_HEADER_RE`
    9. example blockquote：`format_verify.check_example_blockquote_lines`
  补充：
    10. OCR 残留模式（verify 不覆盖的 OCR 特有模式）

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


# ── 主入口 ────────────────────────────────────────────────────────────────
def check_body(utype, name, body):
    """对单个单元正文做「写对」质量校验。返回 (ok, problems)。

    按 verify F 层校验顺序执行全部检测，报告所有错误（不只第一个）。
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
    # 只对数学模式外的散文段匹配（_prose_text 剥除 $...$ / $$ 块），
    # 否则 `\boldsymbol{\Gamma} f` 这类合法显示公式被误报。
    joined = _prose_text(line_list)
    for pat, msg in _OCR_FORMULA_PATTERNS:
        if re.search(pat, joined):
            all_problems.append(msg)

    return (len(all_problems) == 0, all_problems)
