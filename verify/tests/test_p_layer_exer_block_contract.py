"""Regression tests: p_exer_block 的「印刷习题集标题」契约豁免（Rosen 8e ch10 实测）。

背景：本层专拦「无中生有新建归拢块」——把原书穿插排布的习题抽出来在节末造一个
`### 习题`。但 Rosen 8e **每一节末都自己印** `EXERCISES` 标题 + 1..N 题；抽取期该标题
作为 `{"text": "Exercises"}` 内容块进了分章契约，写手照原书位置渲染成 `**习题**`
（中文版）/ `**Exercises**` 是**忠实**。此前判据只看 md 文本，把这条印刷标题当成违规
（ch10 §10.7 / §10.8 实测 2 条 BLOCKING），而同一条题集又被 `lib/problem_coverage`
系闸门（⑫⑬⑮）要求**必须整块在位且题号连续** —— 两条判据互相矛盾，无解。

根治后行为（本文件锁定）：
  1. 契约该节（或其祖先节）子树里确有整行习题标题 → md 里该节的标题行放行；
  2. 契约**无据**的节照样拦截（豁免不是橡皮图章，闸门保留牙齿）；
  3. 不传 ext_dir（老调用方 / 单测）→ 退回纯文本判据，行为不变；
  4. 中英文两版同一位置结果一致（同一真值源，语言不再影响判据）。
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
    _ROOT = str(Path(__file__).resolve().parents[2])
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

from verbose_gates import (check_exer_blocks, contract_exer_heading_sections,
                           EXER_BOLD_RE, EXER_HEADING_RE)


def _contract_with_printed_head():
    """§1.2 末印 EXERCISES（标题独立成块）；§1.3 无习题块。"""
    return {
        "key": "1", "type": "chapter", "name": "1 Test Chapter",
        "page_start": 1, "page_end": 40,
        "sub_sec": [
            {"key": "1.2", "type": "section", "name": "1.2 Interpolation",
             "page_start": 10, "page_end": 14, "consolidated": False,
             "sub_sec": [
                 {"key": "例3", "type": "example", "name": "例3 3",
                  "sub_sec": [{"text": "The error bound follows."},
                              {"text": "Exercises"},
                              {"text": "1. Prove the bound.\n2. Compute it."}]}]},
            {"key": "1.3", "type": "section", "name": "1.3 Splines",
             "page_start": 15, "page_end": 18, "consolidated": False,
             "sub_sec": [{"key": "D1", "type": "description", "name": "",
                          "sub_sec": [{"text": "A paragraph without any list."}]}]},
        ]}


def _book(with_head_node=True):
    """建一棵最小 _extract（只需 book_structure/ch1.json）。"""
    tmp = tempfile.mkdtemp(prefix="bks_p_exer_")
    bs = os.path.join(tmp, "book_structure")
    os.makedirs(bs)
    root = _contract_with_printed_head()
    if not with_head_node:
        root["sub_sec"][0]["sub_sec"][0]["sub_sec"] = [
            {"text": "The error bound follows."}]
    with open(os.path.join(bs, "ch1.json"), "w", encoding="utf-8") as fh:
        json.dump(root, fh, ensure_ascii=False)
    return tmp


MD = """# 第1章 测试章

## §1.2 插值

> **例 3.** 误差界如下。

**习题**

1. 证明该界。

2. 计算该界。

---

## §1.3 样条

一段没有习题的正文。

**习题**

1. 阅读材料。
"""


class TestContractBackedExemption(unittest.TestCase):
    def test_truth_source(self):
        ext = _book()
        self.assertEqual(contract_exer_heading_sections(ext, 1), {"1.2"})
        self.assertEqual(contract_exer_heading_sections(ext, "1"), {"1.2"})

    def test_backed_section_exempt_unbacked_still_flagged(self):
        ext = _book()
        lines = MD.split("\n")
        got = check_exer_blocks(lines, ext, 1)
        self.assertEqual(len(got), 1, msg=str(got))
        self.assertIn("L19", got[0])          # §1.3 的自建块照样拦
        self.assertNotIn("L9", got[0])

    def test_without_contract_context_behaves_as_before(self):
        lines = MD.split("\n")
        got = check_exer_blocks(lines)
        self.assertEqual(len(got), 2)         # 纯文本判据：两处都报
        self.assertEqual(check_exer_blocks(lines, None, 1), got)

    def test_no_contract_evidence_means_no_exemption(self):
        ext = _book(with_head_node=False)
        self.assertEqual(contract_exer_heading_sections(ext, 1), set())
        self.assertEqual(len(check_exer_blocks(MD.split("\n"), ext, 1)), 2)

    def test_ancestor_heading_covers_deeper_md_section(self):
        """md 里标题在更深的 `### §1.2.1` 下，豁免仍按祖先 §1.2 生效。"""
        ext = _book()
        lines = ("## §1.2 插值\n\n### §1.2.1 细分\n\n**习题**\n").split("\n")
        self.assertEqual(check_exer_blocks(lines, ext, 1), [])
        self.assertEqual(len(check_exer_blocks(lines)), 1)

    def test_atx_heading_form_same_rule(self):
        ext = _book()
        lines = "## §1.2 插值\n\n### 习题\n\n1. 题面\n".split("\n")
        self.assertEqual(check_exer_blocks(lines, ext, 1), [])
        lines2 = "## §1.3 样条\n\n### 习题\n\n1. 题面\n".split("\n")
        self.assertEqual(len(check_exer_blocks(lines2, ext, 1)), 1)

    def test_regexes_unchanged_for_plain_forms(self):
        for ln in ("**习题**", "**练习**", "**Exercise**", "### 习题", "## §1.1 Exercises"):
            self.assertTrue(EXER_BOLD_RE.match(ln) or EXER_HEADING_RE.match(ln), ln)


if __name__ == "__main__":
    unittest.main(verbosity=2)
