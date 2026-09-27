# -*- coding: utf-8 -*-
"""Regression: 章级图片覆盖闸不得要求 **consolidated 习题块** 的插图有落点。

Strogatz《Nonlinear Dynamics and Chaos》3e ch2/ch3 实测：章末集中习题块按
writing-rules V-I「整块省略、不生成单元」，但 `chapter_images` 把块内插图也算进
「契约任一图必须被本章某个单元嵌入」的真值集 → 门控对 ch02_unnamed_01/02/03、
ch03_unnamed_01/02 报 MISSING FAIL。写手被逼迫的两条坏出路都真实发生过：把习题图
硬塞进不相干的例题单元（V-E 归属错误），以及**改 manifest.json 迁就**（篡改脚本
产物，且合并后正文里凭空多出一张无正文支撑的图）。

根治点在真值集本身（`data/book_structure/book_structure.py` 的 `chapter_images`
默认跳过 `consolidated: true` 子树），不在调用方打补丁。本测试锁死两件事：
① consolidated 子树的图**不在**默认真值集里；② 非 consolidated 的图**仍在**
（漏图 = 内容丢失的兜底闸不许被顺手放宽）。
"""
import os
import sys
import unittest

_here = os.path.dirname(os.path.abspath(__file__))
_root = _here
while not os.path.exists(os.path.join(_root, "SKILL.md")):
    _parent = os.path.dirname(_root)
    if _parent == _root:
        raise RuntimeError("SKILL.md not found above %s" % _here)
    _root = _parent
sys.path.insert(0, _root)
import lib.boot  # noqa: E402
lib.boot.setup()

from data.book_structure.book_structure import (chapter_image_counts,
                                                chapter_images)


def _contract():
    """章 = 一节，节下挂一个正文例题（图 A）与一个 consolidated 习题块（图 B/C）。"""
    return {
        "key": "2", "type": "chapter", "name": "2 Flows on the Line",
        "consolidated": False,
        "sub_sec": [
            {
                "key": "2.1", "type": "section", "name": "2.1 Examples",
                "consolidated": False,
                "sub_sec": [
                    {
                        "key": "2.1-1", "type": "example", "name": "2.1.1",
                        "consolidated": False,
                        "sub_sec": [{"image": "figure/ch02_figA.png"}],
                    },
                    {
                        "key": "2.1.10", "type": "exercise", "name": "2.1.10",
                        "consolidated": True,
                        "sub_sec": [
                            {"image": "figure/ch02_unnamed_01.png"},
                            {"text": "See Figure 2.1.10."},
                        ],
                    },
                ],
            },
        ],
    }


class TestChapterImagesSkipConsolidated(unittest.TestCase):
    def test_consolidated_images_excluded_from_default_truth(self):
        got = [os.path.basename(p) for p in chapter_images(_contract())]
        self.assertEqual(got, ["ch02_figA.png"])

    def test_non_consolidated_image_still_required(self):
        """兜底闸不许被放宽：正文图缺嵌仍须出现在真值集里。"""
        self.assertIn("figure/ch02_figA.png", chapter_images(_contract()))

    def test_opt_out_returns_physical_full_set(self):
        got = sorted(os.path.basename(p)
                     for p in chapter_images(_contract(), skip_consolidated=False))
        self.assertEqual(got, ["ch02_figA.png", "ch02_unnamed_01.png"])

    def test_consolidated_section_subtree_skipped_wholesale(self):
        """整节都是习题块（consolidated 挂在 section 上）→ 其下全部图豁免。"""
        c = {
            "key": "3", "type": "chapter", "consolidated": False,
            "sub_sec": [{
                "key": "3.5", "type": "section", "consolidated": True,
                "sub_sec": [
                    {"image": "figure/ch03_unnamed_01.png"},
                    {"key": "3.5-1", "type": "exercise",
                     "sub_sec": [{"image": "figure/ch03_unnamed_02.png"}]},
                ],
            }],
        }
        self.assertEqual(chapter_images(c), [])
        self.assertEqual(len(chapter_images(c, skip_consolidated=False)), 2)


class TestChapterImageCountsDetectsMergedCrop(unittest.TestCase):
    """并图缺陷真值集：`chapter_image_counts`（**不去重**计数）须看见「两块同 file」。

    Shafarevich《Basic Algebraic Geometry 1》ch2 实测：Figure 8 与 Figure 9 两张
    上下相邻的图被框成一个区域，回填时把同一 `bbox`+`file` 复制给两个标号 ⇒
    契约 `推论2.4` 的两个 image 块都指向 `figure/ch02_fig9.png`，而
    `figure/ch02_fig8.png` 根本不存在。章级覆盖闸按**集合**比较，两块同 file
    在集合里只剩一个元素 ⇒ 该缺陷对既有闸门完全隐形，成品 md 里同一张「两图
    叠在一起」的长条出现两次、Figure 8 丢失。语料标定：624 份分章契约命中 0 处，
    故计数闸无跨书面误报。
    """

    def test_same_file_twice_is_counted(self):
        c = {
            "key": "2", "type": "chapter", "consolidated": False,
            "sub_sec": [{
                "key": "2.1", "type": "section", "consolidated": False,
                "sub_sec": [{
                    "key": "推论2.4", "type": "corollary", "consolidated": False,
                    "sub_sec": [
                        {"image": "figure/ch02_fig9.png"},
                        {"image": "figure/ch02_fig9.png"},
                    ],
                }],
            }],
        }
        self.assertEqual(chapter_image_counts(c), {"figure/ch02_fig9.png": 2})
        # 覆盖闸（集合并集）看不见它——这正是需要计数闸的理由
        self.assertEqual(chapter_images(c), ["figure/ch02_fig9.png"])

    def test_distinct_files_not_flagged(self):
        c = {
            "key": "2", "type": "chapter", "consolidated": False,
            "sub_sec": [{
                "key": "2.1", "type": "section", "consolidated": False,
                "sub_sec": [
                    {"key": "A", "type": "item", "consolidated": False,
                     "sub_sec": [{"image": "figure/ch02_fig8.png"}]},
                    {"key": "B", "type": "item", "consolidated": False,
                     "sub_sec": [{"image": "figure/ch02_fig9.png"}]},
                ],
            }],
        }
        self.assertEqual(set(chapter_image_counts(c).values()), {1})

    def test_consolidated_subtree_exempt_as_well(self):
        c = {
            "key": "3", "type": "chapter", "consolidated": False,
            "sub_sec": [{
                "key": "3.5", "type": "exercise", "consolidated": True,
                "sub_sec": [{"image": "figure/ch03_unnamed_01.png"},
                            {"image": "figure/ch03_unnamed_01.png"}],
            }],
        }
        self.assertEqual(chapter_image_counts(c), {})
        self.assertEqual(chapter_image_counts(c, skip_consolidated=False),
                         {"figure/ch03_unnamed_01.png": 2})


if __name__ == "__main__":
    unittest.main(verbosity=2)
