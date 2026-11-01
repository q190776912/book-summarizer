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
④manifest/契约是**逐字节复演不了**的手改形（pretty 里夹单行 `tags`）却要改 `tags` 账。
🔴 两条**不算**异形（旧守卫都把它们一并拒掉＝逼人手写 JSON，正是本工具要杜绝的动作）：
一个尾换行（普查 787 份里 72 份带，见
`test_manifest_with_one_trailing_newline_is_not_a_shape_refusal`）与 `indent=1`（Fraleigh
ch23 两侧 manifest 实测，见 `test_manifest_in_indent_1_shape_is_rewritten_in_its_own_style`
及契约侧同名 `…_indent_1_contract_style`）。幂等：契约与正文都无该
tag → NO-OP exit 0。

🔴 `--mispaired`（第三类缺陷：号**真印**但挂在了**错误的块**上，2026-10-16 Lehmann ch6
实测 (6.5.10) 被从概率表 `text` 块错挂到上方无号展示式）是「⑭ 不判毒」时唯一合法的摘除出口：
必须配 `--host <契约节点 key | non-display>`、该号须在契约里**恰好登记一处**，台账另记
`mode`/`mispaired_from`/`host` 并在待办里先打印回填命令（真主为展示块时）。
负向：缺 --host / --host 不在契约 / 同一号两处登记 / `--host` 漏配 `--mispaired`（防静默忽略）。

🔴 `--false-anchor`（第四类缺陷：**锚点是假的**，2026-10-30 跨语料普查 8 例逐条裁页坐实）：
⑭ 的裸排锚点集不管数字块的角色，页码 / 节号 `§6.2` / 数学零 `\\boldsymbol{0}` / 公式片段
`4m` 都能替幻影 tag 自证清白 → ⑭ 判不出毒，常规通道与 `--mispaired` 都不认它，旧工具**没有
合法出口**。该通道要求 `--anchor-kind` 指名假锚真身，并**机械**要求该号在页窗里只有裸块锚点
**或**它的 `(N)` 全是**算式因子**形（`lib.tag_attestation.operand_only_paren_anchor`：整章
页窗一个独立编号块都没有，且每处 `(N)` 都紧贴括号/运算符——2026-10-31 Fraleigh ch23 的
Z₁₂ 陪积链 `(2)(6)=(6)(2)=(3)(4)=…` 即此形态；旧口径「有任一 `(N)` 即拒」把这种真幻影
分流到 `--mispaired`，而那条处方要指认一个印面上不存在的宿主块）。
台账记 `mode=false-anchor` + `anchor_kind` + 工具自己抓回的 `bare_anchors`（页 → 原块文本）
与 `paren_factor_anchors`（放行时逐块原样）。
负向：缺 --anchor-kind / 值不在词表 / 与 --mispaired 同时给 / 该号有 `(N)` 锚点且呈编号本形 /
章里只要印着一处独立编号块就不再算「纯因子」/ 无括号锚点时不放行 /
`--anchor-kind` 漏配 `--false-anchor`。
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
EV_FA = ("fitz 200dpi p37：该展示式右缘无号，页眉印的是页码 29；"
         "契约里 29 的裸锚就是那个页眉块")
EV_CHAIN = ("fitz 300dpi p212 右缘裁剪 + 页窗 p208-p220 跨距普查：该章页边一个公式编号也没印，"
            "印面这段是 Z12 零因子的陪积链，`(31)` 是链里的因子不是编号")
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


def _compact_tags(txt):
    """把 `"tags": [...]` 整段挤成一行 = 语料里那 102 份「真异形」的手改形态。

    pretty 文件里夹一条单行数组，**任何**统一缩进候选（indent=1/2/4 或整体紧凑）都复演不了
    原文 → 整文件重生必拒。用它当「无法逐字节复演」的反面教材，而不是 `indent=1`
    （后者是写入器真会产出的正常形，见 `test_manifest_in_indent_1_...`）。
    """
    def _one(mo):
        items = [s.strip() for s in mo.group(1).split(",") if s.strip()]
        return '"tags": [%s]' % ", ".join(items)
    return re.sub(r'"tags": \[\s*(.*?)\s*\]', _one, txt, flags=re.S)


