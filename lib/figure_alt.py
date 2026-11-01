"""lib/figure_alt.py — 图 `alt` **形制判据**的唯一真源（写手 / 回写工具 / 闸共用）。

为什么要单独成模块：`alt` 的脏形（图号碎字、图号写了两遍、号后粘连、粘连词）在
2026-11-01 的 MSDA 返修里被同时抓到三个源头，而三处各写了一份判据必然漂移：
  · 写手：`embed_figures.short_caption()` / `render_draft._img_html()` 造 alt；
  · 回写：`tools/clean_figure_alts.py` 按证腿改 alt；
  · 校验：`gate_units.py` 要判「这批 alt 干不干净」。
⇒ 判据与「剥标签词+号」都只在这里有一份；其余三处一律 import，不许自带正则。

判据四档（`defects` 返回的四个键，全空即「净」）：
  label  图号碎字：`FIG U RE`（连续拆字）/ `FI G U RE`（散开拆字，MSDA 图 14.27
         实测）/ `FIGU RE`（拆在词中间，MSDA 图 14.12/14.26 实测——`RE_LABELJUNK` 要
         FIG 后带空白、片段表只连 1–3 字母，两档都漏 ⇒ 由 `half_junk` 补）/
         同一个号写了两遍（Lee ISM 图 5.3、MSDA 图 10.4 实测）。
  stuck  号后粘连：`10.4An` —— 号之后**直接跟 ≥2 个字母**且这串字母是题注首词的
         前缀（或互为前缀）。单子标号 `3.4A`（后随空格/另一词）合法，不算粘连。
  jam    粘连词：**不并连字符**取 token（`raw_toks`），>6 字母、不在参照词表里、
         且能切成两个参照词。参照词表 = 同图其余各腿（登记题注 / 别的单元 / 交付）
         剥号后的 token 集，并词形 ∪ 不并词形都要（`witness_toks`）；
         与本轮串**逐字相同**的腿不进参照表——同案被告不能给自己作证。
         🔴 连字符不参与粘连判定：`least-squares` / `Creasy-Williams` 是人写的复合词，
         并成 `leastsquares` 再查无此词＝判据自己造的假阳（两枪实测，见 `raw_toks`）。
         🔴 已知漏档：`split_ok` 只试**两刀**，三词串成一串（`500pseudorandomvariables`）
         不报（MSDA 图 9.8 交付实测）。
  esc    二次转义：`&amp;lt;` —— 印面 `<` 被转义两遍（MSDA 图 14.26 交付实测）；
         `&amp;` 单独出现不算（那是 `S&P` 的正形）。

`[:40]` 半词截断（旧 `short_caption` 的写法）造的串不在这里判：原地补空格修不回
被截掉的字母，只能回来源腿（`clean_figure_alts.in_place` 的锁②负责识别）。
"""
import os
import re

from lib.figure_io import FIGURE_LABELS_DEFAULT, fig_label_alt

# `<img>` 一行里 src/alt 的两种书写先后都支持
RE_FIGURE = re.compile(r'<img\b[^>]*?\bsrc="([^"]+)"[^>]*?\balt="([^"]*)"[^>]*?>',
                       re.I)
RE_FIGURE_REV = re.compile(r'<img\b[^>]*?\balt="([^"]*)"[^>]*?\bsrc="([^"]+)"[^>]*?>',
                           re.I)
RE_LABELJUNK = re.compile(r"\bFIG\s{1,3}U\s{1,3}RE\b|\bFIGURE\s+FIGURE\b", re.I)
# 书写**正确**的标签词（擦掉它们才看得见碎字）
RE_GOOD_LABEL_WORD = re.compile(r"\b(?:fig(?:ure)?|图|表)\.?\b", re.I)
# `&` 自己被二次转义：印面 `<` → `&lt;` → `&amp;lt;`（MSDA ch14 图 14.26 交付实测）。
# 题注里不可能这样印，`&amp;` 单独出现也不命中（那是 `S&P` 的正形转义）。
RE_DOUBLE_ESC = re.compile(r"&amp;(?:lt|gt|amp|quot|apos|#39);", re.I)
# 转义 → 本形。**只用于「比内容多少」**（`clean_figure_alts` 的禁改短锁）：转义层数是
# 形制，词表长度是内容；拿带转义的串直接比长度会把「同一句话」量成三个长度。
ENTS = {u"&lt;": u"<", u"&gt;": u">", u"&quot;": u'"', u"&apos;": u"'",
        u"&#39;": u"'", u"&#x27;": u"'", u"&nbsp;": u" ", u"&amp;": u"&"}


