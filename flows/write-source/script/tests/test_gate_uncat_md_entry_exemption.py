"""合并证据闸的 `uncat` 豁免：判据须与 B/M 层同源（Arnold 附录K 系91 实测 2026-09-29）。

缺陷现场：`merge_source` 证据复核报
    1 组 md 相对结构契约漏骨架节/编号项: appendixK [cn] 缺 1 项（如 ['系91']）
而 `系91` 是 OCR 粘连幻影——印面 p349 作「…取一个坐标**系 $q_1,\cdots,q_n$.** 令
$p_1,\cdots,p_n$ 为余切丛的纤维中的相应坐标」，抽取器把「系」（“坐标系”的尾字）+
误读成 `91` 的 `q_1` 当成「系N」（推论）条头。该节点 `type == "uncat"`（配置分组表
没认领的号一律落兜底族），md 里当然没有、也**不该有**这个条头。

判据不一致：B/M 层从一开始就把 uncat 排除在「须成条目」之外
（`item_numbering_integrity.extracted_raw = {… if it.get('label') != 'uncat'}`，
理由写在代码里：图/表这类 uncat 号按写作规则**只在散文里引用**，不作 `**…**` 条头），
而 `structure_io.read_structure_items` 的 `label` 正是
`TYPE_TO_LABEL.get(n.type, 'uncat')` —— 同一个 uncat。合并证据闸不认这一豁免，
等于**要求 md 凭空造一个原书不存在的条目**（闸逼代理编造 = 闸门 bug）。

根治 = 本闸与 B/M 层共用同一豁免（`t in (…, "uncat")`）。内容在位仍由覆盖闸⑩
（契约 ↔ manifest 双向对账）与内容完整性闸门保证，本处只免「条头必须出现」一项。

负向（必须仍然成立，否则豁免无意义）：契约里真·编号项（定理/定义）在 md 缺失时
照旧报缺——豁免只吃 uncat 一族，不吞真内容丢失。

Runs under stdlib unittest:
  python flows/write-source/script/tests/test_gate_uncat_md_entry_exemption.py
"""
import os
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

from flows._flow_contract import physical_evidence  # noqa: E402


def _contract(*nodes):
    return {"key": "K", "type": "chapter", "name": "附录K 短波渐近",
            "sub_sec": [dict(n) for n in nodes]}


def _miss(nodes, md):
    return physical_evidence._missing_contract_names(
        _contract(*nodes), physical_evidence._norm_text(md))


class UncatExempted(unittest.TestCase):
    NODE_UNCAT = {"key": "系91", "type": "uncat",
                  "name": '系91 ·"：，9n．令p1,···,Pn为余切丛的纤维中的相应坐标',
                  "page_start": 364, "page_end": 364, "sub_sec": []}

    def test_uncat_node_does_not_demand_an_md_entry(self):
        # 现场：md 里只有散文（坐标系 q_1,…,q_n），没有任何 `**系91**` 条头。
        md = ("## §B 莫尔斯指数和马斯洛夫指数\n\n"
              "考虑拉格朗日流形上的某简单奇点。在此点取坐标系 $q_1,\\cdots,q_n$。"
              "令 $p_1,\\cdots,p_n$ 为余切丛纤维中的相应坐标。\n")
        self.assertEqual(_miss([self.NODE_UNCAT], md), [])

    def test_uncat_alias_family_also_exempted(self):
        # 图表题号同属 uncat 兜底族（B 层注释里的原始动机）。
        for k in ("图12", "Table 3"):
            with self.subTest(key=k):
                node = {"key": k, "type": "uncat", "name": k + " 说明文字",
                        "page_start": 10, "page_end": 10, "sub_sec": []}
                self.assertEqual(_miss([node], "正文里提到该图，但无条头。\n"), [])


class GenuineItemsStillRequired(unittest.TestCase):
    def test_real_theorem_absent_from_md_still_reported(self):
        node = {"key": "定理1", "type": "theorem", "name": "定理1 存在唯一解",
                "page_start": 5, "page_end": 6, "sub_sec": []}
        self.assertEqual(_miss([node], "## §1 引言\n\n只有一段散文。\n"), ["定理1"])

    def test_mixed_contract_reports_only_the_genuine_gap(self):
        uncat = self.NODE = {"key": "系91", "type": "uncat", "name": "系91，…",
                             "page_start": 364, "page_end": 364, "sub_sec": []}
        th = {"key": "定理2", "type": "theorem", "name": "定理2 指数定理",
              "page_start": 365, "page_end": 365, "sub_sec": []}
        md = "## §B 莫尔斯指数和马斯洛夫指数\n\n坐标系 $q_1,\\cdots,q_n$ 下的讨论。\n"
        self.assertEqual(_miss([uncat, th], md), ["定理2"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
