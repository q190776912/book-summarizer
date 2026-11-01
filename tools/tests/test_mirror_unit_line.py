# -*- coding: utf-8 -*-
"""test_mirror_unit_line.py — `tools/mirror_unit_line.py`：单元单行 → 交付 md 单行镜像。

场景：已收官书禁重 merge，但交付 md 的**一行**与单元正文脱钩（U 层报「正文读不到」）。
合法出口 = 只改那一行；工具必须拒绝一切「多处差异 / 位置歧义 / 短块猜位置」。

正向：dry-run 零写入；--commit 后**只有**目标行变，其余每行逐字节相同，行数与换行风格
守恒，备份件 = 原始字节，单元文件不动，复核归零，重跑为「已一致」（幂等）。
负向：①同一行差段不止一处 → 拒；②交付里有同形块（两个偏移都只差一行）→ 拒；
③正文整块读不到 → 拒；④相等行不足 → 拒；⑤manifest 无 language → 不猜交付文件（SystemExit）；
六种拒绝路径都必须磁盘零改动。

``--delete-line``（单元侧整行删过 ``\\tag``，交付要跟着少一行）：正向删**唯一**的那一行、
行数 −1、其余逐字节不变、幂等；负向 = 两处都多一行（位置歧义）→ 拒；「单元全部匹配后
交付还剩一行」**不得**当成待删行（那是下一块的开头）；待删文本与取证不符 → :func:`apply_delete`
自拒。一个单元摘掉**两行**独占 ``\\tag`` 时逐趟重跑同一条判据（正：少两行且只少那两行；
负：两行挤同一块 = 位置证据断了 → 拒；待删行数超过上限 → 整条拒、零写入）。

``--delete-blank-line`` 是同一条走查换形状档（交付多的是「整行只剩块引用围栏」的空行，
2026-10-31 Gelfand–Manin 实测 4 处）：正：只少那一行且删完与单元逐行相等；负：**默认档必须
照旧拒**（A/B 对照，证明新档没有顺手放宽 tag 路径）、多出的行是内容行 → 拒。

``--fill-tag-line`` 是反方向（单元有独占 ``\\tag``、交付那个位置只剩一个空行）：正：把单元
那一行**填进**空行、行数守恒、幂等；负：那个位置没有空行（真要插行）→ 拒；空行不止一个 →
拒；单元多出的行不是独占 ``\\tag`` → 拒；两处块都缺 → 位置不唯一 → 拒。
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

_SPEC = importlib.util.spec_from_file_location(
    "mirror_unit_line", os.path.join(_ROOT, "tools", "mirror_unit_line.py"))
mul = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mul)

MARK = "<!-- book-summarizer DONE unit: id=0005 type=item key=例1 name=N -->"
BODY = [u"**例1 求解线性方程组**：",
        u"$$",
        u"\\begin{cases} 8x_1 - 3x_2 = 20 \\end{cases}",
        u"$$"]
MATH = u"\\begin{cases} 8x_1 - 3x_2 = 20 \\end{cases}"


def _write(path, lines, eol):
    if not os.path.isdir(os.path.dirname(path)):
        os.makedirs(os.path.dirname(path))
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write(eol.join(lines))


def _tree(md_lines, unit_body=None, eol="\r\n", lang="cn", md_name=u"第6章_迭代法.md"):
    """造一棵最小书树：`<root>/_extract/book_structure/units/ch6/{manifest.json,0005_item_例1.md}`
    + `<root>/第6章_迭代法.md`（真实 CRLF 形态）。"""
    root = tempfile.mkdtemp()
    ext = os.path.join(root, u"_extract")
    udir = os.path.join(ext, u"book_structure", u"units", u"ch6")
    _write(os.path.join(udir, u"0005_item_例1.md"),
           [MARK] + (unit_body if unit_body is not None else BODY), eol)
    man = {u"chapter_key": u"6", u"language": lang, u"final_md": u"",
           u"units": [{u"id": u"0005", u"file": u"0005_item_例1.md",
                       u"type": u"item", u"key": u"例1", u"name": u"N"}]}
    _write(os.path.join(udir, u"manifest.json"),
           json.dumps(man, ensure_ascii=False, indent=2).split(u"\n"), eol)
    md = os.path.join(root, md_name)
    _write(md, md_lines, eol)
    return root, ext, udir, md


def _drifted():
    """交付侧 = 单元首行被多插一个 `：`（实测形态），其余行逐字相同。"""
    return [u"# 第6章 迭代法", u"",
            u"**例1：求解线性方程组**：",            # ← 漂移行
            u"", u"$$", MATH, u"$$",
            u"", u"下一段正文"]


def _norm_body():
    return [u"# 第6章 迭代法", u"",
            u"**例1 求解线性方程组**：",
            u"", u"$$", MATH, u"$$",
            u"", u"下一段正文"]


def _run(ext, ch, files, commit=False, book=None, delete_line=False, delete_tag=None,
         multi_hunk=False, fill_tag_line=False, delete_blank_line=False):
    argv = [ext, ch] + files
    if book:
        argv += [u"--book-dir", book]
    if commit:
        argv.append(u"--commit")
    if delete_line:
        argv.append(u"--delete-line")
    if delete_blank_line:
        argv.append(u"--delete-blank-line")
    if fill_tag_line:
        argv.append(u"--fill-tag-line")
    if multi_hunk:
        argv.append(u"--multi-hunk")
    for n in (delete_tag or []):
        argv += [u"--delete-tag-line", n]
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = mul.main(argv)
    return rc, buf.getvalue()


def _ledger(ext, ch, nums):
    """写一条 `deregister_formula_tags` 同形的摘除台账（只填本模式会读的两列）。"""
    p = os.path.join(ext, u"_formula_tag_deregistrations.jsonl")
    with io.open(p, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps({u"ts": u"2026-10-31T13:00:00", u"ch_key": str(ch),
                             u"numbers": list(nums), u"mode": u"false-anchor"},
                           ensure_ascii=False) + u"\n")
    return p


class MirrorUnitLine(unittest.TestCase):
    def tearDown(self):
        for d in getattr(self, "_dirs", []):
            shutil.rmtree(d, ignore_errors=True)

    def _tree(self, *a, **kw):
        t = _tree(*a, **kw)
        self.__dict__.setdefault("_dirs", []).append(t[0])
        return t

    # ---- 正向 ----
    def test_dry_run_writes_nothing(self):
        root, ext, udir, md = self._tree(_drifted())
        before = open(md, "rb").read()
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"])
        self.assertEqual(rc, 0)
        self.assertIn(u"拟改", out)
        self.assertEqual(open(md, "rb").read(), before)          # 零写入
        self.assertFalse(os.path.isdir(os.path.join(ext, u"_bak_mirror_unit_line")))

    def test_commit_touches_only_that_line_and_idempotent(self):
        root, ext, udir, md = self._tree(_drifted())
        before_raw = open(md, "rb").read()
        unit_before = open(os.path.join(udir, u"0005_item_例1.md"), "rb").read()
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"], commit=True)
        self.assertEqual(rc, 0, out)
        self.assertIn(u"已改", out)
        after_raw = open(md, "rb").read()
        bl = before_raw.decode(u"utf-8").split(u"\r\n")
        al = after_raw.decode(u"utf-8").split(u"\r\n")
        self.assertEqual(len(bl), len(al))                       # 行数守恒
        self.assertEqual([i for i in range(len(bl)) if bl[i] != al[i]], [2])
        self.assertEqual(al[2], u"**例1 求解线性方程组**：")       # = 单元那一行
        self.assertIn(b"\r\n", after_raw)                        # 换行风格守恒
        # 备份 = 原始字节（先备份后写）
        bakdir = os.path.join(ext, u"_bak_mirror_unit_line")
        baks = [os.path.join(bakdir, d, u"第6章_迭代法.md")
                for d in os.listdir(bakdir)]
        self.assertEqual(len(baks), 1)
        self.assertEqual(open(baks[0], "rb").read(), before_raw)
        # 单元文件一概不动
        self.assertEqual(open(os.path.join(udir, u"0005_item_例1.md"), "rb").read(),
                         unit_before)
        # 幂等：再跑一次 = 已一致，且不再写
        mid = open(md, "rb").read()
        rc2, out2 = _run(ext, u"6", [u"0005_item_例1.md"], commit=True)
        self.assertEqual(rc2, 0)
        self.assertIn(u"已一致", out2)
        self.assertEqual(open(md, "rb").read(), mid)
        self.assertEqual(len(os.listdir(bakdir)), 1)             # 没多出第二份备份

    def test_lf_file_stays_lf(self):
        root, ext, udir, md = self._tree(_drifted(), eol="\n")
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"], commit=True)
        self.assertEqual(rc, 0, out)
        raw = open(md, "rb").read()
        self.assertNotIn(b"\r", raw)
        self.assertEqual(raw.decode(u"utf-8").split(u"\n")[2], u"**例1 求解线性方程组**：")

    def test_unit_blank_lines_do_not_break_alignment(self):
        """单元块**内部**有空行、交付做过 V-A 空行整理把那些空行吃掉 → 仍须认成「只差一行」。

        变异对照：对齐若按单元原始行号走步长（每多一个空行就多算一处 mismatch），
        这条会掉进「拿不到「只差一行」的对齐」——2026-10-30 数值分析首跑 50 条里
        32 条就是这样被假拒的（含 5 条只差条头数字的行），所以按「两侧都压空行」打分。
        """
        body = [u"**例1 求解线性方程组**：", u"", u"$$", u"", MATH, u"$$"]
        root, ext, udir, md = self._tree(_drifted(), unit_body=body)
        before = open(md, "rb").read()
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"])
        self.assertEqual(rc, 0, out)
        self.assertIn(u"拟改", out)
        self.assertEqual(open(md, "rb").read(), before)           # dry-run 仍零写入
        rc2, out2 = _run(ext, u"6", [u"0005_item_例1.md"], commit=True)
        self.assertEqual(rc2, 0, out2)
        self.assertEqual(open(md, "rb").read().decode(u"utf-8").split(u"\r\n")[2],
                         u"**例1 求解线性方程组**：")

    def test_separator_line_inside_block_still_aligns(self):
        """交付块内被拼接期插了 `---`（单元里没有那行）→ 分隔线不是正文，不得算成第二处差。

        变异对照：把 `---` 当正文行，本例会因位置整体位移而报「拿不到「只差一行」的对齐」，
        于是「条头多一个 `：`」这种真单行漂移永远修不了（2026-10-30 数值分析 ch7 例16）。
        """
        md = _drifted()
        md.insert(4, u"---")                       # 插在条头与 $$ 之间
        root, ext, udir, path = self._tree(md)
        before = open(path, "rb").read()
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"])
        self.assertEqual(rc, 0, out)
        self.assertIn(u"拟改", out)
        self.assertEqual(open(path, "rb").read(), before)
        rc2, out2 = _run(ext, u"6", [u"0005_item_例1.md"], commit=True)
        self.assertEqual(rc2, 0, out2)
        raw = open(path, "rb").read().decode(u"utf-8").split(u"\r\n")
        self.assertEqual(raw[2], u"**例1 求解线性方程组**：")
        self.assertEqual(raw[4], u"---")            # 分隔线原样留着，没被顺手动掉

    def test_two_line_block_pins_on_long_unique_line(self):
        """2 行正文的短块：漂移行之外只剩一行相等 → 该行够长且全篇唯一就应当可镜像。

        否则「只差一行」对短块结构性失效（数值分析 ch3 性质5 实测被这样拒掉）。
        变异对照：把那条长行在交付里**再印一遍**（不再唯一）→ 必须转拒（见负向用例）。
        """
        long_line = (u"若令 $\\widetilde{T}_0(x)=1$，则 $\\widetilde{T}_n(x)$ 是首项系数为 1 的"
                     u"（首一）切比雪夫多项式，记集合 $\\widetilde{H}_n$ 如下所述。")
        root, ext, udir, md = self._tree(
            [u"# 第6章 迭代法", u"", u"**例1：求解线性方程组**：", u"", long_line, u"",
             u"下一段正文"],
            unit_body=[u"**例1 求解线性方程组**：", u"", long_line])
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"], commit=True)
        self.assertEqual(rc, 0, out)
        self.assertIn(u"已改", out)
        raw = open(md, "rb").read().decode(u"utf-8").split(u"\r\n")
        self.assertEqual(raw[2], u"**例1 求解线性方程组**：")
        self.assertEqual(raw[4], long_line)                 # 那一行没被顺手动过

    def test_two_line_block_refuses_when_long_line_repeats(self):
        """同一行长在交付里出现两次 = 位置不唯一 → 短块也不能镜像（宁可拒）。"""
        long_line = (u"若令 $\\widetilde{T}_0(x)=1$，则 $\\widetilde{T}_n(x)$ 是首项系数为 1 的"
                     u"（首一）切比雪夫多项式，记集合 $\\widetilde{H}_n$ 如下所述。")
        root, ext, udir, md = self._tree(
            [u"# 第6章 迭代法", u"", long_line, u"", u"**例1：求解线性方程组**：", u"",
             long_line, u"", u"下一段正文"],
            unit_body=[u"**例1 求解线性方程组**：", u"", long_line])
        before = open(md, "rb").read()
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"], commit=True)
        self.assertEqual(rc, 1, out)
        self.assertEqual(open(md, "rb").read(), before)

    # ---- 负向：全部拒绝且磁盘零改动 ----
    def test_multi_op_line_refuses(self):
        md = _drifted()
        md[2] = u"**例1：求解线性方程组 ：**："                   # 与单元差两段
        root, ext, udir, path = self._tree(md)
        before = open(path, "rb").read()
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"], commit=True)
        self.assertEqual(rc, 1, out)
        self.assertIn(u"需人工逐字判", out)
        self.assertIn(u"--multi-hunk", out)                      # 处方要给出合法出口
        self.assertEqual(open(path, "rb").read(), before)

    def test_ambiguous_duplicate_block_refuses(self):
        """交付里有两处都能做到「只差一行」→ 位置不唯一，拒绝（不猜哪一处才是漂移）。"""
        md = _drifted()                                  # 第一处：条头行差
        md += [u"", u"**例1 求解线性方程组**：",           # 第二处：条头逐字对，数学行差
               u"", u"$$", MATH + u"，多了一段", u"$$"]
        root, ext, udir, path = self._tree(md)
        before = open(path, "rb").read()
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"], commit=True)
        self.assertEqual(rc, 1, out)
        self.assertIn(u"对齐不唯一", out)
        self.assertEqual(open(path, "rb").read(), before)

    def test_block_absent_refuses(self):
        """整块读不到（多行差）≠ 单行镜像的适用范围。"""
        md = [u"# 第6章 迭代法", u"", u"**例1：求解线性方程组**：", u"",
              u"$$", u"完全不同的正文 $$", u"还有一行"]
        root, ext, udir, path = self._tree(md)
        before = open(path, "rb").read()
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"], commit=True)
        self.assertEqual(rc, 1, out)
        self.assertIn(u"拿不到", out)
        self.assertEqual(open(path, "rb").read(), before)

    def test_short_block_needs_two_matching_lines(self):
        """只有一行相等不足以钉位置（= U 层「结构上量不到」那类短块）→ 拒绝。"""
        root, ext, udir, path = self._tree(
            [u"# 第6章", u"", u"**例1：求解线性方程组**：", u"", u"$$", u"", u"另一段"],
            unit_body=[u"**例1 求解线性方程组**：", u"$$"])
        before = open(path, "rb").read()
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"], commit=True)
        self.assertEqual(rc, 1, out)
        self.assertEqual(open(path, "rb").read(), before)

    def test_no_language_refuses_to_guess_md_side(self):
        root, ext, udir, path = self._tree(_drifted(), lang="")
        before = open(path, "rb").read()
        with self.assertRaises(SystemExit):
            _run(ext, u"6", [u"0005_item_例1.md"], commit=True)
        self.assertEqual(open(path, "rb").read(), before)

    def test_en_side_uses_chapter_file(self):
        """EN 侧单元 → 交付 = `ChapterN_*.md`（语种只认 manifest，不认文件名猜）。"""
        md = [u"# Chapter 6", u"", u"**Ex1：solve**：", u"", u"$$",
              u"abc", u"$$", u"", u"next"]
        root, ext, udir, path = self._tree(
            md, lang="en", unit_body=[u"**Ex1 solve**：", u"$$", u"abc", u"$$"],
            md_name=u"Chapter6_iter.md")
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"], commit=True)
        self.assertEqual(rc, 0, out)
        self.assertEqual(open(path, "rb").read().decode(u"utf-8").split(u"\r\n")[2],
                         u"**Ex1 solve**：")


class MirrorMultiHunk(unittest.TestCase):
    """``--multi-hunk``：同一行差**多段**（GM 2026-10-31 实测：一行里两处 `(1.1)` 回指）
    时的定点覆写口。它只放宽「一段」这一条，不放宽对齐唯一性与「只改这一行」。"""

    UNIT = u"关系 (I.1) 与 (I.1) 如前述："
    MD = u"关系 (1.1) 与 (1.1) 如前述："

    def tearDown(self):
        for d in getattr(self, "_dirs", []):
            shutil.rmtree(d, ignore_errors=True)

    def _tree(self, md_line=None):
        t = _tree([u"# 第6章 迭代法", u"", md_line if md_line else self.MD,
                   u"", u"$$", MATH, u"$$", u"", u"下一段正文"],
                  unit_body=[self.UNIT, u"$$", MATH, u"$$"])
        self.__dict__.setdefault("_dirs", []).append(t[0])
        return t

    def test_default_refuses_and_prints_every_segment(self):
        root, ext, udir, path = self._tree()
        before = open(path, "rb").read()
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"], commit=True)
        self.assertEqual(rc, 1, out)
        self.assertIn(u"差 2 段", out)
        self.assertEqual(out.count(u"replace"), 2, out)          # 两段都要摊开，不能只给第一段
        self.assertEqual(open(path, "rb").read(), before)

    def test_opt_in_replaces_the_whole_line(self):
        root, ext, udir, path = self._tree()
        before = open(path, "rb").read().decode("utf-8").split("\r\n")
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"], commit=True, multi_hunk=True)
        self.assertEqual(rc, 0, out)
        self.assertEqual(out.count(u"已改"), 2, out)
        after = open(path, "rb").read().decode("utf-8").split("\r\n")
        self.assertEqual(len(after), len(before))
        self.assertEqual([i for i in range(len(before)) if after[i] != before[i]], [2])
        self.assertEqual(after[2], self.UNIT)                    # 整行照单元覆写
        self.assertEqual(len(os.listdir(os.path.join(ext, u"_bak_mirror_unit_line"))), 1)

    def test_opt_in_is_idempotent(self):
        root, ext, udir, path = self._tree()
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"], commit=True, multi_hunk=True)
        self.assertEqual(rc, 0, out)
        mid = open(path, "rb").read()
        rc2, out2 = _run(ext, u"6", [u"0005_item_例1.md"], commit=True, multi_hunk=True)
        self.assertEqual(rc2, 0, out2)
        self.assertIn(u"已一致", out2)
        self.assertEqual(open(path, "rb").read(), mid)

    def test_opt_in_does_not_loosen_alignment(self):
        """整块拿不到「只差一行」时，加了 --multi-hunk 也照样拒（放宽的只是段数）。"""
        root, ext, udir, path = self._tree()
        md = open(path, "rb").read().decode("utf-8").split(u"\r\n")
        md[5] = u"\\begin{cases} 8x_1 - 3x_2 = 21 \\end{cases}"
        _write(path, md, u"\r\n")
        before = open(path, "rb").read()
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"], commit=True, multi_hunk=True)
        self.assertEqual(rc, 1, out)
        self.assertIn(u"拿不到", out)
        self.assertEqual(open(path, "rb").read(), before)


class MirrorDeleteLine(unittest.TestCase):
    """``--delete-line``：单元侧整行删过 ``\\tag``（deregister 工具的独占一行分支）后的交付镜像。"""

    MATH = u"\\lim_{n\\to\\infty}\\frac{1}{n}r(P(n))=0."
    UNIT = [u"$$", MATH, u"$$"]                       # 摘掉 \tag 之后的单元正文
    TAG = u"\\tag{6.2}"

    def tearDown(self):
        for d in getattr(self, "_dirs", []):
            shutil.rmtree(d, ignore_errors=True)

    def _tree(self, md_lines, **kw):
        t = _tree(md_lines, unit_body=self.UNIT, **kw)
        self.__dict__.setdefault("_dirs", []).append(t[0])
        return t

    def _md(self, tail=None):
        """带 \tag 的一块 + 一块**无 tag 的重复**display + 尾部正文（遍历论 D23 实测形态）。"""
        out = [u"# 第6章 变分原理", u"",
               u"$$", self.MATH, self.TAG, u"$$", u"",
               u"**引理6.6.2**：", u"", u"$$", self.MATH, u"$$", u"",
               u"下一段正文"]
        return out + (tail or [])

    def test_dry_run_writes_nothing(self):
        root, ext, udir, md = self._tree(self._md())
        before = open(md, "rb").read()
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"], delete_line=True)
        self.assertEqual(rc, 0, out)
        self.assertIn(u"拟删", out)
        self.assertEqual(open(md, "rb").read(), before)

    def test_commit_removes_exactly_that_line(self):
        root, ext, udir, md = self._tree(self._md())
        before = open(md, "rb").read().decode(u"utf-8").split(u"\r\n")
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"], commit=True, delete_line=True)
        self.assertEqual(rc, 0, out)
        self.assertIn(u"已删", out)
        after = open(md, "rb").read().decode(u"utf-8").split(u"\r\n")
        self.assertEqual(len(after), len(before) - 1)
        self.assertEqual(after, before[:4] + before[5:])   # 只少第 5 行（\tag{6.2}）
        self.assertNotIn(self.TAG, u"\n".join(after))
        # 幂等：再跑 = 已一致，磁盘与备份都不再动
        mid = open(md, "rb").read()
        bakdir = os.path.join(ext, u"_bak_mirror_unit_line")
        rc2, out2 = _run(ext, u"6", [u"0005_item_例1.md"], commit=True, delete_line=True)
        self.assertEqual(rc2, 0, out2)
        self.assertIn(u"已一致", out2)
        self.assertEqual(open(md, "rb").read(), mid)
        self.assertEqual(len(os.listdir(bakdir)), 1)

    def test_clean_tail_after_matched_block_is_not_the_target(self):
        """🔴 块在交付里印了两遍时，第一遍「单元全匹配 + 后面还有行」不得被当成待删行。

        变异对照：若接受「走查结束后剩下的第一行」为候选，干净的第一次出现会把**下一块的
        开头**（这里是 ``**引理6.6.2**：``）报成待删行，两处候选 → 位置歧义 → 整条拒改，
        而更坏的是只有一处出现时它会**静默删掉无辜的一行**（2026-10-30 遍历论_孙文祥
        第6章 D23 display 重复实测）。收窄后唯一候选 = 带 ``\\tag`` 的那一行。
        """
        root, ext, udir, md = self._tree(self._md())
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"], delete_line=True)
        self.assertEqual(rc, 0, out)
        self.assertIn(u"拟删", out)
        self.assertNotIn(u"位置不唯一", out)
        line = [l for l in out.split(u"\n") if u"拟删" in l][0]
        self.assertIn(repr(self.TAG), line)               # 指的就是 \tag 那一行

    def test_ambiguous_two_extra_lines_refuses(self):
        """两处块都多一行 → 位置不唯一，拒绝且零写入。"""
        md = self._md()
        md += [u"", u"$$", self.MATH, self.TAG, u"$$"]
        root, ext, udir, path = self._tree(md)
        before = open(path, "rb").read()
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"], commit=True, delete_line=True)
        self.assertEqual(rc, 1, out)
        self.assertIn(u"位置不唯一", out)
        self.assertEqual(open(path, "rb").read(), before)

    def test_apply_delete_refuses_when_text_moved(self):
        """并发保护：待删行与取证文本不符 → SystemExit，磁盘不动。"""
        root, ext, udir, md = self._tree(self._md())
        before = open(md, "rb").read()
        with self.assertRaises(SystemExit):
            mul.apply_delete(md, 4, u"\\tag{9.9}", os.path.join(ext, u"_bak"))
        self.assertEqual(open(md, "rb").read(), before)


class MirrorDeleteTwoLines(unittest.TestCase):
    """一个单元里被摘掉**两行**独占 ``\\tag``（2026-10-31 数学分析 ch18 `0036_item_18_2-10.md`）。

    `deregister_formula_tags` 对同一单元的两个 display 块各删一行 `\\tag`，交付必须跟着少
    **两**行。早先「只许跳一次」的 :func:`align_deletes` 前身在这里直接给不出合法出口
    （走查在第二个多余行上判死 → 拒），而收官书禁重 merge，于是闸把唯一的修法堵死、
    逼出的下一步就是手改交付（没有复核）。现在一次算全组待删行，每行的见证仍是
    「整行只有 ``\\tag`` + 前后都接得上单元行」，删完再用 :func:`align` 归零。
    """

    A = u"> \\int_{0}^{+\\infty}\\frac{x^{p-1}}{1+x}\\,\\mathrm{d}x=\\frac{1}{p}+\\sum_{n=1}^{\\infty}(-1)^n\\frac{2p}{p^2-n^2}."
    B = u"> \\int_{0}^{+\\infty}\\frac{x^{p-1}}{1+x}\\,\\mathrm{d}x=\\frac{\\pi}{\\sin p\\pi}\\quad(0<p<1)."
    TA = u"> \\tag{1D}"
    TB = u"> \\tag{2p}"
    UNIT = [u"> $$", A, u"> $$", u">", u"> 故最后得", u">", u"> $$", B, u"> $$"]

    def tearDown(self):
        for d in getattr(self, "_dirs", []):
            shutil.rmtree(d, ignore_errors=True)

    def _tree(self):
        """标准形：两个 display 块，每块里各多一行独占 ``\\tag``。"""
        md = self.UNIT[:2] + [self.TA] + self.UNIT[2:7] + [self.B, self.TB] + self.UNIT[8:]
        return self._raw([u"# 第6章 含参变量积分", u""] + md)

    def _raw(self, md_lines, unit=None):
        t = _tree(md_lines, unit_body=unit if unit is not None else self.UNIT)
        self.__dict__.setdefault("_dirs", []).append(t[0])
        return t

    def test_dry_run_lists_both_lines_and_writes_nothing(self):
        root, ext, udir, md = self._tree()
        before = open(md, "rb").read()
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"], delete_line=True)
        self.assertEqual(rc, 0, out)
        hits = [l for l in out.split(u"\n") if u"拟删" in l]
        self.assertEqual(len(hits), 2, out)
        self.assertIn(repr(self.TA), hits[0])
        self.assertIn(u"L5", hits[0])
        self.assertIn(repr(self.TB), hits[1])
        self.assertIn(u"L12", hits[1])                   # 报的是**运行前**的文件行号
        self.assertEqual(open(md, "rb").read(), before)

    def test_commit_removes_exactly_the_two_tag_lines(self):
        root, ext, udir, md = self._tree()
        before = open(md, "rb").read().decode(u"utf-8").split(u"\r\n")
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"], commit=True, delete_line=True)
        self.assertEqual(rc, 0, out)
        after = open(md, "rb").read().decode(u"utf-8").split(u"\r\n")
        self.assertEqual(len(after), len(before) - 2)
        self.assertEqual(after, before[:4] + before[5:11] + before[12:])   # 只少 L5 与 L12
        self.assertNotIn(u"\\tag{", u"\n".join(after))
        for line in self.UNIT:                      # 单元每一行都还在交付里
            self.assertIn(line, after)
        # 幂等：再跑 = 已一致，磁盘与备份都不再动
        mid = open(md, "rb").read()
        rc2, out2 = _run(ext, u"6", [u"0005_item_例1.md"], commit=True, delete_line=True)
        self.assertEqual(rc2, 0, out2)
        self.assertIn(u"已一致", out2)
        self.assertEqual(open(md, "rb").read(), mid)
        self.assertEqual(len(os.listdir(os.path.join(ext, u"_bak_mirror_unit_line"))), 1)

    def test_two_tags_inside_one_block_are_both_removed(self):
        """同一块里连排两行独占 ``\\tag`` 也算得出位置：跳过的行须**全是**独占 tag，且跳完立刻接上单元行。"""
        unit = [u"> $$", self.A, u"> $$"]
        md = [u"# 第6章 含参变量积分", u"", u"> $$", self.A, self.TA, self.TB, u"> $$",
              u"", u"下一段正文"]
        root, ext, udir, path = self._raw(md, unit=unit)
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"], commit=True, delete_line=True)
        self.assertEqual(rc, 0, out)
        after = open(path, "rb").read().decode(u"utf-8").split(u"\r\n")
        self.assertEqual(after, md[:4] + md[6:])

    def test_extra_non_tag_line_is_never_deleted(self):
        """🔴 多出来的行不是「整行 \\tag」（这里是重复的数学行）→ 拒，零写入。

        变异对照：若按「交付比单元多一行就删」放宽形状判据，重复的数学行会被当成 tag 删掉，
        交付少的是**内容**而不是账——那种差异的合法出口是整块搬移/改判单元，不是这里。
        """
        unit = [u"> $$", self.A, u"> $$"]
        md = [u"# 第6章 含参变量积分", u"", u"> $$", self.A, self.A, u"> $$",
              u"", u"下一段正文"]
        root, ext, udir, path = self._raw(md, unit=unit)
        before = open(path, "rb").read()
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"], commit=True, delete_line=True)
        self.assertEqual(rc, 1, out)
        self.assertIn(u"多 tag 行", out)
        self.assertIn(u"本工具不删", out)
        self.assertEqual(open(path, "rb").read(), before)


class MirrorDeleteTagLine(unittest.TestCase):
    """``--delete-tag-line N``：交付块**另有非 tag 漂移**时（:func:`align_deletes` 结构性拿不齐），
    由「台账在账 + 单元已摘 + 全章唯一命中」三件定死那一行（2026-10-31 Fraleigh ch23 英文侧）。

    fixture 是那条的等形缩小：单元用裸 ``$$``，交付整块被 ``>`` 围栏包住（旧流水线拼的形），
    于是「除 tag 行外逐行相等」永远凑不平——`--delete-line` 必须拒（第一个用例就是负向对照），
    而幻影 ``\\tag`` 行仍要有合法出口，且这个出口**只**认台账里记过的号。
    """

    PROSE = u"由此得到"
    MATH = u"\\begin{array}{rl}&(2)(6)=(6)(2)\\end{array}"
    UNIT = [PROSE, u"", u"$$", MATH, u"$$"]
    MD = [u"# Chapter 6", u"", PROSE, u"", u"> $$", u"> " + MATH, u"> \\tag{3}", u"> $$",
          u"", u"next"]
    NUM = u"3"

    def tearDown(self):
        for d in getattr(self, "_dirs", []):
            shutil.rmtree(d, ignore_errors=True)

    def _tree(self, md=None, unit=None, ledger=(NUM,), ledger_ch=u"6"):
        t = _tree(md if md is not None else self.MD,
                  unit_body=unit if unit is not None else self.UNIT,
                  lang="en", md_name=u"Chapter6_iter.md")
        self.__dict__.setdefault("_dirs", []).append(t[0])
        if ledger:
            _ledger(t[1], ledger_ch, ledger)
        return t

    # ---- 负向对照：老通道在这条形上确实拿不齐 ----
    def test_delete_line_mode_cannot_align_this_shape(self):
        root, ext, udir, md = self._tree()
        before = open(md, "rb").read()
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"], delete_line=True)
        self.assertEqual(rc, 1, out)
        self.assertIn(u"本工具不删", out)
        self.assertEqual(open(md, "rb").read(), before)      # 拒绝 = 零写入

    def test_no_ledger_record_refuses(self):
        """🔴 没在账 = 没有删交付的资格：先摘单元/契约侧，再来镜像。"""
        root, ext, udir, md = self._tree(ledger=None)
        before = open(md, "rb").read()
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"], commit=True, delete_tag=[self.NUM])
        self.assertEqual(rc, 1, out)
        self.assertIn(u"没有摘除记录", out)
        self.assertEqual(open(md, "rb").read(), before)
        self.assertFalse(os.path.isdir(os.path.join(ext, u"_bak_mirror_unit_line")))

    def test_ledger_record_for_another_chapter_refuses(self):
        """台账是**按章**的：ch7 摘过 3 号，不给 ch6 的交付当资格（变异对照：全局集合会放行）。"""
        root, ext, udir, md = self._tree(ledger_ch=u"7")
        before = open(md, "rb").read()
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"], commit=True, delete_tag=[self.NUM])
        self.assertEqual(rc, 1, out)
        self.assertIn(u"没有摘除记录", out)
        self.assertEqual(open(md, "rb").read(), before)

    def test_unit_still_holding_the_tag_refuses(self):
        """🔴 单元正文里还写着这个号 = 前提不成立（该动的是单元，不是交付）。"""
        unit = [self.PROSE, u"", u"$$", self.MATH, u"\\tag{3}", u"$$"]
        root, ext, udir, md = self._tree(unit=unit)
        before = open(md, "rb").read()
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"], commit=True, delete_tag=[self.NUM])
        self.assertEqual(rc, 1, out)
        self.assertIn(u"单元正文里仍写着", out)
        self.assertEqual(open(md, "rb").read(), before)

    def test_two_identical_tag_rows_refuses_as_ambiguous(self):
        """两处同形独占行 = 位置不唯一：没有整块对齐当证据时不猜删哪一处。"""
        md = self.MD + [u"", u"> $$", u"> " + self.MATH, u"> \\tag{3}", u"> $$"]
        root, ext, udir, path = self._tree(md=md)
        before = open(path, "rb").read()
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"], commit=True, delete_tag=[self.NUM])
        self.assertEqual(rc, 1, out)
        self.assertIn(u"有 2 处", out)
        self.assertEqual(open(path, "rb").read(), before)

    def test_not_a_whole_line_tag_is_never_touched(self):
        """🔴 行形状不符（tag 与数学内容同行 / 号不同）→ 零命中 = 「已不在交付里」，绝不删内容行。"""
        md = [u"# Chapter 6", u"", self.PROSE, u"", u"> $$",
              u"> " + self.MATH + u" \\tag{3}", u"> $$", u"", u"next"]
        root, ext, udir, path = self._tree(md=md)
        before = open(path, "rb").read()
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"], commit=True, delete_tag=[self.NUM])
        self.assertEqual(rc, 0, out)
        self.assertIn(u"已不在交付里", out)
        self.assertEqual(open(path, "rb").read(), before)

    def test_mode_flags_are_mutually_exclusive(self):
        root, ext, udir, md = self._tree()
        with self.assertRaises(SystemExit):
            _run(ext, u"6", [u"0005_item_例1.md"], delete_line=True, delete_tag=[self.NUM])

    # ---- 正向 ----
    def test_dry_run_deletes_one_line_and_reports_residual_drift(self):
        root, ext, udir, md = self._tree()
        before = open(md, "rb").read()
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"], delete_tag=[self.NUM])
        self.assertEqual(rc, 0, out)
        self.assertIn(u"拟删 \\tag{3}", out)
        self.assertIn(u"L7", out)
        # 诚实条款：块里**其余**的 `>` 围栏漂移必须打印出来，不能被这次删除盖住
        self.assertIn(u"非 tag** 行差异", out)
        self.assertIn(u"> $$", out)
        self.assertEqual(open(md, "rb").read(), before)
        self.assertFalse(os.path.isdir(os.path.join(ext, u"_bak_mirror_unit_line")))

    def test_commit_removes_exactly_that_line_and_is_idempotent(self):
        root, ext, udir, md = self._tree()
        raw_before = open(md, "rb").read()
        before = raw_before.decode(u"utf-8").split(u"\r\n")
        unit_before = open(os.path.join(udir, u"0005_item_例1.md"), "rb").read()
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"], commit=True, delete_tag=[self.NUM])
        self.assertEqual(rc, 0, out)
        after = open(md, "rb").read().decode(u"utf-8").split(u"\r\n")
        self.assertEqual(len(after), len(before) - 1)
        self.assertEqual(after, before[:6] + before[7:])       # 只少第 7 行
        self.assertNotIn(u"\\tag{", u"\n".join(after))
        # 本 fixture 的交付**就是**与单元不同形（裸 `$$` vs `> $$`），所以不能断言
        # 「单元每行都在交付里」；要断言的是「除那一行以外，交付一行没少」。
        self.assertIn(u"> $$", after)
        self.assertIn(u"> " + self.MATH, after)
        self.assertEqual(open(os.path.join(udir, u"0005_item_例1.md"), "rb").read(),
                         unit_before)                          # 单元侧不动
        bakroot = os.path.join(ext, u"_bak_mirror_unit_line")
        self.assertEqual(len(os.listdir(bakroot)), 1)
        bak = os.path.join(bakroot, os.listdir(bakroot)[0], u"Chapter6_iter.md")
        self.assertEqual(open(bak, "rb").read(), raw_before)  # 备份 = 原始字节
        mid = open(md, "rb").read()
        rc2, out2 = _run(ext, u"6", [u"0005_item_例1.md"], commit=True, delete_tag=[self.NUM])
        self.assertEqual(rc2, 0, out2)
        self.assertIn(u"已不在交付里", out2)                     # 幂等
        self.assertEqual(open(md, "rb").read(), mid)
        self.assertEqual(len(os.listdir(os.path.join(ext, u"_bak_mirror_unit_line"))), 1)


class MirrorFillTagLine(unittest.TestCase):
    """``--fill-tag-line``：单元有独占一行的 ``\\tag``、交付那个位置只剩一个空行。

    复刻 2026-10-31 Gelfand–Manin ch1 ``0050_item_1_4-1.md`` 的 ``\\tag{2}``：印面 p24 右栏
    确有其号、契约与 manifest 都在账，交付里那一行被拼接期吃掉只留空位 ⇒ :func:`align`
    报「最好偏移仍差 4 行」（1 真差 + 3 连锁错位），而收官书禁重 merge。
    """

    MATH = u"\\left(d^{n} f \\right) (x) = \\sum_{i = 0}^{n + 1} (- 1)^{i} f (x) ."
    TAG = u"\\tag{2}"
    UNIT = [u"$$", MATH, TAG, u"$$"]

    def tearDown(self):
        for d in getattr(self, "_dirs", []):
            shutil.rmtree(d, ignore_errors=True)

    def _tree(self, md, unit=None):
        t = _tree(md, unit_body=unit if unit is not None else self.UNIT)
        self.__dict__.setdefault("_dirs", []).append(t[0])
        return t

    def _md(self, gap=1):
        """交付侧 = display 块里那个位置有 ``gap`` 个空行（gap=1 才是可补的形）。"""
        return ([u"# 第6章 迭代法", u"", u"$$", self.MATH] + [u""] * gap
                + [u"$$", u"", u"下一段正文"])

    def test_default_mode_still_refuses_this_shape(self):
        """A/B 对照：不带 ``--fill-tag-line`` 时这条必须照旧拒（新档没顺手放宽默认路径）。"""
        root, ext, udir, md = self._tree(self._md())
        before = open(md, "rb").read()
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"])
        self.assertEqual(rc, 1, out)
        self.assertIn(u"拿不到", out)
        self.assertEqual(open(md, "rb").read(), before)

    def test_dry_run_writes_nothing(self):
        root, ext, udir, md = self._tree(self._md())
        before = open(md, "rb").read()
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"], fill_tag_line=True)
        self.assertEqual(rc, 0, out)
        self.assertIn(u"拟补", out)
        self.assertIn(repr(self.TAG), out)
        self.assertEqual(open(md, "rb").read(), before)
        self.assertFalse(os.path.isdir(os.path.join(ext, u"_bak_mirror_unit_line")))

    def test_commit_fills_the_blank_and_keeps_line_count(self):
        root, ext, udir, md = self._tree(self._md())
        raw_before = open(md, "rb").read()
        before = raw_before.decode(u"utf-8").split(u"\r\n")
        unit_before = open(os.path.join(udir, u"0005_item_例1.md"), "rb").read()
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"], commit=True, fill_tag_line=True)
        self.assertEqual(rc, 0, out)
        self.assertIn(u"已补", out)
        after = open(md, "rb").read().decode(u"utf-8").split(u"\r\n")
        self.assertEqual(len(after), len(before))                 # 行数守恒（填坑，不插行）
        self.assertEqual([i for i in range(len(before)) if after[i] != before[i]], [4])
        self.assertEqual(after[4], self.TAG)
        self.assertEqual(after[:4] + after[5:], before[:4] + before[5:])
        self.assertIn(b"\r\n", open(md, "rb").read())             # 换行风格守恒
        self.assertEqual(open(os.path.join(udir, u"0005_item_例1.md"), "rb").read(),
                         unit_before)                             # 单元侧不动
        mid = open(md, "rb").read()
        rc2, out2 = _run(ext, u"6", [u"0005_item_例1.md"], commit=True, fill_tag_line=True)
        self.assertEqual(rc2, 0, out2)
        self.assertIn(u"已一致", out2)                             # 幂等
        self.assertEqual(open(md, "rb").read(), mid)
        self.assertEqual(len(os.listdir(os.path.join(ext, u"_bak_mirror_unit_line"))), 1)

    def test_two_tags_in_one_unit_both_filled(self):
        """一个单元里两块都缺（GM 同一次镜像的复数形态）→ 一次算全组、计划期先复核。"""
        unit = [u"$$", self.MATH, u"\\tag{I.13}", u"$$", u">",
                u"$$", self.MATH + u" x", u"\\tag{I.14}", u"$$"]
        md = [u"# 第6章 迭代法", u"", u"$$", self.MATH, u"", u"$$", u">",
              u"$$", self.MATH + u" x", u"", u"$$"]
        root, ext, udir, path = self._tree(md, unit=unit)
        before = open(path, "rb").read().decode(u"utf-8").split(u"\r\n")
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"], commit=True, fill_tag_line=True)
        self.assertEqual(rc, 0, out)
        self.assertEqual(out.count(u"已补"), 2, out)
        after = open(path, "rb").read().decode(u"utf-8").split(u"\r\n")
        self.assertEqual(len(after), len(before))
        self.assertEqual([i for i in range(len(before)) if after[i] != before[i]], [4, 9])
        self.assertEqual(after[4], u"\\tag{I.13}")
        self.assertEqual(after[9], u"\\tag{I.14}")

    def test_no_blank_placeholder_refuses(self):
        """🔴 那个位置**没有**空行 = 真要插行，行数守恒这条硬不变量不允许 → 拒、零写入。"""
        root, ext, udir, path = self._tree(self._md(gap=0))
        before = open(path, "rb").read()
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"], commit=True, fill_tag_line=True)
        self.assertEqual(rc, 1, out)
        self.assertIn(u"本工具不补", out)
        self.assertEqual(open(path, "rb").read(), before)

    def test_two_blank_lines_refuse_because_target_is_ambiguous(self):
        """两个空行 = 填哪个都是猜，且填完交付仍比单元多一行 → 拒。"""
        root, ext, udir, path = self._tree(self._md(gap=2))
        before = open(path, "rb").read()
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"], commit=True, fill_tag_line=True)
        self.assertEqual(rc, 1, out)
        self.assertEqual(open(path, "rb").read(), before)

    def test_extra_unit_line_that_is_not_a_tag_refuses(self):
        """单元多出的那行不是「整行只有一个 \\tag」（这里是正文行）→ 不补。

        变异对照：若按「单元比交付多一行就补」放宽形状，散文/数学行能被凭空印进交付。
        """
        unit = [u"$$", self.MATH, u"这一行是正文，不是 tag", u"$$"]
        root, ext, udir, path = self._tree(self._md(), unit=unit)
        before = open(path, "rb").read()
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"], commit=True, fill_tag_line=True)
        self.assertEqual(rc, 1, out)
        self.assertEqual(open(path, "rb").read(), before)

    def test_two_candidate_blocks_refuse_as_ambiguous(self):
        """交付里有两块都「缺同一行」→ 落笔点不唯一，拒绝（不猜哪一块才是本块）。"""
        md = self._md() + [u"", u"$$", self.MATH, u"", u"$$"]
        root, ext, udir, path = self._tree(md)
        before = open(path, "rb").read()
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"], commit=True, fill_tag_line=True)
        self.assertEqual(rc, 1, out)
        self.assertIn(u"落笔点不唯一", out)
        self.assertEqual(open(path, "rb").read(), before)

    def test_mode_flags_are_mutually_exclusive(self):
        root, ext, udir, md = self._tree(self._md())
        with self.assertRaises(SystemExit):
            _run(ext, u"6", [u"0005_item_例1.md"], delete_line=True, fill_tag_line=True)
        with self.assertRaises(SystemExit):
            _run(ext, u"6", [u"0005_item_例1.md"], delete_blank_line=True, fill_tag_line=True)


class MirrorDeleteBlankLine(unittest.TestCase):
    """``--delete-blank-line``：交付比单元多一行**只剩块引用围栏**的空行（拼接期残留）。

    复刻 2026-10-31 Gelfand–Manin 的 4 处：单元 ``> \\end{CD}`` 与 ``> $$`` 相邻，交付中间
    夹一行 ``> ``。:func:`norm_text` 把 ``> `` 折成 ``>``（非空）⇒ 它进得了比较空间，
    :func:`align` 就永远「多差一行」；它渲染为空，删掉不动内容。形状档单独开一个，
    **默认档（tag）必须照旧拒**，否则「多出的行不成形状就不删」这条证据被顺手放宽。
    """

    A = u"> \\begin{array}{c}{X \\longrightarrow Y}\\end{array}"
    UNIT = [u"> $$", A, u"> $$"]
    BLANK = u"> "

    def tearDown(self):
        for d in getattr(self, "_dirs", []):
            shutil.rmtree(d, ignore_errors=True)

    def _tree(self, md, unit=None):
        t = _tree(md, unit_body=unit if unit is not None else self.UNIT)
        self.__dict__.setdefault("_dirs", []).append(t[0])
        return t

    def _md(self):
        return [u"# 第6章 同伦代数", u"", u"> $$", self.A, self.BLANK, u"> $$",
                u"", u"下一段正文"]

    def test_default_tag_shape_still_refuses(self):
        """A/B 对照：同一 fixture 走 ``--delete-line``（tag 档）必须拒。"""
        root, ext, udir, md = self._tree(self._md())
        before = open(md, "rb").read()
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"], delete_line=True)
        self.assertEqual(rc, 1, out)
        self.assertIn(u"本工具不删", out)
        self.assertEqual(open(md, "rb").read(), before)

    def test_commit_removes_exactly_the_blank_fence_line(self):
        root, ext, udir, md = self._tree(self._md())
        before = open(md, "rb").read().decode(u"utf-8").split(u"\r\n")
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"], commit=True, delete_blank_line=True)
        self.assertEqual(rc, 0, out)
        self.assertIn(u"已删", out)
        after = open(md, "rb").read().decode(u"utf-8").split(u"\r\n")
        self.assertEqual(len(after), len(before) - 1)
        self.assertEqual(after, before[:4] + before[5:])          # 只少第 5 行（那条空围栏）
        for line in self.UNIT:
            self.assertIn(line, after)                            # 单元每一行都还在
        mid = open(md, "rb").read()
        rc2, out2 = _run(ext, u"6", [u"0005_item_例1.md"], commit=True, delete_blank_line=True)
        self.assertEqual(rc2, 0, out2)
        self.assertIn(u"已一致", out2)                             # 幂等
        self.assertEqual(open(md, "rb").read(), mid)
        self.assertEqual(len(os.listdir(os.path.join(ext, u"_bak_mirror_unit_line"))), 1)

    def test_extra_content_line_is_not_deleted_by_the_blank_mode(self):
        """🔴 多出来的行是**内容**（重复的数学行）→ 空围栏档也照样拒，零写入。"""
        md = [u"# 第6章 同伦代数", u"", u"> $$", self.A, self.A, u"> $$", u"", u"下一段正文"]
        root, ext, udir, path = self._tree(md)
        before = open(path, "rb").read()
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"], commit=True, delete_blank_line=True)
        self.assertEqual(rc, 1, out)
        self.assertIn(u"多 blank 行", out)
        self.assertEqual(open(path, "rb").read(), before)

    def test_two_blocks_both_with_blank_refuse_as_ambiguous(self):
        """两块都多一行 → 位置不唯一，拒绝（同 tag 档的保守性）。"""
        md = self._md() + [u"", u"> $$", self.A, self.BLANK, u"> $$"]
        root, ext, udir, path = self._tree(md)
        before = open(path, "rb").read()
        rc, out = _run(ext, u"6", [u"0005_item_例1.md"], commit=True, delete_blank_line=True)
        self.assertEqual(rc, 1, out)
        self.assertIn(u"位置不唯一", out)
        self.assertEqual(open(path, "rb").read(), before)

    def test_two_delete_shapes_are_mutually_exclusive(self):
        root, ext, udir, md = self._tree(self._md())
        with self.assertRaises(SystemExit):
            _run(ext, u"6", [u"0005_item_例1.md"], delete_line=True, delete_blank_line=True)

    def test_unknown_shape_name_is_a_hard_error(self):
        """形状档认不出来 = 直接崩，不降级成「什么都算」（那等于没有形状闸）。"""
        root, ext, udir, md = self._tree(self._md())
        before = open(md, "rb").read()
        with self.assertRaises(SystemExit):
            mul.align_deletes(self.UNIT, open(md, encoding=u"utf-8").read().split(u"\r\n"),
                              shapes=("whatever",))
        self.assertEqual(open(md, "rb").read(), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
