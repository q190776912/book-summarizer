# -*- coding: utf-8 -*-
"""Regression: 附录/补篇的**数字序标必须有印刷证据**（lib/appendix_ordinal
→ config/verify_config/make_config.py fail-closed 硬闸）。

背景（Shafarevich《Basic Algebraic Geometry 1》2026-09-29 实测）：印面标题就是裸的
``Algebraic Appendix``（目录页 / 标题页 / 页眉都没有任何序标），chapter_map 却顺着
正文把它登记成第 5 章，于是契约 ``appendix5.json``、单元目录 ``units/appendix5/``、
成品 ``附录5_代数附录.md`` / ``Appendix5_Algebraic_Appendix.md``、H1
``# Chapter 5: Algebraic Appendix`` 整条链长出**伪造序标**。SKILL.md 早有「无编号附录
→ 键写裸 appendix」的规定，但没有任何机械校验，靠人记得住 = 会再犯。

判据（跨书普查实测后收窄，51 本书 41 个带序标附录章只打出 5 处真伪造）：
* 只判 **阿拉伯数字** 序标；字母/罗马序标（A、B、S、I…）一律放过——它们的印面形态
  多样（Lee 只印 ``A. Point-Set Topology``、Arnold 中译本印 ``附录Ⅰ`` 而登记成 A…P），
  要求「附录词 + 字母相邻」会打成一片假阳。
* 取证面 = 该章页窗 **+ 前置目录区**（两处独立来源）。

Runs under stdlib unittest:
  python lib/tests/test_appendix_ordinal_evidence.py
"""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[2])
sys.path.insert(0, _ROOT)
from lib.boot import setup  # noqa: E402
setup()

from data.chapter_map.chapter_map import load_chapter_records  # noqa: E402
from lib.appendix_ordinal import (appendix_ordinal_problems,  # noqa: E402
                                  evidence_pattern, page_text)

FLAG = "找不到该序标的任何印刷证据"


def _mk_extract(pages, chapters):
    """临时 extract_dir：chapter_map（列表形态）+ page_*.json 文字层。"""
    d = tempfile.mkdtemp()
    with io.open(os.path.join(d, "chapter_map.json"), "w", encoding="utf-8") as f:
        json.dump({"chapters": chapters}, f, ensure_ascii=False, indent=2)
    for pno, texts in pages.items():
        with io.open(os.path.join(d, "page_%03d.json" % pno), "w",
                     encoding="utf-8") as f:
            json.dump({"page": pno, "formulas": [],
                       "text": [{"text": t} for t in texts]}, f, ensure_ascii=False)
    return d


def _problems(d):
    return appendix_ordinal_problems(load_chapter_records(d), d)


def _apx(num, name, start, end):
    return {"ch": num, "kind": 2, "name": name, "start": start, "end": end}


