# -*- coding: utf-8 -*-
"""`register_formula.py` is the only sanctioned writer of `formula.known_book`.

`known_book` 登记「原书确有、抽取器读不到」的公式编号（页边号与正文粘连、左括号
被 OCR 读成字母等，Apostol IANT ch2 的 `(4)` 实测为 `C4)`）。它是 Q 层与写源闸门
⑭ 共用的人工确证通道，因此**登记纪律必须可机械执行**，否则白名单会变成遮丑工具：

  1. **契约已登记且 Q 层页窗收得到**的号 → 拒绝（门控本来就要求写手写它，挂号=把
     漏写洗白）；契约已登记但**页窗收不到**（页边号整块漏读）→ 放行，因为登记只解除
     Q 的 FABRICATED、门控判据 ③ 仍要求写手写 `\tag`；
  2. 无 `--evidence`（印面目视证据）→ 拒绝；
  3. 手写/手改的 `verify_config.json`（无 `_provenance`）→ 拒绝；
  4. 契约缺档即可登记，**即使 Q 层页扫描收得到**（内联粘连编号：契约里没有可挂
     `tag` 的展示式，闸门 ⑱ 的回填修法无从下手）——账本记 `contract_missing` /
     `harvested` 两标记并打印「优先回填契约」提示；
  5. 写回保留原换行风格、同号幂等；
  6. `make_config --force` 重生成不得清空登记（`_load_old_formula` 保留两键）。

Runs under stdlib unittest:
  python config/verify_config/tests/test_register_formula.py
"""
import json
import os
import shutil
import subprocess
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

import make_config as MC

CLI = os.path.join(_ROOT, "config/verify_config/register_formula.py")


def _mk_ext(pages, cfg, crlf=False):
    """pages = per-page list of block texts; cfg = verify_config dict."""
    ext = os.path.join(tempfile.mkdtemp(prefix="rf_"), "_extract")
    os.makedirs(ext, exist_ok=True)
    with open(os.path.join(ext, "chapter_map.json"), "w", encoding="utf-8") as f:
        json.dump({"chapters": [{"kind": 1, "num": 2, "name": "Ch2",
                                 "start": 1, "end": len(pages)}]}, f)
    for i, blocks in enumerate(pages, start=1):
        with open(os.path.join(ext, "page_%03d.json" % i), "w",
                  encoding="utf-8") as f:
            json.dump({"text": [{"text": b, "poly": [0, 40, 200, 52]}
                                for b in blocks]}, f)
    text = json.dumps(cfg, ensure_ascii=False, indent=2)
    if crlf:
        text = text.replace("\n", "\r\n")
    with open(os.path.join(ext, "verify_config.json"), "wb") as f:
        f.write(text.encode("utf-8"))
    return ext


def _cfg(with_prov=True):
    node = {"ordinal": [], "formula": {"type": 1, "scope": 3, "ignore": [],
                                       "bare_number": False}}
    if with_prov:
        node["_provenance"] = {"generated_by": "make_config.py"}
    return {"ch": node}


def _run(ext, *args):
    return subprocess.run([sys.executable, CLI, ext] + list(args),
                          cwd=_ROOT, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=300,
                          encoding="utf-8", errors="replace")


def _formula(ext):
    with open(os.path.join(ext, "verify_config.json"), encoding="utf-8") as f:
        return json.load(f)["ch"]["formula"]


def _mk_contract(ext, chapter, tags):
    """写一份最小内容化契约：description 节点带 ``len(tags)`` 个展示公式块（各挂 tag）。

    这就是单元门控判据 ③ 读的同一真值源（``chapter_tag_map``）。
    """
    d = os.path.join(ext, "book_structure")
    os.makedirs(d, exist_ok=True)
    tree = {"key": str(chapter), "type": "chapter", "name": "Ch%s" % chapter,
            "page_start": 1, "page_end": 3,
            "sub_sec": [{"key": "D1", "type": "description", "name": "",
                         "page_start": 1, "page_end": 3,
                         "sub_sec": [{"formula": "x = %s" % t, "display": True,
                                      "tag": t} for t in tags]}]}
    p = os.path.join(d, "ch%s.json" % chapter)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(tree, f, ensure_ascii=False)
    return p


