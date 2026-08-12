"""build_structure.py — 统一结构骨架生成器：产出全书单个 book_structure.json（书对象）

设计（2026-08-12 用户最终确认）
------------------------------
全书只产出一个 ``<extract_dir>/book_structure.json``，顶层是一个「书」对象（**不是数组**）：
    {"key": -1, "type": -1, "name": "<书名>", "page_start": <书起始页>,
     "page_end": <书终止页>, "sub_sec": [ <章节对象...> ]}
章节 / 条目节点递归嵌套，schema 见 ``flows/extract/structure/structure.md``
（key / type / name / page_start / page_end / sub_sec）。

增量合并：已存在 book_structure.json 时，替换/追加指定章（``build_structure <ext> [ch ...]``），
随后按章号稳定排序并整体写回；不传 <ch> 即全量重建全书。模型类见
``data/book_structure/book_structure.py``（BookStructure / StructureNode）。


为什么需要它
------------
本脚本把 `scan_skeleton` 的 `SEC`/`EXER` 扫描 与 `extract_items*` 的编号项抽取**内部调用**，
统一合成为**单一 `book_structure.json` 书对象**，一次产出同时满足两类需求：
  · write-source 写作契约：章节顺序、条目/练习齐全、印刷标题（name 带序标）。
  · verify 编号项基准：展平树、filter type!="exercise" 即得本书编号项集合
    （data_provider 改为读此 JSON，不再重跑抽取器）。

设计要点（与 verify/data_provider 对齐）
--------------------------------------
  · 编号模式（three-level / two-level / en / vakil / gm / roman / fraleigh）
    由 `<extract_dir>/verify_config.json` 的 `ordinal` 自动判定，与 verify/data_provider
    同一套分派逻辑。**build_structure 是抽取器的唯一调用方**（verify 读 JSON，不再重跑抽取器）。
  · **条目权威来自抽取器**（带类型）：skeleton 的 ITEM 行对 dash 编号书
    （如 Kreyszig `1.1-1`）匹配不到 `1.1.1.` 正则，故不可靠；en two-level 的
    skeleton 整块乱匹配，同样不可靠。所以 ITEM 节点一律用抽取器结果。
  · **章节骨架来自 skeleton SEC**（含印刷标题）；当某方案 skeleton SEC 捕获
    不全（en two-level / vakil），用「条目键派生章节号」补齐。
  · **练习来自 skeleton EXER**（统一来源），抽取器里的 练习/习题 类键被排除，
    避免与 EXER 重复计数。
  · 条目/练习挂到章节：优先「派生章节号命中」→ 否则「按页码归最近 SEC」。

节点字段
--------
    key        书原生编号（语言无关，如 "1.1-1" / "定义 1.2" / "1.2.A" / "1"）
    type       chapter|section|definition|theorem|lemma|corollary|proposition|
               example|exercise|remark|uncat
    name       带序标的纯标题（不含正文内容）；叶子即 key
    page_start 起始页（叶子 == page_end）
    page_end   容器取末代子孙页；叶子 == page_start
    sub_sec    递归子节点；仅 chapter/section 含此键（叶子省略）

顶层为数组，按章顺序；每章一个 chapter 节点。

用法
----
    python build_structure.py <extract_dir> [ch ...]
    # 全书：不传 <ch> 即扫全部章
    # 编号模式由 verify_config.json 的 ordinal 自动判定，无需 --scheme
"""
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

import json
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

import scan_skeleton
from extract_items import extract_items, extract_items_two_level
from extract_items_en import extract_items_en
from extract_items_vakil import extract_items_vakil
from extract_items_gm import extract_items_gm
from verify_config import (ORDINAL_EN, ORDINAL_TWO_LEVEL, ORDINAL_FRALEIGH,
                           ORDINAL_GM, ORDINAL_ROMAN, ORDINAL_VAKIL,
                           ConfigLoader, ConfigError, BookConfig)
import chapter_map
from verify.script.key_parse import _canon_label
from data.book_structure.book_structure import BookStructure, StructureNode


# ---------------------------------------------------------------------------
# 类型映射：抽取器 label（中文 canon 或英文原文） -> 树 type
# ---------------------------------------------------------------------------
_LABEL_TO_TYPE = {
    "定义": "definition", "Definition": "definition",
    "定理": "theorem", "Theorem": "theorem",
    "引理": "lemma", "Lemma": "lemma",
    "推论": "corollary", "Corollary": "corollary",
    "命题": "proposition", "Proposition": "proposition",
    "例": "example", "Example": "example",
    "评注": "remark", "Remark": "remark",
    "注": "remark",
    "断言": "proposition", "Assertion": "proposition",  # 近似归入命题
    "猜想": "uncat", "Conjecture": "uncat",
    "算法": "uncat", "Algorithm": "uncat",
    "假设": "uncat", "Assumption": "uncat",
    "uncat": "uncat",
}
_EXERCISE_LABELS = {"练习", "习题", "Exercise", "练习."}


