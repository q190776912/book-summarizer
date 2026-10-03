# -*- coding: utf-8 -*-
r"""Q 层「标签自身证据」四支判据的回归（动力系统 5 书实测 2026-10-02）。

这一批假阳的**共同根因**只有一个：MISPLACED / ORDER 两套判定把「抽取器碰巧记到的
位置」当成书的事实，而书在标签里**已经自证**了归属，抽取器却因为形态盲区看不见它。
四支修法各对应一处实测：

1. `_heading_num` 认得「希腊字母节题被 OCR 读成拉丁字母」的**单 token 尾巴**
   （IDDS ch5：印面 `§5.3 ε-orbits` → OCR `5.3 e-Orbits` / `5.3. e-Orbits`）。
   旧判据「尾巴首字母小写 = 散句」把该节标题**全书永不识别**，`_cur_heading`
   永远停在 §5.2 → 印在 p126 的 (5.2)…(5.6) 五枚忠实 `\tag` 整批误判。
2. 位置 / 定义节证据按**强弱分级**（IDDS ch2：行内数学 `B(w, 2-1)` 经分隔符归一
   得到裸 `2.1`，抢先把定义点锚在 §2.3 的散文页，把 p49 的真标签 `(2.1)` 顶掉）。
   强信号 = 带括号或 `Eq./Equation/式` 前缀（= 印刷标签本身），弱信号只是同形噪声。
3. 带字母后缀的标签要**逐字**有书源记录才判位（nonlin ch3：单分量书的 pattern 核
   是 `\d+`，印面 `(8a)`/`(8b)` 两个独立标签块**根本匹配不到**；`\tag{8a}` 折成键
   `8` 后比较的是别处那枚真 `(8)` 的位置）。
4. 层级自述编号（`C.S.i` 挂在 `## §C.S` 之下）**不参与 MISPLACED**（Katok ch1：
   `(1.2.2)` 印在 p41，而 §1.2 的起始页判成 p42——页跨整页粒度 + 节头漏识的滞后
   必然越界）。真正的「挂错节」（chaos ch7 把 `7.4.*` 写在 `## §7.3`、ch8 把
   `8.8.*` 写在 `## §8.7`）前缀不等 → 照判，一条不流失。

负向守卫全部在本文件里：每一支放宽都配一条「真缺陷仍报」的用例，且集合成员
（FABRICATED / MISSING）与 ORDER 两支不受 3、4 影响。
"""
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[2])
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot  # noqa: E402
_boot.setup()

from verify.formula_tag.script.formula_tag import (  # noqa: E402
    SourceFormulaIndex, _compute_order_and_section, _heading_num)


def _tag(n, raw=None, latex="$$\nx\n$$\n"):
    return SimpleNamespace(normalized=n, raw_tag=raw if raw is not None else n,
                           latex=latex)


class _Src:
    """最小 `SourceFormulaIndex` 替身：只暴露判据实际读取的账本。"""

    def __init__(self, union, sec_start=None, n_pages=None, pos_sec=None,
                 book_section=None, full_keys=None):
        self._union = set(union)
        self._sec_start_page = dict(sec_start or {})
        self._n_pages = {k: set(v) for k, v in (n_pages or {}).items()}
        self._pos_sec = dict(pos_sec or {})
        self._book_section = dict(book_section or {})
        self._book_section_sec = {}
        self._full_keys = set(full_keys or ())
        self._walk_last_page = max(list(self._sec_start_page.values()) or [0])

    def source_numbers(self):
        return set(self._union)

    def primary_pos(self, n):
        return None

    def book_section(self, n):
        return self._book_section.get(n)


