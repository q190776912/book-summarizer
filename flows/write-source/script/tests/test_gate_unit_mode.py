# -*- coding: utf-8 -*-
"""Regression: `gate_units --unit <file>` 逐单元自检必须与章门控**同一套装配**。

写手逐个改单元时只能自检，不能拿整章门控当入口（同事的 DRAFT 单元会被一并报出，
噪音大且慢）。此前自检入口是外部脚本 `tools/_selfcheck_unit.py`，它另起一次
`check_body` 调用——少传一个参数就是一片假绿。实测 Lehmann ch1：该脚本不传
``ext_dir``/``ch`` ⇒ 第 19 项「顶层散文照抄」整个缺席，写手据此翻 DONE，章门控
再把**同一单元**打回（0013 / 0026 / 0035 三例），平白多一轮返工。

根治方式 = 自检入口由门控自己提供（``gate_chapter(..., only_unit=file)``），
复用主循环里同一个 `check_body` 调用点，只跳过与别的单元有关的章级闸。锁死：

1. 照抄源书散文的 DONE 单元：**整章门控报 → 逐单元自检也报**（装配等价，判据本体）。
   照抄闸的源语言真值取自 `page_*.json`（`_source_ngrams`），故夹具必须铺
   chapter_map + page_001，否则重合率恒 0、闸门退化成只拦硬顶长度 = 假夹具；
2. 逐单元自检**只报该单元**，不把同章另一个 DRAFT 单元的问题算进来（无噪音）；
3. 全绿的单元自检 PASS，且首行仍为 DRAFT 的单元自检 FAIL（标记判据不因自检模式放宽）；
4. `--unit` 给了不在 manifest 里的文件名 → FAIL 并说明「不在 manifest」，绝不静默通过；
5. `--unit` 需要恰好一个章键（多章键时无法归属，exit 2）。
"""
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
else:
    _ROOT = str(Path(__file__).resolve().parents[3])
