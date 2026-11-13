# -*- coding: utf-8 -*-
"""非阻断明细的机器可读旁路（缺陷③，2026-10-23 根治）。

根因（茆诗松《概率论与数理统计教程》实测）：`report.print_result` 的
「EXTRA-MENTION · 领域归属豁免」段超过 40 个键就印 `…（其余 N 个从略）`，
而该书该桶有 228 个键 —— 被截掉的 188 个在盘上**没有任何副本**。
于是「非阻塞」实际等于「不可机器复核」：销项时只能靠重跑一次性探针脚本才能
看见全量清单（`_extract/_mentions_20261023.json` 就是那么来的），
日志本身不能自证它省略了什么。

口径（本测试锁定）：
  1. 截断只许截**呈现**，不许截**账**：`print_result` 先经 `lib.verify_detail.dump`
     把全部非阻断桶落成 `<extract>/verify_detail/<md 名>.json`，截断行点名该路径。
  2. 旁路**只读不判**：PASS/FAIL 与逐桶判定逐字节不受是否落盘影响。
  3. 全空不产文件（收官书多数章节如此，零信息产物不许污染书树）。
  4. 阻断桶（truly_missing / blocking / F 层 / U 层）不进旁路——它们必须整条看，
     需要旁路来兜就等于判据有缺陷。

运行：
  python verify/script/tests/test_verify_detail_sidecar.py
"""
import io
import json
import os
import shutil
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
for _p in (_ROOT, os.path.join(_ROOT, "lib"),
           os.path.join(_ROOT, "verify", "script")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot  # noqa: E402
_boot.setup()

import report as RP  # noqa: E402
from lib import verify_detail as VD  # noqa: E402


def _base_r(extract_dir=None, **over):
    """print_result 会 `r[...]` 直取的最小结果字典（缺键即 KeyError = 测试自身坏）。"""
    r = {
        "ch": 2,
        "md": os.path.join(extract_dir or "", "._verify_merged_ch2_cn.md"),
        "d_layer": {},
        "label_warns": [],
        "truly_missing": [],
        "mentioned_only": [],
        "extra": [],
        "blocking": [],
        "warnings": [],
        "katex_errors": [],
        "katex_lines": [],
        "fig_missing": [],
        "fig_extra": [],
        "fig_invalid": [],
        "fig_invalid_warn": [],
        "fig_skipped": True,
        "entry_keys": ["例2.2.1"],
        # U 层正常跑完时必发非空覆盖率账本；这里补上以免被「无证据」闸误拦
        # （本文件测的是 verify_detail 旁路，与 U 层无关）。
        "md_order_stats": {"units": 1, "expected": 1, "located": 1,
                           "coverage": 100.0, "units_dir": "units",
                           "unmeasurable": 0, "um_keys": [],
                           "ambiguous": 0, "amb_keys": [], "unlocated": []},
    }
    if extract_dir:
        r["extract_dir"] = extract_dir
    r.update(over)
    return r


class SidecarTest(unittest.TestCase):
    def setUp(self):
        self.ext = tempfile.mkdtemp(prefix="vd_sidecar_")

    def tearDown(self):
        shutil.rmtree(self.ext, ignore_errors=True)

    def _run(self, r):
        buf = io.StringIO()
        with redirect_stdout(buf):
            verdict = RP.print_result(r)
        return verdict, buf.getvalue()

    def test_truncated_bucket_points_at_full_listing(self):
        keys = [f"评注{i}" for i in range(1, 46)]        # 45 > 40 → 截断
        r = _base_r(self.ext, extra_mention_domain=keys)
        verdict, out = self._run(r)
        self.assertEqual(verdict, "PASS")
        self.assertIn("其余 5 个从略", out)
        art = os.path.join(VD.SUBDIR, "verify_merged_ch2_cn.json")
        self.assertIn(os.path.join(self.ext, art), out, "截断行必须点名旁路文件")
        with io.open(os.path.join(self.ext, art), encoding="utf-8") as f:
            payload = json.load(f)
        self.assertEqual(payload["counts"]["extra_mention_domain"], 45)
        self.assertEqual(payload["detail"]["extra_mention_domain"], keys,
                         "旁路必须是**全量**清单，不能同样被截")
        self.assertEqual(payload["chapter"], 2)

    def test_verdict_is_independent_of_the_sidecar(self):
        """同一结果在「有 extract_dir（落旁路）」与「无」（不落）下判定一致。"""
        keys = [f"评注{i}" for i in range(1, 46)]
        with_ext, out_with = self._run(_base_r(self.ext, extra_mention_domain=keys))
        without_ext, out_without = self._run(_base_r(None, extra_mention_domain=keys))
        self.assertEqual(with_ext, without_ext)
        self.assertIn("其余 5 个从略", out_without)
        self.assertIn("未落盘", out_without, "无落点时须明说没写旁路，不得假装有")

    def test_blocking_items_still_fail_with_sidecar(self):
        r = _base_r(self.ext, truly_missing=["定理2.3-1"], extra_mention_domain=["评注7"])
        verdict, out = self._run(r)
        self.assertEqual(verdict, "FAIL")
        self.assertIn("定理2.3-1", out)
        with io.open(os.path.join(self.ext, VD.SUBDIR,
                                  "verify_merged_ch2_cn.json"), encoding="utf-8") as f:
            payload = json.load(f)
        self.assertNotIn("truly_missing", payload["detail"], "阻断桶不进旁路")
        self.assertEqual(payload["detail"]["extra_mention_domain"], ["评注7"])

    def test_all_empty_writes_nothing(self):
        verdict, _out = self._run(_base_r(self.ext))
        self.assertEqual(verdict, "PASS")
        self.assertFalse(os.path.exists(os.path.join(self.ext, VD.SUBDIR)),
                         "全空不得建目录污染书树")

    def test_nonblocking_buckets_are_carried_verbatim(self):
        r = _base_r(
            self.ext,
            mentioned_only=["例3.1.2"],
            extra_attested=["注5.2.1"], extra_attested_reasons={"注5.2.1": "印面误指"},
            long_formula_rows=["L120"], b_gap_warnings=["~ 缺号 3"],
            o_subitem_gaps=["~ 尾缺 (4)", "x 中间缺 (3)"],
            q_tag_mismatch=[{"number": "(3.6)", "summary_latex": "$x$"}],
        )
        self._run(r)
        with io.open(os.path.join(self.ext, VD.SUBDIR,
                                  "verify_merged_ch2_cn.json"), encoding="utf-8") as f:
            detail = json.load(f)["detail"]
        for name in ("mentioned_only", "extra_attested", "extra_attested_reasons",
                     "long_formula_rows", "b_gap_warnings", "q_tag_mismatch",
                     "o_subitem_tail_warnings"):
            self.assertIn(name, detail, name)
        self.assertEqual(detail["o_subitem_tail_warnings"], ["~ 尾缺 (4)"],
                         "O 层只走旁路里的 WARN 支（x 阻断项不进旁路）")

    def test_dump_returns_relative_display_path(self):
        self.assertEqual(VD.dump(_base_r(self.ext, extra_mention_domain=["评注1"])),
                         f"{VD.SUBDIR}/verify_merged_ch2_cn.json")
        self.assertIsNone(VD.dump(_base_r(self.ext)))
        self.assertIsNone(VD.dump(_base_r(None, extra_mention_domain=["评注1"])))

    def test_sidecar_is_visible_to_plain_glob(self):
        """旁路名不得以 `.` 起头：合并视图 `._verify_merged_*` 会把它带成隐藏文件。"""
        self._run(_base_r(self.ext, extra_mention_domain=["评注1"]))
        found = os.listdir(os.path.join(self.ext, VD.SUBDIR))
        self.assertEqual(found, ["verify_merged_ch2_cn.json"])
        self.assertFalse(found[0].startswith("."))

    def test_unmeasurable_bucket_shows_on_the_coverage_line(self):
        """U 层「量不到」桶（空正文占位 / 整块正文 <6 字）已从覆盖率分母剔出，
        于是覆盖率会显示 100%。此时**报告行必须同屏交代这几条没测**、旁路必须因它们
        落盘：否则「工具量不到」被静音成「交付没问题」，而 `located == expected` 恰好
        让旁路的旧触发条件不再命中（2026-10-30 周民强 8 条 + 全架普查 163 条空正文）。"""
        st = {"units": 132, "expected": 130, "located": 130, "coverage": 100.0,
              "units_dir": "units", "unmeasurable": 2,
              "um_keys": [u"description«D12»", u"chapter«appendix»"], "unlocated": []}
        _v, out = self._run(_base_r(self.ext, md_order_stats=st))
        self.assertIn(u"100.0%", out)
        self.assertIn(u"量不到 2 条", out, u"覆盖率 100%% 时必须说出这 2 条没测：%s" % out)
        self.assertIn(u"D12", out)
        with io.open(os.path.join(self.ext, VD.SUBDIR,
                                  "verify_merged_ch2_cn.json"), encoding="utf-8") as f:
            detail = json.load(f)["detail"]
        self.assertEqual(detail["md_order_stats"]["unmeasurable"], 2)
        self.assertEqual(detail["md_order_stats"]["um_keys"], st["um_keys"],
                         u"旁路须带**全量** um_keys，不受报告行前 12 条截断")

    def test_unlocated_still_reports_beside_unmeasurable(self):
        """负向对照：正文够长却没出现在交付里的那条仍留在分母并报「未定位」，
        覆盖率随之 <100%——证明新桶不是把「量不到」扩大成静音豁免的后门。"""
        st = {"units": 5, "expected": 2, "located": 1, "coverage": 50.0,
              "units_dir": "units", "unmeasurable": 2,
              "um_keys": [u"description«D1»"], "unlocated": [u"item«1.2»"]}
        _v, out = self._run(_base_r(self.ext, md_order_stats=st))
        self.assertIn(u"已定位 1/2", out)
        self.assertIn(u"未定位 1 条", out)
        self.assertIn(u"item«1.2»", out)
        self.assertIn(u"量不到 2 条", out)


    def test_ambiguous_bucket_is_reported_apart_from_unlocated(self):
        """整块正文在交付里出现 ≥2 次 = 位置歧义（内容在，只是本闸不猜位置），
        必须与「未定位 = 交付里读不到这块」分桶显示并全量进旁路：2026-10-30 全架
        571 条残差实测 = 189 歧义 + 71 未定位，混报会让前者冒充后者、把真脱钩的 71 条埋掉。"""
        st = {"units": 4, "expected": 4, "located": 2, "coverage": 50.0,
              "units_dir": "units", "unmeasurable": 0, "um_keys": [],
              "ambiguous": 1, "amb_keys": [u"description«D7»"],
              "unlocated": [u"item«1.3»"]}
        _v, out = self._run(_base_r(self.ext, md_order_stats=st))
        self.assertIn(u"位置歧义 1 条", out, out)
        self.assertIn(u"description«D7»", out)
        self.assertIn(u"未定位 1 条", out)
        self.assertIn(u"item«1.3»", out)
        with io.open(os.path.join(self.ext, VD.SUBDIR,
                                  "verify_merged_ch2_cn.json"), encoding="utf-8") as f:
            detail = json.load(f)["detail"]
        self.assertEqual(detail["md_order_stats"]["amb_keys"], st["amb_keys"])
        self.assertEqual(detail["md_order_stats"]["unlocated"], st["unlocated"],
                         u"两桶各落各的键，旁路不得只留一份")

    def test_ambiguous_alone_still_triggers_sidecar(self):
        """只有歧义、没有未定位时旁路仍要落盘：歧义留在分母里 ⇒ `located != expected`
        这条既有条件必须命中（别把它误当成「量不到」那种已剔出分母的桶）。"""
        st = {"units": 3, "expected": 3, "located": 1, "coverage": 33.3,
              "units_dir": "units", "unmeasurable": 0, "um_keys": [],
              "ambiguous": 2, "amb_keys": [u"desc«A»", u"desc«B»"], "unlocated": []}
        self._run(_base_r(self.ext, md_order_stats=st))
        p = os.path.join(self.ext, VD.SUBDIR, "verify_merged_ch2_cn.json")
        self.assertTrue(os.path.isfile(p), u"歧义条目须有全量落点（报告行只印前 12 条）")


if __name__ == "__main__":
    unittest.main(verbosity=2)
