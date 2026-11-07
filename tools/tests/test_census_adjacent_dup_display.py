r"""test_census_adjacent_dup_display.py — 「同一条 display 就近连印两遍」探测器的回归。

本工具**只报不拦**，所以它的可信度全靠档位边界被测试锁住。三次实测（2026-10-31 遍历论_孙文祥
ch6 的 D23 / D18 两处 + 跨 58 书基线）说明两档不可互换：

1. `SHAPE`（两份之间**只剩**空行 / `---` / `#` 标题 / 粗体条头）= 可点名的症状：
   「一条无主式子」紧跟着「同一条式子作为某条目的题面」；
2. `GAP`（行距 ≤ 20）**只作背景量**：合法复述（定理在证明末尾再写一遍、推导链里隔几句再现）
   跨书有 148 条，把它做成闸门会把正确交付判违规 → 必须测「中间有一句散文 ⇒ 只落 GAP、不落 SHAPE」；
3. 证明围栏（行首 `>`）里再写一遍 = 合法：**前后任一份**带 `>` 都不配 → 不得落 SHAPE。
   后一份单独判不可省：两块之间只剩一个空行时，围栏的 `>` 行根本不在「之间」窗口里；
4. `MIN_CORE` 拦掉 `$$x$$` 这类无判别力的短内核；
5. 多行 `$$…$$` 块的**结束行**必须算进配对基准，否则块自身的尾巴会被当成「两份之间的内容」
   而让 SHAPE 永远落空（静默失明，正是本档最坏的失效方式）。

known_true 控件（`test_control_backup_names_both_sites`）用**手术前**的交付备份件；
磁盘上没有该备份时跳过，但正式报告前须按 SKILL.md 的 `--control` 配方实跑一次。

Run with stdlib unittest:
    python tools/tests/test_census_adjacent_dup_display.py
"""
import io
import os
import sys
import unittest
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[2])
for _p in (_ROOT, os.path.join(_ROOT, "lib"), os.path.join(_ROOT, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

import census_adjacent_dup_display as cad

# 遍历论_孙文祥 第6章 手术前交付 L1679–L1691 的逐字形态（D23：description 节点持孤立式子，
# 紧邻的 引理6.6.2 单元又持同一句）
D23_SITE = (
    u"### §6.6.3 唯一的遍历测度支撑在唯一的不动点上\n"
    u"\n"
    u"$$\n"
    u"\\lim_{n\\to\\infty}\\frac{1}{n}r(P(n))=0.\n"
    u"$$\n"
    u"\n"
    u"---\n"
    u"\n"
    u"**引理6.6.2**：\n"
    u"\n"
    u"$$\n"
    u"\\lim_{n\\to\\infty}\\frac{1}{n}r(P(n))=0.\n"
    u"$$\n"
    u"\n"
    u"> **证明**：\n"
)
# 手术后的正确形态：孤立式子并入条目标题行，全交付只剩一份
D23_REPAIRED = (
    u"### §6.6.3 唯一的遍历测度支撑在唯一的不动点上\n"
    u"\n"
    u"**引理6.6.2**：\n"
    u"\n"
    u"$$\n"
    u"\\lim_{n\\to\\infty}\\frac{1}{n}r(P(n))=0.\n"
    u"$$\n"
    u"\n"
    u"> **证明**：\n"
)
CORE = u"\\lim_{n\\to\\infty}\\frac{1}{n}r(P(n))=0."


def _shape(text):
    return [h for h in cad.scan_text(text, u"x.md") if u"SHAPE" in h[5]]


class ShapeLeg(unittest.TestCase):
    def test_orphan_display_then_item_head_is_caught(self):
        hits = _shape(D23_SITE)
        self.assertEqual(len(hits), 1)
        label, l1, l2, d, core, legs = hits[0]
        self.assertEqual(core, CORE)
        self.assertEqual((l1, l2), (3, 11))          # 两份各自的块起始行
        self.assertIn(u"SHAPE", legs)

    def test_repaired_delivery_is_clean(self):
        self.assertEqual(_shape(D23_REPAIRED), [])

    def test_prose_between_is_gap_only(self):
        """🔴 判据核心：中间多一句**散文**就不是「无主式子紧跟条目题面」，只落背景档。

        跨 58 书 GAP≤20 有 148 条、绝大多数是合法复述；若这里也落 SHAPE，探测器就
        变成了批量噪音源（同一个错误在 merge_units 手修对齐闸上已经犯过一次）。
        """
        text = D23_SITE.replace(u"---\n", u"上式说明冗余度在极限意义下消失。\n\n---\n")
        hits = cad.scan_text(text, u"x.md")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0][5], [u"GAP"])

    def test_quoted_restatement_does_not_pair(self):
        """证明围栏（行首 `>`）里再写一遍 = 合法，不得与正文那份配对。"""
        text = (u"$$\n\\mu(\\partialcap_{i=0}^{n-1}T^{-i}A_{i})=0.\n$$\n"
                u"\n"
                u"> $$\n"
                u"> \\mu(\\partialcap_{i=0}^{n-1}T^{-i}A_{i})=0.\n"
                u"> $$\n")
        self.assertEqual(cad.scan_text(text, u"x.md"), [])

    def test_body_copy_after_a_quoted_one_pairs_with_the_body_one(self):
        """quoted 那份仍进 `seen`，但配对的「上一份」永远取最近的**正文**出现。"""
        blk = u"$$\nr(P(n))\\leq r(A_{i})+r(Q_{i}).\n$$\n"
        text = (blk + u"\n---\n\n" + u"> " + blk.replace(u"\n", u"\n> ") +
                u"\n---\n\n" + blk)
        hits = cad.scan_text(text, u"x.md")
        self.assertEqual([(h[1], h[5]) for h in hits], [(1, [u"GAP"])])
        # 若把围栏那份当成「上一份」，两份之间就只剩 `---` → 会虚报 SHAPE（此处必须不发生）
        self.assertEqual(_shape(text), [])

    def test_multiline_block_tail_is_not_treated_as_between(self):
        """静默失明回归：块跨多行时，配对基准必须是块**结束行**，不能是块起始行。

        起始行当基准会把块自身的 `aligned`/`$$` 尾巴算进「两份之间」，那些行永远不是
        脚手架 → SHAPE 永不成立，工具看似在跑实则全哑。
        """
        blk = (u"$$\n\\begin{aligned}\n\\frac{1}{n}r(P(n)) &\\leq \\frac{1}{|A_i|}(|A_{i-1}|+4i)\\\\\n"
               u"&\\to 0.\n\\end{aligned}\n$$\n")
        text = blk + u"\n---\n\n**引理6.6.2**：\n\n" + blk
        hits = _shape(text)
        self.assertEqual(len(hits), 1, u"多行 display 的 SHAPE 档失明了")

    def test_short_core_is_skipped(self):
        self.assertEqual(cad.scan_text(u"$$\nx\n$$\n\n---\n\n$$\nx\n$$\n", u"x.md"), [])
        self.assertLess(len(cad.dup_core(u"$$\nx\n$$")), cad.MIN_CORE)


