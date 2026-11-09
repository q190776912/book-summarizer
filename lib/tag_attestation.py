"""契约公式编号的**印刷锚点**审计（闸门 ⑭，纯函数）。

契约 tag 是步骤 5 门控的对账真值：契约里多一个原书**根本没印过**的编号，写手就被
逼着凭空 ``\\tag{}``（「编造」），删了又报「漏写」——两头堵。实测 Kreyszig 五个毒
tag 全属此类：``22``（display 里两个 ε/2 的分母被 OCR 成独立数字块）、``50``/``25``
（``= 0.50`` 的小数尾巴）、``18751A``/``12818A``（波长 ``18 751 Å``）。

判据（保守优先——漏报可接受，误报会把写手卡在门外）：
① tag 在本章页窗内**既无** ``(N)`` 形态的印刷编号、**也无**独立成块的裸 ``N`` →
   无锚点，判毒；
② 本章编号以 ``(N)`` 为主（parenthesized 占比 ≥90% 且 ≥5 个）时，只有裸排锚点的
   tag 判毒——带括号的书里，裸数字块几乎总是公式内部碎片而不是编号列。
③ tag 带**字母尾**（``_lettered_tail``：数字后紧跟字母，如 `2n` / `12x` / `18.10a`）而本章
   体例不用字母时判毒（公式残渣 / 换行粘连型幻影，如 `2n` 来自 `2` + 下行 `n`）。
   🔴 口径是**尾巴**不是「含字母」：`V.1` / `III.16` 那种**前缀**字母是另一种编号体例，
   该由判据①管；把它们算进分母会把体例证据挤死（Gelfand–Manin《methods-of-homological-algebra》
   ch5 印面 30 块独立编号里 29 块「含字母」却**一块字母尾都没有**，旧口径下该章契约里的
   `9x` / `9y` 两个公式残渣永远量不到体例矛盾——2026-10-31 改口径后即点名）。「本章体例」
   有两处证据，任一成立即可（:func:`lettered_leg_enabled`）：
   **印面侧**＝页窗里「整块就是 `(号)`」的独立编号 ≥5 个且字母尾 ≤10%；**契约侧**＝本章
   纯整数 tag ≥5 且字母尾 ≤10%。拿到「整块就是 `(号)`」强证据的号一律放行（字母编号的书
   很多：2026-10-31 跨 58 书 / 472 章实测，契约里余下 93 个字母尾号，**91 个**拿到强证据
   （真印的 `7a` / `9.25a` / `5.1.3a` / `11.1d` 型号），另 2 个（数学分析 ch8 `2M`、
   LawrenceEvans-SDE chC `2k`）所在章页窗独立编号 <5 且纯整数 tag <5 ＝**按设计量不到**，
   照实报出、交印面取证裁定，不得批量豁免静音）。

🔴 **②③ 的「本章体例」分母读全量契约 tag，裁决只作用于未登记的号**。登记处
（``attested`` / ``known_book``）说的是「这个号别判毒」，不是「这个号不算本章体例」；
旧写法先摘掉登记号再从同一列表数分母，于是**登记得越多、闸越弱**——基础/数学分析 把
``known_book`` 写成 `1..30`（本书编号正是章内 `(1)`..`(30)` 型），采样纯整数 tag 塌到 0–2 个，
②③两条比例腿同时关死，13 个公式残渣字母尾幻影全数放过（2026-10-30 跨 58 书 / 477 契约行
普查：旧口径下 ③ 在全语料**点名 0 处**＝死代码）。两处改版（分母读全量 + 印面侧证据腿 +
字母尾口径）之后这条腿点名并落账 **16 处**（数学分析 14、Gelfand–Manin ch5 `9x`/`9y`，
均经 fitz 裁剪目视裁定，见各书 ``_extract/_formula_tag_deregistrations.jsonl``）。
🔴 现在普查报「点名 0 处」是**因为账已销清**，不是腿死了：known_true 核把摘除前的契约备份
喂给今天的判据（真页窗 + ``condemned_map`` 出厂入口），数学分析 ch18 `1D`/`2p`、ch9
`2g`/`9x`/`3w`、Gelfand–Manin ch5 `9x`/`9y` 全部复现点名。校准与失明口径见
``tools/census_gate14_lettered_blindness.py``（含 `--dump/--ab` 两遍裁决对照与 known_true 核）。

**人工确证豁免**（``attested=``）：判据①②全靠 OCR 页窗，而**扫描书的 OCR 会整块漏掉
某些真印编号**（页边号与公式粘连后被丢弃、双色排版、拟合裁剪切掉右缘）。这类号一旦被
判毒，写手就陷入本模块开头说的两头堵：**凭印面真相 \tag 判编造、删掉判漏写**——闸与
Q 层（``verify_config.json`` 的 ``formula.known_book``，其定义正是「书源确有、抽取器
漏挂的真编号」）互相矛盾。故 ⑭ 与 Q 层共用同一份人工确证登记：在 ``attested`` 里的号
**不再判毒**（三种理由码一律豁免），闸的举证责任回到登记方（人工目视印面后才登记，
登记工具会复验 JSON）。``attested`` 默认 ``None`` = 行为与既往完全一致（收割期
``strip_unattested`` 在人工复核之前，不传豁免）。

负向测试见 ``lib/tests/test_tag_attestation.py``。

本模块同时提供闸门 ⑭ 的**对偶** —— 闸门 **⑱**「收割漏号」
``unharvested_anchor_tags``（印面 `(N)` 锚点在契约里在档、其展示式却没登记 tag）+
``unharvested_anchor_problems``（四条收紧判据：有单元记录 / 同节正文里该号整体消失 /
编号形态干净 / 印刷序列有邻居，全语料 477 章实测 491→22）。判据与用法见函数文档。
"""

import re

from lib.numbering import _FORMULA_SEP, formula_num_core

__all__ = ["collect_contract_tags", "tag_attestation_problems",
           "unattested_tags", "strip_unattested", "dir_page_loader",
           "attested_numbers", "condemned_map",
           "bare_only_leg_enabled", "lettered_leg_enabled",
           "unharvested_anchor_tags", "unharvested_anchor_problems",
           "glued_anchor_tags", "glued_anchor_problems",
           "exercise_context_keys",
           "rendered_numbers", "page_geom_loader", "page_anchor_index",
           "number_column", "column_separable", "margin_anchor_audit",
           "numbering_gaps", "numbering_gap_problems",
           "paren_block_is_factor_form", "standalone_label_sites",
           "operand_only_paren_anchor"]


def _norm(tag):
    s = str(tag if tag is not None else "").strip()
    return s


def collect_contract_tags(tree):
    """契约树 → [(节点 key, tag 字符串)]，按文档序；``tags`` 列表展开在 ``tag`` 之后。"""
    out = []

    def walk(node):
        if isinstance(node, dict):
            blk = node.get("formula")
            if blk is not None:
                for t in ([node.get("tag")] if not node.get("tags")
                          else [node.get("tag")] + list(node.get("tags") or [])):
                    n = _norm(t)
                    if n:
                        out.append((node.get("key"), n))
            for c in node.get("sub_sec") or []:
                walk(c)
        elif isinstance(node, list):
            for c in node:
                walk(c)

    walk(tree)
    seen, uniq = set(), []
    for k, n in out:
        if n in seen:
            continue
        seen.add(n)
        uniq.append((k, n))
    return uniq


_LABEL_TAIL = r"[A-Za-z]*[\*'’′]*"
# 🔴 序标主体取自 `lib.numbering.formula_num_core`（编号形态 SSOT），本模块不得
# 自写 `\d+(\.\d+)*`。旧写法**只认数字开头**，于是**字母章位编号**（附录 `(A.5)`
# 型，Shafarevich《Basic Algebraic Geometry 1》附录 5 的 A.1–A.15、Lee ISM 附录
# B/C/D 实测）在页窗里**查无锚点** → 一整批**真实**印刷编号被判「unattested」并在
# 收割处（`build_structure` → `strip_unattested`）剔光 → 契约不登记、单元侧写
# `\tag{A.N}` 判编造、删掉判漏写，且完整性闸门 ① 的复算与磁盘契约互相缺块
# （假 FAIL，实测本书 appendix5 13 缺 13 多）。
# `letter=True` 变体**只进括号形态**：裸排 `A.5` 与 `Fig. A.5` / 小节标题 `C.1`
# 无形态区别（与 `formula_tag_re` 的取舍同源，不得各写一份）。
# 🔴 罗马章位（`formula.type: 16`，`(II.5)` 型）同理加 `_ORD_ROMAN = _index_core(
# lead='roman')` 并进两条 alternation，否则多字母罗马头在页窗里查无锚点、被
# `strip_unattested` 剔光（与上文字母章位假 FAIL 同一失配路径）。
# 🔴 锚点索引**不认逗号**（SSOT 的 `_FORMULA_SEP` 含 `,`，此处收窄为 `[.\-·]`）：
# `(0, 1)` / `(83, 3)` 在页面上几乎总是坐标 / 列表而非编号，认了就把这类毒 tag
# 放回来（methods-of-homological-algebra ch1/ch3 的 `0,1` / `0,0,1` / `83,3` 实测，
# 跨语料 607 份契约标定：收窄后旧判毒→新放行只剩字母章位一类，反向 0 处）。
_NO_COMMA_SEP = r"[.\-·]"


def _index_core(letter=False, lead=None):
    return formula_num_core(None, letter=letter, lead=lead).replace(
        _FORMULA_SEP, _NO_COMMA_SEP)


_ORD_DIGIT = _index_core()
_ORD_LETTER = _index_core(letter=True)
_ORD_ROMAN = _index_core(lead='roman')
_PAREN_LABEL_RE = re.compile(
    r"[（(]\s*((?:%s|%s|%s)%s)\s*[)）]"
    % (_ORD_DIGIT, _ORD_LETTER, _ORD_ROMAN, _LABEL_TAIL))
