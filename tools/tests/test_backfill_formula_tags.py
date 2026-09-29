"""test_backfill_formula_tags.py — 回填丢失印刷公式编号的正规通道（三本账同步 + 拒绝面）。

缺陷根因（Apostol《Introduction to Analytic Number Theory》实测 2026-09-29）：抽取器收割
`tag` 时把印在编号列的 `(N)` 整块丢掉（编号与展示式粘连、`array` 多行逐行编号、跨页）。
契约无档 → 单元级 tag 对账**空转**：门控既不要求写手写 `\\tag{N}`，也不把写手照印面写出
的号判成编造；全书 368 个印面号里 18 个因此静默消失（`lib.tag_attestation.numbering_gaps`
一次数出，⑱/页池审计当时均报 0）。

修复形态：`tools/backfill_formula_tags.py` = 带断言的正规通道（印面佐证闸 + 备份 + JSONL
台账 + 「去掉新增 tag 即回到原字节」一致性断言），正文 `\\tag{}` 一本账留给人（工具打印待办）。

正向：dry-run 不落盘；--apply 后契约目标块有 `tag`、两侧 manifest `tags` 同步、**其余字节
逐字不变**、台账落一行、再跑为 NO-OP；--auto 由 ⑱ 判据定位；--needle / --block 定位。
负向（一律 exit 2 且零写入）：①无印面佐证 ②该号已在账（幂等 NO-OP，exit 0）③同键多单元
未指定 --unit ④节点里多个未挂号块却不给定位方式 ⑤--needle 命中 0/多个 ⑥目标是行内公式
（该走 register_formula）⑦`--number` 是 0/00 类 OCR 碎片 ⑧缺 --evidence ⑨契约不是
indent=2 标准形 ⑩节点键不存在。
"""
import io
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
    "backfill_formula_tags",
    os.path.join(_ROOT, "tools", "backfill_formula_tags.py"))
bft = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(bft)

TARGET = ("\\prod _ { p \\mid n } \\left( 1 - \\frac { 1 } { p } \\right) "
          "= \\prod _ { i = 1 } ^ { r }")
EV = "fitz 170dpi 渲染物理页37：(4) 印在多行展开式左缘编号列"


def _tree():
    item = {"key": "定理2.4", "type": "theorem", "name": "2.4 For n >= 1",
            "page_start": 37, "page_end": 37,
            "sub_sec": [
                {"formula": "\\varphi ( n ) = n \\prod", "display": True, "tag": "3"},
                {"text": "Suppose, then, that n > 1."},
                {"formula": TARGET, "display": True},
                {"text": "On the right, in a term such as"},
                {"formula": "\\sum _ { d \\mid n } \\frac { \\mu ( d ) } { d }",
                 "display": True},
                {"type": "proof", "key": "定理2.4-P1", "sub_sec": [
                    {"formula": "\\chi ( a ) = \\chi ( b )", "display": False}]},
            ]}
    subs = [item]
    return {"key": "2", "type": "chapter", "name": "2 Multiplicative functions",
            "page_start": 37, "page_end": 38, "sub_sec": subs}


def _man(entries):
    return {"chapter_key": "2", "language": "en", "final_md": "x.md", "units": entries}


def _entry(i, key, tags):
    return {"id": "%04d" % i, "file": "%04d_item_%s.md" % (i, key.replace(".", "_")),
            "type": "item", "ntype": "theorem", "key": key, "name": key,
            "tags": tags, "images": [], "content": 12, "hash": "deadbeef"}


