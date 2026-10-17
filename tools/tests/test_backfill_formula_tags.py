"""test_backfill_formula_tags.py — 回填丢失印刷公式编号的正规通道（三本账同步 + 拒绝面）。

缺陷根因（Apostol《Introduction to Analytic Number Theory》实测 2026-09-29）：抽取器收割
`tag` 时把印在编号列的 `(N)` 整块丢掉（编号与展示式粘连、`array` 多行逐行编号、跨页）。
契约无档 → 单元级 tag 对账**空转**：门控既不要求写手写 `\\tag{N}`，也不把写手照印面写出
的号判成编造；全书 368 个印面号里 18 个因此静默消失（`lib.tag_attestation.numbering_gaps`
一次数出，⑱/页池审计当时均报 0）。

修复形态：`tools/backfill_formula_tags.py` = 带断言的正规通道（印面佐证闸 + 备份 + JSONL
台账 + 「去掉新增 tag 即回到原字节」一致性断言），正文 `\\tag{}` 一本账留给人（工具打印待办）。

正向：dry-run 不落盘；--apply 后契约目标块有 `tag`、两侧 manifest `tags` 同步、**其余字节
逐字不变**、台账落一行、再跑为 NO-OP；--auto 由 ⑱ 判据定位；--needle / --block 定位；
`--number` 认**多级**印刷号（`(1.1.9)`/`(A.2.1)` 一类按节重启或字母章位形态，旧式只认
单级号会把这类书整类拒在门外）；同键多型节点（Definition/Lemma/Example 共用序标）由
`--unit` 那条 manifest 记录的 `ntype` 收窄定位。
负向（一律 exit 2 且零写入）：①无印面佐证 ②该号已在账（幂等 NO-OP，exit 0）③同键多单元
未指定 --unit ④节点里多个未挂号块却不给定位方式 ⑤--needle 命中 0/多个 ⑥目标是行内公式
（该走 register_formula）⑦`--number` 是 0/00 类 OCR 碎片 ⑧缺 --evidence ⑨契约不是
indent=2 标准形 ⑩节点键不存在 ⑪同键多型却不给 --unit（拒绝猜类型）
⑫**锚点邻接闸**：该号在契约里有整块 `(N)` 锚点、锚点挨的是表格行而目标块在别处
（= 号真印但配对错，机械夹逼判据的盲区，Lehmann (6.5.10) 实测）→ 拒绝并指路
`deregister_formula_tags.py --mispaired`；契约无整块锚点时本闸不判（既往行为不变）；
散文回引被切成独立 `(N)` 块属本闸已知误伤，`--confirm-non-adjacent` 具名放行并记入台账。
"""
import io
import json
import contextlib
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


def _entry(i, key, tags, ntype="theorem"):
    return {"id": "%04d" % i, "file": "%04d_item_%s.md" % (i, key.replace(".", "_")),
            "type": "item", "ntype": ntype, "key": key, "name": key,
            "tags": tags, "images": [], "content": 12, "hash": "deadbeef"}


