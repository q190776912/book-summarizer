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
ORDINAL_DEPTH = {0: 0, 1: 1, 2: 2, 3: 3, 4: 2, 5: 3, 6: 2, 8: 3, 9: 3, 10: 3, 11: 2, 12: 2,
                 # 0 = UNNUMBERED：条目**不带任何编号**（无数字分量 ⇒ 段数 0）。
                 # 它是「未声明 ordinal」的内部兜底组，也可由用户显式声明
                 # （`{"type": 0, ...}` 表示本书条目无编号）。🔴 必须登记 0，否则
                 # `ORDINAL_DEPTH.get(0, 3)` 会给无编号组安上 depth=3 的幻影默认。
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
    """公式编号 token 的正则源（**不含括号**、**不锚定**、**无捕获组**）。

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
    variants = [r'[（(]\s*%s\s*[）)]' % core]        # (2.17) / （A.3）
    if bare and not letter:
        variants.append(core)                        # 裸排 2.17
    return re.compile(r'^(?:%s)$' % '|'.join(variants))


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
