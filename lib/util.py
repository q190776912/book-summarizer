"""lib/util.py — small helpers shared across multiple flow packages.

These have no per-flow state and were duplicated in >1 package; they live here
rather than inside any single flow's ``script/`` tree.
"""


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
