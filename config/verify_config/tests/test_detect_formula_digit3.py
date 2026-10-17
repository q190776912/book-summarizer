# -*- coding: utf-8 -*-
"""test_detect_formula_digit3.py — 三段**数字**公式序标 `(C.S.N)`（formula type 3）。

锁死 2026-10-15 的根治（用户诉求：判据修进 skill 校验链，不许只补一本书）。
实测成因：Lehmann《Elements of Large-Sample Theory》(Springer 1999) 印
`(1.1.5)`…`(7.9.14)` 共 2323 枚右缘编号，而 `make_config.detect_formula` 的数字探针
只有两段核 `F_DOT_RE`（第二个数字段后就要求闭括号）与单段核 `F_SINGLE_RE`
（要 `(N)` 整串）——**两者对三段形态命中均为零**，于是择族落到散文括号年份
`(1979)` 被 `F_SINGLE_RE` 收走的 522 条上，产出 `{"type": 1, "scope": 3}`：
Q 层按单段核对 `(1)`，全书三级序标整体失明（且永不报错，属静默漏检）。

判据（跨 55 书普查 `tools/census_digit3_formula.py` 校准）：

1. **条数闸** `_FORMULA_MIN_COUNT`（30，与单段/两段同级）；
2. **主导权闸**：三段命中必须 > 单段 + 两段 + 字母 + 罗马全部对手，否则不得改写
   选型（实测 `theory-of-point-estimation`：同作者、公式只印两段，1420 条两段 vs
   47 条撞形三段 → 正确地不择）；
3. **形状闸**：与 alpha-3 共用 `_alpha3_confident`（跨桶 + 连续升序），判据只一份；
4. **scope 从书证派生**（无默认值）：同章内跨节重启 → 3；章内跨节连续、章末重启
   → 2；全书连续 → 1。

存量对照：普查里 d3>=30 的 6 本书（chaos-fractals / statistical-inference /
Katok / 概率论与数理统计教程 / 高等代数 / 本书）新判据**逐一复现** type 3，
零回归；唯一被标「存量 3 却择不出」的 `数理逻辑导引 (冯琦)` 在 534 页里**三段
命中为 0**（其 3 是老探针遗留，改动前的探测器同样 emit 不出 3），处置是别再
`--force` 该书，而非放宽阈值。

运行：
  python config/verify_config/tests/test_detect_formula_digit3.py
  python -m pytest config/verify_config/tests/test_detect_formula_digit3.py -q
"""
import os
import sys
import json
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

from lib.regexlib import F_DOT_RE, F_SINGLE_RE, F_DIGIT3_RE   # noqa: E402


def _write_pages(ext, page_blocks):
    """`page_blocks` = 每页一组 text 块字符串（右缘编号块的尾巴必须干净）。"""
    os.makedirs(ext, exist_ok=True)
    for i, blocks in enumerate(page_blocks, start=1):
        with open(os.path.join(ext, "page_%03d.json" % i), "w",
                  encoding="utf-8") as f:
            json.dump({"text": [{"text": t} for t in blocks]}, f,
                      ensure_ascii=False)


def _extract_with():
    d = tempfile.mkdtemp()
    ext = os.path.join(d, "_extract")
    os.makedirs(ext, exist_ok=True)
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
    r = subprocess.run([sys.executable, "-c", code, ext], capture_output=True,
                       text=True, timeout=180, encoding="utf-8",
                       errors="replace")
    assert r.returncode == 0, "detect_formula failed: %s" % r.stderr
    line = [ln for ln in r.stdout.splitlines() if ln.startswith("RESULT:")]
    assert line, "no RESULT in %r" % r.stdout
    return json.loads(line[-1][len("RESULT:"):])


_BARE_DRIVER = """
import sys, json
sys.path.insert(0, %r)
from make_config import detect_bare_number
out = detect_bare_number(sys.argv[1], %s)
print("RESULT:" + json.dumps(out))
"""


def _bks_series(n_total, per_bucket=4):
    """右缘 `(章.节.号)` 序列：**每节从 1 重启**（Lehmann / 高等代数 印面体例）。

    返回 n_total 条文块，跨足够多的 (章, 节) 桶。"""
    out = []
    ch, sec = 1, 1
    for i in range(n_total):
        out.append("and we obtain the bound x <= y (%d.%d.%d)." % (ch, sec,
                                                                  i % per_bucket + 1))
        if (i + 1) % per_bucket == 0:
            sec += 1
            if sec > 3:
                sec = 1
                ch += 1
    return out


