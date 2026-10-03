# -*- coding: utf-8 -*-
"""test_formula_lead_decoupling.py — 公式 lead 家族（digit / letter / roman）解耦回归。

用户诉求（2026-10-01）：**不**复用 ordinal 的 type，新增 formula-only 码 15（字母二级）/
16（罗马二级），并保证**各 formula type 之间的判断逻辑相对独立、绝不互相判成功**。

本文件锁死三件事：
1. **命名空间隔离**：formula-only 码（15/16 二级、17/18 三级）只在 `FORMULA_ONLY_CODES`
   里，**不在** `ORDINAL_CODES` /
   `ORDINAL_DEPTH`，条目侧 `ordinal_depth(15/16)` 必须**硬报错**（fail-loud），这样
   `verify_config` 的 ordinal 组校验（`t not in ORDINAL_CODES`）天然拒绝它们；
2. **形态互斥**：digit / letter / roman 三条正则核互相拒绝对方的特征 token
   （`2.17` vs `A.3` vs `II.5`），且 alpha-led（letter/roman）**永不**收裸排；
   唯一允许的重叠是**单字母罗马头**（`I.`/`V.`/`X.`…），由整书单 lead + detect 保守择族消解；
3. **`make_config.detect_formula` 保守择族**：只有**多字母罗马证据**且**无非罗马字母头**
   时才选 type 16；纯字母附录（A/B/C）即便混入罗马噪声也**不得**被罗马夺走；只有单字母
   罗马头的书**保持 letter**（宁缺勿滥，绝不误判罗马）。

`norm()` 的多字母头保留（旧 `[A-Z]` 只留首字符会把 `II.5` 拆坏）也在此锁定。

运行：
  python config/verify_config/tests/test_formula_lead_decoupling.py
  python -m pytest config/verify_config/tests/test_formula_lead_decoupling.py -q
"""
import os
import re
import sys
import json
import tempfile
import subprocess
import unittest
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

from lib.numbering import (                                        # noqa: E402
    resolve_formula_type, formula_num_core, formula_tag_re,
    formula_tag_number, ordinal_depth, OrdinalDepthError,
    FORMULA_LEAD_DIGIT, FORMULA_LEAD_LETTER, FORMULA_LEAD_ROMAN,
    FORMULA_TYPE_LETTER_TWO, FORMULA_TYPE_ROMAN_TWO,
    FORMULA_TYPE_SHAPE, FORMULA_ONLY_CODES, ORDINAL_DEPTH,
)
from verify_config import ORDINAL_CODES                            # noqa: E402
from formula_tag import SourceFormulaIndex, build_formula_patterns  # noqa: E402

MAKE_CONFIG_PY = os.path.join(_ROOT, "config/verify_config/make_config.py")


class ResolveFormulaTypeMapping(unittest.TestCase):
    """`resolve_formula_type` 是公式形态的唯一入口。"""

    def test_letter_only_code_15(self):
        # 15 恒为 letter 二级，且**不受 letter_ch 影响**（专用码自己就是字母家族）。
        self.assertEqual(resolve_formula_type(15, letter_ch=False),
                         (FORMULA_LEAD_LETTER, 2))
        self.assertEqual(resolve_formula_type(15, letter_ch=True),
                         (FORMULA_LEAD_LETTER, 2))

    def test_roman_only_code_16(self):
        self.assertEqual(resolve_formula_type(16, letter_ch=False),
                         (FORMULA_LEAD_ROMAN, 2))
        self.assertEqual(resolve_formula_type(16, letter_ch=True),
                         (FORMULA_LEAD_ROMAN, 2))

    def test_digit_codes_route_through_ordinal_depth(self):
        self.assertEqual(resolve_formula_type(1), (FORMULA_LEAD_DIGIT, 1))
        self.assertEqual(resolve_formula_type(2), (FORMULA_LEAD_DIGIT, 2))
        self.assertEqual(resolve_formula_type(3), (FORMULA_LEAD_DIGIT, 3))

    def test_legacy_letter_ch_still_maps_to_letter(self):
        # 旧字母书体例 `type=2 + letter_ch=true` 必须逐字节等价地给 letter 家族。
        self.assertEqual(resolve_formula_type(2, letter_ch=True),
                         (FORMULA_LEAD_LETTER, 2))

    def test_unconfigured_is_digit_none(self):
        lead, ncomp = resolve_formula_type(None)
        self.assertEqual(lead, FORMULA_LEAD_DIGIT)
        self.assertIsNone(ncomp)

    def test_shape_table_is_the_authority(self):
        for code, shape in FORMULA_TYPE_SHAPE.items():
            self.assertEqual(resolve_formula_type(code), tuple(shape))