def _mk(extract, translate=True, page_anchor=True, indent=2, dup_entry=False):
    bs = os.path.join(extract, "book_structure")
    u = os.path.join(bs, "units", "ch2")
    os.makedirs(u)
    tree = _tree()
    cpath = os.path.join(bs, "ch2.json")
    with io.open(cpath, "w", encoding="utf-8", newline="\n") as f:
        json.dump(tree, f, ensure_ascii=False, indent=indent)
    entries = [_entry(16, "定理2.4", ["3"])]
    if dup_entry:      # 同节内「定义 / 定理」共用序标的真实形态
        entries.append(_entry(17, "定理2.4", []))
    with io.open(os.path.join(u, "manifest.json"), "w", encoding="utf-8",
                 newline="\n") as f:
        json.dump(_man(entries), f, ensure_ascii=False, indent=2)
    if translate:
        ut = os.path.join(bs, "units-translate", "ch2")
        os.makedirs(ut)
        with io.open(os.path.join(ut, "manifest.json"), "w", encoding="utf-8",
                     newline="\n") as f:
            json.dump(_man([dict(e) for e in entries]), f, ensure_ascii=False,
                      indent=2)
    if page_anchor:
        with io.open(os.path.join(extract, "page_037.json"), "w", encoding="utf-8",
                     newline="\n") as f:
            json.dump({"page": 37, "text": [{"text": "(4)  product expansion",
                                             "score": 0.9}]},
                      f, ensure_ascii=False, indent=2)


def _run(extract, number="4", apply=False, evidence=EV, **flags):
    argv = [extract, "2", "--number", number, "--evidence", evidence]
    for k, v in flags.items():
        if v is True:
            argv.append("--" + k.replace("_", "-"))
        elif v is not False and v is not None:
            argv += ["--" + k.replace("_", "-"), str(v)]
    if apply:
        argv.append("--apply")
    return bft.main(argv)


def _read(p):
    return io.open(p, encoding="utf-8").read()