def _chapter_restart_series(n_total, per_chapter=12):
    """右缘 `(章.节.号)` 序列：**章内跨节连续**编号、换章才从 1 重启（scope 2 证据）。"""
    out = []
    for i in range(n_total):
        ch = i // per_chapter + 1
        k = i % per_chapter + 1
        sec = 1 if k <= per_chapter // 2 else 2
        out.append("hence (and only hence) (%d.%d.%d)." % (ch, sec, k))
    return out


class ProbeShapes(unittest.TestCase):
    """探针形态：两段/单段核**结构性看不见**三段 = 本次故障的根因。"""

    def test_two_and_single_probe_cannot_see_digit3(self):
        for tok in ("(1.1.5)", "（2.3.14）", "(7.9.14)"):
            self.assertIsNone(F_DOT_RE.search(tok),
                              "%s 若被两段核命中，故障就不存在了" % tok)
            self.assertIsNone(F_SINGLE_RE.search(tok),
                              "%s 若被单段核命中，就不会只靠年份噪声择族了" % tok)

    def test_digit3_probe_matches_both_paren_widths(self):
        self.assertEqual(F_DIGIT3_RE.search("x = y (1.1.5).").groups(),
                         ("1", "1", "5"))
        self.assertEqual(F_DIGIT3_RE.search("故得 （2.3.14）").groups(),
                         ("2", "3", "14"))

    def test_digit3_probe_needs_the_paren_form(self):
        # 裸排 `1.1.5` 与小节标题 / 条目号同形，一律不收（宁缺勿滥）。
        self.assertIsNone(F_DIGIT3_RE.search("2.2.1 符号"))
        # 词内粘连（函数调用 / 下标写法）不收——与 F_DOT_RE 同一负向后顾。
        self.assertIsNone(F_DIGIT3_RE.search("f(1.1.5)"))


class DetectDigitThreeComponent(unittest.TestCase):
    def test_per_section_restart_elects_type_3_scope_3(self):
        _d, ext = _extract_with()
        blocks = _bks_series(40)
        _write_pages(ext, [blocks[i:i + 4] for i in range(0, len(blocks), 4)])
        res = _run_detect(ext)
        self.assertIsNotNone(res, "三级公式书不该探测为空")
        self.assertEqual(res.get("type"), 3, "应选数字三段 type 3：%r" % res)
        self.assertEqual(res.get("scope"), 3,
                         "印面每节从 1 重启 → scope 3：%r" % res)
        self.assertNotIn("letter_ch", res)

    def test_year_paren_noise_cannot_outvote_the_real_series(self):
        # 🔴 本书的故障现场：522 条 `(1979)` 型年份括号 vs 2323 条三段右缘编号。
        _d, ext = _extract_with()
        three = _bks_series(48)
        pages = []
        for i in range(12):
            pages.append(["see Lehmann (%d)." % (1900 + i)] * 3
                         + three[i * 4:(i + 1) * 4])
        _write_pages(ext, pages)
        res = _run_detect(ext)
        self.assertEqual(res.get("type"), 3, "年份括号不得赢过真系列：%r" % res)

    def test_chapter_restart_series_gets_scope_2(self):
        _d, ext = _extract_with()
        blocks = _chapter_restart_series(36)
        _write_pages(ext, [blocks[i:i + 3] for i in range(0, len(blocks), 3)])
        res = _run_detect(ext)
        self.assertEqual(res.get("type"), 3)
        self.assertEqual(res.get("scope"), 2,
                         "章内跨节连续、换章重启必须判 2，不得凭跨节一跳冒充 3：%r"
                         % res)


