r"""tag_formula_pairing.py — Q 层「印面标签 ↔ 展示式正文」**配对**校验（专判同号配错式）。

为什么需要这一族（Katok《Introduction to the Modern Theory of Dynamical Systems》
ch2 §2.6 / §2.8 / ch4 §4.4 实测，2026-10-03）：

既有 Q 判据全部建立在**编号集合**上——FABRICATED/MISSING 比集合成员、
ORDER_MISMATCH 比首现顺序、MISPLACED 比归属小节；`gate_units` 的契约 tag 对账也是
**章级集合**比较。于是一种缺陷可以一路全绿穿过整条链：

  写手漏贴某一枚印面标签（印面 `(2.6.1)` 那行展示式在交付物里不带 tag），
  随后把后面每一枚 `\tag` **整体错位一格**（印面 `(2.6.2)` 的式子挂成 `\tag{2.6.1}`），
  末了再给印面**无号**的展示式贴上一枚号补齐集合。

章级集合仍是完整的、顺序仍单调、归属仍对——**没有任何一条既有判据会响**，
只有当某枚号被贴到**别的章节**（本书 `\tag{2.6.5}` 孤儿挂在 §2.8）时才偶然露出一条
MISPLACED。交付物里的正文与编号却是错配的，读者按号检索会取到错的式子。

本模块把「号」和「式」重新钉在一起：以 `page_*.json` 构造书侧真值账
`印面标签 -> 该标签所在行的展示式 latex`，再与总结里
`$$ ... \tag{X} ... $$` 的正文做**归一化**相似度对账，只有当
「正文高度匹配**另一个**印面号（≥ `hi`）且**不**匹配自己那个号」时才开报——
即「配错号」；两边都配不上属内容改写（散文式重排、Tier 压缩），本族**不判**，
宁缺勿滥。

判据取向：
  * **只可能少报，不会多报**：无书侧账（`len(printed) < 3`）、总结号在书里查无载体
    （`known_book` / 抽取漏收，MISSING 一支已管）、正文过短（归一化 < `min_body`
    字符，`(1)` 型 trivial 式）、**正文只剩箭头/堆叠命令骨架**（`connector_share`
    ≥ 0.5，Leinster 交换图族）一律跳过——与 Q 层既有的「无证据不判」同一约定。
  * **降级为 WARN、不阻断**（`q_tag_mismatch`）：新缺陷族先取证不先执法，跨 51 书
    普查校准阈值后再议是否升级。
"""
import os
import re
import difflib
from typing import Dict, List, Optional, Set, Tuple

from page_json import PageJson
from lib.page_dir import resolve_page_dir
from lib.numbering import formula_num_core

from formula_tag import (SourceFormulaIndex, _tail_pre_guard,
                         formula_latex_text)


# 总结侧：一个 `$$ ... $$` 展示块 + 其中的 `\tag{...}`
_BLOCK_RE = re.compile(r'\$\$(.*?)\$\$', re.S)
_TAG_RE = re.compile(r'\\tag\s*\{([^}]*)\}')

# 印面侧标签块：整块就是一枚带括号的编号（`(2.6.1)` / `（2.6.1）`，可带尾随句点）
# 🔴 形状核与 `lib.numbering.formula_num_core` 同源（与 build_formula_patterns /
# attach_content / 完整性闸门一个口径），段数由本书 `formula.type` 决定。
# 🔴 这三个是**模板串**（`%s` 处填编号核），不是已编译正则——编译在
# `printed_tag_bodies` 里按本书 ncomp 现做。
_LAB_ALONE = r'^\s*[（(]\s*(%s)\s*[）)]\s*[.。]?\s*$'
_LAB_TAIL = r'[（(]\s*(%s)\s*[）)]\s*[.。]?\s*$'
_LAB_HEAD = r'^\s*[（(]\s*(%s)\s*[）)]\s*'