PAGES = [["(5)", "the next display has no readable label C7)"]]


class TestRegistration(unittest.TestCase):
    def tearDown(self):
        for d in getattr(self, "_dirs", []):
            shutil.rmtree(os.path.dirname(d), ignore_errors=True)
        self._dirs = []

    def _mk(self, cfg=None, crlf=False):
        ext = _mk_ext(PAGES, cfg if cfg is not None else _cfg(), crlf=crlf)
        self._dirs = getattr(self, "_dirs", []) + [ext]
        return ext

    def test_unharvestable_number_registers_with_evidence(self):
        ext = self._mk(crlf=True)
        rc = _run(ext, "--chapter", "2", "--number", "7",
                  "--evidence", "fitz p001 左缘目视确有 (7)，OCR 读成 C7)")
        self.assertEqual(rc.returncode, 0, rc.stderr[-400:])
        fm = _formula(ext)
        self.assertEqual(fm["known_book"], ["7"])
        self.assertEqual(fm["known_book_audit"][0]["chapter"], 2)
        self.assertIn("fitz", fm["known_book_audit"][0]["evidence"])
        with open(os.path.join(ext, "verify_config.json"), "rb") as fh:
            raw = fh.read()
        self.assertIn(b"\r\n", raw, "写回破坏了原文件 CRLF 换行风格")

    def test_number_in_contract_and_harvestable_is_refused(self):
        # 契约在档 **且** Q 层页窗收得到 = 写手两头都被要求写出该号，
        # 挂号只会把漏写（或 tag 挂错公式）洗白 → 拒绝。
        ext = self._mk()
        _mk_contract(ext, 2, ["5"])
        rc = _run(ext, "--chapter", "2", "--number", "5",
                  "--evidence", "此书该号契约已登记，写手漏写才是问题")
        self.assertNotEqual(rc.returncode, 0)
        self.assertIn("契约已登记", rc.stderr)
        self.assertIn("Q 层页窗收得到", rc.stderr)
        self.assertEqual(_formula(ext).get("known_book"), None)

    def test_number_in_contract_but_unharvestable_registers(self):
        # 「页边号整块漏读」形态（Underactuated Robotics ch7 `(6)` 实测：出版社
        # 文字层右缘有独立行 `(6)`，OCR 把该块整块漏掉，页 JSON 里只剩散文回指
        # `satisfying (6)`，而 Q 的形态判据刻意不收散文回指）。
        # 此时登记**只**解除 Q 层的 FABRICATED；门控判据 ③（契约 tag 真值）照旧
        # 要求写手写 `\tag`，漏写仍 FAIL → 洗白不了任何东西，必须放行，
        # 否则「Q 要写 / Q 又判编造」与「契约要写」两头互斥，无解。
        ext = self._mk()
        _mk_contract(ext, 2, ["7"])
        rc = _run(ext, "--chapter", "2", "--number", "7",
                  "--evidence", "fitz p001 右缘目视确有独立的 (7)，"
                                "该块 OCR 整块漏读，页 JSON 只剩散文回指")
        self.assertEqual(rc.returncode, 0, rc.stderr[-400:])
        self.assertIn("Q 层页窗收不到", rc.stdout)
        fm = _formula(ext)
        self.assertEqual(fm["known_book"], ["7"])
        entry = fm["known_book_audit"][0]
        self.assertEqual(entry["harvested"], False)
        self.assertEqual(entry["contract_missing"], False)
        self.assertNotIn("契约无档", rc.stdout)

    def test_harvested_but_absent_from_contract_registers(self):
        # 内联粘连编号：Q 层页扫描收得到 `(5)`，契约里却没有可挂 tag 的展示式
        # （整条式子是行内公式、编号粘在散文块尾）——三头堵的正主，必须可登记。
        ext = self._mk()
        _mk_contract(ext, 2, ["9"])
        rc = _run(ext, "--chapter", "2", "--number", "5",
                  "--evidence", "fitz p001 印面确有 (5)，编号与公式同行粘连，契约无档")
        self.assertEqual(rc.returncode, 0, rc.stderr[-400:])
        self.assertIn("契约无档", rc.stdout)
        fm = _formula(ext)
        self.assertEqual(fm["known_book"], ["5"])
        self.assertEqual(fm["known_book_audit"][0]["harvested"], True)
        self.assertEqual(fm["known_book_audit"][0]["contract_missing"], True)

    def test_unharvestable_registration_is_not_flagged_harvested(self):
        ext = self._mk()
        _mk_contract(ext, 2, ["9"])
        rc = _run(ext, "--chapter", "2", "--number", "7",
                  "--evidence", "fitz p001 左缘目视确有 (7)，OCR 读成 C7)")
        self.assertEqual(rc.returncode, 0, rc.stderr[-400:])
        entry = _formula(ext)["known_book_audit"][0]
        self.assertEqual(entry.get("harvested"), False)
        self.assertNotIn("契约无档", rc.stdout)

    def test_missing_evidence_is_refused(self):
        ext = self._mk()
        rc = _run(ext, "--chapter", "2", "--number", "7")
        self.assertNotEqual(rc.returncode, 0)
        self.assertIn("--evidence", rc.stderr)
        self.assertEqual(_formula(ext).get("known_book"), None)

    def test_hand_written_config_is_refused(self):
        ext = self._mk(_cfg(with_prov=False))
        rc = _run(ext, "--chapter", "2", "--number", "7",
                  "--evidence", "印面确有，但配置是手写的")
        self.assertNotEqual(rc.returncode, 0)
        self.assertIn("_provenance", rc.stderr)

    def test_reregistering_same_number_is_idempotent(self):
        ext = self._mk()
        ev = "fitz p001 左缘目视确有 (7)，OCR 读成 C7)"
        self.assertEqual(_run(ext, "--chapter", "2", "--number", "7",
                              "--evidence", ev).returncode, 0)
        rc = _run(ext, "--chapter", "2", "--number", "(7)", "--evidence", ev)
        self.assertEqual(rc.returncode, 0, rc.stderr[-300:])
        self.assertEqual(_formula(ext)["known_book"], ["7"])
        self.assertEqual(len(_formula(ext)["known_book_audit"]), 1)

    def test_dry_run_writes_nothing(self):
        ext = self._mk()
        rc = _run(ext, "--chapter", "2", "--number", "7",
                  "--evidence", "fitz p001 左缘目视确有 (7)", "--dry-run")
        self.assertEqual(rc.returncode, 0, rc.stderr[-300:])
        self.assertEqual(_formula(ext).get("known_book"), None)


class TestForceKeepsRegistration(unittest.TestCase):
    def test_load_old_formula_preserves_known_book_and_audit(self):
        ext = _mk_ext(_PAGES_EMPTY, {"ch": {
            "formula": {"type": 1, "scope": 3,
                        "known_book": ["4"],
                        "known_book_audit": [{"number": "4", "chapter": 2,
                                              "evidence": "fitz p039"}]}}})
        out = MC._load_old_formula(os.path.join(ext, "verify_config.json"), "ch")
        self.assertEqual(out["known_book"], ["4"])
        self.assertEqual(out["known_book_audit"][0]["evidence"], "fitz p039")
        shutil.rmtree(os.path.dirname(ext), ignore_errors=True)

    def test_no_registration_stays_absent(self):
        # 零回归：从未登记的书不得凭空长出 known_book。
        ext = _mk_ext(_PAGES_EMPTY, {"ch": {"formula": {"type": 1, "scope": 3}}})
        self.assertIsNone(
            MC._load_old_formula(os.path.join(ext, "verify_config.json"), "ch"))
        shutil.rmtree(os.path.dirname(ext), ignore_errors=True)


_PAGES_EMPTY = [["x = y"]]

if __name__ == "__main__":
    unittest.main(verbosity=2)
