# -*- coding: utf-8 -*-
"""test_mirror_delivery_ref_form.py — `tools/mirror_delivery_ref_form.py`：交付散文回指号形镜像。

场景：给一章整体换号形（GM 印面页边列是罗马 `(I.12)`，早期笔记写成阿拉伯 `(1.12)`）后，
单元/契约已全罗马、**交付 md 仍停在旧形**：`mirror_unit_line` 的前提是「整块只差一行」，
换号形是一章里几十处差 ⇒ 全拒；gate 与 verify 都不看散文回指 ⇒ 整章全绿隐形。本工具是
那条唯一合法出口（收官书禁重 merge）。

正向：dry-run 零写入；--commit 后**只有**回指号那一行变、行数守恒、CRLF 守恒、备份 = 原始字节
且同名不覆盖（留首轮真身）、重跑归零（幂等）；`\\tag{}` 里的号**不**被顺手改（块号归
dereg/backfill 管）；坐标对 `(1.3, 2.4)` 形状不匹配 ⇒ 不动；源侧没写过的号 `(1.9)` ⇒ 不动；
跨章旧形（ch2 交付里的 `(11.24)`/`(2.24)`/`(1.12)`）各自映射到本形；号集第二路（契约没登记、
**单元正文**写成 `(I.1)` 的号）能清，且 `--contract-only` 可复现地关掉这一路。
负向（全部要求磁盘零改动）：①同一旧形在同章撞两个目标字面形 → 拒；②`--from-ch` 指到缺失的契约 → 拒；
③字母章键（附录 A）→ 拒（本工具按章序派生罗马前缀，字母章无旧形可言）；④该语种没有交付 md → 拒；
⑤号集为空 → 不写并明说；⑥回指落在单元 marker 行 → 拒（marker 是登记处抄本，改一处即整章脱账）。
"""
import importlib.util
import io
import json
import os
import re
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

_SPEC = importlib.util.spec_from_file_location(
    "mirror_delivery_ref_form", os.path.join(_ROOT, "tools", "mirror_delivery_ref_form.py"))
rf = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rf)

EN_MD = u"Chapter1_Simplicial_Sets.md"
CN_MD = u"第1章_单纯集.md"
EN_MD2 = u"Chapter2_Main_Notions.md"
COORD = u"坐标 $(1.3, 2.4)$ 不是回指；(1.9) 源侧从没写成 (I.9)。"


def _write(path, text, eol="\r\n"):
    d = os.path.dirname(path)
    if not os.path.isdir(d):
        os.makedirs(d)
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text.replace(u"\n", eol))


def _tree(contract=None, unit_src=None, mds=None, eol="\r\n"):
    """最小书树：`<root>/_extract/book_structure/{chN.json,units/chN/,units-translate/chN/}` + 交付 md。"""
    root = tempfile.mkdtemp()
    ext = os.path.join(root, u"_extract")
    bs = os.path.join(ext, u"book_structure")
    for ch, tags in (contract or {}).items():
        man = {u"chapter_key": ch, u"language": u"en", u"final_md": u"",
               u"units": [{u"id": u"0001", u"file": u"0001_item_x.md",
                           u"type": u"item", u"key": u"1.1", u"name": u"N"}]}
        for side in (u"units", u"units-translate"):
            udir = os.path.join(bs, side, u"ch%s" % ch)
            os.makedirs(udir)
            _write(os.path.join(udir, u"manifest.json"),
                   json.dumps(man, ensure_ascii=False, indent=2), eol)
        body = (unit_src or {}).get(ch)
        if body:
            _write(os.path.join(bs, u"units", u"ch%s" % ch, u"0001_item_x.md"),
                   u"\n".join(body), eol)
        _write(os.path.join(bs, u"ch%s.json" % ch),
               json.dumps({u"sub_sec": [{u"items": [{u"tag": t} for t in tags]}]},
                          ensure_ascii=False), eol)
    for name, lines in (mds or {}).items():
        _write(os.path.join(root, name), u"\n".join(lines), eol)
    return root, ext


