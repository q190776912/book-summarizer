"""test_tighten_loose_math.py — 松散数学「机械档」修法器与判据第 25 项**同进同出**。

判据（`check_unit_quality.loose_math_problems`）与修法器（`tighten_math_text`）共用
`math_frag_iter` / `line_math_spans` 这一份片段遍历，所以本测的正反两向都必须成立：
①改完判据必须归零（否则工具假绿、门控仍红）；②判据没看的散文 / 表格数字列 / `\\tag{}`
内容不许被改（否则「按判据口径改」这句话就是空话）。

🔴 断言只钉**保证的语义**，不钉「好看程度」：
  · 机械档 = 只删空白（`X _ { t }`→`X_{t}`、`\\frac { a } { b }`→`\\frac{a}{b}`、
    `\\left ( x )`→`\\left(x)`、`} {`→`}{`），数学模式里这些空白不产生排版效果，可逆；
  · 语义档 = 数字逐位摊开（`3 . 1 . 1`）一律不动并如实报数——直接焊起来，遇到真漏位/
    漏小数点的误读就是把错值钉死；
  · **绝不制造新事故**：控制字与字母之间的空格不删（`\\in T` 不能变 `\\inT`）、
    text 模式参数内不删（`\\text{ a s }` 的空格是内容）、`$$` 围栏外观不动。
"""
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "lib"))
import lib.boot as _boot  # noqa: E402
_boot.setup()

import check_unit_quality as cq  # noqa: E402

_SPEC = importlib.util.spec_from_file_location(
    "tighten_loose_math", os.path.join(_ROOT, "tools", "tighten_loose_math.py"))
tlm = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(tlm)

MARK = "<!-- book-summarizer DONE unit: id=0001 type=item key=定理2.4 name=定理2.4 -->"


def tighten(text):
    return cq.tighten_math_text(text)


def judge(text):
    return cq.loose_math_problems(text)


def mech_left(text):
    """机械档**片段**数（与判据同遍历）——工具的落盘前置条件就是它为 0。"""
    n = 0
    for _i, frag, _ln in cq.math_frag_iter(text):
        f = cq._LOOSE_MATH_TAG.sub("", frag)
        if any(p.search(f) for p in cq.LOOSE_MATH_MECHANICAL):
            n += 1
    return n