_BARE_LABEL_RE = re.compile(r"(?:%s)%s" % (_ORD_DIGIT, _LABEL_TAIL))
# 🔴 **排版壳**宏名白名单——:func:`_label_forms` 折平时**只**删这些，其余宏一律留在形态里。
# 动因（基础/数学分析 ch3 物理页 173 实测）：旧折平用 `\\[a-zA-Z]+` **无差别删宏名**，
# 于是行内公式 `f ^ { \prime } \left( { \frac { 1 } { n \pi } } \right)` 被折成 `f'(1n)'`
# ——`\left`/`\frac`/`\pi` 一删，`1` 与 `n` 直接贴进括号，**造出**一个印面上根本不存在的
# `(1n)` 括号锚点。后果两层：① 幻影 tag（`1n` / `0x` 一类公式残渣）拿到「锚点」→ ⑭ 判不
# 出毒；② `tools/deregister_formula_tags.py --false-anchor` 见「有 `(N)` 括号锚点」即
# **机械拒绝**，把真幻影分流到 `--mispaired`（处方指向一个并不存在的宿主节点）。
# 白名单只收**不携带数字内容**的壳：字体/加粗/文本包装 + 定界符尺寸 + 老式字体切换；
# `\frac` / `\pi` / `\sum` / `\begin` 等内容宏留在形态里，其相邻的括号自然就不再是
# 「纯编号形」。真锚点不受影响：`( 7 \mathbf { c } ^ { \prime } )` → `(7c')`、
# `\mathbf { 29 }` → `29` 靠的正是这里列出的壳宏；而「编号被 OCR 粘进公式行」的既有口径
# （块内任意位置）也不需要删内容宏——`\sum_k (12)` 里的 `(12)` 照样命中。A/B 校准与
# 「只削假阳」的四档 known_true 见 `tools/census_gate14_anchor_forms.py`。
_LATEX_STYLE_MACROS = frozenset({
    # 定界符与尺寸
    "left", "right", "big", "Big", "bigg", "Bigg",
    "bigl", "bigr", "Bigl", "Bigr", "biggl", "biggr", "Biggl", "Biggr",
    # 字体/加粗/文本包装（其**参数**可能是编号本身，故必须删壳）
    "mathbf", "mathit", "mathrm", "mathsf", "mathtt", "mathcal", "mathbb",
    "mathfrak", "mathnormal", "boldsymbol", "bm", "pmb",
    "text", "textrm", "textit", "textbf", "textsf", "texttt", "emph",
    "mbox", "operatorname",
    # 老式字体切换开关（无参数、作用到下一个 `}`）
    "bf", "it", "rm", "sf", "tt", "mit", "sl",
})
# 🔴 匹配必须取**极大命令名**（`\\([a-zA-Z]+)` + 集合查），不能用 `\\(?:it|text|…)\b`：
# Iwaniec–Kowalski《Analytic Number Theory》p462 印面编号 `(20.60)` 的 OCR 形是
# `({\it20.60})`——`\it` 后面**直接跟数字**，`\b` 在 `t` 与 `2` 之间不成立，白名单分支
# 永不命中，真锚点被吃掉（A/B 普查实测到的唯一一次反向误伤）。按整词取名再查集合没有
# 这个洞；未被白名单收录的命令（含 `\dot`/`\hat` 这类**参数是数学内容**的重音命令）
# 一律留在形态里。
_LATEX_CMD_RE = re.compile(r"\\([a-zA-Z]+)\s*")


def _strip_style_macros(t):
    """LaTeX 串 → 删掉**排版壳**命令，其余命令原样留下（内容宏是造假锚点的原料）。"""
    return _LATEX_CMD_RE.sub(
        lambda m: "" if m.group(1) in _LATEX_STYLE_MACROS else m.group(0), t)


# 🔴 **无数字头的符号编号**（Arnold《经典力学的数学方法》§52 印作 `(*)` 的展示式，
# 印刷 p.231）：编号主体 SSOT `formula_num_core` 以 `\d+` 开头，因此**收割端永远产不
# 出**这类 tag（`formula_tag_re` 整块匹配必须命中数字头）。于是上面两条正则对它是
# 双盲：契约里一旦出现手回填/将来体例变化产生的 `*`，页窗里明明印着 `(*)` 却「查无
# 锚点」→ ⑭ 判毒 → 写手照印面 `\tag{*}` 判编造、删掉判漏写（两头堵，本模块文档串
# 开头描述的正是这个形态）。
# 该分支**只认括号形态**：裸排 `*` 与脚注星号 / 乘号 / OCR 火星无区别。
# 🔴 为何这个放宽对既有判据是**安全**的（不会把真毒 tag 放回来）：收割器产出的 tag
# 一律含数字头，其锚点仍由 `_PAREN_LABEL_RE` 判定，本分支只对「整块纯粹由
# 星号/撇号构成」的号生效，对既有全语料标定结果零影响（实测跨书普查：除本书回填的
# `*` 外，607 份契约无任何数字头缺失 tag）。
_SYMBOL_LABEL_RE = re.compile(r"[（(]\s*([*'’′＊]{1,3})\s*[)）]")
# 🔴 **独立成块**的带括号编号（整块只有 `(号)`，最多跟一个句号）。`_PAREN_LABEL_RE`
# 是「块内任意位置」口径，对「无锚点」判毒正合适（宁松勿严），但它会把数学表达式也
# 收进来：`(2n)!!` / `(2n)!` 是**双阶乘/阶乘**，不是公式编号（基础/数学分析 ch7 p325、
# ch14 p209 实测）。形态启发式（lettered）要放行一个号，必须拿到「这一整块就是编号」
# 级别的证据，故另立本口径。
# 🔴 主体沿用 SSOT `_index_core`（与 `_PAREN_LABEL_RE` 同源）而不是自写 `[0-9]…`：
# 后者要求「单个数字 + 点分段」，`18.10a` 的第 2 位 `8` 直接失配，豁免永不生效。
_STANDALONE_LABEL_RE = re.compile(
    r"^\s*(?:>\s*)?[（(]\s*((?:%s|%s|%s)%s)\s*[)）]\s*[.。]?\s*$"
    % (_ORD_DIGIT, _ORD_LETTER, _ORD_ROMAN, _LABEL_TAIL))


def _standalone_labels(page_loader, lo, hi):
    """页窗内**整块即为** `(号)` 的编号集合（lettered 豁免用的强证据口径）。

    与假锚通道的「印面有没有编号列」判据同源（:func:`standalone_label_sites` 投影，
    匹配只有一趟）。
    """
    return set(standalone_label_sites(page_loader, lo, hi))


def _label_forms(raw):
    """一个页内块 → 它可能承载编号的**书写形态**。

    MFD 把左缘印刷编号当公式检测出来时，`(7c')` 长成 ``( 7 \\mathbf { c } ^ { \\prime } )``、
    `(7*)` 长成 ``( 7 ^ { * } )``——不还原成扁平形态就永远「查无锚点」，闸门会把**真实**
    印刷编号判成噪声（反向误伤）。故对含反斜杠的块额外给一份去掉**排版壳**/花括号/空格/
    上标符的形态（`\\prime`→`'`）。

    🔴 去壳**只**许删排版宏（:data:`_LATEX_STYLE_MACROS`）：内容宏（`\\frac` / `\\pi` /
    `\\sum`…）必须留在形态里，否则 `\\left(\\frac{1}{n\\pi}\\right)` 会被折成 `(1n)`，
    凭空造出一个印面不存在的括号锚点（幻影自证 + `--false-anchor` 误拒，见该常量注）。

    🔴 OCR 还常把编号分隔点两侧夹进空格（茆诗松概率论 p139 实测：印面 `(2.7.5)` 被
    OCR 成独立块 ``(2. 7. 5)``）——带空格形态让 `_PAREN_LABEL_RE` 查无锚点，把真号
    判毒（⑭ 与 Q 层两头堵）。对含「数字 空格 分隔点 空格 数字」的块额外给一份
    收缩空格的形态；只收缩数字与分隔符之间的空格，不动块内其他空格。
    """
    s = str(raw or "").strip()
    if not s:
        return
    yield s
    if re.search(r"\\|\^|[{}]", s):
        t = s.replace("\\prime", "'")
        t = _strip_style_macros(t)
        t = re.sub(r"[{}\s^]", "", t)
        if t and t != s:
            yield t
    t2 = re.sub(r"(?<=[0-9])\s*([.\-·])\s*(?=[0-9])", r"\1", s)
    if t2 != s:
        yield t2


def anchor_locations(page_loader, lo, hi, _samples=3):
    """页窗 → ``{号: {"paren": {页: [原块]}, "bare": {页: [原块]}}}``。

    这是**唯一一趟锚点匹配**（:func:`_label_index_by_page` / :func:`_label_index` 都只从
    它投影，修复工具不得另写一份）。多留「原块文本」这一维是给**事后修复**取证的：
    `tools/deregister_formula_tags.py --false-anchor` 要求操作者说清「那个裸块到底是什么」
    （页码 / 节号 ``§6.2`` / 数学零 ``\\boldsymbol{0}`` / 公式片段 ``4m``），工具把原块
    一并打印并写进台账 —— 声称「假锚」无法凭空写下。每（号,页）最多留 `_samples` 条。
    """
    out = {}

    def add(num, kind, pg, raw):
        d = out.setdefault(num, {"paren": {}, "bare": {}})[kind]
        lst = d.setdefault(pg, [])
        # 一个块经 `_label_forms` 可能有好几种形态（原形 + 去宏名形），同一个（去首尾空白）
        # 原块只记一次：假锚通道要把这些样本**打印出来给人核对印面**，
        # 重复形会挤掉真正不同的块。
        v = str(raw).strip()[:80]
        if v not in lst and len(lst) < _samples:
            lst.append(v)

    for pg in range(int(lo), int(hi) + 1):
        blocks = page_loader(pg)
        if not blocks:
            continue
        for raw in blocks:
            for t in _label_forms(raw):
                tt = t.replace("．", ".")
                if _BARE_LABEL_RE.fullmatch(tt):
                    add(tt, "bare", pg, raw)
                for m in _PAREN_LABEL_RE.finditer(tt):
                    add(m.group(1).replace("．", "."), "paren", pg, raw)
                for m in _SYMBOL_LABEL_RE.finditer(tt):
                    add(m.group(1), "paren", pg, raw)
    return out


# 🔴 **算式因子**形态：页窗里的 `(N)` 是**链式算式里的一项**（陪集/坐标/因子），
# 不是页边的公式编号。
# 动因（2026-10-31 Fraleigh《AFCAA》ch23 §23.1 实测）：印面 p.194 排的是 Z₁₂ 零因子的
# 陪积链 `(2)(6) = (6)(2) = (3)(4) = … = (9)(8) = 0`，**整章页边一个公式编号也没印**
# （300 dpi 右缘裁剪 + 页窗 p208–220 跨距普查双重取证），可契约与两侧单元里躺着幻影
# `\\tag{3}` / `tags: ["3","8"]`。⑭ 判不出它毒，因为括号锚点走的是「块内任意位置」口径
# （`(3)` 就在阵列**内容**里）；而 `tools/deregister_formula_tags.py --false-anchor` 又以
# 「页窗里有 `(N)` 括号锚点」为**机械拒**，于是真幻影被硬分流到 `--mispaired` —— 那条处方
# 要求指认一个印面上根本不存在的宿主展示块（该章没有任何带真号的展示式）。
# 🔴 单看**局部贴邻**判不出编号：OCR 把长陪积链**切成多块**，块尾的 `(8)(3)` 与「公式行尾
# 粘着页边编号」的 `g(x) (3)` 形状完全相同（两侧都是「一边贴 `)`、一边到块尾」）。所以放行
# 判据的**承重墙是「同号形」**：本章页窗里只要印着一个「整块就是 `(N)`」且**号形与该号相同**
# 的独立编号块，该号是编号的可能就没被排除，通道照旧拒（:func:`standalone_label_sites`
# 是那一档证据的口径，与 lettered 豁免同源；:func:`_num_shape` 是「同号形」的口径）。
# 为什么从「整章任一独立编号块」收窄到「同号形」（2026-10-31 Gelfand–Manin 实测）：该书
# 页边印的是**章级罗马号** `(I.N)/(II.N)/(III.N)`，而正文里 `F(\mathcal{G})`、`T(1)`、
# `f'(9)` 这类**函子自变量**被 OCR 成 `(9)`——旧承重墙被罗马号列永久撑住，于是章章都印着
# `(III.x)` 的书里，任何裸阿拉伯幻影都声称不了假锚，只能改口 `--mispaired` 去指认一个
# 印面上不存在的主展示块。号形把两套编号分开算：`(III.41)` 证不了裸 `9` 是编号，
# 而 ch1 p39 那个**真印的**独立块 `(2)` 仍然一票否决裸 `2`（同书自带的反向控件）。
# 集合含 TeX 花括号：数组形 `& { ( 2 ) ( 6 ) =` 折平后 `(2)` 贴 `&`、未折平时贴 `{`，
# 两种形态都该认出是因子；而页边编号块不会以 `{` 起头、也不会以 `}` 收尾。
_FACTOR_FLANK = frozenset("()[]{}<>）（【】〔〕=+-*/^_<>,|&;×·∈≤≥±÷")
# 「函数应用」左贴字符集（`F(9)`、`T(1)`、`fr(2)`、`f'(9)`）：**只**收拉丁字母/数字/撇号，
# 且要求**零间隙**（判据见 :func:`_span_is_factor`）。不收 CJK——中文书的 `其中(2)成立`
# 同样零间隙，但那是回指编号而不是算式一项。
_APPLY_LEFT = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'")
# 跳过的「贴邻」间隙：只有水平空白算贴着（换行不算——跨行的 `(N)` 多半是独立成行的编号）。
_FLANK_GAP = " \t"

