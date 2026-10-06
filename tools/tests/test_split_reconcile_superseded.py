"""test_split_reconcile_superseded.py — `split_chapters` 同节号残档回收判据。

成因（Katok 实测）：节文件名带标题截断，标题一改（节名统一轮）新名字会被写出，
而旧名字的文件**从来没人动** → 同一节留下两份交付物；章级重拼视图把两份都读进去，
正文与 `\\tag` 双份 → Q 层「duplicate \\tag number」硬 FAIL（ch1 1.5 实测 6 条同号）。
判据：`reconcile_section_files` 以 mtime 最新者为交付，其余**逐字相同**者移入
`<book>/_extract/_superseded_split_md/<日期>/`（只移动不删除，可回滚）；
内容分叉者一律留在原地并报告（哪份是正文须人工裁决）。

Run with stdlib unittest:
    python tools/tests/test_split_reconcile_superseded.py
"""
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[2])
for _p in (_ROOT, os.path.join(_ROOT, "lib"), os.path.join(_ROOT, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

import split_chapters as SC  # noqa: E402

BODY = '# Chapter 1\n\n## 1.1 Maps\n\n$$\nx = y\n\\tag{1.1.1}\n$$\n'


def _write(dirpath, name, text, mtime):
    fp = os.path.join(dirpath, name)
    with open(fp, 'w', encoding='utf-8') as f:
        f.write(text)
    os.utime(fp, (mtime, mtime))


class ReconcileSupersededTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='bks_reconcile_')
        self.now = time.time()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _root_md(self):
        return sorted(f for f in os.listdir(self.dir) if f.endswith('.md'))

    def test_identical_stale_name_is_archived_not_deleted(self):
        _write(self.dir, 'Chapter1_1.1_Newtitle.md', BODY, self.now)
        _write(self.dir, 'Chapter1_1.1_Oldtitl.md', BODY, self.now - 100)
        moved, diverged = SC.reconcile_section_files(self.dir)
        self.assertEqual((moved, diverged), (1, 0))
        # 交付目录只剩最新名字
        self.assertEqual(self._root_md(), ['Chapter1_1.1_Newtitle.md'])
        # 旧档仍在磁盘上（移动到 _extract 归档，未被销毁）
        arch = os.path.join(self.dir, '_extract', '_superseded_split_md')
        found = [os.path.join(r, f) for r, _d, fs in os.walk(arch) for f in fs]
        self.assertEqual(len(found), 1, found)
        with open(found[0], encoding='utf-8') as f:
            self.assertEqual(f.read(), BODY)

    def test_divergent_content_is_kept_for_human_adjudication(self):
        _write(self.dir, 'Chapter1_1.1_Newtitle.md', BODY, self.now)
        _write(self.dir, 'Chapter1_1.1_Oldtitl.md', BODY + 'extra\n', self.now - 100)
        moved, diverged = SC.reconcile_section_files(self.dir)
        self.assertEqual((moved, diverged), (0, 1))
        self.assertEqual(len(self._root_md()), 2)

    def test_other_sections_and_merged_files_untouched(self):
        _write(self.dir, 'Chapter1_1.1_A.md', BODY, self.now)
        _write(self.dir, 'Chapter1_1.2_B.md', BODY, self.now - 10)
        _write(self.dir, 'Chapter1_1.10_C.md', BODY, self.now - 10)
        _write(self.dir, 'Chapter1_First_Examples.md', BODY, self.now - 10)
        moved, diverged = SC.reconcile_section_files(self.dir)
        self.assertEqual((moved, diverged), (0, 0))
        self.assertEqual(len(self._root_md()), 4)

    def test_chinese_prefix_uses_same_rule(self):
        _write(self.dir, '第2章_2.1_新标题.md', BODY, self.now)
        _write(self.dir, '第2章_2.1_旧标题截.md', BODY, self.now - 50)
        moved, diverged = SC.reconcile_section_files(self.dir)
        self.assertEqual((moved, diverged), (1, 0))

    def test_dry_run_moves_nothing(self):
        _write(self.dir, 'Chapter1_1.1_Newtitle.md', BODY, self.now)
        _write(self.dir, 'Chapter1_1.1_Oldtitl.md', BODY, self.now - 50)
        moved, _d = SC.reconcile_section_files(self.dir, dry_run=True)
        self.assertEqual(moved, 1)
        self.assertEqual(len(self._root_md()), 2)

    def test_section_file_key_shape(self):
        self.assertEqual(SC.section_file_key('Chapter12_12.3_Foo.md'), ('en', 12, '12.3'))
        self.assertEqual(SC.section_file_key('第3章_3.1_标题.md'), ('zh', 3, '3.1'))
        self.assertEqual(SC.section_file_key('第3章_3-1_标题.md'), ('zh', 3, '3-1'))
        # 合并稿 / 附录 / 补篇都不是节文件
        self.assertIsNone(SC.section_file_key('Chapter1_First_Examples.md'))
        self.assertIsNone(SC.section_file_key('AppendixA_Background.md'))
        self.assertIsNone(SC.section_file_key('补篇S_Things.md'))


class ReconcileMergedTest(unittest.TestCase):
    """同章两份**合并稿**的回收判据（IntroDS 第9章 实测形态）。

    合并稿改名后旧名同样不会被覆盖；这里不能要求逐字相同（旧名那份往往是折行/修订
    之前的版本），判据改为「较早那份的 `\\tag` 集合是保留者的子集」——即同一交付的
    早期版本；含保留者没有的 tag 者一律保留待人工裁决。
    """

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='bks_merged_')
        self.now = time.time()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _root_md(self):
        return sorted(f for f in os.listdir(self.dir) if f.endswith('.md'))

    def test_subset_tags_is_archived_not_deleted(self):
        new = ('# 第9章\n\n$$\nh_\\mu(T) = \\sup h(T,\\alpha)\n\\tag{9.2}\n$$\n'
               '$$\n\\text{folded}\n\\end{aligned}\n\\tag{9.3}\n$$\n')
        old = ('# 第9章\n\n$$\nh_\\mu(T) = \\sup h(T,\\alpha)\n\\tag{9.2}\n$$\n'
               '$$\nh_{\\mu}(T)=\\sup h(T,\\alpha)\n\\tag{9.3}\n$$\n')
        _write(self.dir, '第9章_Measure-Theoretic_Entropy.md', new, self.now)
        _write(self.dir, '第9章_测度论熵.md', old, self.now - 100)
        moved, diverged = SC.reconcile_merged_files(self.dir)
        self.assertEqual((moved, diverged), (1, 0))
        self.assertEqual(self._root_md(), ['第9章_Measure-Theoretic_Entropy.md'])
        arch = os.path.join(self.dir, '_extract', '_superseded_split_md')
        found = [os.path.join(r, f) for r, _d, fs in os.walk(arch) for f in fs]
        self.assertEqual([os.path.basename(p) for p in found], ['第9章_测度论熵.md'])

    def test_extra_tag_in_older_is_kept_for_adjudication(self):
        new = '# Ch9\n\n$$\nx = y\n\\tag{9.2}\n$$\n' + 'filler paragraph. ' * 30 + '\n'
        old = '# Ch9\n\n$$\nx = y\n\\tag{9.2}\n$$\n$$\nz = w\n\\tag{9.7}\n$$\n'
        _write(self.dir, 'Chapter9_New.md', new, self.now)
        _write(self.dir, 'Chapter9_Old.md', old, self.now - 100)
        moved, diverged = SC.reconcile_merged_files(self.dir)
        self.assertEqual((moved, diverged), (0, 1))
        self.assertEqual(len(self._root_md()), 2)

    def test_same_mtime_tie_breaks_on_larger_delivery(self):
        # 复制/还原过的文件 mtime 会并列：此时以内容更完整（字节更多）者为交付
        t = self.now
        _write(self.dir, 'Chapter9_B_fat.md', BODY + 'extra row\n' * 20, t)
        _write(self.dir, 'Chapter9_A_thin.md', BODY, t)
        moved, _d = SC.reconcile_merged_files(self.dir)
        self.assertEqual(moved, 1)
        self.assertEqual(self._root_md(), ['Chapter9_B_fat.md'])

    def test_one_per_language_is_not_a_duplicate(self):
        _write(self.dir, 'Chapter9_Title.md', BODY, self.now)
        _write(self.dir, '第9章_标题.md', BODY, self.now)
        _write(self.dir, 'AppendixA_Back.md', BODY, self.now)
        _write(self.dir, '附录A_背景.md', BODY, self.now)
        moved, diverged = SC.reconcile_merged_files(self.dir)
        self.assertEqual((moved, diverged), (0, 0))
        self.assertEqual(len(self._root_md()), 4)

    def test_dry_run_moves_nothing(self):
        _write(self.dir, 'Chapter9_New.md', BODY, self.now)
        _write(self.dir, 'Chapter9_Old.md', BODY, self.now - 100)
        moved, _d = SC.reconcile_merged_files(self.dir, dry_run=True)
        self.assertEqual(moved, 1)
        self.assertEqual(len(self._root_md()), 2)

    def test_merged_file_head_shapes(self):
        self.assertEqual(SC.merged_file_head('Chapter9_Title.md'), ('en', 'Chapter9'))
        self.assertEqual(SC.merged_file_head('第9章_标题.md'), ('zh', '第9章'))
        self.assertEqual(SC.merged_file_head('附录A_背景.md'), ('zh', '附录A'))
        self.assertEqual(SC.merged_file_head('SupplementS_Things.md'), ('en', 'SupplementS'))
        self.assertEqual(SC.merged_file_head('附录.md'), ('zh', '附录'))
        # 节文件与不相关文件名一律不归桶
        self.assertIsNone(SC.merged_file_head('Chapter1_1.1_Newtitle.md'))
        self.assertIsNone(SC.merged_file_head('README.md'))
        self.assertIsNone(SC.merged_file_head('第9章_9.2_标题.md'))


if __name__ == '__main__':
    unittest.main()
