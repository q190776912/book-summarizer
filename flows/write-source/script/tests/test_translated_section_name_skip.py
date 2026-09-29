# -*- coding: utf-8 -*-
"""回归：译本 md 组**跳过 section 名核对**（check_sections=False），编号项仍两语核对。

事故（Arnold《Ordinary Differential Equations》EN→CN 全书 5 章，2026-09-29，
merge_translation 证据复核被假报硬拒）：结构契约的 section `name` 是**原书语言**
（`1.10 Example: Harvesting with a Relative Quota`），而中文 md 的小节标题按
译文 + 局部号印刷（`### 10. 例：按相对定额捕获`）。
`physical_evidence._missing_contract_names` 的候选全部来自原书语言标题
（整名归一 `110example…` / `_pm` 剥父号得 `10example…`）或父点号键
（`1.10` → `110`），这些串在中文标题里**永不连续**，于是译文组假报全书
81 个 section「不在位」，证据门拒绝 mark——写手被逼的出路仍是伪造/改标签两条，
都是坏的。英文源组用同源标题，全部命中（miss=0），所以此假阳性**只出现在译文组**。

根治 = `_merge_present_ok` 按「本组语言 == 契约源语言」决定 `check_sections`：
译文组跳过 `section` 名核对（其版块完整性已由 ``check_translate_parity`` 的
#1 单元 id/type/key/name/file 1:1 与 #4 节号一致机械保证，跳过不构成放宽），
**编号项**（定理 / 定义 …）两语继续核对——其数字条题渲染一致。默认 True 保持
历史逐字节行为，故 merge_source（只看源组）与本判据的既有语义零回归。
本测试同时锁死负向：译文组里真漏的编号项仍须报，源组 section 真缺仍须报。
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

from flows._flow_contract import physical_evidence as pe  # noqa: E402


def _contract():
    """一源语(EN)章：section `1.10 Example: Harvesting…` + theorem `1.10 定义…`。"""
    return {"key": "1", "type": "chapter", "name": "1 Phase Spaces",
            "sub_sec": [
                {"key": "1.10", "type": "section",
                 "name": "1.10 Example: Harvesting with a Relative Quota",
                 "text": [{"text": "intro body"}],
                 "sub_sec": [
                     {"key": "定理1.1", "type": "theorem",
                      "name": "定理 1.1 Harvesting equilibrium",
                      "text": [{"text": "body"}]}]}]}


# 中文译文组：小节标题为译文 + 局部号「10.」，条目数字号「1.1」两版一致渲染。
_CN_MD = pe._norm_text(
    "# 第1章 相空间\n\n## §10. 例：按相对定额捕获\n\n"
    "考察……\n\n**定理 1.1**：在 $c = 1/4$ 处存在唯一不稳定平衡。\n")

# 英文源组：小节标题为原书语言、条目同样在位。
_EN_MD = pe._norm_text(
    "# Chapter 1 Phase Spaces\n\n### 10. Example: Harvesting with a "
    "Relative Quota\n\n**Theorem 1.1**: there is a single unstable "
    "equilibrium.\n")


class TranslatedSectionSkipTest(unittest.TestCase):
    def test_cn_section_false_positive_without_skip(self):
        """复现假阳性：不跳过时，中文组会把在位的译文小节误报为缺。"""
        self.assertIn("1.10", pe._missing_contract_names(
            _contract(), _CN_MD, check_sections=True))

    def test_cn_section_skipped_is_not_reported(self):
        """修复：译文组跳过 section → `1.10` 不再被报。"""
        self.assertNotIn("1.10", pe._missing_contract_names(
            _contract(), _CN_MD, check_sections=False))

    def test_cn_item_still_checked_when_section_skipped(self):
        """编号项不受跳过影响：数字条题两语一致，本例中文已印 → 不报缺。"""
        self.assertEqual(pe._missing_contract_names(
            _contract(), _CN_MD, check_sections=False), [])

    def test_cn_genuinely_missing_item_still_reported_with_skip(self):
        """🔴 负向：译文组真漏的编号项，即便跳过 section 也照报。"""
        md = pe._norm_text("# 第1章\n## §10. 例：捕获\n（无定理条目的散文）\n")
        self.assertIn("定理1.1", pe._missing_contract_names(
            _contract(), md, check_sections=False))

    def test_source_group_section_still_enforced(self):
        """源组不跳过（默认 True）：英文 md 里缺该原书小节标题须照报。"""
        en_missing_sec = pe._norm_text(
            "# Chapter 1\n**Theorem 1.1**: equilibrium.\n")  # 无 10. Harvesting 标题
        self.assertIn("1.10", pe._missing_contract_names(
            _contract(), en_missing_sec, check_sections=True))

    def test_default_is_backward_compatible(self):
        """默认参数保持既有语义（等价 check_sections=True）。"""
        self.assertEqual(
            pe._missing_contract_names(_contract(), _EN_MD),
            pe._missing_contract_names(_contract(), _EN_MD, check_sections=True))
        self.assertEqual(
            pe._missing_contract_names(_contract(), _EN_MD), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