class FillerPattern(unittest.TestCase):
    def test_allowed_scaffold_forms(self):
        for line in [u"", u"   ", u"---", u"### §6.6.3 标题", u"**引理6.6.2**：", u"**Example 3.1** "]:
            self.assertTrue(cad.only_scaffold(line), line)

    def test_real_content_forms_block_the_leg(self):
        for line in [u"> **证明**：", u"上式说明冗余度消失。", u"推论6.4.1 的结论为", u"$a+b=c$"]:
            self.assertFalse(cad.only_scaffold(line), line)

    def test_pattern_is_byte_locked(self):
        r"""收窄/放宽 `_FILLER` 都要重跑 --control 与全语料基线；此处钉住 2026-10-31 标定形。"""
        self.assertEqual(cad._FILLER.pattern,
                         u"^(?:\\s*$|-+|#{1,6}\\s.*|\\*\\*[^*]+\\*\\*[:：]?\\s*)$")


class BookScan(unittest.TestCase):
    """known_true 控件：两次手术**各自**的术前交付备份件必须被点名。

    快照顺序即预期差：`_bak_d23_dedup` 早于 D18 手术 → 两处都在；`_bak_d18_dedup` 晚于
    D23 修复 → 只剩 D18 一处。把两份快照都当控件跑，等于同时验证「抓得到」与
    「已修的不再抓」（否则一个永远全红的探测器也能过测）。
    """
    D18_CORE = u"h(T)=\\sup_{\\mu\\inE(X,T)}h_{\\mu}(T)."

    def _cores(self, bak_dir):
        ctl = _backup_delivery(bak_dir)
        if ctl is None:
            self.skipTest(u"手术前交付备份件不在盘（_extract/%s/*/）" % bak_dir)
        with io.open(ctl, encoding=u"utf-8", errors=u"replace") as f:
            text = f.read()
        return sorted(h[4] for h in _shape(text))

    def test_control_d23_snapshot_names_both_sites(self):
        self.assertEqual(self._cores(u"_bak_d23_dedup"),
                         sorted([self.D18_CORE, CORE]))

    def test_control_d18_snapshot_names_only_d18(self):
        """D23 已在该快照前修掉 → 探测器不再点名它；只剩 D18。"""
        self.assertEqual(self._cores(u"_bak_d18_dedup"), [self.D18_CORE])


