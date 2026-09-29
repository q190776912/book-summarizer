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


def _mk(extract, h2=H2, contract_name=OLD, manifest_name=OLD, dup_key=False):
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
    with io.open(os.path.join(bs, "ch2.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(tree, f, ensure_ascii=False, indent=2)
    man = {"chapter_key": "2", "language": "en", "units": [
        {"id": "0008", "file": "0008_section_2_3.md", "type": "section", "ntype": "section",
         "key": "2.3", "name": manifest_name, "tags": [], "images": [], "content": 5,
         "hash": "deadbeef"}]}
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


if __name__ == "__main__":
    unittest.main()
