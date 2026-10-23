# -*- coding: utf-8 -*-
"""audit_ignore 对「组索引伪组豁免键」（`gi:prefix:num`）的举证判定（2026-10-22）。

根因（《微分遍历论》实测）：B 层 emit 的豁免 token 形如 `0:5:2`——`ordinal[0]`（图组）
按章号收前缀、把 uncat 裸键（节标题 `5.1-1` / 条目号 `5.5-1` 等）误收成 item_num，
于是「0:5 组缺 2/3/4」是**伪洞**。此类键的正确救济就是写进 `ignore_chN.json`，但
`_canon_key_of` 只认点/划分隔的编号键，冒号组索引键一律落到 SKIP → 即使登记原因里
已经写好印面证据（本技能约定的 `VERIFIED-SPARSE` / 已核实跳号），审核报告也永远是
`ACCEPTED=0`：**带取证的豁免与裸静音在机器侧不可区分**，护栏只剩人眼。
（全库普查 2026-10-22：454 条冒号组索引键，437 条已带 VERIFIED-SPARSE 证据、
 17 条裸登记，全部处于 SKIP——不是只有本书的问题。）

判定（本测试锁定）：
  1. 理由带证据标记 → ACCEPTED（非阻断），并解析出组标签/前缀/号写进 why。
  2. 理由无证据标记 → NEEDS-EVIDENCE（点名要求补举证，**不阻断**：晚生判据不得把
     已收官书刷红；只可降级 / 回写 / 明说）。
  3. 单章审计也要呈现本章的伪组键（旧实现整批丢弃 → 调用方据 total 误判「已审」）。
  4. 非回归：真·三级序列洞（邻居都在契约）无证据仍 SUSPECT、有证据才 ACCEPTED；
     普通点分键 / 带标签键的解析行为不变。

运行：
  python verify/script/tests/test_group_token_ignore_attestation.py
"""
import io
import json
import os
import shutil
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
for _p in (_ROOT, os.path.join(_ROOT, "lib"),
           os.path.join(_ROOT, "verify", "script")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot  # noqa: E402
_boot.setup()

import audit_ignore as ai  # noqa: E402

VERIFY_CONFIG = {
    "ordinal": [
        {"type": 2, "name": ["图"], "scope": 2},
        {"type": 3, "name": ["定义", "定理"], "scope": 3},
    ],
    "strict": True,
    "language": "cn",
}

# 契约：5.1-1 / 5.1-3 在册 → 5.1-2 是真正的序列中间洞
CH5 = {
    "key": "5", "type": "chapter", "name": "5 章", "page_start": 1, "page_end": 2,
    "sub_sec": [
        {"key": "5.1", "type": "section", "name": "5.1 节",
         "page_start": 1, "page_end": 2, "sub_sec": []},
        {"key": "5.1-1", "type": "theorem", "name": "定理5.1.1",
         "page_start": 1, "page_end": 1, "sub_sec": []},
        {"key": "5.1-3", "type": "theorem", "name": "定理5.1.3",
         "page_start": 1, "page_end": 1, "sub_sec": []},
    ],
}

EVIDENCED = "VERIFIED-SPARSE: 已核对印面 p126-152，全章唯一插图是图5.1，无图5.2"
BARE = "伪组豁免：uncat 裸键被图组按章号误收，非真实缺号"


def _mk_extract():
    ext = tempfile.mkdtemp(prefix="ai_group_token_")
    os.makedirs(os.path.join(ext, "book_structure"))
    with io.open(os.path.join(ext, "verify_config.json"), "w", encoding="utf-8") as f:
        json.dump(VERIFY_CONFIG, f, ensure_ascii=False, indent=2)
    with io.open(os.path.join(ext, "book_structure", "ch5.json"), "w",
                 encoding="utf-8") as f:
        json.dump(CH5, f, ensure_ascii=False, indent=2)
    with io.open(os.path.join(ext, "chapter_map.json"), "w", encoding="utf-8") as f:
        json.dump({"chapters": [{"num": 5, "start": 1, "end": 2}]}, f,
                  ensure_ascii=False)
    ignore = {
        "0:5:2": EVIDENCED,       # 带取证的伪组豁免 → ACCEPTED
        "0:5:3": BARE,            # 裸豁免 → NEEDS-EVIDENCE（不阻断）
        "5.1-2": BARE,            # 真序列洞、无证据 → SUSPECT
        "定理 5.4": EVIDENCED,    # 带标签点分键：剥标签后解析为 (5,4) 两级 → SAFE
    }
    with io.open(os.path.join(ext, "ignore_ch5.json"), "w", encoding="utf-8") as f:
        json.dump(ignore, f, ensure_ascii=False, indent=2)
    return ext


class TestGroupTokenParsing(unittest.TestCase):
    def test_colon_group_token_forms(self):
        self.assertEqual(ai._group_token_of("0:5:2"), (0, "5", 2))
        self.assertEqual(ai._group_token_of("12::3"), (12, "", 3))
        self.assertEqual(ai._group_token_of("0:A:1"), (0, "A", 1))
        self.assertIsNone(ai._group_token_of("5.3"))
        self.assertIsNone(ai._group_token_of("5.1-2"))
        self.assertIsNone(ai._group_token_of("图 5.2"))

    def test_canon_key_parse_unchanged(self):
        # 非回归：冒号键此前无法解析（返回 None）这一点不能变——否则 B 层的 `full`
        # 折叠匹配路径会被带标签键误命中。
        self.assertIsNone(ai._canon_key_of("0:5:2"))
        self.assertEqual(ai._canon_key_of("5.1-2"), (5, 1, 2))
        self.assertEqual(ai._canon_key_of("定理 5.4"), (5, 4))
        # 词表外的标签（图属 E 层命名空间）仍不可解析 —— 不属本审计
        self.assertIsNone(ai._canon_key_of("图 5.4"))


class TestGroupTokenVerdicts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ext = _mk_extract()
        cls.rep = ai.run_audit(cls.ext)
        cls.by_key = {r["key"]: r for r in cls.rep["entries"]}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.ext, ignore_errors=True)

    def test_evidenced_group_token_is_accepted(self):
        r = self.by_key["0:5:2"]
        self.assertEqual(r["verdict"], "ACCEPTED", r.get("why"))
        self.assertEqual(r["group"], {"index": 0, "label": "图", "prefix": "5", "num": 2})
        self.assertIn("图", r["why"])

    def test_bare_group_token_needs_evidence_but_does_not_block(self):
        r = self.by_key["0:5:3"]
        self.assertEqual(r["verdict"], "NEEDS-EVIDENCE", r.get("why"))
        self.assertEqual(self.rep["needs_evidence_count"], 1)
        self.assertNotIn(r["verdict"], ("SUSPECT", "SKIP"))

    def test_real_sequence_hole_still_suspect_without_evidence(self):
        r = self.by_key["5.1-2"]
        self.assertEqual(r["verdict"], "SUSPECT", r.get("why"))
        self.assertEqual(self.rep["suspect_count"], 1)

    def test_labelled_dot_key_still_parses_as_two_level(self):
        r = self.by_key["定理 5.4"]
        self.assertEqual(r["verdict"], "SAFE", r.get("why"))

    def test_no_skip_bucket_left_for_group_tokens(self):
        self.assertNotIn("SKIP", {r["verdict"] for r in self.rep["entries"]})


