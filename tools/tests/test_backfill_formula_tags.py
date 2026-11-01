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
契约与 manifest 按**各自**的 JSON 形写回（全架 57 本 2139 份普查：indent=2 / indent=1 /
紧凑 × LF/CRLF × 有无尾换行——旧版只认 indent=2+LF+无尾换行一种，且把 CRLF 读折后按 LF
硬写，整文件换行符被翻掉而内存断言抓不到；Kreyszig ch11 因此整章 3 个漏号无路可回填）；
`--number` 认**多级**印刷号（`(1.1.9)`/`(A.2.1)` 一类按节重启或字母章位形态，旧式只认
单级号会把这类书整类拒在门外）；同键多型节点（Definition/Lemma/Example 共用序标）由
`--unit` 那条 manifest 记录的 `ntype` 收窄定位；**「该号已在账」只在同节域里算 NO-OP**
（逐节重启编号的书：别节同号要 `--restart-per-section` 具名放行并记台账，见 `_mk_secs`）。
负向（一律 exit 2 且零写入）：①无印面佐证 ②该号在**本节**已在账（幂等 NO-OP，exit 0）
②b 该号只在别节在账却不带 `--restart-per-section`③同键多单元
未指定 --unit ④节点里多个未挂号块却不给定位方式 ⑤--needle 命中 0/多个 ⑥目标是行内公式
（该走 register_formula）⑦`--number` 是 0/00 类 OCR 碎片 ⑧缺 --evidence ⑨契约/manifest 是
候选集**外**的形（indent=3/4/6/8，或某处缩进被手改导致任何一形都复现不了原字节 = 真实语料
里那 54 份不规则契约）——此时拒做整文件重写，宁可交人工核对 ⑩节点键不存在 ⑪同键多型却不给 --unit（拒绝猜类型）
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


def _man(entries, language="en"):
    return {"chapter_key": "2", "language": language, "final_md": "x.md", "units": entries}


def _entry(i, key, tags, ntype="theorem"):
    return {"id": "%04d" % i, "file": "%04d_item_%s.md" % (i, key.replace(".", "_")),
            "type": "item", "ntype": ntype, "key": key, "name": key,
            "tags": tags, "images": [], "content": 12, "hash": "deadbeef"}


def _wj(path, obj, indent=2, crlf=False, trail=""):
    """按指定 JSON 形落盘：indent=None 走紧凑形，crlf/trail 管换行符与末字节。

    真实语料里三种形并存（Kreyszig ch1/ch3 是 CRLF、ch10 是 indent=1、ch11 是两者叠加），
    夹具必须能复现它们，否则「按该文件自身的形还原」这条无从测起。
    """
    body = json.dumps(obj, ensure_ascii=False,
                      **({} if indent is None else {"indent": indent}))
    text = body + trail
    if crlf:
        text = text.replace("\n", "\r\n")
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def _mk(extract, translate=True, page_anchor=True, indent=2, dup_entry=False,
        anchor="(4)  product expansion", multi_type=False,
        crlf=False, trail="", language="en", empty_tag=False):
    bs = os.path.join(extract, "book_structure")
    u = os.path.join(bs, "units", "ch2")
    os.makedirs(u)
    tree = _tree()
    if empty_tag:   # 抽取器对「这条式子印面无号」的**显式**记录：tag 键在、值为空串
        tree["sub_sec"][0]["sub_sec"][2]["tag"] = ""
    if multi_type:      # 同键多型：三级序标书里 Definition/Lemma/Example 共用一个 key
        for t, f in (("definition", "\\delta _ { definition } only"),
                     ("example", "\\delta _ { example } only")):
            tree["sub_sec"].append({"key": "定理2.4", "type": t, "name": "2.4 %s" % t,
                                    "page_start": 37, "page_end": 37,
                                    "sub_sec": [{"formula": f, "display": True}]})
    _wj(os.path.join(bs, "ch2.json"), tree, indent=indent, crlf=crlf, trail=trail)
    entries = [_entry(16, "定理2.4", ["3"])]
    if dup_entry:      # 同节内「定义 / 定理」共用序标的真实形态
        entries.append(_entry(17, "定理2.4", []))
    if multi_type:
        entries += [_entry(17, "定理2.4", [], ntype="definition"),
                    _entry(18, "定理2.4", [], ntype="example")]
    _wj(os.path.join(u, "manifest.json"), _man(entries, language), indent=indent,
        crlf=crlf, trail=trail)
    if translate:
        ut = os.path.join(bs, "units-translate", "ch2")
        os.makedirs(ut)
        _wj(os.path.join(ut, "manifest.json"),
            _man([dict(e) for e in entries], language),
            indent=indent, crlf=crlf, trail=trail)
    if page_anchor:
        with io.open(os.path.join(extract, "page_037.json"), "w", encoding="utf-8",
                     newline="\n") as f:
            json.dump({"page": 37, "text": [{"text": anchor, "score": 0.9}]},
                      f, ensure_ascii=False, indent=2)