def unescape(s):
    u"""剥到不动点：`&amp;lt;` → `&lt;` → `<`。层数不定 ⇒ 一遍剥不干净不许算剥完。"""
    prev = None
    while prev != s:
        prev = s
        for k, v in ENTS.items():
            s = (s or u"").replace(k, v)
    return s or u""

RE_DUP_LABEL = re.compile(
    r"^\s*(?:图\s*)?(?:fig(?:ure|\.)?)\s*[0-9]+(?:\.[0-9]+)+[A-Za-z]?"
    r"[ ]{0,2}(?:图\s*)?(?:fig(?:ure|\.)?)\b", re.I)
RE_STUCK = re.compile(r"\b([0-9]{1,2}(?:\.[0-9]{1,2})+)([A-Za-z]{2,})")
# 标签词的书写形：写对（`Figure` / `Fig.`）、OCR 连续拆字（`FIG U RE`）、
# OCR 散开拆字（`FI G U RE`，MSDA ch14 图 14.27 实测）。
LBL = r"(?:fig(?:ure|\.)?|F\s+I\s+G(?:\s+U\s+R\s+E)?)"
# 号之后允许的分离符，按**尝试次序**排：`:`/`：`（可带前后空白）→ 空白 → 句点。
# 句点这一支**只会在「点紧贴号」时命中**（`Figure 1.3.The combined effect` 是数值分析
# ch1 的实测形：OCR 把号后的句点与空格挤在一起）；号与句点之间有空格时前一支 `\s+` 已经
# 吃掉空格，句点留在体里（`.NET framework` 这类首词不能少个点）。
# `strip_lead`（按登记号严剥）与 `_generic_lead`（通用剥）共用这一条尾巴——两处不一致就会
# 一个剥得动一个剥不动，alt 前导随即把号再拼一次。
LEAD_TAIL = u"(?:\\s*[:：]\\s*|\\s+|\\.)?\\s*"
RE_PLAIN_LABEL = re.compile(r"^[0-9]+(?:\.[0-9]+)*[A-Za-z]?$")
RE_ZONE_NUM = re.compile(r"[0-9]+(?:\.[0-9]+)+")
# 前导只写了标签词、没带号（`图`/`Fig.`/`Figure`/`表`）——原地档取本轮自己书写形的判据
RE_TAG_ONLY = re.compile(r"^\s*(图\s*|FIG\s{1,3}U\s{1,3}RE|fig(?:ure|\.)?|表)\s*$", re.I)
# 码位区间表（判语种用；不手敲汉字）
CJK = re.compile(u"[" + u"".join(u"%s-%s" % (chr(lo), chr(hi)) for lo, hi in (
    (0x3000, 0x30FF), (0x3400, 0x9FFF), (0xF900, 0xFAFF), (0xFF00, 0xFFEF))
) + u"]")


def toks(s):
    u"""词表（**给证人用**）：先把「字母-字母」「字母.字母」这类**词内标点**并回，再切。

    并 `-` 是印面行末断词（`approxi-mated` 会把写对的 `approximated` 反判成粘连）；
    并 `.` 是 OCR 把行末连字符**读成句点**（Modern Robotics ch5 图 5.32 登记题注实测
    `configura.tions` ⇒ 旧词表拆出 `configura`/`tions` 两个碎片，反过来把写对的
    `configurations` 判成粘连词，工具接着把**正词拆成两个半词**）。
    🔴 只有**连字符**允许后面带空格（OCR 常把行末断词写成 `approxi- mated` /
    `Creasy- Williams`），**句点不许带空格**：`s` 先小写过，`ming. We` 的句点+空格一旦
    被吃，两个词就粘成 `programmingwe` —— 参照表里**真证人词消失了**，写对的
    `programming` 反倒「查无此词」，再被 `split_ok` 拆成 `program`+`ming` 判成粘连
    （Koopman ch11 图 11.1 / ch16 图 16.2 实测 8 行，p1106 逐字坐实；工具当时要把
    对的 alt 改成 `program ming`）。空格仍是分隔符 ⇒ 印面真是两个词（`least squares`）
    时照样是两个证人词。
    """
    return _toks(s, True)


