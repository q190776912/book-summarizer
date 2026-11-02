# -*- coding: utf-8 -*-
"""test_sync_delivery_from_units.py — `tools/sync_delivery_from_units.py`：交付复位成 merge(units)。

这一格补的是「单元↔交付」2×2 里以前**没有合法出口**的那一格：
  * `mirror_unit_line` = 单元→交付，**一行**（要求整块除一行外逐行相等）；
  * `sync_unit_from_delivery` = 交付→单元，**整块**；
  * 本工具 = 单元→交付，**整章 / 整节文件集**（移动形 / 围栏形 / 多段差异）。
2026-10-31 数值分析 ch1 实测：幻影 `\\tag{2.3}` 从「不编号的对齐块」搬到 `\\varepsilon(A^*)`
展示块 = 一次删除 + 一次插入，`mirror_unit_line` 结构上量不到（「最好偏移仍差 14 行」），
违规重 merge 又是收官书死规则禁止的 ⇒ 只有本工具能落。

🔴 本工具不判断真值方向（它只保证「交付 == merge(units)」），所以测试要盯的是**边界**：
dry-run 零写入、写盘只动差异段、**按节拆分形态**（工厂拆分器 + 文件名精确配对）、
文件名对不上即拒、合并件与节件混放即拒、删掉后 **src 消失**的图拒（只换 `> ` 围栏放行）、
换行风格守恒、F 层围栏回归守卫（净增违规即拒、既有违规不误伤）、
幂等、门控失败不得写盘、写后逐字节复核。

夹具做法：先用拼接器自己算出「应有形」（`_assemble(require_gate=False)`），再在它上面造
**已知**缺陷当交付 —— 这样断言不依赖拼接器的归一化细节（空行 / `---` / I 层补线）。
"""
import importlib.util
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
sys.path.insert(0, os.path.join(_ROOT, "flows/write-source/script"))
import merge_units as _mu  # noqa: E402

_SPEC = importlib.util.spec_from_file_location(
    "sync_delivery_from_units",
    os.path.join(_ROOT, "tools", "sync_delivery_from_units.py"))
sd = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(sd)

MARK = "<!-- book-summarizer DONE unit: id=0005 type=item key=例1 name=N -->"
IMG = '<img src="figures/ch6_f1.png" width="60%">'
BODY = ["**例1 求解线性方程组**：",
        "$$",
        "\\begin{aligned} x_1 &= 2 \\\\",
        "\\tag{2.3}",
        "$$",
        "于是 $x_1=2$。"]

# F 层判据样本：`> ` 落在 `$$…$$` 围栏内 ⇒ check_displaymath_gt 命中
BQ_MATH = ["$$", "> 围栏里的块引用", "$$", "于是 $x=1$。"]

# I 层判据样本（Fraleigh ch25 实测形态）：`> **Example…**` 块结束后紧跟**顶层散文**，
# 中间必须有一条 `---`（writing-rules V-F）。单元拼接侧给不出这一条——块尾与散文分属
# 两个单元，`_assemble` 的状态机对 `desc` 只在 `prev == "item"` 时补线 ⇒ 复位会把交付
# 里**已有且必需**的 `---` 删掉，前五档围栏判据对此完全量不到。
PROSE_SEP = ["> **Example 25.1.** 求逆矩阵：",
             "> 先把矩阵化成行阶梯形。",
             "",
             "于是 $x=1$。"]


def _write(path, text, eol="\n"):
    d = os.path.dirname(path)
    if not os.path.isdir(d):
        os.makedirs(d)
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text.replace("\n", eol))