class TestSingleChapterAttribution(unittest.TestCase):
    def test_group_rows_appear_in_own_chapter_run(self):
        ext = _mk_extract()
        try:
            rep = ai.run_audit(ext, chapter=5)
            keys = {r["key"] for r in rep["entries"]}
            self.assertIn("0:5:2", keys)
            self.assertIn("0:5:3", keys)
            other = ai.run_audit(ext, chapter=1)
            self.assertNotIn("0:5:2", {r["key"] for r in other["entries"]})
        finally:
            shutil.rmtree(ext, ignore_errors=True)


class TestEvidenceRequiredForThreeLevelHole(unittest.TestCase):
    """带证据的三级序列洞仍走原 ACCEPTED 通道（改后不得收紧成人人待举证）。"""

    def test_accepted_with_evidence(self):
        ext = _mk_extract()
        try:
            p = os.path.join(ext, "ignore_ch5.json")
            d = json.load(io.open(p, encoding="utf-8"))
            d["5.1-2"] = EVIDENCED
            with io.open(p, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
            rep = ai.run_audit(ext)
            r = {x["key"]: x for x in rep["entries"]}["5.1-2"]
            self.assertEqual(r["verdict"], "ACCEPTED", r["why"])
            self.assertEqual(rep["suspect_count"], 0)
        finally:
            shutil.rmtree(ext, ignore_errors=True)


class TestBomIgnoreFileNotSilentlyDropped(unittest.TestCase):
    """PowerShell 写出的带 BOM sidecar 不得整文件静默丢弃。

    同一缺陷在 B 层 `_load_ignore_file` 已根治（Ross《Analysis on Manifolds》
    ignore_fig_ch3.json 实测 2026-10-01，注释明写「with plain utf-8 json.load raises
    and the WHOLE file was silently dropped」），但 audit_ignore 的 `_collect_ignore`
    仍用 plain utf-8 → 这些 ignore 条目对审核隐形（《概率统计》a-first-course…
    ignore_ch9.json 实测 2026-10-22：全书 18 条只审到 6 条）。
    """

    def test_bom_file_entries_are_collected(self):
        ext = _mk_extract()
        try:
            plain = os.path.join(ext, "ignore_ch5.json")
            body = io.open(plain, encoding="utf-8").read()
            with io.open(plain, "wb") as f:
                f.write((u"\ufeff" + body).encode("utf-8"))
            rep = ai.run_audit(ext)
            keys = {r["key"] for r in rep["entries"]}
            self.assertIn("0:5:2", keys, "带 BOM 的 ignore 文件必须照常入审")
            self.assertEqual(rep["accepted_count"], 1, rep["entries"])
        finally:
            shutil.rmtree(ext, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