class DetectDigitThreeComponentDeclines(unittest.TestCase):
    """负向：不足条数 / 被占优 / 非右缘 一律不改写选型。"""

    def test_below_count_floor_declines(self):
        _d, ext = _extract_with()
        blocks = _bks_series(12)          # 形状成套，但条数 < 30
        _write_pages(ext, [blocks[i:i + 3] for i in range(0, len(blocks), 3)])
        self.assertIsNone(_run_detect(ext),
                          "条数不足 30 的三段系列不得凭空立体例（普查阈值）")

    def test_two_component_book_not_stolen_by_collisions(self):
        # theory-of-point-estimation 型：两段右缘编号成规模（占优），三段只是撞形。
        _d, ext = _extract_with()
        dotted = ["x + y = z (%d.%d)." % (c, n) for c in (1, 2, 3)
                  for n in range(1, 21)]
        three = _bks_series(35)
        pages = [(dotted + three)[i:i + 15] for i in range(0, len(dotted) + 35, 15)]
        _write_pages(ext, pages)
        res = _run_detect(ext)
        self.assertIsNotNone(res)
        self.assertEqual(res.get("type"), 2,
                         "两段书必须保持 type 2，不被撞形三段劫持：%r" % res)

    def test_prose_embedded_hits_are_not_counted(self):
        # 尾点纪律：括号后还有内容的一律不是右缘编号。
        _d, ext = _extract_with()
        blocks = ["from (1.1.1) and (1.1.2) we get the bound",
                  "using (1.2.1) together with lemma 2",
                  "cf (2.1.1) below for the construction",
                  "note (2.2.2) says otherwise and (2.2.3) too"]
        _write_pages(ext, [blocks])
        self.assertIsNone(_run_detect(ext))


class DetectBareNumberKnowsThreeComponent(unittest.TestCase):
    """🔴 同一次故障的第二半：`detect_bare_number` 也必须认识三段括号形态。

    它的「显式落点」清单与 `_mask_explicit_forms` 若漏掉 `F_DIGIT3_RE`，则
    `(1.1.5)` **既不算显式、又没被掩掉**——裸核 `_BARE_NUM_RE` 的 `(?<![\\d.])`
    看得见 `(` 后面的 `1.1.5`，于是**每一个括号三段公式号都被当成裸排落点**，
    裸占比恒 ≈1 → `bare_number` 一律误判 true（本书实测 2329 显式 vs 463 裸，
    修复前判 true、修复后按书证判不交）。两处共用 `_EXPLICIT_FORMULA_RES` 一份
    清单，判据不许再各写一份。
    """

    def _run_bare(self, ext, cfg):
        code = _BARE_DRIVER % (os.path.join(_ROOT, "config", "verify_config"),
                               json.dumps(cfg))
        r = subprocess.run([sys.executable, "-c", code, ext],
                           capture_output=True, text=True, timeout=180,
                           encoding="utf-8", errors="replace")
        assert r.returncode == 0, "detect_bare_number failed: %s" % r.stderr
        line = [ln for ln in r.stdout.splitlines() if ln.startswith("RESULT:")]
        assert line, "no RESULT in %r" % r.stdout
        val = line[-1][len("RESULT:"):]
        return None if val == "null" else json.loads(val)

    def test_paren_only_three_component_book_is_not_bare_true(self):
        _d, ext = _extract_with()
        blocks = _bks_series(40)
        pages = [blocks[i:i + 4] for i in range(0, len(blocks), 4)]
        # 少量真裸排（目录小节号形态）——占比 <= 10% 应判 false
        pages.append(["1.4", "1.5"])
        _write_pages(ext, pages)
        res = self._run_bare(ext, {"type": 3, "scope": 3})
        self.assertIsNot(res, True, "纯括号三段书绝不能判 bare_number=true")
        self.assertIs(res, False, "括号主导且裸落点≈0 → false：%r" % res)

    def test_mixed_toc_noise_declines_instead_of_claiming_true(self):
        # 本书的印面实况：目录页有整页裸 `N.M` 小节号（占比落在混叠区）——
        # 探测器必须**判不交**（None，交 agent 依书补定），绝不因把 `(1.1.5)`
        # 误数成裸落点而报 true。
        _d, ext = _extract_with()
        pages = [_bks_series(40)[i:i + 4] for i in range(0, 40, 4)]
        pages += [["1.%d" % n] for n in range(1, 15)]
        _write_pages(ext, pages)
        self.assertIn(self._run_bare(ext, {"type": 3, "scope": 3}),
                      (None, False))


class CensusToolIsSsot(unittest.TestCase):
    """普查台不得自带一份判据副本（否则校准结果与生产探测器会漂移）。"""

    def test_census_imports_the_ssot_regex_and_predicates(self):
        path = os.path.join(_ROOT, "tools", "census_digit3_formula.py")
        src = open(path, encoding="utf-8").read()
        self.assertIn("F_DIGIT3_RE", src)
        self.assertIn("_alpha3_confident", src)
        self.assertIn("_digit3_scope", src)
        self.assertNotIn("_F_DIGIT3 = re.compile", src,
                         "普查工具内不许另立一份三段核")


if __name__ == "__main__":
    unittest.main(verbosity=2)