def _run(ext, ch, commit=False, book=None, backup=None, side=None, extra=()):
    argv = [ext, str(ch)]
    if book:
        argv += [u"--book-dir", book]
    if backup:
        argv += [u"--backup-dir", backup]
    if side:
        argv += [u"--side", side]
    argv += list(extra)
    if commit:
        argv.append(u"--commit")
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = rf.main(argv)
    return rc, buf.getvalue()


def _lines(path, eol=u"\r\n"):
    return io.open(path, encoding=u"utf-8", newline=u"").read().split(eol)


def _stale_ch1():
    """ch1 交付：两处旧形回指 + 一处 `\\tag` + 一处坐标对 + 一个不在号集的号。"""
    return [u"# 第1章 单纯集",
            u"",
            u"边界算子由公式 (1.3) 给出，见 (1.12) 的对偶。",
            u"",
            u"$$",
            u"dx = 0 \\tag{1.3}",
            u"$$",
            u"",
            COORD,
            u""]


class RefForm(unittest.TestCase):
    def tearDown(self):
        for d in getattr(self, "_dirs", []):
            shutil.rmtree(d, ignore_errors=True)

    def _t(self, *a, **kw):
        t = _tree(*a, **kw)
        self.__dict__.setdefault("_dirs", []).append(t[0])
        return t

    # ---- 正向 ----
    def test_dry_run_writes_nothing(self):
        root, ext = self._t(
            contract={u"1": [u"I.3", u"I.12"]},
            unit_src={u"1": [u"公式 (I.3) 如前述"]},
            mds={EN_MD: _stale_ch1()})
        path = os.path.join(root, EN_MD)
        before = open(path, "rb").read()
        rc, out = _run(ext, 1, book=root)
        self.assertEqual(rc, 0)
        self.assertIn(u"dry-run", out)
        self.assertIn(u"(1.3) → (I.3)", out)
        self.assertEqual(open(path, "rb").read(), before)
        self.assertFalse(os.path.isdir(os.path.join(ext, u"_bak_delivery_ref_form")))

    def test_commit_touches_only_the_ref_line(self):
        root, ext = self._t(
            contract={u"1": [u"I.3", u"I.12"]},
            unit_src={u"1": [u"公式 (I.3)"]},
            mds={EN_MD: _stale_ch1()})
        path = os.path.join(root, EN_MD)
        before_raw = open(path, "rb").read()
        bl = _lines(path)
        rc, out = _run(ext, 1, commit=True, book=root)
        self.assertEqual(rc, 0, out)
        self.assertIn(u"已写盘", out)
        al = _lines(path)
        self.assertEqual(len(bl), len(al))                      # 行数守恒
        self.assertEqual([i for i in range(len(bl)) if bl[i] != al[i]], [2])
        self.assertEqual(al[2], u"边界算子由公式 (I.3) 给出，见 (I.12) 的对偶。")
        self.assertEqual(al[5], u"dx = 0 \\tag{1.3}")            # 块号不归本工具管
        self.assertEqual(al[8], COORD)                           # 坐标对 + 无源号：原样
        self.assertIn(b"\r\n", open(path, "rb").read())          # 换行风格守恒
        bakroot = os.path.join(ext, u"_bak_delivery_ref_form")
        stamps = os.listdir(bakroot)
        self.assertEqual(len(stamps), 1)
        self.assertEqual(open(os.path.join(bakroot, stamps[0], EN_MD), "rb").read(),
                         before_raw)                            # 备份 = 原始字节

    def test_second_run_is_clean(self):
        root, ext = self._t(
            contract={u"1": [u"I.3"]},
            unit_src={u"1": [u"公式 (I.3)"]},
            mds={EN_MD: _stale_ch1()})
        path = os.path.join(root, EN_MD)
        rc, out = _run(ext, 1, commit=True, book=root)
        self.assertEqual(rc, 0, out)
        mid = open(path, "rb").read()
        rc2, out2 = _run(ext, 1, commit=True, book=root)
        self.assertEqual(rc2, 0)
        self.assertIn(u"共 0 处", out2)
        self.assertEqual(open(path, "rb").read(), mid)

    def test_backup_keeps_the_first_original(self):
        """同名不覆盖：第二轮再漂一次，备份里仍是**首轮真身**（回滚面最大时靠它）。"""
        root, ext = self._t(
            contract={u"1": [u"I.3"]},
            unit_src={u"1": [u"公式 (I.3)"]},
            mds={EN_MD: _stale_ch1()})
        path = os.path.join(root, EN_MD)
        first_raw = open(path, "rb").read()
        bak = os.path.join(ext, u"_bak_fixed")
        _run(ext, 1, commit=True, book=root, backup=bak)
        _write(path, u"\n".join([u"# 第1章 单纯集", u"", u"又漂回 (1.3) 一次", u""]), u"\r\n")
        _run(ext, 1, commit=True, book=root, backup=bak)
        self.assertEqual(open(os.path.join(bak, EN_MD), "rb").read(), first_raw)
        self.assertIn(u"(I.3)", _lines(path)[2])

    def test_cross_chapter_old_forms(self):
        """ch2 交付里三种历史旧形并存：`(11.24)`（罗马当数字抄）、`(2.24)`（阿拉伯章号）、
        `(1.12)`（跨章回指 ch1）——各按**自己那章**的前缀映射。"""
        root, ext = self._t(
            contract={u"1": [u"I.12"], u"2": [u"II.24"]},
            unit_src={u"1": [u"见 (I.12)"], u"2": [u"由 (II.24)"]},
            mds={EN_MD2: [u"# Chapter 2", u"",
                          u"关系 (11.24) 与 (2.24) 如前述，另引 (1.12)。", u""]})
        path = os.path.join(root, EN_MD2)
        rc, out = _run(ext, 2, commit=True, book=root)
        self.assertEqual(rc, 0, out)
        self.assertEqual(_lines(path)[2],
                         u"关系 (II.24) 与 (II.24) 如前述，另引 (I.12)。")

    def test_lf_file_stays_lf(self):
        root, ext = self._t(
            contract={u"1": [u"I.3"]},
            unit_src={u"1": [u"公式 (I.3)"]},
            mds={EN_MD: _stale_ch1()}, eol=u"\n")
        path = os.path.join(root, EN_MD)
        rc, out = _run(ext, 1, commit=True, book=root)
        self.assertEqual(rc, 0, out)
        raw = open(path, "rb").read()
        self.assertNotIn(b"\r", raw)
        self.assertIn(u"(I.3)", raw.decode(u"utf-8").split(u"\n")[2])

    def test_unit_prose_only_numbers_are_mirrored(self):
        """号集第二路：契约**没**登记、但单元正文写成 `(I.1)` 的号也要能清（GM ch1 实测）。"""
        root, ext = self._t(
            contract={u"1": [u"I.3"]},
            unit_src={u"1": [u"如 (I.1) 与 (I.6) 所示"]},
            mds={EN_MD: [u"# Ch1", u"", u"见 (1.1) 与 (1.6)。", u""]})
        path = os.path.join(root, EN_MD)
        rc, out = _run(ext, 1, commit=True, book=root)
        self.assertEqual(rc, 0, out)
        self.assertEqual(_lines(path)[2], u"见 (I.1) 与 (I.6)。")

    def test_contract_only_skips_unit_prose_numbers(self):
        """``--contract-only`` 关掉第二路 → 那些号**不该**被动（口径可复现，不许偷偷放宽）。"""
        root, ext = self._t(
            contract={u"1": [u"I.3"]},
            unit_src={u"1": [u"如 (I.1) 所示"]},
            mds={EN_MD: [u"# Ch1", u"", u"见 (1.1) 与 (1.3)。", u""]})
        path = os.path.join(root, EN_MD)
        rc, out = _run(ext, 1, commit=True, book=root, extra=[u"--contract-only"])
        self.assertEqual(rc, 0, out)
        self.assertEqual(_lines(path)[2], u"见 (1.1) 与 (I.3)。")

    def test_side_selection_leaves_the_other_lang_alone(self):
        root, ext = self._t(
            contract={u"1": [u"I.3"]},
            unit_src={u"1": [u"公式 (I.3)"]},
            mds={EN_MD: _stale_ch1(), CN_MD: [u"# 第1章", u"", u"由 (1.3) 给出", u""]})
        en = os.path.join(root, EN_MD)
        cn = os.path.join(root, CN_MD)
        en_before = open(en, "rb").read()
        rc, out = _run(ext, 1, commit=True, book=root, side=u"cn")
        self.assertEqual(rc, 0, out)
        self.assertEqual(open(en, "rb").read(), en_before)
        self.assertEqual(_lines(cn)[2], u"由 (I.3) 给出")

    # ---- 负向：拒绝且磁盘零改动 ----
    def test_colliding_targets_refuse(self):
        """同章账里 `I.5` 与 `I. 5` 两种字面形 → 同一旧形两个目标，宁可拒。"""
        root, ext = self._t(
            contract={u"1": [u"I.5", u"I. 5"]},
            unit_src={u"1": [u"公式 (I.5)"]},
            mds={EN_MD: [u"# Ch1", u"", u"见 (1.5)。", u""]})
        path = os.path.join(root, EN_MD)
        before = open(path, "rb").read()
        with self.assertRaises(SystemExit) as cm:
            _run(ext, 1, commit=True, book=root)
        self.assertIn(u"撞两个目标", str(cm.exception))
        self.assertEqual(open(path, "rb").read(), before)

    def test_missing_contract_refuses(self):
        root, ext = self._t(
            contract={u"1": [u"I.3"]},
            unit_src={u"1": [u"公式 (I.3)"]},
            mds={EN_MD: [u"# Ch1", u"", u"见 (1.3)。", u""]})
        os.remove(os.path.join(ext, u"book_structure", u"ch1.json"))
        path = os.path.join(root, EN_MD)
        before = open(path, "rb").read()
        with self.assertRaises(SystemExit) as cm:
            _run(ext, 1, commit=True, book=root, extra=[u"--from-ch", u"1"])
        self.assertIn(u"缺契约文件", str(cm.exception))
        self.assertEqual(open(path, "rb").read(), before)

    def test_letter_chapter_refuses(self):
        """字母章（附录 A）没有「章序 → 罗马前缀」的旧形可派生，直接拒而不是猜。"""
        root, ext = self._t(
            contract={u"1": [u"I.3"]},
            unit_src={u"1": [u"公式 (I.3)"]},
            mds={EN_MD: [u"# Ch1", u"", u"见 (1.3)。", u""]})
        path = os.path.join(root, EN_MD)
        before = open(path, "rb").read()
        with self.assertRaises(SystemExit) as cm:
            _run(ext, u"A", commit=True, book=root)
        self.assertIn(u"字母章", str(cm.exception))
        self.assertEqual(open(path, "rb").read(), before)

    def test_no_delivery_for_requested_side_refuses(self):
        root, ext = self._t(
            contract={u"1": [u"I.3"]},
            unit_src={u"1": [u"公式 (I.3)"]},
            mds={CN_MD: [u"# 第1章", u"", u"由 (1.3) 给出", u""]})
        with self.assertRaises(SystemExit) as cm:
            _run(ext, 1, commit=True, book=root, side=u"en")
        self.assertIn(u"没有交付 md", str(cm.exception))

    def test_empty_number_set_writes_nothing(self):
        """号集为空（契约全是裸号、单元也无罗马回指）→ 明说不写，不许静默扫一遍。"""
        root, ext = self._t(
            contract={u"1": [u"5", u"7"]},
            unit_src={u"1": [u"普通正文，没有罗马回指"]},
            mds={EN_MD: [u"# Ch1", u"", u"见 (1.5)。", u""]})
        path = os.path.join(root, EN_MD)
        before = open(path, "rb").read()
        rc, out = _run(ext, 1, commit=True, book=root)
        self.assertEqual(rc, 0)
        self.assertIn(u"号集为空", out)
        self.assertEqual(open(path, "rb").read(), before)

    def test_ref_inside_unit_marker_line_refuses(self):
        """marker 行是登记处抄本：回指落在那儿必须整条拒，不能「顺手改一个字符」。"""
        mark = u"<!-- book-summarizer DONE unit: id=0001 type=item key=1.5 name=(1.5) -->"
        root, ext = self._t(
            contract={u"1": [u"I.5"]},
            unit_src={u"1": [u"公式 (I.5)"]},
            mds={EN_MD: [mark, u"# Ch1", u"", u"见 (1.5)。", u""]})
        path = os.path.join(root, EN_MD)
        before = open(path, "rb").read()
        with self.assertRaises(SystemExit) as cm:
            _run(ext, 1, commit=True, book=root)
        self.assertIn(u"marker", str(cm.exception))
        self.assertEqual(open(path, "rb").read(), before)


