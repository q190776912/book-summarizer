# -*- coding: utf-8 -*-
"""`make_config.py --set-formula` = 人工具名登记**某段 formula 体例**的唯一正规写入口。

成因（2026-10-29 数学分析 appendixA 实测）：`detect_formula` 的单段择族要过**全书**
下限 `_FORMULA_MIN_COUNT = 30` 枚右缘 `(N)`（这条保守判据是对的——Silverman 型书
正文里有 ~90 枚散文括号编号、真公式号 0 枚），而 appendix/supplement 段只扫**自己
那一段的页窗**：本书附录 A 印面右缘共 23 枚公式号，20 页 ⇒ 恒不过闸 ⇒
`appendix.formula` 谁都补不上（`_backfill_missing_formula_cfg` 探测 None 就什么都不
写，Q 层对整个附录永久 no-op + WARN）。
把 30 按窗口缩小**不安全**：中文书的小问标号 `(1)(2)(3)(4)(5)` 在同一页窗里同样是
右缘裸号，降闸等于给整类书自动造出一套并不存在的编号体例。所以本通道**不放宽任何
判据**，只把人已从印面读出的结论按纪律落账。

正向：只往「该段没有 `formula` 键」里写；写后该段其余键（ordinal/strict/…）与
`ch` 段逐字节不变；`formula_audit` 记证据与页窗；备份落在 `_bak_make_config/`。
负向（一律 rc=2 且零写入）：①`--evidence` 缺失/过短 ②该段已有 `formula`
③段不存在 ④体例码未登记 ⑤`scope` 非 1/2/3 ⑥缺 `_extraction_done.json`
⑦`bare_number` 探测不出又没具名给（无默认值：工具绝不代拟）。

Runs under stdlib unittest:
  python config/verify_config/tests/test_set_formula_channel.py
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

CLI = os.path.join(_ROOT, "config/verify_config/make_config.py")
EV = "fitz 170dpi 渲染上册 p456-475：附录 A 公式号是右缘裸 (N)，逐 A.N 小节从 (1) 重启"


def _mk_ext(n_pages=20, n_tags=23, with_done=True, appendix_seg=True,
            appendix_formula=False):
    """一份「附录段存在但缺 formula」的最小可复现 `_extract`。"""
    ext = os.path.join(tempfile.mkdtemp(prefix="sf_"), "_extract")
    os.makedirs(ext, exist_ok=True)
    with open(os.path.join(ext, "chapter_map.json"), "w", encoding="utf-8") as f:
        json.dump({"chapters": [
            {"kind": 1, "num": 2, "name": "Ch2", "start": 1, "end": 20},
            {"kind": 2, "num": "A", "name": "Appendix A", "start": 21,
             "end": 20 + n_pages}]}, f)
    # 附录页窗里放 n_tags 枚右缘裸号（低于全书 30 下限 ⇒ 探测层必然择不出）
    per = max(1, n_tags // n_pages)
    placed = 0
    for i in range(1, n_pages + 1):
        num = i if placed < n_tags else None
        blocks = [{"text": "f(x) = x + 1", "poly": [0, 40, 200, 52]}]
        if placed < n_tags:
            for k in range(min(per, n_tags - placed)):
                blocks.append({"text": "(%d)" % (k + 1), "poly": [700, 40, 720, 52]})
            placed += min(per, n_tags - placed)
        with open(os.path.join(ext, "page_%03d.json" % (20 + i)), "w",
                  encoding="utf-8") as f:
            json.dump({"text": blocks}, f)
    for i in range(1, 21):   # 正文页（不参与本段扫描）
        with open(os.path.join(ext, "page_%03d.json" % i), "w", encoding="utf-8") as f:
            json.dump({"text": [{"text": "g(x) = x", "poly": [0, 40, 200, 52]}]}, f)
    if with_done:
        with open(os.path.join(ext, "_extraction_done.json"), "w", encoding="utf-8") as f:
            json.dump({"done": True}, f)
    apx = {"ordinal": [{"type": 13, "name": ["定义"], "scope": 3}],
           "strict": True, "language": "cn", "_provenance":
               {"generated_by": "make_config.py"}}
    if appendix_formula:
        apx["formula"] = {"type": 1, "scope": 3, "ignore": [], "bare_number": True}
    cfg = {"ch": {"ordinal": [{"type": 1, "name": ["定义"], "scope": 3}],
                  "strict": True, "language": "cn",
                  "formula": {"type": 1, "scope": 3, "ignore": [],
                              "bare_number": True, "known_book": ["1", "2"]},
                  "_provenance": {"generated_by": "make_config.py"}}}
    if appendix_seg:
        cfg["appendix"] = apx
    with open(os.path.join(ext, "verify_config.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return ext


def _load(ext):
    with open(os.path.join(ext, "verify_config.json"), encoding="utf-8") as f:
        return json.load(f)


def _call(ext, **kw):
    """直调 CLI 参数面（覆盖 argparse 装配与 main 的分流）。"""
    argv = [ext]
    if kw.get("section", True) is not None:
        argv += ["--set-formula", kw.get("section", "appendix")]
    for flag, key in (("formula-type", "ftype"), ("formula-scope", "fscope"),
                      ("formula-bare-number", "bare"), ("evidence", "evidence")):
        if key in kw and kw[key] is not None:
            argv += ["--" + flag, str(kw[key])]
    return MC._cli_set_formula(argv)


class SetFormulaChannelTest(unittest.TestCase):
    def setUp(self):
        self._tmp = []

    def tearDown(self):
        for d in self._tmp:
            shutil.rmtree(d, ignore_errors=True)

    def _ext(self, **kw):
        e = _mk_ext(**kw)
        self._tmp.append(Path(e).parent)
        return e

    # ── 正向 ────────────────────────────────────────────────────────────
    def test_lands_only_the_missing_formula_key(self):
        ext = self._ext()
        before = _load(ext)
        rc = _call(ext, ftype=1, fscope=3, bare="true", evidence=EV)
        self.assertEqual(rc, 0)
        after = _load(ext)
        self.assertEqual(after["ch"], before["ch"])                 # 正文段逐字节不动
        self.assertEqual(after["appendix"]["ordinal"], before["appendix"]["ordinal"])
        self.assertEqual(after["appendix"]["strict"], True)
        f = after["appendix"]["formula"]
        self.assertEqual((f["type"], f["scope"], f["bare_number"]), (1, 3, True))
        self.assertEqual(f["ignore"], [])
        self.assertEqual(f["formula_audit"]["evidence"], EV)
        self.assertEqual(f["formula_audit"]["set_by"], "make_config.py --set-formula")
        self.assertEqual(f["formula_audit"]["scan_pages"], 20)

    def test_backup_is_written(self):
        ext = self._ext()
        raw = open(os.path.join(ext, "verify_config.json"), "rb").read()
        self.assertEqual(_call(ext, ftype=1, fscope=3, bare="true", evidence=EV), 0)
        bak_root = os.path.join(ext, "_bak_make_config")
        snaps = [os.path.join(bak_root, d, "verify_config.json")
                 for d in os.listdir(bak_root)]
        self.assertEqual(len(snaps), 1)
        self.assertEqual(open(snaps[0], "rb").read(), raw)          # 改前原样

    def test_main_routes_the_flag(self):
        """`main()` 的分流：带 `--set-formula` 走登记通道，**不**跑通用增量升级。"""
        ext = self._ext()
        rc = MC.main([ext, "--set-formula", "appendix", "--formula-type", "1",
                      "--formula-scope", "3", "--formula-bare-number", "true",
                      "--evidence", EV])
        self.assertEqual(rc, 0)
        self.assertEqual(_load(ext)["appendix"]["formula"]["type"], 1)

    def test_bare_number_probe_is_used_when_not_named(self):
        ext = self._ext()
        rc = _call(ext, ftype=1, fscope=3, evidence=EV)
        if rc == 0:     # 页窗证据够 ⇒ 用探测值；不够则走下面的拒绝测
            self.assertIn("bare_number", _load(ext)["appendix"]["formula"])
        else:
            self.assertEqual(rc, 2)
            self.assertNotIn("formula", _load(ext)["appendix"])

    # ── 负向：拒绝且零写入 ──────────────────────────────────────────────
    def _assert_refused(self, ext, **kw):
        before = open(os.path.join(ext, "verify_config.json"), "rb").read()
        rc = _call(ext, **kw)
        self.assertEqual(rc, 2, kw)
        self.assertEqual(open(os.path.join(ext, "verify_config.json"), "rb").read(),
                         before)
        self.assertFalse(os.path.isdir(os.path.join(ext, "_bak_make_config")))
        return rc

    def test_refuse_without_evidence(self):
        self._assert_refused(self._ext(), ftype=1, fscope=3, bare="true", evidence="")

    def test_refuse_short_evidence(self):
        self._assert_refused(self._ext(), ftype=1, fscope=3, bare="true",
                             evidence="印面有 (1)")

    def test_refuse_when_segment_already_has_formula(self):
        """已选举过的段一律不碰：改判是另一个决定，且 `--force` 会洗人工账。"""
        self._assert_refused(self._ext(appendix_formula=True), ftype=1, fscope=3,
                             bare="true", evidence=EV)

    def test_refuse_unknown_section(self):
        """该书没有 supplement 段 ⇒ 不代造整段配置。"""
        self._assert_refused(self._ext(), section="supplement", ftype=1, fscope=3,
                             bare="true", evidence=EV)

    def test_refuse_unregistered_type_code(self):
        self._assert_refused(self._ext(), ftype=99, fscope=3, bare="true",
                             evidence=EV)

    def test_refuse_type_zero_depth(self):
        """type 0 = 无编号体例，不该开 Q 层。"""
        self._assert_refused(self._ext(), ftype=0, fscope=3, bare="true", evidence=EV)

    def test_refuse_bad_scope(self):
        for bad in ("7", "x"):
            self._assert_refused(self._ext(), ftype=1, fscope=bad, bare="true",
                                 evidence=EV)

    def test_scope_is_required(self):
        """无默认值纪律：不写 scope 连参数面都不过（argparse 退出码 2）。"""
        ext = self._ext()
        before = open(os.path.join(ext, "verify_config.json"), "rb").read()
        with self.assertRaises(SystemExit) as cm:
            _call(ext, ftype=1, bare="true", evidence=EV)
        self.assertEqual(cm.exception.code, 2)
        self.assertEqual(open(os.path.join(ext, "verify_config.json"), "rb").read(),
                         before)

    def test_refuse_without_extraction_done(self):
        """MM Repair 未完 ⇒ 页窗文字层不可信，不得登记体例（与生成期同一硬闸）。"""
        self._assert_refused(self._ext(with_done=False), ftype=1, fscope=3,
                             bare="true", evidence=EV)

    def test_refuse_when_bare_number_undecided(self):
        """探测不出 bare_number 且没具名给 ⇒ 拒绝（绝不代拟默认值）。"""
        ext = self._ext()
        real = MC.detect_bare_number
        MC.detect_bare_number = lambda *a, **k: None
        try:
            self._assert_refused(ext, ftype=1, fscope=3, evidence=EV)
        finally:
            MC.detect_bare_number = real

    def test_letter_two_component_code_accepted(self):
        """formula-only 码 15（字母两段 `(A.3)`）合法：附录体例并非只有裸单号一种。"""
        ext = self._ext()
        self.assertEqual(_call(ext, ftype=15, fscope=2, bare="true", evidence=EV), 0)
        self.assertEqual(_load(ext)["appendix"]["formula"]["type"], 15)

    def test_detection_path_unchanged_by_the_channel(self):
        """回归闸：页窗低于全书下限时，**自动**探测仍旧什么都不写（本通道没顺手放宽判据）。"""
        ext = self._ext()
        pages = MC._special_page_files(
            ext, MC._detect_special_chapters(ext, MC.KIND_APPENDIX))
        self.assertTrue(pages, "附录页窗应能按章解析到 20 页")
        self.assertIsNone(MC.detect_formula(ext, pages=pages))
        self.assertNotIn("formula", _load(ext)["appendix"])


class SetFormulaCliProcessTest(unittest.TestCase):
    """子进程跑一遍真 CLI（`python make_config.py … --set-formula …` 的 exit code）。"""

    def setUp(self):
        self.ext = _mk_ext()
        self.addCleanup(shutil.rmtree, Path(self.ext).parent, ignore_errors=True)

    def _run(self, *args):
        return subprocess.run([sys.executable, CLI, self.ext] + list(args),
                              cwd=_ROOT, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=300,
                              encoding="utf-8", errors="replace")

    def test_subprocess_apply_and_refuse(self):
        r = self._run("--set-formula", "appendix", "--formula-type", "1",
                      "--formula-scope", "3", "--formula-bare-number", "true",
                      "--evidence", EV)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("APPLIED", r.stdout)
        r2 = self._run("--set-formula", "appendix", "--formula-type", "1",
                       "--formula-scope", "3", "--formula-bare-number", "true",
                       "--evidence", EV)
        self.assertEqual(r2.returncode, 2, r2.stdout)     # 第二次=改已有段 ⇒ 拒绝
        self.assertIn("REFUSED", r2.stdout)


if __name__ == "__main__":
    unittest.main()