_DIGIT_RE = re.compile(r"\d")
_LETTER_RE = re.compile(r"[A-Za-z]")


def _num_shape(num):
    """号 → **号形**三档：``plain``（纯数字）｜``dotted``（含分隔点）｜``lettered``（含字母）。

    用途：独立编号块只能为**同号形**的锚点背书——页边排 `(III.41)`（dotted）的书，其编号列
    证不了裸 `9`（plain）是编号；页边排 `(7)`（plain）的书则照样拦住裸 `3` 的假锚声称。
    """
    s = str(num)
    if "." in s or "-" in s or "．" in s:
        return "dotted"
    if _LETTER_RE.search(s):
        return "lettered"
    if _DIGIT_RE.search(s):
        return "plain"
    return "other"


def _flank_chars(s, i, j):
    """`(N)` 占据 ``s[i:j]`` → 该**行内**左右贴着的字符（跳水平空白；到行界返回 ""）。"""
    k = i - 1
    while k >= 0 and s[k] in _FLANK_GAP:
        k -= 1
    lead = s[k] if k >= 0 and s[k] not in "\r\n" else ""
    n = len(s)
    k2 = j
    while k2 < n and s[k2] in _FLANK_GAP:
        k2 += 1
    tail = s[k2] if k2 < n and s[k2] not in "\r\n" else ""
    return lead, tail


def _paren_spans(form, num):
    """一个折平形态里号 ``num`` 的括号 occurrence 区间——与 :func:`anchor_locations`
    **同一套**正则与归一（`_PAREN_LABEL_RE` + `_SYMBOL_LABEL_RE`），保证「算不算锚点」
    与「锚点呈什么形态」两趟判的是同一批 occurrence。"""
    want = str(num)
    for rx in (_PAREN_LABEL_RE, _SYMBOL_LABEL_RE):
        for m in rx.finditer(form):
            if m.group(1).replace("．", ".") == want:
                yield m.start(), m.end()


def _span_is_factor(s, i, j):
    """一个 `(num)` occurrence 算不算「算式里的一项」。

    两档成立其一即算：① 任一侧贴运算符/括号（旧口径，`= (4) (3) = 0`、`(2)(6)`）；
    ② 左括号**零间隙**紧贴拉丁字母/数字/撇号 —— **函数应用形** `F(9)`、`T(1)`、`y(1)`、
    `f'(9)`、`fr(2)`（动因 2026-10-31 Gelfand–Manin ch2/ch3 实测：那几处 `(N)` 全是
    函子/映射的自变量，旧口径把「贴字母」一律当编号本形，于是 `--false-anchor` 把
    真幻影分流到 `--mispaired`，而那条处方要求指认一个印面上不存在的主展示块）。

    🔴 ② 只认**零间隙**：页边编号与公式之间印面上必有空白，OCR 切成一块时是
    `x + y = z (12)` 这种带间隙形，而 `_label_forms` 只对含 `\\`/`^`/`{}` 的块折平，
    纯文本块拿不到零间隙形 —— 所以「贴着字母」在文本行里不会被误当成内容。
    🔴 ② 不认 CJK：中文书 `其中(2)成立` 也零间隙，但那是**回指编号**，不是算式一项。
    """
    if any(c in _FACTOR_FLANK for c in _flank_chars(s, i, j)):
        return True
    return i > 0 and s[i - 1] in _APPLY_LEFT


def paren_block_is_factor_form(raw, num):
    """一个页内块里号 ``num`` 的 `(N)`，是否**只**呈「算式一项」形态。

    → ``None``：该块没有该号的括号锚点（不参与判定）；``True``：存在一种书写形态，其中
    **每一个** `(num)` 都算算式一项（判据见 :func:`_span_is_factor`）；``False``：
    至少一个 occurrence 有一侧是**空的**（块首/块尾/行界）或贴着普通文字 ⇒ 编号本形。

    🔴 取「**任一**折平形态成立即算因子」而不是「所有形态」：`_label_forms` 会把数组
    LaTeX 的空格/花括号折掉，同一处印面在折平形里贴 `&`、在原形里贴 `{`，要求两形同时
    成立会让阵列里的因子永远判成编号（= 本判据要修的那个机械拒）。
    """
    hit = False
    for t in _label_forms(raw):
        tt = t.replace("．", ".")
        spans = list(_paren_spans(tt, num))
        if not spans:
            continue
        hit = True
        if all(_span_is_factor(tt, i, j) for i, j in spans):
            return True
    return False if hit else None


def standalone_label_sites(page_loader, lo, hi, _samples=3):
    """页窗 → ``{号: {页: [原块]}}``：**整块就是** `(N)`（可带 `>` 引用前缀 / 尾点）的
    独立编号块——「印面确有编号列」这一档证据的**唯一口径**（lettered 豁免与
    :func:`operand_only_paren_anchor` 共用，不得各写一份）。
    """
    out = {}
    for pg in range(int(lo), int(hi) + 1):
        for raw in (page_loader(pg) or []):
            for t in _label_forms(raw):
                m = _STANDALONE_LABEL_RE.match(t.replace("．", "."))
                if not m:
                    continue
                num = m.group(1).replace("．", ".")
                lst = out.setdefault(num, {}).setdefault(pg, [])
                v = str(raw).strip()[:80]
                if v not in lst and len(lst) < _samples:
                    lst.append(v)
    return out


def operand_only_paren_anchor(page_loader, lo, hi, num):
    """闸门「假锚」通道的**机械放行判据**：该号在本章页窗里的 `(N)` 只是算式因子。

    → ``(ok, 理由, 证据块)``。``ok=True`` 要求两条同时成立：
      ① 本章页窗没有**与该号同号形**的独立编号块（:func:`standalone_label_sites` 按
         :func:`_num_shape` 筛）——该形的页边编号列不存在，`(N)` 才可能只是内容；
      ② 该号的**每一个**括号锚点块都呈算式因子形（:func:`paren_block_is_factor_form`，
         含「函数应用零间隙」那一档）。
    任一不成立即 ``(False, 理由, 那几块原样)``，工具据此**照旧拒**并打印原块。
    """
    sites = standalone_label_sites(page_loader, lo, hi)
    shape = _num_shape(num)
    same_shape = {n: d for n, d in sites.items() if _num_shape(n) == shape}
    if same_shape:
        ev = ["(%s) p%s | %s" % (n, pg, v[0])
              for n, d in sorted(same_shape.items()) for pg, v in sorted(d.items())]
        return (False,
                "本章页窗里印着与该号**同号形**（%s）的独立编号块（%d 处）⇒ 印面这一章确有"
                "该形的页边编号列，「(N) 只是算式内容」不成立" % (shape, len(ev)),
                ev[:6])
    bad, good = [], []
    for pg in range(int(lo), int(hi) + 1):
        for raw in (page_loader(pg) or []):
            f = paren_block_is_factor_form(raw, num)
            if f is False:
                bad.append("p%s | %s" % (pg, str(raw).strip()[:80]))
            elif f:
                good.append("p%s | %s" % (pg, str(raw).strip()[:80]))
    if bad:
        return (False,
                "该号有 %d 块括号锚点呈**编号本形**（一侧空着或贴普通文字），"
                "与「页边编号被 OCR 粘进公式行」同形" % len(bad),
                bad[:6])
    if not good:
        # 没有任何括号锚点时不该说「放行」——放行是在为 `(N)` 锚点开路，无锚点就没有可开的门
        # （调用方此处不该发生；发生即读页口径/号形对不上，按不放行处理）。
        return (False, "该号在本章页窗里**没有**括号锚点（无需分流，也无从举证）", [])
    return (True, "该号在本章页窗里的每个 `(N)` 都紧贴括号/运算符，且整章无独立编号块",
            good)


def _label_index_by_page(page_loader, lo, hi):
    """页窗 → ``(paren: {号: {页}}, bare: {号: {页}})`` —— 与 :func:`_label_index`
    **同一套匹配**，只是多留「哪些页出现」这一维（同一处算术，普查不得另写一份）。

    抽出来的动机（2026-10-30 Rising Sea ch21 实测）：章级锚点集是**整页窗的并集**，于是
    p587 上一个孤立裸块 ``0`` 能给 p590 证明里那条展示式的 tag ``0`` 当锚点 —— 幻影自证
    的通道不止「数组元素」一种，根子是**裸块锚点没有位置约束**。判据本身暂不改（收紧
    会新增判毒，必须先跨语料普查，见 ``tools/census_gate14_bare_blindness.py``）。
    """
    locs = anchor_locations(page_loader, lo, hi)
    return ({n: set(d["paren"]) for n, d in locs.items() if d["paren"]},
            {n: set(d["bare"]) for n, d in locs.items() if d["bare"]})


def _label_index(page_loader, lo, hi):
    """页窗 → (parenthesized 集合, 裸排集合)。

    ``paren`` 收**任意块内**出现的 ``(N)``（编号被 OCR 粘进公式行、或被 MFD 当公式
    检测出来都认），``bare`` 只收**整块就是一个数**的块。
    ``paren`` 另收**无数字头**的符号编号 `(*)` / `(**)`（见 `_SYMBOL_LABEL_RE`）。
    """
    paren, bare = _label_index_by_page(page_loader, lo, hi)
    return set(paren), set(bare)


