"""Gate ②c 「正文块守恒」(`check_content_completeness._orphan_text_blocks`).

Why this gate exists (Shafarevich《Basic AG 1》I, built 2026-09-28): check ①
recomputes the contract with the SAME pipeline and diffs it against disk, so when
the pipeline itself drops a block both sides are missing it and ① says PASS.  ②c
instead compares the pipeline's *kept* text blocks (pre anchor-dispatch) against
the finished contract tree — the only place a block swallowed during dispatch
shows up.  It is a conservation-only gate: content filed under the WRONG node
(empty `content=0` item) stays its sister checks' business.

The exemptions are where the risk lives, so they are pinned both ways: what must
be let through (glued print headers `_strip_header` absorbed into a node `name`,
short fragments) and what must NOT (a lost paragraph that merely *starts with* or
*merely contains* a contract block — mid-containment is not exempt).
"""
import os
import sys
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[2])
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

from verify.script.check_content_completeness import _orphan_text_blocks

_LOST = ("If f : X -> Y is a regular map of varieties and Y is closed in A^n, "
         "then the graph of f is closed in X x A^n.")
assert len(_LOST) >= 40


def _contract(*blocks, name=""):
    """Minimal contract tree: one node + the given content blocks."""
    return {"key": "1", "type": "chapter", "name": name, "sub_sec": list(blocks)}


def _kept(text, page=74):
    return [{"text": text, "page": page}]


def test_true_loss_is_flagged():
    got = _orphan_text_blocks(_kept(_LOST), _contract({"text": "totally other "
                                                       "paragraph content here "
                                                       "long enough to matter."}))
    assert len(got) == 1
    assert got[0][1] == " ".join(_LOST.split())   # 报告里是归一化文本
    assert got[0][0] == 74                        # page reported for the fix-up


def test_block_present_in_contract_is_not_flagged():
    assert _orphan_text_blocks(_kept(_LOST), _contract({"text": _LOST})) == []


def test_formula_and_image_blocks_are_not_audited():
    """②b / ② own those; a kept formula must never surface as a text orphan."""
    kept = [{"formula": r"x^2 + y^2 = z^2", "display": True, "page": 9},
            {"image": "figure/ch1_fig3.png", "page": 9}]
    assert _orphan_text_blocks(kept, _contract()) == []


def test_short_fragment_is_exempt():
    assert _orphan_text_blocks(_kept("p. 74"), _contract()) == []


def test_glued_print_header_absorbed_into_name_is_exempt():
    """Real shapes from this book (ch1 p74 / p88, ch3 p173)."""
    tail = (" of a regular map is closed in Xx Y")
    nm = "引理1.4 Lemma1.4Thegraph" + tail
    kept = _kept("Lemma1.4Thegraph of a regular map is closed in Xx")
    assert len(" ".join(kept[0]["text"].split())) >= 40      # above the floor
    c = _contract(name=nm)
    assert _orphan_text_blocks(kept, c) == []


def test_remainder_of_stripped_block_is_exempt():
    body = _contract({"text": _LOST})
    head = "then the graph of f is closed"
    assert _orphan_text_blocks(_kept(head), body) == []


def test_lost_paragraph_starting_with_a_node_name_is_still_flagged():
    """The `nm in nt` direction must NOT exempt: a genuine loss typically begins
    with the section/item head that was folded into `name`."""
    glued = _LOST + " Some further printed body text that never reached the contract."
    c = _contract(name="If f : X -> Y is a regular map of varieties")
    assert [t for _pg, t in _orphan_text_blocks(_kept(glued), c)] == [glued.strip()]


def test_loss_glued_around_contract_text_is_still_flagged():
    """Contract holds the MIDDLE of a glued printed block (body survived, the two
    section heads around it did not) — substring containment must not exempt it."""
    glued = ("5.2 Products and Maps of Quasiprojective Varieties.  " + _LOST +
             "  6 Rational Maps and Birational Equivalence of Varieties")
    c = _contract({"text": _LOST})
    assert len(_orphan_text_blocks(_kept(glued), c)) == 1


def test_duplicate_blocks_are_consumed_one_by_one():
    """Two identical printed blocks, one in the contract → the second is a loss."""
    kept = _kept(_LOST) + _kept(_LOST)
    assert len(_orphan_text_blocks(kept, _contract({"text": _LOST}))) == 1