def _type_of(label):
    return _LABEL_TO_TYPE.get((label or "").strip(), "uncat")


# ---------------------------------------------------------------------------
# 章节号推导
# ---------------------------------------------------------------------------
_STRIP_LABEL = re.compile(
    r'^(定义|定理|引理|推论|命题|例|评注|注|算法|假设|断言|猜想|'
    r'Definition|Theorem|Lemma|Corollary|Proposition|Example|Remark|'
    r'Assertion|Conjecture|Algorithm|Assumption)\b\s*', re.IGNORECASE)
_STRIP_LABEL_CN = re.compile(r'^(定义|定理|引理|推论|命题|例|评注|注)')


def _section_of_key(key, ordinal):
    """从带类型的条目 key 推导其所属『章节号』（用于挂到 section 节点）。

    返回 "C.S"（字符串）或 None（交由页码归并）。
    """
    if ordinal == ORDINAL_TWO_LEVEL:
        # 中文两级：key 形如 "定义1.1"（标签自有计数器），无章节分量 -> 页码归并
        return None
    k = _STRIP_LABEL.sub("", key)
    k = _STRIP_LABEL_CN.sub("", k)
    nums = re.findall(r"\d+", k)
    if ordinal == ORDINAL_FRALEIGH:
        # 节基两级：key 形如 "定义8.1"，首数字即『节号』
        return nums[0] if nums else None
    if len(nums) >= 2:
        return f"{nums[0]}.{nums[1]}"
    if len(nums) == 1:
        return nums[0]
    return None


def _section_of_exer(num):
    """练习序标（如 "1.2.A" / "1.2" / "1.A"）推导章节号；不足两级归章级。"""
    nums = re.findall(r"\d+", num)
    if len(nums) >= 2:
        return f"{nums[0]}.{nums[1]}"
    return None


# ---------------------------------------------------------------------------
# 标题清洗：从抽取器 text snippet 抽取印刷标题（去掉 key / label 前缀，截断）
# ---------------------------------------------------------------------------
def _clean_title(text, key):
    if not text:
        return ""
    t = text.replace(key, "", 1).strip()
    t = _STRIP_LABEL.sub("", t)
    t = _STRIP_LABEL_CN.sub("", t)
    t = t.strip(" .:：．，,()（）\u00a0")
    if not t:
        return ""
    if len(t) > 90:
        cut = t[:90]
        sp = cut.rfind(" ")
        if sp > 40:
            cut = cut[:sp]
        t = cut.rstrip(" .:：．，,") + "\u2026"
    return t


def _node(key, ntype, name, page):
    node = {"key": key, "type": ntype, "name": name,
            "page_start": page, "page_end": page}
    return node


# ---------------------------------------------------------------------------
# 章节图归一（兼容 多套字段名：chapter/start/end 与 num/start_page/end_page）
# ---------------------------------------------------------------------------
def _build_rng(cm):
    def _aint(x):
        try:
            return int(x)
        except (TypeError, ValueError):
            return None

    if isinstance(cm, dict) and "chapters" in cm:
        chs = cm["chapters"]
    elif isinstance(cm, dict):
        out = {}
        for kk, cc in cm.items():
            s = cc.get("start", cc.get("start_page"))
            e = cc.get("end", cc.get("end_page"))
            n = _aint(kk)
            if n is None or s is None or e is None:
                continue
            out[n] = (int(s), int(e))
        return out
    else:
        chs = cm
    out = {}
    for cc in chs:
        n = _aint(cc.get("num", cc.get("ch", cc.get("chapter", cc.get("n")))))
        s = cc.get("start", cc.get("start_page"))
        e = cc.get("end", cc.get("end_page"))
        if n is None or s is None or e is None:
            continue
        out[n] = (int(s), int(e))
    return out


def _chapter_title(cm, ch):
    if isinstance(cm, dict) and "chapters" in cm:
        ent = next((c for c in cm["chapters"] if str(c.get("num", c.get("chapter", c.get("ch")))) == str(ch)), None)
    elif isinstance(cm, dict):
        ent = cm.get(str(ch)) or cm.get(ch)
    else:
        ent = next((c for c in cm if str(c.get("num", c.get("chapter", c.get("ch")))) == str(ch)), None)
    if not ent:
        return ""
    for kk in ("title", "name", "name_en"):
        if ent.get(kk):
            return str(ent[kk])
    return ""


