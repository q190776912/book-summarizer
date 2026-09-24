"""Shared numbering regexes and label maps for book-summarizer.

Centralizes constants that were duplicated across extractors/verifiers — most
notably the Hilton & Stammbach two-level "section.item" scheme, which was
copied verbatim in both ``extract_items_hom.py`` and ``verify_hom.py``.
Importing from here keeps the two scripts in sync (one source of truth).
"""

import functools
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))

import re

# --- H&S two-level "section.item" scheme (NO chapter digit) ---
# Chapters are ROMAN (I..IX) and are not part of item numbers; items are
# numbered per section: "Theorem 2.1", "Proposition 3.1", "Definition 1.1" ...
HOM_ITEM_RE = re.compile(
    r'(定义|定理|引理|推论|命题|Definition|Theorem|Lemma|Corollary|Proposition)'
    r'\s*[（(]?\s*(\d{1,2})\.(\d{1,3})[）)]?')
HOM_EX_RE = re.compile(r'(例|Example)\s*\(?(\d{1,2})(?:\.(\d{1,3}))?\)?')

# citation words that mark a cross-reference rather than a definition
HOM_CITE_RE = re.compile(r'(见|由|根据|参考|参见|据|cf\.|see|by|from|in)\s*$', re.I)

HOM_LABEL_MAP = {'定义': '定义', '定理': '定理', '引理': '引理', '推论': '推论',
                 '命题': '命题', 'Definition': '定义', 'Theorem': '定理',
                 'Lemma': '引理', 'Corollary': '推论', 'Proposition': '命题'}

HOM_MD_ENTRY_RE = re.compile(r'\*\*(定义|定理|引理|推论|命题)\s*(\d{1,2})\.(\d{1,3})')

# ---------------------------------------------------------------------------
# Canonical ordinal-depth map（唯一真源）
# ---------------------------------------------------------------------------
# Numbering depth (= number of numeric components) per ordinal style code.
# 🔴 这是 `ORDINAL_DEPTH` 的**唯一定义处**——`config/verify_config/verify_config.py`
# 与 `lib/figure_io.py` 一律从这里导入，禁止再各抄一份（抄副本必然漂移）。
ORDINAL_DEPTH = {0: 0, 1: 1, 2: 2, 3: 3, 8: 3, 12: 1,
                 # 0 = UNNUMBERED：条目**不带任何编号**（无数字分量 ⇒ 段数 0）。
                 # 它是「未声明 ordinal」的内部兜底组，也可由用户显式声明
                 # （`{"type": 0, ...}` 表示本书条目无编号）。🔴 必须登记 0，否则
                 # `ORDINAL_DEPTH.get(0, 3)` 会给无编号组安上 depth=3 的幻影默认。
                 # 🔴 已弃用码：4(EN 两级)→2、9(EN3)→3、10(CN3LAB)→3、11(Ross)→1；
                 #    映射表 = 本文件下方 DEPRECATED_ORDINAL_REMAP（唯一真源，
                 #    verify_config 只再导出）；BookConfig.from_dict 在加载时映射，
                 #    运行时不再直接识别（见 verify_config.md）。直读 raw config
                 #    的消费方须自调 resolve_ordinal_code 归一。
                 # 13 = ORDINAL_APP：附录字母章号三级体例 `Label A.1.1`（章位是
                 # 字母 A/B/C…，后跟 节.号 两个数字段），段数同样是 3。
                 13: 3,
                 # 14 = ORDINAL_APP2：附录字母章号两段体例 `Label B.N`（Lee ISM
                 # 附录实测：条目/练习均无节段），章位字母 + 1 个数字段。
                 14: 2}


class OrdinalDepthError(KeyError):
    """An ordinal `type` code has no registered depth in `ORDINAL_DEPTH`.

    This is a registration/config bug — never a signal to fall back to a
    phantom depth (e.g. 3). Callers must surface it, not swallow it.
    """