class NamespaceDecoupling(unittest.TestCase):
    """formula-only 码与 ITEM ordinal 码彻底隔离——解耦的落点。"""

    def test_only_codes_are_the_alpha_led_families(self):
        # 15/17 = 字母二级/三级，16/18 = 罗马二级/三级（Katok 附录 `(A.2.1)` 实测）。
        self.assertEqual(set(FORMULA_ONLY_CODES), {15, 16, 17, 18})

    def test_formula_only_not_in_ordinal_codes(self):
        for code in FORMULA_ONLY_CODES:
            self.assertNotIn(code, ORDINAL_CODES,
                             "formula-only 码 %s 混进了条目 ORDINAL_CODES → 会污染条目体例判定"
                             % code)

    def test_formula_only_not_in_ordinal_depth(self):
        for code in FORMULA_ONLY_CODES:
            self.assertNotIn(code, ORDINAL_DEPTH,
                             "formula-only 码 %s 不该进 ORDINAL_DEPTH" % code)

    def test_item_side_rejects_formula_only_fail_loud(self):
        # 条目侧若误拿 15/16 去查 depth，必须**硬报错**（不静默兜默认）——
        # 这正是「两套 type 空间互不知晓」的机械保证。
        for code in FORMULA_ONLY_CODES:
            with self.assertRaises(OrdinalDepthError):
                ordinal_depth(code)

    def test_digit_formula_codes_stay_in_ordinal_namespace(self):
        # 数字家族复用条目码 1/2/3——它们在 ORDINAL_CODES 里，与专用码泾渭分明。
        for code in (1, 2, 3):
            self.assertIn(code, ORDINAL_CODES)
            self.assertNotIn(code, FORMULA_ONLY_CODES)


class CoreMutualExclusion(unittest.TestCase):
    """三条正则核互相拒绝对方特征 token（用户核心诉求：不互相判成功）。"""

    # ---- digit 家族：只认纯数字 -----------------------------------------
    def test_digit_accepts_numeric_rejects_alpha(self):
        rx = formula_tag_re(2, lead=FORMULA_LEAD_DIGIT)
        self.assertTrue(rx.match("(2.17)"))
        self.assertFalse(rx.match("(A.3)"), "digit 核不得收字母章位")
        self.assertFalse(rx.match("(II.5)"), "digit 核不得收罗马章位")

    # ---- letter 家族：恰单个大写字母头 ----------------------------------
    def test_letter_accepts_single_letter(self):
        self.assertEqual(formula_tag_number("(A.3)", ncomp=2,
                                             lead=FORMULA_LEAD_LETTER), "A.3")
        self.assertEqual(formula_tag_number("(B.12)", ncomp=2,
                                             lead=FORMULA_LEAD_LETTER), "B.12")

    def test_letter_rejects_digit_and_multi_letter_roman(self):
        rx = formula_tag_re(2, lead=FORMULA_LEAD_LETTER)
        self.assertFalse(rx.match("(2.17)"))
        # 罗马多字母头 `II.5` 的第二字母紧跟首字母、非分隔符 → 单字母核失配。
        self.assertFalse(rx.match("(II.5)"),
                         "letter 核（要求单字母后紧跟分隔符）绝不该命中 II.5")

    # ---- roman 家族：[IVXLCDM] 头 ---------------------------------------
    def test_roman_accepts_multi_char_head(self):
        self.assertEqual(formula_tag_number("(II.5)", ncomp=2,
                                            lead=FORMULA_LEAD_ROMAN), "II.5")
        self.assertEqual(formula_tag_number("(IV.3)", ncomp=2,
                                            lead=FORMULA_LEAD_ROMAN), "IV.3")
        self.assertEqual(formula_tag_number("(IX.12)", ncomp=2,
                                            lead=FORMULA_LEAD_ROMAN), "IX.12")

    def test_roman_rejects_non_roman_letter_and_digit(self):
        rx = formula_tag_re(2, lead=FORMULA_LEAD_ROMAN)
        self.assertFalse(rx.match("(A.3)"),
                         "roman 核 [IVXLCDM] 必须拒非罗马字母头 A")
        self.assertFalse(rx.match("(2.17)"))

    def test_single_char_roman_head_overlap_is_intended(self):
        # 单字母罗马头 I/V/X/L/C/D/M 既是字母又是罗马——两核都收（唯一残留歧义，
        # 由整书单 lead + detect 保守择族消解，不是缺陷）。
        for lead in (FORMULA_LEAD_LETTER, FORMULA_LEAD_ROMAN):
            self.assertTrue(formula_tag_re(2, lead=lead).match("(I.5)"),
                            "单字母罗马头 %s 家族都应收下" % lead)

    def test_three_cores_partition_the_signature_tokens(self):
        # 每个特征 token 恰好被**一个**家族收（单字母罗马头除外，已在上例说明）。
        cases = {"(2.17)": FORMULA_LEAD_DIGIT,
                 "(A.3)": FORMULA_LEAD_LETTER,
                 "(II.5)": FORMULA_LEAD_ROMAN}
        for tok, winner in cases.items():
            for lead in (FORMULA_LEAD_DIGIT, FORMULA_LEAD_LETTER,
                         FORMULA_LEAD_ROMAN):
                hit = bool(formula_tag_re(2, lead=lead).match(tok))
                self.assertEqual(hit, lead == winner,
                                 "%s 应只被 %s 家族命中，实得命中家族 %s"
                                 % (tok, winner, lead if hit else "-"))