def dir_page_loader(*dirs):
    """→ ``load(pdf_page)``：该页**可能承载印刷编号**的全部块文本（正文 + MFD 公式
    latex），找不到页文件返回 None。

    ⑭ / 剔除 / 事后修复三处共用同一读页口径（旧实现只住在 `gate_units` 里，
    `build_structure` 想在落盘前剔除就得复制一份——两份读页逻辑必然分叉）。
    MM 修复后的页里 ``text`` 可能再套一层 ``{"text": {"text": ...}}``，一并摊平。
    """
    import json
    import os

    cache = {}

    def _flat(s):
        if isinstance(s, dict):
            s = s.get("text")
        return str(s or "")

    def load(pg):
        if pg in cache:
            return cache[pg]
        val = None
        for d in dirs:
            if not d:
                continue
            for name in ("page_%03d.json" % pg, "page_%d.json" % pg,
                         "page_%04d.json" % pg):
                p = os.path.join(d, name)
                if os.path.exists(p):
                    try:
                        with open(p, encoding="utf-8") as f:
                            d_ = json.load(f)
                    except Exception:
                        d_ = {}
                    val = ([_flat(b.get("text")) for b in (d_.get("text") or [])]
                           + [str(b.get("latex") or "")
                              for b in (d_.get("formulas") or [])])
                    break
            if val is not None:
                break
        cache[pg] = val
        return val

    return load


# 🔴 判据③的形态口径是**字母尾巴**（数字紧跟字母：`2n` / `12x` / `18.10a` / `18751A`），
# **不是**「含字母」。动因（2026-10-31 methods-of-homological-algebra ch5 实测）：该书印面
# 编号是 `V.1`..`V.29`（罗马数字章前缀），页窗里 30 块「整块即 `(号)`」的独立编号有 29 块
# 「含字母」——用 `[A-Za-z]` 数分母时，印面侧比例腿被**前缀**挤死（29/30 > 10%），该章契约
# 里 `9x` / `9y` 两个公式残渣就永远量不到体例矛盾。前缀字母（`V.1` / `A.5`）是**另一种编号
# 体例**而不是尾巴：它该由判据①（查无锚点）管，不该由③管——否则「书用字母章位」直接等价于
# 「本章体例矛盾」，正是要避免的批量误伤。
_LETTER_TAIL_RE = re.compile(r"[0-9][A-Za-z]")


def _lettered_tail(num):
    """号 `num` 是否带**字母尾巴**（数字紧跟字母）—— 判据③的形态口径，判据与普查共用。"""
    return bool(_LETTER_TAIL_RE.search(str(num)))


# 🔴 印面侧体例证据的**最少独立编号块数**（:func:`lettered_leg_enabled` 的第一条腿）。
# 取 5 与契约侧那道门同数：少于 5 个「整块即 `(号)`」的印刷编号时，这一章的体例**量不到**，
# 不许由 tag 分布猜「字母尾＝幻影」。跨 58 书实测这样仍留 2 个章级量不到站点
# （数学分析 ch8 页窗只有 4 个、Evans-SDE chC 为 0）—— 照实报「失明」，不批量豁免。
_PRINTED_CONVENTION_MIN = 5


def attested_numbers(ext):
    """``verify_config.json`` 的 ``formula.known_book`` → 人工确证真印编号集合（裸号）。

    这是 ⑭ 的**人工确证登记处**（SSOT，读页/读配置口径唯一）：``known_book`` 的定义
    本就是「书源确有、却被抽取器漏挂的真实编号」（典型：编号与公式同行内联粘连，
    或扫描书 OCR 整块漏掉页边号）。Q 层据此**要求** ``\\tag``，⑭ 若看不见它就会
    **禁止**同一个 ``\\tag`` —— 两头堵（Iwaniec–Kowalski ch1 的 (1.104) 实测：印面
    确有、OCR 全无，两处判据必须共用这份登记）。任何缺失 / 异常 → 空集（判据退回
    既往行为）。兼容扁平（顶层 ``formula``）/ 分组（``ch``/``appendix``/
    ``supplement``）/ 历史 ``data`` 三种配置形状。
    """
    import json
    import os

    path = os.path.join(str(ext), "verify_config.json")
    if not os.path.exists(path):
        return set()
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return set()
    nums = set()

    def _harvest(formula):
        if isinstance(formula, dict):
            for x in (formula.get("known_book") or []):
                s = _norm(x)
                if s:
                    nums.add(s)

    def _harvest_node(node):
        if not isinstance(node, dict):
            return
        _harvest(node.get("formula"))
        if "known_book" in node:
            _harvest(node)

    _harvest(cfg.get("formula"))
    for grp in (cfg.get("ch"), cfg.get("appendix"), cfg.get("supplement")):
        _harvest_node(grp)
    data = cfg.get("data")
    if isinstance(data, dict):
        for sub in data.values():
            _harvest_node(sub)
    for v in cfg.values():
        if isinstance(v, dict):
            _harvest_node(v)
    return nums


def bare_only_leg_enabled(n_paren, n_bare):
    """``bare-only`` 这条腿是否生效 —— 抽成函数供判据与只读普查共用（同一处算术）。

    🔴 已知方向性缺陷（2026-10-30 数值分析 ch5 实测，见
    ``tools/census_gate14_bare_blindness.py``）：这是**比例**判据，幻影越多 → ``n_bare``
    越大 → 分母越大 → 腿越不生效，于是「最该查的章恰好失明」。摘掉一批幻影后腿会自己
    转开并点名剩下的，所以它只在幻影已经很少的书上工作。放宽它之前必须先跨语料普查。
    """
    return n_paren >= 5 and n_paren >= 0.9 * (n_paren + n_bare)


def lettered_leg_enabled(n_numeric, n_lettered, p_standalone=0, p_lettered=0):
    """``lettered`` 这条腿是否生效 —— 同 :func:`bare_only_leg_enabled`，抽成函数供判据与
    只读普查共用（同一处算术）。

    生效 ⇔ 有字母尾 tag，且**下面两条体例证据任成其一**：

    * **印面侧**（`_PRINTED_CONVENTION_MIN` 个以上「整块即 `(号)`」的印刷编号，其中字母尾
      ≤10%）——「本章编号到底怎么印」的**第一手**证据；
    * **契约侧**（本章纯整数 tag ≥5 且字母尾 ≤10%）——印面证据不足时的兜底（页窗里独立
      编号块少于 5 个的章，体例量不到，只能靠 tag 分布猜）。

    两条都要求「字母尾是少数」，因为字母编号的书里 `2a` / `9.25b` 是**正常号**，形态本身
    不是罪：2026-10-31 跨 58 书 / 472 章实测（字母尾口径），契约里余下 93 个字母尾号，
    **91 个**拿到「整块即 `(号)`」强证据而豁免（Koopman `9.25a/9.25b/9.25c`、Strogatz
    `5.1.3a`、Numerical-Methods `11.1a..11.1d`、Kreyszig `7a/7b`，共 21 章 / 8 书），
    另 2 个（数学分析 ch8 `2M`、LawrenceEvans-SDE chC `2k`）两条腿的证据都不足＝按设计
    量不到。所以这条腿只能在「印面/契约证明本章不用字母」时开口，否则就是批量误伤。
    🔴 同一份普查里「印面字母尾 >10% 而门关」（本章真用字母编号，门关得对）当前 **0 章**
    ——那些章的号全部走强证据豁免，轮不到腿来判；这条分支只有合成负向测在守
    （``lib/tests/test_tag_attestation.py::test_printed_lettered_convention_keeps_the_leg_shut``），
    别把它当已实测过的语料形态。

    🔴 为何必须加**印面侧**那条（2026-10-30 跨 58 书 / 477 契约行普查）：只看契约侧时这条腿
    在**全语料点名 0 处**＝死代码，16 个失明号（数学分析 13、Gelfand–Manin 2、Evans-SDE 1）全部
    卡在 `n_numeric >= 5` 这道门上——两个原因都不是「字母尾太多」（比例压死 = 0 章），而是
    ① 章本身 tag 稀疏（数学分析每章只有 1–3 个**未登记**的 tag）；② 登记处把样本掏空
    （见 :func:`_condemned` 的全量样本注）。比例读的是**契约**，而契约薄/被登记的章恰恰是
    幻影藏身处 ⇒ 分母越该有证据的章越量不到。印面侧那条读的是页窗，与契约厚薄、登记多少
    **无关**，方向才是对的。
    """
    if not n_lettered:
        return False
    printed = (p_standalone >= _PRINTED_CONVENTION_MIN
               and p_lettered <= 0.10 * p_standalone)
    contract = (n_numeric >= 5 and n_lettered <= 0.10 * (n_numeric + n_lettered))
    return bool(printed or contract)


def _condemned(tree, page_loader, attested=None):
    """→ (tags, kinds)；``kinds`` = {判毒 tag: 理由码}。页窗不可判时返回 (tags, {})。

    理由码：
    * ``unattested`` —— 页窗内既无 `(N)` 也无独立裸块锚点；
    * ``bare-only`` —— 只有裸排锚点，而本章编号以 `(N)` 为主；
    * ``lettered`` —— tag 含字母，而本章体例不用字母（印面独立编号块 / 契约 tag 分布
      任一证明之；字母尾巴多半是公式碎片 / 换行粘连，如 Strogatz 3e ch7 的 `2n`
      来自 `2` + 下一行 `n ?`）。

    ``attested`` = 人工目视印面确证为**真印编号**的号集（豁免判据，见模块文档串）。
    """
    skip = {_norm(x) for x in (attested or [])}
    all_tags = list(collect_contract_tags(tree))
    tags = [(k, n) for k, n in all_tags if n not in skip]
    if not tags:
        return tags, {}
    try:
        lo, hi = int(tree.get("page_start")), int(tree.get("page_end"))
    except (TypeError, ValueError):
        return tags, {}
    avail = [p for p in range(lo, hi + 1) if page_loader(p)]
    if not avail:
        return tags, {}
    paren, bare = _label_index(page_loader, lo, hi)
    # 🔴 「本章体例」的**分母读全量** tag（含已登记的号），**裁决只作用于**未登记的 ``tags``。
    # 旧写法先摘掉 attested，再从同一个列表数出 paren_hits / numeric，于是
    # **「登记得越多，闸越弱」**：基础/数学分析 把 ``known_book`` 写成 `1..30`（本书编号就是
    # 章内 `(1)`..`(30)` 型），采样纯整数 tag 立刻塌到 0–2 个，两条比例腿（bare-only 要
    # ``paren_hits>=5``、lettered 要 ``numeric>=5``）**同时**关死 —— 跨 58 书实测该腿全语料
    # 点名 0 处。登记处说的是「这个号别判毒」，不是「这个号不算本章体例」；两者必须分开，
    # 否则人工确证通道变成章级静音键（`tools/census_gate14_lettered_blindness.py` ④(b) 核）。
    paren_all = [n for _k, n in all_tags if n in paren]
    bare_all = [n for _k, n in all_tags if n not in paren and n in bare]
    unattested = [n for _k, n in tags if n not in paren and n not in bare]
    kinds = {n: "unattested" for n in unattested}
    if bare_only_leg_enabled(len(paren_all), len(bare_all)):
        for n in [x for _k, x in tags if x not in paren and x in bare]:
            kinds.setdefault(n, "bare-only")
    # 🔴 形态启发式**必须让位于印面锚点**（2026-10-01 Koopman Operator ch18 实测）：
    # 印面确有 `(18.10a)` / `(18.10b)`（物理页 502 独立成块），旧判据却只看形态
    # （本章 21 个号里 19 个纯整数）就一票否决，于是「照印面写对的号」被判「须在
    # 收割处剔除」，而 Q 层同一号又要求写 `\tag` ——两头堵。Strogatz 的 `2n`
    # （`2` + 下行 `n` 粘连）按定义没有独立编号块，故「拿到独立锚点即放行」只削掉
    # 这一类假阳。豁免口径用 `_STANDALONE_LABEL_RE`（整块就是 `(号)`）而不是
    # `_PAREN_LABEL_RE`（块内任意位置）：后者会把 `(2n)!!` 这类阶乘当成锚点。
    standalone = _standalone_labels(page_loader, lo, hi)
    lettered = [n for _k, n in tags
                if _lettered_tail(n) and n not in standalone]
    if lettered_leg_enabled(
            len([n for _k, n in all_tags if not _lettered_tail(n)]),
            len([n for _k, n in all_tags
                 if _lettered_tail(n) and n not in standalone]),
            len(standalone),
            len([n for n in standalone if _lettered_tail(n)])):
        for n in lettered:
            kinds.setdefault(n, "lettered")
    return tags, kinds


