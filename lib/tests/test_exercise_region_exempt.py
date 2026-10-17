"""Tests for the 章末**集中习题节**（V-I「整节都是习题的节一律省略」）豁免链。

Run:  python lib/tests/test_exercise_region_exempt.py

立项根因（Lehmann《Elements of Large-Sample Theory》实测 2026-10-16）：本书章末节印
`1.7 Problems` / `6.6 Problems`，V-I 规定整块省略，产出侧（`scan_skeleton` STICKY 闩锁 +
`build_structure` 3a-2 条目切断 + 4a-exer 节打标）照此不落，但校验链原先**不认识**
`exercise_region_headings` 这个声明，于是：
  * D 层报「MISSING TAIL SECTION §1.7」（该节头连契约都没进，`--backfill` 会回填出伪节）；
  * B 层报「§1.7 书中含「定理」1 条（首项 定理1.7-1），但总结未含任何「定理」条目」；
  * 结构闸门把习题区里的 `Theorem 1.7-1` 报成 readable 缺项并索要回填。
即**闸门逼写手写书里规定要省略的内容**。本测试钉住豁免链的每一环，并钉住
「未声明的书零回归」（负向用例）。
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
    _ROOT = str(Path(__file__).resolve().parents[2])
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lib.boot as _boot
_boot.setup()

import scan_skeleton
from lib import exercise_region as _exreg
from verify_config import BookConfig, GroupConfig
from data.book_structure.book_structure import unit_node_entries
from section_continuity import check_d_layer


def _rx(headings):
    return scan_skeleton._exercise_headings_re(headings)


class TestHeadingRegex(unittest.TestCase):
    """块头匹配器：印面形态全覆盖，散文行不误伤。"""

    def test_declared_headings_only(self):
        self.assertIsNone(_rx(None))
        self.assertIsNone(_rx([]))

    def test_bare_and_numbered_forms(self):
        rx = _rx(["Problems"])
        for s in ["Problems", "1.7 Problems", "2.9 Problems", "PROBLEMS",
                  "1.7 Problems.", "§1.7 Problems"]:
            self.assertTrue(rx.match(s), s)

    def test_glued_printed_page_number_and_trailing_debris(self):
        """`4.5 Problems269` / `1.7 Problems  35`：OCR 把印刷页码粘在标题后。"""
        rx = _rx(["Problems"])
        for s in ["4.5 Problems269", "5.8 Problems349", "1.7 Problems  35",
                  "6.6 Problems."]:
            self.assertTrue(rx.match(s), s)

    def test_letter_chapter_ordinal(self):
        """附录章 `A.7 Problems`：序标可是字母。"""
        rx = _rx(["Problems"])
        self.assertTrue(rx.match("A.7 Problems"))

    def test_prose_line_is_not_a_block_head(self):
        rx = _rx(["Problems"])
        for s in ["Problems and proofs are collected at the end of each chapter",
                  "the following problems illustrate the result",
                  "1.7 Problems and complementary exercises"]:
            self.assertIsNone(rx.match(s), s)


class _PageFixture(unittest.TestCase):
    """共用临时页目录构造。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ext = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def write_page(self, page, blocks):
        """blocks: [text] 或 [(text, y)] 或 [(text, y, x)]（几何供页眉带判据用）。"""
        out = []
        for b in blocks:
            if isinstance(b, tuple):
                text, y = b[0], b[1]
                x = b[2] if len(b) > 2 else 40.0
                out.append({"text": text,
                            "poly": [x, y, x + 460.0, y, x + 460.0, y + 20.0,
                                     x, y + 20.0]})
            else:
                out.append({"text": b})
        with open(os.path.join(self.ext, "page_%03d.json" % page),
                  "w", encoding="utf-8") as f:
            json.dump({"text": out}, f, ensure_ascii=False)


