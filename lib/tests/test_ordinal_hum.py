"""Tests for OrdinalHum (type 12, Humphreys letter-ordinal style).

Covers the 2026-09-21 requirement: define the "label + letter ordinal" format
and support the label on BOTH sides of the letter (``**Corollary A**`` ↔
``**A Corollary**`` normalise to the same canonical key), without mis-detecting
single-level EN books (``**Theorem 1**``) as type 12.
"""
import lib.boot as _boot
_boot.setup()

from lib.ordinal_styles import OrdinalHum, OrdinalStyle


def test_registration():
    assert OrdinalStyle.get(12).__class__ is OrdinalHum
    h = OrdinalHum()
    assert h.code == 12
    assert h.depth == 1
    assert h.name == 'hum'


def test_extract_bidirectional_label():
    h = OrdinalHum()
    # label in front  <->  label after letter  -> SAME canonical key
    assert h.extract('**Corollary A**') == '推论 A'
    assert h.extract('**A Corollary**') == '推论 A'
    assert h.extract('**Lemma B**') == '引理 B'
    assert h.extract('**B Lemma**') == '引理 B'
    # CN labels too
    assert h.extract('**定理 A**') == '定理 A'
    assert h.extract('**A 定理**') == '定理 A'
    assert h.extract('**Definition C**') == '定义 C'
    assert h.extract('**C Definition**') == '定义 C'


def test_negative_not_label_plus_letter():
    h = OrdinalHum()
    # number ordinal form is intentionally OUT of pilot type 12 (-> type 1)
    assert h.extract('**Example 1**') is None
    # pure label (no ordinal) is out of pilot type 12 (legacy config branch)
    assert h.extract('**Theorem**') is None
    # letter-chapter + digits -> type 13/14, not type 12
    assert h.extract('**Definition A.1.1**') is None
    assert h.extract('**A.1.1 Definition**') is None
    # digit.digit + letter -> type 8, not type 12
    assert h.extract('**Exercise 2.3.A**') is None
    # two-level digits -> type 2, not type 12
    assert h.extract('**Theorem 1.2**') is None


def test_page_form_judge():
    h = OrdinalHum()
    assert h.judge('Corollary A', page=True) is True
    assert h.judge('A Corollary', page=True) is True
    assert h.judge('Example 1', page=True) is False


def test_key_to_tuple_folds_letter():
    h = OrdinalHum()
    assert h._key_to_tuple('推论 A') == (1,)
    assert h._key_to_tuple('引理 B') == (2,)
    assert h._key_to_tuple('定义 C') == (3,)
    assert h._key_to_tuple('定理 A') == (1,)


def test_detect_scope_letter_reset():
    h = OrdinalHum()
    keys = ['推论 A', '推论 B', '推论 C', '引理 A', '引理 B']
    # A->B->C reset then Lemma A->B reset => chapter/parent-reset (2)
    assert h.detect_scope(keys) == 2


def test_judge_extract_self_consistent():
    # Rule #5: anything judge(page=True) recognises must be extractable.
    # Regression: trailing period inside the bold span (``**Corollary A.**``)
    # used to be recognised by judge but returned None from extract
    # (strict ``\s*\*\*`` terminal). Now aligned with Vakil's lenient
    # ``[^*]*\*+`` terminal.
    h = OrdinalHum()
    for t in ['**Corollary A**', '**Corollary A.**', '**A Corollary**',
               '**Lemma B.**', '**A 定理**']:
        judged = h.judge(t, page=True)
        extracted = h.extract(t)
        assert judged is True, f"{t!r} should be judged type 12"
        assert extracted is not None, f"{t!r} must be extractable (judge/extract mismatch)"


def test_classify_does_not_misdetect_single_level_en():
    # label + letter -> type 12
    assert type(OrdinalStyle.classify('Corollary A')).__name__ == 'OrdinalHum'
    assert type(OrdinalStyle.classify('A Corollary')).__name__ == 'OrdinalHum'
    # single-level EN number must NOT become type 12 (it is type 1)
    assert type(OrdinalStyle.classify('Theorem 1')).__name__ == 'OrdinalSingle'
    assert type(OrdinalStyle.classify('Example 1')).__name__ == 'OrdinalSingle'
    # pure label -> no ordinal style detected
    assert OrdinalStyle.classify('Theorem') is None
