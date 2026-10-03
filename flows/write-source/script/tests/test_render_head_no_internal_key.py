"""草稿条头不得携带契约内部键：`strip_internal_key_head` 判据（跨书普查 6 书 1305 单元，2026-10-02）。

`extract_items` 把条目节点 name 存成 ``"<key> <印刷文本>"``，而三级序标 key 是印面
`N.M.K` 的内部归一形 `N.M-K`；`render_draft._render_item` 无条件 `**name**：`，于是
`**5.2-1 5.2.1 A homology spectral sequence**：` 这类**原书从未印过**的连字符序标随
草稿落进交付物。实测命中：Weibel 121 / Gelfand–Manin 846 / Kreyszig 284 / 数学分析 33 /
概率论与数理统计教程 20 / 微分遍历论 8（后者的 `**2.2-3**：` 等已随本轮数据手术清毕）。

判据：仅当「剥掉开头内部键后剩下的文本里确实出现该序标的**印刷点分形**」才剥，
所以原书真用连字符编号的形态（习题 `3-15`，文本里没有 `3.15`）保持原样——
只去重，不丢印刷序标。

Runs under stdlib unittest:
  python flows/write-source/script/tests/test_render_head_no_internal_key.py
"""
import sys
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

import render_draft as rd  # noqa: E402

strip = rd.strip_internal_key_head


class LeakedKeyStripped(unittest.TestCase):
    def test_weibel_shape(self):
        self.assertEqual(
            strip('5.2-1 5.2.1 A homology spectral sequence (starting with)', '5.2-1'),
            '5.2.1 A homology spectral sequence (starting with)')

    def test_cn_lemma_shape(self):
        self.assertEqual(strip('2.2-3 2.2.3令α ∈U(M)，则', '2.2-3'), '2.2.3令α ∈U(M)，则')

    def test_example_shape(self):
        self.assertEqual(strip('2.3-1 2.3.1考虑概率空间', '2.3-1'), '2.3.1考虑概率空间')

    def test_render_item_head_has_no_internal_key(self):
        node = {'key': '5.4-2', 'type': 'definition',
                'name': '5.4-2 5.4.2 Definition (Bounded filtrations)',
                'sub_sec': [{'text': 'A filtration is bounded if ...',
                             'line_start': True, 'indent': 2.0}]}
        out = []
        rd._render_item(node, out, 'en')
        joined = '\n'.join(out)
        self.assertNotIn('5.4-2', joined, joined)
        self.assertIn('5.4.2', joined, joined)


class PrintedHyphenPreserved(unittest.TestCase):
    def test_hyphen_printed_ordinal_untouched(self):
        # 原书真印连字符形（无点分双胞胎）→ 不剥
        self.assertEqual(strip('3-15 Prove that the limit exists', '3-15'),
                         '3-15 Prove that the limit exists')

    def test_non_dash_key_untouched(self):
        self.assertEqual(strip('定理3 存在唯一解', '3'), '定理3 存在唯一解')

    def test_key_not_at_name_start_untouched(self):
        self.assertEqual(strip('注 4.5.5 的记号', '4.5-5'), '注 4.5.5 的记号')

    def test_name_equal_to_key_alone_untouched(self):
        self.assertEqual(strip('2.2-3', '2.2-3'), '2.2-3')


if __name__ == "__main__":
    unittest.main(verbosity=2)
