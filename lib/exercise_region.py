"""章末**集中习题区**（verify_config `exercise_region_headings`）判据的单一真源。

writing-rules V-I 规定「有专门小标题的集中习题块（含**整节都是习题**的节）一律省略」，
所以产出侧（`build_structure` 3a-2 条目切断 + 4a-exer 节打标 + `scan_skeleton` STICKY
闩锁）不写它，**校验侧也不许索要它**。此前两侧各写一份判据，闸门的 D 层 / B 层不知道
该声明，于是把印面 `1.7 Problems` 里的 `Theorem 1.7-1` 报成缺节 / 缺项 / 「总结未含任何
定理」（Lehmann《Elements of Large-Sample Theory》ch1 §1.7、ch6 §6.6 实测 = 闸逼写手
去写书里规定要省略的内容）。本模块把「哪些节号属于习题区」收成一份判据，供
`verify/section_continuity`（D 层）与 `verify/item_numbering_integrity`（B 层）共用。

判据与产出侧同源：标题匹配器 = `scan_skeleton._exercise_headings_re`（整行锚定），
页眉带复本不算块头（`scan_skeleton.is_running_head`）。🔴 **opt-in**：未在
verify_config 声明 `exercise_region_headings` 的书，`headings_re` 返回 None、
`section_numbers` 返回空集 → 所有调用方逐字节零回归。
"""

import os
import re

# 块头行首的点分段号（`1.7 Problems` / `6.6 Problems448` / `4.5 Problems269`）。
_LEAD_RE = re.compile(r'^(\d{1,3}(?:[.\-–·]\d{1,3}){0,3})')
_SEP = re.compile(r'[.\-–·]')


def headings_re(cfg):
    """本书的习题块标题匹配器；未声明（或 scan_skeleton 不可用）→ None。"""
    heads = getattr(cfg, "exercise_region_headings", None) or None
    if not heads:
        return None
    try:
        import scan_skeleton as _sk
    except Exception:
        return None
    try:
        return _sk._exercise_headings_re(heads)
    except Exception:
        return None


def _heading_line_number(line, ch):
    """块头行的**节号**（相对章号）：`"1.7 Problems"`, ch=1 → 7；不匹配 → None。

    只认「首段 == 章号」的数值节号；字母序标（`A.7 Problems`）与无号头不进数值域——
    字母/无号附录章由契约 `consolidated` 侧（`_filter_d_layer_by_contract`）豁免。
    """
    m = _LEAD_RE.match(line.strip())
    if not m:
        return None
    parts = [int(x) for x in _SEP.split(m.group(1)) if x.isdigit()]
    if len(parts) >= 2 and parts[0] == int(ch):
        return parts[1]
    return None


def section_numbers(ext, ch, start, end, cfg, page_dir=None):
    """本章页窗内印面习题块节头的节号集合（如 ch1 → ``{7}``）。未声明 → ``set()``。"""
    rx = headings_re(cfg)
    if rx is None:
        return set()
    try:
        import page_json
        import scan_skeleton as _sk
        from lib.page_dir import resolve_page_dir
    except Exception:
        return set()
    _dir = page_dir or resolve_page_dir(ext, ch)
    out = set()
    for p in range(int(start), int(end) + 1):
        fp = os.path.join(_dir, "page_%03d.json" % p)
        if not os.path.exists(fp):
            continue
        try:
            data = page_json.PageJson.load(fp).data
        except Exception:
            continue
        blocks = data.get("text") or []
        left, span = _sk.page_x_extent(blocks)
        top = _sk.page_top_y(blocks)
        for b in blocks:
            if not isinstance(b, dict):
                continue
            x, y = _sk.block_xy(b.get("poly") or [])
            if _sk.is_running_head(x, y, left, span, top):
                continue
            for line in (b.get("text") or "").split("\n"):
                s = line.strip().rstrip("$").strip()
                if s and rx.match(s):
                    sec = _heading_line_number(s, ch)
                    if sec is not None:
                        out.add(sec)
    return out


def is_exercise_section(ch, sec, cfg, ext, start, end):
    """``ch.sec`` 是否印面章末习题节（B 层按节覆盖判据用）。"""
    return sec in section_numbers(ext, ch, start, end, cfg)