def _mk_secs(extract):
    """**逐节重启**编号的书：§2.1 印 (4)，§2.4 从 (1) 重启、其 (4) 漏收。

    缺陷根因（2026-10-29 数学分析 ch17 实测）：印面 §17.1 号到 (12)、§17.4 号到 (15)、
    §17.5 自己 (1)…(23)，于是 §17.5 的 `(11)…(16)` 六个真漏，其裸号在**别节**都在账；
    旧的章级「该号已在账 ⇒ NO-OP」把整族挡在正规通道外（同一章里 verify 的 q-inc
    只查同节重号，本来就不把这算重号）。
    """
    bs = os.path.join(extract, "book_structure")
    u = os.path.join(bs, "units", "ch2")
    os.makedirs(u)
    tree = {"key": "2", "type": "chapter", "name": "2 Multiplicative functions",
            "page_start": 37, "page_end": 38,
            "sub_sec": [
                {"key": "2.1", "type": "section", "name": "2.1 Earlier set",
                 "page_start": 37, "page_end": 37,
                 "sub_sec": [{"key": "定理2.1", "type": "theorem", "name": "2.1 Earlier",
                              "page_start": 37, "page_end": 37,
                              "sub_sec": [{"formula": "\\zeta _ { earlier }",
                                           "display": True, "tag": "4"}]}]},
                {"key": "2.4", "type": "section", "name": "2.4 Restart",
                 "page_start": 37, "page_end": 38,
                 "sub_sec": [{"key": "定理2.4", "type": "theorem", "name": "2.4 For n >= 1",
                              "page_start": 37, "page_end": 37,
                              "sub_sec": [
                                  {"formula": "\\varphi ( n ) = n \\prod", "display": True,
                                   "tag": "3"},
                                  {"text": "Suppose, then, that n > 1."},
                                  {"formula": TARGET, "display": True},
                                  {"text": "On the right, in a term such as"},
                                  {"formula": "\\sum _ { d \\mid n } \\frac { \\mu ( d ) } { d }",
                                   "display": True}]}]}]}
    with io.open(os.path.join(bs, "ch2.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(tree, f, ensure_ascii=False, indent=2)
    with io.open(os.path.join(u, "manifest.json"), "w", encoding="utf-8",
                 newline="\n") as f:
        json.dump(_man([_entry(16, "定理2.4", ["3"])]), f, ensure_ascii=False, indent=2)
    with io.open(os.path.join(extract, "page_037.json"), "w", encoding="utf-8",
                 newline="\n") as f:
        json.dump({"page": 37, "text": [{"text": "(4)  product expansion", "score": 0.9}]},
                  f, ensure_ascii=False, indent=2)
    return tree


def _mk_letter_secs(extract):
    """**字母节键**的逐节重启书（附录）：§A.1 印 (4)，§A.3 自己从 (1) 重启、其 (4) 漏收。

    缺陷根因（2026-10-29 数学分析 appendixA 实测）：节域判定复用
    `lib/tag_attestation._sec_index`，其 `_SEC_RE` 只认数字节键 `N.M`，于是
    `A.1`/`A.3` 全部落进 ``None`` 域 ⇒ §A.3 的 (4) 被 §A.1 的 (4)「已在账」顶掉，
    工具打印 `NO-OP 本章 节的契约已登记 4` **exit 0、零写入**——正规回填通道对整类
    字母章位书（附录/补篇）关门，且它不是拒绝而是**假装这号已登记**。
    """
    bs = os.path.join(extract, "book_structure")
    u = os.path.join(bs, "units", "appendixA")
    os.makedirs(u)
    tree = {"key": "A", "type": "chapter", "name": "Appendix A Interpolation",
            "page_start": 37, "page_end": 38,
            "sub_sec": [
                {"key": "A.1", "type": "section", "name": "A.1 Earlier",
                 "page_start": 37, "page_end": 37,
                 "sub_sec": [{"key": "DA1", "type": "description", "name": "A.1 Earlier",
                              "page_start": 37, "page_end": 37,
                              "sub_sec": [{"formula": "\\zeta _ { earlier }",
                                           "display": True, "tag": "4"}]}]},
                {"key": "A.3", "type": "section", "name": "A.3 Restart",
                 "page_start": 37, "page_end": 38,
                 "sub_sec": [{"key": "DA3", "type": "description", "name": "A.3 Spline",
                              "page_start": 37, "page_end": 37,
                              "sub_sec": [
                                  {"formula": "\\varphi ( n ) = n \\prod", "display": True,
                                   "tag": "3"},
                                  {"text": "Suppose, then, that n > 1."},
                                  {"formula": TARGET, "display": True},
                                  {"text": "On the right, in a term such as"},
                                  {"formula": "\\sum _ { d \\mid n } \\frac { \\mu ( d ) } { d }",
                                   "display": True}]}]}]}
    with io.open(os.path.join(bs, "appendixA.json"), "w", encoding="utf-8",
                 newline="\n") as f:
        json.dump(tree, f, ensure_ascii=False, indent=2)
    entry = dict(_entry(8, "DA3", ["3"]), type="desc", ntype="description",
                 file="0008_desc_DA3.md")
    with io.open(os.path.join(u, "manifest.json"), "w", encoding="utf-8",
                 newline="\n") as f:
        json.dump({"chapter_key": "A", "language": "cn", "final_md": "x.md",
                   "units": [entry]}, f, ensure_ascii=False, indent=2)
    with io.open(os.path.join(extract, "page_037.json"), "w", encoding="utf-8",
                 newline="\n") as f:
        json.dump({"page": 37, "text": [{"text": "(4)  product expansion",
                                         "score": 0.9}]}, f, ensure_ascii=False, indent=2)
    return tree


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


def _run_letter(extract, number="4", apply=False, evidence=EV, **flags):
    """同上，但章键取字母附录 `A`（契约 `appendixA.json`、单元目录 `units/appendixA`）。"""
    argv = [extract, "A", "--number", number, "--evidence", evidence]
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


def _rb(p):
    """**字节**读盘：_read 走通用换行会把 CRLF 折成 LF，看不见「换行符被整文件翻掉」
    这类附带改动——旧版回填工具正是这么坏掉的，断言必须用原始字节。"""
    with open(p, "rb") as f:
        return f.read()


def _shape(p):
    """该文件当前的 (indent, 尾换行, 换行符) 形，用工具自己的判据。"""
    blob = _rb(p)
    nl = "\r\n" if b"\r\n" in blob else "\n"
    text = blob.decode("utf-8").replace("\r\n", "\n")
    return bft._shape_of(json.loads(text), text) + (nl,)


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

    def test_empty_string_tag_is_a_value_not_a_missing_key(self):
        """`tag: ""`（抽取器**显式**记「这条式子印面无号」）的块必须能回填，且写出仍带该键。

        动因（2026-10-31 Rising Sea ch2 `2.1.1.1` 实测）：一致性断言旧写法用
        `del ["tag"]` 表示「去掉新增 tag」——对**键本就不存在**的块成立，对空串块则把
        原文件里那一行**删掉**，断言必然失败 ⇒ REFUSE「契约改动不止目标块的 tag」，
        佐证与邻接全过也写不进。全架 15437 个带 tag 键的块里 122 个是空串、散布 12 本书
        （Lehmann / Evans-SDE / Gelfand–Manin / 数学分析 / Rising Sea…），即这类块**整类**
        无路回填。空串在 `node_tags` 里是 falsy ⇒ 不算在账号，回填语义与无键块一致。
        """
        _mk(self.E, empty_tag=True)
        craw = _read(self.c)
        self.assertIn('"tag": ""', craw)
        self.assertEqual(_run(self.E, node="定理2.4", block=1, apply=True), 0)
        after = json.loads(_read(self.c))
        blk = after["sub_sec"][0]["sub_sec"][2]
        self.assertEqual(blk.get("tag"), "4")
        blk["tag"] = ""          # 还原**原值**即回到原字节 = 只动了这一个值，没顺手删键
        self.assertEqual(json.dumps(after, ensure_ascii=False, indent=2), craw)
        # 控件：旧路（删键）在这形上必炸——把上面改成 `del` 就复现 REFUSE，不是断言变松。
        import copy as _copy
        undo_del = _copy.deepcopy(after)
        del undo_del["sub_sec"][0]["sub_sec"][2]["tag"]
        self.assertNotEqual(json.dumps(undo_del, ensure_ascii=False, indent=2), craw)

    # ── 正向：契约/manifest 的 JSON 形不止一种（全架 57 本 2139 份普查）──
    def _new_E(self):
        """一个用例里跑多档形时，每档都要一棵**干净**的树：
        复用 setUp 的 self.E 会让 _mk 的 makedirs 撞车，还会带上上一档的台账/备份。"""
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        return td.name

    @staticmethod
    def _cp(e):
        return (os.path.join(e, "book_structure", "ch2.json"),
                os.path.join(e, "book_structure", "units", "ch2", "manifest.json"))

    def test_every_census_shape_lands_in_its_own_shape(self):
        """indent=2+LF、indent=1+CRLF+尾换行、紧凑+LF 都得能落账，**且落完仍是原来那个形**；
        三本账的**备份件**还须各自字节可回滚（旧命名让两侧 manifest 互相盖掉）。

        动因：旧版只认 indent=2+LF+无尾换行一种形，Kreyszig ch11（indent=1+CRLF）的 3 个
        ⑱ 漏号整章无路可回填；它又把 CRLF 读成 LF 后按 indent=2 硬写，整文件换行符被翻掉，
        而「回到原字节」断言只在内存里比，抓不到这种附带改动（2026-10-29）。
        """
        for indent, crlf, trail in ((2, False, ""), (1, True, "\n"),
                                    (2, True, ""), (None, False, "\n")):
            with self.subTest(indent=indent, crlf=crlf, trail=trail):
                e = self._new_E()
                _mk(e, indent=indent, crlf=crlf, trail=trail)
                c, m = self._cp(e)
                mt = os.path.join(e, "book_structure", "units-translate",
                                  "ch2", "manifest.json")
                self.assertEqual(_shape(c), (indent, trail, "\r\n" if crlf else "\n"))
                before = {p: (_shape(p), _rb(p)) for p in (c, m, mt)}
                self.assertEqual(_run(e, node="定理2.4", block=1, apply=True), 0)
                for p in (c, m, mt):
                    blob = _rb(p)
                    self.assertEqual(_shape(p), before[p][0],
                                     "%s 落账后被换成了另一种形" % p)
                    if crlf:      # CRLF 文件里不许混进裸 LF（换行符被整文件翻掉的直接证据）
                        self.assertEqual(blob.count(b"\n"), blob.count(b"\r\n"), p)
                baks = sorted(os.listdir(os.path.join(e, "_bak_formula_tags")))
                self.assertEqual(len(baks), 1)
                bak = os.path.join(e, "_bak_formula_tags", baks[0])
                want = {p: ("book_structure+ch2.json" if p == c else
                            "book_structure+%s+ch2+manifest.json"
                            % ("units" if p == m else "units-translate"))
                        for p in (c, m, mt)}
                self.assertEqual(sorted(os.listdir(bak)), sorted(want.values()),
                                 "备份件必须**三份都在**且名字互不覆盖")
                for p, nm in want.items():
                    self.assertEqual(_rb(os.path.join(bak, nm)), before[p][1],
                                     "%s 的备份件不是原字节（回滚即附带改动）" % p)
                for side in ("units", "units-translate"):
                    man = json.loads(_rb(os.path.join(e, "book_structure", side, "ch2",
                                                      "manifest.json")).decode("utf-8"))
                    self.assertEqual(man["units"][0]["tags"], ["3", "4"])

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
    def _refuse(self, mkw=None, e=None, **kw):
        e = e or self.E
        c, m = self._cp(e)
        _mk(e, **(mkw or {}))
        craw, mraw = _read(c), _read(m)
        argv = kw.pop("argv", None)
        code = (bft.main(argv) if argv is not None
                else _run(e, apply=True, **kw))
        self.assertEqual(code, 2)
        self.assertEqual(_read(c), craw)
        self.assertEqual(_read(m), mraw)
        self.assertFalse(os.path.exists(os.path.join(e,
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

    def test_refuse_indent_outside_census(self):
        """候选集按全架 2139 份普查定（indent=2/1/紧凑；3/4/6/8 零份），集外一律拒。"""
        for indent in (3, 4, 6, 8):
            with self.subTest(indent=indent):
                self._refuse(e=self._new_E(), mkw={"indent": indent},
                             number="4", node="定理2.4", block=1)

    def test_refuse_mixed_indent_file(self):
        """某一形「看着像」但整文件复现不了原字节的（真实语料里 54 份契约即此类）→ 拒。"""
        _mk(self.E)
        raw = _rb(self.c)
        mutated = raw.replace(b'\n      "key"', b'\n       "key"', 1)
        self.assertNotEqual(mutated, raw)      # 夹具确实把一处缩进改深了一格
        with open(self.c, "wb") as f:
            f.write(mutated)
        craw, mraw = _rb(self.c), _rb(self.m)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = _run(self.E, node="定理2.4", block=1, apply=True)
        self.assertEqual(rc, 2, buf.getvalue())
        self.assertIn("拒绝整文件重写", buf.getvalue())
        self.assertEqual(_rb(self.c), craw)
        self.assertEqual(_rb(self.m), mraw)
        self.assertFalse(os.path.exists(os.path.join(self.E,
                                                     "_formula_tag_fixes.jsonl")))

    def test_refuse_unknown_node_key(self):
        self._refuse(number="4", node="定理2.99", block=1)

    def test_refuse_same_key_multi_type_without_unit(self):
        """收窄靠 --unit 那条记录的 ntype；不给就照旧拒绝，绝不猜编号属于哪个类型。"""
        self._refuse(mkw={"multi_type": True}, number="4", node="定理2.4", block=0)

    def test_refuse_without_locator(self):
        self._refuse(argv=[self.E, "2", "--number", "4", "--evidence", EV, "--apply"])

    # ── 逐节重启编号的书：别节同号 ≠「已在账」（数学分析 ch17 §17.5 实测）──
    def test_cross_section_duplicate_needs_a_named_flag(self):
        _mk_secs(self.E)
        craw, mraw = _read(self.c), _read(self.m)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = _run(self.E, node="定理2.4", block=1, apply=True)
        self.assertEqual(rc, 2, buf.getvalue())
        self.assertIn("已在别节登记", buf.getvalue())
        self.assertIn("2.1", buf.getvalue())
        self.assertIn("--restart-per-section", buf.getvalue())
        self.assertEqual(_read(self.c), craw)          # 零写入
        self.assertEqual(_read(self.m), mraw)
        self.assertFalse(os.path.exists(os.path.join(self.E, "_formula_tag_fixes.jsonl")))

    def test_restart_per_section_flag_lands_and_is_ledgered(self):
        _mk_secs(self.E)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = _run(self.E, node="定理2.4", block=1, apply=True,
                      restart_per_section=True)
        self.assertEqual(rc, 0, buf.getvalue())
        self.assertIn("跨节同号", buf.getvalue())
        rec = json.loads(_read(os.path.join(
            self.E, "_formula_tag_fixes.jsonl")).strip().split("\n")[-1])
        self.assertEqual(rec["section_domain"], "2.4")
        self.assertEqual(rec["cross_section_domains"], ["2.1"])
        man = json.loads(_read(self.m))
        self.assertEqual(man["units"][0]["tags"], ["3", "4"])

    # ── 字母节键（附录/补篇）同样按节取域（数学分析 appendixA §A.3 实测）──
    def test_letter_section_domain_index(self):
        """`_domain_index` 认字母节键：`A.1`/`A.3` 是**两个**域，不是同一个 ``None``。"""
        tree = _mk_letter_secs(self.E)
        sec = bft._domain_index(tree)
        self.assertEqual(sec["A.1"], "A.1")
        self.assertEqual(sec["DA1"], "A.1")
        self.assertEqual(sec["DA3"], "A.3")
        self.assertEqual(sec["A"], None)          # 章键本身不是节域
        dom, _s = bft.contract_tag_domains(tree)
        self.assertEqual(dom["4"], {"A.1"})
        self.assertEqual(dom["3"], {"A.3"})

    def test_letter_section_duplicate_is_not_a_noop(self):
        """§A.1 的 (4) **不能**冒充 §A.3 的 (4)：必须是拒绝 + 指路，绝不能 exit 0 报 NO-OP
        （旧判据把字母节全归 ``None`` 域 ⇒ 「该号已在账」⇒ 假装这号已登记、零写入）。"""
        _mk_letter_secs(self.E)
        c = os.path.join(self.bs, "appendixA.json")
        m = os.path.join(self.bs, "units", "appendixA", "manifest.json")
        craw, mraw = _read(c), _read(m)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = _run_letter(self.E, node="DA3", block=1, apply=True)
        self.assertEqual(rc, 2, buf.getvalue())
        self.assertNotIn("NO-OP", buf.getvalue())
        self.assertIn("已在别节登记", buf.getvalue())
        self.assertIn("A.1", buf.getvalue())
        self.assertIn("--restart-per-section", buf.getvalue())
        self.assertEqual(_read(c), craw)          # 零写入
        self.assertEqual(_read(m), mraw)
        self.assertFalse(os.path.exists(os.path.join(self.E, "_formula_tag_fixes.jsonl")))

    def test_letter_section_flag_lands_and_is_ledgered(self):
        _mk_letter_secs(self.E)
        c = os.path.join(self.bs, "appendixA.json")
        m = os.path.join(self.bs, "units", "appendixA", "manifest.json")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = _run_letter(self.E, node="DA3", block=1, apply=True,
                             restart_per_section=True)
        self.assertEqual(rc, 0, buf.getvalue())
        self.assertIn("跨节同号", buf.getvalue())
        rec = json.loads(_read(os.path.join(
            self.E, "_formula_tag_fixes.jsonl")).strip().split("\n")[-1])
        self.assertEqual(rec["section_domain"], "A.3")
        self.assertEqual(rec["cross_section_domains"], ["A.1"])
        self.assertEqual(json.loads(_read(m))["units"][0]["tags"], ["3", "4"])

    def test_same_letter_section_duplicate_is_still_a_noop(self):
        """号落进**本节**之后再跑 = 真幂等 NO-OP（放宽字母域不能把这层保护也放宽掉）。"""
        _mk_letter_secs(self.E)
        self.assertEqual(_run_letter(self.E, node="DA3", block=1, apply=True,
                                     restart_per_section=True), 0)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = _run_letter(self.E, node="DA3", block=1, apply=True,
                             restart_per_section=True)
        self.assertEqual(rc, 0, buf.getvalue())
        self.assertIn("A.3 节的契约已登记", buf.getvalue())

    def test_multivolume_page_jsons_read_from_volume_dir(self):
        """多册书：`page_*.json` 只放在各册子目录里（`_extract/上册/`，两册页码各自从 1 起）。
        旧写法直接读 `extract_dir` 根 ⇒ 每页 `isfile` 皆 False ⇒ 佐证 (a)/(e) 在整本多册书上
        **静默失效**（数学分析 ch17 实测：印面页边 (11)…(16) 明明在 `下册/page_359-361.json`，
        工具却报「既不在页区间锚点里」）。页目录一律走 SSOT `lib.page_dir`。"""
        _mk(self.E, page_anchor=False)
        tree = json.loads(_read(self.c))
        tree["page_dir"] = "上册"
        with io.open(self.c, "w", encoding="utf-8", newline="\n") as f:
            json.dump(tree, f, ensure_ascii=False, indent=2)
        vol = os.path.join(self.E, "上册")
        os.makedirs(vol)
        with io.open(os.path.join(vol, "page_037.json"), "w", encoding="utf-8",
                     newline="\n") as f:
            json.dump({"page": 37, "text": [{"text": "(4)  product expansion",
                                             "score": 0.9}]}, f, ensure_ascii=False,
                      indent=2)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = _run(self.E, node="定理2.4", block=1, anchor_page="37")
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn("页文字层  = 上册", out)
        self.assertIn("(a) 页区间", out)
        self.assertIn("(e) 指定页 p37", out)
        self.assertFalse(os.path.isfile(os.path.join(self.E, "page_037.json")))

    def test_anchor_in_another_section_does_not_veto(self):
        """逐节重启的书：**别节**的整块 `(N)` 锚点是别条公式自己的号，不参与邻接否决
        （数学分析 appendixA (3)(4) 实测：`(4)` 的锚点躺在 DA6/DA8 自己的式子上，
        DA3 的 (4) 被 OCR 粘进行内，旧判据一律拒绝，这类书正规通道整类关门）。"""
        _mk_secs(self.E)
        tree = json.loads(_read(self.c))
        tree["sub_sec"][0]["sub_sec"][0]["sub_sec"].append({"text": "(4)"})
        with io.open(self.c, "w", encoding="utf-8", newline="\n") as f:
            json.dump(tree, f, ensure_ascii=False, indent=2)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = _run(self.E, node="定理2.4", block=1, apply=True,
                      restart_per_section=True)
        self.assertEqual(rc, 0, buf.getvalue())
        self.assertIn("别节另有 1 处该号锚点", buf.getvalue())

    def test_same_section_duplicate_is_still_a_noop(self):
        """号落进**本节**之后再跑 = 真幂等 NO-OP（章级判据原有的保护不能丢）。"""
        _mk_secs(self.E)
        self.assertEqual(_run(self.E, node="定理2.4", block=1, apply=True,
                              restart_per_section=True), 0)
        craw, mraw = _read(self.c), _read(self.m)
        self.assertEqual(_run(self.E, node="定理2.4", block=1, apply=True,
                              restart_per_section=True), 0)
        self.assertEqual(_read(self.c), craw)
        self.assertEqual(_read(self.m), mraw)


# ── #25 散文判据按书面语分叉 + 中文书「页边编号在右侧」倒退 leg ──────────────
# 真形态来源：2026-10-31 数学分析 ch17 D21 六连号 (11)…(16) 全部走
# `--confirm-non-adjacent` 人工具名才落账（`_formula_tag_fixes.jsonl` 三条
# `adjacency_confirmed=True`），fitz 裁 p359/p360 确证号印在展示式右缘。
_D21_DISPLAY = (r"f ( x ) \, = \, \frac { 2 } { \pi } { \int } _ { 0 } ^ { + \infty }"
                r" \, \mathrm { c o s \, } \, u x \mathrm { d } u { \int } _ { 0 } "
                r"^ { + \infty } \, f ( \, t \, ) \mathrm { c o s \, } \, u t \, "
                r"\mathrm { d } \, t \, .")
# 真契约 `ch17.json` → D21 → sub_sec[16:21] 逐块抄入（生成脚本
# `_p830_d21_seq.py`；锚点号换成夹具用的 4，其余字面不动）。
D21_SLICE = [
    {"text": u"这时，积分公式可写为", "line_start": True},
    {"formula": _D21_DISPLAY, "display": True},
    {"text": "cos uxdu f(t)cos utdt.", "line_start": True, "indent": 13.2},
    {"text": u"f（x）="},
    {"text": "(4)"},
]
# 收紧侧的形：锚点向后**跨过一句中文**才够到展示式——旧拉丁档看不见汉字句子
# （一个 4+ 字母词都没有）照样放行，全架 1277 处即此形。
HAN_CROSS = [
    {"formula": "\\varphi ( n ) = n \\prod", "display": True, "tag": "3"},
    {"text": "(4)"},
    {"text": u"在这两个公式中，f 是连续的"},
    {"formula": TARGET, "display": True},
]


class AdjacencyProseForkTest(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.E = self._td.name
        self.c = os.path.join(self.E, "book_structure", "ch2.json")

    def tearDown(self):
        self._td.cleanup()

    def _mk_seq(self, blocks, language):
        _mk(self.E, language=language)
        tree = json.loads(_read(self.c))
        tree["sub_sec"][0]["sub_sec"] = blocks
        with io.open(self.c, "w", encoding="utf-8", newline="\n") as f:
            json.dump(tree, f, ensure_ascii=False, indent=2)
        return tree

    def test_cjk_book_pairs_the_right_margin_number_backward(self):
        """中文书：display → 两个**无汉字**续行碎片 → 锚点「(4)」= 页边编号印在右缘，
        OCR 按列切把号排到公式之后。向后②走空，倒退 leg 必须顶上（旧判据在此假拒，
        实测三处靠 `--confirm-non-adjacent` 具名才落账）。"""
        tree = self._mk_seq([dict(b) for b in D21_SLICE], "cn")
        blk = tree["sub_sec"][0]["sub_sec"][1]
        self.assertIs(bft.anchor_adjacency(tree, blk, "4")[0], False)   # 旧档（默认关）
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = _run(self.E, node="定理2.4", block=0, apply=True)
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn(u"向前", out)
        self.assertIn(u"页边编号印在展示式右缘", out)
        self.assertEqual(json.loads(_read(self.c))["sub_sec"][0]["sub_sec"][1]["tag"], "4")

    def test_latin_book_never_gets_the_backward_leg(self):
        """同一份块序列换成语种 `en` 必须照旧拒绝：给拉丁书开倒退 = 把 (6.5.10)
        那类已证伪挂重新放行（真契约对照见 `test_real_lehmann_pairings_hold`）。"""
        tree = self._mk_seq([dict(b) for b in D21_SLICE], "en")
        blk = tree["sub_sec"][0]["sub_sec"][1]
        self.assertIs(bft.anchor_adjacency(tree, blk, "4")[0], False)
        craw = _read(self.c)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = _run(self.E, node="定理2.4", block=0, apply=True)
        out = buf.getvalue()
        self.assertEqual(rc, 2, out)
        self.assertIn(u"既不相邻", out)
        self.assertNotIn(u"向前", out)                     # 拒绝话术不承诺没做的判
        self.assertEqual(_read(self.c), craw)              # 零写入

    def test_han_sentence_now_stops_the_forward_walk(self):
        """收紧侧（同一分叉的另一半）：锚点向后**跨过汉字句子**才够到展示式 = 印面上
        号挨的是句子，不是那条公式 → 中文书必须拒；旧拉丁档把它放过去（rc 0）。"""
        tree = self._mk_seq([dict(b) for b in HAN_CROSS], "cn")
        blk = tree["sub_sec"][0]["sub_sec"][3]
        self.assertIs(bft.anchor_adjacency(tree, blk, "4", cjk_prose=True)[0], False)
        craw = _read(self.c)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = _run(self.E, node="定理2.4", block=1, apply=True)
        out = buf.getvalue()
        self.assertEqual(rc, 2, out)
        self.assertIn(u"既不相邻", out)
        self.assertEqual(_read(self.c), craw)
        # 变异对照：拉丁档看不见汉字句子 ⇒ 同一个站点旧判据放行（这条断言就是
        # 「1277 处收紧」的成因，别把它当冗余删掉）。
        self.assertIs(bft.anchor_adjacency(tree, blk, "4", cjk_prose=False)[0], True)

    def test_prose_classifiers_are_not_interchangeable(self):
        """两档散文判据各管一本书，写死四形，防止有人日后「统一成一条正则」。"""
        latin = {"text": "the assignment of the two subjects is made at random"}
        frag = {"text": "cos uxdu f(t)cos utdt."}
        cjk = {"text": u"在这两个公式中，f 是连续的"}
        fullwidth = {u"text": u"f（x）="}          # 全角括号 = 中文书体例，不是句子
        self.assertTrue(bft._is_prose_fragment(latin, False))
        self.assertFalse(bft._is_prose_fragment(latin, True))    # ← 汉字档会跨英文句子
        self.assertTrue(bft._is_prose_fragment(frag, False))     # ← 拉丁档把续行当句子
        self.assertFalse(bft._is_prose_fragment(frag, True))
        self.assertFalse(bft._is_prose_fragment(cjk, False))     # ← 拉丁档看不见中文句子
        self.assertTrue(bft._is_prose_fragment(cjk, True))
        self.assertFalse(bft._is_prose_fragment(fullwidth, True))
        self.assertFalse(bft._is_prose_fragment({"formula": "\\alpha", "display": False}, True))
        self.assertTrue(bft.cjk_prose_lang("cn"))
        self.assertFalse(bft.cjk_prose_lang("en"))
        self.assertFalse(bft.cjk_prose_lang(None))      # 拿不到语种 = 维持旧判据（收口）

    def test_real_lehmann_pairings_hold(self):
        """真契约负向测（语料不在盘则跳过）：Lehmann 两笔**已证伪挂**
        (6.5.10)（号挨概率表）/ (3.2.26)（号挨被编号散文）在出厂路径（`language=en`
        ⇒ 拉丁档）下必须**一条展示式都不认**（该节点整块否决）；把语种开关手动打开，
        两笔各自复活一条——(6.5.10) 认到的块**自己带着 tag 6.5.11**（同一时刻两个号
        抢一条展示式），(3.2.26) 认到后面第 32 块的 `I _ { j } = \\left\\{…`。
        这条就是「关掉分叉即复现」的控件：它证明语种开关不是装饰。"""
        import glob as _glob
        hits = _glob.glob(u"D:/study/book/*/elements-of-large-sample-theory/_extract")
        if not hits:
            self.skipTest(u"Lehmann 语料不在盘")
        ext = hits[0]
        lang = json.loads(_read(os.path.join(
            ext, "book_structure", "units", "ch6", "manifest.json"))).get("language")
        self.assertEqual(lang, "en")
        self.assertFalse(bft.cjk_prose_lang(lang))
        for cf, nkey, num in ((u"ch6", u"6.5-3", u"6.5.10"), (u"ch3", u"3.2-5", u"3.2.26")):
            tree = json.loads(_read(os.path.join(ext, "book_structure", cf + ".json")))
            _td, sec_of = bft.contract_tag_domains(tree)
            node = bft.find_node(tree, nkey)
            own = sec_of.get(str(node.get("key")))
            seq = node.get("sub_sec") or []
            ds = [b for b in seq if isinstance(b, dict) and bft._is_display(b)]
            self.assertTrue(ds, u"%s 宿主节点没有展示块" % num)
            vetoed = [b for b in ds
                      if bft.anchor_adjacency(tree, b, num, sec_of=sec_of,
                                              own_dom=own, cjk_prose=False)[0] is not False]
            self.assertEqual(vetoed, [], u"%s 出厂路径必须整块否决" % num)
            reopened = [i for i, b in enumerate(ds)
                        if bft.anchor_adjacency(tree, b, num, sec_of=sec_of,
                                                own_dom=own, cjk_prose=True)[0] is True]
            self.assertTrue(reopened, u"%s 的汉字档对照失效 = 分叉开关其实没起作用" % num)



if __name__ == "__main__":
    unittest.main()