# ---------------------------------------------------------------------------
# 抽取器分派：build_structure 是抽取器的唯一调用方（data_provider 现已只读 JSON）。
# 生成 book_structure.json 后，verify 与 write-source 均消费该 JSON，不再重跑抽取器。
# ---------------------------------------------------------------------------
def _extract_items(ext, ch, start, end, book, manual=None):
    primary = book.primary_type
    if primary == ORDINAL_EN:
        items = extract_items_en(ext, start, end, want_examples=True)
        kept = []
        for it in items:
            lab, _, num = it["key"].partition(" ")
            chp = num.split(".")[0]
            if chp.isdigit() and int(chp) != ch:
                continue
            it = dict(it)
            it["key"] = f"{_canon_label(lab)}{num}"
            kept.append(it)
        return kept
    if primary in (ORDINAL_GM, ORDINAL_ROMAN):
        items, _, _ = extract_items_gm(ext, ch, start, end, manual_overrides=manual)
        return items
    if primary == ORDINAL_VAKIL:
        items, _, _ = extract_items_vakil(ext, ch, start, end, manual_overrides=manual)
        return items
    # three_level / two_level / fraleigh 全部走 extract_items（内部按 ordinal 选路）
    items, _, _ = extract_items(ext, ch, start, end, manual_overrides=manual, cfg=book)
    return items


