#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""coverage_gate.py — 反过度精简闸门（lower-bound gate）。

背景：verify 的 P 层只罚「太长 / 整段照抄」（>450 字/段），没有任何机制罚
「太短 / 漏内容」，写作 agent 缺少下界依据 → 系统性把 Tier 2 描述段整段删光，
读起来不完整、看不懂。本工具给出**可机器判定的覆盖度指标**，配套规则见
``docs/writing-rules.md`` 的「保真分级（Tier 1/2/3）」与 V-P 第 3 条。

三个指标（章级）
  ratio      压缩比 = md 正文词数 ÷ 源正文词数
             （两侧都剔除展示公式；源侧另剔除页眉页脚 / 参考文献 / 作者机构块）
  term_cov   术语覆盖率 = 源侧「稀有内容词」在 md 中出现的比例。
             分母口径：源频 ∈ [rare_min, rare_max]（默认 2–3）、长度 ≥ 4、
             非停用/常见词、且非 OCR 碎片。
             - 排除 hapax（源频=1）：OCR 书上 hapax 绝大多数是识别错字或
               断词残留，把它们计入分母等于要求总结「复述 OCR 错字」，
               与 writing-rules「严禁照抄 OCR 文本流」冲突。
             - 排除 OCR 碎片：无元音 / 5+ 辅音连缀 / 三连重复字符。
             未加权，每个词一票 → 漏掉一个概念就扣分。
  var_cov    变量覆盖率 = 源侧 LaTeX 数学对象在 md 中出现的比例。
             只认：希腊字母、具名算符/集合/空间命令、带下标的裸标识符；
             排除结构/环境命令（`\\left` `\\frac` …）、字体样式开关
             （`\\bf` `\\rm` `\\it` …）、关系符（`\\le` `\\ne` …）与函数
             （`\\ln` `\\arg` `\\max` …）——后者是排版/运算记号，不是数学对象。

译文口径
  `--scheme cn` 且源为非中文（即 md 是译本）时，词表语言不通，覆盖度
  **不可直接对 OCR 源测**（实测 term_cov 恒落在 0.01–0.13 的假红区）。
  此时自动改测同章源语言母版 `ChapterN_*.md` 并在行下标注；
  找不到母版则该章记 N/A，不参与 PASS/FAIL 判定。译本与母版的 1:1 同构
  由 `check_translate_parity` 把关，不归本工具管。

用法
    python tools/coverage_gate.py <extract_dir> <chapter_md> <chapter_no> [选项]
    python tools/coverage_gate.py <extract_dir> --all <book_dir> [--scheme en|cn]

选项
    --ratio MIN        压缩比下限（默认 0.55）
    --term MIN         术语覆盖率下限（默认 0.80）
    --var MIN          变量覆盖率下限（默认 0.85）
    --rare-max N       术语词频上界（默认 3）
    --rare-min N       术语词频下界（默认 2；设为 1 可退回含 hapax 的旧口径）
    --json             以 JSON 输出，便于脚本消费
    --show-missing N   列出未覆盖的术语 / 变量（默认 0 = 不列）

退出码
    0 = PASS（三项均达标）    1 = FAIL    2 = 用法/数据错误

注：源侧剔除参考文献依赖启发式（章内最后一个 "References" / "参考文献"
标题之后的全部内容），若某书参考文献标题形态特殊，可在 extract_dir 放
``coverage_gate_overrides.json``: {"skip_headings": ["Bibliography"]}。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── 词法 ────────────────────────────────────────────────────────────────
WORD_RE = re.compile(r"[A-Za-z]{4,}")
CJK_RE = re.compile(r"[\u4e00-\u9fff]{2,}")

STOP = set("""that this with from have been which their there where these those would could
should shall will can may might must into onto upon over under about above below between
through during before after while when then than them they its its' our ours your yours
his hers hers itself itselfs also such same more most less least very much many some any
each both either neither other others another however therefore thus hence moreover
furthermore nevertheless given using used use uses based follows following proposed
propose shown show shows obtain obtained results result here we our us
consider considered consider let denote denotes denoted define defined definition
chapter section figure table equation equations example examples remark note notes
paper work approach method methods system systems result obtained using respectively
""".split())

