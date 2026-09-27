"""test_chapter_map_bare_num_opener.py — 章开页「独占大号章号数字」形态的起点判据。

缺陷根因（Apostol《Introduction to Analytic Number Theory》实测 2026-09-28）：
该书开页不印 "Chapter N"，而是把章号排成**独占一行的超大数字**（p158 首行 "7"），
标题词在同一带内（OCR 可能把数字排到第 0/1/2 行，如 p169 "Periodic Arithmetical
Functions / 8 / and Gauss Sums"）；该章**第二页**起改用行内页眉
"7: Dirichlet's theorem on primes in arithmetic progressions"。两者标题归一后
同分，Mode B 取先见者时按页序命中页眉页 → 起点整体后移 1-2 页，
ch7 的 §7.1/§7.2 与 Theorem 7.1 被切进 ch6 尾部（实测 ch7 160→真 158、
ch8 170→真 169、ch12 262→真 261）。页码是下游所有阶段的区间真值，
一处起点后移就吃掉整节内容。

修复形态：`scan_openers` 除 "Chapter N" 外，还收「顶部三行内独占一行的 1-3 位
数字 + 同带内标题行」为 A0 开页证据（A0 优先于 A/B，且要求章号与本章号一致）。

正向：数字开页 + 后一页页眉同分 → 取开页页；数字被 OCR 排到第 1/2 行也能命中。
负向：①纯数字表格页（顶部全是数字、无 ≥4 字母标题行）不得成为开页；
      ②数字在但标题不匹配 → 不落 A0，交回 A/B（不抢别章）；
      ③原 "Chapter N" 形态行为不变（回归）。
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "lib"))
import lib.boot as _boot  # noqa: E402
_boot.setup()

import importlib.util  # noqa: E402

_SPEC = importlib.util.spec_from_file_location(
    "build_chapter_map", os.path.join(_ROOT, "tools", "build_chapter_map.py"))
bcm = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(bcm)


def _write_pages(dirpath, pages):
    for pno, lines in pages.items():
        with open(os.path.join(dirpath, "page_%03d.json" % pno), "w",
                  encoding="utf-8") as f:
            json.dump({"page": pno,
                       "text": [{"poly": [100.0, 60.0 * (i + 1), 700.0, 60.0 * (i + 1),
                                          700.0, 60.0 * (i + 1) + 30.0,
                                          100.0, 60.0 * (i + 1) + 30.0],
                                 "text": t} for i, t in enumerate(lines)]},
                      f, ensure_ascii=False)


# ── Apostol 实测形态（PDF 页号 = page_NNN.json 页号）─────────────────────────
APOSTOL = {
    158: ["7", "Dirichlet's Theorem on", "Primes in Arithmetical Progressions",
          "7.1 Introduction"],
    159: ["7.2: Dirichlet's theorem for primes of the form 4n - 1 and 4n + 1",
          "7.2 Dirichlet's theorem for primes of", "the form 4n - 1 and 4n + 1"],
    160: ["7: Dirichlet's theorem on primes in arithmetic progressions",
          "such as 5n - 1, 8n - 1, 8n -- 3 and 8n + 3 (see Exercise 8)."],
    169: ["Periodic Arithmetical Functions", "8", "and Gauss Sums",
          "8.1 Functions periodic modulo k"],
    170: ["8: Periodic arithmetical functions and Gauss sums",
          "Theorem 8.1 For fixed k >= 1 let"],
    261: ["The Functions", "12", "(s) and L(s, x)", "12.1 Introduction"],
    262: ["12: The functions (s) and L(s, x)",
          "This representation of L(s, x) as a linear combination"],
    # 纯数字表格页（章号数字撞车风险）：顶部全是数字，无标题行
    229: ["14", "29", "22", "31"],
}
CH7 = {"ch": 7, "name": "算术级数中的素数", "name_en":
       "Dirichlet's Theorem on Primes in Arithmetic Progressions",
       "start": 160, "end": 169}
CH8 = {"ch": 8, "name": "周期算术函数与高斯和", "name_en":
       "Periodic Arithmetical Functions and Gauss Sums", "start": 170, "end": 189}
CH12 = {"ch": 12, "name": "函数 ζ(s) 与 L(s, χ)", "name_en":
        "The Functions zeta(s) and L(s, chi)", "start": 262, "end": 289}
CH14 = {"ch": 14, "name": "分拆", "name_en": "Partitions",
        "start": 316, "end": 340}


class ScanOpenersBareNumeral(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        _write_pages(cls.tmp.name, APOSTOL)
        cls.openers = {o["page"]: o for o in bcm.scan_openers(cls.tmp.name)}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_numeral_opener_pages_are_collected(self):
        """三种数字开页形态（数字在第 0/1/2 行）都要收进来。"""
        for pno, label in ((158, 7), (169, 8), (261, 12)):
            self.assertIn(pno, self.openers, "page %d 未被识别为开页" % pno)
            self.assertEqual(self.openers[pno]["label_norm"], label)

    def test_opener_title_spans_lines(self):
        """跨行标题拼接后须能命中本章标题（渐进候选里存在全长拼接）。"""
        cands = self.openers[158]["title_cands"]
        target = bcm.norm_title(CH7["name_en"])
        best = max(bcm.title_similarity(c, target) for c in cands)
        self.assertGreaterEqual(best, bcm.TITLE_THRESHOLD)

    def test_pure_number_table_page_is_not_an_opener(self):
        """负向：顶部只有数字的表格页不得冒充章号开页。"""
        self.assertNotIn(229, self.openers)


class DetectStartsPrefersNumeralOpener(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        _write_pages(cls.tmp.name, APOSTOL)
        cls.openers = bcm.scan_openers(cls.tmp.name)
        cls.headings, cls.title_lines = bcm.scan_headings(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_start_lands_on_opener_not_running_head(self):
        """正向：页眉页在 Mode B 同样满分，起点仍须取开页页。"""
        det = bcm.detect_starts([CH7, CH8, CH12], self.headings,
                                self.title_lines, openers=self.openers)
        self.assertEqual(det["7"][0], 158)
        self.assertEqual(det["8"][0], 169)
        self.assertEqual(det["12"][0], 261)

    def test_running_head_would_win_without_openers(self):
        """负向（证明修复必要）：摘掉开页证据后起点退回页眉页——
        即本项缺陷的真实表现，而非测试夹具本身正确。"""
        det = bcm.detect_starts([CH7, CH8, CH12], self.headings,
                                self.title_lines, openers=[])
        self.assertNotEqual(det.get("7", (None,))[0], 158)

    def test_mismatched_title_does_not_claim_opener(self):
        """负向：数字行在、标题不匹配本章 → 不落 A0，别章不得蹭这一页。"""
        ch = dict(CH14)
        det = bcm.detect_starts([ch], self.headings, self.title_lines,
                                openers=self.openers)
        self.assertNotEqual(det.get("14", (None,))[0], 158)


class LegacyChapterKeywordUnchanged(unittest.TestCase):
    def test_chapter_keyword_opener_still_works(self):
        """回归：原 "Chapter N" 独占首行形态行为不变。"""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        _write_pages(tmp.name, {
            40: ["Chapter 5", "MEASURABLE FUNCTIONS", "5.1 Introduction"],
            41: ["CHAPTER 5. MEASURABLE FUNCTIONS", "Let f be integrable."],
        })
        ops = {o["page"]: o for o in bcm.scan_openers(tmp.name)}
        self.assertIn(40, ops)
        self.assertEqual(ops[40]["label_norm"], 5)
        headings, title_lines = bcm.scan_headings(tmp.name)
        det = bcm.detect_starts(
            [{"ch": 5, "name": "Measurable Functions",
              "name_en": "Measurable Functions", "start": 41, "end": 60}],
            headings, title_lines, openers=bcm.scan_openers(tmp.name))
        self.assertEqual(det["5"][0], 40)


if __name__ == "__main__":
    unittest.main()
