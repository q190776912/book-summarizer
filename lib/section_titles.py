"""lib/section_titles.py — 节标题「折行截短 / 词间空格丢失」核心校验（纯函数，无副作用）。

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
   两侧归一（去 `#`/`§`/序标/尾部页码残渣、压空白、统一撇号与连接符、转小写）后必须相等；
   不等时按前缀关系分报「契约截短」/「单元缺词」/「互非前缀」三种修法提示。
3. **词间空格丢失**（`glued_reason`）：整名无空格而含驼峰接缝 = OCR 吞空格（判据与
   跨书标定见该函数注释）。第 2 条比对**剥掉空白**，看不见这类残缺，必须由本条补上，
   否则契约带病而门控放行（下次重拆即把成品退回粘连题）。

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
# 尾部 OCR 粘连页码（'Phase Flows 57' / 'Complexification and Realification177'）。
# 🔴 带空格的变体只剥 **两位以上** 数字：正文页码 ≥10 恒为两位数起，而真实节题常以
# 「词 + 个位数」收尾（Vakil 3e §19.8 'Curves of genus 4 and 5' 实测）——旧式 `\d{1,4}`
# 把「 5」当页码剥掉，制造出以 and 收尾的假悬空题（负向用例见 test_section_titles）。
_TRAIL_PAGE = re.compile(r"(?:[\s,，]\d{2,4}|\d{2,4})\s*$")
_APOS = {"\u2019": "'", "\u2018": "'", "\u02bc": "'", "\uff07": "'",
         # U+2032 PRIME 是导数记号的 Unicode 单码位（OCR/直接排印侧），与 ASCII 撇号、
         # 以及 `\prime` 宏折出来的 `'` 必须同形（见 _SYMBOL_TEX["prime"] 注释）。
         "\u2032": "'"}
# 🔴 **连字符族**（U+2013 en / U+2014 em / U+2212 minus / U+2010-2011-2012/2015 /
# U+2043 / 半角 `-`）在比对形里一律折成 `-`。抽题器与页 OCR 对同一个印刷连接符给出的
# 码位不同（印刷排 en dash、抽取侧归一成半角），而**写手按印面把单元 H2 里的连接符写成
# `–`** 是完全正确的做法——不折的话 `norm_title` 会把「Riemann–Roch」与「Riemann-Roch」
# 判成「两侧互非前缀（其中一侧被 OCR 改写）」，反过来要求「统一五处」，逼写手把印面的
# en dash 改成半角（Shafarevich 代数几何 1 ch3 §7「The Riemann–Roch Theorem on Curves」
# 与 §7.2 实测；折 dash 后两侧归一形相同，两条假报同时消失）。
# 只收**连字符族**码位（写成转义以免肉眼混淆）；中间点 `·`/`・` 不折——它不是连接符。
_DASHES = "\u2010\u2011\u2012\u2013\u2014\u2015\u2212\u2043\u2213-"
_DASH_MAP = {ord(c): "-" for c in _DASHES}
# 右括号族（半/全角圆括号、方括号、花括号、书名号右半）——`dangling_reason` 用它判
# 「虚词在括号组内」，见该函数注释。
_CLOSE_TAIL = (")", "]", "}", "\uff09", "\u3011", "\u300d", "\uff3d")
_TRAIL_DOT = re.compile(r"[.．。]\s*$")

# 🔴 **KaTeX 排版形 ↔ OCR 裸字符**在比对形里折成同一串（与上面折 dash 同一类，
# 2026-09-28 Apostol《Introduction to Analytic Number Theory》ch2 实测 6 处假报）：
# 契约节名来自页 OCR（`2.2 The Mobius function μ(n)`、`2.4 A relation connecting Φ
# and μ`），而写手**按印面**把单元 H2 写成数学模式（`The Möbius function $\mu(n)$`、
# `A relation connecting $\varphi$ and $\mu$`）——排版侧写 KaTeX 是写作要求，不是
# 偏差。旧 `norm_title` 只看空白/撇号/连接符，于是 `$\mu(n)$` ≠ `μ(n)`、`Möbius` ≠
# `Mobius`，六条**都对**的标题被判「两侧互非前缀（其中一侧被 OCR 改写）」并索要
# 「统一五处」，实际是逼写手把印面写法降级去迁就 OCR 残骸（闸门 bug 的经典形态：
# 闸把正确做法判死）。折形只在**比对**里做，`clean_title`（展示形）一律不动。
#   折叠三件事：① 剥数学定界符与宏包装（`$`、`\text{}`/`\mathrm{}`/`\operatorname{}`
#   取内容、未知宏丢反斜杠、花括号丢）；② 常见希腊字母宏映射成同一码位（`\mu`→μ、
#   `\varphi`→φ…，大小写都收，因 OCR 侧可能给出大写 Φ）；③ NFD 剥组合符（变音符
#   ö → o），使 `Möbius` 与 OCR 的 `Mobius` 归一。
# 🔴 折叠**不放松**截短判定：真截短（契约 `p(n)` vs 印面 `\varphi(n)` 一类 OCR 误读、
# 以及悬空虚词）照旧由前缀关系与 `dangling_reason` 报出。
_GREEK_TEX = {
    "alpha": "\u03b1", "beta": "\u03b2", "gamma": "\u03b3", "Gamma": "\u0393",
    "delta": "\u03b4", "Delta": "\u0394", "epsilon": "\u03b5", "varepsilon": "\u03b5",
    "zeta": "\u03b6", "eta": "\u03b7", "theta": "\u03b8", "Theta": "\u0398",
    "iota": "\u03b9", "kappa": "\u03ba", "lambda": "\u03bb", "Lambda": "\u039b",
    "mu": "\u03bc", "nu": "\u03bd", "xi": "\u03be", "Xi": "\u039e",
    "pi": "\u03c0", "Pi": "\u03a0", "rho": "\u03c1", "sigma": "\u03c3",
    "Sigma": "\u03a3", "tau": "\u03c4", "upsilon": "\u03c5", "phi": "\u03c6",
    "varphi": "\u03c6", "Phi": "\u03a6", "chi": "\u03c7", "psi": "\u03c8",
    "Psi": "\u03a8", "omega": "\u03c9", "Omega": "\u03a9",
    # 印刷体异形（`var` 前缀）折到同一码位：印面排 ϑ/ε/ϱ/ς/φ，写手可能用任一宏名
    "vartheta": "\u03d1", "thetasym": "\u03d1", "upvartheta": "\u03d1",
    "varrho": "\u03f1", "varsigma": "\u03c2", "varkappa": "\u03fa",
    "varpi": "\u03d6",
}
# 🔴 非字母符号宏同样必须折叠：写手在标题里写 `$(-1\mid p)$`（Legendre 符号）而
# OCR 侧给 `(-1|p)`；不折 `\mid` 的话 `\mid`→`mid` 与 `|` 永不相等，又是一条
# 「逼写手降级写法」的假阳（Apostol ch9 §9.3 实测形态）。
_SYMBOL_TEX = {
    "mid": "|", "lvert": "|", "rvert": "|", "vert": "|", "lVert": "\u2016",
    "rVert": "\u2016", "langle": "\u27e8", "rangle": "\u27e9",
    "dots": "\u2026", "ldots": "\u2026", "cdots": "\u22ef", "vdots": "\u22ee",
    "pm": "\u00b1", "mp": "\u2213", "cdot": "\u00b7", "bullet": "\u2219",
    "ast": "*", "star": "\u22c6", "circ": "\u2218",
    # 🔴 导数撇号：写手在节题里写 `$\zeta ^ { \prime } ( s )$`（印面 ζ′(s) 的规范 KaTeX
    # 写法）而 OCR/契约侧给 `ζ'(s)`。不收录 `\prime` 时宏名退化成裸词 `prime`，两侧
    # **永不同形** → `norm_title` 判「互非前缀（一侧被 OCR 改写）」，`fix_section_name`
    # 只能 REFUSE（它拒绝含 `\`/`$` 的 --name），于是要么闸把正确写法判死、要么逼写手
    # 降级标题——同一类闸门 bug（Apostol《IANT》ch13 §13.4/§13.6 实测）。折成 **ASCII
    # 撇号**，与 `_APOS` 把 U+2032 折到同一形配套。
    "prime": "'",
    "le": "\u2264", "leq": "\u2264", "ge": "\u2265", "geq": "\u2265",
    "ne": "\u2260", "neq": "\u2260", "equiv": "\u2261", "cong": "\u2245",
    "approx": "\u2248", "sim": "\u223c", "simeq": "\u2243", "propto": "\u221d",
    "times": "\u00d7", "div": "\u00f7", "bmod": " mod ", "pmod": " mod ",
    "sum": "\u2211", "prod": "\u220f", "int": "\u222b", "oint": "\u222e",
    "in": "\u2208", "notin": "\u2209", "ni": "\u220b", "subset": "\u2282",
    "subseteq": "\u2286", "supset": "\u2283", "supseteq": "\u2287",
    "cup": "\u222a", "cap": "\u2229", "emptyset": "\u2205", "varnothing": "\u2205",
    "forall": "\u2200", "exists": "\u2203", "nexists": "\u2204",
    "to": "\u2192", "rightarrow": "\u2192", "longrightarrow": "\u2192",
    "leftarrow": "\u2190", "leftrightarrow": "\u2194", "mapsto": "\u21a6",
    "implies": "\u21d2", "impliedby": "\u21d0", "iff": "\u21d4",
}
_TEX_MACRO_RE = re.compile(r"\\([a-zA-Z]+)")
_TEX_ARG_RE = re.compile(
    r"\\(?:mathrm|text|textrm|textit|mathit|mathbf|mathsf|operatorname|bm)"
    r"\s*\{([^{}]*)\}")
_TEX_SPACING_RE = re.compile(r"\\[,;! ]")


def fold_typeset_markup(text):
    r"""把 LaTeX/KaTeX 排版形折成**可与裸 OCR 文本比对**的形态（纯函数）。

    `$\mu(n)$` → `μ(n)`；`\text{Selberg}` → `Selberg`；`\mid` → `|`；`\Foo` → `Foo`；
    `$`/`{}`/上下标标记 `^` `_` 剥除。只供 `norm_title` 比对用；展示形（`clean_title`）
    绝不调用它。

    🔴 上下标标记一并剥除：写手对同一印面可写 `\sigma_a(n)` 或 `\sigma_{a}(n)`，
    花括号折叠后前者留 `σ_a`、后者留 `σa`——不剥 `_` 就是「两侧互非前缀」假阳。
    剥后 `^`/`_` 在两侧同形，真残缺（少词、误读字母）仍由前缀关系与
    `dangling_reason` 独立捕获。
    """
    t = str(text or "")
    t = _TEX_ARG_RE.sub(lambda m: m.group(1), t)
    t = _TEX_SPACING_RE.sub("", t)

    def _macro(m):
        name = m.group(1)
        return _GREEK_TEX.get(name) or _SYMBOL_TEX.get(name) or name

    t = _TEX_MACRO_RE.sub(_macro, t)
    for ch in "$\\{}^_":
        t = t.replace(ch, "")
    return t


def fold_diacritics(text):
    """NFD 剥组合符：`Möbius` → `Mobius`（OCR 常丢变音符，比对侧须同形）。"""
    import unicodedata
    t = str(text or "")
    if not any(ord(c) > 127 for c in t):
        return t
    d = unicodedata.normalize("NFD", t)
    return "".join(c for c in d if not unicodedata.combining(c))



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
    """比对用归一形：无空白、撇号统一、小写、去尾点，并折排版标记与变音符。

    折形只做**比对侧**同形（KaTeX `\mu` ↔ OCR 的 μ、`Möbius` ↔ OCR 的 `Mobius`），
    展示形 `clean_title` 不受影响；截短判定仍走 `dangling_reason` 与前缀关系。
    """
    t = clean_title(text, key)
    # numeric-local（bare_head）二级小节会把标题渲染成裸整数序号起头（如 "### 2. Phase
    # Spaces"）。那个 "2. " 是**展示产物**：既不是标题文字，也不等于节点 key（key 形如
    # "1.2"，_drop_ordinal 的前缀剥离命不中）。若不剥掉，单元侧 "2. Phase Spaces" 与
    # 契约侧 "Phase Spaces" 会「互非前缀」→ 误判 OCR 改写。此处（仅比对归一形，clean_title
    # 展示形不动）对称剥掉两侧的裸整数序号；真截短仍由 dangling_reason 与 startswith 前缀
    # 判据独立捕获，剥前后缀关系不变，不会漏报。
    t = _BARE_LOCAL_ORDINAL.sub("", t)
    t = fold_typeset_markup(t)
    t = "".join(t.split())
    t = t.translate(_DASH_MAP)
    for src, dst in _APOS.items():
        t = t.replace(src, dst)
    return fold_diacritics(_TRAIL_DOT.sub("", t).lower())


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
    raw_last = words[-1].rstrip()
    # 🔴 末 token 以**右括号**收尾 → 该虚词在括号组**内部**（数学变体 / 限定语），
    # 不是折行悬空。印刷折行的续行被丢弃时，标题必然收在**裸虚词**上，绝不会带着
    # 闭合括号收笔（带着右括号收笔说明这个括号组本身是完整的）。
    # 跨书普查（2026-09-29，corpus 690 份契约 / 6517 个 section 名）：dangling 命中 165 条，
    # 其中末 token 以右括号收尾的只有 **2 条**，均为印面真题——Apostol《IANT》
    # §12.7 `Hurwitz's formula for ζ(s, a)`、§12.11 `Evaluation of ζ(-n, a)`（末 `a` 是
    # Hurwitz zeta 的第二个变体，被当成冠词）。**零真截短被放过**。
    if raw_last.endswith(_CLOSE_TAIL):
        return None
    last = raw_last.strip(".,;:!?()\u201c\u201d\u2018\u2019\u300c\u300d\uff08\uff09")
    if last.lower() in DANGLE_EN:
        return "以英文虚词「%s」收尾（印刷折行标题的续行被丢弃）" % last
    return None


# 🔴 **OCR 吞掉词间空格**的粘连节题（Shafarevich 代数几何 1 实测 8 处：契约 §3.1
# name=`IrreducibleAlgebraicSubsets`、§2.2 `RegularFunctionsonaClosedSubset`、ch4
# §1.1/§2.7/§4.2/§4.5、ch3 §5.5/§7.2；根因在 OCR 块本身——`page_051.json` 该标题块
# text=`'3.1IrreducibleAlgebraicSubsets'`，抽取器照抄）。此前**没有任何闸门看得见**：
# `norm_title` 比较前剥掉全部空白，于是写手按印面
# 写对的 H2「Irreducible Algebraic Subsets」与残缺契约名**判等放行**，契约成为唯一带病
# 的 SSOT——下次 `split_draft_units` 重拆就把成品标题退回粘连形态（正是本模块要防的
# 「SSOT 与成品分叉」）。判据刻意收窄到零假阳形态：**整名不含任何空格** + 有
# 「小写→大写」驼峰接缝 + 长度 ≥8。跨书面标定（2026-09-28，corpus 全部契约 + 单元目录）：
# 命中 86 条报告 / 13 本书，抽样逐条为真粘连（'TheDeltaMethod'/'ConfidenceSets'/…）、
# 0 假阳。已知**漏报**（保守代价）：① 只吞掉**部分**空格的形态（`Exercises toSection 1`、
# `The General Definition ofIntersectionNumber`）——放宽到「含空格名 + 单词内
# 小写段→大写→小写段」跨书命中 142 处，其中 **110 处**属
# a-first-course-in-abstract-algebra 的「**整句被当节名**」形态（缺陷在收割形状而非空格，
# 报「补空格」会把修法带偏），故维持窄判据；② 纯小写粘连（`setofall` 一类）无从机械辨认。
_HUMP = re.compile(r"[a-z\u00e0-\u00ff](?=[A-Z\u00c0-\u00de])")


def glued_reason(title, key=""):
    """返回粘连成因（str）或 None（不是该形态）。"""
    t = clean_title(title, key)
    if not t or len(t) < 8 or " " in t:
        return None
    if _HUMP.search(t) is None:
        return None
    m = _HUMP.search(t)
    seam = t[max(0, m.start() - 8):m.end() + 8]
    return "整名无词间空格而在「…%s…」处出现小写→大写接缝（OCR 把印刷词间空格吞掉）" % seam


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
        c_glued = glued_reason(cname, key)
        if c_glued:
            probs.append("契约节 %s 的 name=%r 词间空格丢失（%s）——SSOT 残缺而单元标题按印面"
                         "写对，重拆即回退成粘连题；须按印刷行回填契约 name 与首行 name=/两侧 "
                         "manifest 为印刷全题[%s]"
                         % (key, c_clean, c_glued, u.get("file") or ""))
            continue
        u_glued = glued_reason(head, key)
        if u_glued:
            probs.append("节 %s 单元标题=%r 词间空格丢失（%s），而契约 name 完整——按契约/印刷行"
                         "补回空格（单元 H2 与首行 name= 两处，改了源单元须重跑 init_translate_units "
                         "重同步 src_hash）[%s]"
                         % (key, u_title, u_glued, u.get("file") or ""))
            continue
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
