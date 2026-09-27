"""Gate #24 「源单元语言闸」(`check_unit_quality.source_language_problems`).

Found while writing Shafarevich《Basic Algebraic Geometry 1》I (EN book, 2026-09-28):
parallel step-5 writers produced 119 source units whose prose is CHINESE
(57 wholly Chinese, 62 with CJK traces), while the pipeline contract is
源语言优先 — step 5 units carry the BOOK's language, Chinese belongs to the step-6
translation layer (`units-translate/`).  The library only had the opposite gate
(`english_residues`, "untranslated English inside a CN translation unit"), so the
source side was completely unguarded and the bilingual product is broken at origin.

Tests pin both directions: an EN source unit with Chinese prose must FAIL, a CN
book's source unit (language `zh`) and an unknown language (None) must NOT be
audited, and the non-prose surfaces that legitimately carry CJK — the unit marker
line (`name= 例1.27`) and figure markup (`alt=`) — must stay exempt.
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

from check_unit_quality import check_body, source_language_problems  # noqa: E402

_MARK = ("<!-- book-summarizer DONE unit: id=0007 type=item "
         "key=例3.1 name=例3.1 例3.1 (X = A\") -->\n")
_EN_OK = (_MARK + "> **Example 3.1 ($X = \\mathbb{A}^n$)**: By Theorem 1.21, any "
          "irreducible codimension 1 subvariety $C$ is defined by one equation.\n")
_CN_BAD = (_MARK + "> **例 3.1 ($X = \\mathbb{A}^n$)**: 由定理 1.21，任一余维数 1 的不可约子簇\n"
           "都在一个方程下被定义。\n")


def test_en_source_unit_with_chinese_prose_is_flagged():
    probs = source_language_problems(_CN_BAD, "en")
    assert probs and "源单元" in probs[0]
    ok, body_probs = check_body("item", "", _CN_BAD, source_language="en")
    assert not ok and any("源单元语言" in p or "源单元（书籍语言" in p for p in body_probs)


def test_english_source_unit_is_clean():
    assert source_language_problems(_EN_OK, "en") == []
    ok, probs = check_body("item", "", _EN_OK, source_language="en")
    assert not any("源单元" in p for p in probs)


def test_chinese_book_source_unit_is_not_audited():
    """CN 书源正文本就是中文：language=zh / None 时该闸一律不跑（不得误伤）。"""
    assert source_language_problems(_CN_BAD, "zh") == []
    assert source_language_problems(_CN_BAD, None) == []
    ok, probs = check_body("desc", "", _CN_BAD, source_language="zh")
    assert not any("源单元" in p for p in probs)


def test_marker_and_figure_markup_lines_are_exempt():
    """首行标记（已剥）与图注 markup 里的中文不算正文残留。"""
    body = ('<div style="display:flex">\n'
            '  <img src="figure/ch01_fig1.png" alt="图 1 二次曲线的交点" width="70%">\n'
            '</div>\n')
    assert source_language_problems(body, "en") == []


def test_cjk_inside_math_and_blockquote_is_still_flagged():
    """数学模式内 / `>` 块内的中文短语一样是残留（写手最常见的躲法）。"""
    assert source_language_problems("> 注：这里 $f$ 是不可约多项式。\n", "en")
    assert source_language_problems("$\\text{证明：由归纳假设即得}$。\n", "en")


def test_single_cjk_ocr_artifacts_are_not_flagged():
    """标定负例（Weibel / Serre / Robinson 实测数十处）：□ 被 OCR 成 `口`、λ→`入`、
    ≡→`三`、+→`十` 都是**单字**残迹，归 OCR 残留闸管，不该由语言闸打回。"""
    assert source_language_problems("> 口\n", "en") == []
    assert source_language_problems("hence x(x) = 入(x) 与 $x _ { 1 }$ 三 x\n", "en") == []


def test_bilingual_gloss_labels_are_not_flagged():
    """标定负例（Leinster BCT / Rosen 收官书实测）：`**Definition A.1-2 (Paradigm 范式)**`
    与 `# Chapter 1: 基本概念` 是写手为读者加的**术语对照**，不是中文正文。"""
    assert source_language_problems(
        "**Definition A.1-2 (Paradigm 范式)** The fundamental category of a "
        "monoid $M$ is the one-object category with hom-set $M$.\n", "en") == []
    assert source_language_problems("# Chapter 1: 基本概念\n", "en") == []
    # 标定实测假阳（收官书 ODE）：长双语章标题靠 `#` 行豁免挡住
    assert source_language_problems("# Chapter 4: 主要定理的证明\n", "en") == []
    assert source_language_problems("# Chapter 5: 流形上的微分方程\n", "en") == []


def test_threshold_boundary_is_inclusive():
    body_zh = "这里 $f$ 是不可约的。\n"        # 连续汉字 = 5（是不可约的）
    body_ok = "这里 $f$ 是不可约。\n"          # 4
    assert len(source_language_problems(body_zh, "en")) == 1
    assert source_language_problems(body_ok, "en") == []