def raw_toks(s):
    u"""**不并**词内标点（`-` / `.`）的词表：标点处照旧切开。

    🔴 判「粘连词」用这一份，参照表两份都用（`judge`）。把 `least-squares` 并成
    `leastsquares` 再去问「别的腿里有没有这个 token」，等于**自己造一个别人没写过
    的串、再判它粘连**：数值分析 ch13 图 13.1（alt `least-squares` vs 登记题注
    `least squares`，印面就是两个词）与 statistical-inference ch12 图 12.2.3
    （alt `Creasy-Williams` vs 登记题注 `Creasy- Williams`，印面无空格）两枪都是
    这一形，且工具想把**写对的那侧**覆写成 OCR 侧 ⇒ 连字符是人写的复合词证据，
    不是 OCR 粘连证据。真粘连（`betweenthe`/`thatinvolves`）本来就没有分隔符，
    不并词也照样是同一个 token ⇒ 检出能力不降。
    """
    return _toks(s, False)


def _toks(s, merge):
    s = (s or "").lower()
    if merge:
        # 连字符：印面行末断词，OCR 常在其后补一个空格 ⇒ 两种间距都并
        s = re.sub(u"(?<=[a-z])-\\s*(?=[a-z])", u"", s)
        # 句点：只在**紧贴**时并（那是连字符被读成句点）；带空格的是句末标点，
        # 吃掉就把两个证人词粘成一个（见 `toks` 的 Koopman 实测）。
        s = re.sub(u"(?<=[a-z])\\.(?=[a-z])", u"", s)
    return [t for t in re.split(r"[^a-z0-9]+", s) if t]


def witness_toks(s):
    u"""参照词表：并词形 ∪ 不并词形**都要**。

    证人只有「一种写法」进表时，反过来就会误判：证人写 `least-squares`（并完只剩
    `leastsquares`）而被告写 `least squares` ⇒ 被告的 `squares` 查无此词。参照表放宽
    不削弱检出（粘连词判据问的是「能不能切成两个词」，多给词形只会更容易切 ⇒ 更少报），
    收紧的一侧交给 `raw_toks`。
    """
    return set(toks(s)) | set(raw_toks(s))


def zone_of(text):
    """图号**之前**那段（碎字只会出现在这里）；没有号时看前 24 字符。"""
    m = RE_ZONE_NUM.search(text or u"")
    return (text or u"")[:m.start()] if m else (text or u"")[:24]


def label_frags(zone):
    u"""号前那段里的 1–3 字母片段连成的串（大小写都算，`Fig U RE` 与 `FI G U RE` 同形）。

    合法书写不会撞上：写对的 alt 号前只有 `Figure`/`Fig.`（6 字母或带点，整词
    长度 >3 进不了片段表），`ANOVA`/`QQ` 这类缩写同理。
    """
    return u"".join(re.findall(r"\b[a-z]{1,3}\b", (zone or u"").lower()))


def half_junk(text):
    u"""号被拆在**词中间**（`Figure FIGU RE 14.12`，MSDA ch14 图 14.12/14.26 单元实测）。

    两档旧判据都漏：`RE_LABELJUNK` 要 `FIG` 与 `U` 之间带空白，而这一形是 `FIGU`+`RE`；
    `label_frags` 只连 1–3 字母片段，`FIGU` 长 4 进不了表 ⇒ 号前只剩 `re`。
    新判据：**擦掉书写正确的标签词**后，号前剩下的字母去空白恰好拼成 `figure`/`fig`。

    🔴 必须**真有号**才判（`RE_ZONE_NUM` 命中即返回，不许用 `zone_of` 的 24 字符兜底）：
    兜底实测两类假阳——中文 alt 里散落的单字母（`对复形 F … I … G …` 连成 `fig`，
    Rising Sea ch23）与 `FIGURE9`（裸整数号与词**粘连**，Rosen ch12，那是另一档不是拆字）。
    p1131 全架量面：收紧后净增命中 4 行，全部是 MSDA ch14 那两张图（另 0 本 0 行）。
    """
    m = RE_ZONE_NUM.search(text or u"")
    if not m:
        return False
    letters = re.sub(u"[^a-z]", u"",
                     RE_GOOD_LABEL_WORD.sub(u" ", (text or u"")[:m.start()]).lower())
    return letters in (u"figure", u"fig")


def lead_junk(text):
    u"""图号被 OCR 拆字：连续形 `FIG U RE`、散开形 `FI G U RE` / `Fig U RE`、
    词中间半拆形 `FIGU RE` 三形都认。MSDA ch14 图 14.27 实测是散开形、
    图 14.12/14.26 实测是半拆形，只配前两形会整条漏掉。"""
    return bool(RE_LABELJUNK.search(text or u"")) or \
        label_frags(zone_of(text)) == u"figure" or half_junk(text)


