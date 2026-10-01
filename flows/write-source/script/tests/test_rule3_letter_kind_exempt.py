"""回归：write-source 规则3 机械闸只管**数字章**，字母序标的附录 / 补篇豁免
（用户裁定 2026-10-01，Katok《Introduction to the Modern Theory of Dynamical
Systems》实测：附录A 中/英 70k/128k、补篇S 中/英 76k/106k 均为合篇单文件，而
``tools/split_chapters.py`` 只产 ``第N章_M_*``/``ChapterN_M_*``、从不扫描
``附录X``/``AppendixX``/``补篇S``/``SupplementS``——字母合篇即便超阈也无从「拆」，
故 ``_merge_present_ok`` 不得据 oversized 拒绝 mark）。

本测试锁死：
  ① 数字章合并件超阈 → 仍 FAIL（规则3 对章继续生效，零回归）；
  ② 附录 kind=2 合并件超阈 → 放行；
  ③ 补篇 kind=3 合并件超阈 → 放行；
  ④ 混合章（超阈数字章 + 超阈附录 + 超阈补篇）→ 仅数字章被点名，
     oversized 明细只含章，证明附录 / 补篇被豁免。
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
else:
    _ROOT = str(Path(__file__).resolve().parents[4])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
import lib.boot  # noqa: E402
lib.boot.setup()

from flows._flow_contract import (  # noqa: E402
    MERGED_MD_CHAR_LIMIT, physical_evidence as pe)
from data.book_structure.book_structure import prime_chapter_kinds  # noqa: E402

_BIG = MERGED_MD_CHAR_LIMIT + 1000


class Rule3LetterKindExemptTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.book = self.root / "book"
        self.ex = self.book / "_extract"
        (self.ex / "book_structure").mkdir(parents=True)

        # chapter_map：数字章 1（kind=1）、附录 A（kind=2）、补篇 S（kind=3）
        (self.ex / "chapter_map.json").write_text(json.dumps({
            "language": "en",
            "chapters": [
                {"kind": 1, "num": 1, "name": "Phase Spaces"},
                {"kind": 2, "num": "A", "name": "Background Material"},
                {"kind": 3, "num": "S", "name": "Nonuniformly Hyperbolic"},
            ],
        }, ensure_ascii=False), encoding="utf-8")
        prime_chapter_kinds(str(self.ex))

        # 每章源 manifest（EN）+ 超阈合并件（放书根）
        for udir in ("ch1", "appendixA", "supplementS"):
            d = self.ex / "book_structure" / "units" / udir
            d.mkdir(parents=True, exist_ok=True)
            (d / "manifest.json").write_text(
                json.dumps({"language": "en"}), encoding="utf-8")
        self._write_big("Chapter1_Phase_Spaces.md")
        self._write_big("AppendixA_Background_Material.md")
        self._write_big("SupplementS_Nonuniformly_Hyperbolic.md")

    def tearDown(self):
        self._tmp.cleanup()

    def _write_big(self, name):
        (self.book / name).write_text(
            "# t\n\n" + "x" * _BIG + "\n", encoding="utf-8")

    def _ok(self, keys):
        return pe._merge_present_ok(str(self.book), str(self.ex),
                                    list(keys), want_tgt=False)

    def test_numbered_chapter_oversized_still_blocks(self):
        ok, detail = self._ok(["1"])
        self.assertFalse(ok)
        self.assertIn("Chapter1_Phase_Spaces.md", detail)

    def test_appendix_oversized_exempt(self):
        ok, detail = self._ok(["A"])
        self.assertTrue(ok, detail)

    def test_supplement_oversized_exempt(self):
        ok, detail = self._ok(["S"])
        self.assertTrue(ok, detail)

    def test_mixed_only_chapter_flagged(self):
        ok, detail = self._ok(["1", "A", "S"])
        self.assertFalse(ok)
        self.assertIn("Chapter1", detail)
        # 附录 / 补篇文件名不得出现在 oversized 明细里（证明被豁免）
        self.assertNotIn("AppendixA_Background_Material.md", detail)
        self.assertNotIn("SupplementS_Nonuniformly_Hyperbolic.md", detail)


if __name__ == "__main__":
    unittest.main()
