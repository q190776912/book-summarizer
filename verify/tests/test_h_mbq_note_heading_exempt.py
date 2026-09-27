# -*- coding: utf-8 -*-
r"""h_mbq 必包闸的「题式注记标签」语言对称性回归（Robinson 李代数书，2026-09-28）。

背景：必包表 `_H_MISSING_BQ` 于 2026-09-27/28 补齐 `注记`/`评注` 等中文标签后，
英文侧 `**Notes**` 因 `Note(?![\w\-])` 的复数尾巴**天然不命中**，而中文同位写法
`**注记 (Notes)**` 命中 → 章末 Notes（标签独占一行、正文另起一段）在**源单元过、
译单元不过**，译者只能把标题塞进 `>` 或改词规避，两版结构分叉（本书 ch3
0009/0034/0050、ch6 0018 实测）。

根治 = 新增 `_H_NOTE_HEADING_RE`：粗体 run 内**只有**关键词（可带英文括注、可 run-in
正文）且**无编号**的 注记/评注 ↔ Notes/Remarks/Comments 题式标签**两侧同时**豁免；
带编号或单数的随文注记（`**注记 3.1**：…` / `**Remark 6.12** …` / `**Note**: …`）
**必须仍然**判必包（负向断言）。
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

from format_verify import check_labels_missing_blockquote, _H_MISSING_BQ
from fix_structural_label_guard import fix_labels_missing_blockquote


def _run(text):
    f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False,
                                    encoding="utf-8")
    f.write(text)
    f.close()
    try:
        return check_labels_missing_blockquote(f.name)
    finally:
        os.unlink(f.name)


def _fix(text):
    f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False,
                                    encoding="utf-8")
    f.write(text)
    f.close()
    try:
        n = fix_labels_missing_blockquote(f.name)
        with open(f.name, encoding="utf-8") as fh:
            body = fh.read()
        return n, body
    finally:
        os.unlink(f.name)


HEADING_BOTH = {
    # 豁免 = 「关键词 + 英文括注 + 粗体 run 即止」（括注 = 印面标题词被翻译的信号）
    "cn": "**注记 (Notes)**\n\n本节材料取自 Bourbaki [2]。\n",
    "cn-remark": "**评注 (Remarks)**\n\n补充说明。\n",
    # run-in 形态（Robinson ch6 0008/0018 实测）：标签后同行直接接正文
    "cn-runin": "**注记 (Notes)** 关于无限维模中的权空间，见 Lemire [1]。\n",
    # 英文侧：`Note` 后紧跟 `s` 使 `Note(?![\w\-])` 失配，复数题头本就不命中
    "en": "**Notes**\n\nPart of the material is drawn from Bourbaki [2].\n",
    "en-runin": "**Notes** On weight spaces in infinite dimensional modules "
                "see Lemire [1].\n",
}


class TestNoteHeadingExempt(unittest.TestCase):
    def test_heading_like_note_clean_both_languages(self):
        for k, text in HEADING_BOTH.items():
            self.assertEqual(_run(text), [], f"{k}: 题式注记标签不得判断裂必包")

    def test_fixer_leaves_heading_like_note_alone(self):
        n, body = _fix(HEADING_BOTH["cn"])
        self.assertEqual(n, 0, "修复器不得把题式 Notes 标题包进 `>`")
        self.assertTrue(body.startswith("**注记 (Notes)**"))

    def test_fixer_leaves_runin_note_heading_alone(self):
        n, _ = _fix(HEADING_BOTH["cn-runin"])
        self.assertEqual(n, 0, "run-in 题式注记同样不得被包裹")


class TestInlineNoteStillRequired(unittest.TestCase):
    def test_numbered_or_body_carrying_note_still_flagged(self):
        cases = {
            "cn-numbered": "**注记 3.1**：这是一条随文注记。\n",
            "cn-numbered-remark": "**评注 6.1** 这是一条带编号的随文评注。\n",
            # 无英文括注的裸标签仍归「随文注记」（保住 2026-09-28 的补词决定）
            "cn-bare-glossless": "**评注** 单独一个词。\n",
            "cn-note": "**注**：见下文。\n",
            "en-colon": "**Note**: see the discussion below.\n",
            "en-remark-numbered": "**Remark 6.12** this one is numbered.\n",
            "en-remarks-period": "**Remarks.** Then the plural form alone.\n",
        }
        for k, text in cases.items():
            self.assertEqual(len(_run(text)), 1, f"{k}: 随文注记仍须判必包")

    def test_regex_vocabulary_untouched(self):
        # 豁免只在 check/fix 的行级判定里，不改必包表本身
        self.assertTrue(_H_MISSING_BQ.match("**注记 3.1**：x"))
        self.assertTrue(_H_MISSING_BQ.match("**注记**"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