class TestSectionNumbers(_PageFixture):
    def _pages(self):
        self.write_page(50, ["1.6 Asymptotic expansions",
                             "Theorem 1.6-1 Suppose that Fn converges"])
        self.write_page(52, ["1.7 Problems",
                             "Theorem 1.7-1 If the distributions are tight"])

    def test_declared_returns_section_number(self):
        self._pages()
        cfg = BookConfig(exercise_region_headings=["Problems"])
        self.assertEqual(_exreg.section_numbers(self.ext, 1, 50, 52, cfg), {7})

    def test_undeclared_returns_empty(self):
        self._pages()
        self.assertEqual(_exreg.section_numbers(self.ext, 1, 50, 52, BookConfig()),
                         set())

    def test_other_chapter_prefix_ignored(self):
        self._pages()
        cfg = BookConfig(exercise_region_headings=["Problems"])
        self.assertEqual(_exreg.section_numbers(self.ext, 2, 50, 52, cfg), set())

    def test_running_head_band_not_a_block_head(self):
        """页眉带（页首 + 明显右移）每页重印 `Problems`，不得当块头。"""
        self.write_page(52, [("1.7 Problems", 30.0, 400.0),
                             ("1.6 Asymptotic expansions", 300.0, 40.0)])
        cfg = BookConfig(exercise_region_headings=["Problems"])
        self.assertEqual(_exreg.section_numbers(self.ext, 1, 52, 52, cfg), set())


class TestDLayerExemption(_PageFixture):
    """D 层：习题节既不索要节本身，也不因节内编号项投影出该节的 labeled 证据。"""

    def _md(self):
        md = "# Chapter 1\n" + "".join(
            "\n## §1.%d Some section\n\nbody\n" % i for i in range(1, 7))
        fd, path = tempfile.mkstemp(suffix=".md")
        os.close(fd)
        self.addCleanup(os.unlink, path)
        with open(path, "w", encoding="utf-8") as f:
            f.write(md)
        return path

    def _pages(self):
        self.write_page(50, ["1.6 Asymptotic expansions",
                             "Theorem 1.6-1 Suppose that Fn converges"])
        self.write_page(52, ["1.7 Problems",
                             "Theorem 1.7-1 If the distributions are tight"])

    def _run(self, cfg):
        self._pages()
        return check_d_layer(1, 50, 52, self._md(), self.ext, cfg=cfg)

    def test_declared_exempts_tail_section(self):
        d = self._run(BookConfig(exercise_region_headings=["Problems"],
                                 section_types=[1, 2, 3]))
        self.assertEqual(d["missing_sections"], [])
        self.assertEqual(d["continuity_sections"], [])

    def test_undeclared_still_demands_it(self):
        """零回归负向：未声明的书照旧报缺节（豁免确实由声明驱动）。"""
        d = self._run(BookConfig(section_types=[1, 2, 3]))
        self.assertIn("7", d["missing_sections"])


class TestContractConsolidatedSection(unittest.TestCase):
    """契约侧：consolidated 的节不出单元（门控反向对账⑩不得索要）。"""

    def _root(self, **sec):
        section = {"type": "section", "key": "1.7", "name": "1.7 Problems",
                   "sub_sec": [{"type": "problem", "key": "1.7-1",
                                "name": "Theorem 1.7-1",
                                "sub_sec": [{"type": "text",
                                             "text": "If the distributions are tight"}]}]}
        section.update(sec)
        return {"type": "chapter", "key": "1", "name": "Chapter 1",
                "sub_sec": [
                    {"type": "section", "key": "1.6", "name": "1.6 Expansions",
                     "sub_sec": [{"type": "theorem", "key": "1.6-1",
                                  "name": "Theorem 1.6-1",
                                  "sub_sec": [{"type": "text",
                                               "text": "Suppose that Fn converges"}]}]},
                    section]}

    def test_consolidated_section_drops_its_whole_subtree(self):
        out = unit_node_entries(self._root(consolidated=True))
        self.assertNotIn(("content", "1.7"), out)
        self.assertNotIn(("exercise", "1.7-1"), out)
        self.assertIn(("content", "1.6"), out)

    def test_plain_section_still_produces_units(self):
        out = unit_node_entries(self._root())
        self.assertIn(("content", "1.7"), out)
        self.assertIn(("exercise", "1.7-1"), out)


