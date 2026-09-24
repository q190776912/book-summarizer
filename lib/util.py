"""lib/util.py — small helpers shared across multiple flow packages.

These have no per-flow state and were duplicated in >1 package; they live here
rather than inside any single flow's ``script/`` tree.
"""

import re as _re

# 序标分隔符归一：同一编号在 OCR/排版里可写作 1-1 / 1–1 / 1·1 / 1．1，
# 比较（契约键 ↔ 单元/md 标签）时一律折成点分，否则同号两形会被当成两个键。
_SECNUM_SEP_RE = _re.compile(r"[.\-–·．]+")
# 三级序标（节.条目类.序号）：契约条目键与标签式习题头（**Exercise 4.3.2**）共用单位
_ORD3_RE = _re.compile(r"\d{1,2}\.\d{1,2}\.\d{1,3}")


def norm_secnum(s):
    """序标/节号归一为点分串并去空白（None → ``''``）。"""
    return _SECNUM_SEP_RE.sub(".", str(s if s is not None else "").strip())


def sec_ordinals(s):
    """取出字符串里全部三级序标（先按 :func:`norm_secnum` 归一分隔符）。"""
    return _ORD3_RE.findall(norm_secnum(s))


def chapter_of_page(page, chaps):
    """Return the chapter id whose [start, end] page range contains ``page``.

    ``chaps`` is an iterable of dicts with ``start``/``end`` plus a chapter-id
    under any of the keys used across the pipeline: ``ch`` (chapter_map.json
    canonical), ``num``, or ``chapter`` (legacy).  Returns ``None`` when no
    range matches.
    """
    for c in chaps:
        if c["start"] <= page <= c["end"]:
            return c.get("ch", c.get("num", c.get("chapter")))
    return None


def blk_text(block):
    """Normalise one ``page_*.json`` text-block entry to a plain string.

    MM-repaired pages occasionally store the repaired line as a nested
    object (``{"text": {"text": ...}}``); consumers only ever want the
    final string, so unwrap one level and coerce anything else to "".
    """
    if not isinstance(block, dict):
        return str(block)
    t = block.get("text", "")
    if isinstance(t, dict):
        t = t.get("text", "")
    return t if isinstance(t, str) else ""