for _p in (_ROOT, os.path.join(_ROOT, "lib"),
           os.path.join(_ROOT, "flows", "write-source", "script")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

import gate_units  # noqa: E402
from verbose_gates import VERBOSE_OVERLAP_MIN, VERBOSE_PARA_CHARS  # noqa: E402

# 原书散文 = 照抄闸的源语言真值（写进 page_001.json）。必须长过散文闸的
# 长度门槛，否则夹具「什么都没测」还全绿。
SOURCE_PROSE = (
    "The present section illustrates a central aspect of large-sample theory, "
    "namely the behavior of sequences of random variables and of the statistics "
    "constructed from them when the sample size becomes large. It shows how the "
    "various modes of convergence differ in strength and in the conclusions that "
    "they are able to support, and explains why the choice of a particular mode "
    "is dictated by the use which the result is to be put to rather than by any "
    "question of mathematical convenience or elegance on the part of the author."
)
# 同一内容的改写（Tier 2 要求）→ 低重合率，自检必须放行
REWRITE = (
    "This section contrasts the modes of convergence. Each supports a different "
    "conclusion, and which one to use follows from the intended application."
)
FLAG = "整段照抄"


def _marker(mark, uid, key, name):
    return ("<!-- book-summarizer %s unit: id=%s type=desc key=%s name=%s -->"
            % (mark, uid, key, name))


class Base(unittest.TestCase):
    def setUp(self):
        assert len(SOURCE_PROSE) > VERBOSE_PARA_CHARS, "夹具散文短于闸门长度门槛"
        self.ext = tempfile.mkdtemp(prefix="bks_only_unit_")
        # 源语言真值：chapter_map（章页窗）+ page_001（正文块）
        with open(os.path.join(self.ext, "chapter_map.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"chapters": [{"kind": 1, "num": 1, "name": "One",
                                     "start": 1, "end": 2},
                                    {"kind": 1, "num": 2, "name": "Two",
                                     "start": 3, "end": 4}]}, f)
        with open(os.path.join(self.ext, "page_001.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"page": 1, "text": [{"text": SOURCE_PROSE,
                                            "poly": [0, 0, 100, 0, 100, 20, 0, 20]}]},
                      f, ensure_ascii=False)
        bs = os.path.join(self.ext, "book_structure")
        os.makedirs(bs)
        # 契约：两个 desc 节点各带一个 text 块（内容块计数 + src_map）
        nodes = [{"key": k, "type": "description", "name": "§1.1 %s" % k,
                  "page_start": 1, "sub_sec": [{"text": p}]}
                 for k, p in (("D1", SOURCE_PROSE), ("D2", REWRITE))]
        with open(os.path.join(bs, "ch1.json"), "w", encoding="utf-8") as f:
            json.dump({"key": "1", "type": "chapter", "name": "One",
                       "sub_sec": [], "items": nodes}, f, ensure_ascii=False)
        # 第二个章契约：`--unit` 的「恰好一个章键」护栏按**契约**列章
        # （`list_chapter_keys`），只有一章时护栏永远不触发 = 假测试。
        with open(os.path.join(bs, "ch2.json"), "w", encoding="utf-8") as f:
            json.dump({"key": "2", "type": "chapter", "name": "Two",
                       "sub_sec": [], "items": []}, f, ensure_ascii=False)
        d = os.path.join(bs, "units", "ch1")
        os.makedirs(d)
        self.units_dir = d
        self.manifest = {
            "language": "en",
            "units": [
                {"id": "0001", "type": "desc", "key": "D1", "ntype": "description",
                 "name": "§1.1 D1", "file": "0001_desc_D1.md",
                 "tags": [], "images": [], "content": 1},
                {"id": "0002", "type": "desc", "key": "D2", "ntype": "description",
                 "name": "§1.1 D2", "file": "0002_desc_D2.md",
                 "tags": [], "images": [], "content": 1},
            ],
        }
        with open(os.path.join(d, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(self.manifest, f, ensure_ascii=False)
        # 0001：DONE，正文逐字照抄原书 → 章门控与自检都必须报
        self._write("0001_desc_D1.md", _marker("DONE", "0001", "D1", "§1.1 D1"),
                    SOURCE_PROSE)
        # 0002：DRAFT（已改写的正文）→ 章门控报「仍未处理」，自检模式不该跟着报它
        self._write("0002_desc_D2.md", _marker("DRAFT", "0002", "D2", "§1.1 D2"),
                    REWRITE)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.ext, ignore_errors=True)

    def _write(self, fname, marker, prose):
        with open(os.path.join(self.units_dir, fname), "w", encoding="utf-8") as f:
            f.write(marker + "\n" + prose + "\n")

    def gate(self, only=None):
        return gate_units.gate_chapter(self.ext, "1", units_sub="units",
                                       only_unit=only)


class AssemblyEquivalence(Base):
    def test_chapter_gate_and_unit_mode_agree_on_verbatim(self):
        ok_all, det_all = self.gate()
        self.assertFalse(ok_all, det_all)
        self.assertIn("0001_desc_D1.md", det_all)
        self.assertIn(FLAG, det_all, det_all)
        # 判据本体：同装配的自检必须报出同一发现（此前外部脚本看不见）
        ok_u, det_u = self.gate(only="0001_desc_D1.md")
        self.assertFalse(ok_u, det_u)
        self.assertIn(FLAG, det_u, det_u)
        self.assertIn("0001_desc_D1.md", det_u, det_u)

    def test_unit_mode_excludes_other_units_noise(self):
        """整章门控同时报「0002 仍未处理」；自检只跑被点名的单元 → 不得带出同事噪音。"""
        ok_all, det_all = self.gate()
        self.assertIn("仍未处理", det_all, det_all)
        ok_u, det_u = self.gate(only="0001_desc_D1.md")
        self.assertNotIn("仍未处理", det_u, det_u)
        self.assertNotIn("0002", det_u, det_u)

    def test_draft_unit_still_fails_unit_mode(self):
        ok_u, det_u = self.gate(only="0002_desc_D2.md")
        self.assertFalse(ok_u, det_u)
        self.assertIn("仍未处理", det_u, det_u)
        self.assertNotIn(FLAG, det_u, det_u)

    def test_clean_done_unit_passes(self):
        # 改写 + 达标 → 自检通过（该单元的真实渲染照跑）
        self._write("0001_desc_D1.md", _marker("DONE", "0001", "D1", "§1.1 D1"),
                    "Here $a_n \\to a$ and $b_n = 1 - 1/n$: two behaviours quite "
                    "unlike the sequence described above.")
        ok_u, det_u = self.gate(only="0001_desc_D1.md")
        self.assertTrue(ok_u, det_u)
        self.assertIn("单元级门控通过", det_u, det_u)

    def test_fixture_overlap_is_real(self):
        """夹具自检：照抄段与 page 源的重合率确实过阈值（防夹具退化成假绿）。"""
        from verbose_gates import _source_ngrams, _verbatim_overlap
        grams = _source_ngrams(self.ext, "1")
        self.assertTrue(grams, "夹具未取到源 n-gram（page/chapter_map 没铺对）")
        self.assertGreaterEqual(_verbatim_overlap(SOURCE_PROSE, grams),
                                VERBOSE_OVERLAP_MIN)
        self.assertLess(_verbatim_overlap(REWRITE, grams), VERBOSE_OVERLAP_MIN)


class UnknownUnit(Base):
    def test_unlisted_file_is_not_silently_green(self):
        ok_u, det_u = self.gate(only="9999_desc_D9.md")
        self.assertFalse(ok_u, det_u)
        self.assertIn("不在", det_u, det_u)
        self.assertIn("manifest.json", det_u, det_u)

    def test_cli_requires_exactly_one_chapter(self):
        old = sys.argv
        sys.argv = ["gate_units.py", self.ext, "1", "2", "--unit", "0001_desc_D1.md"]
        try:
            self.assertEqual(gate_units.main(), 2)
        finally:
            sys.argv = old


class DraftBodyPrecheck(Base):
    """``tolerate_draft`` 正文预判通道：DRAFT 态也要能拿到**正文**结论。

    默认路径在「标记仍为 DRAFT」处 `continue`，正文质量判据**根本不跑** ⇒ 写手在改
    正文阶段只能见 `RESULT FAIL`，与作业纪律「没拿到 OK 不许写 DONE」字面冲突，
    实际结果是先翻 DONE 再验（先落账后验收）。Lehmann 2026-10-17/18 三个批次独立上报。
    """

    def test_precheck_actually_runs_body_judgment(self):
        """判据本体（负向）：DRAFT 单元正文照抄原书 → 预判必须照样报出，不是 blanket pass。"""
        self._write("0002_desc_D2.md", _marker("DRAFT", "0002", "D2", "§1.1 D2"),
                    SOURCE_PROSE)
        ok, det = gate_units.gate_chapter(self.ext, "1", units_sub="units",
                                         only_unit="0002_desc_D2.md",
                                         tolerate_draft=True)
        self.assertFalse(ok, det)
        self.assertIn(FLAG, det, det)

    def test_precheck_passes_clean_draft_body_without_marker_noise(self):
        ok, det = gate_units.gate_chapter(self.ext, "1", units_sub="units",
                                         only_unit="0002_desc_D2.md",
                                         tolerate_draft=True)
        self.assertTrue(ok, det)
        self.assertNotIn("仍未处理", det, det)

    def test_default_path_still_requires_done(self):
        """放宽只给预判通道：不带 tolerate_draft 的默认门控口径一字不变。"""
        ok, det = self.gate(only="0002_desc_D2.md")
        self.assertFalse(ok, det)
        self.assertIn("仍未处理", det, det)

    def test_no_bookwide_backdoor(self):
        """🔴 不给 only_unit 就放宽 = 整章静默放过 DRAFT，必须是报错而不是放行。"""
        with self.assertRaises(ValueError):
            gate_units.gate_chapter(self.ext, "1", units_sub="units",
                                    tolerate_draft=True)

    def test_selfcheck_entry_emits_body_token(self):
        """`tools/_selfcheck_unit.py` 的输出契约：DRAFT 态给 MARK/RESULT/BODY 三行。"""
        import subprocess
        tool = os.path.join(_ROOT, "tools", "_selfcheck_unit.py")
        env = dict(os.environ, PYTHONUTF8="1",
                   PYTHONPATH=_ROOT + os.pathsep + os.pathsep.join(sys.path))
        p = subprocess.run([sys.executable, tool,
                            os.path.join(self.units_dir, "0002_desc_D2.md")],
                           capture_output=True, text=True, encoding="utf-8", env=env)
        self.assertIn("MARK DRAFT", p.stdout, p.stdout + p.stderr)
        self.assertIn("RESULT FAIL", p.stdout, p.stdout + p.stderr)
        self.assertIn("BODY OK", p.stdout, p.stdout + p.stderr)
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
