"""Regression: 11b「OCR 乱码重复片段」对行首粗体标题的误判根治（Rising Sea ch9 0053, 2026-09-24）。

Vakil 印刷标题「General fibers, generic fibers, generically finite morphisms」里
「fibers, generic」合法连续并列两次（并列同义词），旧判据在原始行上跑
`(.{12,}?)\1+` 把它误报成 OCR 抽风复制。根治 = 扫描前先剥离开头的 `**…**`
粗体 run-in 标签，只对标签之后的正文查重。锁死：并列同义词标题放行；
标题**之后同行正文**里的真·重复仍被捕获。
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


def _dup_msgs(probs):
    return [p for p in probs if "乱码重复" in p]


class Test11bTitleExemption(unittest.TestCase):
    def test_parallel_synonym_title_exonerated(self):
        # the exact ch9 0053 case: doubled "fibers, generic" lives inside the bold title
        body = ('**9.3.6 General fibers, generic fibers, generically finite '
                'morphisms.** The phrases "generic fiber" and "general fiber" '
                'parallel the phrases "generic point" and "general point".')
        ok, probs = cuq.check_body("item", "9.3-6", body)
        self.assertEqual(_dup_msgs(probs), [], probs)

    def test_body_duplicate_after_title_still_flagged(self):
        # genuine OCR copy-fest lands in the prose AFTER the label
        body = ('**9.3.7 Some title.** we consider the structure sheaf of the '
                'structure sheaf of the scheme as defined previously.')
        ok, probs = cuq.check_body("item", "9.3-7", body)
        self.assertTrue(_dup_msgs(probs), probs)


if __name__ == "__main__":
    unittest.main()