class AlphaLeadBareSuppression(unittest.TestCase):
    """alpha-led（letter / roman）永不发裸排变体（宁缺勿滥）；digit 裸排保持。"""

    def test_letter_bare_suppressed_paren_kept(self):
        rx = formula_tag_re(2, bare=True, lead=FORMULA_LEAD_LETTER)
        self.assertTrue(rx.match("(A.3)"))
        self.assertFalse(rx.match("A.3"), "裸排 A.3 与 Fig. A.3 / 小节标题不可分，须拒")

    def test_roman_bare_suppressed_paren_kept(self):
        rx = formula_tag_re(2, bare=True, lead=FORMULA_LEAD_ROMAN)
        self.assertTrue(rx.match("(II.5)"))
        self.assertFalse(rx.match("II.5"), "裸排 II.5 与散文罗马计数不可分，须拒")

    def test_digit_bare_still_allowed(self):
        # 数字家族的裸排是既有行为，解耦后不得改变。
        rx = formula_tag_re(2, bare=True, lead=FORMULA_LEAD_DIGIT)
        self.assertTrue(rx.match("2.17"))

    def test_build_formula_patterns_roman_no_bare_variant(self):
        pats = build_formula_patterns(2, allow_bare=True, letter=False,
                                      lead=FORMULA_LEAD_ROMAN)
        # 任何一条模式都不得在无括号上下文里匹配裸 `II.5`。
        for p in pats:
            self.assertIsNone(re.search(p, "the value II.5 here"),
                              "roman 模式 %r 竟匹配裸排" % p)
        self.assertTrue(any(re.search(p, "(II.5)") for p in pats),
                        "roman 至少要收带括号的 (II.5)")

    def test_build_formula_patterns_letter_rejects_roman_token(self):
        pats = build_formula_patterns(2, allow_bare=False, letter=False,
                                      lead=FORMULA_LEAD_LETTER)
        self.assertTrue(any(re.search(p, "(A.3)") for p in pats))
        self.assertFalse(any(re.search(p, "(II.5)") for p in pats),
                         "letter 模式不得命中罗马 (II.5)")


class NormKeepsMultiCharHead(unittest.TestCase):
    """`SourceFormulaIndex.norm` 必须保留**完整**多字母罗马头（旧 `[A-Z]` 只留首字符的回归）。"""

    def test_roman_head_intact(self):
        self.assertEqual(SourceFormulaIndex.norm("(II.5)"), "II.5")
        self.assertEqual(SourceFormulaIndex.norm("(IV.3)"), "IV.3")
        self.assertEqual(SourceFormulaIndex.norm("(III.12)"), "III.12")

    def test_roman_leading_zero_folded(self):
        self.assertEqual(SourceFormulaIndex.norm("(II.05)"), "II.5")
        self.assertEqual(SourceFormulaIndex.norm("II.005"), "II.5")

    def test_letter_head_still_single(self):
        self.assertEqual(SourceFormulaIndex.norm("(A.03)"), "A.3")

    def test_digit_unaffected(self):
        self.assertEqual(SourceFormulaIndex.norm("(11.1-1)"), "11.1.1")
        self.assertEqual(SourceFormulaIndex.norm("2.17"), "2.17")

    def test_bare_roman_parsed_without_parens(self):
        # norm 只被**模式已捕获**的 token 调用，但直接喂裸串也不该把 II.5 拆成 I.5。
        self.assertNotEqual(SourceFormulaIndex.norm("II.5"), "I.5")