# 常见英语词（非技术词）：术语覆盖率只统计"看起来像专业/内容词"的 rare token，
# 否则 absence / account / achieve 这类通用词会把指标变成噪声。
COMMON = set("""able about above absence absent accept account achieve across act action
active activity actual actually add addition address adopt advantage affect afford after
again against age agree agreement ahead all allow allows almost alone along already also
although always among amount an analysis analyze and announce another answer any anyone
anything appear apply approach appropriate approve area argue argument arise around
arrive art article ask assign assist assume assure at attempt attention audience author
authors available average avoid away back bad base based basic basis bear beat become
before begin beginning behalf behave behavior behind belief believe below best better
between beyond big bill bit black blue board body book border both bound boundary box boy
break brief briefly bring broad brother budget build building business but buy call came
camera campaign can cannot capital car care carry case cases cash cause central century
certain certainly chair chance change character charge check child children choice choose
church city civil claim class clear clearly client clinical close closely closer
coffee cold college color come coming common company compare compared comparison
complete completely complex comply concept concern conclude conclusion condition conduct
conference confidence confirm conflict congress connect consider consideration consist
constant construct consult consumer contain content context continue contract contrast
control convention conversation copy corner corporate correct cost could council count
country county couple course court cover create credit crisis critical culture current
customer cut data date daughter day dead deal death debate decade decide decision declare
decline deep deeply degree department depend depends describe description design desire
despite detail details determine develop development die difference different difficult
difficulty dinner direct direction director discover discuss discussion disease display
distance distinct distribute division do doctor document dog door double down draw dream
drive drop drug due during each early east easy eat economic economy edge education
effect effective effort eight either election element eleven else elsewhere emerge
emphasis employ empty enable end energy engage engine English enjoy enough ensure enter
entire entirely environment equal equipment error especially establish estate estimate
even evening event ever every everybody everyone everything evidence exactly example
excellent except exchange executive exist existence expect expense experience expert
explain explanation explore express expression extend extension extent external extra
eye face fact factor fail failure fair fall family far father fear feature federal feel
feeling few field fight figure fill film final finally finance find fine finger finish
fire firm first fish five flat floor flow fly focus follow food foot force foreign
forget form formal former forward four free freedom friend front full fund function
future game garden gas general generate generation gentleman get girl give glad glass
go goal god gold good govern government grant great green ground group grow growth
guess guest guide gun guy hair half hand happen happy hard hardly head health hear heart
heat heavy help her here herself high highly him himself history hit hold hole home hope
hospital hot hotel hour house how however huge human hundred husband idea identify
identity if ignore ill image imagine impact important impose improve inch include
including increase indeed independent index indicate individual industry information
initial inner inside instead institute institution interest interested interesting
internal international interview into introduce investment invite involve issue item
join journal journey judge just keep kept key kill kind king kitchen know knowledge lab
labour lack lady land language large largely last late later laugh law lawyer lay lead
leader learning leave lecture left leg legal length less let letter level liberal library
lie life light like likely line link list listen literature little live local long look
lose loss lot love low machine main mainly maintain major majority make man manage
management manager many market marriage mass master material matter may maybe mean
measure media medical meet meeting member memory mention merely message middle might
military mind mine minister minute miss mission model modern moment money month more
morning most mother mouth move movement much music must name nation national natural
nature near nearly necessary need negative neglect neither never new news next nice
night nine no none nor normal north not note nothing notice notion novel now nowhere
number object obtain obvious obviously occasion occur ocean offer office officer official
often old once one only onto open operation opinion opportunity oppose option order
ordinary organ organization origin original other others our out outside over own page
pain paint paper parent part particular particularly partner party pass passage past
patient pattern pay peace people per percent perfect perform performance perhaps period
permanent person personal phase phone photo physical pick picture piece place plan plane
plant play please plenty point political pool poor popular population port position
positive possible power practice prepare present president press pressure pretty prevent
previous price prime prince principle print prior priority problem procedure proceed
process produce product production professional professor profile program project
promise promote property propose protect prove provide public publish pull purpose push
put quality question quick quickly quite quote race radio raise range rate rather reach
read ready real realize really reason receive recent recently recognize recommend record
recover red reduce reduction reflect reform refuse regard region relate relation
relationship release remain remark remember remind remove repair repeat replace reply
report represent request require research resource respond response responsibility rest
result return reveal rich right rise risk road role room round rule run safe same save
say scale scene schedule scheme school science scientist score sea season seat second
secretary section see seed seek seem sell send senior sense series serious serve service
set seven several sex shadow shall shape share sharp she sheet shift ship short should
shoulder show side sign signal significance significant silence similar simple simply
since sing single sir sister sit site situation six size skill skin small smile society
soldier some someone something sometimes somewhere son song soon sort sound source south
space speak special specific speech speed spend spirit sport staff stage stand standard
star start state statement station stay step still stop store story strategy street
stress strong structure student study stuff style subject submit succeed success
successful such sudden suddenly suffer sufficient suggest summer sun supply support
suppose sure surface surprise survey survive switch symbol system table take talk task
tax teach team tear technical technique technology telephone television tell ten term
test than thank that the their them themselves then theory there therefore these they
thing think third this those though thought thousand threat three through throughout
throw thus ticket time tiny title today together tomorrow tone too top total touch
toward town trade traditional train transfer travel treat treatment tree trial trip
trouble true truth try turn two type under understand unit until upon use useful usual
usually value various vary very victim view violent visit visual voice volume vote wait
walk wall want war warm warn watch water way weak wear week weight well west what when
where whether which while white who whole whom whose why wide widely wife will win wind
window winter wish within without witness woman wonder word work worker world worry
would write writer wrong yard year yes yet young your yourself youth zero
""".split())