def condemned_map(tree, page_loader, attested=None):
    """只读出口：→ ``{判毒 tag: 理由码}`` —— **判据与普查共用同一趟裁决**。

    存在的理由：跨语料 A/B（`tools/census_gate14_lettered_blindness.py --dump/--ab`）要按
    **理由码**对比新旧裁决，而 `unattested_tags` 只给集合、`tag_attestation_problems` 只给
    中文句子。普查若自己复制一份 `_condemned` 的算术，判据一改就悄悄分叉（本模块的
    「同一处算术」规矩），所以这里把裁决原样递出去，不改判任何东西。
    """
    return dict(_condemned(tree, page_loader, attested)[1])


def unattested_tags(tree, page_loader, attested=None):
    """契约里**无印刷锚点 / 形态与本章体例矛盾**的 tag 集合（收割处剔除的判据）。

    与 :func:`tag_attestation_problems` 同一套判据（共用 :func:`_condemned`），
    只换成「集合」出口，供两处消费：① `build_structure` 落盘前剔除（毒 tag 不进契约）；
    ② 老契约的事后修复（步骤 5 单元已写毕、不能重建契约的书）。
    ``attested``（人工确证真印编号）里的号**不算毒**，见模块文档串。
    """
    return set(_condemned(tree, page_loader, attested)[1])


def strip_unattested(tree, page_loader, attested=None):
    """**就地**删除 ``tree`` 内被判毒的公式 tag（``tag`` 字段与 ``tags`` 列表元素）。

    → 被删除的 tag 字符串列表（去重、按文档序）。删除后公式块仍在（正文不丢），
    只是不再声称自己带编号 —— 单元侧因此既不该写 `\tag{}`，也不该因缺它被判漏写。

    ``attested`` 默认 ``None``：收割期还没有人工目视印面，此时不豁免任何东西。
    """
    tags, kinds = _condemned(tree, page_loader, attested)
    condemned = set(kinds)
    if not condemned:
        return []
    removed = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("formula") is not None:
                t = _norm(node.get("tag"))
                if t and t in condemned:
                    removed.append(t)
                    node["tag"] = ""
                    node.pop("tags", None)
                elif node.get("tags"):
                    keep = [x for x in node["tags"] if _norm(x) not in condemned]
                    if len(keep) != len(node["tags"]):
                        removed.extend(_norm(x) for x in node["tags"] if _norm(x) in condemned)
                        node["tags"] = keep
            for c in node.get("sub_sec") or []:
                walk(c)
        elif isinstance(node, list):
            for c in node:
                walk(c)

    walk(tree)
    seen, out = set(), []
    for t in removed:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def tag_attestation_problems(tree, page_loader, chapter_label="", attested=None):
    """→ 问题描述列表（空 = 全部 tag 有印刷锚点）。

    ``tree`` 分章契约（dict，需 ``page_start``/``page_end``）；``page_loader(pg)``
    给该页文本块内容列表或 None（缺页文件时**跳过不判**，fail-open 于缺数据、
    判毒只依据「有页而找不到锚点」）。``attested`` = 人工目视印面确证的真印编号
    （典型来源 `verify_config.json` 的 ``formula.known_book``，与 Q 层同一份登记），
    其中的号不参与判毒 —— 否则闸会逼写手删掉**照印面写对的** `\tag{}`。
    """
    _tags, kinds = _condemned(tree, page_loader, attested)
    if not kinds:
        return []
    try:
        lo, hi = int(tree.get("page_start")), int(tree.get("page_end"))
    except (TypeError, ValueError):
        return []
    paren, bare = _label_index(page_loader, lo, hi)
    # 🔴 报文里的分母与 :func:`_condemned` 的**裁决分母**必须是同一个（全量 tag，含已登记号）。
    # 用摘掉 attested 的那份会印出「21 个编号里 0 个是纯整数」这种自相矛盾的话，而读者正要
    # 拿这句去判断该不该剔号（2026-10-30 数学分析 ch14 实测：登记 `1..30` 把样本掏空）。
    all_tags = list(collect_contract_tags(tree))
    paren_hits = [n for _k, n in all_tags if n in paren]
    bare_only = [n for _k, n in all_tags if n not in paren and n in bare]
    # 🔴 报文与 :func:`_condemned` 用**同一个**形态口径：字母**尾巴**（`_lettered_tail`），
    # 不是「含字母」。罗马数字章前缀（`V.1` 型）含字母却没有尾巴，混用会印出与裁决依据不符、
    # 且把「书用字母章位」说成「体例矛盾」的句子。
    lettered = [n for _k, n in all_tags if _lettered_tail(n)]
    numeric = [n for _k, n in all_tags if not _lettered_tail(n)]
    # 「本章体例不用字母尾」有两条证据腿，报文要说清**是哪一条**证的（印面侧证的，
    # 契约侧往往薄得说不出话 —— 拿契约句子去解释印面裁决，读者会误以为证据不成立）。
    standalone = _standalone_labels(page_loader, lo, hi)
    p_le = [n for n in standalone if _lettered_tail(n)]
    lettered_ns = [n for n in lettered if n not in standalone]
    prov_printed = lettered_leg_enabled(0, 1, len(standalone), len(p_le))
    prov_contract = lettered_leg_enabled(len(numeric), len(lettered_ns))
    out = []
    for n in kinds:
        if kinds[n] == "unattested":
            out.append("契约编号 %s 在本章页窗 p%d–p%d 内找不到任何印刷锚点"
                       "（既无 `(N)` 也无独立成块的裸 N）—— 疑似 OCR 噪声"
                       "（公式内部数字 / 小数尾巴 / 带单位的量），须在收割处剔除，"
                       "不得由写手凭空 \\tag" % (n, lo, hi))
        elif kinds[n] == "bare-only":
            pct = 100.0 * len(paren_hits) / max(1, len(paren_hits) + len(bare_only))
            out.append("契约编号 %s 只有裸排锚点，而本章编号 %d%% 印作 `(N)`"
                       "—— 裸数字块多半是公式内部碎片而非编号列，须在收割处剔除"
                       % (n, round(pct)))
        else:
            if prov_printed and prov_contract:
                ev = ("本章页窗 p%d–p%d 内 %d 块「整块就是 `(编号)`」的独立印刷号里只有 %d 块"
                      "带字母尾巴，且 %d 个契约编号里 %d 个不带字母尾巴"
                      % (lo, hi, len(standalone), len(p_le),
                         len(numeric) + len(lettered), len(numeric)))
            elif prov_printed:
                ev = ("本章页窗 p%d–p%d 内 %d 块「整块就是 `(编号)`」的独立印刷号里只有 %d 块"
                      "带字母尾巴" % (lo, hi, len(standalone), len(p_le)))
            else:
                ev = ("本章 %d 个契约编号里 %d 个不带字母尾巴，且页窗 p%d–p%d 内没有任何一块"
                      "「整块就是 `(%s)`」的独立编号"
                      % (len(numeric) + len(lettered), len(numeric), lo, hi, n))
            out.append("契约编号 %s 带字母尾巴（数字后紧跟字母），而%s —— 这类尾巴多半是"
                       "公式碎片 / 换行粘连（如 `2` + 下行 `n…`），须在收割处剔除"
                       % (n, ev))
    if chapter_label and out:
        out = ["[%s] %s" % (chapter_label, p) for p in out]
    return out


# ── 闸门 ⑭ 的**对偶**：印面有编号、契约却没挂上（收割漏号）────────────────────
_ANCHOR_ONLY_RE = re.compile(r"^\(\s*([0-9]{1,3}[a-z]?)\s*\)[.。]?$")
# 🔴 ``\\tag`` 在正则里必须**双写**反斜杠：``"\t"+"ag"`` 会被 re 当成 TAB + "ag"，
# 整条判据静默 0 命中（本模块开发时实测：单元正文有 9 个 \tag，findall 返回 []）。
_UNIT_TAG_RE = re.compile(r"\\tag\s*\{\s*([0-9]{1,3}[a-z]?)\s*\}")
# 🔴 **负向前视后顾 `(?<![\^_{\\])`**：只收「印刷形态的裸编号 `(N)`」，不收 LaTeX
# **数学内部分组括号**。实测假阳（郑大钟《线性系统理论》ch10 例10.3，2026-11-02）：
# 兄弟单元 0092 忠实照印面写了块位置矩阵指标 `\eta_1^{(11)}`、`\eta_1^{(1q)}`，其中
# `(11)` 紧跟 `^{` 的 `{`——它是**分块行列表记号**（第(1,1)块），不是本章公式编号。
# 旧谓词把 `(11)` 当裸编号收进 `rendered_numbers` 逃逸池，于是闸门 ⑱ 对契约里那个
# 本就被 OCR 误当锚点的矩阵块位标签 `(12)`（印面是右缘块位号，非式号）**误判出邻居
# "11"** → 判据④「序列有邻居」假命中 → 整章凭空变红。加了 `^_{\` 四类后顾即根治：
# 真·裸编号前面恒是空白/中文标点/行首（`，(12)`、`\qquad (12)`、行首 `(12)`），不受
# 影响；而 `^{...}`/`_{...}`/`{...}`/`\(` 之后必然是数学分组，一律排除。检测趟与
# 修复趟共用同一 `rendered_numbers`（见 1124/1257），故两侧对称收紧、不产生工具-闸门分叉。
_UNIT_PAREN_RE = re.compile(r"(?<![\^_{\\])\(\s*([0-9]{1,3}[a-z]?)\s*\)")
_SEC_RE = re.compile(r"^[0-9]{1,3}\.[0-9]{1,3}$")
_CLEAN_NUM_RE = re.compile(r"^[1-9][0-9]{0,2}[a-z]?$")
_NUM_HEAD_RE = re.compile(r"^[0-9]+")


def _content_seq(node):
    """节点**自己的**内容块序列（按文档序，剔除子节点壳）。"""
    return [b for b in (node.get("sub_sec") or [])
            if isinstance(b, dict) and ("text" in b or "formula" in b)]