class BackfillFormulaTagsTest(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.E = self._td.name
        self.bs = os.path.join(self.E, "book_structure")
        self.u = os.path.join(self.bs, "units", "ch2")
        self.c = os.path.join(self.bs, "ch2.json")
        self.m = os.path.join(self.u, "manifest.json")

    def tearDown(self):
        self._td.cleanup()

    # ── 正向 ────────────────────────────────────────────────────────────
    def test_dry_run_writes_nothing(self):
        _mk(self.E)
        craw, mraw = _read(self.c), _read(self.m)
        self.assertEqual(_run(self.E, node="定理2.4", needle=r"1 - \\frac \{ 1 \}"), 0)
        self.assertEqual(_read(self.c), craw)
        self.assertEqual(_read(self.m), mraw)
        self.assertFalse(os.path.exists(os.path.join(self.E,
                                                    "_formula_tag_fixes.jsonl")))

    def test_apply_syncs_contract_and_both_manifests(self):
        _mk(self.E)
        craw = _read(self.c)
        self.assertEqual(_run(self.E, node="定理2.4", needle=r"1 - \\frac \{ 1 \}",
                              apply=True), 0)
        after = _read(self.c)
        # 差异只有一行新增 tag，其余字节逐字相同
        self.assertEqual([l for l in after.split("\n") if l not in set(craw.split("\n"))],
                         ['          "tag": "4"'])
        self.assertEqual([l for l in craw.split("\n") if l not in set(after.split("\n"))],
                         [])
        for side in ("units", "units-translate"):
            man = json.loads(_read(os.path.join(self.bs, side, "ch2", "manifest.json")))
            self.assertEqual(man["units"][0]["tags"], ["3", "4"])
        self.assertTrue(os.path.isdir(os.path.join(self.E, "_bak_formula_tags")))
        lines = _read(os.path.join(self.E, "_formula_tag_fixes.jsonl")).strip().split("\n")
        rec = json.loads(lines[-1])
        self.assertEqual(rec["number"], "4")
        self.assertEqual(rec["unit_key"], "定理2.4")
        self.assertIn("(a) 页区间", " ".join(rec["corroboration"]))

    def test_second_run_is_noop(self):
        _mk(self.E)
        self.assertEqual(_run(self.E, node="定理2.4", block=1, apply=True), 0)
        craw = _read(self.c)
        self.assertEqual(_run(self.E, node="定理2.4", block=1, apply=True), 0)
        self.assertEqual(_read(self.c), craw)

    def test_block_index_addressing(self):
        _mk(self.E)
        self.assertEqual(_run(self.E, node="定理2.4", block=1), 0)

    def test_auto_locates_via_gate_18_predicate(self):
        """⑱ 的粘连锚点判据点名时，--auto 无需人工定位即可回填。"""
        _mk(self.E)
        tree = json.loads(_read(self.c))
        blk = tree["sub_sec"][0]["sub_sec"][2]
        self.assertTrue(blk["formula"].startswith(TARGET))
        # 让锚点块进契约（⑱ 的搜索空间 = 契约树），并去掉页佐证以证明走的是 (c)
        tree["sub_sec"][0]["sub_sec"].insert(3, {"text": "(4)"})
        with io.open(self.c, "w", encoding="utf-8", newline="\n") as f:
            json.dump(tree, f, ensure_ascii=False, indent=2)
        os.remove(os.path.join(self.E, "page_037.json"))
        self.assertEqual(_run(self.E, auto=True, apply=True), 0)
        man = json.loads(_read(self.m))
        self.assertEqual(man["units"][0]["tags"], ["3", "4"])

    # ── 负向：exit 2 且零写入 ────────────────────────────────────────────
    def _refuse(self, mkw=None, **kw):
        _mk(self.E, **(mkw or {}))
        craw, mraw = _read(self.c), _read(self.m)
        argv = kw.pop("argv", None)
        code = (bft.main(argv) if argv is not None
                else _run(self.E, apply=True, **kw))
        self.assertEqual(code, 2)
        self.assertEqual(_read(self.c), craw)
        self.assertEqual(_read(self.m), mraw)
        self.assertFalse(os.path.exists(os.path.join(self.E,
                                                    "_formula_tag_fixes.jsonl")))

    def test_refuse_without_print_evidence(self):
        """页区间无 (9) 锚点、非夹心空洞、⑱ 未点名 → 回填等于凭空编号。"""
        self._refuse(number="9", node="定理2.4", block=1)

    def test_refuse_ambiguous_unit_without_flag(self):
        self._refuse(mkw={"dup_entry": True}, number="4", node="定理2.4", block=1)

    def test_refuse_when_several_untagged_blocks_and_no_locator(self):
        self._refuse(number="4", node="定理2.4")

    def test_refuse_needle_with_no_hit(self):
        self._refuse(number="4", node="定理2.4", needle=r"nonexistent_formula")

    def test_refuse_needle_with_multiple_hits(self):
        self._refuse(number="4", node="定理2.4", needle=r"\\frac")

    def test_refuse_inline_block_points_to_register_formula(self):
        """行内公式块不回填 tag：该走 known_book 登记通道（判据 3）。"""
        self._refuse(number="4", node="定理2.4", block=3)

    def test_refuse_block_already_tagged(self):
        """--block 与 --list-blocks 同坐标系，抄到已挂号的块必须拒绝对真实编号动刀。"""
        self._refuse(number="4", node="定理2.4", block=0)

    def test_refuse_noise_like_number(self):
        self._refuse(argv=[self.E, "2", "--number", "00", "--node", "定理2.4",
                           "--block", "1", "--evidence", EV, "--apply"])

    def test_refuse_missing_evidence_text(self):
        self._refuse(argv=[self.E, "2", "--number", "4", "--node", "定理2.4",
                           "--block", "1", "--evidence", "太短", "--apply"])

    def test_refuse_nonstandard_json(self):
        self._refuse(mkw={"indent": 4}, number="4", node="定理2.4", block=1)

    def test_refuse_unknown_node_key(self):
        self._refuse(number="4", node="定理2.99", block=1)

    def test_refuse_without_locator(self):
        self._refuse(argv=[self.E, "2", "--number", "4", "--evidence", EV, "--apply"])


if __name__ == "__main__":
    unittest.main()