# 页内标签与展示式的垂直配对窗口（源图 DPI 像素）：右缘标签通常与其式子**同行**，
# 但 OCR 的多行 array 会把式子拉高，故留 80px。同页多枚标签时，每条展示式行只归
# **最近的那枚号**所有（见 `printed_tag_bodies` 里的 Voronoi 归属），不再用固定
# 并窗——旧并窗会让相邻两枚号拿到逐字相同的两个账身，账本对自己失去判别力。
_LABEL_MATCH_DX = 80.0

# 🔴 文字行尾标签（形态④）的垂直配对窗口，比上面**紧得多**：只有当这条 OCR 文字行
# 本身就是那行公式的转写时，行尾的 `(N.M.K)` 才是**这行的号**。散文回指（"using
# (20.5.1) yields"）虽也以号结尾，但它所在行不与任何展示式同行，故被这个窄窗挡掉。
_GLUED_TEXT_LABEL_DY = 20.0

# 数学串归一化：OCR 侧与交付侧的唯一可比形态。
# ① 去掉排版壳命令（`\mathrm{Id}` 与 `\operatorname{Id}` 必须折成同一个 `id`）；
# ② 去掉**一切**非字母数字（空格/花括号/`\`/运算符/中文标点全消），因为 OCR 的
#    `{ \lambda ^ { 2 } }` 与手写的 `\lambda^{2}` 只差在空白与括号；
# ③ 小写。
# 🔴 定界符**尺寸命令族必须列全**（real-analysis ch14 (14.6) 实测，2026-10-03）：
# 旧写法 `big|Big|bigg|Bigg` 后面跟 `\b`，遇到 `\biggl\{` 时 `big` 与 `gl` 之间没有
# 词边界 → 整条不剥，书侧串凭空多出 `biggl` 五个字母，把本来 r=1.00 的自身匹配压到
# 0.79（差 0.01 就越过 `hi` 误报）。按「长名在前」重排，`l/r/m` 与星号变体一并覆盖。
_SHELL_CMDS = re.compile(
    r'\\(?:mathrm|text|textrm|textnormal|operatorname|mathbf|boldsymbol|emph|'
    r'ensuremath|mathit|mathsf|mathtt|pmb|bm|displaystyle|scriptstyle|textstyle|'
    r'stystyle|limits|colon|quad|'
    r'qquad\\*|;|,|!|nonumber|notag)\b\s*|'
    r'\\(?:Biggl|Biggr|biggl|biggr|Biglm|Bigrm|biglm|bigrm|Bigl|Bigr|bigl|bigr|'
    r'Bigg|bigg|Big|big|left|right)\b\s*|'
    r'\\(?:left|right)?[.,;:!]\s*')
# 🔴 排版环境壳必须整体剥掉（Katok §2.6 实测）：OCR 把「两行共用一个编号」的
# 显示式存成一条 `\begin{array}{r} 行1 \\ 行2 \end{array}`，交付侧同一条式子却常写成
# 裸的两行。留着 `beginarrayr`/`endarray` 这 15 个字符会把本来**逐字相同**的正文
# 稀释到 r=0.78（差 0.02 就漏报）。环境名与其对齐参数（`{r}`/`{lllll}`/`{rl}`）
# 都是纯排版信息，两侧同剥不影响任何数学内容。
_ENV_SHELL = re.compile(
    r'\\(?:begin|end)\s*\{[a-zA-Z*]+\}\s*(?:\{[^{}]*\}\s*)?')
_NON_ALNUM = re.compile(r'[^0-9A-Za-z]+')

