# -*- coding: utf-8 -*-
"""test_fix_bq_math_blank.py — `tools/fix_bq_math_blank.py`：删引用块 display math 的围栏内空 `>` 行。

判据住在 `verify/format_verify/script/format_verify.py::bq_math_inner_blanks`（SSOT），
本测试**两侧都测**：判据认对位、工具只删点名的行。

🔴 盯的边界：
  * 甲形一律不动（乙才是缺陷）；
  * 只删围栏**内**的空 `>` 行，围栏外那条（门控 F7c 要求的）必须留着；
  * 「空行两侧都有内容」= 真在分隔两段内容 ⇒ 整块不动并计 REFUSE；
  * dry-run 零写入；commit 后备份+逐行相等+台账一行；复跑幂等；
  * 换行风格与 BOM 按文件自身守恒；单元首行标记逐字节不变；
  * 未配对的 `> $$` 不猜关门 ⇒ 不动。
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "lib"))
import lib.boot as _boot  # noqa: E402
_boot.setup()
sys.path.insert(0, os.path.join(_ROOT, "verify", "format_verify", "script"))
from format_verify import bq_math_inner_blanks  # noqa: E402

import importlib.util
_SPEC = importlib.util.spec_from_file_location(
    "fix_bq_math_blank", os.path.join(_ROOT, "tools", "fix_bq_math_blank.py"))
fb = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(fb)

MARK = "<!-- book-summarizer DONE unit: id=0005 type=item key=例1 name=N -->"

JIA = [MARK,
       u"**例1**：",
       u">",
       u"> $$",
       u"> x_1 + x_2 = 2",
       u"> $$",
       u">",
       u"> 后文散文。"]
YI_P2 = [MARK,
         u"**例1**：",
         u">",
         u"> $$",
         u"> x_1 + x_2 = 2",
         u">",
         u"> $$",
         u">",
         u"> 后文散文。"]
YI_P4 = [MARK,
         u">",
         u"> $$",
         u">",
         u"> y = 3",
         u">",
         u"> $$",
         u">",
         u"> 后文散文。"]
YI_BOTH = [MARK,
           u">",
           u"> $$",
           u"> a = 1",
           u">",
           u"> b = 2",
           u"> $$",
           u">",
           u"> 后文散文。"]
UNCLOSED = [MARK, u">", u"> $$", u"> z = 9", u">", u"散文在引用块外"]


def _tree(lines, eol="\n", bom=False, sub=u"units/ch6"):
    """造 `<root>/_extract/book_structure/<sub>/0005_item_例1.md` → (root, path)。"""
    root = tempfile.mkdtemp(prefix="fbb_")
    d = os.path.join(root, "_extract", "book_structure")
    if sub:
        d = os.path.join(d, *sub.split(u"/"))
    os.makedirs(d)
    text = u"\n".join(lines) + u"\n"
    p = os.path.join(d, u"0005_item_例1.md")
    data = text.replace("\n", eol).encode("utf-8")
    if bom:
        data = b"\xef\xbb\xbf" + data
    with io.open(p, "wb") as f:
        f.write(data)
    return root, p


def _snap(root):
    out = {}
    for base, _dirs, files in os.walk(root):
        for n in files:
            q = os.path.join(base, n)
            with io.open(q, "rb") as f:
                out[os.path.relpath(q, root)] = f.read()
    return out


def _run(paths, commit=False):
    buf = io.StringIO()
    argv = [str(p) for p in paths] + (["--commit"] if commit else [])
    old = sys.argv
    sys.argv = ["fix_bq_math_blank.py"] + argv
    try:
        with redirect_stdout(buf):
            rc = fb.main()
    finally:
        sys.argv = old
    return rc, buf.getvalue()


def _lines_of(path):
    """读回行清单（去掉文件**末尾换行**造成的那个空尾元）。"""
    with io.open(path, encoding="utf-8") as f:
        got = f.read().split(u"\n")
    return got[:-1] if got and got[-1] == u"" else got


def _added(before, after):
    """写盘后**新增**的文件（备份件 + 台账件）。"""
    return sorted(set(after) - set(before))


class TestPredicate(unittest.TestCase):
    def test_flags_only_inner_blanks(self):
        # 行号 1 起，且含首行 MARK ⇒ YI_P2 的开门围栏是 L4、围栏内空行是 L6。
        self.assertEqual(bq_math_inner_blanks(YI_P2), [(4, 6)])
        self.assertEqual(bq_math_inner_blanks(YI_P4), [(3, 4), (3, 6)])
        self.assertEqual(bq_math_inner_blanks(JIA), [])

    def test_does_not_guess_on_unclosed_fence(self):
        """开门找不到关门 ⇒ 不猜，也不报（未配对由别的判据管）。"""
        self.assertEqual(bq_math_inner_blanks(UNCLOSED), [])

    def test_top_level_block_out_of_scope(self):
        """顶层 `$$…$$` 内的空行不归本判据（它没有 `>` 围栏）。"""
        self.assertEqual(bq_math_inner_blanks([u"$$", u"x=1", u"", u"$$"]), [])


class TestPositive(unittest.TestCase):
    def test_jia_untouched(self):
        root, p = _tree(JIA)
        try:
            rc, out = _run([p])
            self.assertEqual(rc, 0)
            self.assertNotIn(u"可删", out)
            snap = _snap(root)
            _run([p], commit=True)
            self.assertEqual(_snap(root), snap, u"甲形被改了")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_commit_deletes_inner_blank_and_keeps_outer(self):
        root, p = _tree(YI_P2)
        try:
            rc, out = _run([p])
            self.assertEqual(rc, 1, u"dry-run 有可改之处须非 0")
            self.assertIn(u"可删", out)
            before = _snap(root)
            rc, _o = _run([p], commit=True)
            self.assertEqual(rc, 0)
            self.assertEqual(_lines_of(p), JIA, u"改后须正好是甲形")
            after = _snap(root)
            # 只有目标件的内容变了；其余既有文件一个字节都不动。
            changed = sorted(k for k in before
                             if before[k] != after.get(k))
            self.assertEqual(changed, [os.path.relpath(p, root)])
            added = sorted(k.replace("\\", "/") for k in _added(before, after))
            self.assertEqual(len(added), 2, u"commit 只该新增备份件与台账件：%s" % added)
            self.assertTrue(any(k.endswith(fb.LEDGER) for k in added),
                            u"台账件缺失：%s" % added)
            self.assertTrue(any(u"_bak_fix_bq_math_blank/" in k for k in added),
                            u"备份件没落在 BAK_DIR 下：%s" % added)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_two_inner_blanks_both_removed(self):
        root, p = _tree(YI_P4)
        try:
            rc, _o = _run([p], commit=True)
            self.assertEqual(rc, 0)
            lines = _lines_of(p)
            self.assertEqual(bq_math_inner_blanks(lines), [])
            self.assertEqual(lines,
                             [MARK, u">", u"> $$", u"> y = 3", u"> $$",
                              u">", u"> 后文散文。"],
                             u"P4（公式上下各一条围栏内空行）须两条都删且公式行不动")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_idempotent_and_ledgers_once(self):
        root, p = _tree(YI_P2)
        try:
            self.assertEqual(_run([p], commit=True)[0], 0)
            self.assertEqual(_run([p], commit=True)[0], 0)
            led = os.path.join(root, "_extract", fb.LEDGER)
            with io.open(led, encoding="utf-8") as f:
                recs = [json.loads(l) for l in f if l.strip()]
            self.assertEqual(len(recs), 1, u"复跑不该再落账")
            self.assertEqual(recs[0]["removed_lines"], 1)
            self.assertEqual(recs[0]["layer"], u"units")
            self.assertTrue(os.path.isfile(recs[0]["backup"]))
            self.assertEqual(_lines_of(recs[0]["backup"]), YI_P2,
                             u"备份件须是改前内容")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_newline_and_bom_preserved(self):
        for eol, bom in (("\r\n", False), ("\n", False), ("\r\n", True), ("\n", True)):
            root, p = _tree(YI_P2, eol=eol, bom=bom)
            try:
                self.assertEqual(_run([p], commit=True)[0], 0)
                with io.open(p, "rb") as f:
                    raw = f.read()
                self.assertEqual(raw.startswith(b"\xef\xbb\xbf"), bom, u"BOM 丢了/多了")
                body = raw[3:] if bom else raw
                if eol == "\r\n":
                    self.assertEqual(body.count(b"\r\n"), body.count(b"\n"))
                else:
                    self.assertNotIn(b"\r", body, u"LF 被翻成 CRLF")
            finally:
                shutil.rmtree(root, ignore_errors=True)

    def test_unit_marker_first_line_untouched(self):
        root, p = _tree(YI_P2)
        try:
            _run([p], commit=True)
            with io.open(p, encoding="utf-8") as f:
                self.assertEqual(f.readline().rstrip("\r\n"), MARK)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_directory_input_is_walked(self):
        root, p = _tree(YI_P2)
        try:
            rc, out = _run([os.path.join(root, "_extract", "book_structure")])
            self.assertEqual(rc, 1)
            self.assertIn(u"0005_item", out)
        finally:
            shutil.rmtree(root, ignore_errors=True)


class TestRefusals(unittest.TestCase):
    def test_refuse_when_blank_separates_two_content_runs(self):
        """空行两侧都有内容 ⇒ 删它会并块，整块不动。"""
        root, p = _tree(YI_BOTH)
        try:
            before = _snap(root)
            rc, out = _run([p], commit=True)
            self.assertEqual(rc, 1)
            self.assertIn(u"REFUSE", out)
            self.assertEqual(_snap(root), before, u"REFUSE 路径动了磁盘")
            self.assertFalse(os.path.isfile(os.path.join(root, "_extract", fb.LEDGER)))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_unclosed_fence_untouched(self):
        root, p = _tree(UNCLOSED)
        try:
            before = _snap(root)
            rc, _out = _run([p], commit=True)
            self.assertEqual(rc, 0)
            self.assertEqual(_snap(root), before, u"未配对围栏被改了")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_dry_run_writes_nothing(self):
        root, p = _tree(YI_P2)
        try:
            before = _snap(root)
            self.assertEqual(_run([p])[0], 1)
            self.assertEqual(_snap(root), before, u"dry-run 动了磁盘")
            self.assertFalse(os.path.isfile(os.path.join(root, "_extract", fb.LEDGER)))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_no_extract_ancestor_still_fixes(self):
        """脱离书根的单文件（无 `_extract`）：照修，只是不落账不备份。"""
        d = tempfile.mkdtemp(prefix="fbb_bare_")
        p = os.path.join(d, u"x.md")
        with io.open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(u"\n".join(YI_P2[1:]) + u"\n")
        try:
            self.assertEqual(_run([p], commit=True)[0], 0)
            self.assertEqual(_lines_of(p), JIA[1:])
            self.assertEqual(os.listdir(d), [u"x.md"], u"无书根时不该造备份/台账目录")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_trailing_newline_shape_preserved(self):
        """结尾换行**形制**守恒：无尾换行不能被补上，两个尾空行不能被削成一个。"""
        E = u""
        cases = ((E, JIA),
                 (u"\n", JIA + [E]),
                 (u"\n\n", JIA + [E, E]))
        for tail, want in cases:
            root = tempfile.mkdtemp(prefix="fbb_tail_")
            d = os.path.join(root, "_extract", "book_structure", "units", "ch6")
            os.makedirs(d)
            p = os.path.join(d, u"u.md")
            with io.open(p, "wb") as f:
                f.write((u"\n".join(YI_P2) + tail).replace("\n", "\r\n").encode("utf-8"))
            try:
                self.assertEqual(_run([p], commit=True)[0], 0)
                with io.open(p, "rb") as f:
                    raw = f.read()
                self.assertEqual(raw.decode("utf-8").replace("\r\n", "\n").split(u"\n"), want,
                                 u"结尾形制被改（tail=%r）" % tail)
                self.assertEqual(raw.count(b"\r"), raw.count(b"\n"), u"CRLF 被翻成 LF")
            finally:
                shutil.rmtree(root, ignore_errors=True)

    def test_layer_recorded_per_side(self):
        """台账的 `layer` 按路径**分段**判定：units / units-translate / 交付 三档互不串。

        盯的是 `layer_of` 的子串判据：`units-translate` 里也含 `units`，先判长名才不错档。
        """
        cases = [(u"units/ch6", u"units"),
                 (u"units-translate/ch6", u"units-translate"),
                 (None, u"交付")]
        for sub, want in cases:
            root, p = _tree(YI_P2, sub=sub)
            try:
                self.assertEqual(_run([p], commit=True)[0], 0)
                led = os.path.join(root, "_extract", fb.LEDGER)
                with io.open(led, encoding="utf-8") as f:
                    rec = json.loads(f.readline())
                self.assertEqual(rec["layer"], want, u"%s 落错档" % sub)
            finally:
                shutil.rmtree(root, ignore_errors=True)

    def test_batch_refuse_does_not_block_other_files(self):
        """一批里有 REFUSE 件时：可修件照常写，退出码非 0 把 REFUSE 报出来（不静默）。"""
        root_a, pa = _tree(YI_P2)
        root_b, pb = _tree(YI_BOTH)
        try:
            rc, out = _run([pa, pb], commit=True)
            self.assertEqual(rc, 1, u"有 REFUSE 须非 0")
            self.assertIn(u"REFUSE", out)
            self.assertEqual(_lines_of(pa), JIA, u"可修件被 REFUSE 连坐")
            self.assertEqual(_lines_of(pb), YI_BOTH, u"REFUSE 件被动了")
        finally:
            shutil.rmtree(root_a, ignore_errors=True)
            shutil.rmtree(root_b, ignore_errors=True)

    def test_backup_dirs_are_never_walked(self):
        """按书根递归喂目录时，**快照面**必须一个字节都不动。

        盯的是 collect() 的快照过滤。2026-11-02 全架普查（p1190 B 档）实测有三种快照形态，
        只有第一种带 `_bak` 前缀：提交备份目录 / 手工改前快照目录 `_pre_fix_*` /
        探针与临时件（文件名以 `_` 开头）。第二趟若把它们一起「修」掉，回滚面与证据就没了。
        """
        root, p = _tree(YI_P2)
        bak_dirs = [os.path.join(root, "_extract", fb.BAK_DIR, "TS1", "book_structure", "units", "ch6"),
                    os.path.join(root, "_extract", "_bak_sync_delivery_from_units", "20261101"),
                    os.path.join(root, "_extract", "_pre_fix_20261022", "delivery")]
        baked = []
        for d in bak_dirs:
            os.makedirs(d)
            q = os.path.join(d, u"0005_item_例1.md")
            with io.open(q, "wb") as f:
                f.write((u"\n".join(YI_P2) + u"\n").encode("utf-8"))
            baked.append(q)
        probe = os.path.join(root, "_extract", u"_probe_ch4.md")
        with io.open(probe, "wb") as f:
            f.write((u"\n".join(YI_P2) + u"\n").encode("utf-8"))
        baked.append(probe)
        try:
            self.assertEqual(_run([root], commit=True)[0], 0)
            self.assertEqual(_lines_of(p), JIA, u"目标件没修")
            for q in baked:
                self.assertEqual(_lines_of(q), YI_P2, u"快照件被改了：%s" % q)
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
