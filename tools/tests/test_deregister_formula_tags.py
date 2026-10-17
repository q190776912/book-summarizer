"""test_deregister_formula_tags.py — 摘除**编造契约公式序标**的正规通道（四本账同步 + 拒绝面）。

缺陷根因（Katok–Hasselblatt《Introduction to the Modern Theory of Dynamical Systems》实测
2026-09-29）：收割把条目序标/散文交叉引用（练习号 `12.2.2`、定理号 `18.3.1`、证明里的
`(i')`）误挂成展示式 `tag`。契约假号成了对账真值 → 写手照印面不写 `\tag` 判漏写、删了判
编造，假号还顺着契约流进两侧单元正文与两版最终 md（本书 19 处）。

修复形态：`tools/deregister_formula_tags.py` = 与 `backfill_formula_tags.py` 互为反向的通道，
判据共用闸门 ⑭（`lib.tag_attestation.unattested_tags` + `attested_numbers` 豁免），
故「⑭ 没判毒即拒绝」就是本工具的**印面举证责任**；四本账一次改齐、字节守恒（CRLF /
无末尾换行的契约也能修）、备份 + JSONL 台账。

正向：dry-run 零写入；--apply 后契约 tag 归空、两侧正文 `\tag{}` 消失、两侧 manifest `tags`
同步、**其余字节逐字相同**、台账落一行、再跑为 NO-OP；独占一行的 `\tag` 整行删除、行尾
内联形只去 token；--list 点名 ⑭ 判毒号与正文命中数。
负向（一律 exit 2 且零写入）：①⑭ 未判毒（页窗有 `(N)` 锚点）②缺 --evidence
③号已登记进 `formula.known_book`（豁免后 ⑭ 不再判毒 → 工具也拒绝删，两处共用一份登记）
④manifest 非标准 indent=2 形却要改 `tags` 账。幂等：契约与正文都无该 tag → NO-OP exit 0。

🔴 `--mispaired`（第三类缺陷：号**真印**但挂在了**错误的块**上，2026-10-16 Lehmann ch6
实测 (6.5.10) 被从概率表 `text` 块错挂到上方无号展示式）是「⑭ 不判毒」时唯一合法的摘除出口：
必须配 `--host <契约节点 key | non-display>`、该号须在契约里**恰好登记一处**，台账另记
`mode`/`mispaired_from`/`host` 并在待办里先打印回填命令（真主为展示块时）。
负向：缺 --host / --host 不在契约 / 同一号两处登记 / `--host` 漏配 `--mispaired`（防静默忽略）。
"""
import io
import json
import os
import re
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
    "deregister_formula_tags",
    os.path.join(_ROOT, "tools", "deregister_formula_tags.py"))
dft = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(dft)

BOGUS = "28"
REAL = [str(n) for n in range(20, 28)]
EV = "fitz 文字层全章页窗 p36-p38：28 只作为条目号出现，从未印作 (28) 编号"
EV_MIS = ("fitz 200dpi p38：(27) 标在概率表 bbb/bbc 行左，契约里该表只是 text 块；"
          "被误挂的展示式 x_{27}=f^{n}(y)+27 印面无号")
MARK = "<!-- book-summarizer DONE unit: id=0001 type=item key=定理2.4 name=定理2.4 -->"


def _tree():
    blocks = [{"text": "Let us define the following."}]
    for n in range(20, 29):
        blocks.append({"formula": "x_{%d} = f^{n}(y) + %d" % (n, n),
                       "display": True, "tag": str(n)})
    item = {"key": "定理2.4", "type": "theorem", "name": "2.4 Statement",
            "page_start": 36, "page_end": 38, "sub_sec": blocks}
    return {"key": "2", "type": "chapter", "name": "2 Multiplicative functions",
            "page_start": 36, "page_end": 38, "sub_sec": [item]}


def _unit_body():
    return "\n".join([MARK, "", "## 定理 2.4 Statement", "",
                      "> $$", "> x_{27} = f^{n}(y) + 27 \\tag{27}", ">", "> $$", "",
                      "> $$", "> x_{28} = f^{n}(y) + 28 \\tag{28}", ">", "> $$", "",
                      "$$", "z_{28} = f^{n}(w) + 28", "\\tag{28}", "$$", ""])


def _entry(i, tags):
    return {"id": "%04d" % i, "file": "%04d_item.md" % i, "type": "item",
            "ntype": "theorem", "key": "定理2.4", "name": "定理2.4",
            "tags": tags, "images": [], "content": 12, "hash": "deadbeef"}


