r"""Q 层「块首裸号 + 句点 = 条目/习题头」结构性锚点门禁（Katok 实测 2026-10-03）。

三条 ORDER_MISMATCH 假阳同源：Katok 的章末习题与条目头（`2.4.7. If f is close to
Ek…` / `2.9.3. For w E S2 let Φ(w) = …` / `15.2.2. Given e > 0 …`）在 OCR 文字层里
就是**以编号开头、编号后紧跟句点**的块。旧的习题头判据靠**枚举祈使动词**
（Give|Prove|Show|…）认出这种形态，两个漏洞：
  ① 词表短一个词（`If`、`For` 根本不在表内）；
  ② 表尾 `\b` 落在词干后 → 变形 `Given` 失配（`Give` 后紧跟 `n` 不是词边界）。
于是习题头既混进书源集合 S，又以更早的 (page, y) **抢到定义位置**，把同一节里
后面那枚真右缘标签判成倒序（实测 `2.4.7` @(95,632) 顶掉 @(95,1612)、
`2.9.3` @(125,908) 把 `2.9.4` 顶成倒挂、`15.2.2` @(521,298) 把 `15.2.3` 顶成倒挂）。

根治 = 用**排版形状**取代枚举：裸号 + 编号是块的首个记号 + 编号后紧跟句点。
印面上的公式标签要么带括号要么在行尾，不会同时「顶在块首」又「后跟句点」。

🔴 反向约束（防将真标签一并门禁掉）：
  · 括号形态（strong signal）一律放过——`(2.4.7).` 仍是标签；
  · 裸号风格的书（印面就是 `2.4.7` 顶在行尾/独立成块、**无尾点**）一律放过；
  · 编号在块**中部**的散文回指不进本门禁，由 `_embedded_ref` 与动词表（已修
    词尾变形）负责。
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

from formula_tag import SourceFormulaIndex, build_formula_patterns  # noqa: E402

PATTERNS3 = build_formula_patterns(3, allow_bare=True)

# 印面实样（Katok p95 / p125 / p521，page_*.json 文字层逐字）
HEAD_95 = ('2.4.7. If f is close to Ek, pick p close to 0. Since F(p) = p, '
           'F(p+1) = p+k, and')
HEAD_125 = '2.9.3. For w E S2 let Φ(w) = ∑nez wn2-Inl and a(w) = Φ(g2w) -Φ(w). Show'
HEAD_521 = ('15.2.2. Given e > 0 and 0 ≤ h ≤ ∞o construct a map of [0, 1] '
            'that is C°-close')


def _blk(t, y):
    return {"text": t, "poly": [60, y, 700, y + 14]}


def _write_pages(ext, pages):
    os.makedirs(ext, exist_ok=True)
    for pg, blocks in pages.items():
        with open(os.path.join(ext, "page_%03d.json" % pg), "w",
                  encoding="utf-8") as f:
            json.dump({"text": blocks}, f, ensure_ascii=False)


class TestPredicate(unittest.TestCase):
    def _hit(self, txt, num, strong=False):
        i = txt.index(num)
        return SourceFormulaIndex._bare_item_head(txt, i, i + len(num), strong)

    def test_katok_heads_caught(self):
        self.assertTrue(self._hit(HEAD_95, '2.4.7'))
        self.assertTrue(self._hit(HEAD_125, '2.9.3'))
        self.assertTrue(self._hit(HEAD_521, '15.2.2'))

    def test_standalone_dot_terminated_head_caught(self):
        self.assertTrue(self._hit('2.4.7.', '2.4.7'))

    def test_parenthesized_label_not_caught(self):
        # 括号形态 = 强信号，尾点也不降级（印面右缘标签的常见 OCR 形态）
        self.assertFalse(self._hit('(2.4.7).', '2.4.7', strong=True))
        self.assertFalse(self._hit('(15.2.1)', '15.2.1', strong=True))

    def test_bare_tag_without_dot_not_caught(self):
        # 裸号风格的书：编号顶在块首但**不跟句点** → 仍作标签证据
        self.assertFalse(self._hit('2.4.7', '2.4.7'))
        self.assertFalse(self._hit('2.4.7  F(p) = p', '2.4.7'))

    def test_mid_block_hit_not_caught(self):
        self.assertFalse(self._hit('by 2.4.7. If', '2.4.7'))


class TestPlainPath(unittest.TestCase):
    def _idx(self):
        return SourceFormulaIndex(
            '.', PATTERNS3, False, ncomp=3, keep_cross_refs=True)

    def test_head_never_tags_nor_anchors(self):
        idx = self._idx()
        nums = set()
        idx._scan_text(HEAD_95, nums, pg=95, y=632.0)
        self.assertNotIn('2.4.7', nums)
        self.assertIsNone(idx.primary_pos('2.4.7'))
        # 真标签随后到达 → 正常锚定
        idx._scan_text('(2.4.7)', nums, pg=95, y=1612.0)
        self.assertIn('2.4.7', nums)
        self.assertEqual(idx.primary_pos('2.4.7'), (95, 1612.0))

    def test_inflected_verb_head_still_rejected_mid_block(self):
        # 动词表的词尾变形修复（Given 曾因 `\b` 失配漏网）
        idx = self._idx()
        nums = set()
        idx._scan_text('see 15.2.2. Given e > 0 construct a map of [0, 1]',
                       nums, pg=521, y=298.0)
        self.assertIsNone(idx.primary_pos('15.2.2'))


class TestSectionedPath(unittest.TestCase):
    def test_real_label_outranks_item_head(self):
        with tempfile.TemporaryDirectory() as d:
            ext = os.path.join(d, "_extract")
            _write_pages(ext, {
                94: [_blk('Lemma 2.4.6. The degree is continuous', 240.0)],
                95: [_blk('Proof of Theorem 2.4.6.We will give the proof', 154.0),
                     _blk('h = lim (1/n) log card', 1000.0),
                     _blk('(2.4.6)', 1136.0),
                     _blk(HEAD_95, 632.0),
                     _blk('(2.4.7)', 1612.0)],
                96: [_blk('f(x) = x + 1', 300.0)],
            })
            idx = SourceFormulaIndex(ext, PATTERNS3, False, ncomp=3,
                                     keep_cross_refs=True)
            idx.build_sectioned(2, 94, 96, ['2.4'], ncomp=3)
            # 习题头不再抢到定义位置：2.4.7 锚在真标签 (95,1612)，顺序不倒挂
            self.assertEqual(idx._pos_sec.get(('2.4', '2.4.7')), (95, 1612.0))
            self.assertLess(idx._pos_sec[('2.4', '2.4.6')],
                            idx._pos_sec[('2.4', '2.4.7')])

    def test_exercise_page_head_does_not_enter_section_set(self):
        with tempfile.TemporaryDirectory() as d:
            ext = os.path.join(d, "_extract")
            _write_pages(ext, {
                124: [_blk('a(x) = Φ(gx) - Φ(x)', 400.0), _blk('(2.9.3)', 900.0)],
                125: [_blk(HEAD_125, 908.0),
                      _blk('2.9.4. Show that Φ is not a coboundary', 980.0)],
            })
            idx = SourceFormulaIndex(ext, PATTERNS3, False, ncomp=3,
                                     keep_cross_refs=True)
            idx.build_sectioned(2, 124, 125, ['2.9'], ncomp=3)
            S = idx.source_numbers()
            self.assertIn('2.9.3', S)              # 真标签仍收录
            self.assertNotIn('2.9.4', S)           # 纯习题号不进 S（不造 MISSING）
            self.assertEqual(idx._pos_sec.get(('2.9', '2.9.3')), (124, 900.0))


if __name__ == '__main__':
    unittest.main()
