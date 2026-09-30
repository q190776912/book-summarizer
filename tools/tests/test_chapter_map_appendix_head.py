# -*- coding: utf-8 -*-
"""test_chapter_map_appendix_head.py — 附录「带前缀章头」的 Mode B 判据。

缺陷根因（Evans《PDE》2ed 实测 2026-09-30）：书后 p706 印一页 ``APPENDICES``，把五个
附录标题**带序标**逐行列出（``A. Notation`` / ``B. Inequalities`` / ``C. Calculus`` …），
A 章就在同页开始；其余附录的真章头写作 ``APPENDIX B: INEQUALITIES``（也带前缀）。
Mode B 只比裸标题 → 列表行把 A–E 全部锚到 p706（起点不递增、end<start → 整本 SUSPECT，
只能人工补页码），真章头反因带前缀命不中。

修复形态（`tools/build_chapter_map.py`）：附录章比对时额外试「剥掉 APPENDIX/附录 +
序标」的形式（:func:`appendix_head_norm`），真章头于是成为起点证据并以满分压过列表行。
数字章不给该形式（不得靠剥前缀蹭别处印的 ``APPENDIX A: …``）。

🔴 曾同时存在「同页 ≥2 章裸标题命中 → 整页作废」的目录/分隔页闸，**已删除**：它对
Evans 无贡献（只留本判据即得 A706/B714/C719/D728/E738，与人工核验逐页相同），却会毁掉
中文书真开页——见 `CjkDegeneratedTitleCollision`。目录页形态由 `_b_shape_ok` 的
"Contents" 首行判据覆盖（Apostol IANT 实测）。

正向：带前缀真章头 → 各附录锚到自己的开页，起点随章序递增。
负向：①无真章头证据时列表页把多章并到同一页（证明本判据是必要证据，而非锦上添花）；
      ②普通单章开页照常命中；③剥前缀只对附录记录生效。
"""
import os
import sys
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
    "build_chapter_map", os.path.join(_ROOT, "tools", "build_chapter_map.py"))
bcm = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(bcm)


def _tl(page, raw, line_idx=0, next_raw="", page_first="", norms=None):
    """构造 scan_headings 形态的 title_line。

    `norms` 给跨行拼接候选（真章头常被大号排版拆成两三行，只有拼接后才与全长标题
    相等）；缺省时只放本行归一值。
    """
    n = bcm.norm_title(raw)
    return {"page": page, "line_idx": line_idx, "norm": n,
            "norms": norms or [n], "raw": raw,
            "next_raw": next_raw, "page_first": page_first or raw}


def _ch(ch, name, start=None, end=None, appendix=False, kind=None):
    rec = {"ch": ch, "name": name, "name_en": name, "start": start, "end": end}
    if appendix:
        rec["appendix"] = True
    if kind is not None:
        rec["kind"] = kind
    return rec


APPS = [
    _ch("A", "Notation", 706, 713, appendix=True, kind=2),
    _ch("B", "Inequalities", 714, 718, appendix=True, kind=2),
    _ch("C", "Calculus", 719, 727, appendix=True, kind=2),
    _ch("D", "Functional Analysis", 728, 737, appendix=True, kind=2),
    _ch("E", "Measure Theory", 738, 743, appendix=True, kind=2),
]

# p706：列表页逐行列出五个附录标题（带序标前缀），appendix A 自己的章头在第 6 行。
# 其余附录的开页只印带前缀章头（Evans 印面形态）。
TITLE_LINES = [
    _tl(706, "APPENDICES", 0, page_first="APPENDICES"),
    _tl(706, "A. Notation", 1, page_first="APPENDICES"),
    _tl(706, "B. Inequalities", 2, page_first="APPENDICES"),
    _tl(706, "C. Calculus", 3, page_first="APPENDICES"),
    _tl(706, "D. Functional analysis", 4, page_first="APPENDICES"),
    _tl(706, "E. Measure theory", 5, page_first="APPENDICES"),
    _tl(706, "APPENDIX A: NOTATION", 6, next_raw="A.1. Notation for matrices",
        page_first="APPENDICES"),
    _tl(714, "APPENDIX B:INEQUALITIES", 0, next_raw="705"),
    _tl(714, "APPENDIX B: INEQUALITIES", 2, next_raw="B.1. Convex functions."),
    _tl(719, "APPENDIX C: CALCULUS", 4, next_raw="C.1. Boundaries."),
    _tl(728, "APPENDIX D: FUNCTIONAL ANALYSIS", 0, next_raw="D.1. Banach spaces."),
    _tl(738, "APPENDIX E: MEASURE THEORY", 0, next_raw="729"),
]