def _mk(extract, translate=True, page_anchor=True, indent=2, dup_entry=False,
        anchor="(4)  product expansion", multi_type=False):
    bs = os.path.join(extract, "book_structure")
    u = os.path.join(bs, "units", "ch2")
    os.makedirs(u)
    tree = _tree()
    if multi_type:      # 同键多型：三级序标书里 Definition/Lemma/Example 共用一个 key
        for t, f in (("definition", "\\delta _ { definition } only"),
                     ("example", "\\delta _ { example } only")):
            tree["sub_sec"].append({"key": "定理2.4", "type": t, "name": "2.4 %s" % t,
                                    "page_start": 37, "page_end": 37,
                                    "sub_sec": [{"formula": f, "display": True}]})
    cpath = os.path.join(bs, "ch2.json")
    with io.open(cpath, "w", encoding="utf-8", newline="\n") as f:
        json.dump(tree, f, ensure_ascii=False, indent=indent)
    entries = [_entry(16, "定理2.4", ["3"])]
    if dup_entry:      # 同节内「定义 / 定理」共用序标的真实形态
        entries.append(_entry(17, "定理2.4", []))
    if multi_type:
        entries += [_entry(17, "定理2.4", [], ntype="definition"),
                    _entry(18, "定理2.4", [], ntype="example")]
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
            json.dump({"page": 37, "text": [{"text": anchor, "score": 0.9}]},
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

    # ── 锚点**邻接**闸：机械夹逼不构成印面证据（Lehmann (6.5.10) 配对错根治）──
    def _inject_anchor(self, at, *blocks):
        tree = json.loads(_read(self.c))
        seq = tree["sub_sec"][0]["sub_sec"]
        for i, b in enumerate(blocks):
            seq.insert(at + i, b)
        with io.open(self.c, "w", encoding="utf-8", newline="\n") as f:
            json.dump(tree, f, ensure_ascii=False, indent=2)
        return tree

    def test_adjacency_vetoes_pairing_when_anchor_abuts_a_text_row(self):
        """契约里 `(4)` 整块锚点挨的是概率表行（text 块），目标却是别处的展示式：
        号真印、页锚点在、⑱ 也可能不点名，但**配对错** → 必须拒绝（实测本形态曾被
        机械夹逼判据挂到无号的 `P(X*₍₁₎=b,…)=3/27` 上，账从此两头堵）。"""
        _mk(self.E)
        # 索引 4 = 未挂号展示块 `sum_{d|n}` 之后、proof 子节点之前
        self._inject_anchor(4, {"text": "(4)"},
                            {"text": "bbb bbc bbd bcb  1/27 3/27 3/27 6/27"})
        craw = _read(self.c)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = _run(self.E, node="定理2.4", needle=r"1 - \\frac \{ 1 \}", apply=True)
        out = buf.getvalue()
        self.assertEqual(rc, 2, out)
        self.assertIn("既不相邻", out)
        self.assertIn("deregister_formula_tags.py --mispaired --host non-display", out)
        self.assertEqual(_read(self.c), craw)          # 零写入
        self.assertFalse(os.path.exists(os.path.join(self.E, "_bak_formula_tags")))

    def test_non_adjacent_override_is_a_named_confirmation(self):
        """散文回引被 OCR 切成独立 `(N)` 块是本闸的**已知误伤**（本书普查 23 处点名里
        8 处即此形）：具名旗可放行，但台账必须留名，机械批量驱动不会传它。"""
        _mk(self.E)
        self._inject_anchor(4, {"text": "(4)"},
                            {"text": "The asymptotic level of (4) is therefore"})
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = _run(self.E, node="定理2.4", needle=r"1 - \\frac \{ 1 \}",
                      apply=True, confirm_non_adjacent=True)
        self.assertEqual(rc, 0, buf.getvalue())
        self.assertIn("--confirm-non-adjacent", buf.getvalue())
        rec = json.loads(_read(os.path.join(
            self.E, "_formula_tag_fixes.jsonl")).strip().split("\n")[-1])
        self.assertTrue(rec["adjacency_confirmed"])
        self.assertIn("既不相邻", rec["anchor_adjacency"])

    def test_forward_first_display_accepts_math_fragments_only(self):
        """印面版式：编号行在展示式**上方**自成一行，同一条公式常被切成
        「编号 + 首行碎片 + display」三块（实测 (2.1.14)/(2.8.46)/(5.1.18)/(7.2.3) 全是
        这一形）→ 锚点向后**第一条**展示式即目标，必须放行，否则本闸假拒率 4/5。"""
        _mk(self.E)
        self._inject_anchor(2, {"text": "(4)"},
                            {"text": "(x-x)=sum x - ()xx-1"})
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = _run(self.E, node="定理2.4", block=1, apply=True)
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn("第一条", out)
        man = json.loads(_read(self.m))
        self.assertEqual(man["units"][0]["tags"], ["3", "4"])

    def test_forward_walk_stops_at_a_prose_sentence(self):
        """印面确有「整行散文被编号」的式子（实测 (3.2.26) 挨的是
        「the assignment … is made at random, i.e., with probability 1/2 each …」）：
        锚点后面是成句英文 → 向后行走**停**，不得跨过句子去配下一条展示式。"""
        _mk(self.E)
        self._inject_anchor(2, {"text": "(4)"},
                            {"text": "the assignment of the two subjects is made "
                                     "at random, i.e., with probability"})
        craw = _read(self.c)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = _run(self.E, node="定理2.4", block=1, apply=True)
        out = buf.getvalue()
        self.assertEqual(rc, 2, out)
        self.assertIn("既不相邻", out)
        self.assertEqual(_read(self.c), craw)          # 零写入
        self.assertFalse(os.path.exists(os.path.join(self.E, "_bak_formula_tags")))

    def test_contract_anchor_adjacency_is_print_evidence_d(self):
        """佐证 (d)：条目/证明**跨页**时 (a) 的单页页窗取不到号（实测本书 ch6 十个号、
        ch5 的 5.7.22 全卡在这），但契约里躺着整块 `(N)` 锚点且与目标相邻——锚点块
        本身就是页文字层收割来的印面证据，此时放行，不必放宽 (a) 的窗口。"""
        _mk(self.E, page_anchor=False)         # 连 page_037.json 都不写 → (a) 必然不中
        self._inject_anchor(4, {"text": "(4)"})
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = _run(self.E, node="定理2.4", block=2, apply=True)
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn("(d) 契约内有整块 (N) 锚点", out)
        self.assertNotIn("(a) 页区间", out)
        man = json.loads(_read(self.m))
        self.assertEqual(man["units"][0]["tags"], ["3", "4"])

    def test_no_page_window_and_no_contract_anchor_still_refused(self):
        """(d) 不是第二个后门：页窗取不到、契约里也没有整块锚点 ⇒ 五条佐证全空，照旧拒绝。"""
        _mk(self.E, page_anchor=False)
        craw = _read(self.c)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = _run(self.E, node="定理2.4", block=2, apply=True)
        out = buf.getvalue()
        self.assertEqual(rc, 2, out)
        self.assertIn("无印面佐证", out)
        self.assertEqual(_read(self.c), craw)   # 零写入
        self.assertFalse(os.path.exists(os.path.join(self.E, "_bak_formula_tags")))

    def _write_page(self, pno, texts):
        with io.open(os.path.join(self.E, "page_%03d.json" % pno), "w",
                     encoding="utf-8", newline="\n") as f:
            json.dump({"page": pno, "text": [{"text": t, "score": 0.9} for t in texts]},
                      f, ensure_ascii=False, indent=2)

    def test_anchor_page_is_rechecked_by_the_tool(self):
        """佐证 (e)：跨页 + 契约锚点被 OCR 粘连 ⇒ 页号由人给，但**号在不在页上仍由
        工具回查**（与 (a) 同一个 `page_anchor_hit` 谓词），不是「写了页号就算数」。"""
        _mk(self.E, page_anchor=False)
        self._write_page(41, ["and hence the variance is", "(4)"])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = _run(self.E, node="定理2.4", block=2, anchor_page="41", apply=True)
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn("(e) 指定页 p41", out)
        man = json.loads(_read(self.m))
        self.assertEqual(man["units"][0]["tags"], ["3", "4"])

    def test_anchor_page_wrong_page_is_not_evidence(self):
        """给的页号里查不到该号 → (e) 不成立，四条全空照旧拒绝（自证通道不存在）。"""
        _mk(self.E, page_anchor=False)
        self._write_page(41, ["and hence the variance is", "(5)"])
        craw = _read(self.c)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = _run(self.E, node="定理2.4", block=2, anchor_page="41", apply=True)
        out = buf.getvalue()
        self.assertEqual(rc, 2, out)
        self.assertIn("无印面佐证", out)
        self.assertEqual(_read(self.c), craw)   # 零写入

    def test_anchor_page_must_be_a_page_number(self):
        _mk(self.E)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = _run(self.E, node="定理2.4", block=2, anchor_page="p37x")
        self.assertEqual(rc, 2, buf.getvalue())
        self.assertIn("不是页号", buf.getvalue())

    def test_adjacency_allows_pairing_next_to_the_anchor(self):
        """目标展示式就在锚点右邻 → 邻接成立，照常落账（本闸只否决配对错）。"""
        _mk(self.E)
        # 未挂号展示块 `sum_{d|n}`（原索引 4）前面插锚点 → 左右相邻成立
        self._inject_anchor(4, {"text": "(4)"})
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = _run(self.E, node="定理2.4", block=2, apply=True)
        self.assertEqual(rc, 0, buf.getvalue())
        self.assertIn("邻接", buf.getvalue())
        man = json.loads(_read(self.m))
        self.assertEqual(man["units"][0]["tags"], ["3", "4"])

    def test_adjacency_not_judged_without_standalone_anchor(self):
        """契约无整块锚点（粘连 / 表格行 / OCR 整块漏）→ 本闸**不判**，既往行为不变。"""
        _mk(self.E)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = _run(self.E, node="定理2.4", needle=r"1 - \\frac \{ 1 \}")
        self.assertEqual(rc, 0, buf.getvalue())
        self.assertIn("邻接闸不判", buf.getvalue())

    def test_standalone_anchor_shape_grammar(self):
        """整块-only 判据：认 `(6.5.10)`/`(4)`，拒元组、句中回引、粘连形与子项标号。"""
        for txt, num in ((" (4) ", "4"), ("(6.5.10)", "6.5.10"), ("（4）", "4"),
                         ("(4).", "4"), ("(28a)", "28a"), ("[12]", "12"),
                         ("(A.3)", "A.3")):
            self.assertEqual(bft.standalone_anchor({"text": txt}), num, txt)
        for bad in ("(b, b, c)", "in generalization of (6.5.6).", "(9) p(k)",
                    "(X*)", "( 1 /27 )", "", "(a)", "(iii)", "(1) and (2)"):
            self.assertIsNone(bft.standalone_anchor({"text": bad}), bad)
        self.assertIsNone(bft.standalone_anchor({"formula": "(4)", "display": True}))

    # ── 正向：多级印刷编号形态（Lehmann 全书 (1.1.9) 三级形）────────────────
    def test_number_shape_grammar(self):
        """`--number` 认多级/字母章位/后缀，仍拒 OCR 碎片（0 起、超长段、非号）。"""
        for ok in ("4", "28b", "1.1.9", "12.3.4.5", "A.3", "A.2.1", "II.5", "VIII.5"):
            self.assertTrue(bft._NUM_RE.match(ok), ok)
        for bad in ("0", "00", "01", "1.1.9.9.9.9.9", "1.2.", ".3", "4)", "四", ""):
            self.assertFalse(bft._NUM_RE.match(bad), bad)

    def test_multilevel_number_backfills_end_to_end(self):
        """旧形态闸只认单级号，(1.1.9) 这类「按节重启」三级号一步就 REFUSE；印面有锚点即须放行。"""
        _mk(self.E, anchor="(1.1.9)  a_n = 1/\\sqrt{n}")
        craw = _read(self.c)
        self.assertEqual(_run(self.E, number="1.1.9", node="定理2.4", block=1,
                              apply=True), 0)
        after = _read(self.c)
        self.assertEqual(after.count('"tag": "1.1.9"'),
                         craw.count('"tag": "1.1.9"') + 1)
        for side in ("units", "units-translate"):
            man = json.loads(_read(os.path.join(self.bs, side, "ch2", "manifest.json")))
            self.assertEqual(man["units"][0]["tags"], ["3", "1.1.9"])

    # ── 正向：同键多型按 --unit 记录的 ntype 收窄 ───────────────────────────
    def test_same_key_multi_type_narrows_via_unit_ntype(self):
        """三级序标书 Definition/Lemma/Example 共用 key 是常态：--unit 指到哪个类型就落哪个节点。"""
        _mk(self.E, multi_type=True)
        self.assertEqual(_run(self.E, node="定理2.4", unit="0018_item_定理2_4.md",
                              block=0, apply=True), 0)
        tree = json.loads(_read(self.c))
        by_type = {n["type"]: n for n in tree["sub_sec"]}
        self.assertEqual(by_type["example"]["sub_sec"][0].get("tag"), "4")
        self.assertIsNone(by_type["definition"]["sub_sec"][0].get("tag"))
        self.assertIsNone(by_type["theorem"]["sub_sec"][2].get("tag"))
        for side in ("units", "units-translate"):
            man = json.loads(_read(os.path.join(self.bs, side, "ch2", "manifest.json")))
            tags = {u["file"]: u["tags"] for u in man["units"]}
            self.assertEqual(tags["0018_item_定理2_4.md"], ["4"])
            self.assertEqual(tags["0016_item_定理2_4.md"], ["3"])
            self.assertEqual(tags["0017_item_定理2_4.md"], [])

    def test_list_blocks_needs_no_number_or_evidence(self):
        """列块是为了**定号**：先要求 --number/--evidence 等于死锁；且须同键多型收窄、零写入。"""
        _mk(self.E, multi_type=True)
        craw, mraw = _read(self.c), _read(self.m)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = bft.main([self.E, "2", "--node", "定理2.4",
                             "--unit", "0018_item_定理2_4.md", "--list-blocks"])
        self.assertEqual(code, 0)
        self.assertIn("delta _ { example }", buf.getvalue())
        self.assertNotIn("delta _ { definition }", buf.getvalue())
        self.assertEqual(_read(self.c), craw)
        self.assertEqual(_read(self.m), mraw)

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

    def test_refuse_same_key_multi_type_without_unit(self):
        """收窄靠 --unit 那条记录的 ntype；不给就照旧拒绝，绝不猜编号属于哪个类型。"""
        self._refuse(mkw={"multi_type": True}, number="4", node="定理2.4", block=0)

    def test_refuse_without_locator(self):
        self._refuse(argv=[self.E, "2", "--number", "4", "--evidence", EV, "--apply"])


if __name__ == "__main__":
    unittest.main()
