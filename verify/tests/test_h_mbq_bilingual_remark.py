"""test_h_mbq_bilingual_remark.py — h_mbq「必包标签表」双语对称回归。

Robinson《An Introduction to Dynamical Systems》步骤6 实测（2026-09-27）：
`_H_MISSING_BQ` 的 keyword-first 分支有 CN `注`（→ `**注 2.5.8**` 写在顶层即 FAIL，
必须包成 `> **注 2.5.8**`），却**没有** EN 对应词 `Remark` → 结构完全相同的英文源单元
`**Remark 2.5.8**` 放行。于是同一本书「源过 / 译不过」，译者只能凭空给中文加 `>`
而英文没有（本书 4 例：ch2/0067、ch7/0065/0101/0104）。

根治 = 把 `Remarks?` 补进同一分支（SSOT 口径见 `verify/format_verify/format_verify.md`
第 29/230 条：证明、例、**注**、说明等附属块一律 `>` 包裹），使注释类标签**双语同判**。

本测试锁三件事：
1. EN `**Remark**` / `**Remarks**` 写在顶层必须被抓（旧版漏抓）；
2. 抓完仍是「同一结构两版同判」——EN/CN 注释标签判定逐一相等，且已包 `>` 时两侧都不报；
3. **不得过度触发**：结构条目（定理/定义/Theorem/Proposition）仍在顶层，
   以 `Remark` 为前缀的普通词（`**Remarkable.**`）不得被误判。
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
                           check_unlabeled_blockquotes, _H_MISSING_BQ)

_TAIL = " The statement above follows at once.\n\n"


def _flagged(body):
    """Return the h_mbq verdict for one top-level label line inside a tiny doc."""
    md = "**Proposition 6.2.1** Some structural item stays at top level.\n\n" \
         + body + _TAIL
    fd, p = tempfile.mkstemp(suffix=".md")
    os.close(fd)
    try:
        with io.open(p, "w", encoding="utf-8", newline="") as f:
            f.write(md)
        return bool(check_labels_missing_blockquote(p))
    finally:
        os.remove(p)


class RemarkMustBeBlockquoted(unittest.TestCase):
    def test_en_remark_keyword_first_flagged(self):
        # 旧版此处假绿：EN `**Remark 2.5.8**` 顶层放行，CN `**注 2.5.8**` 却报
        self.assertTrue(_flagged("**Remark 2.5.8** Holonomy maps are absolutely continuous."))
        self.assertTrue(_flagged("**Remark 1.1** A bare singular label."))

    def test_en_remarks_plural_flagged(self):
        self.assertTrue(_flagged("**Remarks 3.4.1** Several remarks at once."))
        self.assertTrue(_flagged("**Remarks.** Then the plural form alone."))

    def test_bilingual_same_verdict(self):
        # 同一结构（注释类 + 自身编号）中英两版判定必须相等。
        # 词对 = 必包表的「成对补齐」清单（SSOT：format_verify.md 第29行约定按语义成立）
        pairs = [("**Remark 2.5.8** text.", "**注 2.5.8** 正文。"),
                 ("**Remark 2.5.8** text.", "**评注 2.5.8** 正文。"),
                 ("**Remarks 2.5.8** text.", "**评注 2.5.8** 正文。"),
                 ("**Note 2.5.8** text.", "**说明 2.5.8** 正文。"),
                 ("**Note 2.5.8** text.", "**注记 2.5.8** 正文。"),
                 ("**Proof 2.5.8** text.", "**证明 2.5.8** 正文。"),
                 ("**Solution 2.5.8** text.", "**解答 2.5.8** 正文。"),
                 ("**Example 2.5.8** text.", "**例 2.5.8** 正文。")]
        for en, cn in pairs:
            self.assertEqual(_flagged(en), _flagged(cn),
                             "EN/CN verdict differ for %r vs %r" % (en, cn))
            self.assertTrue(_flagged(en), "annotation label must be flagged: %r" % en)

    def test_cn_pingzhu_flagged(self):
        # 补 Remark 后若不同步补 评注，不对称只是换个方向（EN 紧 / CN 松）
        self.assertTrue(_flagged("**评注 2.5.8** 和乐映射绝对连续。"))
        self.assertTrue(_flagged("**评注** 单独一个词。"))
        self.assertTrue(_H_MISSING_BQ.match("**2.5-8 评注（续）。**"))

    def test_structural_items_not_swept_in(self):
        # 词对表只覆盖附属块；条目类词绝不能被成对补齐逻辑带进来
        for en, cn in (("**Theorem 2.5** x.", "**定理 2.5** x。"),
                       ("**Definition 2.5** x.", "**定义 2.5** x。"),
                       ("**Proposition 2.5** x.", "**命题 2.5** x。"),
                       ("**Lemma 2.5** x.", "**引理 2.5** x。"),
                       ("**Corollary 2.5** x.", "**推论 2.5** x。")):
            self.assertFalse(_flagged(en), "EN item flagged: %r" % en)
            self.assertFalse(_flagged(cn), "CN item flagged: %r" % cn)

    def test_wrapped_form_passes_both_languages(self):
        for line in ('> **Remark 2.5.8** text.', '> **注 2.5.8** 正文。'):
            self.assertFalse(_flagged(line + "\n"))

    def test_wrapped_remark_is_a_legit_blockquote_opener(self):
        # 包进 `>` 后不得被「无标签块引用」反向抓（开吻词表本就含 Remark）
        md = "\n".join(['> **Remark 2.5.8.** Holonomy maps are absolutely continuous.',
                        '>',
                        '> 1. Take a transversal.',
                        ''])
        fd, p = tempfile.mkstemp(suffix=".md")
        os.close(fd)
        try:
            with io.open(p, "w", encoding="utf-8", newline="") as f:
                f.write(md)
            self.assertEqual(check_unlabeled_blockquotes(p), [])
            self.assertEqual(check_labels_missing_blockquote(p), [])
        finally:
            os.remove(p)


class NoOverTrigger(unittest.TestCase):
    def test_remark_prefixed_words_not_flagged(self):
        # `(?![\w\-])` 词边界仍在位：普通英文词不得被注释标签误伤
        self.assertFalse(_flagged("**Remarkable** as it may seem, the proof is short."))
        self.assertFalse(_flagged("**Remember 1.1** the standing assumption."))

    def test_structural_items_stay_top_level(self):
        # 条目类标签（定义/定理/命题/Theorem/Proposition）按 SSOT 留在顶层
        for line in ("**定理 2.5** 存在周期点。", "**Theorem 2.5** There is a periodic point.",
                     "**Proposition 6.2.1** Something.", "**Definition 1.1** A foliation.",
                     "**Corollary 7.3.7** If $n$ is odd."):
            self.assertFalse(_flagged(line + "\n"), "structural item flagged: %r" % line)

    def test_number_first_remark_still_flagged(self):
        # number-first 分支（`**3.1-3 Remark …**`）为既有行为，须不受本次补词影响
        self.assertTrue(_H_MISSING_BQ.match("**3.1-3 Remark (some book style).**"))


if __name__ == "__main__":
    unittest.main()