def _tree(unit_body=None, eol="\n", md_name=u"第6章_迭代法.md", merge_false=False):
    """最小书树：`<root>/_extract/book_structure/units/ch6/{manifest.json,0005_item_例1.md}`
    + `<root>/<md_name>`（内容 = 拼接器应有形）。→ (root, ext, md_path, splice_text)"""
    root = tempfile.mkdtemp(prefix="sdfu_")
    ext = os.path.join(root, u"_extract")
    udir = os.path.join(ext, "book_structure", "units", "ch6")
    _write(os.path.join(udir, u"0005_item_例1.md"),
           "\n".join([MARK] + (unit_body if unit_body is not None else BODY)) + "\n", eol)
    units = [{u"id": u"0005", u"file": u"0005_item_例1.md",
              u"type": u"item", u"key": u"例1", u"name": u"N"}]
    if merge_false:
        units.append({u"id": u"0006", u"file": u"0006_item_例2.md",
                      u"type": u"item", u"key": u"例2", u"name": u"N",
                      u"merge": False})
        _write(os.path.join(udir, u"0006_item_例2.md"),
               MARK.replace("0005", "0006").replace(u"例1", u"例2")
               + "\n**例2 不进交付**：\n\n这一段只在单元层保留。\n", eol)
    man = {u"chapter_key": u"6", u"language": u"cn", u"final_md": md_name,
           u"units": units}
    _write(os.path.join(udir, "manifest.json"),
           json.dumps(man, ensure_ascii=False, indent=2) + "\n", eol)
    lines, _owners = _mu._assemble(ext, 6, "units", clean_cjk=None, require_gate=False)
    splice = "\n".join(lines).rstrip() + "\n"
    md = os.path.join(root, md_name)
    _write(md, splice, eol)
    return root, ext, md, splice


def _read(path):
    with io.open(path, encoding="utf-8", newline="") as f:
        return f.read()


SEC1 = u"## § 6.1 迭代"
SEC2 = u"## § 6.2 收敛"
SEC1_MD = u"第6章_6.1_迭代.md"
SEC2_MD = u"第6章_6.2_收敛.md"
# 工厂拆分器的产出（split_one_file 把节界前的 `---` 留在上一节末尾）
SEC1_EXPECT = (u"## § 6.1 迭代\n\n**例1 求解**：\n\n$$\nx=1\n$$\n\n---\n")
SEC2_EXPECT = (u"## § 6.2 收敛\n\n**例2 收敛**：\n\n$$\ny=2\n$$\n")


def _split_tree(eol="\n", with_merged=False):
    """按节拆分形态的最小书树：两节两段单元 + 两件节文件交付。

    → (root, ext, {节文件名: 路径}, 期望文本 {节文件名: 文本})
    """
    root = tempfile.mkdtemp(prefix="sdfu_split_")
    ext = os.path.join(root, u"_extract")
    udir = os.path.join(ext, "book_structure", "units", "ch6")
    units = [
        (u"0002_section_6_1.md", u"section", u"6.1", [SEC1]),
        (u"0003_desc_D1.md", u"desc", u"D1", [u"**例1 求解**：", u"", u"$$", u"x=1", u"$$"]),
        (u"0004_section_6_2.md", u"section", u"6.2", [SEC2]),
        (u"0005_desc_D2.md", u"desc", u"D2", [u"**例2 收敛**：", u"", u"$$", u"y=2", u"$$"]),
    ]
    man_units = []
    for fn, utype, key, body in units:
        mark = (u"<!-- book-summarizer DONE unit: id=%s type=%s key=%s name= -->"
                % (fn[:4], utype, key))
        _write(os.path.join(udir, fn), u"\n".join([mark] + body) + u"\n", eol)
        man_units.append({u"id": fn[:4], u"file": fn, u"type": utype,
                          u"key": key, u"name": u""})
    _write(os.path.join(udir, "manifest.json"),
           json.dumps({u"chapter_key": u"6", u"language": u"cn",
                       u"final_md": u"第6章_迭代法.md", u"units": man_units},
                      ensure_ascii=False, indent=2) + u"\n", eol)
    paths = {SEC1_MD: os.path.join(root, SEC1_MD),
             SEC2_MD: os.path.join(root, SEC2_MD)}
    expect = {SEC1_MD: SEC1_EXPECT, SEC2_MD: SEC2_EXPECT}
    for name, text in expect.items():
        _write(paths[name], text, eol)
    if with_merged:
        _write(os.path.join(root, u"第6章_迭代法.md"),
               u"".join(expect.values()), eol)
    return root, ext, paths, expect