# ---------------------------------------------------------------------------
# 单章结构构建
# ---------------------------------------------------------------------------
def build_chapter(ext, ch, start, end, book, cm):
    ordinal = book.primary_type
    language = book.language
    mode = scan_skeleton._mode_for_ordinal(ordinal, language)

    # 1) skeleton 原始行
    rows = scan_skeleton.scan(ext, ch, start, end, mode)
    sec_rows = [r for r in rows if r[1] == "SEC"]
    ex_rows = [r for r in rows if r[1] == "EXER"]

    # 2) skeleton SEC 去重（优先非空标题，保留最佳标题）
    sec_best = {}
    for p, kind, num, title in sec_rows:
        if num not in sec_best or (sec_best[num][3] == "" and title != ""):
            sec_best[num] = (p, kind, num, title)
    seen = set()
    dedup_sec = []
    for p, kind, num, title in sec_rows:
        if num in seen:
            continue
        seen.add(num)
        dedup_sec.append(sec_best[num])

    # 3) 抽取器条目（权威 ITEM，排除练习类）
    raw_items = _extract_items(ext, ch, start, end, book)
    items = [it for it in raw_items
             if (it.get("label") or "").strip() not in _EXERCISE_LABELS]

    # 4) 章节骨架：skeleton SEC ∪ 条目/练习派生章节号
    sec_pages = {}   # num -> 最佳候选页（skeleton）
    sec_titles = {}  # num -> 标题
    for p, kind, num, title in dedup_sec:
        sec_pages.setdefault(num, p)
        if title and not sec_titles.get(num):
            sec_titles[num] = title

    # 派生章节号收集（用于补齐 skeleton 缺失的章节）
    derived_sec_firstpage = {}
    def _note_sec(num, page):
        if num is None:
            return
        if num not in sec_pages:  # skeleton 已有则不打扰
            if num not in derived_sec_firstpage or page < derived_sec_firstpage[num]:
                derived_sec_firstpage[num] = page

    for it in items:
        _note_sec(_section_of_key(it["key"], ordinal), it["page"])
    for p, kind, num, title in ex_rows:
        _note_sec(_section_of_exer(num), p)

    all_sec_nums = list(sec_pages.keys()) + [n for n in derived_sec_firstpage if n not in sec_pages]
    # 章节排序：按（skeleton 页 或 派生最小页）
    def _sec_sort_key(n):
        return sec_pages.get(n, derived_sec_firstpage.get(n, start))
    all_sec_nums.sort(key=_sec_sort_key)

    sec_nodes = {}
    for n in all_sec_nums:
        title = sec_titles.get(n, "")
        page = sec_pages.get(n, derived_sec_firstpage.get(n, start))
        node = _node(n, "section", (f"{n} {title}".strip() if title else n), page)
        node["sub_sec"] = []
        sec_nodes[n] = node

    # 5) 条目/练习挂到章节
    chapter_bucket = []  # 无章节可挂时归章级（置于最前）

    def _place(node, sec_key, page):
        if sec_key is not None and sec_key in sec_nodes:
            sec_nodes[sec_key]["sub_sec"].append(node)
            return
        # 页码归并：最近的、起始页 <= page 的章节
        cand = None
        for n in all_sec_nums:
            if sec_pages.get(n, derived_sec_firstpage.get(n, start)) <= page:
                cand = n
        if cand is not None:
            sec_nodes[cand]["sub_sec"].append(node)
        else:
            chapter_bucket.append(node)

    for it in items:
        sec_key = _section_of_key(it["key"], ordinal)
        title = _clean_title(it.get("text", ""), it["key"])
        name = (f"{it['key']} {title}".strip()) if title else it["key"]
        node = _node(it["key"], _type_of(it.get("label")), name, it["page"])
        _place(node, sec_key, it["page"])

    for p, kind, num, title in ex_rows:
        sec_key = _section_of_exer(num)
        name = (title if title else num)
        node = _node(num, "exercise", name, p)
        _place(node, sec_key, p)

    # 6) 章节内子节点按页码稳定排序
    for n in all_sec_nums:
        sec_nodes[n]["sub_sec"].sort(key=lambda x: (x["page_start"], x["key"]))

    # 7) 递归算 page_start / page_end（容器取末代子孙页）
    def _fix_pages(node):
        kids = node.get("sub_sec")
        if not kids:
            return node["page_end"]
        child_starts = [k["page_start"] for k in kids]
        child_ends = [_fix_pages(k) for k in kids]
        node["page_start"] = min(child_starts)
        node["page_end"] = max(child_ends)
        return node["page_end"]

    ordered_secs = [sec_nodes[n] for n in all_sec_nums]
    for s in ordered_secs:
        _fix_pages(s)

    # 章级子节点：章级桶（无章节可挂）置于章节之前，按页码排
    chapter_bucket.sort(key=lambda x: (x["page_start"], x["key"]))
    sub = chapter_bucket + ordered_secs

    ch_title = _chapter_title(cm, ch)
    ch_name = (f"{ch} {ch_title}".strip()) if ch_title else str(ch)
    chapter = _node(str(ch), "chapter", ch_name, start)
    chapter["sub_sec"] = sub
    _fix_pages(chapter)
    return chapter


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    ext = args[0]
    want = [int(x) for x in args[1:]]

    cfg_path = os.path.join(ext, "verify_config.json")
    try:
        loader = ConfigLoader(ext, os.path.dirname(ext.rstrip("/")) or ext)
        loader.require_complete()
        book = loader.book
    except (ConfigError, ValueError) as e:
        # 兼容 chapter_map.json 含字母章号（附录 A/B…）导致 ConfigLoader 崩的
        # 既有书（如 Evans）。直接读 verify_config.json 构造 BookConfig（只解析
        # verify_config，不触发 chapter_map 解析），ordinal / language 不受影响。
        if not os.path.exists(cfg_path):
            print(e)
            return 2
        with open(cfg_path, encoding="utf-8-sig") as fh:
            vcfg = json.load(fh)
        book = BookConfig.from_dict(vcfg)

    cm = chapter_map.load_chapter_map_raw(os.path.join(ext, "chapter_map.json"))
    rng = _build_rng(cm)

    # 书名：取 book_dir 的目录名（ConfigLoader 已持有 book_dir = <book>）。
    book_dir = os.path.dirname(ext.rstrip("/")) or ext
    book_name = os.path.basename(book_dir) if book_dir else ""

    # 增量合并：若已存在 book_structure.json，则在其上替换/追加指定章；否则新建空书。
    bs = BookStructure.load(ext, book_dir) or BookStructure.new_book(book_name, book_dir)
    if not bs.root.name and book_name:
        bs.root.name = book_name

    for ch in (want or sorted(rng)):
        if ch not in rng:
            print("ch%-3d SKIP (not in chapter_map)" % ch)
            continue
        start, end = rng[ch]
        chapter = build_chapter(ext, ch, start, end, book, cm)
        node = StructureNode.from_dict(chapter)
        replaced = bs.root.replace_chapter(node)
        n_item = sum(1 for _ in _iter_items(chapter)
                     if _["type"] not in ("exercise", "section", "chapter"))
        n_ex = sum(1 for _ in _iter_items(chapter) if _["type"] == "exercise")
        n_sec = sum(1 for _ in _iter_items(chapter) if _["type"] == "section")
        verb = "UPDATE" if replaced else "ADD"
        print("ch%-3d %s | sections=%d items=%d exercises=%d"
              % (ch, verb, n_sec, n_item, n_ex))

    # 按章顺序稳定排序（chapter_map 顺序），避免增量写入导致乱序；再写回单个
    # book_structure.json（save 内部重算书根页码）。
    bs.root.sub_sec.sort(key=lambda n: _chapter_sort_key(n.key))
    out = bs.save(ext)
    print("BOOK -> %s | chapters=%d"
          % (os.path.basename(out), len(bs.root.sub_sec)))
    return 0


def _chapter_sort_key(key):
    """章号排序键：数字章号按数值，字母/其它章号（附录 A/B…）排末尾。"""
    try:
        return (0, int(str(key)))
    except (TypeError, ValueError):
        return (1, str(key))


def _iter_items(node):
    """展平树（不含 chapter 自身），供统计/消费使用。"""
    for k in node.get("sub_sec", []):
        yield k
        yield from _iter_items(k)


if __name__ == "__main__":
    sys.exit(main())
