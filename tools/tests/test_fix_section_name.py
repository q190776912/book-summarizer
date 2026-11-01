"""test_fix_section_name.py — 修回 OCR 残缺节标题的正规通道（五本账同步 + 拒绝面）。

缺陷根因（Apostol《Introduction to Analytic Number Theory》实测 2026-09-29）：
扫描件 OCR 把节标题里的希腊字母读成拉丁字母（印面 `φ(n)` → 契约 `p(n)`、`Λ(n)` → `A(n)`、
`σ_α(n)` → `oa(n)`）。写手按「以印面为唯一真值」把单元 H2 写成 `$\\varphi(n)$`，门控
`lib/section_titles.title_problems` 随即报「契约 name 与单元标题互非前缀；以印刷证据为准统一五处」。
闸是对的、契约是残缺的，但**写手禁改契约**，主代理手改 JSON 又极易只改一处留下四账漂移。

修复形态：`tools/fix_section_name.py` = 带断言的正规通道（锚定字节替换、写后复算、印面证据必填、
备份 + JSONL 台账），marker 一本账交既有 `tools/sync_translate_markers.py`。

正向：dry-run 不落盘；--apply 后契约与 manifest 的该节 name 变新值、**其余字节逐字不变**、
单元 H2 与新名在 `norm_title` 下 MATCH、台账落一行、再跑一次为幂等 no-op。
负向：①key 不存在 / ②锚点重复命中 / ③`--name` 含 LaTeX 标记 / ④缺 `--evidence` /
⑤`--name` 不以序标开头 / ⑥单元 H2 与新名不同形（= 单元侧写错，禁把契约拉歪去迁就）/
⑦manifest 与契约该节名本就不一致 —— 一律 exit 2 且**一个文件都不写**。
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
    "fix_section_name", os.path.join(_ROOT, "tools", "fix_section_name.py"))
fsn = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(fsn)

OLD = "2.3 The Euler totient function p(n)"
NEW = "2.3 The Euler totient function φ(n)"
H2 = "## §2.3 The Euler totient function $\\varphi(n)$"


def _mk(extract, h2=H2, contract_name=OLD, manifest_name=OLD, dup_key=False,
        cross_type_key=False):
    bs = os.path.join(extract, "book_structure")
    u = os.path.join(bs, "units", "ch2")
    os.makedirs(u)
    tree = {
        "chapter_key": "2",
        "sub_sec": [
            {"key": "2.3", "type": "section", "name": contract_name,
             "page_start": 37, "page_end": 38,
             "sub_sec": [{"type": "description", "key": "D4", "name": "",
                          "page_start": 37, "sub_sec": [
                              {"type": "text", "text": "Here is a short table."}]}]},
            {"key": "2.4", "type": "section", "name": "2.4 Another section",
             "page_start": 38, "sub_sec": []},
        ],
    }
    if dup_key:
        tree["sub_sec"].append({"key": "2.3", "type": "section", "name": contract_name,
                                "page_start": 39, "sub_sec": []})
    if cross_type_key:
        # 印面把章末习题按节号起号 → 同键的**习题**节点与节共存（Lehmann ch1 §1.1 与
        # §1.7 的 Problem 1.1）；节名修复必须只按 type 命中节节点，不碰习题那侧。
        tree["sub_sec"].append({"key": "2.3", "type": "exercise",
                                "name": "EXERCISE NAME THAT MUST NOT MOVE",
                                "page_start": 47, "consolidated": True,
                                "sub_sec": [{"type": "text", "text": "2.3 Prove it."}]})
    with io.open(os.path.join(bs, "ch2.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(tree, f, ensure_ascii=False, indent=2)
    man = {"chapter_key": "2", "language": "en", "units": [
        {"id": "0008", "file": "0008_section_2_3.md", "type": "section", "ntype": "section",
         "key": "2.3", "name": manifest_name, "tags": [], "images": [], "content": 5,
         "hash": "deadbeef"}]}
    if cross_type_key:
        man["units"].append({"id": "0117", "file": "0117_exercise_2_3.md",
                             "type": "exercise", "ntype": "exercise",
                             "key": "2.3", "name": "EXERCISE NAME THAT MUST NOT MOVE",
                             "tags": [], "images": [], "content": 1, "hash": "feedface"})
    with io.open(os.path.join(u, "manifest.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(man, f, ensure_ascii=False, indent=2)
    with io.open(os.path.join(u, "0008_section_2_3.md"), "w", encoding="utf-8",
                 newline="\n") as f:
        f.write("<!-- book-summarizer DONE unit: id=0008 type=section key=2.3 name=%s -->\n\n%s\n\nbody\n"
                % (manifest_name, h2))


def _run(extract, name=NEW, evidence="fitz 300dpi 裁物理页37标题行，印面作 φ(n)", apply=False,
         extra=()):
    argv = [extract, "2", "2.3", "--name", name, "--evidence", evidence] + list(extra)
    if apply:
        argv.append("--apply")
    return fsn.main(argv)


def _read(p):
    return io.open(p, encoding="utf-8").read()


class FixSectionNameTest(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.E = self._td.name
        self.bs = os.path.join(self.E, "book_structure")
        self.u = os.path.join(self.bs, "units", "ch2")

    def tearDown(self):
        self._td.cleanup()

    # ── 正向 ────────────────────────────────────────────────────────────
    def test_dry_run_writes_nothing(self):
        _mk(self.E)
        before = {p: _read(os.path.join(self.u, p)) for p in ("manifest.json", "0008_section_2_3.md")}
        cpath = os.path.join(self.bs, "ch2.json")
        craw = _read(cpath)
        self.assertEqual(_run(self.E), 0)
        self.assertEqual(_read(cpath), craw)
        for p, v in before.items():
            self.assertEqual(_read(os.path.join(self.u, p)), v)
        self.assertFalse(os.path.exists(os.path.join(self.E, "_section_name_fixes.jsonl")))

    def test_apply_changes_only_the_name_bytes(self):
        _mk(self.E)
        cpath = os.path.join(self.bs, "ch2.json")
        mpath = os.path.join(self.u, "manifest.json")
        craw, mraw = _read(cpath), _read(mpath)
        self.assertEqual(_run(self.E, apply=True), 0)
        new_craw, new_mraw = _read(cpath), _read(mpath)
        # 该节名已换新，且差异只在 name 字面量（其余字节逐字相同）
        self.assertIn(json.dumps(NEW, ensure_ascii=False), new_craw)
        self.assertEqual(new_craw, craw.replace(json.dumps(OLD, ensure_ascii=False),
                                                json.dumps(NEW, ensure_ascii=False)))
        self.assertEqual(new_mraw, mraw.replace(json.dumps(OLD, ensure_ascii=False),
                                                json.dumps(NEW, ensure_ascii=False)))
        self.assertEqual(json.loads(new_craw)["sub_sec"][0]["page_start"], 37)
        self.assertTrue(os.path.isdir(os.path.join(self.E, "_bak_section_names")))
        lines = io.open(os.path.join(self.E, "_section_name_fixes.jsonl"),
                        encoding="utf-8").read().strip().split("\n")
        rec = json.loads(lines[-1])
        self.assertEqual(rec["new"], NEW)
        self.assertEqual(rec["heading_check"], "MATCH")
        # 单元正文一字节未动（marker 一本账由 sync_translate_markers 负责）
        self.assertIn("name=%s" % OLD, _read(os.path.join(self.u, "0008_section_2_3.md")))

    def test_second_run_is_idempotent(self):
        _mk(self.E)
        self.assertEqual(_run(self.E, apply=True), 0)
        self.assertEqual(_run(self.E, apply=True, extra=["--check"]), 0)

    def test_apply_when_key_collides_with_exercise_number(self):
        """同键的节与章末习题共存（Lehmann ch1 1.1 / ch2 2.7 / ch7 7.5 实测）：
        旧锚点判据「key 命中数≠1 即拒绝」让这三处印刷残缺节名永远修不了；
        现按 `"type": "section"` 收窄，只动节那一侧，习题节点名一字节不变。"""
        _mk(self.E, cross_type_key=True)
        cpath = os.path.join(self.bs, "ch2.json")
        mpath = os.path.join(self.u, "manifest.json")
        craw, mraw = _read(cpath), _read(mpath)
        self.assertEqual(_run(self.E, apply=True), 0)
        new_craw, new_mraw = _read(cpath), _read(mpath)
        self.assertEqual(new_craw, craw.replace(json.dumps(OLD, ensure_ascii=False),
                                                json.dumps(NEW, ensure_ascii=False)))
        self.assertEqual(new_mraw, mraw.replace(json.dumps(OLD, ensure_ascii=False),
                                                json.dumps(NEW, ensure_ascii=False)))
        self.assertEqual(new_craw.count("EXERCISE NAME THAT MUST NOT MOVE"), 1)
        tree = json.loads(new_craw)
        ex = [n for n in tree["sub_sec"] if n.get("type") == "exercise"][0]
        self.assertEqual(ex["name"], "EXERCISE NAME THAT MUST NOT MOVE")

    # ── 负向：一律 exit 2 且零写入 ──────────────────────────────────────
    def _assert_refuse(self, code, argv_name=NEW, evidence="fitz 300dpi 裁物理页37标题行，印面作 φ(n)",
                       **mkw):
        _mk(self.E, **mkw)
        cpath = os.path.join(self.bs, "ch2.json")
        craw = _read(cpath)
        self.assertEqual(_run(self.E, name=argv_name, evidence=evidence, apply=True), code)
        self.assertEqual(_read(cpath), craw)
        self.assertFalse(os.path.exists(os.path.join(self.E, "_section_name_fixes.jsonl")))

    def test_refuse_unknown_key(self):
        _mk(self.E)
        cpath = os.path.join(self.bs, "ch2.json")
        craw = _read(cpath)
        self.assertEqual(fsn.main([self.E, "2", "2.99", "--name", "2.99 Whatever",
                                   "--evidence", "fitz 300dpi 裁图目视确认印面如此", "--apply"]), 2)
        self.assertEqual(_read(cpath), craw)

    def test_refuse_ambiguous_anchor(self):
        self._assert_refuse(2, dup_key=True)

    def test_refuse_latex_markup_in_name(self):
        self._assert_refuse(2, argv_name="2.3 The Euler totient function $\\varphi(n)$")

    def test_refuse_missing_evidence(self):
        self._assert_refuse(2, evidence="太短")

    def test_refuse_name_without_ordinal(self):
        self._assert_refuse(2, argv_name="The Euler totient function φ(n)")

    def test_refuse_when_unit_heading_is_the_wrong_side(self):
        """契约修过去仍与 H2 不同形 = 单元侧写错，禁把 SSOT 拉歪去迁就。"""
        self._assert_refuse(2, h2="## §2.3 The Euler totient function $\\sigma(n)$")

    def test_refuse_when_manifest_and_contract_disagree(self):
        self._assert_refuse(2, manifest_name="2.3 The Euler totient function q(n)")

    def test_allow_bare_is_accepted(self):
        _mk(self.E)
        self.assertEqual(_run(self.E, name="The Euler totient function φ(n)",
                              extra=["--allow-bare"]), 0)


class SupplementChapterTest(unittest.TestCase):
    """补篇章键（`S`）：旧 `contract_path` 一刀切 `appendix%s.json`、单元目录算成
    `appendixS` → 补篇每个节都报「找不到契约/manifest」而拒绝修名（Katok supplementS
    实测）。路径判据必须按**磁盘物理证据**在 ch/appendix/supplement 三候选里取实际存在者。"""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.E = self._td.name

    def tearDown(self):
        self._td.cleanup()

    def _mk_sup(self, dirs=("supplementS",)):
        bs = os.path.join(self.E, "book_structure")
        tree = {"chapter_key": "S",
                "sub_sec": [{"key": "S.2", "type": "section", "name": "S.2",
                             "page_start": 661, "page_end": 662, "sub_sec": []}]}
        os.makedirs(os.path.join(bs))
        with io.open(os.path.join(bs, "supplementS.json"), "w", encoding="utf-8",
                     newline="\n") as f:
            json.dump(tree, f, ensure_ascii=False, indent=2)
        for side in ("units", "units-translate"):
            for nm in dirs:
                d = os.path.join(bs, side, nm)
                os.makedirs(d)
                with io.open(os.path.join(d, "manifest.json"), "w", encoding="utf-8",
                             newline="\n") as f:
                    json.dump({"chapter_key": "S", "units": [
                        {"id": "0002", "file": "0002_section.md", "type": "section",
                         "key": "S.2", "name": "S.2", "tags": [], "images": [],
                         "content": 3, "hash": "x"}]}, f, ensure_ascii=False, indent=2)
                with io.open(os.path.join(d, "0002_section.md"), "w", encoding="utf-8",
                             newline="\n") as f:
                    f.write("<!-- book-summarizer DONE unit: id=0002 type=section "
                            "key=S.2 name=S.2 -->\n\n## §S.2 Lyapunov exponents\n\nbody\n")

    def test_supplement_section_name_fixed(self):
        self._mk_sup()
        rc = fsn.main([self.E, "S", "S.2", "--name", "S.2 Lyapunov exponents",
                       "--evidence", "印面 p682 节题 'S.2. Lyapunov exponents'（契约只有裸序标）",
                       "--apply"])
        self.assertEqual(rc, 0)
        tree = json.load(io.open(os.path.join(self.E, "book_structure", "supplementS.json"),
                                 encoding="utf-8"))
        self.assertEqual(tree["sub_sec"][0]["name"], "S.2 Lyapunov exponents")
        man = json.load(io.open(os.path.join(self.E, "book_structure", "units",
                                             "supplementS", "manifest.json"),
                                encoding="utf-8"))
        self.assertEqual(man["units"][0]["name"], "S.2 Lyapunov exponents")

    def test_ambiguous_unit_dir_refused(self):
        """同键下 `appendixS/` 与 `supplementS/` 并存 = 章型歧义 → 拒绝，不猜。"""
        self._mk_sup(dirs=("supplementS", "appendixS"))
        rc = fsn.main([self.E, "S", "S.2", "--name", "S.2 Lyapunov exponents",
                       "--evidence", "印面 p682 节题 'S.2. Lyapunov exponents'", "--apply"])
        self.assertEqual(rc, 2)
        tree = json.load(io.open(os.path.join(self.E, "book_structure", "supplementS.json"),
                                 encoding="utf-8"))
        self.assertEqual(tree["sub_sec"][0]["name"], "S.2")


class TrailingSubscriptDigitTest(unittest.TestCase):
    """⑤ 腿的「保尾数」通道（Fraleigh《AFCAA》ch9/9.10 等 6 站实测）。

    印面节题 `9.10 Example: Order of (8, 4, 10) in Z_12 x Z_60 x Z_24`：单元 H2 写 KaTeX
    `$\\mathbb{Z}_{12} \\times \\mathbb{Z}_{60} \\times \\mathbb{Z}_{24}$`（收尾 `$`），
    而本工具硬禁 `--name` 含 `$`/`\\` ⇒ 账目面只能写裸文本 `… Z24`（收尾是数字）。
    `clean_title` 的 `_TRAIL_PAGE` 在**比对之前**运行，把裸文本侧的 `24` 当页码残渣剥掉，
    `$` 侧却因收尾非数字而留住 → 同一印面两侧永不同形，6 个站点全卡在 MISMATCH。

    修法＝**判据的第二通道**（`norm_title(..., keep_trailing_digits=True)` 只在两侧保住
    尾数后逐位相等时判同形），闸 ⑰ 与本工具的⑤腿共用同一条实现；`_TRAIL_PAGE` 本体与
    展示形 `clean_title` 一字节不动，真页码残渣与真错数字仍各自被抓住。
    """

    H2_BB = ("## §2.3 Order of $(8, 4, 10)$ in "
             "$\\mathbb{Z}_{12} \\times \\mathbb{Z}_{60} \\times \\mathbb{Z}_{24}$")
    NAME_BB = "2.3 Order of (8, 4, 10) in Z12 × Z60 × Z24"
    OLD_TRUNC = "2.3 Order of (8, 4, 10) in Z"

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.E = self._td.name
        self.bs = os.path.join(self.E, "book_structure")
        self.u = os.path.join(self.bs, "units", "ch2")

    def tearDown(self):
        self._td.cleanup()

    def _mkbb(self, h2, contract_name, manifest_name=None):
        _mk(self.E, h2=h2, contract_name=contract_name,
            manifest_name=contract_name if manifest_name is None else manifest_name)

    def _ledger(self):
        p = os.path.join(self.E, "_section_name_fixes.jsonl")
        return json.loads(io.open(p, encoding="utf-8").read().strip().split("\n")[-1])

    # ── 正向：黑板粗体下标数字节题修得动，且台账能区分通道 ──────────────
    def test_blackboard_bold_trailing_digit_is_applied(self):
        self._mkbb(self.H2_BB, self.OLD_TRUNC)
        self.assertEqual(_run(self.E, name=self.NAME_BB, apply=True), 0)
        tree = json.load(io.open(os.path.join(self.bs, "ch2.json"), encoding="utf-8"))
        self.assertEqual(tree["sub_sec"][0]["name"], self.NAME_BB)
        self.assertEqual(self._ledger()["heading_check"], "MATCH-DIGIT")

    def test_plain_channel_still_wins_when_h2_has_no_math_shield(self):
        """H2 也写成裸文本（两侧都被 `_TRAIL_PAGE` 剥尾数）→ 常规形先命中，台账记 `MATCH`。

        锁「两条通道的取序」：只有常规形判不出时才允许走保尾数，避免把 `MATCH` 通道
        变成默认，事后审计就分不清哪些站点靠哨兵过关。
        """
        h2 = "## §2.3 Order of (8, 4, 10) in Z12 x Z60 x Z24"
        self._mkbb(h2, self.OLD_TRUNC)
        self.assertEqual(_run(self.E, name="2.3 Order of (8, 4, 10) in Z12 x Z60 x Z24",
                              apply=True), 0)
        self.assertEqual(self._ledger()["heading_check"], "MATCH")

    # ── 控件：把第二通道关掉必须复现现状（= 仍 MISMATCH）───────────────
    def test_channel_off_reproduces_the_old_refusal(self):
        from lib.section_titles import norm_title
        saved = fsn._norm_keep_digits
        unit = os.path.join(self.u, "0008_section_2_3.md")
        _mk(self.E, h2=self.H2_BB, contract_name=self.OLD_TRUNC)
        try:
            fsn._norm_keep_digits = lambda t, k: norm_title(t, k)   # 关掉保尾数
            self.assertEqual(fsn.check_heading(unit, "2.3", self.NAME_BB)[0], "MISMATCH")
        finally:
            fsn._norm_keep_digits = saved
        self.assertEqual(fsn.check_heading(unit, "2.3", self.NAME_BB)[0], "MATCH-DIGIT")

    def test_channel_is_the_same_one_the_gate_uses(self):
        """工具的第二通道必须**就是判据那条**（`norm_title(..., keep_trailing_digits=True)`）。

        各写一份实现 ⇒ 「工具 MATCH-DIGIT 放行、重跑闸仍判红」的分叉（本轮要根治的形态）。
        """
        from lib.section_titles import norm_title
        for t in (self.NAME_BB, self.H2_BB, OLD, self.OLD_TRUNC, "2.3 Group Z 57"):
            self.assertEqual(fsn._norm_keep_digits(t, "2.3"), norm_title(t, "2.3", True))

    # ── 负向：只有「尾部数字」这一类差异能走该通道 ────────────────────
    def _assert_refuse_bb(self, name):
        self._mkbb(self.H2_BB, self.OLD_TRUNC)
        cpath = os.path.join(self.bs, "ch2.json")
        craw = _read(cpath)
        self.assertEqual(_run(self.E, name=name, apply=True), 2)
        self.assertEqual(_read(cpath), craw)
        self.assertFalse(os.path.exists(os.path.join(self.E, "_section_name_fixes.jsonl")))

    def test_refuse_wrong_trailing_digit(self):
        """`Z25` vs 印面 `Z24`：常规形会剥掉两侧尾数后假同形？不会——H2 侧有 `$` 遮蔽，
        保尾数形必须逐位相等，故仍拒。"""
        self._assert_refuse_bb("2.3 Order of (8, 4, 10) in Z12 × Z60 × Z25")

    def test_refuse_wrong_subscript_in_the_middle(self):
        self._assert_refuse_bb("2.3 Order of (8, 4, 10) in Z13 × Z60 × Z24")

    def test_refuse_name_missing_the_subscript_group(self):
        """少一整段（只写到 `Z12`）不是「尾数遮蔽不对称」，不许放行。"""
        self._assert_refuse_bb("2.3 Order of (8, 4, 10) in Z12")

    def test_refuse_name_missing_words(self):
        self._assert_refuse_bb("2.3 Order of (8, 4, 10)")

    # ── 展示形不受影响：新通道只活在比对里 ─────────────────────────────
    def test_display_form_still_strips_trailing_page_digits(self):
        """`clean_title`（manifest/marker/闸门文案读的展示形）默认照剥尾数，
        新参数只服务比对腿；否则 `Phase Flows 57` 这类真残渣会改到展示面。"""
        from lib.section_titles import clean_title
        self.assertEqual(clean_title("2.3 Phase Flows 57", "2.3"), "Phase Flows")
        self.assertEqual(clean_title("2.3 Phase Flows 57", "2.3", keep_trailing_digits=True),
                         "2.3 Phase Flows 57".replace("2.3 ", ""))

    def test_norm_keep_digits_matches_h2_exactly(self):
        self.assertEqual(fsn._norm_keep_digits(self.NAME_BB, "2.3"),
                         fsn._norm_keep_digits(self.H2_BB, "2.3"))


if __name__ == "__main__":
    unittest.main()