# 源侧需整段截断的非内容小节（参考文献 / 致谢 / 基金 / 合规声明）
TAIL_CUT_HEADINGS = (
    "references", "bibliography", "reference", "参考文献",
    "acknowledgements", "acknowledgments", "acknowledgment",
    "funding", "conflict of interest", "compliance with ethical standards",
    "data availability", "declarations",
)

# 中文虚词（中文书术语统计时剔除）
CJK_STOP = set("""我们 他们 这个 那个 因此 而且 但是 如果 可以 因为 所以 就是 这样 那样
什么 怎么 对于 关于 以及 通过 由于 其中 这些 那些 一个 一种 情况 进行 得到 表示 说明
如下 上面 下面 本节 本章 文中 本书 参见 例如 注意 显然 于是 从而 并且 或者 则有 使得
""")

# LaTeX 结构命令（非数学对象，排除在"变量"之外）
LATEX_STRUCT = set("""frac dfrac tfrac binom sqrt sum int oint prod lim limsup liminf
left right big bigg Big Bigg biggl biggr qquad quad label tag begin end array aligned
cases matrix pmatrix bmatrix vmatrix text mathrm mathbb mathcal mathbf boldsymbol
boldsymbol operatorname underset overset stackrel displaystyle limits nolimits
cdot cdots ldots vdots ddots to mapsto rightarrow leftarrow Rightarrow Leftarrow
rightarrow leq geq neq approx equiv sim simeq propto in notin subset subseteq cup cap
infty partial nabla forall exists emptyset top log exp sin cos tan max min sup inf det
dim ker im re im hat tilde bar vec dot ddot check breve acute grave
""".split())

# 定界 / 尺寸 / 占位 / 箭头 / 杂符（排版件，不是数学对象）
LATEX_DELIM = set("""Big bigg Bigg bigl bigr Bigl Bigr biggl biggr Biggl Biggr bigm Bigm
Vert vert mid nmid lVert rVert lvert rvert langle rangle lceil rceil lfloor rfloor
lbrace rbrace lbrack rbrack lgroup rgroup lmoustache rmoustache
lefteqn vphantom phantom hphantom rule everymath sideset displaylimits ensuremath
cfrac dfrac tfrac boxed mathstrut strut smash vspace* hspace* qquad
colon dots hdots dotsc dotsb dotsm dotsi ddotso copyright dag ddag pounds
bowtie sqcup sqcap sqsupset sqsubseteq sqsupseteq circledcirc circledast
doteq triangle triangleleft triangleright bigtriangleup bigtriangledown
star bullet circ dagger ddagger backslash prime second minute degree angle measuredangle
nearrow searrow swarrow nwarrow hookrightarrow hookleftarrow rightharpoonup
xrightarrow xleftarrow xleftrightarrow xRightarrow xLeftarrow xleftrightarrow
longmapsto longrightarrow longleftarrow Longmapsto Longrightarrow Longleftarrow
Downarrow Uparrow updownarrow downarrow uparrow leftrightarrow
sqsubset sqsupset blacktriangle blacktriangledown varnothing emptyset
models perp parallel nparallel asymp simeq cong ncong doteqdot
llless gggtr lll ggg gtrless lessgtr
""".split())

