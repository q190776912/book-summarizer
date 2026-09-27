"""lib/section_titles.py — 节标题「折行截短」核心校验（纯函数，无副作用）。

背景（2026-09-27 Rosen《离散数学》8e 实测）
-----------------------------------------
原书节题**排成两行**时（"6.1 The Basics of / Counting"、"8.6 Applications of /
Inclusion-Exclusion"），抽取器（`scan_skeleton` 的 `SEC_2` 等）按**单行**正则取标题，
只拿到第一行，第二行既不含序标也不匹配任何条目正则 → 被当正文噪声丢弃。于是分章契约
的节节点 `name` 天生残缺（`6.1 The Basics of`），并顺着 `split_draft_units` 灌进单元
H2、首行 `name=`、manifest 与最终 md **文件名**（`Chapter6_6.1_The_Basics_of.md`）。
更糟的是两种半修形态都存在：步骤 5 的写手凭印刷证据把**单元 H2** 补全了而契约照旧残缺
（SSOT 与成品分叉，下次重拆即回退成残题），以及契约/单元**双双残缺**（成品直接是残题）。
全书 623 个节点里 34 个中招，此前**没有任何闸门看得见**（门控按 key/tag/图片对账，
verify 的 B/O 层只比序标不比标题文字）。

判据（保守，宁可漏报）
--------------------
1. **悬空结尾**（`dangling_reason`）：节题末词是英文虚词（of/and/the/to/…）或以连字符
   结尾——印刷标题不可能这样收笔，必是折行续行被丢。只对**拉丁文**标题生效（中文标题
   「……是如何陈述的」「为什么数学归纳法是有效的」结尾的「的」完全合法，CJK 虚词判据
   实测假阳率 100%，故不提供）。
2. **契约 ↔ 单元标题对账**（仅源语言单元目录跑；译版 H2 是译文，与契约英文标题不可比）：
   两侧归一（去 `#`/`§`/序标/尾部页码残渣、压空白、统一撇号、转小写）后必须相等；
   不等时按前缀关系分报「契约截短」/「单元缺词」/「互非前缀」三种修法提示。

修法一律在**提取层**（契约 `name` + 单元 H2 + 首行 `name=` + 两侧 manifest `name` 五处
同步，源单元正文变化后须重跑 `init_translate_units` 重同步 src_hash），以页 OCR 行 /
书前目录行为准补全；**不是**把单元标题削短去迁就契约。
"""
import re

# 英文虚词：真印刷标题绝不以它们收笔（末词整词比较，故 "Divide-and-Conquer" 安全）
DANGLE_EN = frozenset("""of and the a an in for with on or at by as to into onto upon
from their its that which this these those is are be not but nor yet so than then
although because while during between among through each every all some most""".split())

_TRAILING_HASH = re.compile(r"^#+\s*")
_ORDINAL_PREFIX = re.compile(r"^[§＄\$]?\s*")
# 尾部 OCR 粘连页码（'Phase Flows 57' / 'Complexification and Realification177'）
_TRAIL_PAGE = re.compile(r"(?:[\s,，]\d{1,4}|\d{2,4})\s*$")
_APOS = {"\u2019": "'", "\u2018": "'", "\u02bc": "'", "\uff07": "'"}
_TRAIL_DOT = re.compile(r"[.．。]\s*$")


def _drop_ordinal(text, key):
    t = str(text or "").strip()
    t = _TRAILING_HASH.sub("", t)
    t = _ORDINAL_PREFIX.sub("", t).strip()
    k = str(key or "").strip()
    if k and t.startswith(k):
        t = t[len(k):]
        t = re.sub(r"^[\s.．、:：\-]+", "", t)
    return t.strip()


def title_of(body):
    """单元正文（首行标记之后）里的第一个标题行文本；没有标题行返回 ''。"""
    for ln in str(body or "").split("\n"):
        s = ln.strip()
        if s.startswith("#"):
            return s
    return ""


def clean_title(text, key=""):
    """标题的**展示形态**：去 `#`/`§`/序标/尾部页码残渣，保留大小写与标点。"""
    t = _drop_ordinal(text, key)
    prev = None
    while prev != t:                      # 反复剥（'Termi- 57' 式多重残渣）
        prev = t
        t = _TRAIL_PAGE.sub("", t).strip()
    return t


_BARE_LOCAL_ORDINAL = re.compile(r"^\d{1,2}[.\u00b7、]\s+")