def ordinal_depth(ocode):
    """Return the numeric component count (depth) for ordinal style `ocode`.

    🔴 NO DEFAULT. `ocode` MUST be a registered key of `ORDINAL_DEPTH`; an
    unregistered code is a registration/config bug and raises `OrdinalDepthError`
    immediately instead of silently mapping to a phantom depth (e.g. 3).

    `ocode is None` is NOT a default — it is the explicit "no ordinal group"
    signal and returns `None`, so callers that legitimately handle unconfigured
    books can keep doing so. They decide what (if anything) to do; this function
    never substitutes a depth for a missing code.
    """
    if ocode is None:
        return None
    try:
        return ORDINAL_DEPTH[ocode]
    except KeyError:
            raise OrdinalDepthError(
            f"ordinal type {ocode!r} 未登记 depth：须在 ORDINAL_DEPTH 注册 "
            f"（合法码 {sorted(ORDINAL_DEPTH)!r}）")


# ---------------------------------------------------------------------------
# Deprecated ordinal codes（弃用码 -> 就近体例码）——唯一真源
# ---------------------------------------------------------------------------
# 🔴 与 ORDINAL_DEPTH 同处定义，`config/verify_config/verify_config.py`
# 只做再导出，其余消费方（lib/figure_io、verify/formula_tag、
# flows/…/attach_content、flows/…/scan_skeleton）一律从这里导入，
# **禁止各抄一份字面量**——抄副本必然漂移。
DEPRECATED_ORDINAL_REMAP = {4: 2, 9: 3, 10: 3, 11: 1}


def resolve_ordinal_code(ocode):
    """Normalise a possibly-deprecated ordinal `type` before `ordinal_depth`.

    `ordinal_depth` 对未登记码（含已弃用的 4/9/10/11）**硬报错是故意的**：
    注册/配置 bug 必须暴露，不做静默兜底。但**直读 raw verify_config.json**
    的消费方不经过 `BookConfig.from_dict` 的归一，拿到的可能正是存量弃用码，
    它们必须先调本函数归一再交给 `ordinal_depth`，否则存量 type-4 书会直接
    崩溃（实测：Koopman 全书 `verify --all` 先后崩于 figure_io 与 formula_tag）。
    """
    if ocode is None:
        return None
    return DEPRECATED_ORDINAL_REMAP.get(ocode, ocode)


# ---------------------------------------------------------------------------
# Figure-label 判据（fig/Figure/图）——唯一真源
# ---------------------------------------------------------------------------
# `ordinal` 里的 Figure 组是**图像管线**关注点（其计数器编的是图注、不是正文
# 条目）。`BookConfig.primary_group` 必须跳过 figure-only 组：否则 Vakil 体例书
# （正文共享计数器声明为 `uncat` 兜底组 + 独立 Figure 组）里 Figure 组会劫持
# `primary_type`，抽取器分派 / skeleton mode 全部错路（Rising Sea 实测：ch1
# 76 条目被静默丢弃、items=0）。消费方：lib/figure_io、
# config/verify_config/{verify_config, make_config}——**禁止再各抄副本**。
_FIG_LABEL_KW = ("fig", "figure")


def is_fig_label_name(name):
    """True iff `name` is a figure-label keyword (Fig / Figure / 图)."""
    s = str(name)
    if "图" in s:
        return True
    return re.sub(r"[^a-z]", "", s.lower()) in _FIG_LABEL_KW


def is_fig_group(group):
    """True iff an ordinal group (dict 或 GroupConfig) 的全部 name 都是图注标签。"""
    if isinstance(group, dict):
        names = group.get("name") or []
    else:
        names = getattr(group, "name", None) or []
    names = list(names)
    return bool(names) and all(is_fig_label_name(n) for n in names)


