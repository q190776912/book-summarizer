r"""Q 层节检测支持破折号序标回归（do Carmo ch3/ch5 实测，2026-09-26）。

背景：公式按节重排号（scope 3）时，Q 层用 `_MD_SEC_TWO`（旧只认 `\d+\.\d+`）
给 summary 分节桶。do Carmo 节标题印作 `## §5-10`（dash），旧判据全部落空，
`## §5-10` 反而被 `_MD_SEC_ONE` 截成节 "5" → 全章挤进一个桶 → 各节都印 (1)(2)
的**合法重号**被误报 FORMULA INCONSISTENT duplicate（ch3 9 条、ch5 7 条假 FAIL）。

修复 = `_MD_SEC_TWO` 接受 `[.-]` 分隔且节键统一经 `norm_secnum` 归一点分
（与 scoped-ignore 键 `4.7#1` 同源）；`_extract_summary_tags_sectioned` 同步归一。

断言：
  1. dash 标题检出为点分节键，跨节同 (1) 号分属两桶（不判 duplicate）；
  2. 同一节内真重复仍计 counts>1（不得放行真错）；
  3. 点分书行为零回归。
"""
import os
import sys
import tempfile
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

from formula_tag import (_detect_summary_sections,
                         _extract_summary_tags_sectioned)


def _md(body):
    f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False,
                                    encoding="utf-8")
    f.write(body)
    f.close()
    return f.name


class DashSectionDetectionTest(unittest.TestCase):
    def test_dash_headings_become_dotted_keys(self):
        body = ("# Chapter 5: X\n\n## §5-1 Intro\n\ntext\n\n"
                "## §5-10 Abstract\n\ntext\n")
        secs, _find_re, _split_re = _detect_summary_sections(body)
        self.assertEqual(secs, ["5.1", "5.10"])

    def test_same_number_in_different_dash_sections_not_duplicate(self):
        body = ("## §5-2 Rigidity\n\n$$ a = b \\tag{1} $$\n\n"
                "## §5-3 Hopf\n\n$$ c = d \\tag{1} $$\n")
        path = _md(body)
        try:
            secs, find_re, split_re = _detect_summary_sections(body)
            tags = _extract_summary_tags_sectioned(path, find_re, split_re)
            by_sec = {}
            for sec, t in tags:
                by_sec.setdefault(sec, []).append(t.normalized)
            self.assertEqual(by_sec, {"5.2": ["1"], "5.3": ["1"]})
            counts = {}
            for sec, t in tags:
                k = (sec, t.normalized)
                counts[k] = counts.get(k, 0) + 1
            self.assertTrue(all(v == 1 for v in counts.values()),
                            "跨节合法重号不得计入节内重复")
            self.assertNotEqual(len(tags), 1)
        finally:
            os.unlink(path)

    def test_within_section_duplicate_still_counts(self):
        body = ("## §5-2 Rigidity\n\n$$ a = b \\tag{1} $$\n\n"
                "$$ e = f \\tag{1} $$\n\n"
                "## §5-3 Hopf\n\n$$ c = d \\tag{1} $$\n")
        path = _md(body)
        try:
            secs, find_re, split_re = _detect_summary_sections(body)
            tags = _extract_summary_tags_sectioned(path, find_re, split_re)
            sec1 = [t for s, t in tags if s == "5.2"]
            self.assertEqual(len(sec1), 2, "同节真重复必须仍在同一桶（可被 duplicate 判出）")
        finally:
            os.unlink(path)

    def test_dotted_style_regression(self):
        body = ("## §3.2 Def\n\n$$ a \\tag{2} $$\n\n## §3.5 More\n\n"
                "$$ b \\tag{2} $$\n")
        secs, find_re, split_re = _detect_summary_sections(body)
        self.assertEqual(secs, ["3.2", "3.5"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