def _snap(root):
    """目录快照 {相对路径: 字节}，用于「零写入」断言。"""
    out = {}
    for base, _dirs, files in os.walk(root):
        for n in files:
            p = os.path.join(base, n)
            with io.open(p, "rb") as f:
                out[os.path.relpath(p, root)] = f.read()
    return out


_OUTPUT = []          # 每次 _run 吞下的工具打印，供人读输出断言用


def _run(ext, root, commit=False, backup_dir=None, require_gate=False, ch=6):
    """跑一次复位，吞掉工具自己的差异段打印（人读输出，不是断言对象）。"""
    buf = io.StringIO()
    with redirect_stdout(buf):
        st, note = sd.sync_chapter(ext, ch, root, "units",
                                   require_gate=require_gate, commit=commit,
                                   backup_dir=backup_dir)
    _OUTPUT.append(buf.getvalue())
    return st, note


class TestPositive(unittest.TestCase):
    def tearDown(self):
        import gc
        gc.collect()

    def test_same_when_delivery_already_matches(self):
        root, ext, md, splice = _tree()
        try:
            st, note = _run(ext, root)
            self.assertEqual(st, "SAME")
            self.assertEqual(_read(md).replace("\r\n", "\n"), splice)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_dry_run_writes_nothing(self):
        root, ext, md, splice = _tree()
        try:
            bad = splice.replace("\\tag{2.3}\n", "") + "\n尾巴\n"
            _write(md, bad, "\n")
            before = _snap(root)
            st, _note = _run(ext, root)
            self.assertEqual(st, "DIFF")
            self.assertEqual(_snap(root), before, "dry-run 动了磁盘")
            self.assertFalse(os.path.exists(os.path.join(ext, sd.LEDGER)))
            out = _OUTPUT[-1]
            self.assertIn(u"0005_item_例1.md", out, "人读输出须点名归属单元")
            self.assertIn("尾巴", out, "人读输出须打印被删的交付行")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_commit_makes_delivery_identical_and_ledgers(self):
        root, ext, md, splice = _tree()
        bdir = os.path.join(root, "_bak")
        try:
            _write(md, splice.replace("\\tag{2.3}\n", ""), "\n")
            st, _note = _run(ext, root, commit=True, backup_dir=bdir)
            self.assertEqual(st, "WRITTEN")
            self.assertEqual(_read(md).replace("\r\n", "\n"), splice)
            rec = json.loads(_read(os.path.join(ext, sd.LEDGER)).strip())
            self.assertEqual(rec["removed"], 0)
            self.assertEqual(rec["added"], 1)
            self.assertEqual(rec["side"], "units")
            baks = [os.path.join(b, n) for b, _d, fs in os.walk(bdir)
                    for n in fs]
            self.assertEqual(len(baks), 1)
            self.assertNotEqual(_read(baks[0]).replace("\r\n", "\n"), splice,
                                "备份件应是改前的字节，不是改后")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_second_run_is_idempotent(self):
        root, ext, md, splice = _tree()
        try:
            _write(md, splice.replace("\\tag{2.3}\n", ""), "\n")
            self.assertEqual(_run(ext, root, commit=True)[0], "WRITTEN")
            snap = _snap(root)
            self.assertEqual(_run(ext, root, commit=True)[0], "SAME")
            self.assertEqual(_snap(root), snap, "幂等复跑动了磁盘")
            self.assertEqual(_read(os.path.join(ext, sd.LEDGER)).count("\n"), 1,
                             "SAME 不该再落账")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_move_shape_reports_two_hunks_with_owner(self):
        """幻影 tag 搬块（一次删除 + 一次插入）= mirror_unit_line 结构上拒改的那一格。"""
        root, ext, md, splice = _tree()
        try:
            moved = splice.replace("\\tag{2.3}\n$$", "$$\n\\tag{2.3}")
            self.assertNotEqual(moved, splice, "夹具没造出移动形")
            _write(md, moved, "\n")
            st, _note = _run(ext, root)
            self.assertEqual(st, "DIFF")
            hs = sd.hunks(moved.split("\n"), splice.split("\n"),
                          [u"0005_item_例1.md"] * len(splice.split("\n")))
            self.assertEqual(sorted(h["op"] for h in hs), ["delete", "insert"],
                             "移动形须拆成一段删 + 一段插（difflib 决定先后）")
            self.assertEqual({tuple(h["delivery"]) for h in hs if h["op"] == "delete"},
                             {(u"\\tag{2.3}",)})
            self.assertEqual({tuple(h["resplice"]) for h in hs if h["op"] == "insert"},
                             {(u"\\tag{2.3}",)})
            ins = [h for h in hs if h["op"] == "insert"][0]
            dele = [h for h in hs if h["op"] == "delete"][0]
            self.assertEqual(ins["units"], [u"0005_item_例1.md"],
                             "拼接侧行须报归属单元，供人工核真值方向")
            wrong = moved.split("\n").index(u"\\tag{2.3}") + 1
            self.assertEqual(dele["where"], u"交付 L%d-%d" % (wrong, wrong),
                             "删除段须点名交付里那行幻影 tag 的位置")
            self.assertNotEqual(ins["delivery_lines"], dele["delivery_lines"],
                                "插入与删除须落在不同位置，否则不叫「搬块」")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_newline_style_preserved(self):
        for eol in ("\n", "\r\n"):
            root, ext, md, splice = _tree(eol=eol)
            try:
                _write(md, splice.replace("\\tag{2.3}\n", ""), eol)
                st, _n = _run(ext, root, commit=True)
                self.assertEqual(st, "WRITTEN")
                raw = _read(md)
                self.assertEqual(raw.replace("\r\n", "\n"), splice)
                if eol == "\r\n":
                    self.assertEqual(raw.count("\r\n"), raw.count("\n"),
                                     "CRLF 交付被写成混合换行")
                else:
                    self.assertNotIn("\r", raw, "LF 交付被翻成 CRLF")
            finally:
                shutil.rmtree(root, ignore_errors=True)

    def test_merge_false_unit_stays_out_of_delivery(self):
        """`merge:false`（V-I 集中习题块）：复位不得把它印进交付。"""
        root, ext, md, splice = _tree(merge_false=True)
        try:
            self.assertNotIn(u"不进交付", _read(md))
            _write(md, splice.replace("\\tag{2.3}\n", ""), "\n")
            st, _n = _run(ext, root, commit=True)
            self.assertEqual(st, "WRITTEN")
            self.assertEqual(_read(md).replace("\r\n", "\n"), splice)
            self.assertNotIn(u"不进交付", _read(md))
        finally:
            shutil.rmtree(root, ignore_errors=True)