class DetectAppendixStarts(unittest.TestCase):
    def _chain(self, chapters, title_lines):
        """生产链路：Mode B 检测 → 章序单调修复（与 compute_ranges 同序）。"""
        pool = {}
        det = bcm.detect_starts(chapters, [], title_lines, openers=[],
                                candidates=pool)
        starts = {k: v[0] for k, v in det.items()}
        fixed, _repairs = bcm.repair_monotonic_starts(
            starts, pool, [str(c["ch"]) for c in chapters])
        return fixed

    def test_each_appendix_anchors_its_own_head_page(self):
        """正向：五个附录各自锚到印有自己的带前缀章头的页，而非 p706 列表页。

        E 的开页只印页眉式章头（后跟裸页码 → 罚分），裸检会被列表页压住，靠章序
        单调修复从候选池里取回真开页——与《Evans》实测的 REPAIRED 同一条路。
        """
        self.assertEqual(self._chain(APPS, TITLE_LINES),
                         {"A": 706, "B": 714, "C": 719, "D": 728, "E": 738})

    def test_starts_strictly_increase_with_head_evidence(self):
        """起点随附录序严格递增（SUSPECT 自检放行的前提）。"""
        pages = [self._chain(APPS, TITLE_LINES)[c["ch"]] for c in APPS]
        self.assertEqual(pages, sorted(pages))
        self.assertEqual(len(set(pages)), len(pages))

    def test_running_head_is_penalised(self):
        """章头行后紧跟裸页码（页眉形态）罚分，真开页那一行当选。"""
        only_head = [_tl(714, "APPENDIX B: INEQUALITIES", 0, next_raw="711"),
                     _tl(730, "APPENDIX B: INEQUALITIES", 2, next_raw="B.9.stuff")]
        det = bcm.detect_starts([APPS[1]], [], only_head, openers=[])
        self.assertEqual(det["B"][0], 730)
        self.assertEqual(det["B"][1], 1.0)   # 罚分的页眉（p714）未当选

    def test_without_head_evidence_the_list_page_collapses(self):
        """负向①：关掉「剥前缀」判据（回到改动前），列表页把多章并到同一页 →
        起点不递增。证明带前缀章头是这条链的必要证据，不是锦上添花。"""
        real = bcm.appendix_head_norm
        bcm.appendix_head_norm = lambda raw: None
        try:
            det = bcm.detect_starts(
                [_ch(c["ch"], c["name"], appendix=True, kind=2) for c in APPS],
                [], TITLE_LINES, openers=[])
        finally:
            bcm.appendix_head_norm = real
        pages = [det[c["ch"]][0] for c in APPS if c["ch"] in det]
        self.assertGreater(len(pages), 1)
        self.assertLess(len(set(pages)), len(pages), pages)

    def test_single_chapter_opener_still_detected(self):
        """负向②：普通单章开页照常命中（本判据不得干扰数字章）。"""
        chs = [_ch(1, "Metric Spaces", 19, 32), _ch(2, "Complete Spaces", 33, 60)]
        tls = [_tl(19, "METRIC SPACES", 0, next_raw="1.1 Introduction"),
               _tl(33, "COMPLETE SPACES", 0, next_raw="2.1 Definition")]
        det = bcm.detect_starts(chs, [], tls, openers=[])
        self.assertEqual({k: v[0] for k, v in det.items()}, {"1": 19, "2": 33})

    def test_prefix_strip_only_for_appendix_records(self):
        """负向③：正文数字章不得靠「剥 APPENDIX 前缀」蹭附录章头（窗口内也不给）。"""
        body = [_ch(3, "Notation", 700, 730)]      # 窗口覆盖 p706
        tls = [_tl(706, "APPENDIX A: NOTATION", 6, next_raw="A.1. Matrices")]
        self.assertEqual(bcm.detect_starts(body, [], tls, openers={}).get("3"), None)