# ---------------------------------------------------------------------------
# 练习条头形态判定（number-first 字母练习书，如 Vakil《The Rising Sea》）——SSOT
# ---------------------------------------------------------------------------
# 字母体例书（EXER 头 "C.S.A. EASY EXERCISE. ..."）里，OCR 会把字母练习号的
# 字形读成数字（O→0、I→1，Rising Sea 全书实测 58 处），产生 "C.S.0." / "C.S.1."
# 假数字头。真数字条目头（"10.1.1. Motivation."）与跨引用行
# （"24.5.11. Exercise 24.5.M can be improved:"）不带练习头形态，必须区分开：
#   * 练习头形态 = [可选修饰词] + EXERCISE(S) 关键词 + 边界（. : ( / 或行尾，
#     可再带括号修饰语，如 "EXERCISE (CF. EXERCISE 3.5.B)."）；
#   * 跨引用 = 关键词后紧跟编号引用（"Exercise 24.5.M"）或散文。
# 消费方：scan_skeleton（数字头→字母 EXER 恢复 + 无关键词幻影头压制）、
# extract_items_vakil（跳过字形乱码练习头、装饰性 Exercise 引用不得染指
# label→type）。**禁止在脚本里各抄副本**。
_EXERCISE_WORD_RE = re.compile(r'\bEXERCISES?\b', re.I)
# 🔴 题头词形（Rising Sea 全书 1466 条印刷条头 + OCR 漂移形态逐条枚举）：
# 旧正则允许任意前导散文（`[A-Za-z][A-Za-z ]{0,44}` + re.I），条目头
# "0.0.1. The importance of exercises. This book…" 的「…of exercises.」被
# 当成习题头 → 真条目被乱码恢复改写成幻影习题。判据（印刷真身=首字母
# 大写修饰词 + EXERCISE(S) + 边界；OCR 叠加大小写漂移）：
#   * 修饰语：`[A-Z][A-Za-z]*[ ]` 重复（A SMALL / LESS IMPORTANT / EAsy…）,
#     行首允许难度星标装饰（⋆/★/*/+/×）；
#   * 关键词枚举：EXERCISE(S) 全大写族 + 实测小写漂移族（ExERCISE /
#     ExERCIsE / EXERcISE / EXERCISe / EXERCIS 截断）；**裸小写
#     exercise(s)（散文）必拒**；"Exercise" 首字母大写形仅当后不接
#     空格+数字（排除跨引用 "Exercise 24.5.M"）；
#   * 边界：`[.:!/“"(]` 或行尾（印刷实测：'.' 623 / ' (X' 括注 / ':' /
#     '/DEFINITION' / ' FOR|AND|TO' 短语形）；括注体大小写不限。
# 整条**不得**加 re.I（会让修饰语类 [A-Z] 同时吞小写，收紧形同虚设）。
_EXERCISE_DECOR = r'(?:[\s⋆★*\u2605\u2606+x\u00d7])*'
# 全形（后随字符不限，短语形 "EXERCISE FOR THOSE…" 靠边界组裁决）与
# 截断形（EXERCIS / EXERCI，OCR 行尾截断实测）分开：截断形必须
# `(?![A-Za-z])`（否则把完整单词的尾巴当修饰）。
_EXERCISE_KEYWORD = (
    r'(?:EXERCISES?|ExERCISES?|ExERCIsE|EXERcISE|EXERCISe|E[Xx]ERCIS[Ee]'
    r'|Exercise(?!\s\d)'
    r'|(?:EXERCIS|EXERCI)(?![A-Za-z]))')
_EXERCISE_MOD = r'(?:(?:[A-Z][A-Za-z]*|\([A-Za-z0-9 ,.;:\-\u2019]{0,60}\))[ ])'
_EXERCISE_HEAD_RE = re.compile(
    r'^' + _EXERCISE_DECOR + _EXERCISE_MOD + r'*' + _EXERCISE_KEYWORD +
    r'(?:\[[^\]]{0,80}\]|\([^\)]{0,80}\)?)?'
    r'(?:\s*[.:!/“"(]|,|\s*[–—-]|\s(?:[A-Z][^ ]*[ ])*[A-Z]+(?![A-Za-z])|\s*$)')


def has_exercise_word(text):
    """True iff `text` contains the EXERCISE keyword anywhere (case-insensitive)."""
    return bool(_EXERCISE_WORD_RE.search(text or ''))


def is_exercise_head_text(text):
    """True iff `text` (编号头之后的同行动) starts like an exercise HEAD:
    optional modifier words + EXERCISE(S) + boundary punctuation.
    False for prose cross-references like "Exercise 24.5.M can be improved:"."""
    return bool(_EXERCISE_HEAD_RE.match((text or '').strip()))


