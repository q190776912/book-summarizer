"""Tests for lib/content_overrides.py — ① 复算闸的人工裁定账本（2026-09-29）。

动因（Iwaniec–Kowalski GTM207 实测）：①「确定性复算比对」把磁盘契约与
`attach_content.build_chapter_contract` 的重算做内容块多重集比对。印面裁定
（把 OCR 漏挂的 `(1.104)` 回填到正确的式上）天然让磁盘偏离纯重算，于是对的契约
被报成「缺块 + 多块」假 FAIL。本账本把裁定变成**管线输入**，并守住三条：

  * `apply_overrides` 真的改重算结果（drop 摘块 / retag 挪号、清空号）；
  * `disk_audit` 看得见登记腐烂（磁盘仍有被 drop 的块 / tag 不等于登记值 /
    未知 op 一律报问题，不静默放行）；
  * `load` 兼容扁平与分组两种配置形状，坏文件退回空账本（判据不得因缺账本而崩）。

Run:  python lib/tests/test_content_overrides.py
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
    _ROOT = str(Path(__file__).resolve().parents[1])
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lib.boot as _boot  # noqa: E402
_boot.setup()
from lib import content_overrides as co  # noqa: E402


def _tree():
    """一棵最小契约树：一节里两条公式 + 两个噪声文本块。"""
    return {"key": "1", "type": "chapter", "name": "1 Intro", "sub_sec": [
        {"key": "1.1", "type": "section", "name": "1.1 Basics", "sub_sec": [
            {"text": "x)."},
            {"formula": "c ( P ) = 1", "display": True, "tag": ""},
            {"formula": "f ( n ) = sum", "display": True, "tag": "1.100"},
            {"text": "body prose stays"},
        ]},
    ]}


def _blocks(tree):
    return [b for _p, b in co._iter_blocks(tree)]


class TestApply(unittest.TestCase):
    def test_drop_removes_only_the_named_block(self):
        t = _tree()
        op = {"ch": "1", "op": "drop", "kind": "text", "match": "x)."}
        res = co.apply_overrides(t, [op])
        self.assertEqual(res[0][1], 1)                    # 命中 1 块
        texts = [b["text"] for b in _blocks(t) if "text" in b]
        self.assertEqual(texts, ["body prose stays"])     # 正文块不动

    def test_drop_counts_zero_hits_so_the_gate_can_call_it_dead(self):
        t = _tree()
        op = {"ch": "1", "op": "drop", "kind": "text", "match": "no such block"}
        self.assertEqual(co.apply_overrides(t, [op])[0][1], 0)

    def test_match_is_whitespace_collapse_not_substring(self):
        t = _tree()
        # 「c ( P ) = 1」的子串「P ) = 1」不得顺手吞掉整块
        op = {"ch": "1", "op": "drop", "kind": "formula", "match": "P ) = 1"}
        self.assertEqual(co.apply_overrides(t, [op])[0][1], 0)
        self.assertEqual(len([b for b in _blocks(t) if "formula" in b]), 2)

    def test_retag_moves_the_number(self):
        t = _tree()
        ops = [{"ch": "1", "op": "retag", "kind": "formula",
                "match": "c ( P ) = 1", "tag": "1.100"},
               {"ch": "1", "op": "retag", "kind": "formula",
                "match": "f ( n ) = sum", "tag": ""}]
        for _op, hits in co.apply_overrides(t, ops):
            self.assertEqual(hits, 1)
        fx = {b["formula"]: b.get("tag") for b in _blocks(t) if "formula" in b}
        self.assertEqual(fx["c ( P ) = 1"], "1.100")
        fblk = [b for b in _blocks(t) if b.get("formula") == "f ( n ) = sum"][0]
        self.assertNotIn("tag", fblk)                     # 清空 = 键不存在

    def test_retag_normalizes_padded_match(self):
        t = _tree()
        op = {"ch": "1", "op": "retag", "kind": "formula",
              "match": "  c   (  P )  =  1  ", "tag": "1.100"}
        self.assertEqual(co.apply_overrides(t, [op])[0][1], 1)


class TestDiskAudit(unittest.TestCase):
    def test_clean_ledger_passes(self):
        t = _tree()
        ops = [{"ch": "1", "op": "retag", "kind": "formula",
                "match": "c ( P ) = 1", "tag": "1.100"}]
        co.apply_overrides(t, ops)
        self.assertEqual(co.disk_audit(t, ops), [])

    def test_stale_drop_is_reported(self):
        # 登记说删了，磁盘还留着 → 必须报（否则 ① 的偏离无账）
        t = _tree()
        ops = [{"ch": "1", "op": "drop", "kind": "text", "match": "x)."}]
        problems = co.disk_audit(t, ops)
        self.assertEqual(len(problems), 1)
        self.assertIn("drop 未生效", problems[0])

    def test_wrong_tag_is_reported(self):
        t = _tree()
        ops = [{"ch": "1", "op": "retag", "kind": "formula",
                "match": "c ( P ) = 1", "tag": "9.999"}]
        self.assertIn("retag 未生效", co.disk_audit(t, ops)[0])

    def test_missing_block_for_retag_is_reported(self):
        t = _tree()
        ops = [{"ch": "1", "op": "retag", "kind": "formula",
                "match": "gone formula", "tag": "1.100"}]
        self.assertIn("retag 失配", co.disk_audit(t, ops)[0])

    def test_unknown_op_is_reported_not_ignored(self):
        t = _tree()
        ops = [{"ch": "1", "op": "merge", "kind": "text", "match": "x)."}]
        self.assertIn("未知 op", co.disk_audit(t, ops)[0])


class TestLoad(unittest.TestCase):
    def _write(self, cfg):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "verify_config.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False)
        return d

    def test_grouped_and_flat_shapes(self):
        ops = [{"ch": "1", "op": "drop", "kind": "text", "match": "x)."}]
        grouped = self._write({"ch": {co.KEY: ops}})
        flat = self._write({co.KEY: ops})
        self.assertEqual(len(co.ops_for(grouped, "1")), 1)
        self.assertEqual(len(co.ops_for(flat, "1")), 1)
        self.assertEqual(co.ops_for(grouped, "2"), [])

    def test_special_sections_harvest_too(self):
        d = self._write({"appendix": {co.KEY: [{"ch": "A", "op": "drop",
                                                "kind": "text", "match": "z"}]}})
        self.assertEqual(len(co.ops_for(d, "A")), 1)

    def test_missing_or_broken_config_is_empty_ledger(self):
        self.assertEqual(co.load(tempfile.mkdtemp()), {})
        d = self._write("not-a-dict")
        with open(os.path.join(d, "verify_config.json"), "w", encoding="utf-8") as f:
            f.write("{ this is not json")
        self.assertEqual(co.load(d), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