def unharvested_anchor_tags(tree):
    """契约树 → [(节点 key, 编号, 公式片段)]：`(N)` 锚点在档、其公式块却无 tag。

    闸门 ⑭ 管「契约多挂了原书没印的号」（毒 tag）；本函数管**反方向**——收割把
    印面编号弄丢，契约不登记，写手按契约对账永远看不见自己少写一个号，章级
    tag 集合比较又常被同章别处的同号掩盖（实测 Strogatz 3e ch13 §13.5：印面
    `(1)` 紧跟展示式 `r e^{i\\psi} = \\langle e^{i\\theta} \\rangle`，而契约该块
    无 `tag`，单元从 `\\tag{2}` 起写；`(1)` 在 §13.4 也在账 → 章级闸放行）。

    判据（保守，宁漏报不误报）：同一节点的内容块序列里，一个「整块只有 `(N)`」
    的文本锚点，其**前一个内容块**是 `display` 公式，且该公式块既无 `tag`、
    编号也不在其 `tags` 列表里 → 判漏挂。锚点前允许再夹若干同类锚点（多行公式
    组逐行编号时，收割会把若干号一并挂到相邻块上）。**不判**：锚点前是散文块
    （OCR 把公式切成多块，无从断定归属）、公式块已带 `tag`、裸排编号（无括号）。
    """
    out = []

    def visit(node):
        if isinstance(node, list):
            for c in node:
                visit(c)
            return
        if not isinstance(node, dict):
            return
        seq = _content_seq(node)
        for i, blk in enumerate(seq):
            txt = blk.get("text")
            if txt is None:
                continue
            m = _ANCHOR_ONLY_RE.match(txt.strip())
            if not m:
                continue
            num = m.group(1)
            j = i - 1
            while j >= 0 and _ANCHOR_ONLY_RE.match((seq[j].get("text") or "").strip()):
                j -= 1
            if j < 0:
                continue
            prev = seq[j]
            if prev.get("formula") is None or not prev.get("display"):
                continue
            have = [_norm(prev.get("tag"))] + [_norm(x) for x in (prev.get("tags") or [])]
            if num in [h for h in have if h]:
                continue
            out.append((node.get("key"), num, str(prev.get("formula"))[:60]))
        for c in node.get("sub_sec") or []:
            if isinstance(c, dict) and c.get("key") is not None:
                visit(c)

    visit(tree)
    seen, uniq = set(), []
    for k, n, f in out:
        if (k, n) in seen:
            continue
        seen.add((k, n))
        uniq.append((k, n, f))
    return uniq


# ── ⑱ 的**盲区**：锚点被 OCR 与公式残渣粘连成一块 ────────────────────────────
# 🔴 单独一个正则而**非**放宽 `_ANCHOR_ONLY_RE`：整块-only 形态是 ⑱ 的既有判据，
# 已在全语料标定；粘连形态是另一种证据强度，必须可单独关停（见 glued_anchor_problems）。
_ANCHOR_GLUED_RE = re.compile(r"^\(\s*([0-9]{1,3}[a-z]?)\s*\)[.。]?\s*(\S.*)$")
# 残渣里出现 ≥3 个连续英文字母 → 判为散文（交叉引用 / 句子开头），不是版面锚点。
_RESIDUE_PROSE_RE = re.compile(r"[A-Za-z]{3,}")
_GLUE_LOOKBEHIND = 5
_GLUE_JUNK_LEN = 24


def _glue_junk(text):
    """锚点与展示式之间的中间块是否只是 OCR 残渣（可跳过）。"""
    return len(text) <= _GLUE_JUNK_LEN


def glued_anchor_tags(tree):
    """契约树 → [(节点 key, 编号, 公式片段)]：**粘连锚点**版漏号探测。

    :func:`unharvested_anchor_tags` 只认「整块恰好是 `(N)`」的锚点；OCR 常把编号
    与公式残渣切成同一块（实测 Apostol IANT ch7 印面 `(9)` 收成 `(9) p(k)`、
    `(15)` 收成 `(15) G(x) = ∑α(n)F`），这类锚点对旧判据**完全隐形**，于是契约
    永不登记、写手按契约对账看不见自己少写两个号。

    判据（与旧判据同构，只把「前一块是展示式」放宽为「往前最多
    ``_GLUE_LOOKBEHIND`` 块、途中只允许跳过行内公式与 :func:`_glue_junk` 残渣，
    遇到散文块即停」）：
      * 块形如 ``(N) 残渣``，且残渣**不含 ≥3 个连续英文字母**——散文交叉引用
        （`(10) with (9) we obtain`、`(1). But`、`(3). See problem`）据此排除；
      * 命中的展示式**既无 `tag` 也不在其 `tags`**；
      * 编号未登记（同旧判据）。

    与 :func:`unharvested_anchor_tags` 一样**只报候选**，是否算真漏由
    :func:`_anchor_problems_for` 的四条收紧判据决定。
    """
    out = []

    def visit(node):
        if isinstance(node, list):
            for c in node:
                visit(c)
            return
        if not isinstance(node, dict):
            return
        seq = _content_seq(node)
        for i, blk in enumerate(seq):
            txt = (blk.get("text") or "").strip() if "text" in blk else None
            if txt is None:
                continue
            m = _ANCHOR_GLUED_RE.match(txt)
            if not m:
                continue
            num, residue = m.group(1), m.group(2)
            if _RESIDUE_PROSE_RE.search(residue):
                continue
            if _ANCHOR_ONLY_RE.match(residue):
                continue
            for step in range(1, _GLUE_LOOKBEHIND + 1):
                j = i - step
                if j < 0:
                    break
                prev = seq[j]
                if prev.get("formula") is not None:
                    if not prev.get("display"):
                        continue
                    if prev.get("tag") or prev.get("tags"):
                        break
                    if num in [_norm(x) for x in (prev.get("tags") or []) if _norm(x)]:
                        break
                    out.append((node.get("key"), num, str(prev.get("formula"))[:60]))
                    break
                if _glue_junk((prev.get("text") or "").strip()):
                    continue
                break
        for c in node.get("sub_sec") or []:
            if isinstance(c, dict) and c.get("key") is not None:
                visit(c)

    visit(tree)
    seen, uniq = set(), []
    for k, n, f in out:
        if (k, n) in seen:
            continue
        seen.add((k, n))
        uniq.append((k, n, f))
    return uniq


def rendered_numbers(text):
    """单元正文里**已按印刷形态出现过**的编号集合。

    ``\\tag{N}`` 与裸 ``(N)`` 都收：⑱ 只抓「整号凭空消失」，同一号的排版形态差异
    （``\\qquad (N)`` / ``\\tag{N}``）属另一判据，不能在这里制造误报。
    """
    s = str(text or "")
    out = set(m.group(1) for m in _UNIT_TAG_RE.finditer(s))
    out |= set(m.group(1) for m in _UNIT_PAREN_RE.finditer(s))
    return out


def _sec_index(tree):
    """契约树 → ({节点 key: 最近 §N.M 祖先或 None}, 全章是否含二级节的任一信号)。

    「节」= 键形如 ``N.M`` 的祖先（三级 ``N.M.K`` 与 ``chN`` 都向上找）。用于把
    逃逸池限定在同一节的单元正文并集——Strogatz 3e ch13 实测：漏的 `(1)` 在
    §13.4 也在账，章级集合比较因此失明，按节取池才既能定位真漏、又不被别处同号掩盖。
    """
    sec = {}

    def walk(node, chain):
        if isinstance(node, dict):
            k = node.get("key")
            nk = chain + [str(k)] if k is not None else chain
            if k is not None:
                sec.setdefault(str(k), _nearest_sec(nk))
            for c in node.get("sub_sec") or []:
                walk(c, nk)
        elif isinstance(node, list):
            for c in node:
                walk(c, chain)

    walk(tree, [])
    return sec


def _nearest_sec(chain):
    for k in reversed(chain):
        if _SEC_RE.match(k):
            return k
    return None


# ── ⑱ 的**裁向**证据：习题语境里的 `(N)` 多半是小问标号，不是公式编号 ──────────
# 🔴 只改**处方措辞**、不改**判定**：⑱ 报不报由 ①–④ 四条收紧决定，与习题语境无关。
# 把习题锚点整条静音会连「习题块里真丢的公式编号」一起放过——实测 复变函数论（钟玉泉
# 第五版）ch6：契约把「第六章习题」尾块折进 `定理6.13` 节点，印面 `(3)` 是 (一)1 的
# 小问标号，而该尾块**确实**整条丢了 (二)1(4) 一个积分式。
# 旧处方直说「回填契约 tag + manifest 后由单元补 \\tag{3}」，照做等于在印面没有公式
# 编号的地方**造一个编号**（随后会被 ⑭ 反向判成编造）。判据②认正文里的裸 `(N)`，
# 所以真修法是把标号恢复回正文、契约不动。
_EXERCISE_HEAD_RE = re.compile(
    r"^(?:>\s*)*(?:#{1,6}\s*)?(?:\*\*|__)?\s*"
    r"(?:第\s*[0-9一二三四五六七八九十百千零两]+\s*(?:章|节|单元|部分)\s*)?"
    r"(?:习题|练习(?:题)?|思考题|问题|Exercises?|Problems?|Questions?)"
    r"\s*(?:[（(][^（()）]{0,14}[）)])?\s*(?:\*\*|__)?\s*$")


def exercise_context_keys(unit_bodies):
    """``{契约节点 key: [单元正文, …]}`` → 正文里带**自成一行的习题标题**的键集合。

    只认整行形如 ``## 第六章习题`` / ``习题`` / ``**Exercises**`` 一类（可选 ``>`` 引用壳
    ——单元里习题尾块的标题实际写成 ``> ## 第六章习题``、可有 ``> >`` 嵌套、可选 ``#``/``**``
    包裹、可选「第 N 章/节/单元/部分」前缀、可选短括注尾），因此从句式散文
    （``由第五章习题（二)第14题，可知…``）不会被误认成标题——尾锚 `$` 把整行锁死。
    """
    out = set()
    for key, texts in (unit_bodies or {}).items():
        for t in texts or []:
            if any(_EXERCISE_HEAD_RE.match(line.strip())
                   for line in str(t or "").splitlines()):
                out.add(str(key))
                break
    return out


