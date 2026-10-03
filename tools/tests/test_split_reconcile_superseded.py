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


if __name__ == '__main__':
    unittest.main()
