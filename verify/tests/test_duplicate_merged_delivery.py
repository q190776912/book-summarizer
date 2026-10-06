# -*- coding: utf-8 -*-
r"""同章多份**合并交付物**检测（`verify_chapter.duplicate_merged_deliveries`）的判据回归。

成因（Introduction-to-Dynamical-Systems 第9章 实测，2026-10-03）：章 md 改名后旧名不会
被覆盖——`merge_units` 按契约章名写出 `第9章_Measure-Theoretic_Entropy.md`，而盘上另有一
份手工旧名 `第9章_测度论熵.md`，于是同一章同一语种交付两次。`chapter_md_groups` 把同前缀
的合并稿**全部**并进一个组，该章正文/`\tag` 在校验视图里出现两次：Q 层开着的书报
duplicate `\tag` 硬 FAIL（Katok ch1），Q 层没开的书则**静默 PASS 且多算一章**（本书
verify 曾报 19/19，回收旧档后才是真实的 18/18）。⇒ 判据必须独立于 Q 层，接在 `--all`
入口做 fail-closed 硬闸，修复命令指向 `tools/split_chapters.py --reconcile`。

跨语料普查（50 书目录 / 全部章-语种桶）：命中 1 组 = 本书第9章本身，零假阳；节文件、
附录/补篇、中英各自一份均不归为重复。
"""
import os
import shutil
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

from verify_chapter import duplicate_merged_deliveries          # noqa: E402

BODY = '# 章\n\n$$\nx = y\n\\tag{9.2}\n$$\n'


class DuplicateMergedDeliveryTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='bks_dupdeliver_')

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _touch(self, *names):
        for n in names:
            with open(os.path.join(self.dir, n), 'w', encoding='utf-8') as f:
                f.write(BODY)

    def test_two_merged_files_same_chapter_same_lang_is_flagged(self):
        self._touch('第9章_Measure-Theoretic_Entropy.md', '第9章_测度论熵.md')
        dups = duplicate_merged_deliveries(self.dir)
        self.assertEqual([(l, h, len(n)) for l, h, n in dups], [('cn', '第9章', 2)])

    def test_section_files_are_not_merged_deliveries(self):
        # 拆章形态：一组节文件不构成重复（另有 reconcile 的同节号判据）
        self._touch('Chapter1_1.1_A.md', 'Chapter1_1.2_B.md', 'Chapter1_1.10_C.md',
                    '第1章_1.1_甲.md', '第1章_1.2_乙.md')
        self.assertEqual(duplicate_merged_deliveries(self.dir), [])

    def test_one_merged_per_language_is_clean(self):
        self._touch('Chapter9_Title.md', '第9章_标题.md',
                    'AppendixA_Back.md', '附录A_背景.md',
                    'SupplementS_Things.md', '补篇S_事项.md')
        self.assertEqual(duplicate_merged_deliveries(self.dir), [])

    def test_bare_and_titled_forms_of_same_bucket_are_flagged(self):
        # 无编号附录只应有一种形态：裸名 + 带标题名 = 同一附录交付两次
        self._touch('附录.md', '附录_代数附录.md')
        dups = duplicate_merged_deliveries(self.dir)
        self.assertEqual([h for _l, h, _n in dups], ['附录'])

    def test_unrelated_md_is_not_bucketed(self):
        self._touch('README.md', '第9章.pdf')
        self.assertEqual(duplicate_merged_deliveries(self.dir), [])


if __name__ == '__main__':
    unittest.main()
