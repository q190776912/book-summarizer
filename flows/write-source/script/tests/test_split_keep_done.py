# -*- coding: utf-8 -*-
"""Regression: `split_draft_units --force --keep-done` (contract 修正后重建单元).

Why this exists
---------------
A contract fix (e.g. the chapter-boundary band clip) re-renders every unit, and
plain `--force` wiped ~300 already-rewritten DONE units with it. `--keep-done`
preserves a DONE unit verbatim when its **source rendering** hash is unchanged.
The first implementation of that feature silently kept **0** units in every
chapter, because it looked for the substring `" DONE unit "` while the mark is
`book-summarizer DONE unit:` — the same wrong predicate also made the
`--force`-without-`--keep-done`毁稿 guard return 0 and let the wipe through.
Both protections failing *open* is exactly what these tests forbid.

Runs under stdlib unittest:
  python flows/write-source/script/tests/test_split_keep_done.py
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
    _ROOT = str(Path(__file__).resolve().parents[3])
sys.path.insert(0, str(Path(_ROOT) / "flows" / "write-source" / "script"))

import split_draft_units as sdu  # noqa: E402

DONE_MARK = "<!-- book-summarizer DONE unit: id=0001 type=desc key=D1 name= -->"
DRAFT_MARK = "<!-- book-summarizer DRAFT unit: id=0001 type=desc key=D1 name= -->"


def _unit(lines, utype="desc", key="D1", name="", ntype="description"):
    return {"type": utype, "key": key, "name": name, "lines": list(lines),
            "ntype": ntype, "ntags": [], "nimages": [], "ncontent": 1}


class Base(unittest.TestCase):
    def setUp(self):
        self.ext = tempfile.mkdtemp(prefix="bks_keepdone_")
        os.makedirs(os.path.join(self.ext, "book_structure"))
        with open(os.path.join(self.ext, "_extraction_done.json"), "w") as f:
            json.dump({"ok": True}, f)
        with open(os.path.join(self.ext, "book_structure", "ch1.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"key": "1", "type": "chapter", "name": "One", "sub_sec": []}, f)
        self._emit = sdu._emit_units
        self.addCleanup(setattr, sdu, "_emit_units", self._emit)

    def emit(self, units):
        sdu._emit_units = lambda node, lang: units

    def dir_of(self, ch="1"):
        return os.path.join(self.ext, sdu.OUT_SUB, "ch%s" % ch)

    def read(self, fn):
        with open(os.path.join(self.dir_of(), fn), encoding="utf-8") as f:
            return f.read().replace("\r\n", "\n")

    def first(self):
        return json.load(open(os.path.join(self.dir_of(), "manifest.json"),
                              encoding="utf-8"))["units"][0]["file"]

    def mark_done(self, fn, body):
        with open(os.path.join(self.dir_of(), fn), "w", encoding="utf-8") as f:
            f.write(DONE_MARK + "\n" + body + "\n")


class TestDoneMarkPredicate(Base):
    def test_real_mark_recognized(self):
        self.assertTrue(sdu._is_done_first_line(DONE_MARK))
        self.assertTrue(sdu._is_done_first_line(DONE_MARK + "\r\n"))

    def test_draft_mark_rejected(self):
        self.assertFalse(sdu._is_done_first_line(DRAFT_MARK))
        self.assertFalse(sdu._is_done_first_line(""))

    def test_space_form_is_not_the_mark(self):
        # locks the bug: a predicate that demands " DONE unit " matches nothing.
        self.assertNotIn(" DONE unit ", DONE_MARK)


class TestKeepDone(Base):
    def test_untouched_done_body_survives(self):
        self.emit([_unit(["原始正文"])])
        sdu.split_chapter(self.ext, "1", "en", force=True)
        fn = self.first()
        self.mark_done(fn, "agent 改好的稿子 $x$")
        h_old = json.load(open(os.path.join(self.dir_of(), "manifest.json"),
                               encoding="utf-8"))["units"][0]["hash"]
        self.emit([_unit(["原始正文"])])              # 正文源不变
        sdu.split_chapter(self.ext, "1", "en", force=True, keep_done=True)
        txt = self.read(self.first())
        self.assertTrue(txt.startswith(DONE_MARK), txt.splitlines()[0])
        self.assertIn("agent 改好的稿子", txt)
        self.assertNotIn("原始正文", txt)
        self.assertEqual(json.load(open(os.path.join(self.dir_of(), "manifest.json"),
                                        encoding="utf-8"))["units"][0]["hash"], h_old)

    def test_changed_source_falls_back_to_draft(self):
        self.emit([_unit(["原始正文"])])
        sdu.split_chapter(self.ext, "1", "en", force=True)
        fn = self.first()
        self.mark_done(fn, "agent 改好的稿子")
        self.emit([_unit(["契约修正后的新正文"])])
        sdu.split_chapter(self.ext, "1", "en", force=True, keep_done=True)
        txt = self.read(self.first())
        self.assertIn("DRAFT unit:", txt.splitlines()[0])
        self.assertIn("契约修正后的新正文", txt)
        self.assertNotIn("agent 改好的稿子", txt)

    def test_cross_family_shared_key_all_preserved(self):
        """同一节内 Definition/Theorem 共用编号键 `1.1-1`：两个 DONE 都必须保住。

        🔴 这是旧实现「(type, key) 撞键整桶丢弃」的误伤锁：编号按家族重启时
        ``item`` + ``key`` 相同而 ``ntype`` 不同属**常态**，丢桶 = 成批作废稿子
        （Lehmann ch3 实测 49 个 DONE 只留 29 个，20 个纯误伤）。
        """
        units = [_unit(["定理正文"], utype="item", key="1.1-1", ntype="theorem"),
                 _unit(["定义正文"], utype="item", key="1.1-1", ntype="definition")]
        self.emit(units)
        sdu.split_chapter(self.ext, "1", "en", force=True)
        recs = json.load(open(os.path.join(self.dir_of(), "manifest.json"),
                              encoding="utf-8"))["units"]
        self.mark_done(recs[0]["file"], "定理的稿子")
        self.mark_done(recs[1]["file"], "定义的稿子")
        self.assertEqual(len(sdu._load_done_index(self.dir_of())), 2)
        self.emit([_unit(u["lines"], utype=u["type"], key=u["key"],
                         ntype=u["ntype"]) for u in units])
        sdu.split_chapter(self.ext, "1", "en", force=True, keep_done=True)
        recs = json.load(open(os.path.join(self.dir_of(), "manifest.json"),
                              encoding="utf-8"))["units"]
        self.assertIn("定理的稿子", self.read(recs[0]["file"]))
        self.assertIn("定义的稿子", self.read(recs[1]["file"]))

    def test_same_identity_duplicates_indexed_by_occurrence(self):
        """连 ntype 也相同的重复身份键（同家族同号两节点）按出现序号区分，各自保留。"""
        units = [_unit(["第一段"], utype="item", key="1.1-1", ntype="example"),
                 _unit(["第二段"], utype="item", key="1.1-1", ntype="example")]
        self.emit(units)
        sdu.split_chapter(self.ext, "1", "en", force=True)
        recs = json.load(open(os.path.join(self.dir_of(), "manifest.json"),
                              encoding="utf-8"))["units"]
        self.mark_done(recs[0]["file"], "第一段稿子")
        self.mark_done(recs[1]["file"], "第二段稿子")
        self.emit(units)
        sdu.split_chapter(self.ext, "1", "en", force=True, keep_done=True)
        recs = json.load(open(os.path.join(self.dir_of(), "manifest.json"),
                              encoding="utf-8"))["units"]
        self.assertIn("第一段稿子", self.read(recs[0]["file"]))
        self.assertIn("第二段稿子", self.read(recs[1]["file"]))

    def test_occurrence_drift_never_keeps_wrong_body(self):
        """同身份前面多出一个节点 ⇒ 序号整体漂移：hash 对不上就回 DRAFT，不得搬错稿。"""
        units = [_unit(["甲"], utype="item", key="1.1-1", ntype="example"),
                 _unit(["乙"], utype="item", key="1.1-1", ntype="example")]
        self.emit(units)
        sdu.split_chapter(self.ext, "1", "en", force=True)
        recs = json.load(open(os.path.join(self.dir_of(), "manifest.json"),
                              encoding="utf-8"))["units"]
        self.mark_done(recs[0]["file"], "甲的稿子")
        self.mark_done(recs[1]["file"], "乙的稿子")
        self.emit([_unit(["丙"], utype="item", key="1.1-1", ntype="example")] + units)
        sdu.split_chapter(self.ext, "1", "en", force=True, keep_done=True)
        recs = json.load(open(os.path.join(self.dir_of(), "manifest.json"),
                              encoding="utf-8"))["units"]
        # 位置 0 是全新的丙（无旧稿）；位置 1/2 的旧稿源已错位 ⇒ 一律保守回 DRAFT
        for r in recs:
            self.assertIn("DRAFT unit:", self.read(r["file"]).splitlines()[0])
        self.assertIn("丙", self.read(recs[0]["file"]))

    def test_draft_units_are_not_indexed(self):
        self.emit([_unit(["A"], key="D1")])
        sdu.split_chapter(self.ext, "1", "en", force=True)
        self.assertEqual(sdu._load_done_index(self.dir_of()), {})


class TestForceGuard(Base):
    def _run(self, argv):
        old = sys.argv
        sys.argv = ["split_draft_units.py"] + argv
        try:
            return sdu.main()
        finally:
            sys.argv = old

    def test_force_with_done_units_blocked(self):
        self.emit([_unit(["A"], key="D1")])
        sdu.split_chapter(self.ext, "1", "en", force=True)
        fn = self.first()
        self.mark_done(fn, "不可作废的稿子")
        self.assertEqual(self._run([self.ext, "--force"]), 2)
        self.assertIn("不可作废的稿子", self.read(fn))       # 未被毁

    def test_force_keep_done_proceeds(self):
        self.emit([_unit(["A"], key="D1")])
        sdu.split_chapter(self.ext, "1", "en", force=True)
        fn = self.first()
        self.mark_done(fn, "不可作废的稿子")
        self.emit([_unit(["A"], key="D1")])
        self.assertEqual(self._run([self.ext, "--force", "--keep-done"]), 0)
        self.assertIn("不可作废的稿子", self.read(self.first()))

    def test_force_without_done_units_allowed(self):
        self.emit([_unit(["A"], key="D1")])
        sdu.split_chapter(self.ext, "1", "en", force=True)
        self.assertEqual(self._run([self.ext, "--force"]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