def drop_junk_lead(text):
    u"""号前那段若只是「Figure 被拆字」的碎片 ⇒ 整段丢掉。

    三种实测形：`Figure FIG U RE 10.4An…`（写对的词 + 碎字）、`Fig U RE 10.4An…`
    （只有碎字）与 `Figure FIGU RE 14.12 …`（半拆字，`half_junk`）。留着它们，
    重组时会把碎字搬进新 alt 尾部（= 新碎字）。
    """
    if label_frags(zone_of(text)) == u"figure" or half_junk(text):
        m = RE_ZONE_NUM.search(text or u"")
        return (text or u"")[m.start():] if m else u""
    return text or u""


def strip_lead(text, label):
    u"""剥开头的「标签词 + 登记号」（含碎字前导、重复号）。号只认 `label` 那一个，
    且剥号时**不吃紧跟其后的第一个字母**（`5.3Smooth` 剥成 `mooth…` 是新碎字）。

    号之后的否定预查只禁「紧跟数字」与「紧跟 .数字」两种延伸，**不再禁单个句点**：
    数学书题注的主流书写是 **`Figure 1.1. Caption`**（号后带句点），旧预查把句点也算成
    号的延伸 ⇒ 整条剥不掉 ⇒ 写手侧会把号再拼一次，造出「图号写了两遍」（p1096 实测
    503 条）。号后的句点由 `LEAD_TAIL` 吃，空白支在前 ⇒ 空之后的句点留在体里。
    """
    if not label:
        return (text or "").strip()
    pat = re.compile(
        u"^\\s*(?:图\\s*)?" + LBL + u"?\\s*"
        + re.escape(label) + r"(?![0-9])(?!\.[0-9])(?:[A-Za-z](?![A-Za-z]))?"
        + LEAD_TAIL,
        re.I)
    out = drop_junk_lead(text)
    for _ in range(3):
        nxt = pat.sub("", out, count=1).strip()
        nxt2 = drop_junk_lead(nxt)
        if nxt2 == out:
            break
        out = nxt2
    return out


def lead_of(text):
    """串开头的图号（不带标签词也算）；用于「不许跨图搬题注」。"""
    m = re.match(u"^\\s*(?:图\\s*)?" + LBL + u"?\\s*"
                 r"([0-9]+(?:\.[0-9]+)*)", text or "", re.I)
    return m.group(1) if m else None


def split_ok(t, ws):
    for i in range(3, len(t) - 2):
        if t[:i] in ws and t[i:] in ws:
            return True
    return False


def defects(text, label, ref_set, first_word):
    u"""→ {label:[…], stuck:[…], jam:[…], esc:[…]}；四项全空即「干净」。"""
    lab = [m.group(0) for m in RE_LABELJUNK.finditer(text or "")]
    if not lab and lead_junk(text):
        lab.append(u"图号拆字(散开形)" if label_frags(zone_of(text)) == u"figure"
                   else u"图号拆字(词中半拆形)")
    if RE_DUP_LABEL.match(text or ""):
        lab.append(u"图号写了两遍")
    stuck = []
    for m in RE_STUCK.finditer(text or ""):
        tail = m.group(2).lower()
        if first_word and (tail.startswith(first_word) or first_word.startswith(tail)):
            stuck.append(m.group(0))
    jam = [t for t in raw_toks(strip_lead(text, label))
           if len(t) > 6 and t not in ref_set and split_ok(t, ref_set)]
    esc = [m.group(0) for m in RE_DOUBLE_ESC.finditer(text or u"")]
    return {"label": lab, "stuck": stuck, "jam": jam, "esc": esc}


def dirty(d):
    return bool(d["label"] or d["stuck"] or d["jam"] or d["esc"])


def why(d):
    bits = []
    for k, nm in (("label", u"图号碎字"), ("stuck", u"号后粘连"), ("jam", u"粘连词"),
                  ("esc", u"二次转义")):
        if d[k]:
            bits.append(u"%s=%s" % (nm, u"/".join(u"%s" % x for x in d[k][:3])))
    return u",".join(bits) if bits else u"净"