class Mechanical(unittest.TestCase):
    """改得到的：机械档 → 紧凑形，且判据归零。"""

    def test_inline_subscript(self):
        out, ch, mech, sem = tighten("设 $X _ { t }$ 为过程。")
        self.assertIn("$X_{t}$", out)
        self.assertEqual((ch, mech, sem), (1, 0, 0))
        self.assertEqual(judge(out), [])

    def test_frac_delim_and_sqrt(self):
        src = "$\\frac { a } { b }$ 与 $\\left ( x \\right )$ 与 $\\sqrt [ n ] { x }$"
        out, _c, mech, sem = tighten(src)
        self.assertIn("\\frac{a}{b}", out)
        # 界符命令与其界符之间归一（`\left (`→`\left(`、`\right )`→`\right)`）；
        # `x \right)` 里控制字**前**的空格是正常写法，不属本工具的档。
        self.assertIn("\\left(x \\right)", out)
        self.assertIn("\\sqrt[n]{x}", out)
        self.assertEqual((mech, sem), (0, 0))
        self.assertEqual(judge(out), [])

    def test_brace_seam(self):
        out, _c, _m, _s = tighten("$\\frac{a} {b}$ 与 $x _{ y }$")
        self.assertIn("\\frac{a}{b}", out)
        self.assertIn("x_{y}", out)

    def test_display_fence_preserves_blockquote_prefix(self):
        src = "\n".join([MARK, "", "$$", "> x _ { n } = \\frac { 1 } { n }", "$$", ""])
        out, _c, mech, sem = tighten(src)
        self.assertIn("> x_{n} = \\frac{1}{n}", out)
        self.assertEqual((mech, sem), (0, 0))
        self.assertEqual(judge(out), [])

    def test_single_line_display_keeps_fence_spacing(self):
        """`$$` 外观不动：只改片段内部，围栏两侧紧贴的空白不删。"""
        src = "$$ y _ { k } \\to y $$"
        out, _c, mech, _sem = tighten(src)
        self.assertEqual(out, "$$ y_{k} \\to y $$")
        self.assertTrue(out.startswith("$$ ") and out.endswith(" $$"))
        self.assertEqual(mech, 0)

    def test_crlf_and_marker_line_untouched(self):
        src = "\r\n".join([MARK, "", "$X _ { t }$", ""])
        out, _c, _m, _s = tighten(src)
        self.assertTrue(out.startswith(MARK + "\r\n"))
        self.assertIn("$X_{t}$\r\n", out)

    def test_judge_face_drops_to_zero(self):
        src = ("$X _ { t }$ 与 $\\frac { a } { b }$ 与 $Y _ { s }$\n"
               "$$\nx _ { 1 } , \\quad \\sqrt [ 3 ] { y }\n$$")
        self.assertEqual(mech_left(src), 4)          # 3 个行内片段 + 1 个围栏内片段
        out, ch, mech, sem = tighten(src)
        self.assertEqual((mech, sem), (0, 0))
        self.assertEqual(mech_left(out), 0)
        self.assertEqual(ch, 4)                      # `changed` 按「数学片段」计（同行替换）
        self.assertEqual(judge(out), [])
        self.assertEqual(len(out.split("\n")), len(src.split("\n")))   # 行结构不动

    def test_idempotent(self):
        src = "$X _ { t }$ 与 $\\frac { 1 } { 2 }$ 与 $\\begin{array} { l l } a\\end{array}$"
        once = tighten(src)[0]
        self.assertEqual(tighten(once)[0], once)
        self.assertEqual(tighten(once)[1], 0)


class NeverTouched(unittest.TestCase):
    """改不得的：语义档、散文、text 模式内容、控制字接缝、合法紧凑形。"""

    def test_digit_spread_is_semantic_and_untouched(self):
        src = "$3 . 1 . 1$ 与 $1 0 6$"
        out, ch, mech, sem = tighten(src)
        self.assertEqual(out, src)                         # 一格不改
        self.assertEqual((ch, mech), (0, 0))
        self.assertEqual(sem, 2)
        self.assertTrue(judge(src))                        # 判据照样红（须人工）

    def test_prose_and_table_digits_not_math(self):
        src = "第 3 . 1 . 1 节见 p. 12 ，表中 $\\begin{array}{cc} 1 & 2 \\\\ 3 & 4 \\end{array}$"
        out, ch, mech, sem = tighten(src)
        self.assertEqual(out, src)                         # 散文视图完全不看
        self.assertEqual((ch, mech, sem), (0, 0, 0))

    def test_control_word_seams_never_joined(self):
        """`\\in T` / `\\alpha x` 之间的空格删了会改解析（`\\inT`）——本工具只看括号内侧。"""
        self.assertEqual(tighten("$x \\in T$ 与 $a b$")[0], "$x \\in T$ 与 $a b$")
        out, _c, mech, _s = tighten("$\\text{ i f } x _ { n }$")
        self.assertIn("\\text{ i f }", out)                # text 模式空格是内容
        self.assertIn("x_{n}", out)
        self.assertEqual(mech, 0)

    def test_text_mode_group_protects_its_own_edges(self):
        r"""`\text{…}` 内侧空格是内容；同一段里的普通组照样归一，数字之间绝不焊。"""
        out, _c, mech, _s = tighten("$\\text{ a }$ 与 $\\text{ x{ y } z }$ 与 ${ 1 0 6 }$")
        self.assertIn("\\text{ a }", out)
        self.assertIn("\\text{ x{ y } z }", out)
        self.assertIn("{1 0 6}", out)                      # 组内侧照删，数字之间保留
        self.assertEqual(mech, 0)

    def test_tag_content_exempt(self):
        src = "$$a _ { n } = b \\tag { 3 . 1 }$$"
        out, _c, mech, sem = tighten(src)
        self.assertIn("\\tag { 3 . 1 }", out)              # tag 内不碰（判据同口径摘除）
        self.assertIn("a_{n}", out)
        self.assertEqual((mech, sem), (0, 0))

    def test_array_blank_row_escaped_space_survives(self):
        r"""回归随机过程 ch7 0024b 事故：`{ \ }` 是 array 空行（`\ ` 为可打印空格）。

        删掉 `\` 与 `}` 之间的空白即成 `\}`——花括号照样配平、真实 KaTeX 在
        `\end{array}` 处炸。修后档必须原样留住 `\ `，同段的真摊开照样归一。
        """
        src = r"$$\begin{array}{l}{\begin{array}{l}{{U _ { 1 } = \cdot \, Z _ { 1 } \cdots ,}} \\ { \ } \\ {U _ { 2}}\end{array}}\end{array}$$"
        out, _c, mech, sem = tighten(src)
        self.assertIn(r"{\ }", out)                         # `\ ` 存活（组内侧空格可删）
        self.assertNotIn(r"\}", out)                        # 绝不让 `\` 直接顶到 `}`
        self.assertIn("U_{1}", out)                         # 同段真摊开照样修
        self.assertIn("U_{2}", out)
        self.assertEqual((mech, sem), (0, 0))

    def test_no_math_no_change(self):
        src = "\n".join([MARK, "", "## 定理 2.4  statement", "", "纯散文，无数学。", "---"])
        self.assertEqual(tighten(src)[0:2], (src, 0))