class TestRefusals(unittest.TestCase):
    def test_refuse_split_form_delivery(self):
        """拆分件名与工厂拆分产物对不上 ⇒ 拒（绝不猜名/改名）。"""
        root, ext, md, splice = _tree()
        try:
            os.remove(md)
            _write(os.path.join(root, u"第6章_6.1_迭代.md"), splice, "\n")
            _write(os.path.join(root, u"第6章_6.2_收敛.md"), splice, "\n")
            before = _snap(root)
            st, note = _run(ext, root, commit=True)
            self.assertEqual(st, "REFUSE")
            self.assertIn("文件名对不上", note)
            self.assertEqual(_snap(root), before, "拆分形态拒绝时动了磁盘")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_refuse_when_delivery_missing(self):
        root, ext, md, splice = _tree()
        try:
            os.remove(md)
            st, note = _run(ext, root, commit=True)
            self.assertEqual(st, "REFUSE")
            self.assertIn("找不到交付", note)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_refuse_when_manifest_missing(self):
        root, ext, md, splice = _tree()
        try:
            os.remove(os.path.join(ext, "book_structure", "units", "ch6",
                                   "manifest.json"))
            st, note = _run(ext, root, commit=True)
            self.assertEqual(st, "REFUSE")
            self.assertIn("manifest.json", note)
            self.assertEqual(_read(md).replace("\r\n", "\n"), splice)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_refuse_removing_injected_img(self):
        """拼接器注入的 `<img>` 在单元侧不存在 ⇒ 覆写会真丢图。"""
        root, ext, md, splice = _tree()
        try:
            _write(md, splice.replace("于是 $x_1=2$。", IMG + "\n\n于是 $x_1=2$。"),
                   "\n")
            before = _snap(root)
            st, note = _run(ext, root, commit=True)
            self.assertEqual(st, "REFUSE")
            self.assertIn("figures/ch6_f1.png", note)
            self.assertEqual(_snap(root), before, "img 拒绝路径动了磁盘")
            self.assertFalse(os.path.exists(os.path.join(ext, sd.LEDGER)))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_allow_img_only_rewrapped(self):
        """同一张图只是被 `> ` 块引用围栏重新包裹（src 不变）⇒ 放行。

        旧闸按「被删的交付行里出现 `<img`」拒，于是「单元侧补围栏」这一类账永远复位不了；
        现在按 src 多重集比，图真丢才拒。
        """
        body = BODY[:5] + [IMG] + [""] + BODY[5:]
        root, ext, md, splice = _tree(unit_body=body)
        try:
            self.assertIn(IMG, splice)
            _write(md, splice.replace(IMG, "> " + IMG), "\n")
            self.assertNotEqual(_read(md), splice)
            st, note = _run(ext, root, commit=True)
            self.assertEqual(st, "WRITTEN", note)
            self.assertEqual(_read(md), splice, "复位后交付应 == 拼接产物")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_gate_failure_writes_nothing(self):
        """默认强制门控：单元首行不是 DONE ⇒ 拒绝拼接，交付一个字节都不许变。"""
        root, ext, md, splice = _tree(unit_body=[l for l in BODY])
        try:
            _write(os.path.join(ext, "book_structure", "units", "ch6",
                                u"0005_item_例1.md"),
                   "\n".join([MARK.replace("DONE", "TODO")] + BODY) + "\n", "\n")
            _write(md, splice.replace("\\tag{2.3}\n", ""), "\n")
            before = _snap(root)
            with self.assertRaises(SystemExit):
                _run(ext, root, commit=True, require_gate=True)
            self.assertEqual(_snap(root), before, "门控失败时动了磁盘")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_post_write_mismatch_is_reported(self):
        """写后逐字节复核：落盘字节与拼接产物不符 ⇒ REFUSE（备份仍在）。

        用 `_Tamper` 包住**工具自己**用的 open（工具走 `sd.io.open`，故只在本用例内把
        `sd.io` 换成一个代理模块对象，不碰全局 `io`）：写模式时偷偷多落一个空行。
        """
        root, ext, md, splice = _tree()
        real_io = sd.io

        class _Proxy(object):
            def __init__(self, mod):
                self._m = mod

            def open(self, path, mode="r", *a, **kw):
                f = self._m.open(path, mode, *a, **kw)
                if "w" not in mode:
                    return f
                orig = f.write

                def write(s, _f=f):
                    orig(s)
                    orig("\n")     # 制造「落盘 != 拼接产物」
                f.write = write
                return f

        try:
            _write(md, splice.replace("\\tag{2.3}\n", ""), "\n")
            sd.io = _Proxy(real_io)
            try:
                st, note = _run(ext, root, commit=True)
            finally:
                sd.io = real_io
            self.assertEqual(st, "REFUSE")
            self.assertIn("写后逐字节复核不等", note)
        finally:
            shutil.rmtree(root, ignore_errors=True)


