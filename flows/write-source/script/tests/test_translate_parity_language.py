"""Tests for translation language-residue detection (2026-09-24 blind spot).

Covers the real-analysis-for-graduate-students ch21/22 incident: half-translated
units (`> **证明**：` translated, but `**Theorem 21.10**: If X, Y …` + English
proof prose left verbatim) passed ``check_translate_parity`` because its only
"untranslated" rule was byte-identity (hash) — any single changed byte escaped.
``check_unit_quality.english_residues`` is the language-based mechanical gate,
now wired into both the gate_units units-translate branch and parity rule 8.
"""
import lib.boot as _boot
_boot.setup()

from check_unit_quality import english_residues, _en_word_run


# ── 负向：真实事故样本必须被抓 ────────────────────────────────────────────

def test_en_item_label_flagged():
    body = "**Theorem 21.10**: 若 $X$, $Y$ 可积，则 $\\mathbb{E}[XY]=(\\mathbb{E}X)(\\mathbb{E}Y)$。\n"
    probs = english_residues(body)
    assert any("标签未翻译" in p for p in probs), probs


def test_en_proof_label_flagged():
    body = "**定理 21.10**：独立随机变量乘积可积。\n**Proof**: By monotone convergence we obtain the claim.\n"
    probs = english_residues(body)
    assert probs, probs


def test_en_proof_prose_flagged():
    # ch21/0023 事故原文的证明步骤（含公式但整句英文）
    body = (
        "> **证明**：\n"
        "> 1. First suppose that $X$ and $Y$ are both non-negative and bounded by a positive integer $M$. Let\n"
        ">\n"
        "> $$\n> X_n=\\sum_{k=0}^{M2^n}\\frac{k}{2^n}.\n> $$\n"
    )
    probs = english_residues(body)
    assert any("未翻译英文散文" in p for p in probs), probs


def test_identical_unit_flagged_by_at_least_one_rule():
    body = "**Remark 22.5**: Suppose for each there is an open subset of containing on which is bounded.\n"
    assert english_residues(body)


# ── 正向：干净译文 / 合法豁免不得误报 ─────────────────────────────────────

def test_clean_cn_translation_passes():
    body = (
        "**定理 21.10**：若 $X$、$Y$ 与 $XY$ 均可积且 $X$ 与 $Y$ 独立，则\n"
        "\n"
        "$$\n\\mathbb{E}[XY]=(\\mathbb{E}X)(\\mathbb{E}Y).\n\\tag{21.10}\n$$\n"
        "\n"
        "> **证明**：\n"
        "> 1. 先设 $X$ 与 $Y$ 非负且有界。由勒贝格控制收敛定理（Dominated Convergence Theorem）即得。\n"
        "> 2. 对一般情形，将 $X$ 分解为正负部 $X=X^+-X^-$，利用线性性完成证明。\n"
    )
    assert english_residues(body) == []


def test_pure_math_unit_passes():
    body = "$$\n\\int f\\,d\\mu = \\lim_{n\\to\\infty} \\int s_n\\,d\\mu.\n\\tag{6.2}\n$$\n"
    assert english_residues(body) == []


def test_image_only_unit_passes():
    body = '<img src="ch6_fig1.png" width="60%">\n'
    assert english_residues(body) == []


def test_bilingual_label_passes():
    body = "**定理 21.10（Theorem 21.10）**：独立随机变量乘积的期望等于期望的乘积。\n"
    assert english_residues(body) == []


def test_short_english_terms_not_flagged():
    body = "称 $f$ 为 Lebesgue 可积函数。\n\n见 Theorem 3.1。\n"
    assert english_residues(body) == []


# ── 词跑计数本身 ──────────────────────────────────────────────────────────

def test_en_word_run_counts_and_breaks():
    assert _en_word_run("First suppose that X and Y are both non negative") >= 8
    assert _en_word_run("由 (21.10) 和 (21.7)，最后一项不超过") == 0
    assert _en_word_run("By the dominated convergence theorem we let") == 7
