"""Regression tests: 序标校验下放到「总结单元校验」（gate_units，合并前即拦）。

背景：序标（1:1 保真铁律）原先只有章级 verify 一道闸——B 层（条目编号缺号 /
顺序错乱）与 O 层（子项 (1)(2)(3) 缺口）都只在**合并后的整章 .md** 上跑，
缺陷要到步骤 8 才暴露，返工成本高。本文件锁定「下放到单元门控」后的行为：

  1. B 层（条目序标）：顺序错乱（1.1-3 排在 1.1-2 前）、缺号（1.1-1 → 1.1-3）
     必须在**合并前**被拦；正常顺序 1,2,3 → 无阻断。
  2. O 层（子项序标）：单元内 `(1)(2)(4)` 缺 3 → 必须拦；`(1)(2)(3)` 干净 → 过。
     **desc 描述单元**内的子项序列同样覆盖（描述单元也在章级拼接里）。
  3. fail-closed：B/O 层不可用 / 抛异常 → 按「序标校验不通过」返回，绝不静默放行。

🔴 **粒度纪律（实测教训，勿回退）**：两者都**按章级跑**（把本章单元按 manifest
顺序重建等价 merge 产物的 md），**不可下放到逐单元**——缺号/顺序天然跨单元；
O 层按「行距 ≤4」成块，逐单元会切断/错并序列窗，实测把已 PASS 的
statistical-inference 误报 2 处（roman `(i)(ii)(iii)` 与 alpha `(c)(d)` 被并进
同一窗，报出一串假缺口）。拼接还必须复刻 `---` 分隔线与 section 单元的 `## §`
锚点，否则与章级 verify 结论分叉。

🔴 两处均**复用 verify 真层**（`_md_gap_blocking` / `check_ordinal_subitem_gaps`），
不复制判据——故本文件不重复断言阈值细节，只断言「单元门控确实拦得住」。
"""
import json
import os
import shutil
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
import lib.boot as _boot  # noqa: E402
_boot.setup()

import gate_units as gu  # noqa: E402
from subitem_continuity import _classify_block  # noqa: E402


_CFG = {"ch": {"ordinal": [{"type": 3, "name": ["uncat"], "scope": 3}],
               "strict": True, "ignore": []}}

# 子项序列（缺口 / 干净各一）
_SUBITEMS_GAP = "\n(1) 第一条结论。\n\n(2) 第二条结论。\n\n(4) 第四条结论。\n"
_SUBITEMS_OK = "\n(1) 第一条结论。\n\n(2) 第二条结论。\n\n(3) 第三条结论。\n"


def _ord_body(ordinal, subitems=""):
    """条目单元正文：加粗条头承载三级序标 `1.1-N`（可选追加子项序列）。"""
    return "**%s**\n\n正文内容。\n%s" % (ordinal, subitems)