# 🔴 连字/堆叠命令**词表**（Leinster《Basic Category Theory》ch5 交换图实测，
# 2026-10-03）：OCR 读交换图时把整条展示式写成命令名串，归一化后大部分字符是命令名
# 而不是数学内容——印面 `(5.21)` 读成 `xlongrightarrowatopiotaatopchi`（30 字符里 20
# 个是 `longrightarrow`/`atop`），真内容只剩 `x`/`iota`/`chi` 三个字母。后果是判据的
# 两个前提被**同时颠倒**：
#   * 同一张图换了箭头写法就不像：交付 `\xrightarrow{f_i}` vs 印面
#     `\stackrel{f_i}{\longrightarrow}` → 自身 r=0.67 < `hi`（本应 1.00）；
#   * 两条不同的图被读错后反而很像：交付 `5.15` 对印面 `(5.17)` r=0.85 ≥ `hi`。
# 于是「配错号」在**完全正确**的交付上一路开报（普查里 Leinster 6 行全是这一类）。
# 这种账身/正文不携带任何可比对的数学证据 → 不收账、不判（fail-open，与「账太薄不判」
# 「正文过短不判」同一取向）。词表只收**无歧义的多字符名**：`to`/`over` 这类会撞进
# 普通字母串的词一律不进（Katok 的 `\circ`/`\bigcap`/`\overline` 等实义命令同样不在表内）。
_CONNECTOR_NAMES = (
    'longrightarrowfrom', 'longleftrightarrow', 'longleftarrow', 'longrightarrow',
    'Longrightarrow', 'rightleftharpoons', 'leftrightsquigarrow', 'twoheadrightarrow',
    'twoheadleftarrow', 'dashedrightarrow', 'dashrightarrow', 'dashleftarrow',
    'overrightarrow', 'overleftarrow', 'hookrightarrow', 'hookleftarrow',
    'xleftrightarrow', 'xRightarrow', 'xleftarrow', 'xrightarrow', 'Rightarrow',
    'Leftarrow', 'leftarrow', 'rightarrow', 'leftrightarrow', 'impliedby',
    'squigarrow', 'nearrow', 'searrow', 'swarrow', 'nwarrow', 'uparrow',
    'downarrow', 'mapsto', 'harpoon', 'implies', 'stackrel', 'underset',
    'overset', 'phantom', 'atop', 'xmapsto')
_CONNECTOR = re.compile('|'.join(sorted({n.lower() for n in _CONNECTOR_NAMES},
                                        key=len, reverse=True)))
# 🔴 阈值 0.50 是**测出来的**，不是猜的（51 书全库占比普查，2026-10-03；一次性校准
# 探针按「特定书脚本落该书 `_extract/`」的契约留在
# `代数几何/Leinster2014BasicCategoryTheory/_extract/_q_tm_share_probe.py`，
# 复跑同一命令即可重测分布）：印面账身 n=1182、交付正文 n=2329，p90 均为 0.000；
#   * Katok 全部 42 行开报的 claimed owner 占比**都是 0.000**（真缺陷一侧根本没有
#     箭头词表），阈值取 0.01 与 0.50 对真缺陷毫无差别；
#   * Leinster 6 行假阳的 claimed owner 是 0.550 / 0.909，取 0.50 全部静音；
#   * 0.20~0.50 之间**全是真式子**（Apostol `o(1) as x\to\infty`、real-analysis
#     `n\rightarrow b`、Leinster `a\leq b\;c\implies a<c`、Katok (15.3.1) 等）——
#     阈值一旦降到 0.5 以下就开始丢真证据。故取「命令名占到归一化串**一半及以上**
#     = 除箭头骨架外没有可比内容」这一字面判据（`share >= 0.50` 即排除）。
_CONNECTOR_SHARE_MAX = 0.50


def norm_math(s: str) -> str:
    """latex -> 仅字母数字的小写串（书侧 OCR 与交付侧手写可比的同一形态）。"""
    if not s:
        return ''
    s = _ENV_SHELL.sub(' ', str(s))
    s = _SHELL_CMDS.sub('', s)
    return _NON_ALNUM.sub('', s).lower()


def connector_share(norm: str) -> float:
    """归一化串里被连字/堆叠命令名占住的字符比例（0~1，重叠按最长名优先各计一次）。"""
    if not norm:
        return 0.0
    hit = sum(m.end() - m.start() for m in _CONNECTOR.finditer(norm))
    return hit / float(len(norm))


def _evidence_bearing(norm: str) -> bool:
    """这条归一化正文是否携带可比对的数学内容（箭头词表撑起来的图不算）。"""
    return connector_share(norm) < _CONNECTOR_SHARE_MAX


