"""判据：ignore 的**标签限定形**只豁免该标签下的同号项，裸键形行为不变。

形态（Strogatz《Chaos, Fractals, and Noise》ch12 §12.8 实测，2026-10-29）：
印刷 §12.8 把 `Proposition 12.8.3` 排了**两次**（物理 p452「If the iterated function
system (12.8.1) is hyperbolic…」/ p454「Assume that the Si : X → X…」，裁剪目视确证
两处条头都印着 Proposition 12.8.3 = 印本自身重号），而 p459 段首
`Theorem 12.8.3 gives a practical way of constructing a picture of A.` 是全书不存在
的定理号之散文回指（当作 Theorem 12.8.2）。三级标签前置书的扫描键**不含标签**，
两者 key 都是 `12.8-3` → 旧 ignore 只有裸键形，登记 `12.8-3` 会把两条真实条目
一并从源侧校验里抹掉（= 用 ignore 抹真条目的反模式），不登记则闸门永 FAIL
（散文谓语判据的条件③按设计拦住它：契约确有 theorem 12.8-1/2）。

处置 = ignore 接受 `标签 [空格] 键` 形（含 `_canon_label` 中文规范形），命中要求
标签也相等。

正向：`"Theorem 12.8-3"` 命中 Theorem 项；裸键 `"12.8-3"` 仍命中任意标签（旧行为）。
负向：① `"Theorem 12.8-3"` **不**命中 Proposition 项（真条目留在校验里）；
     ② 标签不认识的串不误命中；③ label 缺失 / `uncat` 时只认裸键；
     ④ ignore 集为空恒 False（不抛）。

审核侧（`audit_ignore.run_audit`）必须认得同一形：契约该号只挂「命题」时，登记
`Theorem 12.8-3` 判 SAFE；若登记标签正是契约真身标签（或裸键）→ 照旧 SUSPECT，
「不许用 ignore 抹真实条目」这条底线不因新形而松。
"""
import os
import sys
import unittest
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[3])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
import lib.boot  # noqa: E402
lib.boot.setup()

sys.path.insert(0, os.path.join(_ROOT, "verify", "script"))
import check_structure_completeness as csc  # noqa: E402
import audit_ignore as AI  # noqa: E402
from key_parse import normkey  # noqa: E402

THEO = {"key": "12.8-3", "label": "Theorem", "has_label": True}
PROP = {"key": "12.8-3", "label": "Proposition", "has_label": True}
BARE = {"key": "12.8-3", "label": "uncat", "has_label": False}


def _k(*keys):
    return {normkey(k) for k in keys}


class TestIgnoreLabelQualified(unittest.TestCase):
    def test_label_qualified_hits_own_label(self):
        self.assertTrue(csc.ignore_hit_item(_k("Theorem 12.8-3"), THEO))

    def test_label_qualified_does_not_hit_other_label(self):
        # 🔴 核心负向：豁免回指不得顺手抹掉同键的真实 Proposition 条目
        self.assertFalse(csc.ignore_hit_item(_k("Theorem 12.8-3"), PROP))

    def test_nospace_and_canon_label_forms(self):
        self.assertTrue(csc.ignore_hit_item(_k("Theorem12.8-3"), THEO))
        self.assertTrue(csc.ignore_hit_item(_k("定理12.8-3"), THEO))

    def test_bare_key_still_matches_every_label(self):
        ign = _k("12.8-3")
        self.assertTrue(csc.ignore_hit_item(ign, THEO))
        self.assertTrue(csc.ignore_hit_item(ign, PROP))
        self.assertTrue(csc.ignore_hit_item(ign, BARE))

    def test_unknown_label_never_hits(self):
        self.assertFalse(csc.ignore_hit_item(_k("Corollary 12.8-3"), THEO))

    def test_uncat_item_only_bare_form(self):
        self.assertFalse(csc.ignore_hit_item(_k("Theorem 12.8-3"), BARE))

    def test_empty_ignore_is_false(self):
        self.assertFalse(csc.ignore_hit_item(set(), THEO))
        self.assertFalse(csc.ignore_hit_item(None, THEO))


class TestAuditLabelQualified(unittest.TestCase):
    """审核侧必须认得标签限定形，否则真条目占号会把正确豁免打成 SUSPECT。"""

    def _run(self, keys, canon_labels):
        orig = (AI._collect_ignore, AI._load_chapter_canons, AI._chapter_range,
                AI._scan_ocr_noise)
        AI._collect_ignore = lambda ext: [(k, "reason", "ignore_ch12.json") for k in keys]
        AI._load_chapter_canons = lambda ext, ch: (set(canon_labels),
                                                   {k: set(v) for k, v in canon_labels.items()})
        AI._chapter_range = lambda ext, ch: None
        AI._scan_ocr_noise = lambda *a, **kw: False
        try:
            return AI.run_audit("dummy-ext", chapter=12)
        finally:
            AI._collect_ignore, AI._load_chapter_canons = orig[0], orig[1]
            AI._chapter_range, AI._scan_ocr_noise = orig[2], orig[3]

    def test_other_label_on_that_number_is_safe(self):
        # 契约 12.8-3 挂的是 命题（两条真 Proposition），登记的是 Theorem 侧幻影
        rep = self._run(["Theorem 12.8-3"], {(12, 8, 3): {"命题"}})
        self.assertEqual(rep["suspect_count"], 0, rep["entries"])
        self.assertEqual(rep["entries"][0]["verdict"], "SAFE")

    def test_same_label_on_that_number_still_suspect(self):
        # 🔴 负向：豁免的标签**正是**契约真身所在标签 → 仍是「抹真实条目」，照拦
        rep = self._run(["Theorem 12.8-3"], {(12, 8, 3): {"定理", "命题"}})
        self.assertEqual(rep["suspect_count"], 1, rep["entries"])
        self.assertEqual(rep["entries"][0]["verdict"], "SUSPECT")

    def test_bare_key_on_existing_item_still_suspect(self):
        rep = self._run(["12.8-3"], {(12, 8, 3): {"命题"}})
        self.assertEqual(rep["suspect_count"], 1, rep["entries"])

    def test_label_of_key_forms(self):
        self.assertEqual(AI._label_of_key("Theorem 12.8-3"), "定理")
        self.assertEqual(AI._label_of_key("定理12.8-3"), "定理")
        self.assertEqual(AI._label_of_key("Proposition 12.8-3"), "命题")
        self.assertIsNone(AI._label_of_key("12.8-3"))
        self.assertIsNone(AI._label_of_key("TAIL:0:12.8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