def _mk(extract, crlf_contract=True, manifest_indent=2, page_anchor=True,
        known_book=None, manifest_tags=True, mixed_units=False, stem="ch2",
        manifest_trail="", manifest_crlf=False, manifest_compact_tags=False):
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
        txt = json.dumps(m, ensure_ascii=False, indent=manifest_indent)
        if manifest_compact_tags:
            txt = _compact_tags(txt)
        _w(os.path.join(d, "manifest.json"), txt + manifest_trail, crlf=manifest_crlf)
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
         mispaired=False, host="", false_anchor=False, anchor_kind=""):
    argv = [extract, key]
    for n in numbers:
        argv += ["--number", n]
    argv += ["--evidence", evidence]
    if mispaired:
        argv.append("--mispaired")
    if false_anchor:
        argv.append("--false-anchor")
    if anchor_kind:
        argv += ["--anchor-kind", anchor_kind]
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
        m_src = _rb(os.path.join(self.bs, "units", "ch2", "manifest.json"))
        m_tr = _rb(os.path.join(self.bs, "units-translate", "ch2", "manifest.json"))
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
        # 备份件按「相对 extract 的路径」命名：两侧 manifest 的父目录**同名**（都叫 ch2），
        # 旧形 `ch2__manifest.json` 会让译侧那份盖掉源侧那份 → 回滚时少一本账。
        baks = os.listdir(os.path.join(self.E, "_bak_deregister_tags"))
        self.assertEqual(len(baks), 1)
        bak = os.path.join(self.E, "_bak_deregister_tags", baks[0])
        self.assertEqual(_rb(os.path.join(
            bak, "book_structure+units+ch2+manifest.json")), m_src)
        self.assertEqual(_rb(os.path.join(
            bak, "book_structure+units-translate+ch2+manifest.json")), m_tr)
        rec = json.loads(io.open(
            os.path.join(self.E, "_formula_tag_deregistrations.jsonl"),
            encoding="utf-8").read().strip().split("\n")[-1])
        self.assertEqual(rec["numbers"], [BOGUS])
        self.assertIn(BOGUS, rec["gate_14_condemned"])
        self.assertEqual(rec["contract_removals"], {BOGUS: 1})
        # 处方分叉（2026-10-30 Gelfand–Manin ch4 实测）：源正文被改 → 待办须给**定点** resync 通道，
        # 不得再喊 `init_translate_units`（它按 init 语义重算每个单元的 `hash`，会覆写 31 处
        # 与本次无关的派生时刻快照）；交付侧须同时给「已收官禁重 merge」的镜像出口。
        self.assertIn("resync_src_hash.py", out)
        self.assertIn("mirror_unit_line.py", out)
        self.assertIn("--delete-line", out)
        self.assertNotIn(u"python flows/write-source/script/init_translate_units.py", out)
        self.assertIn(u"勿用", out)          # 只作为「别用这条」的说明出现，不进命令

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

    def test_refuses_hand_edited_manifest_tags_ledger(self):
        """手改过的 manifest（`tags` 挤成一行，其余 pretty）→ 复演不了原文 → 必拒零写入。

        🔴 这一条 formerly 用 `indent=1` 当「异形」，那是**错的样本**：indent=1 是写入器
        真会产出的正常形（Fraleigh 两侧 manifest 实测），放宽后它必须能改账。异形判据只
        剩「无法逐字节复演」，故这里手工造一个真的异形（同族 `load_strict` 拒的那 102 份）。
        """
        self._assert_refused(mkw={"manifest_compact_tags": True})

    def test_manifest_in_indent_1_shape_is_rewritten_in_its_own_style(self):
        """🔔 indent=1 的 manifest **不是**异形（2026-10-31 Fraleigh ch23 实测）：旧守卫
        只认 indent=2，于是那本书 `--false-anchor` 干跑到 manifest 账本被「请人工同步后重跑」
        挡死＝逼人手写 JSON 改 `tags`；而 manifest 里的幻影号不摘，`node_tags` 就继续把它
        当对账真值。修法是复用契约那条 :func:`probe_dump_style`（能逐字节复演才算认识该风格）。"""
        _mk(self.E, manifest_indent=1)
        rc, out = self._quiet(lambda: _run(self.E, apply=True))
        self.assertEqual(rc, 0, out)
        for side in ("units", "units-translate"):
            p = os.path.join(self.bs, side, "ch2", "manifest.json")
            text = _text(p)
            obj = json.loads(text)
            self.assertEqual(obj["units"][0]["tags"], REAL)     # 28 摘掉，20..27 留下
            # 写出必须**还是** indent=1（整文件重生不许漂风格）
            self.assertEqual(json.dumps(obj, ensure_ascii=False, indent=1), text)
            self.assertNotEqual(json.dumps(obj, ensure_ascii=False, indent=2), text)

    def test_manifest_with_one_trailing_newline_is_not_a_shape_refusal(self):
        """🔴 尾换行**不算**异形（2026-10-30 跨架普查 787 份 `units/*/manifest.json`：
        613 无尾换行 / 72 恰有一份 / 102 真异形）。旧守卫 `dumps(obj, indent=2) != text`
        把那 72 份格式完全正常的账判成「请人工同步后重跑」＝用手写 JSON 改 `tags`，
        正是本工具要杜绝的动作（数学分析 ch15 摘幻影 `1x` 时实测撞墙）。
        同族 `backfill_formula_tags.load_strict` 早按 `indent × 尾换行` 两档探测——
        本工具是落后的那份副本。写回必须**还原同一尾串**（含 CRLF 形）。"""
        _mk(self.E, manifest_trail="\n")
        rc, out = self._quiet(lambda: _run(self.E, apply=True))
        self.assertEqual(rc, 0, out)
        for side in ("units", "units-translate"):
            raw = _rb(os.path.join(self.bs, side, "ch2",
                                   "manifest.json")).decode("utf-8")
            self.assertTrue(raw.endswith("}\n"), repr(raw[-3:]))
            self.assertFalse(raw.endswith("\n\n"))
            self.assertEqual(json.loads(raw)["units"][0]["tags"], REAL)

    def test_crlf_manifest_with_trailing_newline_keeps_both_styles(self):
        """还原尾串走的是 `restyle` 之前的 LF 形：CRLF 文件出去还得是 CRLF + `\\r\\n` 结尾。"""
        _mk(self.E, manifest_trail="\n", manifest_crlf=True)
        rc, out = self._quiet(lambda: _run(self.E, apply=True))
        self.assertEqual(rc, 0, out)
        raw = _rb(os.path.join(self.bs, "units", "ch2", "manifest.json")).decode("utf-8")
        self.assertIn("\r\n", raw)
        self.assertNotIn("\n", raw.replace("\r\n", ""))
        self.assertTrue(raw.endswith("}\r\n"))
        self.assertEqual(json.loads(raw)["units"][0]["tags"], REAL)

    def test_refuses_extra_blank_line_at_manifest_tail(self):
        """放宽只到**一个**尾换行：两个＝没有任何写入器产这个形，整文件重生照旧必拒。"""
        self._assert_refused(mkw={"manifest_trail": "\n\n"})

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

    # ── `--false-anchor`：锚点是页码/节号/数学符号（第四类缺陷，⑭ 失明）──────
    FA = "29"

    def _mk_bare_anchor(self):
        """页窗里加一个**整块就是一个数**的裸锚（页眉页码形态），并让契约多一条带该号的块。

        此时 ⑭ 的 bare-only 腿被比例压死（paren_hits=8、bare_only=1 → 8 < 0.9×9）→
        该号**失明**：常规通道必拒，`--mispaired` 语义又不符（印面根本没有 `(29)`）。
        """
        _mk(self.E)
        tree = json.loads(_text(self.c))
        tree["sub_sec"][0]["sub_sec"].append(
            {"formula": "P = [artifact of the running header]", "display": True,
             "tag": self.FA})
        _w(self.c, json.dumps(tree, ensure_ascii=False, indent=2))
        p = os.path.join(self.E, "page_037.json")
        d = json.loads(_text(p))
        d["text"].append({"text": self.FA})
        _w(p, json.dumps(d, ensure_ascii=False, indent=2))

    def test_false_anchor_channel_is_the_only_exit_for_a_blind_phantom(self):
        """失明幻影：常规拒 / mispaired 语义不符 / false-anchor 走得通且四本账同步。"""
        from lib.tag_attestation import (attested_numbers, dir_page_loader,
                                         unattested_tags)
        self._mk_bare_anchor()
        tree = json.loads(_text(self.c))
        self.assertNotIn(self.FA, {str(x) for x in unattested_tags(
            tree, dir_page_loader(self.E), attested_numbers(self.E))},
            "夹具失效：该号已被 ⑭ 判毒，就不该走假锚通道")
        before = _snap(self.E)
        rc, out = self._quiet(lambda: _run(self.E, numbers=(self.FA,), apply=True))
        self.assertEqual(rc, 2)
        self.assertIn("--false-anchor --anchor-kind", out)
        self.assertEqual(_snap(self.E), before)
        rc, out = self._quiet(lambda: _run(self.E, numbers=(self.FA,), apply=True,
                                           false_anchor=True, anchor_kind="page-number",
                                           evidence=EV_FA))
        self.assertEqual(rc, 0, out)
        self.assertIn("APPLIED", out)
        self.assertIn("--false-anchor（假锚：印面无此号，真身=页眉/页脚页码）", out)
        self.assertIn("假锚证据  = (29) p37 裸块 '29'", out)
        tree = json.loads(_text(self.c))
        tags = [b.get("tag") for b in tree["sub_sec"][0]["sub_sec"] if "formula" in b]
        self.assertEqual(tags[-1], "")
        rec = json.loads(io.open(os.path.join(
            self.E, "_formula_tag_deregistrations.jsonl"),
            encoding="utf-8").read().strip().split("\n")[-1])
        self.assertEqual(rec["mode"], "false-anchor")
        self.assertEqual(rec["anchor_kind"], "page-number")
        self.assertEqual(rec["bare_anchors"], {self.FA: {"37": [self.FA]}})
        self.assertEqual(rec["numbers"], [self.FA])

    def test_false_anchor_refused_when_number_has_a_paren_anchor(self):
        """`(N)` 处在一块的**边缘**（块首/块尾贴普通文字）= 编号本形 → 那不是幻影而是
        挂错块，必拒并指路 --mispaired。夹具里三页印的都是 `(27)  label` 这种「号在块首、
        后面跟着文字」的形态，正是页边编号被 OCR 粘进一行的样子。"""
        _mk(self.E)
        before = _snap(self.E)
        rc, out = self._quiet(lambda: _run(self.E, numbers=("27",), apply=True,
                                          false_anchor=True, anchor_kind="page-number",
                                          evidence=EV_FA))
        self.assertEqual(rc, 2)
        self.assertIn("编号本形", out)
        self.assertIn("--mispaired", out)
        self.assertEqual(_snap(self.E), before)
        self.assertFalse(os.path.exists(
            os.path.join(self.E, "_formula_tag_deregistrations.jsonl")))

    def test_false_anchor_allows_a_product_chain_factor(self):
        r"""🔴 新放行档：整章页窗**不印**独立编号块，而 `(N)` 每处都贴在括号/运算符之间
        （Fraleigh ch23 印面 p.194 的 Z₁₂ 陪积链 `(2)(6)=(6)(2)=(31)(4)`）→ 假锚通道走得通，
        台账把逐块原样记进 `paren_factor_anchors`。

        夹具的三页 `(N)  label` 不是「整块就是 `(N)`」，所以条件①（印面无编号列）成立。
        """
        num = "31"
        _mk(self.E)
        tree = json.loads(_text(self.c))
        tree["sub_sec"][0]["sub_sec"].append(
            {"formula": r"\begin{array} { r l } & { ( 2 ) ( 6 ) = ( 6 ) ( 2 ) }"
                        r"\end{array}", "display": True, "tag": num})
        _w(self.c, json.dumps(tree, ensure_ascii=False, indent=2))
        p = os.path.join(self.E, "page_037.json")
        d = json.loads(_text(p))
        d["text"].append({"text": "(2)(6)=(6)(2)=(%s)(4)" % num})
        d["text"].append({"text": num})
        _w(p, json.dumps(d, ensure_ascii=False, indent=2))
        rc, out = self._quiet(lambda: _run(self.E, numbers=(num,), apply=True,
                                           false_anchor=True, anchor_kind="math-glyph",
                                           evidence=EV_CHAIN))
        self.assertEqual(rc, 0, out)
        self.assertIn("APPLIED", out)
        self.assertIn("括号锚点  = (%s)" % num, out)
        rec = json.loads(io.open(os.path.join(
            self.E, "_formula_tag_deregistrations.jsonl"),
            encoding="utf-8").read().strip().split("\n")[-1])
        self.assertEqual(rec["mode"], "false-anchor")
        self.assertEqual(rec["anchor_kind"], "math-glyph")
        self.assertEqual(rec["paren_factor_anchors"],
                         {num: ["p37 | (2)(6)=(6)(2)=(%s)(4)" % num]})

    def test_one_standalone_label_in_the_window_voids_the_factor_clearance(self):
        """控件：同一批陪积链里**多印一处**整块就是 `(7)` 的号 ⇒ 印面确有编号列，
        「`(N)` 只是算式内容」这个声称失去章级依据 → 照旧拒（关掉条件①即复现放行）。"""
        num = "31"
        E2 = tempfile.mkdtemp()
        _mk(E2)
        c2 = os.path.join(E2, "book_structure", "ch2.json")
        tree = json.loads(_text(c2))
        tree["sub_sec"][0]["sub_sec"].append(
            {"formula": "(2)(6)=(6)(2)=(%s)(4)" % num, "display": True, "tag": num})
        _w(c2, json.dumps(tree, ensure_ascii=False, indent=2))
        p = os.path.join(E2, "page_037.json")
        d = json.loads(_text(p))
        d["text"] += [{"text": "(2)(6)=(6)(2)=(%s)(4)" % num}, {"text": "(7)"},
                      {"text": num}]
        _w(p, json.dumps(d, ensure_ascii=False, indent=2))
        rc, out = self._quiet(lambda: _run(E2, numbers=(num,), apply=True,
                                          false_anchor=True, anchor_kind="math-glyph",
                                          evidence=EV_CHAIN))
        self.assertEqual(rc, 2)
        self.assertIn("独立编号块", out)
        self.assertFalse(os.path.exists(
            os.path.join(E2, "_formula_tag_deregistrations.jsonl")))

    def test_false_anchor_refused_when_page_window_is_unreadable(self):
        """页窗一页也读不到（⑭ fail-open）时假锚通道**照拒**：「印面无此号」这个声称
        必须有裸块原页当证据，否则等于凭空摘号。
        （「混排块 `page 29 of 41` 不算裸锚」这层粒度住在判据里，由
        `lib/tests/test_tag_attestation.py::TestAnchorLocations` 守——那种页窗下 ⑭
        会直接把号判毒，常规通道就能摘，本通道的校验根本不会跑到。）"""
        _mk(self.E, page_anchor=False)
        tree = json.loads(_text(self.c))
        tree["sub_sec"][0]["sub_sec"].append(
            {"formula": "P = [artifact of the running header]", "display": True,
             "tag": self.FA})
        _w(self.c, json.dumps(tree, ensure_ascii=False, indent=2))
        before = _snap(self.E)
        rc, out = self._quiet(lambda: _run(self.E, numbers=(self.FA,), apply=True,
                                          false_anchor=True, anchor_kind="page-number",
                                          evidence=EV_FA))
        self.assertEqual(rc, 2)
        self.assertIn("连裸块锚点都没有", out)
        self.assertEqual(_snap(self.E), before)

    def test_false_anchor_requires_anchor_kind_from_the_vocabulary(self):
        for kind in ("", "页码"):
            self._mk_bare_anchor()
            before = _snap(self.E)
            rc, out = self._quiet(lambda: _run(self.E, numbers=(self.FA,), apply=True,
                                               false_anchor=True, anchor_kind=kind,
                                               evidence=EV_FA))
            self.assertEqual(rc, 2, "%r 不该放行" % kind)
            self.assertIn("--anchor-kind", out)
            self.assertEqual(_snap(self.E), before)

    def test_false_anchor_and_mispaired_are_exclusive(self):
        self._mk_bare_anchor()
        before = _snap(self.E)
        rc, out = self._quiet(lambda: _run(self.E, numbers=(self.FA,), apply=True,
                                          false_anchor=True, mispaired=True,
                                          host="non-display", anchor_kind="page-number",
                                          evidence=EV_FA))
        self.assertEqual(rc, 2)
        self.assertIn("语义相反", out)
        self.assertEqual(_snap(self.E), before)

    def test_anchor_kind_without_false_anchor_is_not_silently_ignored(self):
        _mk(self.E)
        before = _snap(self.E)
        rc, out = self._quiet(lambda: _run(self.E, apply=True,
                                           anchor_kind="math-glyph"))
        self.assertEqual(rc, 2)
        self.assertIn("--anchor-kind 只在 --false-anchor 通道有意义", out)
        self.assertEqual(_snap(self.E), before)

    def test_false_anchor_flag_stays_inert_for_condemned_numbers(self):
        """⑭ 已判毒的 28 不因 --false-anchor 改变语义：仍走幻影通道、mode=unattested、
        不打印假锚证据（假锚通道只管 ⑭ 看不见的那批）。"""
        _mk(self.E)
        rc, out = self._quiet(lambda: _run(self.E, numbers=(BOGUS,), apply=True,
                                          false_anchor=True, anchor_kind="math-glyph"))
        self.assertEqual(rc, 0, out)
        self.assertIn("⑭ 判毒（幻影）", out)
        self.assertNotIn("假锚证据", out)
        rec = json.loads(io.open(os.path.join(
            self.E, "_formula_tag_deregistrations.jsonl"),
            encoding="utf-8").read().strip().split("\n")[-1])
        self.assertEqual(rec["mode"], "unattested")
        self.assertEqual(rec["bare_anchors"], {})

    def test_false_anchor_second_run_is_noop(self):
        self._mk_bare_anchor()
        self._quiet(lambda: _run(self.E, numbers=(self.FA,), apply=True,
                                 false_anchor=True, anchor_kind="page-number",
                                 evidence=EV_FA))
        before = _snap(self.E)
        rc, out = self._quiet(lambda: _run(self.E, numbers=(self.FA,), apply=True,
                                          false_anchor=True, anchor_kind="page-number",
                                          evidence=EV_FA))
        self.assertEqual(rc, 0)
        self.assertIn("NO-OP", out)
        self.assertEqual(_snap(self.E), before)

    # ── 块上多号（抽取器把展示式里数组的元素当编号收割，数值分析 ch5 例9 实测）──
    def _append_block(self, tag, tags, formula="A = [array of components]",
                      drop_existing=False):
        tree = json.loads(_text(self.c))
        blocks = tree["sub_sec"][0]["sub_sec"]
        if drop_existing:      # 夹具里 20..28 各占一块，测「一处=一块」须先清掉同号那块
            blocks[:] = [b for b in blocks if b.get("tag") != tag]
        blocks.append({"formula": formula, "display": True,
                       "tag": tag, "tags": list(tags)})
        _w(self.c, json.dumps(tree, ensure_ascii=False, indent=2))

    def _last_block(self):
        return json.loads(_text(self.c))["sub_sec"][0]["sub_sec"][-1]

    def test_same_block_tag_plus_tags_is_one_site_for_mispaired(self):
        """同一块的 `tag` 与 `tags[0]` 是**一处**登记的两种书写，不是两处。
        旧码按字段数算成 2 处 → 唯一错挂处被当歧义假拒（实测 2026-10-30）。"""
        _mk(self.E)
        self._append_block("27", ["27", "25.1"], drop_existing=True)
        rc, out = self._quiet(lambda: _run(self.E, numbers=("27",), apply=True,
                                           mispaired=True, host="non-display",
                                           evidence=EV_MIS))
        self.assertEqual(rc, 0, out)
        self.assertNotIn("处（", out)
        self.assertIn("tag+tags", out)

    def test_multi_tag_block_promotes_survivor_into_tag(self):
        """摘幻影号时**幸存者提升为 `tag`**，单号块回到「无 `tags`」的常规形。"""
        _mk(self.E)
        self._append_block("28", ["28", "25.1"])
        rc, out = self._quiet(lambda: _run(self.E, numbers=("28",), apply=True))
        self.assertEqual(rc, 0, out)
        blk = self._last_block()
        self.assertEqual(blk["tag"], "25.1")
        self.assertNotIn("tags", blk)
        rec = json.loads(_text(os.path.join(
            self.E, "_formula_tag_deregistrations.jsonl")).splitlines()[-1])
        self.assertEqual([b for b in rec["contract_blocks"] if b["node"] == "定理2.4"]
                         [-1]["left"], ["25.1"])

    def test_promoted_survivor_is_visible_to_unit_tag_truth(self):
        """提升的意义：`node_tags` 只在 `tag` 非空时才展开 `tags`，幸存者不提升就隐身，
        单元照印面写它反被 Q 层判「编造编号」。"""
        from data.book_structure.book_structure import chapter_tag_map, node_tags
        _mk(self.E)
        self._append_block("28", ["28", "25.1"])
        rc, _out = self._quiet(lambda: _run(self.E, numbers=("28",), apply=True))
        self.assertEqual(rc, 0)
        tree = json.loads(_text(self.c))
        self.assertIn("25.1", node_tags(tree["sub_sec"][0]))
        self.assertIn("25.1", chapter_tag_map(tree)["定理2.4"])

    def test_clearing_tag_without_promotion_hides_survivor(self):
        """对照组（解释上一条为何成立）：`tag` 空、号只留在 `tags` → 对账真值看不见它。"""
        from data.book_structure.book_structure import node_tags
        _mk(self.E)
        tree = json.loads(_text(self.c))
        tree["sub_sec"][0]["sub_sec"].append(
            {"formula": "x = 1", "display": True, "tag": "", "tags": ["99.9"]})
        self.assertNotIn("99.9", node_tags(tree["sub_sec"][0]))

    def test_two_blocks_carrying_the_number_still_ambiguous(self):
        """跨**两块**同号才算歧义：--mispaired 仍拒（一处=一块，不是一处=一个字段）。"""
        _mk(self.E)
        self._append_block("27", ["27"], formula="B = [second block]")
        before = _snap(self.E)
        rc, out = self._quiet(lambda: _run(self.E, numbers=("27",), apply=True,
                                           mispaired=True, host="non-display",
                                           evidence=EV_MIS))
        self.assertEqual(rc, 2)
        self.assertIn("27：该号在契约里登记 2 处", out)
        self.assertEqual(_snap(self.E), before)

    def test_multi_tag_edit_refuses_when_style_not_reproducible(self):
        """字面替换表达不了 + 文件风格无法逐字节复演（pretty 里夹单行 `tags`）→ 必拒且零写入。"""
        _mk(self.E)
        tree = json.loads(_text(self.c))
        tree["sub_sec"][0]["sub_sec"].append(
            {"formula": "A = [array]", "display": True, "tag": "28", "tags": ["28", "25.1"]})
        _w(self.c, _compact_tags(json.dumps(tree, ensure_ascii=False, indent=2)))
        before = _snap(self.E)
        rc, out = self._quiet(lambda: _run(self.E, numbers=("28",), apply=True))
        self.assertEqual(rc, 2, out)
        self.assertIn("无法逐字节复演", out)
        self.assertEqual(_snap(self.E), before)
        self.assertFalse(os.path.exists(
            os.path.join(self.E, "_formula_tag_deregistrations.jsonl")))

    def test_multi_tag_edit_works_in_indent_1_contract_style(self):
        """🔴 indent=1 的**契约**同属正常形（与 manifest 那侧同一个探测、同一份候选集）：
        旧候选集没有它，多号块 + indent=1 = 假拒「风格无法逐字节复演」→ 逼人手写 JSON。
        放宽只加候选，判据仍是「旧树逐字节复演原文」，写出必须回到 indent=1。"""
        _mk(self.E)
        self._append_block("28", ["28", "25.1"])
        _w(self.c, json.dumps(json.loads(_text(self.c)), ensure_ascii=False, indent=1))
        rc, out = self._quiet(lambda: _run(self.E, numbers=("28",), apply=True))
        self.assertEqual(rc, 0, out)
        text = _text(self.c)
        obj = json.loads(text)
        self.assertEqual(self._last_block(), {"formula": "A = [array of components]",
                                              "display": True, "tag": "25.1"})
        self.assertEqual(json.dumps(obj, ensure_ascii=False, indent=1), text)
        self.assertNotIn('"tag": "28"', text)

    def test_multi_tag_edit_works_in_no_space_colon_style(self):
        """🔴 候选风格须含 `separators=(",", ":")`（冒号后不空格的历史契约形）：
        2026-10-30 遍历论_孙文祥 ch6 的 `6.2` 同块 `tag`+`tags` 双登记，字面替换表达不了，
        只能整树重写，而旧候选集探不到该风格 → **假拒**「风格无法逐字节复演」。
        加候选不放宽安全性：探测仍以「旧树逐字节复演原文」为唯一判据（上一条就是反证）。"""
        _mk(self.E)
        self._append_block("28", ["28", "25.1"])
        _w(self.c, json.dumps(json.loads(_text(self.c)), ensure_ascii=False,
                              indent=2, separators=(",", ":")))
        rc, out = self._quiet(lambda: _run(self.E, numbers=("28",), apply=True))
        self.assertEqual(rc, 0, out)
        text = _text(self.c)
        self.assertIn('"tag":"25.1"', text)          # 写出仍按原风格（非 `": "`）
        self.assertNotIn('"tag": "25.1"', text)
        self.assertEqual(self._last_block(), {"formula": "A = [array of components]",
                                              "display": True, "tag": "25.1"})


if __name__ == "__main__":
    unittest.main()
