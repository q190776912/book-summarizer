"""fix_math_blockquote_leak.py — M-LAYER (code 'M', fix_order 10) auto-fix.

判据 `check_displaymath_gt` 住在 `format_verify.py`（同目录），有**两条**子判据；本修复必须
两条都能修，否则 `verify --fix` 会出现「修了 N 行、判据照旧红」的假闭环：
  1. 顶层 `$$…$$` 里泄进 `>` —— 剥掉 `>` 前缀；
  2. 引用块 `> $$ … > $$` 的**围栏内**空 `>` 行 —— 删掉那一行。
     「哪些能删」不在这里另写一份，走 `format_verify.bq_deletable_inner_blanks`（SSOT）：
     它同时给出**拒删清单**（空行两侧都有内容 ⇒ 删了会并块），闸与
     `tools/fix_bq_math_blank.py` 因此共用同一个安全边界。

Fix-dict key: {m}.
"""
import io
import os
import sys
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[2])
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

from verify.script.base import LayerFixResult, register_fixer
from format_verify import bq_deletable_inner_blanks   # 删除决策的 SSOT，不在本文件另写一份


def _sep_of(raw):
    """该文件**自身**的换行风格（`\r\n` 占多数则 CRLF，否则 LF）。"""
    return "\r\n" if (b"\r\n" in raw and raw.count(b"\r\n") * 2 >= raw.count(b"\n")) else "\n"


def fix_displaymath_gt(md_file):
    """M-LAYER auto-fix，两条子判据都修。→ 改动的行数。

    1. 顶层 `$$…$$` 里泄进的 `>` 前缀 —— 剥掉；
    2. 引用块 `> $$ … > $$` 的围栏内空 `>` 行 —— 删掉（安全边界见
       `format_verify.bq_deletable_inner_blanks`；它拒删「空行两侧都有内容」那种，
       闸照它执行，不在本文件另判一遍）。

    写回按文件**自身**换行风格（第二子判据是整文件重写：删一行就会顺带把 LF 件翻成 CRLF，
    与 `tools/fix_bq_math_blank.py` 的边界 ③ 同一条要求）。
    """
    try:
        with open(md_file, "rb") as f:
            raw = f.read()
        sep = _sep_of(raw)
        lines = raw.decode("utf-8").replace(sep, "\n").split("\n")
    except Exception:
        return 0
    changes = 0
    n = len(lines)
    i = 0
    while i < n:
        s = lines[i].strip()
        if s == '$$':
            j = i + 1
            while j < n and lines[j].strip() != '$$':
                j += 1
            if j < n:
                for k in range(i + 1, j):
                    ln = lines[k]
                    stripped = ln.lstrip()
                    if stripped.startswith('>'):
                        new_ln = ln.replace('>', '', 1)
                        if new_ln.startswith(' '):
                            new_ln = new_ln[1:]
                        if new_ln != ln:
                            lines[k] = new_ln
                            changes += 1
                i = j
        i += 1
    drop, _refuses, _blocks = bq_deletable_inner_blanks(lines)
    if drop:
        lines = [ln for idx, ln in enumerate(lines) if (idx + 1) not in drop]
        changes += len(drop)
    if changes > 0:
        with io.open(md_file, "w", encoding="utf-8", newline=sep) as f:
            f.write("\n".join(lines))
    return changes


def apply_fix(ctx) -> LayerFixResult:
    """Run the M auto-fix and return the byte-compatible fix dict {m}."""
    return LayerFixResult(fix_dict={'m': fix_displaymath_gt(ctx.md_file)})


register_fixer('M', 10, apply_fix)
