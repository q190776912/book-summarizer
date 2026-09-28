"""条头「行首粘连标点」漏识的判据测试（2026-09-28 Arnold《经典力学的数学方法》实测）。

缺陷现场：中文扫描版 OCR 把上一句的句末标点粘在下一条条目头之前——
page_078 印面「例 9」实排为行 '．例9考虑k个铰接杆所成的封闭链条这个力学系'，
行首锚定的 `lab_re` 因首字符是 '．' 而整条不命中 ⇒ 契约无 例9 节点 ⇒
B 层只报一个「4:18 缺号 9」，根因（抽取器看不见行首噪声）被完全掩盖。

判据（`lib/regexlib.strip_head_noise`）：
  ① 一切「行首条目头」检测在匹配前一律先剥行首噪声，噪声字符集**只含标点/
     引用符号**（不含数字、汉字、字母），所以只会放行「前面粘了标点」的真条头，
     绝不会把句中片段（'由定理3 可见'）变成行首命中；
  ② 剥噪声只用于**检测**；条目正文快照一律取原始行，真标点不得被改写；
  ③ 抽取侧与查漏/回填侧共用同一谓词——`check_structure_completeness.scan_raw_items`
     对 CN 单级书直接委托 `extract_items_cn_single`，故本修复对两侧同时生效；
  ④ 加噪行与干净行必须给出**完全相同**的结果（等价性），杜绝「只在检测侧
     豁免、修复侧不认识」的双份逻辑漂移。

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_head_noise_item_label.py
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

from lib.regexlib import strip_head_noise
from extract_items_cn_single import extract_items_cn_single
from verify_config import GroupConfig


def _groups():
    return [GroupConfig(type=1, name=["例"], scope=3),
            GroupConfig(type=1, name=["定理"], scope=3)]


GROUPS = _groups()


def _mk_pages(d, pages):
    """pages = [[line, ...], ...] -> page_001.json ...（每页一个 text 块列表）"""
    for i, lines in enumerate(pages, start=1):
        with open(os.path.join(d, f"page_{i:03d}.json"), "w", encoding="utf-8") as f:
            json.dump({"text": [{"text": t} for t in lines], "formulas": []}, f)


def _keys(d, n):
    return [it["key"] for it in extract_items_cn_single(d, 1, n, groups=GROUPS)]


class TestStripHeadNoise(unittest.TestCase):
    def test_punctuation_prefix_removed(self):
        self.assertEqual(strip_head_noise('．例9考虑k个铰接杆'), '例9考虑k个铰接杆')
        self.assertEqual(strip_head_noise('。，、· 定理3 存在唯一解'),
                         '定理3 存在唯一解')
        self.assertEqual(strip_head_noise('> **例1**'), '例1**')

    def test_content_characters_never_stripped(self):
        # 数字 / 汉字 / 字母开头一律原样返回（噪声集不含这些字符）。
        self.assertEqual(strip_head_noise('3 个铰接杆'), '3 个铰接杆')
        self.assertEqual(strip_head_noise('例9 考虑'), '例9 考虑')
        self.assertEqual(strip_head_noise('SO(3) 是流形'), 'SO(3) 是流形')
        self.assertEqual(strip_head_noise(''), '')
        self.assertEqual(strip_head_noise(None), '')


class TestGluedHeadRecovered(unittest.TestCase):
    def test_glued_example_head_is_extracted(self):
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, [
                ['例8设刚性直角三角形OAB绕顶点O运动.'],
                ['．例9考虑k个铰接杆所成的封闭链条这个力学系'],
                ['例10嵌入流形.我们说M是欧氏空间的一个k维嵌入子流形'],
            ])
            self.assertEqual(_keys(d, 3), ['例8', '例9', '例10'])

    def test_body_snippet_keeps_original_punctuation(self):
        # 判据②：剥噪声只服务检测，正文快照必须逐字保留原始行。
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, [['．例9考虑k个铰接杆所成的封闭链条这个力学系']])
            it = extract_items_cn_single(d, 1, 1, groups=GROUPS)[0]
            self.assertTrue(it["text"].startswith('．例9'), it["text"])

    def test_no_new_false_positive_from_prefix(self):
        # 剥掉标点后仍以引用词（由/见/利用）或正文起头的行，不是条头。
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, [
                ['．由定理3 可见链形是可积的'],
                ['。见例5 的构形空间讨论'],
                ['，例2和例3 给出对称形式'],
            ])
            self.assertEqual(_keys(d, 1), [])

    def test_parity_with_clean_line(self):
        # 判据④：同一行的加噪形态与干净形态结果必须逐字等价。
        for variant in ('定理3 群作用给出守恒量', '．定理3 群作用给出守恒量',
                        '·定理3 群作用给出守恒量', '> 定理3 群作用给出守恒量'):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as d:
                _mk_pages(d, [[variant]])
                self.assertEqual(_keys(d, 1), ['定理3'])


class TestRawScanSharesPredicate(unittest.TestCase):
    def test_scan_raw_items_sees_glued_head(self):
        # 判据③：查漏/回填侧（scan_raw_items → extract_items_cn_single）同视图。
        from check_structure_completeness import scan_raw_items
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, [['．例9考虑k个铰接杆所成的封闭链条这个力学系']])
            out = scan_raw_items(d, 4, 1, 1, primary_type=1,
                                 chapter_first=True, language="cn",
                                 groups=GROUPS)
            self.assertEqual([o["key"] for o in out], ['例9'])
            self.assertEqual(out[0]["canon"], (9,))


if __name__ == "__main__":
    unittest.main(verbosity=2)