def judge(text, label, legs):
    u"""按「其余各腿互为参照」评一条串。`legs` = [(腿名, 串)]（含本轮串自己）。

    与 `text` 完全相同的腿**不进参照表**：同案被告不能给自己作证（units 与
    units-translate 逐字同源，MSDA 28 行全是这一形）。
    """
    others = [(n, v) for (n, v) in legs if (v or "").strip() != (text or "").strip()]
    ref = set()
    for _n, v in others:
        ref |= witness_toks(strip_lead(v, label))
    first = ""
    cap = next((v for (n, v) in legs if n == "C" and (v or "").strip()), "")
    if others:
        if cap.strip() and cap.strip() != (text or "").strip():
            first = (toks(strip_lead(cap, label)) or [""])[0]
        else:
            first = (toks(strip_lead(others[0][1], label)) or [""])[0]
    return defects(text, label, ref, first)


def _nospace(s):
    return re.sub(r"\s+", "", s or u"")


def img_pairs(text):
    """正文里所有 (src末段, alt, alt值区间)；src/alt 先后两种书写形都支持，按区间去重。"""
    out, seen = [], set()
    for rx, si, ai in ((RE_FIGURE, 1, 2), (RE_FIGURE_REV, 2, 1)):
        for m in rx.finditer(text):
            key = (m.start(ai), m.end(ai))
            if key in seen:
                continue
            seen.add(key)
            out.append((os.path.basename(m.group(si)), m.group(ai), key))
    return out


# ---------------------------------------------------------------------- 写手侧
# `alt = 标签词 + 号 + 题注体`，三段各有唯一取法，凑起来杜绝实测的三形：
#   号优先取 `figure_index.json` 的 `label`（旧写法拿正则去题注里**再找一遍**号，
#     题注被 OCR 拆字时找不到 ⇒ 退化成「只有标签词、没有号」，数值分析 ch13–16 实测）；
#   体一律过 `strip_lead`（旧写法的剥号正则只认「标签词紧贴号」，`Fig U RE 10.4`
#     与 `Figure FIG U RE 10.4` 剥不掉 ⇒ 前导再拼一次号，就是 Lee/MSDA 的「图号写了两遍」）；
#   截断走词边界（旧写法 `s[:40]` 把 `effect` 切成 `effec`，原地补空格修不回来）。

def alt_label(caption, label):
    u"""alt 该带哪个号：登记表 `label` 优先；未登记的图（unnamed）才回退题注自己写的号。

    前导与体**必须用同一个号**：体用 A 号剥、前导拼 B 号，就会造出重复号或丢号。
    """
    return (label or u"").strip() or (lead_of(caption) or u"")


def label_prefix(caption, labels):
    u"""题注开头**实际写出**的标签词形（允许被拆字）；对不上就用本书声明的第一个形。

    只在串首找：题注散文里出现的小写 `figure`（`…see figure 3 for…`）不是前导，
    把它当书写形会把 alt 的前导改成与全书体例不同的形。
    题注自己**没写**标签词时的兜底必须**合语种**：默认表是 `["图", "Figure", "Fig"]`
    （无 config 的书才用它），直取 `labels[0]` 会把中文形塞进英文题注（`图 10.4 An
    additive…`）⇒ 按「题注含无 CJK」挑第一个同语种的声明形。
    """
    cap = caption or u""
    for lab in sorted([str(x) for x in (labels or [])], key=len, reverse=True):
        if not lab or lab.isspace():
            continue
        rx = u"\\s*".join(re.escape(c) for c in lab if not c.isspace())
        m = re.match(u"^\\s*" + rx + u"\\.?", cap, re.I)
        if m:
            return lab + (u"." if m.group(0).endswith(u".") else u"")
    has_cjk = bool(CJK.search(cap))
    for lab in [str(x) for x in (labels or [])]:
        if lab and not lab.isspace() and bool(CJK.search(lab)) == has_cjk:
            return lab
    return (str(labels[0]) if labels else u"")


# 剥完号之后**体自己就以标签词开头**的形：登记题注本身就是脏串时会出现
# （Fraleigh 图 3.10 登记成 `'3.10 Figure'`、Katok 附录图登记成 `'FIGURE F.1.'`）。
RE_BODY_LABEL_WORD = re.compile(u"^\\s*(?:图|表|fig(?:ure|\\.)?)\\b", re.I)


def alt_prefix(caption, label, labels, body=None):
    u"""→ alt 的前导（`标签词 + 号`）；题注体由 `strip_caption_lead` 出，两者共用 `alt_label`。

    `body`（已剥好、已截断的体）传入时：体自己就以标签词开头 ⇒ 前导**只补号、不再说一遍
    标签词**。否则登记侧的脏题注会被拼成 `Figure 3.10 Figure` / `Figure FIGURE F.1.`——
    判据里正是「图号写了两遍」与连续拆字两档，而这两档的脏源在登记题注，不在拼装。
    （两种脏题注的分叉由 `build_alt` 裁决，别在这里加条件。）
    """
    num = alt_label(caption, label)
    word = label_prefix(caption, labels)
    if body and RE_BODY_LABEL_WORD.match(body):
        word = u""
    return u" ".join(p for p in (word, num) if p).strip()


