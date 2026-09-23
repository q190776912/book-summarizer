r"""
test_verbose_gates_dashkey.py — P 层「编造条目」契约键归一化回归。

build_structure 对判型不稳的节点把契约键写成 dash 形（'6.1-5'），而 md 渲染为
点分（`**6.1.5**: ...`）。旧 _load_contract 只收 `^\d+\.\d+\.\d+$` 的点分键，
dash 键漏登记 → P 层把契约里真实存在的条目报成「编造条目」（Leinster BCT ch6
实测 15 处假 BLOCKING）。修复 = 收集时对键做 _norm_secnum 归一。
反向用例：契约确无此编号仍必须报（不得放松成永真）。
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

from verbose_gates import check_extra_items


def _mk_ext(dash_key, dot_key, exercise_keys=()):
    d = tempfile.mkdtemp()
    bs = os.path.join(d, 'book_structure')
    os.makedirs(bs)
    contract = {
        "key": "9", "type": "chapter", "name": "Chapter 9",
        "sub_sec": [
            {"key": "9.1", "type": "section", "name": "9.1 S", "sub_sec": [
                {"key": dash_key, "type": "description", "name": "x",
                 "sub_sec": []},
            ]},
        ],
    }
    if dot_key:
        contract["sub_sec"][0]["sub_sec"].append(
            {"key": dot_key, "type": "proposition", "name": "y", "sub_sec": []})
    for ek in exercise_keys:
        contract["sub_sec"][0]["sub_sec"].append(
            {"key": ek, "type": "exercise", "name": "ex", "sub_sec": []})
    with open(os.path.join(bs, 'ch9.json'), 'w', encoding='utf-8') as f:
        json.dump(contract, f, ensure_ascii=False)
    return d


class DashKeyContractTest(unittest.TestCase):
    def test_dash_contract_key_admits_dotted_md_item(self):
        ext = _mk_ext('9.1-5', '9.1.6')
        lines = ["**9.1.5**: Interpret all the theory of this section.",
                 "**Proposition 9.1.6**: dual statement."]
        self.assertEqual(check_extra_items(lines, ext, 9), [])

    def test_unknown_number_still_flagged(self):
        ext = _mk_ext('9.1-5', '9.1.6')
        lines = ["**9.1.9**: This number is in no contract."]
        out = check_extra_items(lines, ext, 9)
        self.assertEqual(len(out), 1, out)
        self.assertIn('编造条目', out[0])

    def test_exercise_node_key_admits_dotted_md_header(self):
        # Leinster-style: exercises share the section item counter and are
        # written as bare dotted `**9.1.13**` headers (not `**Exercise …**`).
        # They are contract `exercise` nodes and must NOT be flagged fabricated.
        ext = _mk_ext('9.1-5', None, exercise_keys=('9.1.12', '9.1.13'))
        lines = ["**9.1.12**: Find three examples of adjoint functors.",
                 "**9.1.13**: What can be said about adjunctions?"]
        self.assertEqual(check_extra_items(lines, ext, 9), [])

    def test_invented_exercise_number_still_flagged(self):
        ext = _mk_ext('9.1-5', None, exercise_keys=('9.1.13',))
        lines = ["**9.1.99**: No such exercise exists in the contract."]
        out = check_extra_items(lines, ext, 9)
        self.assertEqual(len(out), 1, out)
        self.assertIn('编造条目', out[0])


if __name__ == '__main__':
    unittest.main()