# 字体 / 样式 / 间距开关（OCR 或排版残留，不是数学对象）
LATEX_STYLE = set("""bf it sf tt sp em rm sc sl bm bold mdseries upshape normalsize
bfseries itshape sffamily ttfamily scshape slshape textbf textit textsf texttt textsc
displaystyle scriptstyle textstyle small large Large LARGE huge Huge tiny footnotesize
nonumber notag center centering raggedright hfill hfil vfill vspace hspace medskip
bigskip smallskip noindent newline arraystretch darraystretch
cal frak bb scr scrs mathfrak mathfrak mathit mathsf mathtt mathnormal pmb
Tilde Tilde Dot Hat Vec Bar Check Breve Acute Grave Widehat Widetilde
tilde dot hat vec bar check breve acute grave widehat widetilde overline underline
overbrace underbrace overrightarrow overleftarrow overleftrightarrow underrightarrow
underleftarrow xleftarrow overparen underparen substack subarray
""".split())

# 具名算符 / 函数（不是变量）
LATEX_OPERATORS = set("""arg deg det dim exp gcd hom ker lcm lim ln lg log max min inf
sup sin cos tan sec csc cot sinh cosh tanh coth arcsin arccos arctan sinh cosh
Pr Im Re Res Tr tr diag span supp range null rank ord sgn sign const id Id
operatorname* mathop
""".split())

# 关系符缩写（不是数学对象）
LATEX_RELATIONS = set("""le ge ne ll gg nl leq geq neq lneq gneq lleq ggeq leqslant
geqslant nleq ngeq nless ngtrlesssim gtrsim llss gmgg
""".split())

# 希腊字母（唯一被认作"数学对象"的短命令）
# 规范形 = GREEK_BASE；OCR/UniMERNet 常吐出 `\upalpha` `\varGamma` `\varepsilon`
# 等变体，比对前一律经 GREEK_ALIAS 归一（writing-rules V-C 允许记号归一）。
GREEK_BASE = set("""alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu
nu xi pi rho sigma tau upsilon phi chi psi omega
Gamma Delta Theta Lambda Xi Pi Sigma Upsilon Phi Psi Omega""".split())

GREEK_ALIAS = {}
for _g in list(GREEK_BASE):
    for _pre in ("up", "var", "Up", "Var", "displaystyle"):
        GREEK_ALIAS[_pre + _g] = _g
GREEK_ALIAS.update({"varepsilon": "epsilon", "vartheta": "theta", "varpi": "pi",
                    "varrho": "rho", "varsigma": "sigma", "varphi": "phi"})

GREEK_NAMES = GREEK_BASE | set(GREEK_ALIAS)

# 拉丁词元音（含 y，避免 rhythm / syzygy 被误判为碎片）
VOWELS = set("aeiouy")

FORMULA_TOKEN_RE = re.compile(r"\\([a-zA-Z]+)|([a-zA-Z])(?:\s*_\s*\{?([0-9a-zA-Z])\}?)?")

REF_HEADINGS = TAIL_CUT_HEADINGS


# ── 读取源 ──────────────────────────────────────────────────────────────
def _poly_top(poly):
    try:
        return float(poly[1])
    except Exception:
        return 0.0


def _poly_left(poly):
    try:
        return float(poly[0])
    except Exception:
        return 0.0


def page_blocks(path):
    """返回该页 text 块，按阅读顺序（Y 再 X）。"""
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    out = []
    for t in d.get("text", []) or []:
        s = (t.get("text") or "").strip()
        if not s:
            continue
        poly = t.get("poly") or [0, 0]
        out.append((_poly_top(poly), _poly_left(poly), s))
    out.sort()
    return [s for _, _, s in out], (d.get("formulas") or [])


def _is_noise(line, chapter_title_words):
    s = line.strip()
    if not s:
        return True
    low = s.lower()
    # 孤立页码 / 纯数字
    if re.fullmatch(r"[\d\s]+", s):
        return True
    # 版权 / 出版
    if re.search(r"(©|copyright|published by|springer|all rights reserved)", low):
        return True
    # 作者机构 / 邮箱 / 致谢基金
    if re.search(r"(@|e-mail|e mail|university|department|institute|laboratory|ac\.jp|\.edu)", low):
        return True
    if re.search(r"(acknowledg|supported by|funded by|grant no|contract no|fellowship)", low):
        return True
    # 页眉：与章标题高度重合的短行
    if len(s) < 90 and chapter_title_words:
        ws = set(re.findall(r"[A-Za-z]{4,}", low))
        if ws and len(ws & chapter_title_words) / max(1, len(ws)) > 0.6:
            return True
    return False