def _labelcores(ncomp: Optional[int], lead: Optional[str]) -> str:
    """本书公式编号的正则核（不含括号、无捕获组），与 Q 层抽取侧同源。"""
    return formula_num_core(ncomp, lead=lead or 'digit')


def printed_tag_bodies(extract_dir: str, ch, start, end,
                       ncomp: Optional[int] = None,
                       lead: Optional[str] = None
                       ) -> Dict[str, List[str]]:
    r"""书侧真值账：`{印面编号: [该编号所指展示式的 latex, ...]}`。

    四种印面形态都收（与 Q 层 `SourceFormulaIndex` 的形态口径一致）：
      ① 独立标签块 `text[]` 整块 = `(N.M.K)` → 就近挂同页展示式；
      ② 标签并进公式行**尾部**（`… \le M (9)`）→ 式子就是这条 latex 去掉尾号；
      ③ 标签在公式行**开头**（`(4.3)\quad …`，Han–Lin 型）→ 同上；
      ④ 标签并进**整行公式的 OCR 文字转写**尾部（`… i = u, s. (20.5.5)`，Katok 实测）
         → 挂同页与该文字行**同行**（±`_GLUED_TEXT_LABEL_DY`）的展示式。

    同一号多次出现（印面重排/回指）保留**全部**正文，比较时取最优，避免「重印行
    被 OCR 切坏」把真确配错淹没。
    """
    core = _labelcores(ncomp, lead)
    alone_re = re.compile(_LAB_ALONE % core)
    tail_re = re.compile(_LAB_TAIL % core)
    head_re = re.compile(_LAB_HEAD % core)

    out: Dict[str, List[str]] = {}
    pdir = resolve_page_dir(extract_dir, ch)
    for pg in range(int(start), int(end) + 1):
        fp = os.path.join(pdir, f'page_{pg:03d}.json')
        if not os.path.exists(fp):
            continue
        try:
            data = PageJson.load(fp).data
        except Exception:
            continue
        # 该页展示式：(中心 y, latex)；`line_ws` 与之同序，存该行的**水平宽度**
        # （源图 DPI 像素，只用于相对比较，见 `_display_at` 兜底）
        lines: List[Tuple[float, str]] = []
        line_ws: List[float] = []
        for fb in (data.get('formulas') or []):
            lx = formula_latex_text(fb)
            if not lx:
                continue
            bb = (fb.get('bbox') if isinstance(fb, dict) else None) or [0, 0, 0, 0]
            try:
                cy = (float(bb[1]) + float(bb[3])) / 2.0
            except Exception:
                continue
            lines.append((cy, lx))
            try:
                line_ws.append(abs(float(bb[2]) - float(bb[0])))
            except Exception:
                line_ws.append(0.0)
        if not lines:
            continue

        def _record(num_raw: str, body: str) -> None:
            n = SourceFormulaIndex.norm(num_raw)
            if not n:
                return
            body = (body or '').strip()
            nb = norm_math(body)
            if len(nb) < 8:
                return
            # 箭头词表撑起来的交换图 = 没有可比内容，不进账（见 `_CONNECTOR_NAMES`）
            if not _evidence_bearing(nb):
                return
            out.setdefault(n, [])
            if body not in out[n]:
                out[n].append(body)

        # 🔴 先收集本页所有**独立标签块**的 y，再按「最近标签」把每条展示式行分给
        # 唯一一枚号（Voronoi，±`_LABEL_MATCH_DX` 内才认领）。旧实现是「取最近一条
        # 行再并 ±25px 邻行」，于是**相邻两枚号各自把对方的行也并了进来**：Katok
        # p109 的 (2.6.4)/(2.6.5) 两行 array 因此得到两个**逐字相同**的账身，账本
        # 对自己没有判别力，任何「配错号」结论都站不住（普查里 Leinster 的
        # ch5 (5.17) 亦是同一形态）。
        label_ys: List[Tuple[float, str]] = []
        for b in (data.get('text') or []):
            txt = ((b.get('text') if isinstance(b, dict) else '') or '').strip()
            if not txt or len(txt) > 40:
                continue
            m = alone_re.fullmatch(txt)
            if not m:
                continue
            poly = (b.get('poly') if isinstance(b, dict) else None) or []
            if len(poly) < 8:
                continue
            label_ys.append(((float(poly[1]) + float(poly[7])) / 2.0, m.group(1)))

        def _display_at(y: float) -> str:
            """挂在标签窗口内的展示式：只收归本号（最近标签）所有的行，逐字重复行并一次。"""
            cands = [(abs(cy - y), i) for i, (cy, _l) in enumerate(lines)
                     if abs(cy - y) <= _LABEL_MATCH_DX]
            if not cands:
                return ''
            # 只收**归本号所有**的行：某行若离另一枚标签更近，那是别人的式子。
            owned = []
            for i, (cy, _l) in enumerate(lines):
                if abs(cy - y) > _LABEL_MATCH_DX:
                    continue
                owner = min(label_ys, key=lambda ly: abs(ly[0] - cy))
                if abs(owner[0] - cy) <= abs(y - cy):
                    continue
                owned.append(lines[i][1])
            if not owned:
                # 🔴 兜底取「最近的一条行」时，先把**碎片行**让开（Katok p669 (20.5.7)
                # 实测，2026-10-03）：右缘号与式子之间常夹着 OCR 拆出的短碎片
                # （`i = u , s`、`\dot { \epsilon }` 这类紧跟其后的散文行内式），
                # 逐字最近的就是碎片 → 账身只有几个字符 → 该号在书侧**没有像样载体**，
                # 配错号读不出来。两级筛选（都是「相对窗口内其他行」的比值，不动绝对
                # 阈值，故对窄栏/宽栏的书都同口径）：① 归一化后仍有内容（≥8 字符）；
                # ② 水平宽度 ≥ 窗口最宽行的 50%（展示式必然比行内碎片宽）。两级筛完
                # 仍空才退回旧行为（取最近一条）。
                subst = [(d, i) for d, i in cands
                         if len(norm_math(lines[i][1])) >= 8] or cands
                widest = max(line_ws[i] for _d, i in subst)
                wide = [(d, i) for d, i in subst if line_ws[i] >= 0.5 * widest]
                _d, anchor = min(wide or subst)
                owned = [lines[anchor][1]]
            # 🔴 同一条**逐字重复**的行不并第二次（Arnold 经典力学 ch9 实测，
            # 2026-10-03）：OCR 把同一行公式重复输出（raw-latex 双检），并窗把重复
            # 行也拼进账身 → 书侧串长一倍 → r_self 系统性偏低 → 明明配对了自己
            # 的条目反被读成「配错号」。归一化相同即视为同一行。
            joined: List[str] = []
            seen_lines: Set[str] = set()
            for lx in owned:
                key = norm_math(lx)
                if key and key in seen_lines:
                    continue
                seen_lines.add(key)
                joined.append(lx)
            return ' '.join(joined)

        # ① 独立标签块
        for y, num_raw in label_ys:
            body = _display_at(y)
            if body:
                _record(num_raw, body)

        # ②③ 标签并进 latex
        for cy, lx in lines:
            mt = tail_re.search(lx)
            if mt and _tail_pre_guard(lx[:mt.start()]):
                _record(mt.group(1), lx[:mt.start()] + ' ' + lx[mt.end():])
                continue
            mh = head_re.match(lx)
            if mh:
                _record(mh.group(1), lx[mh.end():])

        # ④ 标签并进 **OCR 文字行**尾部（Katok p669 (20.5.5)/(20.5.6) 实测，
        # 2026-10-03）：印面右缘的号被 OCR 连同整行公式一起输出一条长 text 行
        # （`… i = u, s. (20.5.5)`）。旧账只认 latex 侧的尾号（形态②），文字行形态
        # 一律漏收 → 该号在书侧账里**没有载体**，「同号配错式」读不出（MISSING 也只
        # 看到印面无此号）。判据三条全中才收：行长 >40（不是独立标签块，那种走形态①）
        # + 去掉行尾标点后正好以该号结尾 + 同页有一条展示式的中心 y 落在该行 y
        # ±`_GLUED_LABEL_DY`（窄窗=「这行就是那行公式的转写」，散文回指不满足）。
        # 🔴 不进 `label_ys`：形态①的 Voronoi 归属口径一字不动，这里只**追加**账身。
        for b in (data.get('text') or []):
            txt = ((b.get('text') if isinstance(b, dict) else '') or '').strip()
            if not txt or len(txt) <= 40:
                continue
            poly = (b.get('poly') if isinstance(b, dict) else None) or []
            if len(poly) < 8:
                continue
            mg = tail_re.search(txt.rstrip(' \t.,;:'))
            if not mg:
                continue
            gy = (float(poly[1]) + float(poly[7])) / 2.0
            near = [lx for cy, lx in lines if abs(cy - gy) <= _GLUED_TEXT_LABEL_DY]
            if not near:
                continue
            seen_glued: Set[str] = set()
            joined_glued: List[str] = []
            for lx in near:
                key = norm_math(lx)
                if key and key in seen_glued:
                    continue
                seen_glued.add(key)
                joined_glued.append(lx)
            _record(mg.group(1), ' '.join(joined_glued))
    return out


