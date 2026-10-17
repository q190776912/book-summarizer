# -*- coding: utf-8 -*-
"""「换行交叉引用否决」回归测试（Lehmann《Elements of Large-Sample Theory》ch3 实测）。

缺陷形态（印面 p172，fitz 200dpi 目视确证）：一句散文跨行，第二行行首恰是被引用
的条目号 + 该句的句号——

    To see how to choose θ_n, consider the situation assumed in Theorem
    3.3.1. Replacing θ by θ_n in (3.3.4) gives

通用节检测器把第二行读成三级节头 `3.3.1 Replacing 0 by 0n in (3.3.4) gives` 并发进
骨架，build_structure 于是落成**自带内容 0 块**的幻影小节节点。既有守卫全部落空：
首词 "Replacing" 不在句首虚词表、非小写；无「句读+空格+小写」从句（Bass 那条判据）；
无尾句读；不含「标签词+数字」。

后果不是「多一个空节」而是**写手无路可走**：门控 `lib/section_titles` 要求单元 H2
与契约 name 互当前缀——照抄残缺名（0/0n）= 成品里凭空多一行假节题（违反保真），
按印面写 θ/θ_n = 判「互非前缀」FAIL。即该单元不存在任何合法 DONE 写法。

修法（`scan_skeleton._xref_wrap_phantom`，两条同时成立才否决）：
  ① 上一行以条目/章节标签词收尾（可带尾随逗号/冒号）；
  ② 本行编号后紧跟句点（引用句的句号）。
只加在 universal 通道，且不吃序位/白名单豁免。已知漏报：①成立而②不成立者仍由
既有从句散文闸负责（保守代价，换取对「上一行恰好停在 Theorem 一词的真节头」零误杀）。

钉死六件事：
  · 幻影行 + 上一行停在 "Theorem" → None（且序位接续号也拦）；
  · 同一幻影行**不传 prev_line** → 照旧识别（默认参数零回归）；
  · 上一行停在标签词、但本行编号后无句点的真节头 → 照旧识别；
  · 编号后带句点、上一行是普通散文句尾（不停在标签词）的成句真节头 → 照旧识别；
  · 上一行中部含标签词（不停在它上面）→ 照旧识别；
  · 尾词是 equation/note/proof（散文高频尾词，已从标签词表剔除）→ 照旧识别，
    同形行尾换成真标签词仍拦；note/proof 尾是本闸**已知漏报**，另有散文闸兜底。

Runs under stdlib unittest / pytest:
  python flows/write-source/structure/script/tests/test_xref_wrap_phantom_section.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import scan_skeleton as S  # noqa: E402

# 印面 p172 第二行（OCR 把 θ 读成 0、θ_n 读成 0n，节标题因此残缺）
PHANTOM = '3.3.1. Replacing 0 by 0n in (3.3.4) gives'
PREV_THM = ('To see how to choose n, consider the situation assumed in Theorem')
PREV_LEMMA_COMMA = 'the conclusion of Lemma,'
PREV_CJK = '由下面的定理'
# 真节头：编号后无句点，上一行恰好停在标签词（①成立、②不成立）
REAL_NODOT = '3.5 The rate of convergence'
# 真节头：编号后带句点的书（do Carmo / Serre 体例），上一行是普通散文句尾
REAL_DOT = '5.1. The cyclic group C'
PREV_PLAIN = 'We now turn to the following question.'


def _info(ln, ch, depths, prev_line=None, successor_num=None):
    return S._section_header_info(ln, ch=ch, depths=depths,
                                  prev_line=prev_line,
                                  successor_num=successor_num)


def test_xref_wrap_phantom_rejected():
    assert _info(PHANTOM, 3, {2, 3}, prev_line=PREV_THM) is None
    # 中文标签词同判（CJK 书同样存在「…下面定理 / 3.3.1.」断行形态）
    assert _info(PHANTOM, 3, {2, 3}, prev_line=PREV_CJK) is None
    # 标签词后带逗号同判
    assert _info(PHANTOM, 3, {2, 3}, prev_line=PREV_LEMMA_COMMA) is None


def test_successor_number_gets_no_waiver():
    # 幻影号恰是「上一个节号 +1」（§3.3 之后期望 3.3.1）——本否决在序位豁免之前，
    # 传 successor_num 也必须拦。
    assert _info(PHANTOM, 3, {2, 3}, prev_line=PREV_THM,
                 successor_num='3.3.1') is None


def test_default_prev_line_is_zero_regression():
    # 不传 prev_line（其他调用点/历史行为）→ 与修前逐字一致：仍识别成节头。
    got = _info(PHANTOM, 3, {2, 3})
    assert got is not None and got[0] == '3.3.1', got


def test_no_dot_head_after_label_word_still_recognized():
    # ②不成立：真节头不带尾点，即使上一行停在 "Theorem" 也放行（误杀代价由此挡住）。
    got = _info(REAL_NODOT, 3, {2, 3}, prev_line=PREV_THM)
    assert got is not None and got[0] == '3.5', got


def test_dot_head_after_plain_prose_still_recognized():
    # ①不成立：带尾点的真节头（do Carmo / Serre 体例）在普通散文句尾后照旧识别。
    got = _info(REAL_DOT, 5, {2, 3}, prev_line=PREV_PLAIN)
    assert got is not None and got[0] == '5.1', got


def test_label_word_mid_line_is_not_a_wrap():
    # 上一行**中部**含标签词但不停在它上面（"…see Theorem 2.4."）→ ①不成立。
    got = _info(REAL_DOT, 5, {2, 3}, prev_line='the argument of Theorem 2.4.')
    assert got is not None and got[0] == '5.1', got


def test_equation_note_proof_are_not_label_words():
    # 🔴 跨书标定实测的**唯一真节头险案**（Evans《PDE》p71 印面 «2.3.3. Properties
    # of solutions.»，上一行 «…the strong maximum principle for the heat equation»）：
    # "equation/note/proof" 是散文高频尾词，收进标签词表即误杀真节头，故表内剔除。
    evans = '2.3.3. Properties of solutions.'
    prev = 'As we shall see, the strong maximum principle for the heat equation'
    got = _info(evans, 2, {2, 3}, prev_line=prev)
    assert got is not None and got[0] == '2.3.3', got
    # 同一行换个尾词（真标签词）仍须拦——证明放行的是**尾词**而非整条件。
    assert _info(evans, 2, {2, 3},
                 prev_line='the corresponding result of the heat Theorem') is None
    # note/proof 尾 = 本闸**已知漏报**（散文高频尾词，收进表内即误杀真节头）：
    # 该形态的幻影由既有从句散文闸兜着，本否决不介入。
    assert _info(evans, 2, {2, 3}, prev_line='as the authors note') is not None
    assert _info(evans, 2, {2, 3}, prev_line='the end of the proof') is not None


if __name__ == '__main__':
    for _n, _f in sorted(globals().items()):
        if _n.startswith('test_'):
            _f()
            print('ok', _n)
