# -*- coding: utf-8 -*-
"""chapter_local_numbering 模式的「序位豁免」回归（Shafarevich 代数几何 1 ch1 实测）。

印面节头 `5.2 The Image of a Projective Variety is Closed`（p74）含**小写系词**
`is`，被 `_section_header_info` 的「小写连词动词闸」否决。其他模式有「序位豁免」
（`successor_num` = 上一个节号 +1 时放行，见 `test_section_successor_waiver.py`），
但 `scan()` 旧代码在 `chapter_local_numbering=True` 时把 `_succn` **硬设成 None**
（注释原话「该模式自带闩锁，不参与序位豁免」）⇒ 该模式下整条豁免通道不存在，
这一节从骨架与内容契约**双双消失**，而 D 层与抽取器同源，报 `missing sections=0`
（假绿），647 个单元的门控全程绿灯。

根治 = 用**闩锁自己的状态**给出序位：`successor = 当前节 cur_global_sec . (上一个
子节号 cur_local_sub + 1)`，与其他模式同强度（只放行恰好接续的号，其余守卫照旧）。

跨书标定（corpus 中声明该模式的 2 本书全量重扫 vs 现契约）：找回 1 处（本节），
回归 0 处；丘维声《解析几何》找回 0 / 回归 0。

跑法：
  python flows/write-source/structure/script/tests/test_cln_successor_waiver_copula.py
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
    _ROOT = str(Path(__file__).resolve().parents[2])
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

import scan_skeleton as S  # noqa: E402

CH_MAP = {"chapters": [{"ch": 1, "name": "Basic Notions", "start": 1, "end": 6}]}


def _mk_pages(d, pages):
    """每行一个块（与真书 OCR 形态一致），块体带 poly（y=300，宽 600）。"""
    for i, blocks in enumerate(pages, start=1):
        with open(os.path.join(d, "page_%03d.json" % i), "w", encoding="utf-8") as f:
            json.dump({"text": [{"text": b,
                                 "poly": [60, 300, 660, 300, 660, 330, 60, 330]}
                                for b in blocks],
                       "formulas": []}, f)
    with open(os.path.join(d, "chapter_map.json"), "w", encoding="utf-8") as f:
        json.dump(CH_MAP, f)


def _secs(rows):
    return {str(r[2]): (r[3] or '') for r in rows if r[1] == 'SEC'}


def _scan(d, n=6):
    return S.scan(d, 1, 1, n, 'three-level',
                  section_depths=[1, 1, 2], chapter_first=True,
                  chapter_local_numbering=True, language='en')


BASE = [
    ["1 Plane Curves"],
    ["2 Quasiprojective Varieties"],
    ["3 Projective Varieties"],
    ["4 Rational Maps"],
    ["5 Products and Maps of Quasiprojective Varieties",
     "5.1 Products",
     "some prose body line that is long enough to be clearly prose here"],
]


class TestClnSuccessorWaiver(unittest.TestCase):
    def test_copula_section_title_recovered(self):
        """正例（实测漏节）：5.1 之后**恰好接续**的 5.2 含小写 `is` 仍须成节。"""
        with tempfile.TemporaryDirectory() as d:
            pages = BASE + [["5.2 The Image of a Projective Variety is Closed"],
                            ["5.3 Finite Maps"]]
            _mk_pages(d, pages)
            secs = _secs(_scan(d, len(pages)))
            self.assertIn('5.2', secs)
            self.assertEqual(secs['5.2'],
                             'The Image of a Projective Variety is Closed')
            for k in ('5', '5.1', '5.3'):
                self.assertIn(k, secs)

    def test_out_of_sequence_copula_line_still_rejected(self):
        """负例：号不接续（5.1 之后出现 5.4）时小写系词闸照旧拦截。"""
        with tempfile.TemporaryDirectory() as d:
            pages = BASE + [["5.4 The Image of a Projective Variety is Closed"],
                            ["5.3 Finite Maps"]]
            _mk_pages(d, pages)
            secs = _secs(_scan(d, len(pages)))
            self.assertNotIn('5.4', secs)
            self.assertIn('5.3', secs)

    def test_prose_at_expected_slot_still_rejected_by_other_guards(self):
        """负例：即便**恰为接续号**，句首虚词起头（`It is …`）的散文行仍须被
        其余守卫拦下——豁免只放开「小写连词动词」这一道，不放开整条判定。"""
        with tempfile.TemporaryDirectory() as d:
            pages = BASE + [["5.2 It is clear that the image is closed"],
                            ["5.3 Finite Maps"]]
            _mk_pages(d, pages)
            secs = _secs(_scan(d, len(pages)))
            self.assertNotIn('5.2', secs)
            self.assertIn('5.3', secs)

    def test_successor_string_shape(self):
        """钉住新路径喂给 `_section_header_info` 的 successor 串形态（闩锁状态）。"""
        ok = S._section_header_info(
            "5.2 The Image of a Projective Variety is Closed",
            ch=None, depths={1, 2}, successor_num="5.2")
        self.assertIsNotNone(ok)
        self.assertEqual(ok[0], "5.2")
        self.assertIsNone(S._section_header_info(
            "5.2 The Image of a Projective Variety is Closed",
            ch=None, depths={1, 2}, successor_num=None))


if __name__ == "__main__":
    unittest.main(verbosity=2)
