"""test_h_mbq_fix_wraps_body_run.py — h_mbq 自动修复必须连正文一起包进 `>`。

配套 2026-09-27 的 `Remark`/`评注` 双语对称补词：补词之后顶级注释类标签在全库新增上千处
待修，只能靠 `--fix` 的 H 修法器批量处理。旧修法**只给标签行加 `> `**，于是产出

    > **Remark 1.1**  The entropy is finite.
    and it is upper semi-continuous.          ← 正文仍裸在顶层

这正是 `check_g_quote_continuity` 报的「半包块」（Robinson ch7 在 4l 双语同判改动落地后
实测撞上，报错为 `example/proof head is quoted but its body is bare top-level prose`）。
**修法器自己的输出被另一条判据拒绝** = 批量整改无法机械完成，故一并根治。

新判据：把标签行与其**段落续行**一起包进 `>`，遇到空行、块起始（`---`/标题/`$$`/`<div`/
`<img`/已引用行/TeX 环境）、结构条目标签（定理/定义…须留顶层）或另一个必包标签（自开一块）
即停。本测试同时锁这些停止条件，防止修法过宽把条目吞进块里。
"""
import io
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
    _ROOT = str(Path(__file__).resolve().parents[2])
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

from format_verify import (check_labels_missing_blockquote,
                           check_g_quote_continuity)
from fix_structural_label_guard import fix_labels_missing_blockquote


def _tmp(md):
    fd, p = tempfile.mkstemp(suffix=".md")
    os.close(fd)
    with io.open(p, "w", encoding="utf-8", newline="") as f:
        f.write(md)
    return p


def _fix_and_read(md):
    p = _tmp(md)
    try:
        n = fix_labels_missing_blockquote(p)
        # read back with universal newlines: that is how the checkers see the file
        out = io.open(p, encoding="utf-8").read()
        flags = check_labels_missing_blockquote(p)
        breaks = check_g_quote_continuity(p)
    finally:
        os.remove(p)
    return n, out, flags, breaks


class WrapsBodyRun(unittest.TestCase):
    def test_multiline_remark_fully_wrapped_and_clean(self):
        md = "\n".join([
            "**Remark 1.1** The topological entropy is finite.",
            "It is in fact upper semi-continuous in the map.",
            "",
            "## 1.2 Next section",
            "",
        ])
        n, out, flags, breaks = _fix_and_read(md)
        self.assertEqual(out.split("\n")[0], "> **Remark 1.1** The topological entropy is finite.")
        self.assertEqual(out.split("\n")[1], "> It is in fact upper semi-continuous in the map.")
        self.assertEqual(flags, [], "h_mbq still reports after its own fix")
        self.assertEqual(breaks, [], "fixer output is a half-wrapped block")
        self.assertGreaterEqual(n, 2)

    def test_cn_pingzhu_body_wrapped(self):
        md = "\n".join([
            "**评注 2.5.8** 该和乐映射在几乎处处意义下可微。",
            "其雅可比在紧集上有界，故叶状结构绝对连续。",
            "",
        ])
        n, out, flags, breaks = _fix_and_read(md)
        lines = out.split("\n")
        self.assertTrue(lines[0].startswith("> **评注 2.5.8**"))
        self.assertTrue(lines[1].startswith("> "))
        self.assertEqual(flags, [])
        self.assertEqual(breaks, [])

    def test_stop_at_blank_line(self):
        md = "\n".join([
            "**Remark 1.1** first paragraph.",
            "",
            "A separate top-level paragraph, not part of the remark.",
            "",
        ])
        n, out, flags, breaks = _fix_and_read(md)
        lines = out.split("\n")
        self.assertTrue(lines[0].startswith("> **Remark"))
        self.assertEqual(lines[2], "A separate top-level paragraph, not part of the remark.")

    def test_does_not_swallow_structural_item(self):
        # 无空行紧跟条目标签时，条目必须留在顶层（否则会把定理吞进 Remark 块）
        md = "\n".join([
            "**Remark 1.1** a remark.",
            "**Theorem 1.2** the next item starts here.",
            "",
        ])
        n, out, flags, breaks = _fix_and_read(md)
        lines = out.split("\n")
        self.assertEqual(lines[0], "> **Remark 1.1** a remark.")
        self.assertEqual(lines[1], "**Theorem 1.2** the next item starts here.")

    def test_two_consecutive_labels_get_two_blocks(self):
        md = "\n".join([
            "**Remark 1.1** first remark body.",
            "**证明** 第二条是证明块。",
            "证明的续行。",
            "",
        ])
        n, out, flags, breaks = _fix_and_read(md)
        lines = out.split("\n")
        self.assertEqual(lines[0], "> **Remark 1.1** first remark body.")
        self.assertEqual(lines[1], "> **证明** 第二条是证明块。")
        self.assertEqual(lines[2], "> 证明的续行。")
        self.assertNotIn("> >", out)
        self.assertEqual(flags, [])

    def test_stop_at_display_math_and_hr(self):
        md = "\n".join([
            "**Remark 1.1** see below.",
            "---",
            "",
            "**Note 1.2** then a rule follows.",
            "$$",
            "x = y",
            "$$",
            "",
        ])
        n, out, flags, breaks = _fix_and_read(md)
        lines = out.split("\n")
        self.assertEqual(lines[1], "---")
        self.assertEqual(lines[3], "> **Note 1.2** then a rule follows.")
        self.assertEqual(lines[4], "$$")

    def test_footnote_brace_branch_stays_line_only(self):
        md = "\n".join([
            "{a footnote marker} trailing text here.",
            "next line after the marker.",
            "",
        ])
        n, out, flags, breaks = _fix_and_read(md)
        lines = out.split("\n")
        self.assertTrue(lines[0].startswith("> {"))
        self.assertEqual(lines[1], "next line after the marker.")


if __name__ == "__main__":
    unittest.main()