def _cut_references(lines, extra_headings=()):
    """从**第一个**尾部非内容小节标题处截断（参考文献 / 致谢 / 基金 / 合规声明）。"""
    heads = tuple(sorted(set(h.lower() for h in list(REF_HEADINGS) + list(extra_headings)),
                         key=len, reverse=True))
    n = len(lines)
    tail = int(n * 0.75)          # 只认章末 25% 内的标题，避免句中 "Reference [1] shows…" 误切
    for i, s in enumerate(lines):
        t = s.strip().lstrip("0123456789. ").strip().lower()
        for h in heads:
            if not (t == h or t.startswith(h + " ") or t.startswith(h + ":")):
                continue
            standalone = (t == h)                # 整行就是标题：任何位置都认
            if standalone or i >= tail:
                return lines[:i]
    return lines


def dehyphenate(lines):
    r"""合并 OCR 断词：行尾是 `字母-` 时与下一行直接拼接（opera-\ntor → operator）。

    不做这步会产生大量 `koop` / `lator` / `chronization` 之类的假词，
    把术语覆盖率变成噪声（Koopman Operator 实测 term_cov 一度被压到 0.24）。
    """
    out, buf = [], ""
    for s in lines:
        s = s.strip()
        if not s:
            if buf:
                out.append(buf)
                buf = ""
            continue
        if re.search(r"[A-Za-z]-\s*$", s):
            buf += re.sub(r"-\s*$", "", s)
            continue
        out.append(buf + s)
        buf = ""
    if buf:
        out.append(buf)
    return out


def load_chapter_map(extract_dir):
    r"""归一化章节记录：`[{ch:int, name, name_en, start, end}, …]`。

    on-disk 存在两种形态（A `{"chapters":[...]}` / B `{"1":{…}}`），统一走
    `data.chapter_map.chapter_map.load_chapter_records`，避免只认其一而在
    另一形态上直接 "chapter N not found"（Kreyszig / Leinster 等书是 B 形态）。
    """
    from data.chapter_map.chapter_map import load_chapter_records
    out = []
    for c in load_chapter_records(os.path.join(extract_dir, "chapter_map.json")):
        try:
            n = int(str(c.get("ch")).strip())
        except (TypeError, ValueError):
            continue
        out.append({"ch": n, "name": c.get("name", ""),
                    "name_en": c.get("name_en", ""),
                    "start": c.get("start"), "end": c.get("end")})
    return out


def chapter_source(extract_dir, ch, start, end, extra_headings=()):
    lines, formulas = [], []
    for p in range(start, end + 1):
        fp = os.path.join(extract_dir, "page_%03d.json" % p)
        if not os.path.exists(fp):
            continue
        bl, fm = page_blocks(fp)
        lines.extend(bl)
        formulas.extend(f.get("latex") or "" for f in fm)
    return lines, formulas


def chapter_title_words(chapters, ch):
    """章标题特征词（中英两个字段都取），用于识别页眉噪声行。"""
    for c in chapters:
        if c.get("ch") == ch:
            text = "%s %s" % (c.get("name", ""), c.get("name_en", ""))
            return set(w.lower() for w in re.findall(r"[A-Za-z]{4,}", text))
    return set()


# ── 指标 ────────────────────────────────────────────────────────────────
def latex_symbol_freqs(latex_list):
    """符号 → 在整章公式中的出现次数（每条公式内先去重，避免同一式堆叠计数）。"""
    from collections import Counter
    c = Counter()
    for lat in latex_list:
        if lat:
            c.update(latex_symbols([lat]))
    return c


def strip_display_math(md):
    return re.sub(r"\$\$.*?\$\$", " ", md, flags=re.S)


def content_words(text, cjk=True):
    """内容词：剔停用词 + 常见英语词（只留像"专业/内容词"的 token）。

    同时产出每个含连字符词的「去连字符」副本（如 `phase-amplitude` →
    `phaseamplitude`），使摘要侧正确书写的连字符复合词能与源侧 OCR 误连写
    的同一词（`phaseamplitude`）对齐——否则只因排版连字符差异就扣分，属
    假阴性。源侧与摘要侧对称处理，不会制造假阳性。
    """
    raw = [w.lower() for w in WORD_RE.findall(text)]
    ws = [w for w in raw if w not in STOP and w not in COMMON]
    joined = [w.replace("-", "") for w in raw if "-" in w and w not in STOP and w not in COMMON]
    ws += joined
    if cjk:
        ws += [c for c in CJK_RE.findall(text) if c not in CJK_STOP]
    return ws


