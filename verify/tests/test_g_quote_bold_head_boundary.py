# -*- coding: utf-8 -*-
r"""G/h_mbq「裸空行劈开块引用」的**任意粗体标签头 = 新块**边界回归（2026-09-28）。

背景（Shafarevich《Basic Algebraic Geometry 1》代数附录 unit 0029 实测）：本技能
另一条判据 `_H_MISSING_BQ` **要求** 注/Note/Remark/评注 类附属块包成
`> **Remark** …`，而连续性检测的「新块」词表 `G_ITEM_BQ_HEAD_RE` 只有
例/Example/证明/Proof/解答/Solution 六个词。于是印面合法形态

    > **Proof**: …
    <裸空行>
    > **Remark**: …

被 `check_g_quote_continuity` 判成「bare blank line splits the `> **例/证明` block」
→ 写手为了让闸门变绿只能把 Remark 正文**挤进证明块**（改结构）或私加 `---`，
即「闸门逼出自撰结构」。

根治 = 新增宽判据 `G_BQ_BOLD_HEAD_BOUNDARY_RE`（任何以 `**…**` 粗体 run 起头的
引用行都是新块开头），检测与 fixer **同一判据**。散文续行从不以粗体 run 起头，
所以「真断裂」的保护力度不降。

跨 corpus 标定（D:\study\book 全部最终 md）：消掉 5 处误报（Weibel ch6/ch7/ch9、
Katok ch9、statistical-inference ch1），**新增报告 0 处**，612 处判定不变。
"""
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

from format_verify import check_g_quote_continuity  # noqa: E402
from fix_blockquote_continuity import _fix_quote_gaps  # noqa: E402
from verify.script.struct_labels import G_BQ_BOLD_HEAD_BOUNDARY_RE  # noqa: E402


def _check(text):
    f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
    f.write(text)
    f.close()
    try:
        return check_g_quote_continuity(f.name)
    finally:
        os.unlink(f.name)


LEGAL_REMARK = (
    "**Proposition A.2**: If $\\mathfrak{a} \\subset A$ is an ideal, then $M' = M$.\n"
    "\n"
    "> **Proof**: Apply Proposition A.11 to the module $M / M'$.\n"
    "\n"
    "> **Remark**: The assumption holds if $A / \\mathfrak{a}$ is a local ring.\n"
)


class TestBoldHeadIsBlockBoundary(unittest.TestCase):
    def test_en_remark_block_not_split(self):
        """实测误报形态：证明块后裸空行接 `> **Remark**` 不得判断裂。"""
        self.assertEqual(_check(LEGAL_REMARK), [])

    def test_cn_remark_block_not_split(self):
        """中文同构块（评注/注记）两侧同判。"""
        txt = LEGAL_REMARK.replace("> **Proof**: Apply Proposition A.11.",
                                   "> **证明**：对模 $M / M'$ 用命题 A.11。") \
                        .replace("> **Remark**: The assumption holds.",
                                 "> **评注**：该假设在局部环时成立。")
        self.assertEqual(_check(txt), [])

    def test_bold_heading_without_label_not_split(self):
        """粗体 run 是**小标题**而非六个关键词之一（Weibel ch9 实测形态）同样放行。"""
        txt = ("> **Proof**: The construction is functorial.\n"
               "\n"
               "> **The three basic homomorphisms $S$, $B$, $I$** are defined next.\n")
        self.assertEqual(_check(txt), [])

    def test_fixer_keeps_legal_split(self):
        """fixer 与检测同一判据：合法分块的空行必须原样保留（不得注入 `> `）。

        注：`changes` 计数含「EOF 前的空行被删」这条无关规则，故断言看**输出形态**。
        """
        lines = LEGAL_REMARK.split("\n")
        out, _ = _fix_quote_gaps(lines)
        self.assertEqual(out, lines[:-1])          # 只少了 EOF 空行
        self.assertNotIn("> ", out)                # 没被并进证明块


class TestRealBreakStillCaught(unittest.TestCase):
    def test_continuation_prose_after_blank_still_split(self):
        """负向：续行是散文（无粗体头）时「劈开」仍须被抓——放宽不得吞掉真缺陷。"""
        txt = ("> **Proof**: Consider the exact sequence\n"
               "\n"
               "> of $A$-modules induced by the inclusion.\n")
        probs = _check(txt)
        self.assertEqual(len(probs), 1, probs)
        self.assertIn("splits", probs[0])

    def test_fixer_still_joins_real_split(self):
        lines = ("> **Proof**: consider\n\n> the tail.\n").split("\n")
        out, _ = _fix_quote_gaps(lines)
        self.assertIn("> ", out)                   # 空 `>` 行把续行接回同一块
        self.assertEqual(out, ["> **Proof**: consider", "> ", "> the tail."])

    def test_halfwrap_still_reported(self):
        """负向：块头有 `>` 而正文裸奔（半包）不受放宽影响。"""
        txt = ("> **Example 1.5**\n"
               "\n"
               "This body sits at top level and must be flagged.\n")
        self.assertTrue(_check(txt), "half-wrapped block must still be reported")


class TestBoundaryRegexShape(unittest.TestCase):
    def test_matches_bold_run_opener(self):
        for ln in ("> **Remark**: x", "> **Remark**", "  > **Notes** 正文",
                   "> **The three basic homomorphisms $S$, $B$, $I$** are…"):
            self.assertTrue(G_BQ_BOLD_HEAD_BOUNDARY_RE.match(ln), ln)

    def test_rejects_plain_or_single_star_opener(self):
        for ln in ("> continuation prose", "> *Italic head*", "> $Math$ first",
                   "top-level **Bold** not in quote"):
            self.assertIsNone(G_BQ_BOLD_HEAD_BOUNDARY_RE.match(ln), ln)


if __name__ == "__main__":
    unittest.main(verbosity=2)
