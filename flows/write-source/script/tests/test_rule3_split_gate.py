"""回归：write-source 规则3「超大章按节拆分」机械闸（集合论导引 ch1–3 收官漏拆根治，2026-09-25）。

当年三章合并 md（151k–217k 字符）远超 60000 阈值却一路绿灯：merge_all 证据只查
「md 在位 + 契约项在位」，不查「该拆没拆」。根治 = _flow_contract 新增
_oversized_merged_md 并在 merge_all_ok 硬拦。本测试锁死判据：
合并形态超阈 = 检出；恰等于阈值 / 低于阈值 = 放行；已按节拆分（节号形态）
即使单节超阈也不检——规则只拆到「节」一级，节文件超限是允许形态。
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


if __name__ == "__main__":
    unittest.main()