class RefFormInternals(unittest.TestCase):
    """派生层的三条形状判据（不建书树，直接打函数）。"""

    def test_roman_only_for_1_to_3999(self):
        self.assertEqual(rf.roman(1), u"I")
        self.assertEqual(rf.roman(4), u"IV")
        self.assertEqual(rf.roman(3999), u"MMMCMXCIX")
        for bad in (0, 4000, None, u"3"):
            self.assertIsNone(rf.roman(bad))

    def test_build_map_skips_cross_chapter_tags(self):
        """本章派生只看本章前缀：ch3 账里引 `I.5` 不给 ch3 造 `(1.5)` 旧形。"""
        mp = rf.build_map([u"I.5", u"III.5"], 3)
        self.assertIn(r"\(\s*3\s*\.\s*5\s*\)", mp)
        self.assertIn(r"\(\s*111\s*\.\s*5\s*\)", mp)
        self.assertNotIn(r"\(\s*1\s*\.\s*5\s*\)", mp)

    def test_old_forms_are_number_shaped_not_substring(self):
        """旧形正则要求 `)` 紧跟数字 ⇒ 坐标对 / 三位小数 / 别的章号形状上就进不来。"""
        mp = rf.build_map([u"I.3"], 1)
        self.assertEqual(sorted(mp), [r"\(\s*1\s*\.\s*3\s*\)"])
        src = list(mp)[0]
        for hit in (u"(1.3)", u"( 1 . 3 )"):
            self.assertTrue(re.fullmatch(src, hit), hit)
        for miss in (u"(1.3, 2.4)", u"(1.30)", u"(11.3)", u"(I.3)", u"x(1.3)y"):
            self.assertFalse(re.fullmatch(src, miss), miss)

    def test_contract_tags_walks_nested_lists(self):
        """契约 tag 藏在 `sub_sec[].items[]` 里，`tag` 与 `tags` 两种壳都要收到。"""
        root = tempfile.mkdtemp()
        try:
            bs = os.path.join(root, u"_extract", u"book_structure")
            os.makedirs(bs)
            _write(os.path.join(bs, u"ch7.json"), json.dumps({
                u"sub_sec": [{u"items": [{u"tag": u"VII.1"}, {u"tags": [u"VII.2", None]}]},
                             {u"blocks": [{u"tag": u" VII.3 "}]}]},
                ensure_ascii=False), u"\n")
            self.assertEqual(rf.contract_tags(os.path.join(root, u"_extract"), u"7"),
                             {u"VII.1", u"VII.2", u"VII.3"})
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