def is_ocr_fragment(word):
    r"""OCR 碎片启发式（只对拉丁词生效）：无元音 / 5+ 辅音连缀 / 三连重复字符。

    公式区被当作正文识别时会吐出 `rnxm` `iiii` `eike` 这类碎片，它们天然是
    hapax，若计入分母就等于要求总结"复述 OCR 错字"——与 V-P 第 1 条
    「剔除 OCR 噪声」直接冲突。故术语分母显式排除之。
    """
    if len(word) < 4 or not word.isascii():
        return False
    w = word.lower()
    if not (set(w) & VOWELS):
        return True
    run = 0
    for c in w:
        run = run + 1 if c not in VOWELS else 0
        if run >= 5:
            return True
    return bool(re.search(r"(.)\1\1", w))


def rare_terms(src_words, rare_max, rare_min=2):
    """术语分母 = 源频落在 [rare_min, rare_max] 且非 OCR 碎片的内容词。

    为什么有下界 rare_min（默认 2）：源频 = 1 的 hapax 在 OCR 书上绝大多数是
    识别错字或断词残留（实测 Koopman 全书 2600 个 missing term 中 87% 是
    hapax），要求总结复述 80% 的 hapax 等价于要求逐字照抄原书，与
    writing-rules「严禁照抄 OCR 文本流」冲突。真正的章内术语几乎总会出现
    2 次以上，故默认只统计出现 2–3 次的稀有词。
    """
    from collections import Counter
    cnt = Counter(src_words)
    return [w for w, n in cnt.items()
            if rare_min <= n <= rare_max and not is_ocr_fragment(w)]


# 字体 / 重音命令：包裹一个变量（如 `\mathbf{L}_i`、`\bar{x}_i`），其右花括号
# 会把「基字母」与「下标」切开，导致正则只抓到裸字母、下标被当成独立碎片。
# 比对前先把这些命令连同其花括号一起脱掉，保留内部内容（如 `\mathbf{L}_i`
# → `L_i`），使基字母与下标重新贴合。嵌套花括号（极少见）不在覆盖范围内。
_FONT_ACCENT = re.compile(
    r"\\(?:mathbf|boldsymbol|bm|mathsf|mathtt|mathit|mathrm|mathnormal|"
    r"mathfrak|mathscr|mathbfit|vec|bar|tilde|hat|dot|ddot|overline|"
    r"widehat|widetilde|check|breve|acute|grave)\s*\{([^{}]*)\}")

def _unwrap_font(s):
    return _FONT_ACCENT.sub(r"\1", s)


def latex_symbols(latex_list):
    """从源公式抽取数学对象符号（去重）。

    只保留：希腊字母、长度 ≥3 且非结构/样式/算符/关系命令的具名命令、
    以及带下标的裸标识符。字体开关（`\\bf` `\\rm`）、关系符（`\\le` `\\ne`）、
    函数（`\\ln` `\\arg`）一律不算数学对象。

    注意：先用 `_unwrap_font` 脱掉字体/重音命令的外壳，否则
    `\\mathbf{L}_i` 会被切成裸 `L` + 下标 `i` 两截，使摘要侧几乎所有
    「粗体下标符号」都被误判为缺失（源侧多为无粗体的 `L_i`）。
    """
    syms = set()
    for lat in latex_list:
        if not lat:
            continue
        lat = _unwrap_font(lat)
        for m in FORMULA_TOKEN_RE.finditer(lat):
            cmd, bare, sub = m.group(1), m.group(2), m.group(3)
            if cmd:
                canon = GREEK_ALIAS.get(cmd, cmd)
                if canon in GREEK_BASE:
                    syms.add("\\" + canon)
                    continue
                # 短命令（≤2 字母）只可能是字体/关系/函数缩写，不是数学对象
                if len(cmd) <= 2:
                    continue
                if cmd in LATEX_STRUCT or cmd in LATEX_STYLE \
                        or cmd in LATEX_OPERATORS or cmd in LATEX_RELATIONS \
                        or cmd in LATEX_DELIM:
                    continue
                syms.add("\\" + canon)
            elif bare:
                syms.add(bare + ("_" + sub if sub else ""))
    return syms


def latex_symbols_in_md(md):
    """md 中出现的符号集合（含 $...$ 内联与 $$ 块）。"""
    spans = re.findall(r"\$\$.*?\$\$", md, flags=re.S) + re.findall(r"\$[^$\n]+\$", md)
    return latex_symbols(spans)