# -- ① 节题识别 ---------------------------------------------------------------
class TestGreekRunInTitleIsAHeading(unittest.TestCase):
    def test_single_token_hytitle_counts_as_heading(self):
        """IDDS ch5 的两种 OCR 形态（p124 无点 / p125、p127 带点）。"""
        self.assertEqual(_heading_num("5.3 e-Orbits"), "5.3")
        self.assertEqual(_heading_num("5.3. e-Orbits"), "5.3")

    def test_letter_suffix_junk_still_rejected(self):
        """负向：`5-6.A` 这类图号/表号残迹仍须被字母后缀守卫拦下。"""
        self.assertIsNone(_heading_num("5-6.A"))
        self.assertIsNone(_heading_num("3-4.B"))

    def test_lowercase_runin_prose_still_rejected(self):
        """多词小写起头 = 散文续行，不得冒充标题（旧判据强度不降）。"""
        self.assertIsNone(_heading_num("5.3 and it is stated that the map expands"))
        self.assertIsNone(_heading_num("2.6 if we set x = 1 then the orbit is dense"))
        # 散文里以大写缩写起头的一句同样不是标题（守卫面不扩到多词）。
        self.assertIsNone(_heading_num("5.3 e Orbits are open"))


# -- ② 强弱分级 ---------------------------------------------------------------
class TestStrongLabelOverridesWeakHit(unittest.TestCase):
    def _idx(self):
        return SourceFormulaIndex("unused", [], False, set(), ncomp=2)

    def test_weak_hit_does_not_hijack_when_strong_arrives(self):
        idx = self._idx()
        idx._cur_heading = "2.3"
        idx._update_pos("2.1", 48, 300.0, strong=False)
        idx._cur_heading = "2.4"
        idx._update_pos("2.1", 49, 200.0, strong=True)
        self.assertEqual(idx.primary_pos("2.1"), (49, 200.0),
                         "行内噪声不得顶掉印刷标签的定义点")
        self.assertEqual(idx.book_section("2.1"), "2.4")

    def test_weak_hit_cannot_overwrite_existing_strong(self):
        idx = self._idx()
        idx._cur_heading = "2.4"
        idx._update_pos("2.1", 49, 200.0, strong=True)
        idx._cur_heading = "2.3"
        idx._update_pos("2.1", 48, 100.0, strong=False)
        self.assertEqual(idx.primary_pos("2.1"), (49, 200.0))
        self.assertEqual(idx.book_section("2.1"), "2.4")

    def test_all_weak_keeps_earliest_behaviour(self):
        """全书只有弱证据 → 与旧写法逐字节一致（最早者胜）。"""
        idx = self._idx()
        idx._cur_heading = "2.3"
        idx._update_pos("2.1", 48, 100.0, strong=False)
        idx._cur_heading = "2.4"
        idx._update_pos("2.1", 52, 900.0, strong=False)
        self.assertEqual(idx.primary_pos("2.1"), (48, 100.0))
        self.assertEqual(idx.book_section("2.1"), "2.3")


# -- ③ 字母后缀标签的逐字印刷证据 ----------------------------------------------
class TestSuffixedTagNeedsVerbatimSourceRecord(unittest.TestCase):
    def _src(self, full_keys):
        return _Src(['8'], sec_start={'3.6': 100, '3.7': 110},
                    n_pages={'8': [105]}, full_keys=full_keys)

    def test_suffix_never_printed_is_skipped(self):
        r"""书源只可能以 `\d+` 核抽到裸 `(8)`：`(8a)` 从未被看见 → 无证据不判。"""
        src = self._src(())
        mp = _compute_order_and_section([('3.7', _tag('8', '8a'))], src,
                                        reset_on_section=True)[1]
        self.assertEqual(mp, [], "抽取器看不见该后缀形态时必须跳过")

    def test_suffix_verbatim_printed_still_flagged(self):
        """负向：多分量书真印过 `(8.11a)`，挂错节照判。"""
        src = _Src(['8.11'], sec_start={'7.10': 200, '7.11': 210},
                   n_pages={'8.11': [205]}, full_keys={'8.11a'})
        mp = _compute_order_and_section([('7.11', _tag('8.11', '8.11a'))], src,
                                        reset_on_section=True)[1]
        self.assertEqual([r['number'] for r in mp], ['8.11'])

    def test_unsuffixed_tag_unaffected(self):
        src = self._src(())
        mp = _compute_order_and_section([('3.7', _tag('8'))], src,
                                        reset_on_section=True)[1]
        self.assertEqual([r['number'] for r in mp], ['8'],
                         "无后缀的标签不得被本豁免吃掉")