class FileLevel(unittest.TestCase):
    def test_marker_guard_refuses_write(self):
        """首行 marker 被改动 → 拒绝写盘（结构性首行与 manifest 逐字对账）。"""
        d = tempfile.mkdtemp()
        p = os.path.join(d, "0001_item_x.md")
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(MARK + "\r\n" + "$X _ { t }$" + "\r\n")
        orig = cq.tighten_math_text
        try:
            cq.tighten_math_text = lambda t: (MARK.replace("DONE", "DRAFT") + "\r\nx\r\n",
                                              1, 0, 0)
            with self.assertRaises(SystemExit):
                tlm.tighten_file(p, True, 0)
        finally:
            cq.tighten_math_text = orig
        self.assertIn("DONE", open(p, encoding="utf-8").read())

    def test_commit_writes_and_dry_run_does_not(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "0001_item_x.md")
        src = MARK + "\r\n" + "$X _ { t }$ 与 $\\frac { a } { b }$" + "\r\n"
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(src)
        rc_dry = tlm.main([p])
        self.assertEqual(rc_dry, 0)
        self.assertEqual(open(p, encoding="utf-8", newline="").read(), src)
        rc = tlm.main([p, "--commit"])
        self.assertEqual(rc, 0)
        got = open(p, encoding="utf-8", newline="").read()
        self.assertIn("$X_{t}$", got)
        self.assertTrue(got.startswith(MARK + "\r\n"))
        self.assertEqual(mech_left(got), 0)

    def test_semantic_residual_exits_nonzero(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "0001_item_x.md")
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(MARK + "\r\n" + "$3 . 1 . 1$" + "\r\n")
        self.assertEqual(tlm.main([p, "--commit"]), 1)     # 有语义档 → 非零，逼人工
        self.assertIn("$3 . 1 . 1$", open(p, encoding="utf-8").read())


