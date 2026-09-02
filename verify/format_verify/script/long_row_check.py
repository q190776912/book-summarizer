# -*- coding: utf-8 -*-
"""long_row_check.py — 检测「显示公式行过长 → KaTeX \\tag 与公式重叠」风险。

已并入 F 层公式校验（`format_verify.FLayer.run`，见 format_verify.md）：每章
`verify_chapter.py` 都会自动扫描全部 `$$` / `> $$` 显示块，把「单行可视长度超过
阈值」的行作为 **WARN（非阻断）** 列出——它不属于 KaTeX 渲染错误，不使章节 FAIL，
只提示排版风险供 writer 处理。

- 阈值：`LONG_ROW_MAX_VIS`（可视字符数，渲染宽度 ≈ 0.5–0.6 em/字符）；默认 100。
- 修法（写作规则 + 工具）：见 `docs/writing-rules.md`「超长显示公式折行」；
  批量检测脚本 `tools/scan_long_formulas.py`；折行修复脚本
  `tools/wrap_long_formulas.py`（dry-run 先行）。
- 判断原则与折行一致：矩阵/array/cases 等不可折环境的整行与 `\\left..\\right`
  内部不算安全断点，此类只列 WARN，修法为「查看器横向滚动」兜底。
"""
import re

LONG_ROW_MAX_VIS = 100

DELIM = re.compile(r'^\s*(?:>\s*)?\$\$\s*$')
CMD = re.compile(r'\\(?:[a-zA-Z]+)')
TAG_RE = re.compile(r'\\tag\{([^}]*)\}')


def vis_len(latex):
    """可视字符数：剥掉 \\tag、\\command 名与花括号后的剩余字符数（近似渲染宽）。"""
    s = TAG_RE.sub('', latex)
    s = CMD.sub('', s)
    s = re.sub(r'[{}]', '', s)
    return len(s.replace('\\', ''))


def _block_line_marker(ln):
    """返回 '$$' 块内的物理行原文；用于把 finding 挂到该行号。"""
    return ln


def check_long_formula_rows(md_lines, max_vis=None):
    """扫描 md 行；返回超长显示行 finding 列表（每项含行号/tag/可视长度）。

    只报带 `\\tag` 的显示块内的行（编号公式才有与 tag 重叠的问题）；
    无 tag 的宽公式只产生横向滚动，不与 tag 重叠，不在此列。
    """
    max_vis = LONG_ROW_MAX_VIS if max_vis is None else max_vis
    findings = []
    n = len(md_lines)
    i = 0
    while i < n:
        if DELIM.match(md_lines[i]):
            j = i + 1
            buf = []
            while j < n and not DELIM.match(md_lines[j]):
                buf.append((j, md_lines[j]))
                j += 1
            if j >= n:
                break
            body = '\n'.join(x[1] for x in buf)
            if not TAG_RE.search(body):
                i = j + 1
                continue
            tagm = TAG_RE.search(body)
            tag = tagm.group(1) if tagm else ''
            for ln_no, raw in buf:
                t = TAG_RE.sub('', raw).rstrip()
                if not t.strip():
                    continue
                v = vis_len(t)
                if v > max_vis:
                    findings.append(
                        'L%d: display row too long (~%d visible chars > %d), '
                        '\\tag{%s} may overlap the formula — wrap per '
                        'writing-rules「超长显示公式折行」or allow container scroll'
                        % (ln_no + 1, v, max_vis, tag))
            i = j + 1
        else:
            i += 1
    return findings
