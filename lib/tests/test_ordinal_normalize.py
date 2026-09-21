"""tests for lib.ordinal_styles.normalize_ordinal

The contract side (verify/script/structure_io.read_structure_items) used to decide
two-level vs three-level by the brittle ``'-' in num_raw`` heuristic + a too-narrow
split set.  normalize_ordinal is the single separator-tolerant authority that
replaces it: it splits on SEP_SPLIT_RE (any wildcard separator) and emits the SAME
canonical key the md side (OrdinalStyle subclasses) produces, so "标点可替换" holds
end-to-end once the contract side is routed through it.
"""
import lib.boot as b
b.setup()

from lib.ordinal_styles import normalize_ordinal, OrdinalTwoLevelCN, OrdinalThreeLevelCN


def test_two_level_dash_normalizes_like_md():
    # two-level with '-' separator -> label.N.N (NOT bare, NOT label-dropped)
    assert normalize_ordinal('1-1', '定义') == '定义1.1'
    assert normalize_ordinal('1-1', '定理') == '定理1.1'


def test_two_level_middledot_keeps_both_segments():
    # regression: old code dropped the 2nd segment ('1·1' -> '定义1'); now fixed
    assert normalize_ordinal('1·1', '定义') == '定义1.1'
    assert normalize_ordinal('1–1', '定义') == '定义1.1'


def test_three_level_dot_is_bare_dash():
    # three-level with '.' separator -> bare N.S-N (matches md T3)
    assert normalize_ordinal('1.1.1') == '1.1-1'
    assert normalize_ordinal('2.3.4') == '2.3-4'


def test_three_level_hyphen():
    assert normalize_ordinal('1-1-1') == '1.1-1'


def test_three_level_middledot():
    # regression: old code truncated '1·1·1' -> '定义1'; now -> 1.1-1
    assert normalize_ordinal('1·1·1') == '1.1-1'
    assert normalize_ordinal('1–1–1') == '1.1-1'


def test_single_level():
    assert normalize_ordinal('1', '定义') == '定义1'


def test_normalize_matches_md_extract():
    # the normalized key must equal what the md side extracts for the SAME raw entry
    assert OrdinalTwoLevelCN().extract('**定义1-1**') == normalize_ordinal('1-1', '定义')
    assert OrdinalThreeLevelCN().extract('**定理1.1.1**') == normalize_ordinal('1.1.1')
    assert OrdinalThreeLevelCN().extract('**定理1·1·1**') == normalize_ordinal('1·1·1')


def test_separator_variants_all_collapse():
    # every separator variant of the same logical entry maps to ONE canonical key
    outs = sorted({normalize_ordinal(v) for v in ['1.1.1', '1-1-1', '1·1·1', '1–1–1']})
    assert outs == ['1.1-1']
    outs2 = sorted({normalize_ordinal(v, '定义') for v in ['1.1', '1-1', '1·1', '1–1']})
    assert outs2 == ['定义1.1']
