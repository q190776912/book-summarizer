"""chapter_boundary.py — 章起始页「章标题之上」溢出的版面判定（structure 阶段公用）

背景（Etingof《Introduction to representation theory》实测 2026-09-27）
--------------------------------------------------------------------
章图把某一页整页划给后一章，但该页**页首**往往还印着**上一章的收尾**——章标题
出现在页面中上部而非页顶。按「整页归属」收集内容会把上一章的尾料挂到本章章首
描述节点（`D1`）上，于是：

  * 本章总结开头多出别章的条目（假内容）；
  * 上一章**整节消失**——实测丢 ``§2.10``（含 Theorem 2.26 / Remark 2.27 及其
    证明）与 Theorem 4.75（含证明），B/D 层各自只在**本章节号空间**里查连续性，
    两边都不报错 → 全绿却缺整节。

修法 = 按 y 切开边界页：标题**之上**的块归上一章（章尾带），标题**及其之下**归
本章（章首带）。本模块只提供**几何判定**（谁是标题、标题在哪个 y），不改动任何
数据结构；消费方：

  * ``attach_content._collect_blocks``：章首页裁掉头带、章末多收一页尾带；
  * ``build_structure.build_chapter``：对尾带页补跑一次骨架 / 条目扫描，把上一章
    缺的节与编号项接回去；
  * ``check_structure_completeness``：源侧真值同样按带归属，缺节 / 缺项才会被查出。

🔴 **fail-open**：判定不了（无章图 / 标题块匹配不到 / 单页无 poly）一律返回
``None``，消费方保持历史行为（整页归属），绝不因判不出而改坏别的书。
"""
import json
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
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
import lib.boot as _boot
_boot.setup()

from data.chapter_map.chapter_map import load_chapter_records  # noqa: E402
from page_json import PageJson  # noqa: E402

# 连字 / 全角标点归一：PDF 文字层与 OCR 通道对同一词的字节不同（"ﬁle" vs "file"），
# 不归一则标题匹配整批落空。
_LIG = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl",
        "ﬅ": "ft", "ﬆ": "st", "‒": "-", "–": "-", "—": "-", "‐": "-",
        "‑": "-", "‘": "'", "’": "'", "“": '"', "”": '"',
        "：": ":", "（": "(", "）": ")", "，": ",", "·": " ", "　": " "}

# 「标题在页顶」判据：OCR 通道坐标是像素（随 DPI 变），故阈值取**页高比例**而非
# 绝对值。标题落在页面顶部这一比例以内 ⇒ 该页几乎全是本章内容 ⇒ 无溢出，不做
# 任何裁剪（保持历史行为）。
_TOP_FRAC = 0.06


def norm_text(s):
    """标题比对用的归一形态：连字展开 + 小写 + 非字母数字压成单空格。"""
    s = str(s or "")
    for k, v in _LIG.items():
        s = s.replace(k, v)
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def _name_phrase(name, ch_key):
    """章名 → 用于匹配印刷标题行的归一短语（去掉行首序标）。"""
    n = str(name or "").strip()
    # 去掉开头的序标（"3 " / "Appendix A " / "附录 A "）
    n = re.sub(r"^(?:appendix|supplement|附录|补篇|章|第)?\s*[0-9IVXLCDMivxlcdm]*\s*"
               r"[.、．:：\-]?\s*", "", n, flags=re.I)
    return norm_text(n)


def _poly_ys(poly):
    """OCR `poly` 两种形态（扁平 [x0,y0,x1,y1,…] / 点对 [[x,y],…]）→ 全部 y。"""
    ys = []
    for i, v in enumerate(poly or []):
        try:
            if isinstance(v, (list, tuple)):
                if len(v) > 1:
                    ys.append(float(v[1]))
            elif i % 2 == 1:
                ys.append(float(v))
        except (TypeError, ValueError):
            pass
    return ys


def _blocks_of_page(page_dir, page):
    """page_*.json 文本块 → ([(y, 归一文本, 原文)], 页内容最大 bottom)。

    bottom 用作页高代理（OCR 坐标是像素，绝对阈值不可移植）。
    """
    fp = os.path.join(page_dir, "page_%03d.json" % int(page))
    if not os.path.exists(fp):
        return [], 0.0
    try:
        pg = PageJson.load(fp)
    except Exception:
        return [], 0.0
    out = []
    bottom = 0.0
    for b in pg.text_blocks:
        if not isinstance(b, dict):
            continue
        t = (b.get("text") or "").strip()
        if not t:
            continue
        poly = b.get("poly") or []
        ys = _poly_ys(poly)
        if not ys:
            continue
        out.append((min(ys), norm_text(t), t))
        bottom = max(bottom, max(ys))
    out.sort(key=lambda z: z[0])
    return out, bottom


def _is_title(norm_block, ch_key, phrase):
    """块文本是否「本章印刷标题」：以序标开头 + 含章名主体短语。"""
    if not phrase:
        return False
    k = norm_text(ch_key)
    # 序标必须出现在行首（"3 representations of finite groups…"）；字母附录同理。
    if k and not re.match(r"^%s(\b|[^a-z0-9])" % re.escape(k), norm_block):
        return False
    words = phrase.split()
    if not words:
        return False
    # 短语按**连续词序**出现即可（OCR 可能吞掉尾部副标题，故只用前若干词判定）。
    if len(words) <= 3:
        probe = " ".join(words)
    else:
        probe = " ".join(words[:3])
    return probe in norm_block


