# -*- coding: utf-8 -*-
"""Regression: parity 第 1 项「按 `file` 配对」（Kreyszig 泛函分析 ch4，2026-10-20）。

旧实现 ``for i, (a, b) in enumerate(zip(su, tu))`` 按 **manifest 下标**配对，于是只要
两侧顺序不同就张冠李戴。全库普查（38 本有译单元的书 / 逐章比对）命中 1 章：
Kreyszig ch4 两侧文件集合**完全相同**、仅 D-注单元与节标题先后差 26 个位置，zip 版
报出 **26 行「字段不一致」假阳**（该章字段本就全等），而真正该比的那一对被跳过；
按 `file` 配对后同一章命中 0 行。

顺序不同本身是**真缺陷**（`merge_units` 各按自己那侧的 `units` 次序拼接 → 源/译交付
md 阅读顺序分叉），故拆成独立一条，只报一次、给出差异位置数，不再伪装成 26 行字段错。

锁死：
1. 顺序不同 + 字段全等 → 只报 1 条「顺序」，**零**条「字段不一致」；
2. 漏译（源有译无）/ 多余（译有源无）分别报出文件名；
3. 同名单元在 manifest 里重复 → 报重复且不做位置猜测；
4. 配对成功但 `key` 不同 → 报出**是哪个文件**的哪个字段；
5. 完全一致 → 零问题、pairs 覆盖全部单元且顺序随源侧。
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

import check_translate_parity as ctp  # noqa: E402


def _u(fid, fname, **kw):
    rec = {"id": fid, "file": fname, "type": "item", "key": fid, "name": "N " + fid}
    rec.update(kw)
    return rec


def _src():
    # 实测形态：源侧把 D-注排在下一节标题**之前**（注属于上一节）
    return [_u("0014", "0014_section_4_2.md"),
            _u("0015", "0015_section_4_3.md"),
            _u("0016", "0016_desc_D2.md"),
            _u("0017", "0017_item_4_3-1.md")]


def _tgt(shift=True):
    lst = _src()
    if shift:                       # 译侧按 id 序登记：D-注落在节标题之后
        lst = [lst[0], lst[2], lst[1], lst[3]]
    return lst


class TestPairByFile(unittest.TestCase):
    def test_identical_lists_pair_fully(self):
        probs, pairs = ctp.pair_units(_src(), _src())
        self.assertEqual(probs, [])
        self.assertEqual(len(pairs), 4)
        self.assertEqual([a["file"] for a, _ in pairs],
                         [u["file"] for u in _src()])

    def test_order_skew_is_one_problem_not_nine(self):
        """🔴 主判据：zip 版在本例报 2 行字段假阳，file 版只报 1 行顺序真缺陷。"""
        probs, pairs = ctp.pair_units(_src(), _tgt())
        fields = [p for p in probs if "不一致：" in p]
        order = [p for p in probs if "顺序" in p]
        self.assertEqual(fields, [], probs)
        self.assertEqual(len(order), 1, probs)
        self.assertIn("2/4", order[0])          # 位置 2、3 的文件名不同
        self.assertEqual(len(pairs), 4, probs)  # 配对不受顺序影响，全部照比

    def test_missing_translation_reported_by_name(self):
        probs, pairs = ctp.pair_units(_src(), _tgt()[:3])
        self.assertTrue(any("漏译" in p and "0017_item_4_3-1.md" in p for p in probs), probs)
        self.assertTrue(any("单元数不一致" in p for p in probs), probs)
        self.assertEqual(len(pairs), 3)

    def test_extra_translation_reported_by_name(self):
        extra = _tgt() + [_u("0018", "0018_item_4_3-2.md")]
        probs, pairs = ctp.pair_units(_src(), extra)
        self.assertTrue(any("多余" in p and "0018_item_4_3-2.md" in p for p in probs), probs)
        self.assertEqual(len(pairs), 4)

    def test_duplicate_file_names_do_not_guess(self):
        dup = _tgt() + [_u("0016", "0016_desc_D2.md")]
        probs, pairs = ctp.pair_units(_src(), dup)
        self.assertTrue(any("重复" in p and "0016_desc_D2.md" in p for p in probs), probs)
        # 重复不得把顺序真缺陷伪装成一堆字段错，也不得多配一对
        self.assertEqual(len(pairs), 4, probs)
        self.assertFalse(any("顺序" in p for p in probs), probs)

    def test_field_difference_names_the_file(self):
        tgt = _tgt(shift=False)
        tgt[3] = _u("0017", "0017_item_4_3-1.md", key="4.3-2")
        probs, pairs = ctp.pair_units(_src(), tgt)
        self.assertEqual(len(probs), 1, probs)
        self.assertIn("0017_item_4_3-1.md", probs[0])
        self.assertIn("key", probs[0])

    def test_renamed_file_counts_as_lost_pair(self):
        """改名 = 一侧漏译 + 另一侧多余（旧 zip 版会把它配成 `file 不一致` 一行）。"""
        tgt = _tgt(shift=False)
        tgt[2] = _u("0016", "0016_desc_D2_renamed.md")
        probs, pairs = ctp.pair_units(_src(), tgt)
        self.assertTrue(any("漏译" in p and "0016_desc_D2.md" in p for p in probs), probs)
        self.assertTrue(any("多余" in p and "0016_desc_D2_renamed.md" in p for p in probs), probs)
        self.assertEqual(len(pairs), 3, probs)

    def test_empty_manifest_side(self):
        probs, pairs = ctp.pair_units(_src(), [])
        self.assertEqual(pairs, [])
        self.assertTrue(any("单元数不一致" in p for p in probs), probs)


class TestContractFields(unittest.TestCase):
    """PAIR_FIELDS 含契约登记四件（tags/images/content/ntype）——MR ch8 0037 实测盲区。

    2026-10-28：源侧按印面把 `\\tag{8.99}–{8.102}` 归还给 0038 后，译侧 0037 的 manifest
    记录仍挂着这 4 式。判据 2 比**单元正文**的 tag 集合（两侧正文一致 → 不报），
    gate 却拿**该单元自己的** manifest 期望值 → 「源 gate 绿 / 译 gate 红 / parity 绿」。
    全库 33,649 个配对单元普查：除这 1 处外四个字段源/译恒等，故判据无假阳代价。
    """

    def _pair(self, **tgt_kw):
        src = _u("0037", "0037_desc_D15.md", type="desc", ntype="description",
                 tags=["8.92", "8.93"], images=[], content=131)
        tgt = _u("0037", "0037_desc_D15.md", type="desc", ntype="description",
                 tags=["8.92", "8.93"], images=[], content=131)
        tgt.update(tgt_kw)
        return ctp.pair_units([src], [tgt])

    def test_stale_translate_tags_is_a_problem(self):
        """真实事故形态：译侧多记 8.99–8.102 → 必须点名单元并点名 tags。"""
        probs, _pairs = self._pair(tags=["8.92", "8.93", "8.99", "8.100"])
        self.assertEqual(len(probs), 1, probs)
        self.assertIn("0037_desc_D15.md", probs[0])
        self.assertIn("tags", probs[0])

    def test_identical_contract_fields_are_clean(self):
        """两侧登记完全一致（含空 images / content 数字）→ 零问题，判据不添假阳。"""
        probs, pairs = self._pair()
        self.assertEqual(probs, [], probs)
        self.assertEqual(len(pairs), 1)

    def test_image_and_content_drift_each_reported(self):
        for kw in ({"images": ["figure/ch08_fig8.7.png"]}, {"content": 130},
                   {"ntype": "descriptionx"}):
            probs, _ = self._pair(**kw)
            self.assertEqual(len(probs), 1, "%s → %s" % (kw, probs))
            self.assertIn(next(iter(kw)), probs[0], probs[0])

    def test_absent_field_treated_as_empty_not_a_drift(self):
        """一侧登记为空表/空串、另一侧整个缺键 → 现口径视为相同（判据放宽处要留痕）。

        钉住 `str(rec.get(fld) or "")` 的语义：它把 `[]`/`""`/`0`/缺键一律折成空串。
        非空 → 缺键**仍算漂移**（见 test_stale_translate_tags_is_a_problem 的反向）。
        """
        src = _u("0037", "0037_desc_D15.md", type="desc", ntype="",
                 name="", tags=[], images=[], content=0)
        tgt = {"id": "0037", "file": "0037_desc_D15.md", "type": "desc",
               "key": "0037", "name": ""}                # 四个契约字段全部缺键
        probs, _ = ctp.pair_units([src], [tgt])
        self.assertEqual(probs, [], probs)
        tgt2 = dict(tgt, tags=["8.99"])                  # 反向：源空、译凭空多记
        probs2, _ = ctp.pair_units([src], [tgt2])
        self.assertEqual(len(probs2), 1, probs2)
        self.assertIn("tags", probs2[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
