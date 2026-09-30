"""test_sync_markers_contract_path.py — 首行复位工具的**契约路径解析**（补篇/附录/章三型）。

缺陷根因（Katok《Modern Theory of Dynamical Systems》实测 2026-09-29）：
`tools/sync_translate_markers.py` 的 `contract_names` / `contract_unit_types` 只手写了两
个候选路径（`ch{N}.json`、`appendix{X}.json`），**补篇契约 `supplement{S}.json` 永远读不到**。
于是该章 `names` 为空集，`manifest_matches_contract` 对任何非空 `name` 都返回 False →
supplementS 的 41 个单元全部被判成「manifest 与契约脱账，须先修 manifest」而跳过复位：
门控要求的标记↔manifest 对账在补篇上**整体空转**，且提示语把责任错指给 manifest。

修复形态：契约路径一律走 SSOT `resolve_chapter_json_path`（先按注册表算，再按磁盘物理证据
回退其余章型，绝不凭空造契约）。

正向：章 / 附录 / 补篇三型都能取到契约 `name`；manifest 合契约 → 列为待复位，`--apply` 后
首行逐字等于 manifest、**首行以外字节不变**。
负向：manifest 的 `name` 不在契约账上 → 跳过并提示「须先修 manifest」，文件一字节不动。
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
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "lib"))
import lib.boot as _boot  # noqa: E402
_boot.setup()

import importlib.util  # noqa: E402

_SPEC = importlib.util.spec_from_file_location(
    "sync_translate_markers",
    os.path.join(_ROOT, "tools", "sync_translate_markers.py"))
STM = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(STM)

NAME_S = "S.4-15 S.4.15. Given a diffeomorphism f: M of a compact"
NAME_A = "A.1.1 Point-set topology"
NAME_1 = "1.1.1 First examples"


def _mk_contract(path, key, name):
    root = {"key": key.split(".")[0], "type": "chapter", "name": "Ch",
            "page_start": 1, "page_end": 9, "consolidated": False,
            "sub_sec": [{"type": "definition", "key": key, "name": name,
                         "page_start": 2, "page_end": 2, "sub_sec": []}]}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(root, f, ensure_ascii=False)


def _mk_unit(d, file, marker, body):
    p = os.path.join(d, file)
    with open(p, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(marker + "\r\n" + body + "\r\n")
    return p


class TestContractPathResolution(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ext = os.path.join(self.tmp.name, "_extract")
        bs = os.path.join(self.ext, "book_structure")
        os.makedirs(bs)
        with open(os.path.join(self.ext, "chapter_map.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"chapters": [
                {"kind": 1, "num": "1", "start": 1, "end": 9, "name": "1 First"},
                {"kind": 2, "num": "A", "start": 10, "end": 20, "name": "Appendix A"},
                {"kind": 3, "num": "S", "start": 21, "end": 40, "name": "Supplement S"}]},
                f, ensure_ascii=False)
        _mk_contract(os.path.join(bs, "ch1.json"), "1.1-1", NAME_1)
        _mk_contract(os.path.join(bs, "appendixA.json"), "A.1-1", NAME_A)
        _mk_contract(os.path.join(bs, "supplementS.json"), "S.4-15", NAME_S)
        STM.prime_chapter_kinds(self.ext)

    def tearDown(self):
        self.tmp.cleanup()

    def _side(self, sub, ch, manifest_name, marker_name=None, body="body text"):
        d = os.path.join(self.ext, "book_structure", sub, STM.unit_dir_name(ch))
        os.makedirs(d, exist_ok=True)
        rec = {"file": "0001_item.md", "id": "0001", "type": "item",
               "key": {"1": "1.1-1", "A": "A.1-1", "S": "S.4-15"}[ch],
               "name": manifest_name}
        with open(os.path.join(d, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"units": [rec]}, f, ensure_ascii=False)
        marker = STM.TPL % ("DONE", rec["id"], rec["type"], rec["key"],
                            marker_name if marker_name is not None else manifest_name)
        p = _mk_unit(d, rec["file"], marker, body)
        return d, p

    def test_supplement_contract_is_read(self):
        """核心负向回归：补篇契约必须读得到 name（旧实现返回空集 → 整章空转）。"""
        for ch, want in (("1", NAME_1), ("A", NAME_A), ("S", NAME_S)):
            self.assertIn(want, STM.contract_names(self.ext, ch),
                          "章 %s 的契约 name 未被读到（契约路径解析漏章型）" % ch)
        self.assertIn("S.4-15", STM.contract_unit_types(self.ext, "S"))

    def test_reset_happens_when_manifest_matches_contract(self):
        d, p = self._side("units", "S", NAME_S, marker_name="S.4-15 S.4.15. Given a")
        checked, changed, diffs = STM.sync_side(self.ext, "units", "S", False)
        self.assertEqual((checked, changed), (1, 1))
        self.assertNotIn("跳过", "".join(diffs))
        with open(p, "rb") as f:
            before = f.read()
        STM.sync_side(self.ext, "units", "S", True)
        with open(p, "rb") as f:
            after = f.read()
        head, _, rest_b = before.partition(b"\r\n")
        head_a, _, rest_a = after.partition(b"\r\n")
        self.assertNotEqual(head, head_a)
        self.assertEqual(rest_a, rest_b, "复位改动了首行以外的字节")
        self.assertIn("name=" + NAME_S, head_a.decode("utf-8"))
        self.assertTrue(os.path.isdir(d))

    def test_manifest_not_on_contract_book_skips_and_does_not_write(self):
        """manifest 的 name 不在契约账上 → 跳过复位（须先修 manifest），文件不动。"""
        _, p = self._side("units", "S", "S.4-15  totally different title")
        with open(p, "rb") as f:
            before = f.read()
        checked, changed, diffs = STM.sync_side(self.ext, "units", "S", True)
        self.assertEqual((checked, changed), (1, 0))
        self.assertIn("须先修 manifest", "".join(diffs))
        with open(p, "rb") as f:
            self.assertEqual(f.read(), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