class Audit(unittest.TestCase):
    """落盘前的机械证明独立于修法器（伪造越界输出，必须被拦下且不写盘）。"""

    def _file(self, body):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "0001_item_x.md")
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(body)
        return p

    def _forge(self, p, fn, commit=True):
        orig = cq.tighten_math_text
        try:
            cq.tighten_math_text = fn
            got = tlm.tighten_file(p, commit, 0)
        finally:
            cq.tighten_math_text = orig
        return got

    def test_joining_control_word_letters_refused(self):
        p = self._file(MARK + "\r\n" + "$x \\in T$" + "\r\n")
        _c, _m, _s, wrote, refused = self._forge(
            p, lambda t: (t.replace("\\in T", "\\inT"), 1, 0, 0))
        self.assertTrue(refused)
        self.assertFalse(wrote)
        with open(p, encoding="utf-8") as f:
            self.assertIn("\\in T", f.read())

    def test_joining_digits_refused(self):
        p = self._file(MARK + "\r\n" + "$1 0 6$" + "\r\n")
        _c, _m, _s, wrote, refused = self._forge(
            p, lambda t: (t.replace("1 0 6", "106"), 1, 0, 0))
        self.assertTrue(refused)
        self.assertFalse(wrote)

    def test_escaped_space_deletion_refused(self):
        r"""守卫独立拦一道：`{ \ }`→`{ \}` 右邻虽是 `}`，左侧是反斜杠即拒。

        修前档正是靠「右邻是闭括号」放过它，把 array 空行焊成 `\}` 字面闭括号——
        判据与审计都查不出（括号照样配平），只有真实渲染会炸，故这道必须写在守卫里。
        """
        p = self._file(MARK + "\r\n" + "${ \\ }$" + "\r\n")
        _c, _m, _s, wrote, refused = self._forge(
            p, lambda t: (t.replace("\\ }", "\\}"), 1, 0, 0))
        self.assertTrue(refused)
        self.assertFalse(wrote)
        self.assertFalse(tlm.only_safe_whitespace_deletions(r"${ \ }$", r"${\}$"))

    def test_char_change_and_line_drop_refused(self):
        p = self._file(MARK + "\r\n" + "$x_1$ 文字" + "\r\n")
        _c, _m, _s, wrote, refused = self._forge(p, lambda t: (t.replace("文字", "文宇"), 1, 0, 0))
        self.assertTrue(refused)
        p2 = self._file(MARK + "\r\n" + "$x_1$" + "\r\n")
        self.assertTrue(self._forge(p2, lambda t: (MARK + "\r\n", 1, 0, 0))[4])

    def test_legit_output_passes_audit(self):
        p = self._file(MARK + "\r\n" + "$X _ { t } = \\frac { 1 } { 2 }$" + "\r\n")
        ch, _m, _s, wrote, refused = tlm.tighten_file(p, True, 0)
        self.assertFalse(refused)
        self.assertTrue(wrote)
        self.assertEqual(ch, 1)

    def test_big_delimiter_seam_is_safe(self):
        r"`\Big |`→`\Big|` 属定界符档（审计允许 `|` 邻侧删空白），字母之间仍不许。"""
        p = self._file(MARK + "\r\n" + "${ \\Big | } \\in T \\quad 1 0 6$" + "\r\n")
        _c, _m, _s, wrote, refused = tlm.tighten_file(p, True, 0)
        self.assertFalse(refused)
        self.assertTrue(wrote)
        with open(p, encoding="utf-8") as f:
            got = f.read()
        self.assertIn("{\\Big|}", got)
        self.assertIn("\\in T", got)
        self.assertIn("1 0 6", got)

    def test_main_exits_nonzero_on_refusal(self):
        p = self._file(MARK + "\r\n" + "$x \\in T$" + "\r\n")
        orig = cq.tighten_math_text
        try:
            cq.tighten_math_text = lambda t: (t.replace("\\in T", "\\inT"), 1, 0, 0)
            rc = tlm.main([p, "--commit"])
        finally:
            cq.tighten_math_text = orig
        self.assertEqual(rc, 1)
        with open(p, encoding="utf-8") as f:
            self.assertIn("\\in T", f.read())


if __name__ == "__main__":
    unittest.main(verbosity=2)
