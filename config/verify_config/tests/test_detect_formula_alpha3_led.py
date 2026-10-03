# -*- coding: utf-8 -*-
"""test_detect_formula_alpha3_led.py — 三段字母/罗马章位公式序标 `(A.2.1)` / `(II.1.3)`。

锁死 2026-10-03 的根治（用户诉求：附录/补篇的印面公式序标必须被校验，不许 no-op）：

1. **两段探针结构性看不见三段**：`F_LETTER_RE` / `F_ROMAN_RE` 在第一个数字段后就要求
   闭括号，`(A.2.1)` 全零命中 → 该段配置丢 `formula` 键 → Q 层静默 no-op
   （实测 Katok《现代动力系统导论》附录A / 补篇S 共 17 枚印面序标无人校验）。
   新分支必须选 formula-only **type 17 / 18**。
2. **主导权闸**（🔴 最关键的一条负向判据）：三段家族必须在**被扫描的范围里压倒**其余
   各族（single / dotted / 两段字母 / 两段罗马）才当选。实测：同一本书**整书扫描**时
   附录的三段系列 21 命中 vs 正文单段右缘编号 79 命中——若只比两段对手，附录体例
   会**劫持**正文段的选举，把 ch 配置改写成字母三段，19 章的 Q 校验当场作废。
3. **置信形状**（跨 51 书普查校准，`tools/census_alpha3_formula.py`：真成套只有 Katok，
   另有三本各 1–2 条撞形）：条数 >= 5 + 至少 **2 个** (字母章, 节) 桶 + 桶内连续升序
   >= 3（或 >= 2 个桶各含 >= 2 号）。单桶成串、孤立撞形一律拒。
4. **scope 从书中推导**（无默认值）：跨 (字母章, 节) 桶重启 → 3；单调连排 → 1。
5. **增量补齐通道**：`_upgrade_missing_special_keys` 对「子配置已在账、却没有
   `formula` 键」的 appendix / supplement 段，按**该段自己的页区间**补写探测值；
   既有 `formula` **绝不覆盖**，`ch` 段**一律不碰**（整份 --force 会洗掉正文段
   早期/人工确定的体例，本书 ch=type 3 即实测受害者）。

运行：
  python config/verify_config/tests/test_detect_formula_alpha3_led.py
  python -m pytest config/verify_config/tests/test_detect_formula_alpha3_led.py -q
"""
import os
import re
import sys
import json
import glob
import tempfile
import subprocess
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

from lib.regexlib import F_LETTER_RE, F_ROMAN_RE              # noqa: E402
from lib.regexlib import F_LETTER3_RE, F_ROMAN3_RE            # noqa: E402
from lib.numbering import (                                   # noqa: E402
    resolve_formula_type, formula_num_core,
    FORMULA_LEAD_LETTER, FORMULA_LEAD_ROMAN,
    FORMULA_TYPE_LETTER_THREE, FORMULA_TYPE_ROMAN_THREE,
)

# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


def _write_pages(ext, page_blocks):
    """`page_blocks` = 每页一组 text 块字符串（右缘编号块的尾巴必须干净）。"""
    os.makedirs(ext, exist_ok=True)
    for i, blocks in enumerate(page_blocks, start=1):
        with open(os.path.join(ext, "page_%03d.json" % i), "w",
                  encoding="utf-8") as f:
            json.dump({"text": [{"text": t} for t in blocks]}, f,
                      ensure_ascii=False)