def _w(path, text, crlf=False):
    _write_raw(path, (text.replace("\n", "\r\n") if crlf else text).encode("utf-8"))


def _write_raw(path, data):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with open(path, "wb") as f:
        f.write(data)


def _mk(extract, crlf_contract=True, manifest_standard=True, page_anchor=True,
        known_book=None, manifest_tags=True, mixed_units=False, stem="ch2"):
    bs = os.path.join(extract, "book_structure")
    _w(os.path.join(bs, stem + ".json"),
       json.dumps(_tree(), ensure_ascii=False, indent=2), crlf=crlf_contract)
    if page_anchor:
        for pg in (36, 37, 38):
            _w(os.path.join(extract, "page_%03d.json" % pg),
               json.dumps({"page": pg,
                           "text": [{"text": "(%s)  label" % n}
                                    for n in REAL if int(n) % 3 == pg % 3]},
                          ensure_ascii=False, indent=2))
    if known_book is not None:
        _w(os.path.join(extract, "verify_config.json"),
           json.dumps({"formula": {"known_book": known_book}},
                      ensure_ascii=False, indent=2))
    tags = REAL + [BOGUS] if manifest_tags else []
    for side in ("units", "units-translate"):
        d = os.path.join(bs, side, stem)
        ent = [_entry(1, tags)]
        if not manifest_tags:
            ent[0].pop("tags")
        m = {"chapter_key": "2", "language": "en", "final_md": "Chapter2.md",
             "units": ent}
        txt = (json.dumps(m, ensure_ascii=False, indent=2) if manifest_standard
               else json.dumps(m, ensure_ascii=False, indent=1))
        _w(os.path.join(d, "manifest.json"), txt)
        body = _unit_body()
        if mixed_units and side == "units":
            parts = body.split("\n")
            body = "".join(l + ("\r\n" if i % 2 else "\n") for i, l in enumerate(parts[:-1]))
            _write_raw(os.path.join(d, "0001_item.md"), body.encode("utf-8"))
            continue
        _w(os.path.join(d, "0001_item.md"), body, crlf=(side == "units"))


def _paths(extract, stem="ch2"):
    bs = os.path.join(extract, "book_structure")
    return [os.path.join(bs, stem + ".json"),
            os.path.join(bs, "units", stem, "0001_item.md"),
            os.path.join(bs, "units", stem, "manifest.json"),
            os.path.join(bs, "units-translate", stem, "0001_item.md"),
            os.path.join(bs, "units-translate", stem, "manifest.json")]


def _snap(extract, stem="ch2"):
    return {p: _rb(p) for p in _paths(extract, stem)}


def _run(extract, numbers=(BOGUS,), apply=False, evidence=EV, key="2",
         mispaired=False, host=""):
    argv = [extract, key]
    for n in numbers:
        argv += ["--number", n]
    argv += ["--evidence", evidence]
    if mispaired:
        argv.append("--mispaired")
    if host:
        argv += ["--host", host]
    if apply:
        argv.append("--apply")
    return dft.main(argv)


def _rb(path):
    with open(path, "rb") as f:
        return f.read()


def _text(path):
    return _rb(path).decode("utf-8").replace("\r\n", "\n")


