"""判据测试：`build_structure.sec_row_prefer` —— 同号 SEC 行择优（含「前缀加长」补全）。

立项缺陷（2026-09-28 Apostol《Introduction to Analytic Number Theory》ch2 §2.7 实测）：
正文节头跨两行印刷（`2.7 Dirichlet inverses and the Mobius` / `inversion formula`），
`scan_skeleton.heading_continuation` 的「三明治归位」判据不成立（续行之后紧接的是定理
头 `Theorem 2.8 …` 而非回到节头左边界的正文）→ 骨架里只留首行残缺标题。同号的**页眉
复本**（running head 恒为单行完整标题 `2.7: Dirichlet inverses and the Mobius inversion
formula`）晚一页到达，旧择优只让位给「公式碎片 / 空标题」，残缺标题永久胜出，契约节名
带病 → 顺着拆分灌进单元 H2、首行 `name=`、两侧 manifest 与最终 md 文件名。

负向锁死三件事：① 只在**新行页码不早于**在库行时补全（真节头先于其页眉复本，先到者页
码准）；② 只补**同一标题的前缀加长**，互非前缀（另一个标题）不换；③ 补全时**页码/y 沿用
在库行**，绝不把节起始页推到页眉复本那一页（否则 sec_pages、条目归节、U 层页码单调全偏）。
"""
import os
import sys
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[4])
for _p in (_ROOT, os.path.join(_ROOT, "lib"),
           os.path.join(_ROOT, "flows", "write-source", "structure", "script")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import unittest  # noqa: E402

from build_structure import sec_row_prefer  # noqa: E402


class TestPrefixUpgrade(unittest.TestCase):
    def test_running_head_completes_wrapped_heading(self):
        """Apostol ch2 §2.7 实测形态：页眉复本补全跨行残缺节头，页码留在首现页。"""
        cur = (42, "SEC", "2.7", "2.7 Dirichlet inverses and the Mobius", 1103)
        new = (43, "SEC", "2.7",
               "2.7: Dirichlet inverses and the Mobius inversion formula", 68)
        self.assertEqual(
            sec_row_prefer(cur, new),
            (42, "SEC", "2.7", "Dirichlet inverses and the Mobius inversion formula", 1103))

    def test_identical_title_keeps_first_row(self):
        cur = (41, "SEC", "2.6", "The Dirichlet product of arithmetical functions", 65)
        new = (42, "SEC", "2.6", "The Dirichlet product of arithmetical functions", 65)
        self.assertEqual(sec_row_prefer(cur, new), cur)

    def test_not_a_prefix_is_not_swapped(self):
        """负向：互非前缀 = 另一个标题（或另一节），绝不覆盖在库标题。"""
        cur = (42, "SEC", "2.8", "2.8 The Mangoldt function", 100)
        new = (43, "SEC", "2.8", "2.8 Liouville function lambda", 68)
        self.assertEqual(sec_row_prefer(cur, new), cur)

    def test_shorter_running_head_never_truncates(self):
        """负向：页眉复本被 OCR 截短（更短）时不得反向往上换。"""
        cur = (42, "SEC", "2.7", "Dirichlet inverses and the Mobius inversion formula", 1103)
        new = (43, "SEC", "2.7", "Dirichlet inverses and the Mobius", 68)
        self.assertEqual(sec_row_prefer(cur, new), cur)

    def test_upgrade_requires_later_page(self):
        """负向：新行页码更早（真节头后补的碎行）不配补全在库标题。"""
        cur = (43, "SEC", "2.7", "Dirichlet inverses and the Mobius", 68)
        new = (42, "SEC", "2.7", "Dirichlet inverses and the Mobius inversion formula", 1103)
        self.assertEqual(sec_row_prefer(cur, new), cur)

    def test_upgrade_length_cap(self):
        """负向：超长「前缀加长」多半是正文首行粘连，不当页眉复本。"""
        tail = " " + "x" * 200
        cur = (42, "SEC", "2.7", "2.7 Dirichlet inverses", 1103)
        new = (43, "SEC", "2.7", "2.7 Dirichlet inverses" + tail, 68)
        self.assertEqual(sec_row_prefer(cur, new), cur)


class TestLegacyPreference(unittest.TestCase):
    def test_mathy_fragment_yields_to_words(self):
        """Hilton & Stammbach 旧判据不回归：公式残行让位给纯词标题。"""
        cur = (10, "SEC", "8", "8 F0=8 FG8 FεG'", 100)
        new = (11, "SEC", "8", "8 Cohomology of groups", 68)
        self.assertEqual(sec_row_prefer(cur, new), new)

    def test_empty_title_yields(self):
        cur = (10, "SEC", "8", "", 100)
        new = (11, "SEC", "8", "8 Cohomology of groups", 68)
        self.assertEqual(sec_row_prefer(cur, new), new)

    def test_words_do_not_yield_to_mathy(self):
        cur = (10, "SEC", "8", "8 Cohomology of groups", 100)
        new = (11, "SEC", "8", "8 F0=8 FG8 FεG'", 68)
        self.assertEqual(sec_row_prefer(cur, new), cur)


if __name__ == "__main__":
    unittest.main(verbosity=2)