def _backup_delivery(bak_dir):
    """定位手术前的交付备份件；不在盘时返回 None（控件测试自动跳过）。

    书名是中文，路径一律由出厂入口 `_book_dirs()` + 目录名枚举得到，绝不手敲 CJK；
    快照目录里同时躺着 `+` 展平的契约/manifest/单元备份件，交付是唯一不带 `+` 的 md。
    """
    for book in cad._book_dirs(u"D:/study/book"):
        root = Path(book) / u"_extract" / bak_dir
        if not root.is_dir():
            continue
        for snap in sorted(root.iterdir(), reverse=True):
            mds = [m for m in snap.glob(u"*.md") if u"+" not in m.name]
            if len(mds) == 1:
                return str(mds[0])
    return None


class TextBodyIsDiscriminating(unittest.TestCase):
    """🔴 本探测器**不许**删 `\\text{}` 体（2026-11-06 郑大钟 12 条假阳的根治）。

    缺陷形态：内核归一复用 `census_unit_delivery_coverage.block_core()`，它经
    `check_translate_parity._flatten_math` 删掉全部 `\\text{}` 散文体 —— 那对**跨语种**
    parity 是对的（源 `\\text{and}` 与译 `\\text{且}` 是同一条式子），对「同一份交付里
    同一条式子印了两遍」是错的：语种不变，中文就是判别内容。郑大钟《线性系统理论》
    实测 SHAPE 12 条全部因此塌成同一内核，逐条读下来零真阳性（下面这对就是原文）。
    """

    # 第7章_7.3_线性相关和线性无关.md L58–L64 的逐字形态：两条**互为否定**的等价关系
    ZDZ_PAIR = (
        u"设 $\\boldsymbol{Q}(s)$ 为一个 $n\\times n$ 方多项式矩阵，则：\n"
        u"\n"
        u"$$\n"
        u"\\boldsymbol{Q}(s)\\text{ 非奇异}\\iff \\boldsymbol{Q}(s)\\text{ 的行/列多项式向量为线性无关}\n"
        u"$$\n"
        u"\n"
        u"$$\n"
        u"\\boldsymbol{Q}(s)\\text{ 奇异}\\iff \\boldsymbol{Q}(s)\\text{ 的行/列多项式向量为线性相关}\n"
        u"$$\n"
    )
    # 真重复（含 `\\text{}` 且逐字相同）：仍必须点名，否则本类测试等于把腿锯了
    TRUE_DUP = (
        u"**定理7.3.1**：\n"
        u"\n"
        u"$$\n"
        u"\\boldsymbol{Q}(s)\\text{ 非奇异}\\iff \\boldsymbol{Q}(s)\\text{ 的行/列多项式向量为线性无关}\n"
        u"$$\n"
        u"\n"
        u"---\n"
        u"\n"
        u"$$\n"
        u"\\boldsymbol{Q}(s)\\text{ 非奇异}\\iff \\boldsymbol{Q}(s)\\text{ 的行/列多项式向量为线性无关}\n"
        u"$$\n"
    )

    def test_cjk_text_bodies_keep_the_pair_apart(self):
        self.assertEqual(cad.scan_text(self.ZDZ_PAIR, u"x.md"), [])

    def test_identical_block_still_pairs(self):
        hits = _shape(self.TRUE_DUP)
        self.assertEqual(len(hits), 1)
        self.assertIn(u"\\text{非奇异}", hits[0][4])   # 内核里中文可见 = 没被删体（空白已折叠）

    def test_core_function_does_not_strip_text(self):
        """直接锁 `dup_core` 与 parity 口径的分叉点（防「顺手换回公共函数」）。"""
        blk = u"$$\nA\\text{ 甲}=B\n$$"
        self.assertIn(u"甲", cad.dup_core(blk))
        from census_unit_delivery_coverage import block_core
        self.assertNotIn(u"甲", block_core(blk))       # 跨语种口径照旧删体，两者不该合流


if __name__ == "__main__":
    unittest.main(verbosity=2)
