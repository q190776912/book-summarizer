# -*- coding: utf-8 -*-
"""Regression: clean_cjk must not ship a heading whose title was CJK-only.

Evans PDE ch7/8/11/12 + Arnold ODE ch1-5 (found 2026-10-30 by the U-layer):
the EN-side chapter unit read `# Chapter 7: 线性演化方程`, and
``merge_units._assemble`` deletes CJK on the ``language == "en"`` side, so the
delivered file began with a title-less ``# Chapter 7:``.  The write-side source
language gate (#24) *exempts* `#` heading lines (bilingual titles are a legal
reader annotation), so the two rules together caught nothing.

The guard now refuses to assemble such a chapter.  These tests pin both the
detector and the two shapes that must NOT be blocked: a bilingual heading that
keeps an English title, and a heading that is number-only **in the print**.

Runs under stdlib unittest:
  python flows/write-source/script/tests/test_merge_empty_heading.py
"""
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[3])
sys_path_root = _ROOT
import sys
sys.path.insert(0, sys_path_root)
import lib.boot as _boot
_boot.setup()

spec = importlib.util.spec_from_file_location(
    "merge_units_guard",
    os.path.join(_ROOT, "flows/write-source/script/merge_units.py"))
mu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mu)


class TestDetector(unittest.TestCase):
    def test_cjk_only_title_is_caught(self):
        hit = mu.heading_emptied_by_cjk_clean(u"# Chapter 7: \u7ebf\u6027\u6f14\u5316\u65b9\u7a0b")
        self.assertIsNotNone(hit)
        self.assertEqual(hit[1], u"")                      # 剥完只剩编号骨架
        self.assertIn(u"\u7ebf\u6027", hit[0])             # 报出来的是那条中文题名

    def test_number_only_heading_in_print_is_not_caught(self):
        """Evans 书内真实形态：`### §7.1.1` 印面本就无题名 → 不得拦。"""
        for line in (u"### \u00a77.1.1", u"## \u00a72.7", u"#### 3.88"):
            self.assertIsNone(mu.heading_emptied_by_cjk_clean(line), line)

    def test_bilingual_title_that_keeps_english_is_not_caught(self):
        self.assertIsNone(mu.heading_emptied_by_cjk_clean(
            u"# Chapter 1: \u57fa\u672c\u6982\u5ff5 Basic Concepts"))
        self.assertIsNone(mu.heading_emptied_by_cjk_clean(
            u"## \u00a72.7 \u4e60\u9898 1\u201310 (Exercises to Section 2)"))

    def test_body_lines_are_not_headings(self):
        self.assertIsNone(mu.heading_emptied_by_cjk_clean(u"\u6b63\u6587\u4e2d\u7684\u4e00\u53e5\u8bdd"))


class TestAssembleGuard(unittest.TestCase):
    """🔴 控件：同一棵树，题名改成英文即放行——证明拦的是数据形态，不是判据本身。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ext = os.path.join(self.tmp, "_extract")
        self.udir = os.path.join(self.ext, "book_structure", "units", "ch1")
        os.makedirs(self.udir)
        self.md = os.path.join(self.tmp, "Chapter1_x.md")
        self._write(u"# Chapter 1: \u57fa\u672c\u6982\u5ff5")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, heading):
        with io.open(os.path.join(self.udir, "0001_chapter_1.md"), "w",
                     encoding="utf-8", newline="") as f:
            f.write(u"<!-- book-summarizer DONE unit: id=0001 type=chapter key=1 "
                    u"name=1 \u57fa\u672c\u6982\u5ff5 -->\n%s\n" % heading)
        with io.open(os.path.join(self.udir, "0002_item_T1.md"), "w",
                     encoding="utf-8", newline="") as f:
            f.write(u"<!-- book-summarizer DONE unit: id=0002 type=item key=T1 name=Theorem 1 -->\n"
                    u"**Theorem 1.** A plain english sentence with no CJK at all.\n")
        with io.open(os.path.join(self.udir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"language": "en", "final_md": os.path.basename(self.md),
                       "units": [
                           {"id": "0001", "file": "0001_chapter_1.md", "type": "chapter",
                            "key": "1", "hash": "0" * 40},
                           {"id": "0002", "file": "0002_item_T1.md", "type": "item",
                            "key": "T1", "hash": "0" * 40}]}, f, ensure_ascii=False)

    def _assemble(self):
        return mu._assemble(self.ext, "1", "units", clean_cjk=None, require_gate=False)

    def test_cjk_only_chapter_title_refuses(self):
        with self.assertRaises(SystemExit) as ctx:
            self._assemble()
        msg = str(ctx.exception)
        self.assertIn(u"0001_chapter_1.md", msg)
        self.assertIn(u"\u4e66\u5370\u7684\u82f1\u6587\u9898\u540d", msg)              # 处方要指到 name_en
        self.assertIn(u"\u57fa\u672c\u6982\u5ff5", msg)                      # 要印出被删的题名

    def test_english_title_assembles_and_keeps_the_title(self):
        self._write(u"# Chapter 1: Basic Concepts")
        lines, owners = self._assemble()
        self.assertEqual(lines[0].strip(), u"# Chapter 1: Basic Concepts")
        self.assertTrue(any(u"English" in l or u"english" in l for l in lines), lines)

    def test_cn_side_is_never_blocked(self):
        """翻译版（cn）不清 CJK：同一份中文题名必须照常拼出（闸只管 en 侧）。"""
        p = os.path.join(self.udir, "manifest.json")
        with io.open(p, encoding="utf-8") as f:
            man = json.load(f)
        man["language"] = "cn"
        with io.open(p, "w", encoding="utf-8") as f:
            json.dump(man, f, ensure_ascii=False)
        lines, _owners = self._assemble()
        self.assertIn(u"\u57fa\u672c\u6982\u5ff5", lines[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
