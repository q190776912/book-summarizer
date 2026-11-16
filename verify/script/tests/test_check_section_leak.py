# -*- coding: utf-8 -*-
"""节界泄漏闸（check_section_leak）回归测试。

根因（Lee《Introduction to Smooth Manifolds》实测 2026-11-16，全书 65 处 LEAK-A）：
§N 的尾部编号条目与 §N+1 的节头**同页**（节头印在该页下部）时，`_place` 的
「位置未知 → 页末 → 归入本页已开节的最后一节」回退把整批条目挂进 §N+1。Lee ISM
节头是裸标题，页眉复本与真标题**同文本、同左缘**，`_band_split_y` 的右移/前缀
重复判据都不触发 → `_find_title_pos` 取到页眉 y（页顶），同页 y 比较全部失真。
B 层（同标签序号单调）对跨节错挂结构性失明——推论 13.30 挂到 §13.3 后各标签
序号仍单调，门控一路放绿，直到交付按节拆分才肉眼可见。

关键负向（防误报）：
  * 父节条目印在**自己子节**标题之后（Lee ISM §7.4 实测）→ 子树边界豁免，不报；
  * consolidated 节（章末集中习题块）→ 整节豁免；
  * 条目块 OCR 丢失（无证据）→ 跳过不报；
  * 页眉复本让位后条目在真节头之下 → 不报。

运行：
  python verify/script/tests/test_check_section_leak.py
"""
import os
import sys
import json
import shutil
import tempfile
import unittest
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[2])
for _p in (_ROOT, os.path.join(_ROOT, "lib"), os.path.join(_ROOT, "verify", "script")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

from check_section_leak import section_leak_problems  # noqa: E402
from data.book_structure.book_structure import StructureNode  # noqa: E402


def _node(key, ntype, page=0, *kids, **kw):
    n = StructureNode(key=key, type=ntype, name=str(kw.get("name", key)),
                      page_start=page, page_end=page, sub_sec=list(kids))
    if kw.get("consolidated"):
        n.consolidated = True
    return n


def _desc(key, page, text):
    """description 节点（携带一个 text 内容块供前缀锚定；普通 dict，
    与磁盘契约 JSON 形态一致，StructureNode 是 __slots__ 类带不了 text 块）。"""
    return {"key": key, "type": "description", "name": "",
            "page_start": page, "page_end": page, "sub_sec": [],
            "text": [{"text": text}]}


def _write_pages(ext, pages):
    """pages = {page_no: [(y, text), ...]}；写成 page_NNN.json（poly=行框，x=147）。"""
    os.makedirs(ext, exist_ok=True)
    for p, rows in pages.items():
        blocks = []
        for y, t in rows:
            blocks.append({"text": t, "poly": [147, y, 1000, y, 1000, y + 20, 147, y + 20]})
        with open(os.path.join(ext, "page_%03d.json" % p), "w",
                  encoding="utf-8") as f:
            json.dump({"text": blocks}, f, ensure_ascii=False)


class TestSectionLeakGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="leak_gate_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---- 正向：Lee p356 形态（页眉复本同文本同左缘 + 同页跨节头）----------
    def test_lee_running_head_duplicate_same_page_leak(self):
        # p356：页眉复本(y98) → 推论13.30(y164) → 口 → 真节头(y750) → §13.3 首段。
        # 真节头取带下独立命中（y750）而非页眉(y98)，推论 13.30 才会被判进 §13.3 之前。
        _write_pages(self.tmp, {
            352: [(150, "Let $g$ be a Riemannian metric on M."),
                  (1200, "The Riemannian Distance Function")],
            354: [(300, "Theorem13.29(RiemannianManifoldsasMetricSpaces).Let(M,g)be a connected")],
            356: [(98, "The Tangent-Cotangent Isomorphism"),
                  (105, "341"),
                  (164, "Corollary13.30.Everysmoothmanifoldwithorwithoutboundaryis metrizable."),
                  (212, "Proof. First suppose M is a smooth manifold without boundary."),
                  (600, "口"),
                  (750, "The Tangent-Cotangent Isomorphism"),
                  (800, "The Tangent-Cotangent Isomorphism. Another convenient feature of every Riemannian metric")],
        })
        u4 = _node("U4", "section", 352,
                   _node("定理13.29", "theorem", 354),
                   name="The Riemannian Distance Function")
        u5 = _node("U5", "section", 356,
                   _node("推论13.30", "corollary", 356),
                   _desc("D10", 356, "The Tangent-Cotangent Isomorphism. Another convenient feature of every Riemannian metric"),
                   name="The Tangent-Cotangent Isomorphism")
        chapter = _node("13", "chapter", 342, u4, u5)
        probs = section_leak_problems(self.tmp, "13", 342, 363, chapter)
        self.assertEqual(len(probs), 1, "应且仅应报推论13.30 一处泄漏（D10 在节头之下不算）")
        self.assertIn("LEAK-A", probs[0])
        self.assertIn("推论13.30", probs[0])
        self.assertIn("U4", probs[0], "建议归位目标应为上一节 U4")

    # ---- 正向：Brin–Stuck p17 形态（数字节头的页眉复本同文本同左缘）--------
    def test_numbered_running_head_duplicate_same_text_left_edge(self):
        # 页眉 running head "1.2. Circle Rotations"（带句点、正文左缘 x=147、
        # y=62=本页最顶块）+ 真节头 "1.2 Circle Rotations"（y=1416，同页下部）。
        # `_band_split_y` 的「右移 >25%」「前缀重复」两判据皆不触发，数字键锚点
        # 取到页眉 y=62 → 下一节边界被提到页顶，整页正文全部假 LEAK-B（该书
        # 普查 143 处全假阳的根因）。数字键必须同文本让位到带下真节头。
        _write_pages(self.tmp, {
            17: [(62, "1.2. Circle Rotations"),
                 (66, "3"),
                 (332, "An invertible semiconjugacy is called a conjugacy."),
                 (1063, "Exercise 1.1.1. Show that the complement of a forward invariant set is"),
                 (1416, "1.2 Circle Rotations"),
                 (1472, "Consider the unit circle where 0 and 1 are identified.")],
            19: [(62, "1.3. Expanding Endomorphisms of the Circle"),
                 (64, "5"),
                 (138, "The rotation semigroup and its generator considered above is an isometry"),
                 (298, "Exercise 1.2.1. Show that every rotation is an isometry."),
                 (1500, "1.3 Expanding Endomorphisms of the Circle")],
        })
        u1 = _node("1.1", "section", 15,
                   _node("1.1.1", "exercise", 17),
                   name="1.1 The Notion of a Dynamical System")
        u2 = _node("1.2", "section", 17,
                   _desc("D4", 19, "The rotation semigroup and its generator considered above is an isometry"),
                   _node("1.2.1", "exercise", 19),
                   name="1.2 Circle Rotations")
        u3 = _node("1.3", "section", 19,
                   name="1.3 Expanding Endomorphisms of the Circle")
        chapter = _node("1", "chapter", 15, u1, u2, u3)
        probs = section_leak_problems(self.tmp, "1", 15, 25, chapter)
        self.assertEqual(
            probs, [],
            "页眉复本让位后：§1.2/§1.3 边界取带下真节头，1.1.1/1.2.1/D4 全部不再越界")
        # 直接判据：让位函数对 §1.2 返回带下真头 y=1416（而非页眉 62）。
        from check_section_leak import _numbered_band_yield
        y2 = _numbered_band_yield(self.tmp, "1", u2)
        self.assertEqual(y2, 1416.0)

    # ---- 负向：页顶同文本命中只有一处（真节头恰在页顶）→ 不让位 ------------
    def test_numbered_no_yield_when_single_top_hit(self):
        # §1.4 真节头印在页顶（无页眉复本、无第二处同文本命中）→ 锚点保持 y=90，
        # 其后的习题越过真边界，仍须报 LEAK-B（让位判据不得钝化闸口）。
        _write_pages(self.tmp, {
            21: [(90, "1.4 Shifts and Subshifts"),
                 (300, "Exercise 1.3.9. Show that the full shift is expansive.")],
        })
        u3 = _node("1.3", "section", 19,
                   _node("1.3.9", "exercise", 21),
                   name="1.3 Expanding Endomorphisms of the Circle")
        u4 = _node("1.4", "section", 21, name="1.4 Shifts and Subshifts")
        chapter = _node("1", "chapter", 15, u3, u4)
        probs = section_leak_problems(self.tmp, "1", 15, 25, chapter)
        self.assertEqual(len(probs), 1, "页顶真节头之下仍须报 LEAK-B")
        self.assertIn("LEAK-B", probs[0])
        self.assertIn("1.3.9", probs[0])

    # ---- 正向：Katok p92 形态（真节头行 OCR 吃掉章号，同文本命中只剩页眉）--
    def test_numbered_topband_title_fallback_when_body_head_lost_prefix(self):
        # 页眉 "2.4. Topological classification..."（y88，页顶）+ 真节头行被 OCR
        # 印成 "4. Topological classification..."（y714，章号 `2.` 被吃）。
        # `_numbered_heading_y` 只有页眉一处命中（y88）；`_numbered_band_yield`
        # 无 below 可取；此时数字锚必须退回标题词锚取带下 y714，否则整页正文
        # （含上一节 §2.3 的 Exercises）全部假 LEAK-B（该书普查 101 处的根因）。
        _write_pages(self.tmp, {
            92: [(88, "2.4. Topological classification of expanding maps on a circle"),
                 (88, "71"),
                 (148, "Exercises"),
                 (216, "2.3.1. Let f be a diffeomorphism of a compact manifold. Prove"),
                 (714, "4. Topological classification of expanding maps on a circle"),
                 (788, "a. Expanding maps in general can be defined similarly to contracting")],
        })
        u3 = _node("2.3", "section", 90,
                   _node("2.3.1", "exercise", 92),
                   name="2.3 Topological conjugacy, factors, and equivalence")
        u4 = _node("2.4", "section", 92,
                   name="2.4 Topological classification of expanding maps on a circle")
        chapter = _node("2", "chapter", 85, u3, u4)
        probs = section_leak_problems(self.tmp, "2", 85, 99, chapter)
        self.assertEqual(
            probs, [],
            "标题词锚取带下真头 y714 后，Exercise 2.3.1 不再越界")
        from check_section_leak import _section_anchor
        a = _section_anchor(self.tmp, "2", u4)
        self.assertEqual(a[1], 714.0)

    # ---- 正向：Katok p478 形态（真节头行 OCR 吞章号 + 拼写噪声）------------
    def test_numbered_topband_title_fallback_fuzzy_ocr_noise(self):
        # 页眉 "14.2.Fixed-point-free fows on the torus"（y92）+ 真节头被 OCR 印成
        # "2. Fixed-point-free fows on the torus"（y859，章号 `14.` 被吃、flows→fows）。
        # 精确/包含匹配全失灵，须靠归一化后序列相似度 ≥0.8 的带下模糊命中。
        _write_pages(self.tmp, {
            478: [(90, "457"),
                  (92, "14.2.Fixed-point-free fows on the torus"),
                  (369, "Exercises"),
                  (450, "14.1.1*.Showthatthere is a open dense set of vector fields"),
                  (859, "2. Fixed-point-free fows on the torus"),
                  (941, "a. Global transversals. According to the Poincare-Hopf Index Theorem")],
        })
        u1 = _node("14.1", "section", 470,
                   _node("14.1.1", "exercise", 478),
                   name="14.1 Poincare-Bendixson theory")
        u2 = _node("14.2", "section", 478,
                   name="14.2 Fixed-point-free flows on the torus")
        chapter = _node("14", "chapter", 460, u1, u2)
        probs = section_leak_problems(self.tmp, "14", 460, 485, chapter)
        self.assertEqual(probs, [], "模糊命中带下真头 y859 后，14.1.1 不再越界")
        from check_section_leak import _section_anchor
        a = _section_anchor(self.tmp, "14", u2)
        self.assertEqual(a[1], 859.0)

    # ---- 负向：条目锚点的页顶带守卫（Weibel 3.6-2 实测形态）---------------
    def test_item_anchor_running_head_contains_guard(self):
        # p99：页眉 "3.6 Universal Coefficient Theorems"(y197) 含条目探针前缀
        # "universal coefficient theorem…"（`_item_pos` 包含匹配截断 24 字符即
        # 命中、min-y 让页眉压过页底），真条目 "Universal Coefficient Theorem
        # for Homology 3.6.2 Let P be…" 印在 §3.6 内 y1617 → 不得报 LEAK-A。
        _write_pages(self.tmp, {
            99: [(197, "3.6 Universal Coefficient Theorems"),
                 (199, "87"),
                 (393, "3.6 Universal Coefficient Theorems"),
                 (604, "Theorem 3.6.1 (Kunneth formula) Let P be a chain complex"),
                 (1617, "Universal Coefficient Theorem for Homology 3.6.2 Let P be a chain complex of free abelian groups")],
        })
        u5 = _node("3.5", "section", 92, name="3.5 Derived Functors of the Inverse Limit")
        u6 = _node("3.6", "section", 99,
                   _node("3.6-1", "theorem", 99,
                         name="3.6-1 3.6.1 (Kunneth formula) Let P be a chain complex of flat right R-modules"),
                   _node("3.6-2", "theorem", 99,
                         name="3.6-2 Universal Coefficient Theorem for Homology"),
                   name="3.6 Universal Coefficient Theorems")
        chapter = _node("3", "chapter", 85, u5, u6)
        probs = section_leak_problems(self.tmp, "3", 85, 110, chapter)
        self.assertEqual(probs, [], "页眉 contains 命中让位给页底真身 → 3.6.2 在 §3.6 内，无泄漏")
        from check_section_leak import _node_anchor
        a = _node_anchor(self.tmp, "3", u6.sub_sec[1])
        self.assertEqual(a[1], 1617.0)

    # ---- 负向：页顶 contains 命中且带下无 body 证据 → 整条放弃（宁漏勿错）--
    def test_item_anchor_top_band_without_body_evidence_is_skipped(self):
        _write_pages(self.tmp, {
            40: [(60, "4.2 Rings of Small Dimension"),
                 (61, "iv"),
                 (300, "**4.2.1** Dimension of a finitely generated module is bounded.")],
        })
        u1 = _node("4.1", "section", 38, name="4.1 Dimensions")
        u2 = _node("4.2", "section", 40, name="4.2 Rings of Small Dimension")
        chapter = _node("4", "chapter", 30, u1, u2)
        probs = section_leak_problems(self.tmp, "4", 30, 48, chapter)
        self.assertEqual(probs, [], "页顶 contains 命中不可信且无带下证据 → 不报")

    # ---- 正向：LEAK-B 跨越下一子节节头（Lee §7.4 实测）--------------------
    def test_leak_b_across_next_subsection_heading(self):
        # p183：例7.30(y318) → Semidirect Products 节头(y553) → (7.10) 公式
        #       → Ex 7.31(y1030) → 例7.32(y1114) → 命题7.33(y1508)。
        # Ex 7.31 验证的 (7.10) 正是上方刚印的半直积公式 → 真属 U6。
        _write_pages(self.tmp, {
            176: [(400, "Group Actions and Equivariant Maps")],
            179: [(500, "Equivariant Maps")],
            183: [(318, "Example7.30(TheSpecialUnitaryGroup).ThegroupSU(n)is"),
                  (553, "Semidirect Products"),
                  (900, "we define a new Lie group N x H, called a semidirect product"),
                  (1030, "Exercise 7.31. Verify that (7.10) does indeed define a Lie group structure"),
                  (1114, "Example 7.32 (The Euclidean Group). If we consider Rn as a Lie group under addition"),
                  (1508, "Proposition 7.33 (Properties of Semidirect Products). Suppose N and H are Lie")],
            184: [(300, "Representations")],
        })
        u5 = _node("U5", "section", 179,
                   _node("例7.30", "example", 183),
                   _node("7.31", "exercise", 183),
                   _node("例7.32", "example", 183),
                   name="Equivariant Maps")
        u6 = _node("U6", "section", 183,
                   _node("命题7.33", "proposition", 183),
                   name="Semidirect Products")
        u7 = _node("U7", "section", 184, name="Representations")
        u4 = _node("U4", "section", 176, u5, u6, u7,
                   name="Group Actions and Equivariant Maps")
        chapter = _node("7", "chapter", 165, u4)
        probs = section_leak_problems(self.tmp, "7", 165, 188, chapter)
        self.assertEqual(len(probs), 2, "应报 Ex 7.31 与 例7.32 两条 LEAK-B")
        self.assertTrue(all("LEAK-B" in p for p in probs))
        self.assertTrue(any("7.31" in p for p in probs))
        self.assertTrue(all("U6" in p for p in probs), "建议归位目标应为 U6(Semidirect Products)")

    # ---- 负向：父节条目印在自己子节标题之后（合法形态）--------------------
    def test_parent_item_after_own_subsection_heading_is_legal(self):
        _write_pages(self.tmp, {
            176: [(400, "Group Actions and Equivariant Maps")],
            179: [(500, "Equivariant Maps")],
            183: [(318, "Example7.30(TheSpecialUnitaryGroup).ThegroupSU(n)is"),
                  (553, "Semidirect Products")],
        })
        u5 = _node("U5", "section", 179,
                   _node("例7.30", "example", 183), name="Equivariant Maps")
        u6 = _node("U6", "section", 183, name="Semidirect Products")
        u4 = _node("U4", "section", 176, u5, u6,
                   name="Group Actions and Equivariant Maps")
        chapter = _node("7", "chapter", 165, u4)
        probs = section_leak_problems(self.tmp, "7", 165, 188, chapter)
        self.assertEqual(probs, [],
                         "例7.30 印在 U5 节头之后、U6 节头之前，不得误报")

    # ---- 负向：条目在真节头之下（无泄漏）----------------------------------
    def test_item_below_real_heading_is_clean(self):
        _write_pages(self.tmp, {
            352: [(150, "Let $g$ be a Riemannian metric on M."),
                  (1200, "The Riemannian Distance Function")],
            353: [(300, "Proposition13.25(ParameterIndependenceofLength).Let(M,g)be")],
        })
        u4 = _node("U4", "section", 352,
                   _node("命题13.25", "proposition", 353),
                   name="The Riemannian Distance Function")
        chapter = _node("13", "chapter", 342, u4)
        probs = section_leak_problems(self.tmp, "13", 342, 363, chapter)
        self.assertEqual(probs, [])

    # ---- 正向：description 首块前缀锚定在节头之前 --------------------------
    def test_description_text_before_heading_is_flagged(self):
        remark = ("It is important to be aware that Corollary 6.11 is false if F is "
                  "merely assumed to be continuous.")
        _write_pages(self.tmp, {
            146: [(150, "Proof. In this case, each point of M is a critical point for F."),
                  (400, remark),
                  (900, "The Whitney Embedding Theorem")],
        })
        u2 = _node("U2", "section", 146,
                   _desc("D9", 146, remark),
                   name="The Whitney Embedding Theorem")
        chapter = _node("6", "chapter", 140, u2)
        probs = section_leak_problems(self.tmp, "6", 140, 164, chapter)
        self.assertEqual(len(probs), 1, "描述块印在节头之上应被锚定并报 LEAK-A")
        self.assertIn("D9", probs[0])
        self.assertIn("LEAK-A", probs[0])

    # ---- 负向：consolidated 节（章末集中习题块）整节豁免 --------------------
    def test_consolidated_section_children_exempt(self):
        _write_pages(self.tmp, {
            162: [(150, "Problems"),
                  (300, "6-1. Use Proposition 6.5 to give a simpler proof.")],
        })
        u = _node("U6", "section", 162,
                  _node("6-1", "problem", 162),
                  name="Problems", consolidated=True)
        chapter = _node("6", "chapter", 140, u)
        probs = section_leak_problems(self.tmp, "6", 140, 164, chapter)
        self.assertEqual(probs, [], "consolidated 节的子节点不参与泄漏判定")

    # ---- 负向：条目块 OCR 丢失（无证据）→ 跳过 ------------------------------
    def test_no_evidence_item_is_skipped(self):
        _write_pages(self.tmp, {
            352: [(1200, "The Riemannian Distance Function")],
        })
        u4 = _node("U4", "section", 352,
                   _node("推论13.30", "corollary", 352),
                   name="The Riemannian Distance Function")
        chapter = _node("13", "chapter", 342, u4)
        probs = section_leak_problems(self.tmp, "13", 342, 363, chapter)
        self.assertEqual(probs, [], "条目块在源页找不到（无证据）时不得凭空报泄漏")


if __name__ == "__main__":
    unittest.main()
