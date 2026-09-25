"""Regression: phantom「标题起于句中」误判根治（Rising Sea ch11 0022, 2026-09-25）。

契约 name 字段把星标 `⋆` 连同 OCR 噪声切进标题前缀（``*x EXERCISE: AN INFINITE-…``），
残留 residue 以字母 ``x`` 起头 → 旧判据把这条**完整、正文自带 `**Exercise 11.1.K…**`**
的真习题误报成「OCR 跨条目续行碎片（幻影习题）」。根治 = 正文含与本题 key 一致的
own-key 粗体头即豁免。锁死：真自洽条目放行；无 own-key 头的句中碎片仍拦。
"""
import sys
import unittest
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[3])
sys.path.insert(0, str(Path(_ROOT) / "flows" / "write-source" / "script"))

import check_unit_quality as cuq  # noqa: E402


class TestPhantomSelfKeyed(unittest.TestCase):
    def test_own_keyed_body_exonerated(self):
        body = ("**Exercise 11.1.K ($\\star\\star$ EXERCISE: AN INFINITE-DIMENSIONAL "
                "NOETHERIAN RING).** Let $A = k[x_1, x_2, \\ldots]$.\n\n(a) Show that $S$ "
                "is a multiplicative set.")
        probs = cuq.phantom_exercise_problems(
            "*x EXERCISE: AN INFINITE-DIMENSIONAL NOETHERIAN RING. Let A =", 4,
            [], [], "11.1.K", body=body)
        self.assertEqual([p for p in probs if "起于句中" in p], [], probs)

    def test_real_fragment_still_flagged(self):
        # genuine OCR continuation fragment: starts mid-sentence, no own-key header
        body = "and the map on stalks is an isomorphism, as required."
        probs = cuq.phantom_exercise_problems(
            "x and the map on stalks", 2, [], [], "11.1.L", body=body)
        self.assertTrue(any("起于句中" in p for p in probs), probs)

    def test_wrong_key_header_not_exempt(self):
        # a self-keyed-looking header for a DIFFERENT ordinal must not exonerate
        body = "**Exercise 11.1.M.** something else entirely here."
        probs = cuq.phantom_exercise_problems(
            "x continuation fragment", 2, [], [], "11.1.K", body=body)
        self.assertTrue(any("起于句中" in p for p in probs), probs)


if __name__ == "__main__":
    unittest.main()
