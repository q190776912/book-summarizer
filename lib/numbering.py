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
ORDINAL_DEPTH = {1: 1, 2: 2, 3: 3, 4: 2, 5: 3, 6: 2, 8: 3, 9: 3, 10: 3, 11: 2, 12: 2,
                 # 13 = ORDINAL_APP：附录字母章号三级体例 `Label A.1.1`（章位是
                 # 字母 A/B/C…，后跟 节.号 两个数字段），段数同样是 3。
                 13: 3}


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
#   (A.3) / （I.2）    字母 / 罗马开头 —— 暂不支持（Q 层同源 TODO，见
#                      verify/formula_tag/script/formula_tag.py）；此处保持同
#                      步不支持，否则 attach 会挂上 Q 层判 FABRICATED 的编号。
_FORMULA_SEP = r'[.\-·,]'                 # 编号分隔符：点 / 连字符 / 间隔号 / 逗号
_FORMULA_SUFFIX = r'(?:[a-zA-Z])?'        # 子式字母后缀：`8.11a`


def formula_num_core(ncomp=None):
    """公式编号 token 的正则源（**不含括号**、**不锚定**、**无捕获组**）。

    `ncomp` = 段数（由 `formula.type` 经 `ORDINAL_DEPTH` 派生）；``None`` = 段数
    不限（书未配置 `formula` 块时的兜底，如集合论/表示论等无编号公式的书）。
    """
    if ncomp is None:
        return r'\d+(?:%s\d+)*%s' % (_FORMULA_SEP, _FORMULA_SUFFIX)
    try:
        n = max(0, int(ncomp) - 1)
    except (TypeError, ValueError):
        n = 0
    return r'\d+(?:%s\d+){%d}%s' % (_FORMULA_SEP, n, _FORMULA_SUFFIX)


@functools.lru_cache(maxsize=None)
def formula_tag_re(ncomp=None, bare=True):
    """匹配「**整块**恰为一个公式编号」的锚定正则。

    `bare=True` 时额外接受**无括号裸排**编号（右缘编号不带括号的书占实测近
    一半，不可或缺）。需要严格判据时（如噪声过滤的页码豁免）用 `bare=False`。
    """
    core = formula_num_core(ncomp)
    variants = [r'[（(]\s*%s\s*[）)]' % core]        # (2.17) / （2.17）
    if bare:
        variants.append(core)                        # 裸排 2.17
    return re.compile(r'^(?:%s)$' % '|'.join(variants))


@functools.lru_cache(maxsize=None)
def formula_paren_tag_re(ncomp=None):
    """只认**带括号**的公式编号（半角 / 全角）。

    用于「页码过滤豁免」一类需要零误判的场合：页码永远不会被写成 `(99)`，
    但裸排的 `99` 与页码无法区分，故裸排不享受豁免。
    """
    return formula_tag_re(ncomp, bare=False)


def formula_tag_number(text, ncomp=None):
    """整块恰为公式编号时返回**裸编号**（去括号 / 去空白），否则返回 ``None``。

    统一返回裸编号，让契约 `tag`、草稿 `\\tag{}` 与 Q 层 `norm()` 三处口径一致。
    """
    m = formula_tag_re(ncomp).match((text or '').strip())
    if not m:
        return None
    s = m.group(0).strip()
    if len(s) > 1 and s[0] in '（(' and s[-1] in '）)':
        return s[1:-1].strip()
    return s