class DeregisterFormulaTagsTest(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.E = self._td.name
        self.bs = os.path.join(self.E, "book_structure")
        self.c = os.path.join(self.bs, "ch2.json")

    def tearDown(self):
        self._td.cleanup()

    def _quiet(self, fn):
        buf, real = io.StringIO(), sys.stdout
        sys.stdout = buf
        try:
            rc = fn()
        finally:
            sys.stdout = real
        return rc, buf.getvalue()

    # ── 正向 ────────────────────────────────────────────────────────────
    def test_dry_run_writes_nothing(self):
        _mk(self.E)
        before = _snap(self.E)
        rc, out = self._quiet(lambda: _run(self.E))
        self.assertEqual(rc, 0)
        self.assertIn("DRY-RUN", out)
        self.assertEqual(_snap(self.E), before)
        self.assertFalse(os.path.exists(
            os.path.join(self.E, "_formula_tag_deregistrations.jsonl")))

    def test_apply_clears_all_four_ledgers_and_keeps_other_bytes(self):
        _mk(self.E)
        craw = _rb(self.c)
        rc, out = self._quiet(lambda: _run(self.E, apply=True))
        self.assertEqual(rc, 0)
        self.assertIn("APPLIED", out)

        tree = json.loads(_text(self.c))
        tags = [b.get("tag") for b in tree["sub_sec"][0]["sub_sec"] if "formula" in b]
        self.assertEqual(tags, REAL + [""])
        # 字节守恒：CRLF + 无末尾换行的形态原样保留，只少了 `"28"` 四个字符
        after = _rb(self.c).decode("utf-8")
        self.assertIn("\r\n", after)
        self.assertFalse(after.endswith("\n"))
        self.assertEqual(len(after), len(craw.decode("utf-8")) - len(BOGUS))

        for side in ("units", "units-translate"):
            d = os.path.join(self.bs, side, "ch2")
            body = _text(os.path.join(d, "0001_item.md"))
            self.assertNotIn("\\tag{28}", body)
            self.assertIn("\\tag{27}", body)
            # 独占一行的 \tag{28} 整行删除（不留空行）、内联形只去 token 与前导空格
            self.assertIn("z_{28} = f^{n}(w) + 28\n$$", body)
            self.assertIn("> x_{28} = f^{n}(y) + 28\n>", body)
            self.assertEqual(body.split("\n")[0].strip(), MARK.strip())
            man = json.loads(_text(os.path.join(d, "manifest.json")))
            self.assertEqual(man["units"][0]["tags"], REAL)
        self.assertTrue(os.path.isdir(os.path.join(self.E, "_bak_deregister_tags")))
        rec = json.loads(io.open(
            os.path.join(self.E, "_formula_tag_deregistrations.jsonl"),
            encoding="utf-8").read().strip().split("\n")[-1])
        self.assertEqual(rec["numbers"], [BOGUS])
        self.assertIn(BOGUS, rec["gate_14_condemned"])
        self.assertEqual(rec["contract_removals"], {BOGUS: 1})
        self.assertIn("init_translate_units", out)

    def test_second_run_is_noop(self):
        _mk(self.E)
        self._quiet(lambda: _run(self.E, apply=True))
        before = _snap(self.E)
        rc, out = self._quiet(lambda: _run(self.E, apply=True))
        self.assertEqual(rc, 0)
        self.assertIn("NO-OP", out)
        self.assertEqual(_snap(self.E), before)

    def test_mixed_newline_unit_files_stay_byte_exact(self):
        """实测卡点（Katok ch1/ch17/ch18/ch20 的单元是 CRLF/LF 混排）：工具必须按原字节
        复现，只去掉目标 tag 的字节，不把整文件折成单一换行风格。"""
        _mk(self.E, mixed_units=True)
        p = os.path.join(self.bs, "units", "ch2", "0001_item.md")
        before = _rb(p)
        rc, out = self._quiet(lambda: _run(self.E, apply=True))
        self.assertEqual(rc, 0)
        self.assertIn("APPLIED", out)
        after = _rb(p)
        self.assertNotIn(b"\\tag{28}", after)
        self.assertEqual(after.count(b"\r"), before.count(b"\r"))
        self.assertEqual(len(before) - len(after), len(" \\tag{28}") + len("\\tag{28}\n"))

    def test_supplement_chapter_resolved_by_physical_evidence(self):
        """补篇键 `S`：进程级 kind 注册表未灌注时 `unit_dir_name('S')` 会算成
        `appendixS` → 两侧单元目录「不存在」→ 正文与 manifest 两本账**静默跳过**而工具
        照样报成功（本书 supplementS 实测同型缺陷让 sync_translate_markers 误跳 41 单元）。
        判据必须交还磁盘物理证据。"""
        _mk(self.E, stem="supplementS")
        rc, out = self._quiet(lambda: _run(self.E, key="S", apply=True))
        self.assertEqual(rc, 0, out)
        self.assertIn("APPLIED", out)
        self.assertIn("units:0001_item.md", out)
        for side in ("units", "units-translate"):
            body = _text(os.path.join(self.bs, side, "supplementS", "0001_item.md"))
            self.assertNotIn("\\tag{28}", body)
        tree = json.loads(_text(os.path.join(self.bs, "supplementS.json")))
        self.assertEqual([b.get("tag") for b in tree["sub_sec"][0]["sub_sec"]
                          if "formula" in b][-1], "")

    def test_ambiguous_unit_dirs_refused(self):
        """同一键同时存在 `appendixS/` 与 `supplementS/` = 章型有歧义 → 拒绝，不猜。"""
        _mk(self.E, stem="supplementS")
        d = os.path.join(self.bs, "units", "appendixS")
        os.makedirs(d)
        _w(os.path.join(d, "0001_item.md"), _unit_body())
        before = _snap(self.E, "supplementS")
        rc, out = self._quiet(lambda: _run(self.E, key="S", apply=True))
        self.assertEqual(rc, 2)
        self.assertIn("REFUSE", out)
        self.assertEqual(_snap(self.E, "supplementS"), before)

    def test_manifest_without_tags_ledger_is_skipped(self):
        _mk(self.E, manifest_tags=False)
        rc, out = self._quiet(lambda: _run(self.E, apply=True))
        self.assertEqual(rc, 0)
        self.assertIn("该 manifest 无 tags 字段", out)
        man = json.loads(_text(os.path.join(self.bs, "units", "ch2", "manifest.json")))
        self.assertNotIn("tags", man["units"][0])

    def test_list_reports_condemned_and_body_hits(self):
        _mk(self.E)
        rc, out = self._quiet(lambda: dft.main([self.E, "2", "--list"]))
        self.assertEqual(rc, 0)
        self.assertIn("  %s " % BOGUS, out)
        self.assertNotIn("  %s " % "27", out)
        self.assertIn("units:0001_item.md", out)
        self.assertIn("units-translate:0001_item.md", out)

    # ── 负向：exit 2 且零写入 ────────────────────────────────────────────
    def _assert_refused(self, mkw=None, **kw):
        _mk(self.E, **(mkw or {}))
        before = _snap(self.E)
        rc, out = self._quiet(lambda: _run(self.E, apply=True, **kw))
        self.assertEqual(rc, 2)
        self.assertIn("REFUSE", out)
        self.assertEqual(_snap(self.E), before)
        self.assertFalse(os.path.exists(os.path.join(self.E, "_bak_deregister_tags")))
        self.assertFalse(os.path.exists(
            os.path.join(self.E, "_formula_tag_deregistrations.jsonl")))

    def test_refuses_tag_with_printed_anchor(self):
        """⑭ 认得的号（页窗里有 `(27)`）不许删——那是真编号，删掉等于毁掉对账真值。"""
        self._assert_refused(numbers=("27",))

    def test_refuses_without_evidence(self):
        self._assert_refused(evidence="太短")

    def test_known_book_exemption_blocks_deletion(self):
        """登记进 known_book 后 ⑭ 不再判毒 → 本工具同样拒绝（两处共用一份登记）。"""
        self._assert_refused(mkw={"known_book": [BOGUS]})

    def test_refuses_non_standard_manifest_tags_ledger(self):
        self._assert_refused(mkw={"manifest_standard": False})

    def test_refuses_when_page_window_unreadable_and_tag_therefore_unknown(self):
        """页文件缺失 = ⑭ 无从判毒（fail-open）→ 工具拒绝，逼先补页证据。"""
        self._assert_refused(mkw={"page_anchor": False})

    # ── `--mispaired`：号真印但**挂错了块**（第三类缺陷，Lehmann ch6 实测）────
    def test_mispaired_non_display_clears_all_four_ledgers(self):
        """27 在页窗里有 `(27)` 锚点 → 幻影通道必拒；`--mispaired --host non-display`
        是它唯一的合法出口：四本账同步摘掉、台账记 mode/mispaired_from/host。"""
        _mk(self.E)
        rc, out = self._quiet(lambda: _run(self.E, numbers=("27",), apply=True,
                                           mispaired=True, host="non-display",
                                           evidence=EV_MIS))
        self.assertEqual(rc, 0, out)
        self.assertIn("APPLIED", out)
        self.assertIn("--mispaired（号真印但挂错块）", out)
        self.assertIn("错挂块    = (27) 在节点 定理2.4", out)
        self.assertIn("契约无展示块可挂", out)
        tree = json.loads(_text(self.c))
        tags = [b.get("tag") for b in tree["sub_sec"][0]["sub_sec"] if "formula" in b]
        self.assertEqual(tags, REAL[:-1] + ["", BOGUS])
        for side in ("units", "units-translate"):
            d = os.path.join(self.bs, side, "ch2")
            self.assertNotIn("\\tag{27}", _text(os.path.join(d, "0001_item.md")))
            self.assertIn("\\tag{28}", _text(os.path.join(d, "0001_item.md")))
            man = json.loads(_text(os.path.join(d, "manifest.json")))
            self.assertEqual(man["units"][0]["tags"], REAL[:-1] + [BOGUS])
        rec = json.loads(io.open(
            os.path.join(self.E, "_formula_tag_deregistrations.jsonl"),
            encoding="utf-8").read().strip().split("\n")[-1])
        self.assertEqual(rec["mode"], "mispaired")
        self.assertEqual(rec["host"], "non-display")
        self.assertEqual(rec["numbers"], ["27"])
        self.assertEqual(rec["mispaired_from"]["27"]["node"], "定理2.4")
        self.assertEqual(rec["mispaired_from"]["27"]["at"], "tag")
        self.assertIn("x_{27}", rec["mispaired_from"]["27"]["formula_head"])

    def test_mispaired_with_display_host_prints_backfill_todo(self):
        """真主是契约里的展示块时，待办必须先给回填命令（含 --node 真主），
        否则摘完就是「号从账上消失」而不是「号回到正确块」。"""
        _mk(self.E)
        rc, out = self._quiet(lambda: _run(self.E, numbers=("27",), apply=True,
                                          mispaired=True, host="定理2.4",
                                          evidence=EV_MIS))
        self.assertEqual(rc, 0, out)
        self.assertIn("backfill_formula_tags.py", out)
        self.assertIn("--number 27 --node 定理2.4", out)
        self.assertIn("gate_units.py", out)

    def test_mispaired_still_uses_phantom_semantics_for_condemned(self):
        """混批：⑭ 判毒的 28 不因 --mispaired 改变行为（mode=unattested、不打印错挂块）。"""
        _mk(self.E)
        rc, out = self._quiet(lambda: _run(self.E, numbers=(BOGUS,), apply=True,
                                          mispaired=True, host="non-display"))
        self.assertEqual(rc, 0, out)
        self.assertIn("⑭ 判毒（幻影）", out)
        self.assertNotIn("错挂块", out)
        rec = json.loads(io.open(
            self.E + os.sep + "_formula_tag_deregistrations.jsonl",
            encoding="utf-8").read().strip().split("\n")[-1])
        self.assertEqual(rec["mode"], "unattested")
        self.assertEqual(rec["mispaired_from"], {})

    def test_second_mispaired_run_is_noop(self):
        _mk(self.E)
        self._quiet(lambda: _run(self.E, numbers=("27",), apply=True, mispaired=True,
                                 host="non-display", evidence=EV_MIS))
        before = _snap(self.E)
        rc, out = self._quiet(lambda: _run(self.E, numbers=("27",), apply=True,
                                           mispaired=True, host="non-display",
                                           evidence=EV_MIS))
        self.assertEqual(rc, 0)
        self.assertIn("NO-OP", out)
        self.assertEqual(_snap(self.E), before)

    def _assert_mis_refused(self, numbers=("27",), host="", **kw):
        _mk(self.E, **kw)
        before = _snap(self.E)
        rc, out = self._quiet(lambda: _run(self.E, numbers=numbers, apply=True,
                                           mispaired=True, host=host,
                                           evidence=EV_MIS))
        self.assertEqual(rc, 2)
        self.assertIn("REFUSE", out)
        self.assertEqual(_snap(self.E), before)
        self.assertFalse(os.path.exists(
            os.path.join(self.E, "_formula_tag_deregistrations.jsonl")))

    def test_mispaired_requires_host(self):
        self._assert_mis_refused(host="")

    def test_mispaired_rejects_unknown_host_node(self):
        """真主 key 不在契约里 = 无法回填 → 拒绝，并指路 non-display。"""
        self._assert_mis_refused(host="不存在的节点")

    def test_mispaired_rejects_ambiguous_double_registration(self):
        """同一号在契约里登记两处 → 「挂错块」无从唯一指认，要求逐条处理。"""
        _mk(self.E)
        tree = json.loads(_text(self.c))
        dup = {"formula": "x_{27} = duplicate", "display": True, "tag": "27"}
        tree["sub_sec"][0]["sub_sec"].append(dup)
        _w(self.c, json.dumps(tree, ensure_ascii=False, indent=2))
        before = _snap(self.E)
        rc, out = self._quiet(lambda: _run(self.E, numbers=("27",), apply=True,
                                           mispaired=True, host="non-display",
                                           evidence=EV_MIS))
        self.assertEqual(rc, 2)
        self.assertIn("登记 2 处", out)
        self.assertEqual(_snap(self.E), before)

    def test_host_without_mispaired_is_not_silently_ignored(self):
        _mk(self.E)
        before = _snap(self.E)
        rc, out = self._quiet(lambda: _run(self.E, apply=True, host="定理2.4"))
        self.assertEqual(rc, 2)
        self.assertIn("--host 只在 --mispaired 通道有意义", out)
        self.assertEqual(_snap(self.E), before)


if __name__ == "__main__":
    unittest.main()