def summary_tag_bodies(md_file: str) -> List[Tuple[str, str]]:
    """交付侧：`[(归一化编号, 该 `$$` 块去掉 `\tag` 后的正文), ...]`（文档序）。"""
    try:
        with open(md_file, encoding='utf-8') as f:
            md = f.read()
    except Exception:
        return []
    out: List[Tuple[str, str]] = []
    for block in _BLOCK_RE.finditer(md):
        mtag = _TAG_RE.search(block.group(1))
        if not mtag:
            continue
        n = SourceFormulaIndex.norm(mtag.group(1))
        if not n:
            continue
        body = (block.group(1)[:mtag.start()] + ' '
                + block.group(1)[mtag.end():])
        out.append((n, body))
    return out


def _ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def pairing_problems(extract_dir: str, ch, start, end, md_file: str,
                     ncomp: Optional[int] = None,
                     ignore: Optional[Set[str]] = None,
                     lead: Optional[str] = None,
                     hi: float = 0.80,
                     min_body: int = 12,
                     printed: Optional[Dict[str, List[str]]] = None
                     ) -> List[dict]:
    r"""总结里「正文与编号配错」的行（非阻断 WARN 族 `q_tag_mismatch`）。

    开报条件（四条同时成立）：
      * 总结某块 `\tag{n}` 的正文 `b`，对书侧**另一号** `m != n` 的最大相似度 ≥ `hi`；
      * 对**自己那号** `n` 的最大相似度 < `hi`（或书侧根本没有 `n` 的载体——那一支
        由 MISSING 负责，这里只在 `n` 有载体时判，否则 `b` 无从比较）；
      * `len(norm_math(b)) >= min_body`（trivial 式子不配）；
      * 🔴 **对手号归属仲裁**：`b` 对 `(m)` 的匹配必须**高过总结自己贴在 `(m)`
        那一格上的正文**对 `(m)` 的匹配。真移位时 `(m)` 那一格装的是 `(m-1)` 的
        式子，必然低分，故不误伤；反之若 `(m)` 那一格本来就配对了，说明 `b` 与
        印面 `(m)` 相符只是「同式两印 / 同骨架短式互冒充 / 书侧账被 OCR 污染」，
        属假阳（51 书普查实测：Apostol 16 行 + Arnold 7 行 + real-analysis 2 行 +
        Leinster 2 行**全**为此类，此一支即抑制其中 8/9，且 Katok 真移位一行不少）。

    单分量编号书（`ncomp == 1`，形如 `(9)`）**整体不判**：这类书按节重启编号，同一
    式子在不同节各印一次、骨架相同的短式（`\sum \square`、`n^s`、同余式族）彼此
    互为「高匹配的另一号」——实测 Arnold 经典力学 7/7、Apostol 16/16 全为假阳，
    且无一条真缺陷可用来标定阈值，故宁缺勿滥（`q_tag_mismatch` 对该形态直接返回空）。

    箭头/堆叠命令占归一化正文一半以上的条目（交换图被 OCR 读成命令名串）两侧都**不
    进账也不判**——判据的两个前提在那种页面上会被同时颠倒（见 `_CONNECTOR_NAMES`）。

    `ignore`（Q 层已合并的全局 + 章级 `ignore_ch{N}.json` 键）里的号一律跳过。
    返回行与 Q 层其他族同形：`number / status / summary_latex / source_text`。
    """
    if ncomp == 1:
        return []
    if printed is None:
        printed = printed_tag_bodies(extract_dir, ch, start, end, ncomp, lead)
    # 书侧账太薄 = 抽取没建立可比真值（老 OCR 页 / 无编号书 / 段数配错），
    # 此时任何「配错」结论都没有根据 —— 无证据不判。
    if len(printed) < 3:
        return []
    ign: Set[str] = set()
    for k in (ignore or set()):
        nn = SourceFormulaIndex.norm(str(k).split('#')[-1])
        if nn:
            ign.add(nn)
    summary = summary_tag_bodies(md_file)
    carrier: Dict[str, str] = {}          # 号 -> 总结贴在它那一格上的正文（首现）
    for n_, b_ in summary:
        carrier.setdefault(n_, b_)
    rows: List[dict] = []
    seen: Set[str] = set()
    for n, body in summary:
        if n in ign or n in seen:
            continue
        nb = norm_math(body)
        if len(nb) < min_body:
            continue
        if not _evidence_bearing(nb):
            continue        # 交付侧同样是「只剩箭头骨架」的图：无证据不判
        own = printed.get(n)
        if not own:
            continue                      # 书侧无载体 → MISSING 一支已管，此处不判
        self_r = max(_ratio(nb, norm_math(p)) for p in own)
        if self_r >= hi:
            continue                      # 配上自己 = 正常
        best_m, best_r = None, 0.0
        for m, bodies in printed.items():
            if m == n or m in ign:
                continue
            r = max(_ratio(nb, norm_math(p)) for p in bodies)
            if r > best_r:
                best_m, best_r = m, r
        if best_m is None or best_r < hi:
            continue                      # 哪边都配不上 = 内容改写，本族不判
        # 🔴 **账本判别力闸**： claimed owner `(best_m)` 的印面正文若与**别的印面号**
        # 也高度相似，那本账对 `(best_m)` 就没有判别力——「b 像 (m)」不构成「b 属于
        # (m)」的证据（Leinster ch5 实测：交换图被 OCR 读成 `xlongrightarrowatopiotaatop`
        # 一类的乱码串，归一化后 20/26 个字符是箭头命令名，任两张图之间都能配到
        # 0.83-0.85；Apostol 的同骨架短式族同理）。无证据不判，与账太薄 / 过短两支
        # 同一约定。
        claim = max((norm_math(p) for p in printed[best_m]),
                    key=lambda pm: _ratio(nb, pm), default='')
        if any(_ratio(claim, norm_math(p)) >= hi
               for m2, bodies in printed.items()
               if m2 != best_m for p in bodies):
            continue
        # 🔴 归属仲裁：`(best_m)` 那一格自己配得好 = `b` 只是「另一个长得像的式子」
        holder = carrier.get(best_m)
        holder_r = 0.0
        if holder is not None and holder is not body:
            hn = norm_math(holder)
            if len(hn) >= min_body:
                holder_r = max(_ratio(hn, norm_math(p)) for p in printed[best_m])
        if best_r <= holder_r:
            continue
        seen.add(n)
        rows.append({
            'number': n,
            'status': 'TAG_MISMATCH',
            'summary_latex': (body or '').strip()[:60],
            'source_text': (f'正文与印面 ({best_m}) 相符 r={best_r:.2f}，'
                            f'与自己的 ({n}) 不符 r={self_r:.2f}'
                            + (f'（而总结贴在 ({best_m}) 的正文对 ({best_m}) '
                               f'仅 r={holder_r:.2f}，故该格也错位）'
                               if holder_r else '')),
        })
    return rows