def _anchor_problems_for(tree, candidates, unit_bodies, chapter_label=""):
    """①–④ 收紧判据的**唯一实现**——检测趟与修复趟共用同一谓词。

    ``candidates`` = ``[(节点 key, 编号, 公式片段)]``，由调用方给出锚点来源
    （:func:`unharvested_anchor_tags` 整块-only 锚点 / :func:`glued_anchor_tags`
    粘连锚点）。判据与来源无关，因此两种锚点形态的**假阳率可比**。

    ``unit_bodies`` = ``{契约节点 key: [该节点的单元正文, …]}``（manifest 已登记的
    节点；未登记的节点 = 无落点，属 V-I 省略，不判）。

    四条收紧判据（全语料 477 章实测：只用「相邻 + 有单元记录」报 491 处、再加号
    形态与逃逸池报 96 处，四条后剩 22 处且逐处抽检为真漏 —— 判据保守，宁漏
    报不误报）：
    ① 节点须在 ``unit_bodies`` 里（无落点不判）；
    ② 该号在**同节**（无 § 祖先时退全章）单元正文里既不以 ``\\tag`` 也不以 ``(N)``
       出现过 —— 写手以别的排版形态渲染过 = 不算丢失；
    ③ 编号形态干净（``^[1-9][0-9]{0,2}[a-z]?$``）：``(00)``/``(000)`` 一类是 OCR
       碎片，不参与判漏；
    ④ 该号在印刷序列里**有邻居**（``N-1`` 或 ``N+1`` 出现在同一逃逸池里）：真漏的
       号总是连续号段里的一个洞；散文里的交叉引用 ``(3)``（"…use (3) also in
       connection with…"）自成一块却无邻居，据此排除。键含 ``-``（习题条目）一并
       排除——题号与公式号不同源。

    修法有**两条**，由 :func:`exercise_context_keys` 按节点选（只换措辞，不换判定）：
    * 普通节点 → 收割/回填：给该公式块补 `tag` + manifest `tags`，再让单元补
      `\\tag{}`；
    * 单元正文里带自成一行的习题标题的节点 → 先回印面裁向：印面 `(N)` 多半是小问
      标号，恢复进正文即可（判据②认），**不动契约、不写 `\\tag`**。
    两条都不许让写手凭空编号——那会被「契约 ↔ 单元 tag 对账」判成编造。旧措辞只有
    第一条，而「习题尾块折进邻近定理节点」的书（键里不含 `-`，④ 后半条例够不着）
    照它做就会造出不存在的公式编号。
    """
    bodies = {str(k): [t for t in (v or []) if t is not None]
              for k, v in (unit_bodies or {}).items()}
    node_pool = {k: set() for k in bodies}
    for k, texts in bodies.items():
        for t in texts:
            node_pool[k] |= rendered_numbers(t)
    sec_map = _sec_index(tree)
    ex_keys = exercise_context_keys(bodies)
    sec_pool, chapter_pool = {}, set()
    for k, pool in node_pool.items():
        chapter_pool |= pool
        s = sec_map.get(k)
        if s is not None:
            sec_pool.setdefault(s, set()).update(pool)
    out = []
    for key, num, frag in candidates:
        k = str(key)
        if k not in bodies:
            continue
        if not _CLEAN_NUM_RE.match(num):
            continue
        if "-" in k:
            continue
        s = sec_map.get(k)
        pool = sec_pool.get(s) if s is not None else chapter_pool
        if pool is None:
            pool = set()
        pool |= node_pool.get(k, set())
        if num in pool:
            continue
        try:
            base = int(_NUM_HEAD_RE.match(num).group(0))
            tail = num[len(str(base)):]
            nbr = {"%d%s" % (base - 1, tail), "%d%s" % (base + 1, tail)}
        except (AttributeError, ValueError):
            nbr = set()
        if not (pool & nbr):
            continue
        nbrs = "/".join(sorted(x for x in (pool & nbr) if x))
        evidence = ("印面编号 (%s) 在契约节点 %s 里以锚点文本块在档，但其展示式未登记 tag"
                    "（`%s…`），且该号在本节单元正文里整体消失（相邻号 %s 在账）"
                    % (num, key, frag, nbrs))
        if k in ex_keys:
            out.append(evidence +
                       "—— 收割漏号。🔴 该节点的单元正文里带**自成一行的习题标题**，"
                       "故印面 `(N)` 多半是**小题/小问标号**而非公式编号：先回印面裁向——"
                       "是小问标号 → 把 `(N)` 原样恢复进正文即可（判据②认这种形态，"
                       "契约不动、**不要写 \\tag**，写了就是凭空编号）；"
                       "确是公式编号 → 才走回填契约 tag + manifest 后由单元补 \\tag{%s}" % num)
        else:
            out.append(evidence +
                       "—— 收割漏号，须回填契约 tag + manifest 后由单元补 \\tag{%s}" % num)
    if chapter_label and out:
        out = ["[%s] %s" % (chapter_label, p) for p in out]
    return out


def unharvested_anchor_problems(tree, unit_bodies, chapter_label=""):
    """→ 闸门 ⑱ 问题列表：「整块只有 `(N)`」锚点一侧的收割漏号。

    判据见 :func:`_anchor_problems_for`（①–④ 四条收紧，全语料标定过）；候选来源
    见 :func:`unharvested_anchor_tags`。**行为与既往一致**——⑱ 的既有假阳率不变。
    """
    return _anchor_problems_for(tree, unharvested_anchor_tags(tree),
                                unit_bodies, chapter_label)


def glued_anchor_problems(tree, unit_bodies, chapter_label=""):
    """→ 粘连锚点（`(9) p(k)` / `(15) G(x) = ∑α(n)F` 一类）的收割漏号，**未接闸**。

    与 :func:`unharvested_anchor_problems` 共用 ①–④ 谓词，只差锚点形态。暂**不**
    并入闸门 ⑱：收紧判据会让**并行在跑**的书（同一技能、步骤 5 在飞）的旧 PASS
    作废；等其在跑书目收官后再把它拼进 `gate_units` 的 ⑱ 调用，并先跑跨书普查报
    backlog。当前用途 = 只读普查（`_extract/_probe_*.py`）+ 负向测试。
    """
    return _anchor_problems_for(tree, glued_anchor_tags(tree),
                                unit_bodies, chapter_label)


# ── 编号序列「空洞」判据（⑭/⑱ 与页池审计之外的第三条腿；纯函数，**未接闸**）────
# ⑭ 与 ⑱ 的搜索空间都是契约树：⑭ 问「契约挂的号印面有没有」，⑱ 问「契约在档的
# 锚点块公式挂上没」。收割把印面编号整块丢掉时，该号在契约里既无 ``tag`` 也无锚点
# 块，两闸同时失明。本判据只用一条**本书级不变量**补这个洞：**逐章连续编号**的书里，
# 一章登记的号集必须是 ``1..max`` 的**无洞前缀**——中间缺一个号 = 该号被收割丢了。
# 实测 Apostol《Introduction to Analytic Number Theory》15 处丢失（ch4 (52)、ch6 (12)、
# ch8 (14)(16)(26)、ch9 (30)(45)、ch12 (16)(28)(30)(31)(32)、ch13 (18)、ch14 (8)(25)）
# 全部由此判据一次性数出，而 ⑭/⑱/页池审计三者的实测 lost 均为 0。
#
# 判据边界（负向测试逐条锁住）：
# * **只判洞，不判截尾**：``max`` 之后的印面号看不见（那属 ⑱/粘连锚点）。
# * **先验序列形态**：``1..max`` 命中率 < ``_GAP_DENSITY`` 时判为「非逐章连续编号」
#   （按节重启编号的书，如 Strogatz；或只收割到零星号），**不出结论**。
# * 号形须干净（``_CLEAN_NUM_RE``）；字母尾巴（``12a``）随其数字头入序。
# * 该号若已在任一单元正文里以 ``\tag`` / ``(N)`` 出现过，**不报**——那是「契约缺档
#   而单元已渲染」，闸门 ⑭ 会以「编造」方向先报，此处重复报只会把两个修法混在一起。
_GAP_DENSITY = 0.8


def numbering_gaps(tree):
    """契约树 → ``[(缺号 int, 前一个在档号 or None, 后一个在档号 or None)]``。

    非逐章连续编号（命中率 < :data:`_GAP_DENSITY`）或无数字号时返回 ``[]``。
    """
    reg = set()
    for _key, num in collect_contract_tags(tree):
        if not _CLEAN_NUM_RE.match(num):
            continue
        m = _NUM_HEAD_RE.match(num)
        if m:
            reg.add(int(m.group(0)))
    if not reg:
        return []
    top = max(reg)
    if top < 2 or len(reg) / top < _GAP_DENSITY:
        return []
    out = []
    for n in range(1, top):
        if n in reg:
            continue
        lo = max((x for x in reg if x < n), default=None)
        hi = min((x for x in reg if x > n), default=None)
        out.append((n, lo, hi))
    return out


def numbering_gap_problems(tree, unit_bodies, chapter_label=""):
    """→ 编号序列空洞的问题列表（判据见模块内 ``# 编号序列「空洞」判据`` 段）。

    **未接闸**：这是**收紧**方向的判据，会让并行在跑的书（同一技能、步骤 5 在飞）
    的旧 PASS 作废；接闸前须先跑跨书普查并出 backlog。当前用途 = 只读普查 + 判据测试。
    """
    gaps = numbering_gaps(tree)
    if not gaps:
        return []
    rendered = set()
    for texts in (unit_bodies or {}).values():
        for t in texts or []:
            if t is not None:
                rendered |= rendered_numbers(t)
    out = []
    for n, lo, hi in gaps:
        if str(n) in rendered:
            continue
        out.append("本章印面编号 (%d) 在契约里整体无档（在档邻居：%s）且全章单元正文"
                   "也无该号 —— 逐章连续编号序列出现空洞 = 收割丢了印刷编号，"
                   "须按印刷证据回填契约 tag + manifest tags，再由单元补 \\tag{%d}"
                   % (n, "%s / %s" % (lo, hi), n))
    if chapter_label and out:
        out = ["[%s] %s" % (chapter_label, p) for p in out]
    return out


# ── 页池审计：编号列（⑭/⑱ 的**共同**盲区；检测趟与修复趟共用一个谓词）────────
# ⑭ 问「契约挂的号印面有没有」、⑱ 问「契约在档的锚点块公式挂上没」——**两者的搜索
# 空间都是契约树**。收割把某些 `(N)` 锚点整块当噪声丢弃时，该号在契约里既无 ``tag``
# 也无锚点块，两闸同时失明（实测 Apostol《Introduction to Analytic Number Theory》
# 多个写手批次独立登记：ch6 (12)、ch8 (14)(16)、ch11 (16)、ch12 (16)(28)(30)(31)(32)、
# ch13 (18)、ch14 (8) 印面有号而契约无档，写手按契约对账看不见自己少写一个号）。
# 同一盲区的**反方向**：OCR 把公式**内部**括号切成独立块（``ζ(4)`` 的 ``(4)``），收割
# 把它当编号挂上 → 契约多出一个印面不存在的号（实测 ch11 Exercise 15 的双和展示式，
# fitz 目视确认该展示式左右均无编号；旧 ⑭ 拦不住，因为 ``(4)`` 确实"在页上"）。
#
# 判据只用**页池 + 几何**，不依赖契约树里是否留有锚点块：
# ① 整块形如 `(N)`，允许 ≤1 个字母 + ≤3 个线状符号的 OCR 残渣（`(16s)`、`(28\`）；
#    左括号本身也允许是 OCR 腐蚀形（`C4)` / `G4)` / `[4)`——实测 Apostol ch2 印面
#    `(4)` 收成 `C4)`，旧正则整类失明）；`glued=True` 时另收「编号 + 公式残渣」的
#    **粘连块**（谓词与闸门 ⑱ 的粘连探测同一条，见 :func:`page_anchor_index`）；
# ② 该块落在本章**编号列**里——列区间**不写死**，由本章契约**已登记**的号所在列
#    学出（本书印在左缘 x0≈55–160/966；右缘排版的书会自动落到右缘）；列种子**只取
#    独立块**，粘连块只参与筛列；
# ③ 号形干净（1–3 位数字，可选一个字母尾巴）。
# 输出两个方向：``lost`` = 在列内而契约无档（收割漏号，须回填契约 tag + manifest）；
# ``unsupported`` = 契约有档而全章找不到在列锚点（假 tag，须从契约剔除）。
_PAGE_ANCHOR_RE = re.compile(
    r"^[（(\[CG]\s*([0-9]{1,3}[a-z]?)[)）\\|]?\s*([A-Za-z]?[\\|]{0,3})$")