def _cjk_ratio(text):
    if not text:
        return 0.0
    return len(re.findall(r"[\u4e00-\u9fff]", text)) / len(text)


def _find_source_md(md_path, ch):
    """在同目录找同章的源语言 md（`Chapter<N>_*.md`）。"""
    d = os.path.dirname(os.path.abspath(md_path))
    if not os.path.isdir(d):
        return None
    pat = re.compile(r"^Chapter0*%d_.*\.md$" % int(ch))
    for fn in sorted(os.listdir(d)):
        if pat.match(fn):
            return os.path.join(d, fn)
    return None


def evaluate(extract_dir, md_path, ch, thresholds, rare_max=3, rare_min=2,
             sym_min=2):
    chapters = load_chapter_map(extract_dir)
    meta = next((c for c in chapters if c.get("ch") == ch), None)
    if meta is None:
        raise SystemExit("[coverage_gate] chapter %s not in chapter_map.json" % ch)

    ov_path = os.path.join(extract_dir, "coverage_gate_overrides.json")
    extra = ()
    if os.path.exists(ov_path):
        with open(ov_path, encoding="utf-8") as f:
            extra = tuple(json.load(f).get("skip_headings", ()))

    tw = chapter_title_words(chapters, ch)
    raw_lines, formulas = chapter_source(extract_dir, ch, meta["start"], meta["end"])
    lines = _cut_references(dehyphenate([s for s in raw_lines if not _is_noise(s, tw)]), extra)

    with open(md_path, encoding="utf-8") as f:
        md = f.read()

    src_text = " ".join(lines)

    # 译文口径：源非中文而 md 是中文 → 词表语言不通，覆盖度不可直接对 OCR 源测
    # （实测会把 term_cov 压到 0.01–0.13 这类恒红假灯）。改测同章源语言母版；
    # 译文本身与母版的 1:1 同构由 check_translate_parity 把关。
    eval_md, translated = md_path, False
    if _cjk_ratio(md) >= 0.15 and _cjk_ratio(src_text) < 0.15:
        alt = _find_source_md(md_path, ch)
        if alt:
            eval_md, translated = alt, True
            with open(alt, encoding="utf-8") as f:
                md = f.read()

    na = (translated is False and _cjk_ratio(md) >= 0.15
          and _cjk_ratio(src_text) < 0.15)
    if na:
        ratio = term_cov = var_cov = None
        mw, sw, terms, src_syms = [], [], [], set()
    else:
        md_text = strip_display_math(md)
        sw = content_words(src_text)
        mw = content_words(md_text)
        mset = set(mw)

        ratio = len(mw) / len(sw) if sw else 0.0

        terms = rare_terms(sw, rare_max, rare_min)
        t_hit = [t for t in terms if t in mset]
        term_cov = len(t_hit) / len(terms) if terms else 1.0

        # 符号分母同 rare_min 口径：整章只出现 1 次的符号（多为 OCR 一次性
        # 误识或孤立排版件）不计入分母，避免用单个噪声符号卡住整章。
        src_syms = {s for s, n in latex_symbol_freqs(formulas).items()
                    if n >= sym_min}
        md_syms = latex_symbols_in_md(md)
        var_cov = len(src_syms & md_syms) / len(src_syms) if src_syms else 1.0

    from collections import Counter
    cnt = Counter(sw)
    n_hapax = sum(1 for _, n in cnt.items() if n < rare_min)
    n_frag = sum(1 for w, n in cnt.items()
                 if rare_min <= n <= rare_max and is_ocr_fragment(w))

    def _ok(v, th):
        return True if v is None else v >= th

    res = {
        "chapter": ch,
        "md": os.path.basename(md_path),
        "eval_md": os.path.basename(eval_md) if eval_md else "",
        "translated": translated,
        "na": na,
        "src_words": len(sw),
        "md_words": len(mw),
        "ratio": None if ratio is None else round(ratio, 3),
        "terms": len(terms),
        "term_cov": None if term_cov is None else round(term_cov, 3),
        "vars": len(src_syms),
        "var_cov": None if var_cov is None else round(var_cov, 3),
        "hapax_dropped": n_hapax,
        "ocr_frag_dropped": n_frag,
        "pass": (_ok(ratio, thresholds["ratio"])
                 and _ok(term_cov, thresholds["term"])
                 and _ok(var_cov, thresholds["var"])),
        "thresholds": dict(thresholds),
        "missing_terms": sorted(t for t in terms if t not in set(mw)),
        "missing_vars": sorted(src_syms - latex_symbols_in_md(md)) if not na else [],
    }
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="反过度精简闸门：压缩比 / 术语覆盖率 / 变量覆盖率")
    ap.add_argument("extract_dir")
    ap.add_argument("chapter_md", nargs="?", help="章节 md 路径；与 --all 二选一")
    ap.add_argument("chapter_no", nargs="?", type=int)
    ap.add_argument("--all", metavar="BOOK_DIR",
                    help="批量：扫描 BOOK_DIR 下 Chapter<N>_*.md 或 第N章_*.md")
    ap.add_argument("--scheme", choices=("en", "cn"), default="en")
    ap.add_argument("--ratio", type=float, default=0.55)
    ap.add_argument("--term", type=float, default=0.80)
    ap.add_argument("--var", type=float, default=0.85)
    ap.add_argument("--rare-max", type=int, default=3,
                    help="术语词频上界（默认 3）")
    ap.add_argument("--rare-min", type=int, default=2,
                    help="术语词频下界（默认 2）：源频=1 的 hapax 在 OCR 书上"
                         "绝大多数是识别错字，不计入分母")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--show-missing", type=int, default=0, metavar="N")
    a = ap.parse_args(argv)

    th = {"ratio": a.ratio, "term": a.term, "var": a.var}

    if a.all:
        pat = re.compile(r"^Chapter(\d+)_.*\.md$" if a.scheme == "en"
                         else r"^第(\d+)章_.*\.md$")
        jobs = []
        for fn in sorted(os.listdir(a.all)):
            m = pat.match(fn)
            if m:
                jobs.append((int(m.group(1)), os.path.join(a.all, fn)))
        if not jobs:
            print("[coverage_gate] no chapter md matched in %s" % a.all, file=sys.stderr)
            return 2
    else:
        if not a.chapter_md or a.chapter_no is None:
            print("[coverage_gate] need <chapter_md> <chapter_no>, or --all <book_dir>",
                  file=sys.stderr)
            return 2
        jobs = [(a.chapter_no, a.chapter_md)]

    results = []
    for ch, md_path in jobs:
        try:
            results.append(evaluate(a.extract_dir, md_path, ch, th,
                                    a.rare_max, a.rare_min))
        except FileNotFoundError as e:
            print("[coverage_gate] %s" % e, file=sys.stderr)
            return 2

    if a.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        def f2(v):
            return "n/a " if v is None else "%.2f" % v

        verdict = lambda r: ("N/A" if r["na"] else ("PASS" if r["pass"] else "FAIL"))

        print("%-4s %-9s %-8s %-8s %-8s %-8s %-8s %s" % (
            "ch", "md", "src_w", "md_w", "ratio", "term_cov", "var_cov", "verdict"))
        print("-" * 78)
        for r in results:
            print("%-4d %-9s %-8d %-8d %-8s %-8s %-8s %s" % (
                r["chapter"], r["md"][:9], r["src_words"], r["md_words"],
                f2(r["ratio"]), f2(r["term_cov"]), f2(r["var_cov"]), verdict(r)))
            if r["translated"]:
                print("      ^ 译文：指标以源语言母版 %s 计（译文同构由 "
                      "check_translate_parity 把关）" % r["eval_md"])
            if a.show_missing:
                print("      术语分母=%d（剔除 hapax %d / OCR 碎片 %d）" % (
                    r["terms"], r["hapax_dropped"], r["ocr_frag_dropped"]))
                if r["missing_terms"]:
                    print("      missing terms (%d): %s" % (
                        len(r["missing_terms"]),
                        " ".join(r["missing_terms"][:a.show_missing])))
                if r["missing_vars"]:
                    print("      missing vars (%d): %s" % (
                        len(r["missing_vars"]),
                        " ".join(r["missing_vars"][:a.show_missing])))
        n_fail = sum(1 for r in results if not r["pass"] and not r["na"])
        n_na = sum(1 for r in results if r["na"])
        if len(results) > 1:
            def avg(key):
                vs = [r[key] for r in results if r[key] is not None]
                return sum(vs) / len(vs) if vs else float("nan")

            print("-" * 78)
            print("AVG ratio=%.2f term=%.2f var=%.2f   FAIL=%d/%d%s" % (
                avg("ratio"), avg("term_cov"), avg("var_cov"),
                n_fail, len(results),
                "   N/A=%d" % n_na if n_na else ""))

    return 0 if all(r["pass"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
