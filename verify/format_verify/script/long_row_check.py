# -*- coding: utf-8 -*-
"""long_row_check.py — 检测「显示公式过长 → KaTeX \\tag 被挤离公式」风险。

已并入 F 层公式校验（`format_verify.FLayer.run`，见 format_verify.md）：每章
`verify_chapter.py` 都会自动扫描全部 `$$` / `> $$` 显示块，把「渲染行过宽」或
「整块过高」的公式作为 **WARN（非阻断）** 列出——它不属于 KaTeX 渲染错误，不使章节
FAIL，只提示排版风险供 writer 处理。

🔴 度量口径（2026-09-06 修正）
------------------------------
旧实现**逐源码行**取 max(vis_len)，对「一个渲染行被折成多行书写」的公式系统性漏报：
18.11 的一个 aligned 行在源码里占 6 行，最长源行仅 39（阈值 100），整行渲染宽度
实为 71 —— 肉眼明显过宽却判为合格。只有恰好写成单行的公式才会被抓到。

现统一复用 `tools/scan_long_formulas.py` 的度量（单一事实来源，避免三处实现分叉）：
* **按渲染行测量**：先按顶层 `\\\\` 切成渲染行（跳过 `bmatrix`/`cases` 等嵌套环境
  内部的分隔符），把被折行的源码拼接回一整行，再逐行量宽。
* 堆叠结构（列向量、分式）按竖向取 max 而非横向累加；`\\sum`/`\\int` 等符号按 1 字形
  计宽（旧实现整条删掉，计 0）。
* 阈值 `LONG_ROW_MAX_VIS` 默认 60（与 `tools/scan_long_formulas.py` 的 `DEFAULT_W`
  一致，由 18.7/18.11/18.20 的实际判决标定）。
* 新增**块高**维度 `LONG_BLOCK_MAX_H`（默认 8 个渲染行）：过高会把 `\\tag` 垂直推远。

修法（写作规则 + 工具）：见 `docs/writing-rules.md`「超长显示公式折行」；
批量检测 `tools/scan_long_formulas.py`；折行规划 `tools/wrap_long_formulas.py`
（dry-run 先行）。
"""
import os
import re
import sys
from pathlib import Path

# 定位 skill 根（与 verify 其他脚本一致的 SKILL.md 探测法），复用 tools 下的度量实现
for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[3])
_TOOLS = os.path.join(_ROOT, "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)
from scan_long_formulas import row_metrics, rendered_rows, DEFAULT_W, DEFAULT_H

LONG_ROW_MAX_VIS = DEFAULT_W      # 渲染行可视宽度阈值（默认 60）
LONG_BLOCK_MAX_H = DEFAULT_H      # 块高（渲染行数）阈值（默认 8）

DELIM = re.compile(r'^\s*(?:>\s*)?\$\$\s*$')
TAG_RE = re.compile(r'\\tag\{([^}]*)\}')


def vis_len(latex):
    """渲染宽度（🔴 与 `tools/scan_long_formulas.py` 同口径）。

    旧实现为「剥掉 \\tag / 命令名 / 花括号后数字符」：逐源码行测量、环境名当可见
    字符、矩阵与分式按横向累加、`\\sum`/`\\int` 计 0 —— 会系统性漏报被折行书写的
    长公式。保留此名仅为兼容既有调用与测试，实际判定请用 `row_metrics`。
    """
    return row_metrics(latex)[0]


def check_long_formula_rows(md_lines, max_vis=None, max_height=None):
    """扫描 md 行；返回过长/过高显示公式 finding 列表（每项含行号/tag/量值）。

    只报带 `\\tag` 的显示块（编号公式才有与 tag 挤开的问题）；无 tag 的宽公式只
    产生横向滚动，不与 tag 重叠，不在此列。
    """
    max_vis = LONG_ROW_MAX_VIS if max_vis is None else max_vis
    max_height = LONG_BLOCK_MAX_H if max_height is None else max_height
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
            tagm = TAG_RE.search(body)
            if tagm:
                tag = tagm.group(1)
                # 🔴 按【渲染行】测量，而非逐源码行（旧行为会漏报折行书写的长公式）
                rows = rendered_rows(body)
                width = 0.0
                height = 0
                for r in rows:
                    rw, rh = row_metrics(r)
                    width = max(width, rw)
                    height += rh
                head = 'L%d:' % (i + 2)  # 块内首行（1-based）
                if rows and width > max_vis:
                    findings.append(
                        '%s display row too wide (~%.0f visible chars > %d), '
                        '\\tag{%s} may be pushed away from the formula — wrap per '
                        'writing-rules「超长显示公式折行」or allow container scroll'
                        % (head, width, max_vis, tag))
                elif rows and height > max_height:
                    findings.append(
                        '%s display block too tall (%d rendered rows > %d), '
                        '\\tag{%s} sits far from the formula — split the derivation '
                        'or shorten per writing-rules「超长显示公式折行」'
                        % (head, height, max_height, tag))
            i = j + 1
        else:
            i += 1
    return findings