def test_matching_is_whitespace_and_case_insensitive():
    """OCR glue (`Corollary1.7Thevarietyof…`) must not manufacture a loss."""
    kept = _kept("Then the graph of f  is CLOSED in X x A^n,  and the claim follows.")
    c = _contract({"text": "then the graph of f is closed in x x a^n, and the claim follows"})
    assert _orphan_text_blocks(kept, c) == []


# ②c 页眉豁免（Atiyah–Macdonald p50/p128 实测假阳，2026-09-28 收官书标定）：
# 「章节标题 + 尾随页码」是版面家具，`_filter_noise` 的 ≥2 页重复判据对奇偶页
# 交替页眉失明，故守恒闸自己放行。

_HEAD_NAME = "Extended and Contracted Ideals in Rings of Fractions"


def test_running_head_with_page_number_is_exempt():
    kept = _kept("EXTENDED AND CONTRACTED IDEALS IN RINGS OF FRACTIONS 41", page=50)
    assert _orphan_text_blocks(kept, _contract(name=_HEAD_NAME)) == []


def test_running_head_with_key_prefix_is_exempt():
    """带键前缀的章名（`3 Divisors and Differential Forms` + 页码）同理放行。"""
    kept = _kept("3 Divisors and Differential Forms 163")
    c = _contract(name="3 Divisors and Differential Forms")
    assert _orphan_text_blocks(kept, c) == []


def test_lost_paragraph_ending_in_digits_is_still_flagged():
    """尾随数字豁免只认「削完正好等于标题」：以 `$n = 41$` 收尾的真丢失段照报。"""
    lost = _LOST + " The same argument applies for n = 41"
    assert len(_orphan_text_blocks(_kept(lost), _contract(name=_HEAD_NAME))) == 1


def test_head_prefix_that_is_only_part_of_a_name_is_not_exempt():
    """相等才放行，「标题的前缀」不放行（前缀形态正是「标题+正文」粘连）。"""
    kept = _kept("EXTENDED AND CONTRACTED 41" * 3)
    assert len(_orphan_text_blocks(kept, _contract(name=_HEAD_NAME))) == 1


# ②c 截断标题豁免（Rising Sea p28/p460/p516 实测假阳，2026-09-28 收官书标定）：
# 管线把过长的印刷标题截断存进节点 `name`（尾随省略号），印面那一整行的**未截断
# 原形**于是既不是 name 的子串、也不等于任何正文块 → 被误报成丢失。只放行**越过
# 截断接缝**的块；无省略号的节头仍不反向豁免，接缝不在块里也照常报。

_TRUNC_NAME = ("17.4-2 17.4.2. Theorem. —— If C is an irreducible separated "
               "regular curve, finite type over a…")
_PRINTED_LINE = ("C is an irreducible separated regular curve, finite type over a field "
                 "$k$, then there is an open embedding into a projective curve")


def test_untruncated_printed_line_of_a_truncated_title_is_exempt():
    assert _orphan_text_blocks(_kept(_PRINTED_LINE), _contract(name=_TRUNC_NAME)) == []


def test_ocr_glue_across_the_truncation_seam_is_exempt():
    """同一印刷行、序标粘连在前的 OCR 形态（接缝仍在块内）→ 放行。"""
    glued = ("17.4.2.TheoremIfCisanirreducible separated regular curve finite type "
             "over a field k then there is an open embedding")
    assert _orphan_text_blocks(_kept(glued), _contract(name=_TRUNC_NAME)) == []


def test_loss_that_does_not_reach_the_seam_is_still_flagged():
    """真丢失段只共享标题**开头**、没到截断接缝 → 照报（反向豁免仍未开）。"""
    lost = ("If C is an irreducible separated regular curve, the argument of the "
            "theorem then exhibits a completion never written into the contract body.")
    assert len(_orphan_text_blocks(_kept(lost), _contract(name=_TRUNC_NAME))) == 1


def test_short_truncated_name_opens_no_seam():
    """接缝只来自**有分量**的标题；短名截断不产生豁免，真丢失照报。"""
    assert len(_orphan_text_blocks(_kept(_PRINTED_LINE),
                                   _contract(name="Blowup…"))) == 1