class CjkDegeneratedTitleCollision(unittest.TestCase):
    """中文书名 norm_title 抹掉 CJK 只剩零散拉丁词时的「伪多章同页」——曾据此整页
    作废目录/分隔页闸的回归现场（微分遍历论实测 2026-09-30）。

    ch1「微分方程的Lyapunov稳定性」→ "LYAPUNOV"、ch5「Pesin集及其结构」→ "PESIN"，
    而 ch4 的开页 p86 顶部恰有续行「等式，Pesin等式」（norm "PESIN"）与正文行
    「Lyapunov指数通过切映射的…」（norm "LYAPUNOV"）：同页凑出「两章命中两行」。
    ch4 自己的标题被大号排版拆在 line0/line1，只有拼接候选 "4LYAPUNOVRUELLEPESIN"
    才与本章标题相等。旧的分隔页闸把 p86 整页作废，起点被挤到 p87（章首页切给上一章）。
    """

    CHS = [
        _ch(1, "微分方程的Lyapunov稳定性", 10, 24),
        _ch(4, "测度熵与Lyapunov指数：Ruelle不等式，Pesin等式", 86, 125),
        _ch(5, "Pesin集及其结构", 126, 152),
    ]
    TLS = [
        _tl(86, "第4 章测度熵与Lyapunov 指数：Ruelle 不", 0,
            next_raw="等式，Pesin等式",
            norms=["4LYAPUNOVRUELLE", "4LYAPUNOVRUELLEPESIN",
                   "4LYAPUNOVRUELLEPESINLYAPUNOV"]),
        _tl(86, "等式，Pesin等式", 1, next_raw="Lyapunov指数通过切映射的…",
            norms=["PESIN", "PESINLYAPUNOV"]),
        _tl(86, "Lyapunov指数通过切映射的扩张性量度保测概率系统的运动复杂", 2,
            next_raw="性。本章给出两个…", norms=["LYAPUNOV", "LYAPUNOVRUELLEPESIN"]),
        _tl(87, "78第4章测度熵与Lyapunov 指数：Ruelle 不等式，Pesin 等式", 0,
            next_raw="V f-iα= {Aio N f-Ai N..}",
            norms=["784LYAPUNOVRUELLEPESIN"]),
        _tl(126, "Pesin集及其结构", 0, next_raw="5.1 稳定集"),
    ]

    def test_degenerate_collision_exists_in_the_pool(self):
        """前提确认：p86 的两行确实与 ch1/ch5 的归一标题精确相等（判据不是空的）。"""
        self.assertEqual(bcm._b_score(self.TLS[1], bcm.norm_title("Pesin集及其结构")), 1.0)
        self.assertEqual(bcm._b_score(self.TLS[2], bcm.norm_title("微分方程的Lyapunov稳定性")), 1.0)

    def test_real_opener_survives_the_collision(self):
        """正向：跨行拼接命中的真开页 p86 不得被同页的别章关键词命中作废。"""
        det = bcm.detect_starts(self.CHS, [], self.TLS, openers=[])
        self.assertEqual(det["4"][0], 86)

    def test_colliding_chapters_are_not_dragged_to_the_page(self):
        """负向：ch1/ch5 靠申报窗口排除 p86，各自锚自己的页（窗口外的命中不作证据）。"""
        det = bcm.detect_starts(self.CHS, [], self.TLS, openers=[])
        self.assertEqual(det["5"][0], 126)
        self.assertNotIn("1", det)          # ch1 窗口内无证据 → 保留人工申报值
        claimed = [tl["page"] for tl in self.TLS if tl["page"] == 86]
        self.assertTrue(claimed)


class AppendixHeadNorm(unittest.TestCase):
    def test_strip_forms(self):
        self.assertEqual(bcm.appendix_head_norm("APPENDIX B:INEQUALITIES"),
                         "INEQUALITIES")
        self.assertEqual(bcm.appendix_head_norm("Appendix C. Calculus"), "CALCULUS")
        self.assertEqual(bcm.appendix_head_norm("APPENDIX D: FUNCTIONAL ANALYSIS"),
                         "FUNCTIONALANALYSIS")

    def test_rejects_non_head(self):
        for raw in ["Notation", "APPENDICES", "AN INTRODUCTION TO CALCULUS", "",
                    "APPENDIX"]:
            self.assertIsNone(bcm.appendix_head_norm(raw), raw)

    def test_cjk_title_returns_none(self):
        """中文题名 norm_title 归一为空 → 本形态不适用，返回 None 而非空串。"""
        self.assertIsNone(bcm.appendix_head_norm("附录 D 泛函分析"))


if __name__ == "__main__":
    unittest.main()
