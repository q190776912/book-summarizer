# -*- coding: utf-8 -*-
r"""Regression: 落账证据趟（`physical_evidence._units_gate_ok`）的契约 tag **按 key
回退**必须带「同键唯一单元」守卫，与权威 CLI `gate_units` 同源。

2026-10-01 Koopman《Koopman Operator》`flow_runner status` 证据复演报
「ch12 单元 0029_item_定理12_5.md 缺编号公式 \tag{12.42}」，而 `gate_units.py … 12`
PASS、全 40 章 verify PASS。根因：老 manifest 无 `tags` 字段 → shadow 回退
`chapter_tag_map[key]` 聚合；契约里 `定理12.5` 是 p343/p344 **两个节点**（仅前者
携带 (12.42)），拆成两个同键单元记录后，回退把 (12.42) 也要求到后半单元头上 =
恒假缺号。gate_units 早已为同一实测加守卫（仅当该 key 在本章只对应一个单元才
回退，Koopman ch12 注释），shadow 的内联复刻漏了它 → 权威趟放行、落账趟打回。

钉住两向：
- 同键多单元：回退**不生效**，后半单元不被罚「缺编号公式」（正向）。
- 同键唯一单元：回退**仍生效**，缺 tag 照罚（负向，防豁免扩大化）。
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
    _ROOT = str(Path(__file__).resolve().parents[4])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
import lib.boot  # noqa: E402
lib.boot.setup()

from flows._flow_contract import physical_evidence as pe  # noqa: E402

_MARK27 = ("<!-- book-summarizer DONE unit: id=0027 type=item key=定理12.5 "
           "name=定理12.5 Theorem 12.5 -->\n")
_MARK29 = ("<!-- book-summarizer DONE unit: id=0029 type=item key=定理12.5 "
           "name=定理12.5 12.5 -->\n")
_U27 = ("**Theorem 12.5**: System (12.41) is quadratic stabilizable if and only "
        "if there exists a symmetric matrix $P$ solving the LMIs\n\n$$\n"
        "P\\varLambda + \\varLambda^{\\top}P \\prec 0,\n\\tag{12.42}\n$$\n")
_U29 = ("**Theorem 12.5** (continued): equivalently, quadratic stabilizability "
        "fails exactly when some nonzero $\\mathbf{z}$ makes the drift term "
        "nonnegative while the control term vanishes.\n")


def _tree(units):
    """造 <ex>/book_structure/{ch12.json, units/ch12/…} + verify_config（公式层开）。"""
    ex = tempfile.mkdtemp()
    bs = os.path.join(ex, "book_structure")
    ud = os.path.join(bs, "units", "ch12")
    os.makedirs(ud)
    contract = {
        "key": "12", "type": "chapter", "name": "Ch 12", "sub_sec": [
            {"key": "定理12.5", "type": "theorem", "name": "Theorem 12.5",
             "page_start": 343, "page_end": 343,
             "sub_sec": [{"type": "formula", "tag": "12.42",
                          "text": "P\\varLambda + \\varLambda^{\\top}P < 0"}]},
            {"key": "定理12.5", "type": "theorem", "name": "12.5",
             "page_start": 344, "page_end": 344, "sub_sec": []},
        ],
    }
    with open(os.path.join(bs, "ch12.json"), "w", encoding="utf-8") as f:
        json.dump(contract, f, ensure_ascii=False)
    with open(os.path.join(ex, "verify_config.json"), "w", encoding="utf-8") as f:
        json.dump({"formula": {"known_book": []}}, f)
    man = {"language": "en", "units": []}
    for name, mark, body in units:
        with open(os.path.join(ud, name), "w", encoding="utf-8",
                  newline="") as f:
            f.write(mark + body)
        key = mark.split("key=")[1].split(" name=")[0]
        man["units"].append({"file": name, "type": "item", "key": key,
                             "name": key})
    with open(os.path.join(ud, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False)
    return ud, man


class SameKeyTagFallback(unittest.TestCase):
    def test_duplicate_key_second_unit_not_flagged(self):
        """同键两单元（后半天然不带 (12.42)）：不得报「缺编号公式 \tag{12.42}」。"""
        ud, man = _tree([
            ("0027_item_定理12_5.md", _MARK27, _U27),
            ("0029_item_定理12_5.md", _MARK29, _U29),
        ])
        ok, problems = pe._units_gate_ok(ud, man, ch_key="12")
        joined = "；".join(problems)
        self.assertNotIn("12.42", joined, problems)
        self.assertNotIn("缺编号公式", joined, problems)

    def test_unique_key_fallback_still_enforced(self):
        """同键唯一单元：回退仍生效，缺 \tag 照罚（负向，防豁免扩大化）。"""
        ud, man = _tree([
            ("0029_item_定理12_5.md", _MARK29, _U29),
        ])
        ok, problems = pe._units_gate_ok(ud, man, ch_key="12")
        self.assertFalse(ok)
        self.assertTrue(any("12.42" in p and "缺" in p for p in problems),
                        problems)


if __name__ == "__main__":
    unittest.main(verbosity=2)