_COLUMN_WINDOW = 120.0      # 编号列的滑动窗口宽度（与页内坐标同单位）
_COLUMN_MIN_SAMPLES = 3     # 少于这么多在列样本就不学列（无从判据 → 不出结论）
# 列**接受带**在簇两端各外扩这么多（同单位）。动因 = Apostol IANT 实测：同一列里
# 独立锚点的 x0 跨 54–193（200-dpi 像素），而簇窗口只有 120，`min..max` 的接受带
# 把 `(19)@(185)`、`(24)@(65)`、`(4)@(187)` 这类**页边**号判成列外，`unsupported`
# 方向因此把 27/35 个真印编号误报成假 tag。外扩 40 后上界 ≈232，而本书正文/公式块
# 起点 ≥328（实测 ch10 `(2k+1)²` 在 328/330），仍留 ~90 像素余量，不会把公式内部
# 括号放进来。
_COLUMN_PAD = 40.0
# 编号列与**正文区**必须可分，否则几何判据不成立。本书实测：页边编号 `(3)` 在
# x0=86、`C4)` 在 79，而散文行长块的左缘就在 68–71——**同一 x 带上混着编号和散文**，
# 列筛选退化成「左半页都算列」，`unsupported` 因此把 35 个真印编号误报成假 tag
# （实测本书 15 章全部不可分）。不可分时本审计**不出结论**（两向都空），把判断
# 让给 :func:`numbering_gaps`（不依赖几何）。两侧各留这么多同单位余量才算可分。
_COLUMN_SEP = 20.0
_SEP_TEXT_MIN = 40          # 长块（≥此字符数）= 散文 / 整行公式，用作正文左右缘的锚


def page_geom_loader(*dirs):
    """→ ``load(pdf_page)`` = ``[(raw, x0, x1, y0)]`` 或 None。

    与 :func:`dir_page_loader` 同一读页口径（``text`` 摊平 + ``formulas`` 的 latex），
    差别只在**保留横向位置**——编号列判据需要 x 坐标。找不到页文件返回 None。
    """
    import json
    import os

    cache = {}

    def _flat(s):
        if isinstance(s, dict):
            s = s.get("text")
        return str(s or "")

    def load(pg):
        if pg in cache:
            return cache[pg]
        val = None
        for d in dirs:
            if not d:
                continue
            for name in ("page_%03d.json" % pg, "page_%d.json" % pg,
                         "page_%04d.json" % pg):
                p = os.path.join(d, name)
                if not os.path.exists(p):
                    continue
                try:
                    with open(p, encoding="utf-8") as f:
                        d_ = json.load(f)
                except Exception:
                    d_ = {}
                rows = []
                for b in (d_.get("text") or []):
                    poly = b.get("poly") or []
                    if len(poly) < 4:
                        continue
                    rows.append((_flat(b.get("text")).strip(),
                                 float(poly[0]), float(poly[2]), float(poly[1])))
                for b in (d_.get("formulas") or []):
                    bb = b.get("bbox") or []
                    if len(bb) < 4:
                        continue
                    rows.append((str(b.get("latex") or "").strip(),
                                 float(bb[0]), float(bb[2]), float(bb[1])))
                val = rows
                break
        cache[pg] = val
        return val

    return load


def page_anchor_index(geom_loader, lo, hi, glued=False):
    """页窗 → ``[(num, page, x0, y0)]``：满足判据 ①③ 的块，**未**筛列。

    ``glued=False``（默认）与既往一致：**只**认整块形如 ``(N)``（可带字母尾巴 /
    线状残渣）的独立锚点。``glued=True`` 时**额外**收「粘连锚点」——OCR 把页边编号
    与同一行的公式残渣切成一块（实测 Apostol IANT ch7 ``(9) p(k)``、ch6 ``(12) B(x) =
    ∑χ(d)/√(qd)``），这类块对整块-only 判据完全隐形，于是本审计的 ``unsupported``
    方向会把**真印的**契约号误报成假 tag（本书普查实测 lost=0 / unsupported=19，
    19 全是这类误报）。

    🔴 粘连形态**复用**闸门 ⑱ 的同一谓词（:data:`_ANCHOR_GLUED_RE` +
    :data:`_RESIDUE_PROSE_RE` 散文排除），不另起正则——检测趟与修复趟共用判据，
    两处的假阳率才可比。粘连块的 ``x0`` 仍是**编号**的左缘（编号在页边，是该块最左
    的文字），所以「编号列」几何约束照旧成立，列本身仍只由独立锚点学出（见
    :func:`margin_anchor_audit`），不被粘连样本污染。
    """
    out = []
    for pg in range(int(lo), int(hi) + 1):
        rows = geom_loader(pg)
        if not rows:
            continue
        for raw, x0, _x1, y0 in rows:
            m = _PAGE_ANCHOR_RE.match(raw)
            if m:
                out.append((m.group(1), pg, x0, y0))
                continue
            if not glued:
                continue
            g = _ANCHOR_GLUED_RE.match(raw)
            if not g:
                continue
            residue = g.group(2)
            if _RESIDUE_PROSE_RE.search(residue):
                continue
            if _ANCHOR_ONLY_RE.match(residue):
                continue
            out.append((g.group(1), pg, x0, y0))
    return out


def number_column(anchors, seed_nums):
    """在列样本 → ``(x_lo, x_hi)``；样本不足返回 None（不出结论）。

    列由 ``seed_nums``（= 本章契约**已登记**的号）所在块的 x0 学出：取宽度
    ``_COLUMN_WINDOW`` 的滑动窗口里样本最多的那一簇，故个别被切进公式区的假锚点
    （实测 ch11 的 ``(4)`` 落在 x0=674）不会把列拉过去。接受带在簇两端各外扩
    ``_COLUMN_PAD``（同页内坐标单位）——OCR 块左缘在同一列里就有 ~140 像素的抖动，
    只取 ``min..max`` 会把真印的页边号判成列外（误报根因，见 ``_COLUMN_PAD`` 注）。
    """
    xs = sorted(x for n, _p, x, _y in anchors if str(n) in seed_nums)
    if len(xs) < _COLUMN_MIN_SAMPLES:
        return None
    best = []
    for i, v in enumerate(xs):
        run = [u for u in xs[i:] if u <= v + _COLUMN_WINDOW]
        if len(run) > len(best):
            best = run
    return (min(best) - _COLUMN_PAD, max(best) + _COLUMN_PAD)


def column_separable(geom_loader, lo, hi, col):
    """→ 编号列与**正文区**是否可分（判据见 ``_COLUMN_SEP`` 注）。

    不可分 = 页边编号与散文行落在同一 x 带上（实测 Apostol IANT 全部 15 章如此），
    此时「在列」退化成「在左半页」，几何筛失去判别力，本审计**无权出结论**。
    正文左/右缘取长块（≥ ``_SEP_TEXT_MIN`` 字符）x0 的 5 分位、x1 的 95 分位——
    用分位数而非极值，避免单个页眉/页脚块把结论带偏。
    """
    if not col:
        return False
    lefts, rights = [], []
    for pg in range(int(lo), int(hi) + 1):
        for raw, x0, x1, _y0 in (geom_loader(pg) or []):
            if len(raw) < _SEP_TEXT_MIN:
                continue
            lefts.append(x0)
            rights.append(x1)
    if len(lefts) < _COLUMN_MIN_SAMPLES:
        return False
    lefts.sort()
    rights.sort()
    body_left = lefts[int(0.05 * (len(lefts) - 1))]
    body_right = rights[int(0.95 * (len(rights) - 1))]
    return (col[1] + _COLUMN_SEP <= body_left) or \
           (col[0] - _COLUMN_SEP >= body_right)


def margin_anchor_audit(tree, geom_loader, chapter_label="", glued=False):
    """契约 ↔ 页池编号列 双向对账 → ``(lost, unsupported)`` 两向问题列表。

    ``glued=True`` 时页池**额外**收粘连锚点块（判据与排除见
    :func:`page_anchor_index`）：页边编号被 OCR 与公式切成同一块的书里，不开这个
    开关会把**真印的**契约号成批误报成假 tag。列的**种子**始终只取独立锚点，
    粘连样本只参与筛列、不参与学列。

    * ``lost``：页池在列锚点里、契约 tag 集合**没有**的号 → 收割漏号。修法在
      收割/回填（契约补 ``tag`` + manifest 补 ``tags`` → 单元补 ``\\tag{}``），
      **不是**让写手凭空编号（那会被「多出=编造」判死）。
    * ``unsupported``：契约登记了、全章在列锚点里**查无此号** → 假 tag（多半是
      公式内部括号被切成独立块）。

    🔴 **暂不接闸**：这是收紧判据，会让并行在跑的书（同一技能、步骤 5 在飞）的旧
    PASS 作废；先做只读普查 + 负向测试，收官 backlog 里再拼进 `gate_units`。
    """
    try:
        lo, hi = int(tree.get("page_start")), int(tree.get("page_end"))
    except (TypeError, ValueError):
        return [], []
    seeds = page_anchor_index(geom_loader, lo, hi)
    anchors = seeds if not glued else page_anchor_index(geom_loader, lo, hi,
                                                       glued=True)
    if not anchors:
        return [], []
    contract = {str(n) for _k, n in collect_contract_tags(tree)}
    col = number_column(seeds, contract)
    if not col or not column_separable(geom_loader, lo, hi, col):
        return [], []
    in_col = [a for a in anchors if col[0] <= a[2] <= col[1]]
    nums = {str(n) for n, _p, _x, _y in in_col}
    lost = sorted(nums - contract, key=lambda s: (len(s), s))
    unsupported = sorted(contract - nums, key=lambda s: (len(s), s))
    where = ("[%s] " % chapter_label) if chapter_label else ""
    lost_msg = ["%s印面编号 (%s) 在编号列 x0≈%.0f–%.0f 内成块（p%s%s），"
                "契约却无档 —— 收割漏号，须回填契约 tag + manifest 后由单元补 \\tag{%s}"
                % (where, n, col[0], col[1],
                   ",".join(str(p) for m, p, _x, _y in in_col if str(m) == n),
                   "，粘连形态" if glued else "", n)
                for n in lost]
    uns_msg = ["%s契约登记编号 (%s)，但全章编号列里查无该锚点 —— 疑似公式内部括号"
               "被切成独立块的假 tag，须从契约剔除（先目视印面确认）" % (where, n)
               for n in unsupported]
    return lost_msg, uns_msg