def _extract_with(done_marker=True):
    d = tempfile.mkdtemp()
    ext = os.path.join(d, "_extract")
    os.makedirs(ext, exist_ok=True)
    if done_marker:
        with open(os.path.join(ext, "_extraction_done.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"done": True}, f)
    return d, ext


_DRIVER = """
import sys, json
sys.path.insert(0, %r)
from make_config import detect_formula
out = detect_formula(sys.argv[1], pages=%r)
print("RESULT:" + json.dumps(out))
"""


def _run_detect(ext, pages=None):
    code = _DRIVER % (os.path.join(_ROOT, "config", "verify_config"), pages)
    argv = [sys.executable, "-c", code, ext]
    r = subprocess.run(argv, capture_output=True, text=True, timeout=180,
                       encoding="utf-8", errors="replace")
    assert r.returncode == 0, "detect_formula failed: %s" % r.stderr
    line = [ln for ln in r.stdout.splitlines() if ln.startswith("RESULT:")]
    assert line, "no RESULT in %r" % r.stdout
    return json.loads(line[-1][len("RESULT:"):])


_UPGRADE_DRIVER = """
import sys, json
sys.path.insert(0, %r)
from make_config import _upgrade_missing_special_keys
rc = _upgrade_missing_special_keys(sys.argv[1], sys.argv[2])
print("RC:" + str(rc))
"""


def _run_upgrade(ext, cfg_path):
    code = _UPGRADE_DRIVER % os.path.join(_ROOT, "config", "verify_config")
    r = subprocess.run([sys.executable, "-c", code, ext, cfg_path],
                       capture_output=True, text=True, timeout=180,
                       encoding="utf-8", errors="replace")
    assert r.returncode == 0, "upgrade failed: %s" % r.stderr
    return json.load(open(cfg_path, encoding="utf-8"))


# Katok 附录A 印面实样（p733–749）：每节从 1 重启
APPENDIX_A = ["We have (A.2.1).",
              "It follows that (A.3.1).", "Moreover (A.3.2).",
              "Combining them gives (A.3.3).", "Finally (A.4.1)."]
# Katok 补篇S 印面实样（p682–702）
SUPPLEMENT_S = ["Set (S.2.1).", "Then (S.2.2).", "Hence (S.2.3).",
                "Also (S.2.4).", "Further (S.2.5).", "Next (S.2.6).",
                "Again (S.3.1).", "Thus (S.3.2).", "So (S.3.3)."]


class ProbeShapes(unittest.TestCase):
    """探针本身的形态（两段探针看不见三段 = 本次故障的根因）。"""

    def test_two_component_probe_cannot_see_three(self):
        for tok in ("(A.2.1)", "（S.3.4）", "(II.1.3)"):
            self.assertIsNone(F_LETTER_RE.search(tok),
                              "%s 若被两段字母探针命中，故障就不存在了" % tok)
            self.assertIsNone(F_ROMAN_RE.search(tok))

    def test_three_component_probe_matches_both_widths(self):
        m = F_LETTER3_RE.search("x = y (A.2.1).")
        self.assertEqual(m.groups(), ("A", "2", "1"))
        m = F_LETTER3_RE.search("故得 （S.3.4）")
        self.assertEqual(m.groups(), ("S", "3", "4"))

    def test_letter3_head_is_single_letter_so_roman_head_is_disjoint(self):
        self.assertIsNone(F_LETTER3_RE.search("(II.1.3)"),
                          "letter 三段核必须拒罗马多字母头")
        self.assertIsNotNone(F_ROMAN3_RE.search("(II.1.3)"))
        self.assertIsNone(F_ROMAN3_RE.search("(A.2.1)"),
                          "roman 三段核必须拒非罗马字母头 A")

    def test_mid_numbering_needs_no_paren_close_after_first_segment(self):
        # 裸排 A.2.1（小节标题 / 条目号同形）一律不收——探针只认括号形态。
        self.assertIsNone(F_LETTER3_RE.search("A.2.6. Prove the inequality"))


class TypeResolution(unittest.TestCase):
    def test_new_codes_resolve_to_three_component_shapes(self):
        self.assertEqual(resolve_formula_type(FORMULA_TYPE_LETTER_THREE),
                         (FORMULA_LEAD_LETTER, 3))
        self.assertEqual(resolve_formula_type(FORMULA_TYPE_ROMAN_THREE),
                         (FORMULA_LEAD_ROMAN, 3))

    def test_letter_core_has_exactly_two_numeric_segments(self):
        core = formula_num_core(3, lead=FORMULA_LEAD_LETTER)
        rx = re.compile("^" + core + "$")
        self.assertTrue(rx.match("A.2.1"))
        self.assertFalse(rx.match("A.3"), "三段核不得收两段 token")
        self.assertFalse(rx.match("A.2.3.4"))


class DetectThreeComponent(unittest.TestCase):
    def test_letter3_appendix_elected_type_17(self):
        _d, ext = _extract_with()
        _write_pages(ext, [APPENDIX_A[:2], APPENDIX_A[2:4], APPENDIX_A[4:]])
        res = _run_detect(ext)
        self.assertIsNotNone(res, "三段字母章位不该再探测为空")
        self.assertEqual(res.get("type"), 17, "应选 formula-only 三段字母码：%r" % res)
        self.assertEqual(res.get("scope"), 3,
                         "印面每节从 1 重启 → scope 3：%r" % res)
        self.assertNotIn("letter_ch", res)

    def test_letter3_supplement_series_elected_type_17(self):
        _d, ext = _extract_with()
        _write_pages(ext, [SUPPLEMENT_S[:3], SUPPLEMENT_S[3:6], SUPPLEMENT_S[6:]])
        res = _run_detect(ext)
        self.assertEqual(res.get("type"), 17)
        self.assertEqual(res.get("scope"), 3)

    def test_roman3_elected_type_18(self):
        _d, ext = _extract_with()
        blocks = ["Eq (II.1.1).", "Eq (II.1.2).", "Eq (II.1.3).",
                  "Eq (II.2.1).", "Eq (II.2.2).", "Eq (III.1.1)."]
        _write_pages(ext, [blocks[:2], blocks[2:4], blocks[4:]])
        res = _run_detect(ext)
        self.assertEqual(res.get("type"), 18, "三段罗马须选 18：%r" % res)
        self.assertEqual(res.get("scope"), 3)

    def test_monotonic_series_gets_scope_1(self):
        _d, ext = _extract_with()
        # 跨桶但**不重启**（B.1 排到 3、B.2 接着 4…）→ scope 1（全书连续）。
        blocks = ["(B.1.1).", "(B.1.2).", "(B.1.3).",
                  "(B.2.4).", "(B.2.5).", "(B.3.6)."]
        _write_pages(ext, [blocks[:2], blocks[2:4], blocks[4:]])
        res = _run_detect(ext)
        self.assertEqual(res.get("type"), 17)
        self.assertEqual(res.get("scope"), 1,
                         "无重启证据时不得凭空赋 scope 3：%r" % res)


class DetectThreeComponentDeclines(unittest.TestCase):
    """负向：撞形 / 稀疏 / 被主导 一律不选体例（宁缺勿滥）。"""

    def test_isolated_collisions_rejected(self):
        # 跨书普查实测形态：`an-introduction-to-homological-algebra` 1 条、
        # `methods-of-homological-algebra` 2 条——都是散文撞形，绝不成体例。
        _d, ext = _extract_with()
        _write_pages(ext, [["The complex (V.5.4) above.", "See (V.5.5)."]])
        self.assertIsNone(_run_detect(ext))

    def test_single_bucket_run_rejected(self):
        # 只有一个 (字母章, 节) 桶：桶内成串也不能证明「跨节重启」的三段体例，
        # 它同样可能是图版子号 a.1.1/a.1.2。
        _d, ext = _extract_with()
        _write_pages(ext, [["(A.3.1)."], ["(A.3.2)."], ["(A.3.3)."],
                           ["(A.3.4)."], ["(A.3.5)."]])
        self.assertIsNone(_run_detect(ext))

    def test_prose_embedded_hits_not_counted(self):
        # 尾点纪律：括号后还有内容的一律不是右缘编号。
        _d, ext = _extract_with()
        blocks = ["from (A.2.1) and (A.3.1) we get the bound",
                  "using (A.4.1) together with lemma 2",
                  "cf (S.2.1) below for the construction",
                  "note (S.3.2) says otherwise",
                  "compare (A.5.1) with (A.5.2) here"]
        _write_pages(ext, [blocks])
        self.assertIsNone(_run_detect(ext))

    def test_digit_book_not_hijacked_by_its_own_appendix(self):
        # 🔴 主导权闸的负向测试（整书扫描口径）：正文单段右缘编号 60 条 +
        # 附录三段 6 条 → 必须仍是单段选举（type 1），附录体例不得劫持正文段。
        _d, ext = _extract_with()
        singles = ["x + y = z (%d)." % n for n in range(1, 31)]
        singles += ["a b = c (%d)." % n for n in range(1, 31)]
        pages = [singles[:6], APPENDIX_A[:2] + singles[6:12],
                 APPENDIX_A[2:4] + singles[12:18],
                 APPENDIX_A[4:] + singles[18:24],
                 singles[24:30], singles[30:36], singles[36:42],
                 singles[42:48], singles[48:54], singles[54:60]]
        _write_pages(ext, pages)
        res = _run_detect(ext)
        self.assertIsNotNone(res)
        self.assertNotEqual(res.get("type"), 17,
                            "附录三段系列劫持了整书（正文段）选举：%r" % res)

    def test_two_component_letter_book_not_stolen(self):
        # 两段字母附录（Lee ISM 式 `(B.12)`）保持原选举，不被三段分支夺走。
        _d, ext = _extract_with()
        blocks = ["Formula (A.%d)." % n for n in range(1, 9)]
        blocks += ["More (B.%d)." % n for n in range(1, 9)]
        _write_pages(ext, [blocks[:8], blocks[8:]])
        res = _run_detect(ext)
        self.assertEqual(res.get("type"), 2, "两段字母书须保持 type 2：%r" % res)
        self.assertTrue(res.get("letter_ch"))


class BackfillMissingFormulaKey(unittest.TestCase):
    """`_upgrade_missing_special_keys` 的增量补齐：只补 formula，不动别的段。"""

    def _fixture(self, with_tags=True, existing_formula=None):
        _d, ext = _extract_with()
        # 页 1–2 = 正文（无编号），页 3–5 = 附录A 页窗
        blocks = [["Body text without labels."], ["More body text."]]
        if with_tags:
            blocks += [APPENDIX_A[:2], APPENDIX_A[2:4], APPENDIX_A[4:]]
        else:
            blocks += [["plain"], ["plain"], ["plain"]]
        _write_pages(ext, blocks)
        with open(os.path.join(ext, "chapter_map.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"chapters": [
                {"kind": 1, "num": 1, "name": "Body", "start": 1, "end": 2},
                {"kind": 2, "num": "A", "name": "Background Material (Appendix A)",
                 "start": 3, "end": 5}]}, f, ensure_ascii=False)
        appendix_seg = {"ordinal": [{"type": 13, "name": ["Theorem"], "scope": 3}],
                        "language": "en", "strict": True}
        if existing_formula is not None:
            appendix_seg["formula"] = existing_formula
        cfg = {"ch": {"ordinal": [{"type": 3, "name": ["Theorem"], "scope": 3}],
                      "language": "en", "strict": True,
                      "formula": {"type": 3, "scope": 3, "bare_number": True,
                                  "ignore": []},
                      "_provenance": {"generated_by": "make_config.py"}},
               "appendix": appendix_seg,
               "supplement": {"ordinal": [{"type": 13, "name": ["Theorem"],
                                           "scope": 3}], "language": "en"}}
        cfg_path = os.path.join(ext, "verify_config.json")
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False)
        return ext, cfg_path, cfg

    def test_formula_key_backfilled_and_everything_else_untouched(self):
        ext, cfg_path, before = self._fixture()
        after = _run_upgrade(ext, cfg_path)
        self.assertEqual(after["ch"], before["ch"], "ch 段必须逐字不动")
        self.assertEqual(after["appendix"]["ordinal"],
                         before["appendix"]["ordinal"])
        f = after["appendix"].get("formula")
        self.assertIsNotNone(f, "附录段应补上探测到的 formula 键")
        self.assertEqual(f.get("type"), 17)
        self.assertEqual(f.get("scope"), 3)
        self.assertIsInstance(f.get("bare_number"), bool,
                              "带 type 的 formula 必须显式带 bare_number（加载闸）")

    def test_existing_formula_never_overwritten(self):
        kept = {"type": 15, "scope": 2, "bare_number": False,
                "ignore": ["A.9"]}
        ext, cfg_path, _b = self._fixture(existing_formula=kept)
        after = _run_upgrade(ext, cfg_path)
        self.assertEqual(after["appendix"]["formula"], kept,
                         "已登记的 formula（含 ignore 账本）绝不被增量升级改写")

    def test_declines_when_window_has_no_evidence(self):
        ext, cfg_path, before = self._fixture(with_tags=False)
        after = _run_upgrade(ext, cfg_path)
        self.assertNotIn("formula", after["appendix"],
                         "探测不出体例时宁可不写（宁缺勿滥）")
        self.assertEqual(after["ch"], before["ch"])

    def test_supplement_segment_backfilled_too(self):
        ext, cfg_path, _b = self._fixture()
        # 追加补篇S 页窗（页 6–8）
        for i, blocks in enumerate([SUPPLEMENT_S[:3], SUPPLEMENT_S[3:6],
                                    SUPPLEMENT_S[6:]], start=6):
            with open(os.path.join(ext, "page_%03d.json" % i), "w",
                      encoding="utf-8") as f:
                json.dump({"text": [{"text": t} for t in blocks]}, f,
                          ensure_ascii=False)
        cm = json.load(open(os.path.join(ext, "chapter_map.json"),
                            encoding="utf-8"))
        cm["chapters"].append({"kind": 3, "num": "S",
                               "name": "Dynamical Systems (Supplement)",
                               "start": 6, "end": 8})
        with open(os.path.join(ext, "chapter_map.json"), "w",
                  encoding="utf-8") as f:
            json.dump(cm, f, ensure_ascii=False)
        after = _run_upgrade(ext, cfg_path)
        f = (after.get("supplement") or {}).get("formula")
        self.assertIsNotNone(f, "补篇段同样应补写：%r" % after.get("supplement"))
        self.assertEqual(f.get("type"), 17)


if __name__ == "__main__":
    unittest.main(verbosity=2)