def _write_pages(ext, page_blocks):
    os.makedirs(ext, exist_ok=True)
    for i, blocks in enumerate(page_blocks, start=1):
        with open(os.path.join(ext, "page_%03d.json" % i), "w",
                  encoding="utf-8") as f:
            json.dump({"text": [{"text": t} for t in blocks]}, f,
                      ensure_ascii=False)


def _run_detect_formula(ext):
    """detect_formula via subprocess（make_config 在 import 期重配 stdout，
    直接在 pytest 里 import 会干扰捕获——与既有 make_config 测试同法）。"""
    code = (
        "import sys, json;"
        "sys.path.insert(0, %r);"
        "from make_config import detect_formula;"
        "print(json.dumps(detect_formula(sys.argv[1])))"
        % os.path.join(_ROOT, "config", "verify_config")
    )
    r = subprocess.run([sys.executable, "-c", code, ext],
                       capture_output=True, text=True, timeout=120,
                       encoding="utf-8", errors="replace")
    assert r.returncode == 0, "detect_formula failed: %s" % r.stderr
    return json.loads(r.stdout)


def _extract_with(done_marker=True):
    d = tempfile.mkdtemp()
    ext = os.path.join(d, "_extract")
    os.makedirs(ext, exist_ok=True)
    if done_marker:
        with open(os.path.join(ext, "_extraction_done.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"done": True}, f)
    return d, ext


class DetectFormulaRoman(unittest.TestCase):
    """`make_config.detect_formula` 的罗马择族：保守、且夺不走字母书。"""

    def _filler(self):
        return "Consider the relation below."

    def test_roman_book_elected_type_16(self):
        _d, ext = _extract_with()
        # 10 个右对齐 `(II.n)` 块（跨 3 页），每块尾净 → roman_count=10 >= 阈值 8；
        # 单字母罗马头 `(I.1)` 落 letter_hits（'I' ∈ IVXLCDM）→ 守卫放行。
        blocks = ["Equation holds (II.%d)." % n for n in range(1, 11)]
        blocks.append("Also (III.2).")
        blocks.append("See (I.1) here.")
        _write_pages(ext, [blocks[:4], blocks[4:8], blocks[8:]])
        res = _run_detect_formula(ext)
        self.assertIsNotNone(res, "罗马体例书不该探测为空")
        self.assertEqual(res["type"], 16, "应选 formula-only 罗马码 16：%r" % res)
        self.assertNotIn("letter_ch", res, "罗马配置不带 letter_ch")

    def test_letter_book_with_roman_noise_stays_letter(self):
        _d, ext = _extract_with()
        # 真·字母附录：A/B/C 头各若干（含**非罗马字母头**），同时混入成串罗马噪声 II.x。
        # 罗马分支的守卫（所有 letter 头 ∈ IVXLCDM）必须失败 → 罗马不夺 → 字母胜出。
        letter_blocks = ["Appendix A formula (A.%d)." % n for n in range(1, 6)]
        letter_blocks += ["Appendix B formula (B.%d)." % n for n in range(1, 6)]
        roman_noise = ["Spurious (II.%d)." % n for n in range(1, 9)]
        allb = letter_blocks + roman_noise
        _write_pages(ext, [allb[0:6], allb[6:12], allb[12:]])
        res = _run_detect_formula(ext)
        self.assertIsNotNone(res)
        self.assertEqual(res["type"], 2, "字母书须保持 type 2，不得被罗马夺走：%r" % res)
        self.assertTrue(res.get("letter_ch"), "须带 letter_ch=true")

    def test_single_char_roman_only_stays_letter(self):
        _d, ext = _extract_with()
        # 只有单字母罗马头（I/V/X…）——与字母不可分，保守起见**保持 letter**，
        # 绝不误判罗马（宁缺勿滥）。
        blocks = []
        for h in ("I", "V", "X"):
            for n in range(1, 7):
                blocks.append("Formula (%s.%d)." % (h, n))
        _write_pages(ext, [blocks[0:6], blocks[6:12], blocks[12:]])
        res = _run_detect_formula(ext)
        self.assertIsNotNone(res)
        self.assertEqual(res["type"], 2,
                         "纯单字母罗马头须保守落 letter，不得选 16：%r" % res)
        self.assertTrue(res.get("letter_ch"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