def title_y_on_page(page_dir, page, ch_key, ch_name):
    """本章印刷标题在该页的 y；判不出 / 标题在页顶（无溢出）返回 None。

    同页多次命中（运行页眉 + 真标题）取**最靠下**者——页眉恒在真标题之上，而
    章首页再印一次本章全名的概率极低。取到页顶带内（页高 6% 以下）即判
    「标题在页顶」⇒ 该页无上一章尾料 ⇒ None（不裁剪）。
    """
    blocks, bottom = _blocks_of_page(page_dir, page)
    phrase = _name_phrase(ch_name, ch_key)
    hits = [y for y, nb, _ in blocks if _is_title(nb, ch_key, phrase)]
    if not hits:
        return None
    y = max(hits)
    if bottom and y < _TOP_FRAC * bottom:
        return None
    return y


def _records(ext):
    """章图规范记录，按起始页升序；读不到返回 []。"""
    try:
        recs = list(load_chapter_records(ext))
    except SystemExit:
        return []
    except Exception:
        return []
    recs = [r for r in recs if r.get("start") and r.get("end")]
    recs.sort(key=lambda r: int(r["start"]))
    return recs


def chapter_bounds(ext, ch_key):
    """→ 本章记录 / 前章记录 / 后章记录（缺失侧为 None）。"""
    recs = _records(ext)
    k = str(ch_key)
    idx = None
    for i, r in enumerate(recs):
        if str(r.get("num_str")) == k:
            idx = i
            break
    if idx is None:
        return None, None, None
    prev_r = recs[idx - 1] if idx > 0 else None
    next_r = recs[idx + 1] if idx + 1 < len(recs) else None
    return recs[idx], prev_r, next_r


def head_floor(ext, page_dir, ch_key, start_page):
    """本章章首**保留下限** y：印刷标题所在 y（标题之上的块属上一章尾带）。

    标题就在页顶（或判不出）时返回 None = 不裁。
    """
    rec, _p, _n = chapter_bounds(ext, ch_key)
    if not rec:
        return None
    y = title_y_on_page(page_dir, start_page, rec.get("num_str"), rec.get("name"))
    return y


def tail_band(ext, page_dir, ch_key):
    """上一章尾带 → ``(页码, y 上限)``：本章标题之上的那一截归**上一章**。

    仅当本章起始页恰为 ``end_page + 1``（章图紧邻）且标题不在页顶时成立；否则
    None（不扩页）。
    """
    rec, _prev, nxt = chapter_bounds(ext, ch_key)
    if not nxt or not rec:
        return None
    # 🔴 页区间一律以**章图**为准（不用调用方传入的本章末页）：契约末页会随切带
    # 自身而漂移（用上版末页算出的 end 在重跑时把 end 推到 next.start，紧邻判据
    # 随即失效 → 二次运行把尾带又吞回本章 = 不幂等）。
    if int(rec.get("end") or 0) + 1 != int(nxt.get("start") or 0):
        return None
    p = int(nxt["start"])
    y = title_y_on_page(page_dir, p, nxt.get("num_str"), nxt.get("name"))
    if y is None:
        return None
    return (p, y)


def clip_page(page_dir, out_dir, page, lo=None, hi=None):
    """把 `page` 按 y 窗口 ``[lo, hi)`` 裁出一份新的 ``page_%03d.json`` 到 `out_dir`。

    用途：骨架 / 条目扫描器按「整页」取数，尾带页需要的是**上一章视角下的半页**。
    与其给十余个抽取器逐个加 y 窗口参数，不如喂它一份裁好的临时页——判定与
    :func:`head_floor` / :func:`tail_band` 同源（同一 poly y），两侧口径天然一致。

    返回裁出文件路径；源页缺失或裁空返回 None（调用方据此跳过补扫）。
    """
    src = os.path.join(page_dir, "page_%03d.json" % int(page))
    if not os.path.exists(src):
        return None
    try:
        with open(src, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return None

    def _in(y):
        return (lo is None or y >= lo) and (hi is None or y < hi)

    kept = 0
    texts = []
    for b in data.get("text") or []:
        if not isinstance(b, dict):
            continue
        ys = _poly_ys(b.get("poly") or [])
        if ys and _in(min(ys)):
            texts.append(b)
            kept += 1
    forms = []
    for fblk in data.get("formulas") or []:
        if not isinstance(fblk, dict):
            continue
        bbox = fblk.get("bbox") or []
        try:
            fy = float(bbox[1])
        except (TypeError, ValueError, IndexError):
            fy = None
        if fy is None or _in(fy):
            forms.append(fblk)
            kept += 1
    if not kept:
        return None
    out = dict(data)
    out["text"] = texts
    out["formulas"] = forms
    os.makedirs(out_dir, exist_ok=True)
    dst = os.path.join(out_dir, "page_%03d.json" % int(page))
    with open(dst, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False)
    return dst
