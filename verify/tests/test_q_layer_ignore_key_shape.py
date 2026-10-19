# -*- coding: utf-8 -*-
"""Q 层 per-chapter `ignore_ch{N}.json` 键**形状**回归（纯章路径根治）。

Lehmann《Elements of Large-Sample Theory》步骤7 实测（2026-10-19）：
附录 A.2 有一句散文交叉引用 `and hence by (A.2.16) and (A.2.6)`——印面（fitz
物理 588）确证左缘编号只到 `(A.2.15)`，`(A.2.16)` 从未作为公式编号印出，属原书
悬空引用。按惯例经 `manage_ignore.py` 登记进 `ignore_appendix.json`，键被写成
**连字符形** `A.2-16`（B 层惯例：`lib/key_parse.normkey` 把点折成连字符）。
正文的 `6.4-67` 同一形状却生效了——因为**分节路径**先把 ignore 过一遍
`_split_scoped_ignore`（内部调 `SourceFormulaIndex.norm` 把 `-` 折回 `.`），而
**纯章路径**（附录 md 的 `## §A.1` 不被 `_detect_summary_sections` 认成节，于是
走这里）把原始键直接交给 `_compare`，`A.2-16` 永不相等于规范化的 `A.2.16`：
登记了照样报 `Q-LAYER FORMULA MISSING`，同一份 ignore 文件「正文过 / 附录不过」。

修法（被测）：加载 per-chapter ignore 后取 **原始 ∪ 规范化 bare 键** 并集。
`_compare` 的 FABRICATED 与 MISSING 两支都先查 `n in ignore`，所以本步只会
**少报**、不可能**多报**——对既有书单调安全；`sec#num` 作用域键仍交
`_split_scoped_ignore` 分桶，**不得**泄漏成全局屏蔽（第 4 例锁死）。

Runs under stdlib unittest:
  python verify/tests/test_q_layer_ignore_key_shape.py
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

from verify_config import BookConfig                              # noqa: E402
from verify.script.base import VerifyContext                     # noqa: E402
from formula_tag import QLayer                                   # noqa: E402

CFG = {'type': 2, 'scope': 2, 'ignore': []}


def _build(d, md_text, page_texts, ignore_map=None, ignore_name="ignore_ch3.json"):
    md = os.path.join(d, 'ch3.md')
    with open(md, 'w', encoding='utf-8') as f:
        f.write(md_text)
    ext = os.path.join(d, '_extract')
    os.makedirs(ext, exist_ok=True)
    for i, t in enumerate(page_texts, start=1):
        with open(os.path.join(ext, 'page_%03d.json' % i), 'w',
                  encoding='utf-8') as f:
            json.dump({'text': [{'text': t}]}, f, ensure_ascii=False)
    if ignore_map is not None:
        with open(os.path.join(ext, ignore_name), 'w', encoding='utf-8') as f:
            json.dump(ignore_map, f, ensure_ascii=False, indent=2)
    return ext, md


def _run(ext, md, n_pages):
    ctx = VerifyContext(ch=3, start=1, end=n_pages, md_file=md, ext_dir=ext,
                        config=BookConfig(formula=dict(CFG)))
    return QLayer().run(ctx).metadata


class TestDashKeyInPlainPath(unittest.TestCase):
    def test_hyphen_key_silences_missing_in_plain_path(self):
        """事故本体：连字符键 `3-5` 须在纯章路径屏蔽规范化后的 `3.5`。

        书侧形态与 Lehmann 附录一致——编号只以**行内交叉引用**出现在散文里
        （`and hence by (3.5) and (3.1)`），keep_cross_refs 把它收进 S，于是
        「总结没写 (3.5)」被判 MISSING；印面确证它不是展示式编号，只能 ignore。
        """
        with tempfile.TemporaryDirectory() as d:
            # 无 `## §` 标题 => 纯章路径（与本书附录 md 同形态）
            ext, md = _build(
                d, "$$\nE=mc^2 \\tag{3.1}\n$$\n",
                ["By (3.1) we get A.", "and hence by (3.5) and (3.1)"],
                {"3-5": "印面确证：(3.5) 只作行内交叉引用出现，无展示式。"})
            res = _run(ext, md, 2)
            self.assertEqual([r['number'] for r in res['q_missing']], [])
            self.assertEqual(res['q_fabricated'], [])

    def test_control_without_ignore_reports_missing(self):
        """对照：同一 fixture 不登记 ignore 时必须报 MISSING（证明上一例非空转）。"""
        with tempfile.TemporaryDirectory() as d:
            ext, md = _build(
                d, "$$\nE=mc^2 \\tag{3.1}\n$$\n",
                ["By (3.1) we get A.", "and hence by (3.5) and (3.1)"],
                None)
            res = _run(ext, md, 2)
            self.assertEqual([r['number'] for r in res['q_missing']], ['3.5'])

    def test_dot_key_still_works(self):
        """点形键（既有形态）行为不变。"""
        with tempfile.TemporaryDirectory() as d:
            ext, md = _build(
                d, "$$\nE=mc^2 \\tag{3.1}\n$$\n",
                ["By (3.1) we get A.", "and hence by (3.5)"],
                {"3.5": "印面确证：真噪声。"})
            res = _run(ext, md, 2)
            self.assertEqual([r['number'] for r in res['q_missing']], [])

    def test_unregistered_number_still_reported(self):
        """🔴 不得过度豁免：同一章里未登记的号照旧 MISSING。"""
        with tempfile.TemporaryDirectory() as d:
            ext, md = _build(
                d, "$$\nE=mc^2 \\tag{3.1}\n$$\n",
                ["By (3.1) we get A.", "and hence by (3.5) and (3.9)"],
                {"3-5": "印面确证：真噪声。"})
            res = _run(ext, md, 2)
            self.assertEqual(sorted(r['number'] for r in res['q_missing']),
                             ['3.9'])

    def test_scoped_key_does_not_leak_globally(self):
        """🔴 `sec#num` 作用域键不得在纯章路径当全局屏蔽用（只在分节路径按节生效）。"""
        with tempfile.TemporaryDirectory() as d:
            ext, md = _build(
                d, "$$\nE=mc^2 \\tag{3.1}\n$$\n",
                ["By (3.1) we get A.", "and hence by (3.5)"],
                {"3.2#3.5": "作用域键：只应屏蔽 §3.2 内的 3.5。"})
            res = _run(ext, md, 2)
            self.assertEqual([r['number'] for r in res['q_missing']], ['3.5'])

    def test_hyphen_key_silences_fabricated_side(self):
        """同形状修复在 FABRICATED 一侧同样成立（并集只减不增）。"""
        with tempfile.TemporaryDirectory() as d:
            ext, md = _build(
                d, "$$\nE=mc^2 \\tag{3.1}\n$$\n\n$$\nz \\tag{3.5}\n$$\n",
                ["By (3.1) we get A."],          # S = {3.1}；3.5 书源没有
                None)
            self.assertEqual([r['number'] for r in _run(ext, md, 1)['q_fabricated']],
                             ['3.5'])
            with open(os.path.join(ext, 'ignore_ch3.json'), 'w',
                      encoding='utf-8') as f:
                json.dump({"3-5": "OCR 噪声号，印面无此编号。"}, f,
                          ensure_ascii=False, indent=2)
            res = _run(ext, md, 1)
            self.assertEqual(res['q_fabricated'], [])
            self.assertEqual(res['q_missing'], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