# ---------------------------------------------------------------------------
# Formula sequence labels（公式序标）——形态按书配置派生，禁止硬编码一种
# ---------------------------------------------------------------------------
# 🔴 各书公式编号形态差异极大（2026-08-29 全语料实测），绝不可以用一条
# `(C.N)` 正则打天下。段数（ncomp）由 `verify_config.json` 的 `formula.type`
# 经 `ORDINAL_DEPTH` 派生；括号 / 分隔符 / 字母后缀按实测形态全量覆盖：
#
#   (1) / （1）        ncomp 1  节级重置：Kreyszig、Evans SDE、PDE、黎曼几何、
#                               经典力学、Analytic Number Theory…
#   (2.17)             ncomp 2  章.号：Koopman、Leinster、微分遍历论、实变函数…
#   (11.1-1)           ncomp 3  章.节-号：Chaos/Fractals/Noise、高等代数、
#                               概率论与数理统计…（分隔符是 `-` 不是 `.`）
#   2,3 / 1-2          分隔符还有 `,` 与 `-`（Ross、遍历论实测）
#   (8.11a)            字母后缀子式（Evans SDE、PDE、Ross 实测）
#   裸排 2.17          大量书右缘编号**不带括号**（bare 形态，占实测近一半）
#   (A.3) / （A.3）    字母章位编号（Lee ISM 附录 B.1-B.15/C.1-C.21/D.1-D.21
#                      实测）：首段单个大写字母、后续段纯数字——`letter=True`
#                      分支支持（2026-09-14）。仅接受**带括号**形态：裸排 `A.3`
#                      与 `Fig. A.3` / 小节标题 `C.1` 无法区分，宁缺勿滥。
#                      多字母前缀（罗马 `II.5`、`App.2`）仍暂不支持，由 Q 层
#                      `_LETTER_LED_RE` 探测兜 WARN（两处注释互为锚点）。
_FORMULA_SEP = r'[.\-·,]'                 # 编号分隔符：点 / 连字符 / 间隔号 / 逗号
_FORMULA_SUFFIX = r'(?:[a-zA-Z])?'        # 子式字母后缀：`8.11a`


def formula_num_core(ncomp=None, letter=False):
    r"""公式编号 token 的正则源（**不含括号**、**不锚定**、**无捕获组**）。

    `ncomp` = 段数（由 `formula.type` 经 `ORDINAL_DEPTH` 派生）；``None`` = 段数
    不限（书未配置 `formula` 块时的兜底，如集合论/表示论等无编号公式的书）。

    `letter=True`：字母章位编号（`(A.3)`）——首段是**单个大写字母**，其余段纯
    数字。`ncomp=2` → ``[A-Z][SEP]\d+``；``None`` → 至少一个数字段。纯单字母
    ``[A-Z]``（无数字段）不构成公式序标，故数字段数下限为 1。
    """
    if letter:
        n_min = 1  # 数字段数下限：`(A)` 不是公式编号
        if ncomp is None:
            return r'[A-Z](?:%s\d+){%d,}%s' % (_FORMULA_SEP, n_min, _FORMULA_SUFFIX)
        try:
            n = max(0, int(ncomp) - 1)
        except (TypeError, ValueError):
            n = 0
        return r'[A-Z](?:%s\d+){%d}%s' % (_FORMULA_SEP, max(n, n_min), _FORMULA_SUFFIX)
    if ncomp is None:
        return r'\d+(?:%s\d+)*%s' % (_FORMULA_SEP, _FORMULA_SUFFIX)
    try:
        n = max(0, int(ncomp) - 1)
    except (TypeError, ValueError):
        n = 0
    return r'\d+(?:%s\d+){%d}%s' % (_FORMULA_SEP, n, _FORMULA_SUFFIX)


@functools.lru_cache(maxsize=None)
def formula_tag_re(ncomp=None, bare=True, letter=False):
    """匹配「**整块**恰为一个公式编号」的锚定正则。

    `bare=True` 时额外接受**无括号裸排**编号（右缘编号不带括号的书占实测近
    一半，不可或缺）。需要严格判据时（如噪声过滤的页码豁免）用 `bare=False`。

    `letter=True`（字母章位 `(A.3)`）时 `bare` 强制无效——只返回带括号变体：
    裸排 `A.3` 与 `Fig. A.3` / 小节标题 `C.1` 无形态区别（宁缺勿滥，见头部
    注释）。
    """
    core = formula_num_core(ncomp, letter=letter)
    return re.compile(r'^(?:%s)$' % '|'.join(_formula_tag_variants(ncomp, bare, letter)))