def alt_body(caption, label, labels, limit=40):
    u"""alt 的「体」= 剥号后截到词边界（写手侧的默认体；book 特定改写由调用方自己接）。"""
    return clip_words(strip_caption_lead(caption, label, labels), limit)


def build_alt(caption, label, labels, body_fn=None):
    u"""→ 一条登记图目的**规范 alt**（前导与体在这里一次装配，两处规则不再可能打架）。

    登记侧的脏题注有两种，处理方向相反，所以必须看到**完整的体**才能定：
      · 体除了标签词什么都不剩（Fraleigh 登记 `'3.10 Figure'` ⇒ 体 = `Figure`）
        ⇒ 体交空、前导保留「词 + 号」⇒ `Figure 3.10`（正形，且没删任何登记字：
        那些字本来就只是重复标签词）；
      · 体里标签词之后还有内容（Fraleigh 图 5.10 的 `(a) Subgroup diagram…`、
        Katok 的 `FIGURE F.1.`）⇒ **保住内容**，改为前导只补号 ⇒ `5.10 Figure(a) …`。
    选「宁可前导不优雅，也不删登记侧的字」：alt 是题注的派生品，题注欠账由印面取证
    那一轮去清（本档 p1093 的「登记侧脏」桶），不在这里顺手改字。
    """
    body = (body_fn or alt_body)(caption, label, labels)
    m = RE_BODY_LABEL_WORD.match(body or u"")
    if m and not toks(re.sub(r"^\W+", u"", body[m.end():])):
        body = u""
        pre = alt_prefix(caption, label, labels)
    else:
        pre = alt_prefix(caption, label, labels, body)
    return ((pre + u" " + body) if pre else body).replace(u'"', u"'").strip()


_LEAD_CACHE = {}


def _generic_lead(labels):
    """「标签词紧贴的任意号」的通用剥法（按本书声明的标签词形，含 OCR `l` 误读形）。"""
    key = tuple(str(x) for x in (labels or FIGURE_LABELS_DEFAULT))
    if key not in _LEAD_CACHE:
        _LEAD_CACHE[key] = re.compile(
            u"^(?:图\\s*)?(?:" + fig_label_alt(list(key)) + u")\\s*"
            u"[0-9]+(?:[.\\-][0-9]+)*(?:[A-Za-z](?![A-Za-z]))?" + LEAD_TAIL, re.I)
    return _LEAD_CACHE[key]


def strip_caption_lead(caption, label, labels=None):
    u"""题注 → alt 的体（**未截断**）：先按登记号严剥，一点没剥动再按通用形剥一次。

    为什么必须有通用剥这一层：登记表的号形与题注写的号形**可以不同**（`1-1` 对 `1.1`、
    题注写全 `1.1.2` 而登记只到 `1.1`、题注是 `FIGURE 0.1.` 而声明形是 `Figure`）。
    这时 `strip_lead` 按登记号剥不动，而 `alt_prefix` 照样把登记号拼回去 ⇒ alt 同时带
    两个号，正是本档要根治的「图号写了两遍」（p1096 在 Weibel/Rising Sea 实测 503 条）。
    通用剥只吃「紧贴标签词的号」，不吃散文；剥不成就原样留着——号缺失由前导补，不会重复。
    """
    s = strip_lead(caption, alt_label(caption, label))
    if (caption or u"").strip() and s == (caption or u"").strip():
        s = _generic_lead(labels).sub(u"", s, count=1).strip()
    return s


def clip_words(s, limit=40):
    u"""按**词边界**截断：宁可不截到上限，也不留半个词（半个词在判据里修不回来）。

    中文题注没有词边界可依 ⇒ 按字符截（`toks()` 不产中文 token，半字不会被判粘连）。
    """
    s = (s or u"").strip()
    if len(s) <= limit:
        return s
    if CJK.search(s):
        return s[:limit].strip()
    cut = s.rfind(u" ", 0, limit + 1)
    if cut <= 0:                       # 40 字符内没有空格：单长词，只能整体留/切
        return s[:limit].strip()
    return s[:cut].strip()
