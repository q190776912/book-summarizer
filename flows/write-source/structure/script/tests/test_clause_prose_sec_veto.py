# -*- coding: utf-8 -*-
"""「从句续行否决技术术语首词豁免」回归测试（Bass《Real Analysis》ch21 p306 实测）。

缺陷形态：跨行散文续句被 OCR 断块后**行首恰是一个交叉引用编号**——前句
"probability 1/2. If N = min{…}, we will see in Remark" 换行，续块独立成块为
"21.30 later on that N < ∞o a.s., but E Mv = 1 ≠ 0 = E Mo."。通用节检测器把
"21.30" 当节号、余下当标题：

  · 小写首词 "later" **不在**虚词负名单 `_SEC_TITLE_FUNC_WORDS`，
  · 句中数学变量 "Mv"/"Mo" 又冒充 Title-Case 延续词，
  ⇒ 「技术术语首词豁免」误放行 → 幻影节 §21.30（全书实仅 §21.1–§21.12）。
    ANCHOR-SANITY 因此判 §21.30(p306) 与 §21.12(p331) 号/页矛盾、整章拒落盘，
    连带把真实的 §21.2 锚点误挂（p291 全大写页眉复本，条头漂到 §21.2 之前）
    一并堵死。

修法：技术术语首词豁免前加一道**从句否决**——标题含「句读 + 空格 + 小写词」
（`_SEC_TITLE_CLAUSE_PROSE`）即判散文续句，撤销豁免。真节标题是「小写首词 +
Title-Case 名词短语」（Rosen "n-ary Relations and Their Applications"、
"gcds as Linear Combinations"），从不含逗号引出的小写子句。仅收紧豁免分支，
**不触**序位+白名单 `_waive` 通道（Serre 小写技术术语真节题照旧放行）。

钉死三件事：
  · 幻影续句（小写首词 + ", <小写词>" 从句）→ None；
  · Rosen 两个无逗号小写首词真标题 → 仍识别；
  · 命中序位接续的成句真节题（Etingof 型）走 `_waive`，不受本否决影响。

Runs under stdlib unittest / pytest:
  python flows/write-source/structure/script/tests/test_clause_prose_sec_veto.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import scan_skeleton as S  # noqa: E402

# ch21 实测幻影续块（p306，OCR 独立成块）
PHANTOM = ('21.30 later on that N < ∞o a.s., but E Mv = 1 ≠ 0 = E Mo.')
# Rosen 8e 真节标题：小写技术术语首词 + Title-Case 名词短语，无逗号
ROSEN_ARY = '9.2.5 n-ary Relations and Their Applications'
ROSEN_GCD = '4.3.8 gcds as Linear Combinations'
# Etingof 成句真节题：靠序位接续豁免（`_waive`/`_succ`）放行，不该被从句否决误伤
ETINGOF = '3.6 Unitary representations. Another proof of Maschke\u2019s theorem'


def _info(ln, ch, depths, successor_num=None):
    return S._section_header_info(ln, ch=ch, depths=depths,
                                  successor_num=successor_num)


def test_phantom_clause_continuation_rejected():
    # 「21.30 …a.s., but …」= 小写首词 later + 逗号引出小写子句 → 散文续句。
    assert _info(PHANTOM, 21, {1, 2}) is None
    # 即便伪装成「下一个节号」也须拦：本否决只收紧技术术语豁免，而 `_waive`
    # 要求**同时**命中目录白名单；无白名单时序位单证不得把从句续句放行成节。
    assert _info(PHANTOM, 21, {1, 2}, successor_num='21.30') is None


def test_roson_lowercase_first_headings_still_recognized():
    got = _info(ROSEN_ARY, 9, {1, 2, 3, 4})
    assert got is not None and got[0] == '9.2.5', got
    # gcds 标题依赖后随 Title-Case 词 "Linear"——无逗号，豁免不受本否决影响。
    got2 = _info(ROSEN_GCD, 4, {1, 2, 3, 4})
    assert got2 is not None and got2[0] == '4.3.8', got2


def test_successor_waived_prose_heading_not_regressed():
    # Etingof 成句节题靠序位接续放行；本否决只在豁免分支，不触该路径。
    got = _info(ETINGOF, 3, {1, 2, 3}, successor_num='3.6')
    assert got is not None and got[0] == '3.6', got


def test_veto_is_scoped_to_lowercase_first_word_titles():
    # 从句否决只嵌在「小写首词」豁免分支里；Title-Case（大写首词）标题根本
    # 不经过该分支，即便含逗号子句也照旧识别——证明本修法的作用域不外溢。
    got = _info('7.2 Relations, and Beyond', 7, {1, 2})
    assert got is not None and got[0] == '7.2', got


def test_lowercase_first_title_with_clause_is_rejected():
    # 小写首词「given」+ 存在大写延续词 "Set"/"Mv"（本可满足豁免的大写词条件），
    # 但含逗号引出小写子句 ", but" → 从句否决生效（而非"无大写词"那条路径）。
    assert _info('7.2 given the Set, but Mv diverges', 7, {1, 2}) is None


if __name__ == '__main__':
    for _n, _f in sorted(globals().items()):
        if _n.startswith('test_'):
            _f()
            print('ok', _n)