def norm_title(text, key=""):
    """比对用归一形：无空白、撇号统一、小写、去尾点。"""
    t = clean_title(text, key)
    # numeric-local（bare_head）二级小节会把标题渲染成裸整数序号起头（如 "### 2. Phase
    # Spaces"）。那个 "2. " 是**展示产物**：既不是标题文字，也不等于节点 key（key 形如
    # "1.2"，_drop_ordinal 的前缀剥离命不中）。若不剥掉，单元侧 "2. Phase Spaces" 与
    # 契约侧 "Phase Spaces" 会「互非前缀」→ 误判 OCR 改写。此处（仅比对归一形，clean_title
    # 展示形不动）对称剥掉两侧的裸整数序号；真截短仍由 dangling_reason 与 startswith 前缀
    # 判据独立捕获，剥前后缀关系不变，不会漏报。
    t = _BARE_LOCAL_ORDINAL.sub("", t)
    t = "".join(t.split())
    for src, dst in _APOS.items():
        t = t.replace(src, dst)
    return _TRAIL_DOT.sub("", t).lower()


def dangling_reason(title, key=""):
    """返回截短成因（str）或 None（不是悬空形态）。"""
    t = clean_title(title, key)
    if not t:
        return None
    if t.endswith("-") or t.endswith("\u2010") or t.endswith("\uff0d"):
        return "以连字符收尾（印刷折行标题的续行被丢弃）"
    words = [w for w in re.split(r"\s+", t) if w]
    if not words:
        return None
    last = words[-1].strip(".,;:!?()\u201c\u201d\u2018\u2019\u300c\u300d\uff08\uff09")
    if last.lower() in DANGLE_EN:
        return "以英文虚词「%s」收尾（印刷折行标题的续行被丢弃）" % last
    return None


def section_names(contract):
    """契约里全部 section 节点：key -> name（原样）。"""
    out = {}

    def walk(node):
        for n in (node.get("sub_sec") or []):
            if (n.get("type") or "") == "section":
                out[str(n.get("key") or "")] = str(n.get("name") or "")
            walk(n)
    if contract:
        walk(contract)
    return out


def title_problems(contract, units, read_body, compare_names=True):
    """章级闸判据：返回问题列表（空 = 通过）。

    * contract —— 分章契约 dict（None = 无契约，只对单元标题做悬空检查）；
    * units —— manifest 的 units 列表；
    * read_body(unit) -> 单元正文；
    * compare_names —— False 时跳过契约↔单元对账（翻译单元目录：H2 是译文）。
    """
    probs = []
    names = section_names(contract) if contract is not None else {}
    for u in units or []:
        if (u.get("type") or "") != "section":
            continue
        key = str(u.get("key") or "")
        head = title_of(read_body(u))
        if not head:
            continue
        u_title = clean_title(head, key)
        why = dangling_reason(head, key)
        if why:
            probs.append("节 %s 标题疑折行截短：%r —— %s；须按该节首页印刷行/书前目录补全"
                         "（契约 name、单元 H2、首行 name=、两侧 manifest 五处同步）[%s]"
                         % (key, u_title, why, u.get("file") or ""))
        if not compare_names:
            continue
        cname = names.get(key)
        if cname is None:
            continue
        c_clean = clean_title(cname, key)
        why_c = dangling_reason(cname, key)
        if why_c and not why:
            probs.append("契约节 %s 的 name=%r 被折行截短（%s），而单元标题完整——"
                         "SSOT 残缺，重拆即回退成残题；须回填契约 name 与首行 name=/manifest "
                         "为印刷全题" % (key, c_clean, why_c))
            continue
        cn, un = norm_title(cname, key), norm_title(head, key)
        if cn == un or not cn or not un:
            continue
        if un.startswith(cn):
            kind = "契约 name 是单元标题的前缀（契约侧截短）"
        elif cn.startswith(un):
            kind = "单元标题是契约 name 的前缀（单元侧缺词，合并后即残题）"
        else:
            kind = "两侧互非前缀（其中一侧被 OCR 改写）"
        probs.append("节 %s 契约 name=%r 与单元标题=%r 不一致：%s；以印刷证据为准统一五处"
                     "（源单元正文若被改，须重跑 init_translate_units 重同步 src_hash）[%s]"
                     % (key, c_clean, u_title, kind, u.get("file") or ""))
    return probs