class _ChapterFixture(unittest.TestCase):
    """搭一个最小可跑章：_extract（含 MM Repair 完成标记 + 配置）+ units/ch1。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bks_ord_")
        self.ext = os.path.join(self.tmp, "_extract")
        self.out_dir = os.path.join(self.ext, "book_structure", "units", "ch1")
        os.makedirs(self.out_dir, exist_ok=True)
        # 🔴 ConfigLoader 硬闸：缺 _extraction_done.json（MM Repair 完成标记）
        # 时拒绝加载 verify_config.json——真实书均已完成 MM Repair，夹具须补。
        with open(os.path.join(self.ext, "_extraction_done.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"status": "done"}, f)
        for d in (self.ext, self.tmp):   # extract_dir / book_dir 两处都放
            with open(os.path.join(d, "verify_config.json"), "w",
                      encoding="utf-8") as f:
                json.dump(_CFG, f)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_unit(self, fname, key, utype, body):
        with open(os.path.join(self.out_dir, fname), "w", encoding="utf-8") as f:
            f.write("<!-- book-summarizer DONE unit: id=%s type=%s key=%s name=x -->\n"
                    % (fname, utype, key))
            f.write(body)

    def _build(self, specs):
        """specs: [(key, utype, body), ...] → 写单元文件，返回 units 列表。"""
        units = []
        for i, (key, utype, body) in enumerate(specs, start=1):
            fname = "%04d_%s.md" % (i, utype)
            self._write_unit(fname, key, utype, body)
            units.append({"file": fname, "type": utype, "key": key})
        with open(os.path.join(self.out_dir, "manifest.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"units": units}, f)
        return units

    def _gate(self, specs):
        """B 层阻断判定（进入门控 problems，会让门控不通过）。"""
        units = self._build(specs)
        return gu._check_ordinals_chapter(self.ext, 1, self.out_dir, units)

    def _subitem(self, specs):
        """O 层子项序标结果（从章级序标校验结果里筛 ``[O层序标]`` 前缀项）。"""
        units = self._build(specs)
        return [p for p in gu._check_ordinals_chapter(
            self.ext, 1, self.out_dir, units) if "O层序标" in p]

    def _items(self, ordinals, subitems=""):
        return [(o, "item", _ord_body(o, subitems)) for o in ordinals]


class ItemOrdinalTest(_ChapterFixture):
    """B 层条目序标：顺序错乱 / 缺号必须在合并前的单元门控即被拦。"""

    def test_clean_sequence_has_no_blocking(self):
        probs = self._gate(self._items(["1.1-1", "1.1-2", "1.1-3"]))
        self.assertEqual(probs, [], "正常 1,2,3 顺序不应产生阻断：%s" % probs)

    def test_out_of_order_is_blocked(self):
        """顺序错乱：1.1-3 排在 1.1-2 之前（B 层判确定性错误，恒 BLOCKING）。"""
        probs = self._gate(self._items(["1.1-1", "1.1-3", "1.1-2"]))
        self.assertTrue(probs, "顺序错乱必须被拦")
        self.assertTrue(any("顺序错乱" in p for p in probs), probs)
        self.assertTrue(any("B层序标" in p for p in probs), probs)

    def test_missing_number_is_blocked(self):
        """缺号：1.1-1 直接跳到 1.1-3（strict 默认 True → BLOCKING）。"""
        probs = self._gate(self._items(["1.1-1", "1.1-3"]))
        self.assertTrue(probs, "缺号 1.1-2 必须被拦")
        self.assertTrue(any("B层序标" in p for p in probs), probs)


class SubitemOrdinalTest(_ChapterFixture):
    """O 层子项序标：缺口阻断门控、干净不报，覆盖 desc 描述单元。

    O 层对拼缝邻接敏感，故待校验 md **必须**由 `merge_units.merge_chapter` 亲自
    产出（`_merged_chapter_md`）——本类同时守护「门控看到的 = 最终章 md」这一前提：
    否则手搓拼接会漂移并误报（见被测函数 docstring 的历史教训）。
    """

    def test_subitem_gap_is_reported(self):
        hints = self._subitem(self._items(["1.1-1"], _SUBITEMS_GAP))
        self.assertTrue(any("O层序标" in h for h in hints), hints)

    def test_subitem_clean_not_reported(self):
        hints = self._subitem(self._items(["1.1-1"], _SUBITEMS_OK))
        self.assertEqual([h for h in hints if "O层序标" in h], [],
                         "干净子项序列不应报：%s" % hints)

    def test_subitem_reported_in_desc_unit(self):
        """描述单元（desc）内的子项序列同样覆盖——用户明确要求。"""
        hints = self._subitem([("D1", "desc", "描述段落。\n" + _SUBITEMS_GAP)])
        self.assertTrue(any("O层序标" in h for h in hints),
                        "desc 单元的子项缺口也应报：%s" % hints)

    def test_subitem_gap_blocks_gate(self):
        """O 层缺口须**进入阻断列表**（校验有效，不再只是提示）。"""
        blocking = self._gate(self._items(["1.1-1"], _SUBITEMS_GAP))
        self.assertTrue(any("O层序标" in p for p in blocking),
                        "O 层缺口应阻断门控：%s" % blocking)


class SubitemClassifierTest(unittest.TestCase):
    """O 层 ``_classify_block`` 异质序列守卫——本次根因修复的回归锁。

    statistical-inference 3.33/3.34 实测：罗马任务段 ``(i)(ii)(iii)`` 与字母选项段
    ``(a)(b)(c)(d)`` 同处一块，而 ``c``/``d`` 恰好也是合法罗马字符（100/500），
    整块过 ``_roman_to_int`` 得 ``[1,2,3,100,500]`` → 凭空造出 4..499 一串幽灵号。

    锁两件事：① 异质块判 ``'mixed'``（下游 ``continue`` 跳过，不制造噪声）；
    ② **不得误伤**正常 roman / numeric / alpha 序列——否则真缺号会被漏掉，
    那就从「误报」变成「漏报」，一样是掩盖缺陷。
    """

    def test_roman_tasks_plus_alpha_items_is_mixed(self):
        st = _classify_block([(0, 'i'), (2, 'ii'), (4, 'iii'),
                              (6, 'c'), (8, 'd')])[0]
        self.assertEqual(st, 'mixed', "罗马任务段+字母选项段须判异质跳过")

    def test_plain_roman_sequence_preserved(self):
        st, vals = _classify_block([(0, 'i'), (2, 'ii'), (4, 'iii'), (6, 'iv')])
        self.assertEqual(st, 'roman')
        self.assertEqual([v for _, v in vals], [1, 2, 3, 4])

    def test_numeric_gap_sequence_preserved(self):
        st, vals = _classify_block([(0, '1'), (2, '2'), (4, '4')])
        self.assertEqual(st, 'numeric', "真缺号序列不能被守卫吃掉")
        self.assertEqual([v for _, v in vals], [1, 2, 4])

    def test_alpha_gap_sequence_preserved(self):
        st, vals = _classify_block([(0, 'a'), (2, 'b'), (4, 'd')])
        self.assertEqual(st, 'alpha', "真缺号序列不能被守卫吃掉")
        self.assertEqual([v for _, v in vals], [1, 2, 4])

    def test_end_to_end_heterogeneous_block_not_reported(self):
        """端到端：3.33 形态（罗马任务 + 字母族）不得再报子项缺口。"""
        body = ("**3.33** For each of the following families:\n\n"
                "(i) Verify it.\n\n(ii) Describe it.\n\n(iii) Sketch it.\n\n"
                "(a) first\n\n(b) second\n\n(c) third\n\n(d) fourth\n")
        import tempfile, shutil as _sh
        tmp = tempfile.mkdtemp(prefix="bks_cls_")
        try:
            from subitem_continuity import check_ordinal_subitem_gaps
            p = os.path.join(tmp, "t.md")
            with open(p, "w", encoding="utf-8") as f:
                f.write(body)
            x = [g for g in (check_ordinal_subitem_gaps(p) or [])
                 if str(g).strip().startswith("x")]
            self.assertEqual(x, [], "异质块不应报子项缺口：%s" % x)
        finally:
            _sh.rmtree(tmp, ignore_errors=True)


class FailClosedTest(_ChapterFixture):
    def test_no_units_yields_no_problems(self):
        """空章（无单元）→ 无序标可判（非「放行缺陷」，同章级空章行为）。"""
        self.assertEqual(self._gate([]), [])

    def test_merge_failure_is_fail_closed(self):
        """单元文件缺失 → merge 抛错 → 序标校验 fail-closed（返回问题，不静默过）。"""
        units = [{"file": "9999_missing.md", "type": "item", "key": "1.1-1"}]
        with open(os.path.join(self.out_dir, "manifest.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"units": units}, f)
        probs = gu._check_ordinals_chapter(self.ext, 1, self.out_dir, units)
        self.assertTrue(any("fail-closed" in p for p in probs), probs)


if __name__ == "__main__":
    unittest.main()