class TestGateItemCut(_PageFixture):
    """结构闸门（step3 源侧条目集）与产出侧 3a-2 同源：块头之下的条目不索要。"""

    def _items(self):
        return [
            {"key": "Theorem 1.6-1", "label": "Theorem", "page": 50,
             "snippet": "Theorem 1.6-1 Suppose that", "canon": [1, 6, 1],
             "has_label": True, "scheme": "en3"},
            {"key": "Theorem 1.7-1", "label": "Theorem", "page": 52,
             "snippet": "Theorem 1.7-1 If the distributions", "canon": [1, 7, 1],
             "has_label": True, "scheme": "en3"},
        ]

    def test_declared_drops_region_items(self):
        from check_structure_completeness import _drop_exercise_region_items
        self.write_page(51, ["1.6 Asymptotic expansions",
                             "Theorem 1.6-1 Suppose that Fn converges"])
        self.write_page(52, [("1.7 Problems", 200.0),
                             ("Theorem 1.7-1 If the distributions are tight", 400.0)])
        cfg = BookConfig(exercise_region_headings=["Problems"])
        kept = _drop_exercise_region_items(1, 50, 52, self.ext, cfg, self._items())
        self.assertEqual([it["key"] for it in kept], ["Theorem 1.6-1"])

    def test_undeclared_keeps_everything(self):
        from check_structure_completeness import _drop_exercise_region_items
        self.write_page(52, ["1.7 Problems",
                             "Theorem 1.7-1 If the distributions are tight"])
        kept = _drop_exercise_region_items(1, 50, 52, self.ext, BookConfig(),
                                           self._items())
        self.assertEqual(len(kept), 2)

    def test_item_above_head_on_head_page_survives(self):
        """y 感知：与块头同页、位于块头**之上**的条目属正文，须保留。"""
        from check_structure_completeness import _drop_exercise_region_items
        self.write_page(52, [("Theorem 1.6-9 Suppose that", 100.0),
                             ("1.7 Problems", 400.0)])
        items = [{"key": "Theorem 1.6-9", "label": "Theorem", "page": 52,
                  "snippet": "Theorem 1.6-9 Suppose that", "canon": [1, 6, 9],
                  "has_label": True, "scheme": "en3"}]
        cfg = BookConfig(exercise_region_headings=["Problems"])
        kept = _drop_exercise_region_items(1, 50, 52, self.ext, cfg, items)
        self.assertEqual([it["key"] for it in kept], ["Theorem 1.6-9"])


class TestBLayerCategoryExemption(_PageFixture):
    """B 层「整类首项缺失」：习题节不参与（ch1 §1.7 只有一条 Theorem 的形态）。"""

    def _ctx(self, cfg):
        from item_numbering_integrity import _merged_category_first_missing

        class _Ctx:
            pass
        ctx = _Ctx()
        ctx.ch, ctx.start, ctx.end, ctx.ext_dir = 1, 52, 52, self.ext
        ctx.config = cfg
        return ctx, _merged_category_first_missing

    def _cfg(self, **kw):
        return BookConfig(ordinal=[GroupConfig(type=3, name=["Theorem"])], **kw)

    def test_exercise_section_skipped(self):
        self.write_page(52, ["1.7 Problems",
                             "Theorem 1.7-1 If the distributions are tight"])
        ctx, fn = self._ctx(self._cfg(exercise_region_headings=["Problems"]))
        blocking = []
        fn(ctx, [], blocking)
        self.assertEqual(blocking, [])

    def test_undeclared_still_reports(self):
        """零回归负向：未声明的书照旧索要该节首项。"""
        self.write_page(52, ["1.7 Problems",
                             "Theorem 1.7-1 If the distributions are tight"])
        ctx, fn = self._ctx(self._cfg())
        blocking = []
        fn(ctx, [], blocking)
        self.assertTrue(blocking)


if __name__ == "__main__":
    unittest.main(verbosity=2)