# -- ④ 层级自述编号 -----------------------------------------------------------
class TestHierarchicalSelfReport(unittest.TestCase):
    def test_label_naming_its_own_section_is_exempt_sectioned(self):
        """Katok ch1：标签 `1.2.2` 写在 `## §1.2` 下，页跨滞后不得判错位。"""
        src = _Src(['1.2.2'], sec_start={'1.1': 36, '1.2': 42, '1.3': 48},
                   n_pages={'1.2.2': [41]})
        mp = _compute_order_and_section([('1.2', _tag('1.2.2'))], src,
                                        reset_on_section=True)[1]
        self.assertEqual(mp, [])

    def test_label_naming_its_own_section_is_exempt_plain(self):
        """plain 支同判：`_cur_heading` 游标滞后（书侧记成 1.1）不构成反证。"""
        src = _Src(['1.5.1'], book_section={'1.5.1': '1.4'})
        mp = _compute_order_and_section([('1.5', _tag('1.5.1'))], src,
                                        reset_on_section=False)[1]
        self.assertEqual(mp, [])

    def test_summary_hanging_label_under_other_section_still_flagged(self):
        """负向（chaos ch7 / ch8 的真实缺陷形态）：`7.4.*` 挂在 `## §7.3` 下，
        书源记录又全在 §7.3 的页跨之外 → 前缀不等 + 页跨越界，必须报。"""
        src = _Src(['7.4.1'], sec_start={'7.3': 210, '7.4': 216},
                   n_pages={'7.4.1': [220]})
        mp = _compute_order_and_section([('7.3', _tag('7.4.1'))], src,
                                        reset_on_section=True)[1]
        self.assertEqual([r['number'] for r in mp], ['7.4.1'],
                         "标签自述的节 ≠ 总结所在节 → 必须仍报 MISPLACED")

    def test_bucket_agreement_in_foreign_section_still_flags(self):
        """趟把该号归在**别**桶（§7.4）而总结写在 §7.3 → 归桶证据反成错位铁证。"""
        src = _Src(['7.4.1'], sec_start={'7.3': 210, '7.4': 216},
                   n_pages={'7.4.1': [220]}, pos_sec={('7.4', '7.4.1'): (220, 90.0)})
        mp = _compute_order_and_section([('7.3', _tag('7.4.1'))], src,
                                        reset_on_section=True)[1]
        self.assertEqual([r['number'] for r in mp], ['7.4.1'])

    def test_plain_branch_foreign_section_still_flagged(self):
        src = _Src(['8.8.1'], book_section={'8.8.1': '8.8'})
        mp = _compute_order_and_section([('8.7', _tag('8.8.1'))], src,
                                        reset_on_section=False)[1]
        self.assertEqual([r['number'] for r in mp], ['8.8.1'])

    def test_self_report_does_not_exempt_order(self):
        """本豁免只动 MISPLACED：顺序倒挂仍须报。"""

        class _OrderSrc(_Src):
            def __init__(self, pos):
                super().__init__(['1.2.1', '1.2.2'])
                self._pos = pos

            def primary_pos(self, n):
                return self._pos.get(n)

        src = _OrderSrc({'1.2.1': (50, 900.0), '1.2.2': (50, 100.0)})
        om = _compute_order_and_section(
            [('1.2', _tag('1.2.1')), ('1.2', _tag('1.2.2'))], src,
            reset_on_section=False)[0]
        self.assertEqual([r['number'] for r in om], ['1.2.2'])


if __name__ == "__main__":
    unittest.main(verbosity=2)
