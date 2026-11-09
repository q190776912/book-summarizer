# -*- coding: utf-8 -*-
"""`merge_all` 证据闸：结构契约损坏必须硬拒，不得 fail-open（2026-11-09 审计）。

旧实现 `_contract_names_missing` 在 `json.load` 抛异常时 `return None`，而调用方
用 `if miss:` 判空 → 契约损坏时「骨架节 / 编号项在位」整章核对被静默放行。
现在返回一条明确的失败项，经 `missing_names` 走硬拒并把路径带进报错。

负向锁：契约**不存在**仍保持老行为（返回 None），由 structure 闸另行兜底，
不在本判据里擅自改变历史书行为。
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

from flows._flow_contract import physical_evidence  # noqa: E402


class TestContractNamesMissingFailClosed(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.ex = os.path.join(self.td.name, "_extract")
        os.makedirs(os.path.join(self.ex, "book_structure"))
        self.md = os.path.join(self.td.name, "ch1.md")
        with open(self.md, "w", encoding="utf-8") as fh:
            fh.write("# Chapter 1\n\nSome text.\n")

    def tearDown(self):
        self.td.cleanup()

    def test_corrupt_contract_is_hard_failure(self):
        cp = os.path.join(self.ex, "book_structure", "ch1.json")
        with open(cp, "w", encoding="utf-8") as fh:
            fh.write("{ this is not json")
        miss = physical_evidence._contract_names_missing(self.ex, 1, [self.md])
        self.assertTrue(miss)
        self.assertIn(u"结构契约读取失败", miss[0])
        self.assertIn("ch1.json", miss[0])

    def test_absent_contract_keeps_legacy_skip(self):
        miss = physical_evidence._contract_names_missing(self.ex, 1, [self.md])
        self.assertIsNone(miss)


class TestMergePresentOkFailClosed(unittest.TestCase):
    """整体闸：损坏契约必须让 _merge_present_ok 硬拒，且原因在 detail 里可见。

    只 mock 前置的「产物在位」查询（_src_manifest / _md_group_lang），
    `_contract_names_missing` 与 `_missing_contract_names` 都走真实实现，
    因此这条测的是从证据复核入口到硬拒消息的完整链路。
    """

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.ex = os.path.join(self.td.name, "_extract")
        os.makedirs(os.path.join(self.ex, "book_structure"))
        self.md = os.path.join(self.td.name, "ch1.md")
        with open(self.md, "w", encoding="utf-8") as fh:
            fh.write("# Chapter 1\n\nSome text.\n")

    def tearDown(self):
        self.td.cleanup()

    def _run(self):
        import flows._flow_contract as fc
        from unittest import mock
        pe = fc.physical_evidence
        with mock.patch.object(pe, "_src_manifest",
                               return_value={"language": "cn"}), \
             mock.patch.object(pe, "_md_group_lang",
                               return_value=[self.md]), \
             mock.patch.object(pe, "_tgt_language", return_value=None), \
             mock.patch.object(fc, "chapter_kind", return_value=2,
                               create=True):
            return pe._merge_present_ok(self.td.name, self.ex, [1], False)

    def test_corrupt_contract_is_hard_reject(self):
        cp = os.path.join(self.ex, "book_structure", "ch1.json")
        with open(cp, "w", encoding="utf-8") as fh:
            fh.write("{ not json")
        ok, detail = self._run()
        self.assertFalse(ok)
        self.assertIn(u"结构契约读取失败", detail)

    def test_valid_contract_no_spurious_reject(self):
        """负向锁：合法契约不得因读取失败闸被误拒。"""
        cp = os.path.join(self.ex, "book_structure", "ch1.json")
        with open(cp, "w", encoding="utf-8") as fh:
            json.dump({"nodes": []}, fh)
        _ok, detail = self._run()
        self.assertNotIn(u"结构契约读取失败", detail)


if __name__ == "__main__":
    unittest.main(verbosity=2)