class TestFGuard(unittest.TestCase):
    """F 层围栏回归守卫：新拼接侧**净增**违规即拒；既有违规不许误伤。"""

    def test_blocks_new_f_violation(self):
        """新拼接侧把 `> ` 引进 `$$…$$` 围栏 ⇒ REFUSE，交付一个字节都不许变。"""
        root, ext, md, splice = _tree(unit_body=BQ_MATH)
        try:
            self.assertIn("> 围栏里的块引用", splice)
            _write(md, splice.replace("> 围栏里的块引用\n", ""), "\n")
            before = _snap(root)
            st, note = _run(ext, root, commit=True)
            self.assertEqual(st, "REFUSE", note)
            self.assertIn("F 层围栏回归守卫", note)
            self.assertEqual(_snap(root), before, "F 层守卫拦下时动了磁盘")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_allows_preexisting_violation(self):
        """旧交付与新拼接侧**同样**带那处违规 ⇒ 不是净增，放行写盘。"""
        root, ext, md, splice = _tree(unit_body=BQ_MATH)
        try:
            _write(md, splice.replace("于是 $x=1$。", u"于是 $x=1$。\n\n补一句。"), "\n")
            st, note = _run(ext, root, commit=True)
            self.assertEqual(st, "WRITTEN", note)
            self.assertEqual(_read(md).replace("\r\n", "\n"), splice)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_blocks_removed_prose_separator(self):
        """🔴 I 层回归（Fraleigh ch25 实测）：拼接侧给不出「`>` 块 → 顶层散文」之间的
        `---`，复位若把交付里**必需**的分隔线当噪声删掉 ⇒ REFUSE，交付一个字节都不许变。

        这一档前五判据（全是围栏 `>` 判据）看不见，单元层 gate 也看不见（块尾与散文分属
        两个单元文件），当时以「46 章 WRITTEN + 幂等 SAME」全绿通过、事后整书 verify 才报
        `F:2` rc=1 ⇒ 守卫必须自己拦，不能靠事后 verify。
        """
        root, ext, md, splice = _tree(unit_body=PROSE_SEP)
        try:
            self.assertNotIn("---", splice, "拼接侧本就没有分隔线（本用例的前提）")
            good = splice.replace("\n于是 $x=1$。", "\n---\n\n于是 $x=1$。")
            self.assertNotEqual(good, splice, "用例没能在散文前插入分隔线")
            _write(md, good, "\n")
            before = _snap(root)
            st, note = _run(ext, root, commit=True)
            self.assertEqual(st, "REFUSE", note)
            self.assertIn("F 层围栏回归守卫", note)
            self.assertIn("check_i_prose_separator", note)
            self.assertEqual(_snap(root), before, "I 层守卫拦下时动了磁盘")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_allows_preexisting_missing_separator(self):
        """对照：两侧**同样**缺那条 `---` ⇒ 不是净增，第 6 档不许把复位一刀切拒掉。"""
        root, ext, md, splice = _tree(unit_body=PROSE_SEP)
        try:
            _write(md, splice + u"\n补一句。\n", "\n")
            st, note = _run(ext, root, commit=True)
            self.assertEqual(st, "WRITTEN", note)
            self.assertEqual(_read(md).replace("\r\n", "\n"), splice)
        finally:
            shutil.rmtree(root, ignore_errors=True)