class TestEvidencePredicate(unittest.TestCase):
    def test_fabricated_numeric_ordinal_flagged(self):
        """负例（本书真实形态）：印面只有裸标题 "Algebraic Appendix"，登记成数字 5。"""
        d = _mk_extract({299: ["Algebraic Appendix", "1 Linear and Bilinear Algebra"],
                         300: ["2 Polynomials"],
                         14: ["Algebraic Appendix ............ 283"]},
                        [{"ch": 1, "name": "Basic Notions", "start": 20, "end": 30},
                         _apx(5, "Algebraic Appendix", 299, 300)])
        probs = _problems(d)
        self.assertEqual(len(probs), 1, probs)
        self.assertIn(FLAG, probs[0])
        self.assertIn("裸 'appendix'", probs[0])

    def test_printed_numeric_ordinal_accepted(self):
        """正例：印面确实印 "Appendix 3" → 放行。"""
        d = _mk_extract({100: ["Appendix 3", "Additional formulae"]},
                        [_apx(3, "3 Additional formulae", 100, 101)])
        self.assertEqual(_problems(d), [])

    def test_front_matter_only_evidence_accepted(self):
        """正文标题页不重复印序标、只在目录页印 "Appendix 2" → 前置目录区取证放行。"""
        d = _mk_extract({8: ["Appendix 2 . . . . . . 155"],
                         155: ["Harmonic functions", "2.1 Mean value property"]},
                        [_apx(2, "Harmonic functions", 155, 160)])
        self.assertEqual(_problems(d), [])

    def test_chinese_numeral_evidence_accepted(self):
        """中文数目字与阿拉伯数字等价：印 "附录三" 登记 num=3 → 放行。"""
        d = _mk_extract({50: ["附录三  傅里叶变换"]}, [_apx(3, "3 傅里叶变换", 50, 55)])
        self.assertEqual(_problems(d), [])

    def test_bare_key_needs_no_evidence(self):
        """正例（合法形态）：键直接写裸 "appendix" → 序标归空，不取证。"""
        d = _mk_extract({299: ["Algebraic Appendix"]},
                        [{"ch": "appendix", "kind": 2, "name": "Algebraic Appendix",
                          "start": 299, "end": 300}])
        self.assertEqual(_problems(d), [])

    def test_letter_ordinal_exempt(self):
        """负例护栏：字母序标的印面形态多样（Lee 只印 "A. Point-Set Topology"），
        要求「Appendix + 字母相邻」会把合法书打成假阳 → 字母序标一律不判。"""
        d = _mk_extract({334: ["A. Point-Set Topology", "The material in this"]},
                        [_apx("A", "Point-Set Topology", 334, 355)])
        self.assertEqual(_problems(d), [])

    def test_unreadable_window_fails_closed(self):
        """页窗与目录区全无文字层 → 无法自证即拦截（fail-closed）。"""
        d = _mk_extract({1: [""], 200: [""]}, [_apx(7, "Hidden", 200, 201)])
        probs = _problems(d)
        self.assertEqual(len(probs), 1, probs)
        self.assertIn("取不到任何文字层", probs[0])

    def test_pattern_helper_shapes(self):
        rx = evidence_pattern("5", 2)
        self.assertIsNotNone(rx.search("APPENDIX 5 Axioms"))
        self.assertIsNotNone(rx.search("附录 5、预备知识"))
        self.assertIsNone(rx.search("Appendix A Axioms"))
        # 谓词本身与序标形态无关；「字母序标一律不判」的收窄发生在
        # appendix_ordinal_problems（见 test_letter_ordinal_exempt）。
        self.assertIsNotNone(evidence_pattern("A", 2).search("Appendix A"))
        self.assertEqual(page_text({"text": [{"text": "x"}, {"text": "y"}]}), "x\ny")


class TestMakeConfigWiring(unittest.TestCase):
    """闸必须接在 make_config（chapter_map 的最早消费点）上，硬退出且不写配置。"""

    def _run_main(self, d):
        import make_config
        with io.open(os.path.join(d, "_extraction_done.json"), "w") as f:
            f.write("{}")
        buf = io.StringIO()
        argv_bak = sys.argv
        sys.argv = ["make_config.py", d]
        try:
            with redirect_stdout(buf):
                rc = make_config.main()
        finally:
            sys.argv = argv_bak
        return rc, buf.getvalue(), os.path.exists(os.path.join(d, "verify_config.json"))

    def test_make_config_blocks_fabricated_ordinal(self):
        d = _mk_extract({299: ["Algebraic Appendix"], 20: ["Basic Notions"]},
                        [{"ch": 1, "name": "Basic Notions", "start": 20, "end": 30},
                         _apx(5, "Algebraic Appendix", 299, 300)])
        rc, out, wrote = self._run_main(d)
        self.assertEqual(rc, 2, out[-500:])
        self.assertIn("BLOCKED", out)
        self.assertFalse(wrote, "被拦时不得写出 verify_config.json")

    def test_make_config_passes_bare_appendix(self):
        d = _mk_extract({299: ["Algebraic Appendix"], 20: ["Basic Notions"]},
                        [{"ch": 1, "name": "Basic Notions", "start": 20, "end": 30},
                         {"ch": "appendix", "kind": 2, "name": "Algebraic Appendix",
                          "start": 299, "end": 300}])
        rc, out, _wrote = self._run_main(d)
        self.assertNotIn("附录/补篇序标没有印刷证据", out, out[-500:])
        self.assertNotEqual(rc, 2, out[-500:])


if __name__ == "__main__":
    unittest.main(verbosity=2)