def _formula_tag_variants(ncomp=None, bare=True, letter=False):
    """公式编号的**形态变体**列表（唯一构造处，`formula_tag_re` / 末尾编号正则共用）。

    🔴 两处必须共用同一份变体：各抄一份必然漂移（裸排 / 字母章位的开关逻辑
    已踩过一次）。
    """
    core = formula_num_core(ncomp, letter=letter)
    variants = [r'[（(]\s*%s\s*[）)]' % core]        # (2.17) / （A.3）
    if bare and not letter:
        variants.append(core)                        # 裸排 2.17
    return variants


def formula_tag_tail_re(ncomp=None, bare=True, letter=False):
    """**只锚定结尾**的编号正则（供 :func:`formula_trailing_tag`）。

    :func:`formula_tag_re` 两端锚定（整块恰为编号），在「公式文本 + 末尾编号」
    这种长文本块里 `finditer` 必然匹配不到，故末尾编号需要本变体。
    """
    return re.compile(r'(?:%s)$'
                      % '|'.join(_formula_tag_variants(ncomp, bare, letter)))


@functools.lru_cache(maxsize=None)
def formula_paren_tag_re(ncomp=None, letter=False):
    """只认**带括号**的公式编号（半角 / 全角）。

    用于「页码过滤豁免」一类需要零误判的场合：页码永远不会被写成 `(99)`，
    但裸排的 `99` 与页码无法区分，故裸排不享受豁免。
    """
    return formula_tag_re(ncomp, bare=False, letter=letter)


def formula_tag_number(text, ncomp=None, letter=False, bare=True):
    """整块恰为公式编号时返回**裸编号**（去括号 / 去空白），否则返回 ``None``。

    `bare=False`：只认带括号形态（`verify_config.json` 的
    `formula.bare_number: false` 书——如 Lee——散文里裸排 `1-11` Problem 标签
    不可当编号）。`letter=True` 时 `bare` 强制无效（见 `formula_tag_re`）。
    统一返回裸编号，让契约 `tag`、草稿 `\\tag{}` 与 Q 层 `norm()` 三处口径一致。
    """
    m = formula_tag_re(ncomp, bare=bare, letter=letter).match((text or '').strip())
    if not m:
        return None
    s = m.group(0).strip()
    if len(s) > 1 and s[0] in '（(' and s[-1] in '）)':
        return s[1:-1].strip()
    return s


def formula_trailing_tag(text, ncomp=None, letter=False, bare=True):
    """文本**末尾**粘着公式编号时返回 ``(裸编号, 匹配原文)``，否则 ``None``。

    成因：OCR 有时把「公式文本 + 右缘编号」读成**一个**文本块（Koopman 实测
    ``'(y(t)-h(x(t)))…dt.  (3.35)'``、``'…, p_0 := p(0,x)， (8.9)'``），而
    :func:`formula_tag_number` 要求整块恰为一个编号，这类永远匹配不上 →
    编号挂不上 tag、掉进散文。本函数只认**紧贴结尾**的编号，且其前一个字符须
    为空白或标点（防 ``abc(3.5)`` 这类粘连）。

    🔴 调用方**仍须**用几何护栏确认它确实是某条 display 公式的行尾编号——
    散文行末尾同样可能以交叉引用 ``(6.20),`` 结尾（见 ``attach_content``：
    要求与 display 公式实质垂直重叠，实测真例 91–100%、反例 ov<0）。
    """
    s = (text or '').strip()
    if not s:
        return None
    m = formula_tag_tail_re(ncomp, bare=bare, letter=letter).search(s)
    if m is None:
        return None
    # 前一字符须为空白或标点（防 `abc(3.5)` 这类与词粘连）。含 OCR 常见替身：
    # 右单引号 ’ / 右双引号 ” / 直角引号 ’（实测 Koopman 15.57 写作 `…z2’(15.57)`）。
    if m.start() > 0 and not re.match(r"[\s,，.。;；:：)\]】、’”'\"）]", s[m.start() - 1]):
        return None
    raw = m.group(0).strip()
    if len(raw) > 1 and raw[0] in '（(' and raw[-1] in '）)':
        return raw[1:-1].strip(), raw
    return raw, raw