class TestSplitForm(unittest.TestCase):
    """按节拆分形态的交付复位（工厂拆分器 + 文件名精确配对）。"""

    def test_same_when_delivery_matches(self):
        root, ext, paths, expect = _split_tree()
        try:
            st, _note = _run(ext, root)
            self.assertEqual(st, "SAME")
            for name, p in paths.items():
                self.assertEqual(_read(p).replace("\r\n", "\n"), expect[name])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_dry_run_writes_nothing(self):
        root, ext, paths, expect = _split_tree()
        try:
            _write(paths[SEC2_MD], expect[SEC2_MD].replace("y=2", "y=3"), "\n")
            before = _snap(root)
            st, _note = _run(ext, root)
            self.assertEqual(st, "DIFF")
            self.assertEqual(_snap(root), before, "dry-run 动了磁盘")
            self.assertFalse(os.path.exists(os.path.join(ext, sd.LEDGER)))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_commit_restores_section_and_ledgers(self):
        root, ext, paths, expect = _split_tree()
        bdir = os.path.join(root, "_bak")
        try:
            _write(paths[SEC2_MD], expect[SEC2_MD].replace("y=2", "y=3"), "\n")
            st, note = _run(ext, root, commit=True, backup_dir=bdir)
            self.assertEqual(st, "WRITTEN", note)
            for name, p in paths.items():
                self.assertEqual(_read(p).replace("\r\n", "\n"), expect[name])
            recs = [json.loads(l) for l in
                    _read(os.path.join(ext, sd.LEDGER)).strip().split("\n")]
            self.assertEqual(len(recs), 1, "只改了一节 ⇒ 只落一行账")
            self.assertEqual(recs[0]["md"], SEC2_MD)
            self.assertEqual(recs[0]["form"], "split")
            baks = [os.path.join(b, n) for b, _d, fs in os.walk(bdir) for n in fs]
            self.assertEqual(len(baks), 1)
            self.assertIn("y=3", _read(baks[0]), "备份件应是改前的字节")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_newline_style_preserved_per_file(self):
        for eol in ("\n", "\r\n"):
            root, ext, paths, expect = _split_tree(eol=eol)
            try:
                _write(paths[SEC2_MD], expect[SEC2_MD].replace("y=2", "y=3"), eol)
                st, note = _run(ext, root, commit=True)
                self.assertEqual(st, "WRITTEN", note)
                raw = _read(paths[SEC2_MD])
                self.assertEqual(raw.replace("\r\n", "\n"), expect[SEC2_MD])
                if eol == "\r\n":
                    self.assertEqual(raw.count("\r\n"), raw.count("\n"))
                else:
                    self.assertNotIn("\r", raw)
            finally:
                shutil.rmtree(root, ignore_errors=True)

    def test_refuse_when_section_name_mismatch(self):
        """节文件被改名 ⇒ 与工厂拆分产物对不上 ⇒ 拒（不猜名、不改名）。"""
        root, ext, paths, expect = _split_tree()
        try:
            os.remove(paths[SEC2_MD])
            other = os.path.join(root, u"第6章_6.2_收敛改名.md")
            _write(other, expect[SEC2_MD], "\n")
            before = _snap(root)
            st, note = _run(ext, root, commit=True)
            self.assertEqual(st, "REFUSE")
            self.assertIn("文件名对不上", note)
            self.assertEqual(_snap(root), before, "改名拒绝时动了磁盘")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_refuse_when_merged_and_split_coexist(self):
        """合并件与节件混放 ⇒ 形态不唯一，拒。"""
        root, ext, paths, expect = _split_tree(with_merged=True)
        try:
            before = _snap(root)
            st, note = _run(ext, root, commit=True)
            self.assertEqual(st, "REFUSE")
            self.assertIn("形态不唯一", note)
            self.assertEqual(_snap(root), before, "混放拒绝时动了磁盘")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_second_run_is_idempotent(self):
        root, ext, paths, expect = _split_tree()
        try:
            _write(paths[SEC2_MD], expect[SEC2_MD].replace("y=2", "y=3"), "\n")
            self.assertEqual(_run(ext, root, commit=True)[0], "WRITTEN")
            snap = _snap(root)
            self.assertEqual(_run(ext, root, commit=True)[0], "SAME")
            self.assertEqual(_snap(root), snap, "幂等复跑动了磁盘")
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
