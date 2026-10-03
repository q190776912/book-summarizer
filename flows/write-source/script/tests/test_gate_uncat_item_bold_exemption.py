"""H1 粗体标签闸的 `uncat` 豁免：判据须与 B/M 层 + 合并证据闸同源（微分遍历论实测 2026-10-02）。

缺陷现场：`split_draft_units` 的 else 分支把**所有**非 description/proof/exercise
节点（含配置分组表没认领的 `uncat` 兜底族）发成 `item` 单元，而 H1 对 `item` 无条件
要求粗体标签。契约里既无编号条头、印面也只是句中散文的节点因此**只能靠造一个原书没有
的粗体条头过闸**（闸逼代理编造 = 闸门 bug）。实测两例，内部键随假头落进交付物：

  ch4 单元 `**4.5-5 回顾注 4.5.5 的记号**：` —— 印面 p117 作「…对于这个 δ>0，
       回顾注 4.5.5 的记号 r_n(x,δ,f)=sup{…} 和下极限 … 有限，μ-a.e.」，是
       跨节回指的句中散文；真·注 4.5.5 是同键的另一个节点（另一单元）。
  ch6 单元 `**6.5-4**：证明引理6.5.4的一般情形…` —— 印面 p184 是 §6.7 习题 5，
       题面已在该章习题单元逐字在位（抽取器把题号 `5.` 当条头、题面当证明）。

B/M 层从一开始就把 uncat 排除在「须成条目」之外
（`item_numbering_integrity.extracted_raw = {… if it.get('label') != 'uncat'}`），
`_flow_contract` 的合并证据闸同一豁免（见 test_gate_uncat_md_entry_exemption.py），
`structure_io.read_structure_items` 的 `label` 正是 `TYPE_TO_LABEL.get(n.type, 'uncat')`
—— 同一个 uncat。本闸补齐同一判据：`node_type == "uncat"` 时免「必须有粗体标签」。

负向（必须仍然成立，否则豁免无意义）：
  * 真·编号项（theorem/definition…）无粗体标签照旧打回；
  * uncat 单元仍受其余各项约束（空正文闸 / 公式闭合 / KaTeX / 契约 tag 对账）。

Runs under stdlib unittest:
  python flows/write-source/script/tests/test_gate_uncat_item_bold_exemption.py
"""
import sys
import unittest
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[4])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
import lib.boot  # noqa: E402
lib.boot.setup()

import check_unit_quality as cuq  # noqa: E402

BOLD_MISSING = "缺粗体标签"
PROSE = ("回顾注 4.5.5 的记号\n\n$$\nr _ { n } ( x , \\delta , f ) = \\sup \\{ r > 0 \\}\n$$\n\n"
         "和下极限 $\\liminf$ 有限，$\\mu$-a.e. $x \\in M$．\n")


class UncatItemExempted(unittest.TestCase):
    def test_uncat_item_without_bold_head_passes(self):
        ok, probs = cuq.check_body("item", "4.5-5 回顾注 4.5.5 的记号", PROSE,
                                   node_type="uncat")
        self.assertFalse([p for p in probs if BOLD_MISSING in p], probs)

    def test_uncat_node_type_from_manifest_ntype(self):
        # gate_units 传 manifest `ntype`；uncat 节点的 ntype 即 "uncat"
        ok, probs = cuq.check_body("item", "6.5-4", "证明引理 6.5.4 的一般情形．\n",
                                   node_type="uncat")
        self.assertFalse([p for p in probs if BOLD_MISSING in p], probs)


class GenuineItemsStillRequired(unittest.TestCase):
    def test_theorem_item_without_bold_head_still_fails(self):
        ok, probs = cuq.check_body("item", "2.2-2 引理", PROSE, node_type="lemma")
        self.assertTrue([p for p in probs if BOLD_MISSING in p], probs)
        self.assertFalse(ok)

    def test_missing_node_type_defaults_to_strict(self):
        # 老 manifest 无 ntype → None → 行为照旧（保守，不放宽）
        ok, probs = cuq.check_body("item", "定理 3", PROSE)
        self.assertTrue([p for p in probs if BOLD_MISSING in p], probs)

    def test_uncat_exempt_only_the_bold_rule(self):
        # 裸命令（未走 KaTeX）在 uncat 单元照样打回——豁免不吃其它判据
        ok, probs = cuq.check_body("item", "4.5-5", "取 \\sup 与 \\liminf 的记号。\n",
                                   node_type="uncat")
        self.assertFalse(ok, probs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
