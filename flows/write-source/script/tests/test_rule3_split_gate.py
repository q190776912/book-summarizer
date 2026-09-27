"""回归：write-source 规则3「超大章按节拆分」机械闸（集合论导引 ch1–3 收官漏拆根治，2026-09-25）。

当年三章合并 md（151k–217k 字符）远超 60000 阈值却一路绿灯：merge_all 证据只查
「md 在位 + 契约项在位」，不查「该拆没拆」。根治 = _flow_contract 新增
_oversized_merged_md 并在 merge_all_ok 硬拦。本测试锁死判据：
合并形态超阈 = 检出；恰等于阈值 / 低于阈值 = 放行；已按节拆分（节号形态）
即使单节超阈也不检——规则只拆到「节」一级，节文件超限是允许形态。

第二轮（2026-09-28 Strogatz 实测）补**跨语配对**判据 `_split_form_pairing_problems`：
绕开 `tools/split_chapters.py` 只手工拆了 EN 六章，CN 同名六章仍是合并单文件，
而 `_oversized_merged_md` 逐语独立判定看不见这种不对称 → 一路绿灯交付两版对不上。
"""
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
    MERGED_MD_CHAR_LIMIT, physical_evidence)

_oversize = physical_evidence._oversized_merged_md


class TestRule3SplitGate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, name, chars):
        p = self.dir / name
        p.write_text("x" * chars, encoding="utf-8")
        return str(p)

    def test_cn_merged_oversized_detected(self):
        big = self._write("第1章_大章.md", MERGED_MD_CHAR_LIMIT + 1)
        out = _oversize([big])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0][0], "第1章_大章.md")
        self.assertGreater(out[0][1], MERGED_MD_CHAR_LIMIT)

    def test_en_merged_oversized_detected(self):
        big = self._write("Chapter1_Big.md", MERGED_MD_CHAR_LIMIT + 10)
        self.assertTrue(_oversize([big]))

    def test_merged_at_or_below_limit_ok(self):
        exact = self._write("第2章_临界.md", MERGED_MD_CHAR_LIMIT)
        small = self._write("第3章_小结.md", 100)
        self.assertEqual(_oversize([exact, small]), [])

    def test_split_form_never_checked(self):
        # 节号形态（第N章_M_*.md / ChapterN_M_*.md）即使超阈也放行：
        # 规则只拆到节一级，子节留在父节文件内是允许形态。
        s1 = self._write("第1章_1.1_节名.md", MERGED_MD_CHAR_LIMIT + 500)
        s2 = self._write("Chapter2_2.1_Section.md", MERGED_MD_CHAR_LIMIT + 500)
        self.assertEqual(_oversize([s1, s2]), [])

    def test_bom_counted_as_content_not_crash(self):
        p = self.dir / "第4章_BOM.md"
        p.write_text("\ufeff" + "字" * (MERGED_MD_CHAR_LIMIT + 1), encoding="utf-8")
        self.assertTrue(_oversize([str(p)]))

    def test_missing_file_tolerated(self):
        # 读不到的文件跳过而不是抛异常（fail-open 仅限 IO，超阈判定仍 fail-closed）
        self.assertEqual(_oversize([str(self.dir / "不存在.md")]), [])


class TestRule3SplitPairing(unittest.TestCase):
    """跨语配对判据：任一语言已按节拆分，其余语言不得留合并件；都拆则节号须一致。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _mk(self, *names):
        for n in names:
            (self.dir / n).write_text("# t\n\nbody\n", encoding="utf-8")

    def _probs(self, langs=("en", "cn")):
        return physical_evidence._split_form_pairing_problems(
            str(self.dir), "3", list(langs))

    def test_en_split_cn_merged_detected(self):
        # 实测事故形态：EN 已拆成节文件、CN 仍整章合并
        self._mk("Chapter3_3.0_Introduction.md", "Chapter3_3.1_Bifurcation.md",
                 "第3章_Bifurcations.md")
        out = self._probs()
        self.assertEqual(len(out), 1, out)
        self.assertIn("合并件", out[0])
        self.assertIn("第3章_Bifurcations.md", out[0])
        self.assertIn("配对拆分", out[0])

    def test_cn_split_en_merged_detected(self):
        # 反方向同样要抓（中文源书先拆、译文漏拆）
        self._mk("第3章_3.0_引言.md", "第3章_3.1_分岔.md", "Chapter3_Bifurcations.md")
        self.assertEqual(len(self._probs()), 1)

    def test_both_split_same_keys_ok(self):
        self._mk("Chapter3_3.0_A.md", "Chapter3_3.1_B.md",
                 "第3章_3.0_甲.md", "第3章_3.1_乙.md")
        self.assertEqual(self._probs(), [])

    def test_both_split_different_keys_detected(self):
        self._mk("Chapter3_3.0_A.md", "Chapter3_3.1_B.md",
                 "第3章_3.0_甲.md", "第3章_3.1_乙.md", "第3章_3.2_丙.md")
        out = self._probs()
        self.assertEqual(len(out), 1, out)
        self.assertIn("节号集合不一致", out[0])

    def test_both_merged_is_oversize_gates_job(self):
        # 两语都合并：形态配对无话可说（超阈由 _oversized_merged_md 判）
        self._mk("Chapter3_Big.md", "第3章_大章.md")
        self.assertEqual(self._probs(), [])

    def test_single_language_book_skipped(self):
        # 单语书无配对可言：只拆了一语也须放行（误伤 = 中文书全堵）
        self._mk("第3章_3.0_引言.md", "第3章_3.1_分岔.md")
        self.assertEqual(self._probs(langs=("cn",)), [])
        self._mk("Chapter3_3.0_Intro.md")
        self.assertEqual(self._probs(langs=("en",)), [])

    def test_absent_group_not_double_reported(self):
        # 某语言整组缺失 → 交 missing 分支报，本闸不得重复出声
        self._mk("Chapter3_3.0_A.md", "Chapter3_3.1_B.md")
        self.assertEqual(self._probs(), [])

    def test_strogatz_accident_layout_replayed(self):
        # 当时真实交付形态全书回放：EN 六章按节拆分（8/9/7/8/7/8 个）、CN 同名六章
        # 仍是合并件，其余七章两语皆合并 → 必须恰好报出这六章，且不误伤七章。
        plan = {3: 8, 6: 9, 7: 7, 8: 8, 9: 7, 10: 8}
        for ch, n in plan.items():
            self._mk(*[f"Chapter{ch}_{ch}.{i}_S.md" for i in range(n)],
                     f"第{ch}章_Chapter_{ch}.md")
        for ch in (1, 2, 4, 5, 11, 12, 13):
            self._mk(f"Chapter{ch}_Name.md", f"第{ch}章_名.md")
        hits = {}
        for ch in range(1, 14):
            p = physical_evidence._split_form_pairing_problems(
                str(self.dir), str(ch), ["en", "cn"])
            if p:
                hits[ch] = p
        self.assertEqual(sorted(hits), sorted(plan))
        for ch, p in hits.items():
            self.assertEqual(len(p), 1)
            self.assertIn(f"{plan[ch]} 个节文件", p[0])


if __name__ == "__main__":
    unittest.main()
