# -*- coding: utf-8 -*-
r"""B 层「字母章位键的标签无关归一」判据回归（2026-10-02 Katok 附录 A 根治）。

实测（Katok《Modern Theory》附录 A，`_extract/_probe_appendix_keys.py`）：契约节点键
是 **裸字母章位** `A.1-1`（`book_structure/appendixA.json` 里 `key='A.2-1'`），
EXTRACT 供水时给它们冠上标签词 → `extracted` 侧是 `定义A.2-1`；而 md 侧同一实体
可能写成 **裸号条头** `**A.2.1**`（键 `A.2-1`）或 **另一个标签词** `**命题 A.1.2**`
（键 `命题A.1-2`，契约把它登记成 definition）。`_norm_path` 的正则
`^([^\d]+)(\d+)\.(\d+)\.(\d+)$` 要求**三个纯数字分量**，带字母章位的键一概不折，
于是两侧同形不同标签 → 同一实体在**两个方向同时报错**：

    truly_missing = [定义A.1-2, 定义A.2-1, 定义A.2-2]      # 书有而「md 无」
    extra_entry   = [命题A.1-2, A.2-1, A.2-2, 定义A.2-9]  # md 有而「契约无」

后果不是难看：`truly_missing` 是**阻断侧**（整条漏写），`extra_entry` 是「契约漏登记
印面条目」的判读通道，同一条附录被同时报成「漏写」和「孤儿条头」= 两侧信号一起失效
（Katok 附录 A 实测 13 键 × cn/en = 26 行 EXTRA-ENTRY）。

修法 = 新增 `_norm_path_labelfree`（先走 `_norm_path`，再按 `^(label?)(L).<sec>[.-]<item>$`
剥掉字母章位键的标签词），并只用于 A 部分的四处存在性比较（`_ext_norm` / `_all_norm` /
`truly_missing` / `_covered`）。

🔴 单调性 = 本函数是函数且**两侧同折**（`k1 == k2 ⇒ f(k1) == f(k2)`）：原本匹配的照旧
匹配，只会多匹配，不会新造 `truly_missing`，也不会新造 EXTRA。代价与既有 `_norm_path`
完全同源：同一 `A.2-1` 路径下「定义 vs 命题」的**类型分歧**不再由 EXTRA 桶暴露
（标签对账另有 `check_label_consistency` / `label_warns` 与闸门⑩）。

`_mention_num_regex`（提及域判据）仍走 `_norm_path` = 字母键一律不判、照旧报，
本折**不得**顺带把字母形态的提及扫进豁免桶。
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
import lib.boot as _boot  # noqa: E402
_boot.setup()

import item_numbering_integrity as MOD  # noqa: E402
from item_numbering_integrity import _norm_path, _norm_path_labelfree  # noqa: E402
from verify.script.base import VerifyManager  # noqa: E402
from verify.script.register_all import LAYER_REGISTRY  # noqa: E402
from verify_config import BookConfig, GroupConfig  # noqa: E402

MD = (
    "# 附录A\n\n"
    "## §A.1 拓扑\n\n"
    "**命题 A.1.2** 紧集在 Hausdorff 空间中闭。\n\n"
    "**定义 A.1.3** 序列的收敛性。\n\n"
    "## §A.2 拓扑线性空间\n\n"
    "**A.2.1** 拓扑线性空间的定义。\n\n"
    "**A.2.2** 范子的定义。\n\n"
    "**定义 A.2.9** 契约里没有的条目。\n\n"
)


class _Loader:
    def __init__(self, cfg):
        self._cfg = cfg
        self.figure_index = []

    def config_for_chapter(self, ch):
        return self._cfg

    def manual_for_chapter(self, ch):
        return []


class _Reg:
    def all_ordered(self):
        return [l for l in LAYER_REGISTRY.all_ordered() if l.code in ('EXTRACT', 'B')]

    def fixable_ordered(self):
        return []


def _node(key, name):
    return {'key': key, 'type': 'definition', 'name': name, 'consolidated': False,
            'page_start': 700, 'page_end': 700,
            'sub_sec': [{'type': 'text', 'text': '内容'}]}


def _contract_root():
    return {'key': 'A', 'type': 'chapter', 'name': 'A Background',
            'consolidated': False, 'page_start': 700, 'page_end': 760,
            'sub_sec': [
                {'key': 'A.1', 'type': 'section', 'name': 'A.1 Basic topology',
                 'consolidated': False, 'page_start': 700, 'page_end': 730,
                 'sub_sec': [_node('A.1-2', 'A.1-2 A.1.2. closed'),
                             _node('A.1-3', 'A.1-3 A.1.3. conv')]},
                {'key': 'A.2', 'type': 'section', 'name': 'A.2 Linear spaces',
                 'consolidated': False, 'page_start': 731, 'page_end': 760,
                 'sub_sec': [_node('A.2-1', 'A.2-1 A.2.1. tvs'),
                             _node('A.2-2', 'A.2-2 A.2.2. norm')]},
            ]}


def _run_b(cfg):
    ext = tempfile.mkdtemp()
    d = os.path.join(ext, 'book_structure')
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, 'appendixA.json'), 'w', encoding='utf-8') as f:
        json.dump(_contract_root(), f, ensure_ascii=False)
    md = os.path.join(ext, 'appendixA.md')
    with open(md, 'w', encoding='utf-8') as f:
        f.write(MD)
    mgr = VerifyManager(_Reg(), _Loader(cfg))
    return mgr.verify_one('A', 700, 760, md, ext)


CFG = BookConfig(ordinal=[GroupConfig(type=13, name=['uncat'], scope=3)],
                 language='cn')


def _sorted(res, key):
    return sorted(str(x) for x in (res.get(key) or []))


class TestLetterSlotFoldingPure(unittest.TestCase):
    """归一函数本体：只剥字母章位键的标签词，其余形态字节不变。"""

    def test_letter_slot_forms_fold(self):
        for k, want in (('定义A.2-1', 'A.2-1'),
                        ('A.2.1', 'A.2-1'),
                        ('命题A.1-2', 'A.1-2'),
                        ('PropositionA.1.2', 'A.1-2'),
                        ('Theorem B.7-6', 'B.7-6')):
            self.assertEqual(_norm_path_labelfree(k), want, k)

    def test_numeric_three_level_unchanged(self):
        """纯数字三段号 = 既有 `_norm_path` 行为，逐字节不变（零回归）。"""
        for k in ('定义1.1.1', 'Theorem1.1.1', '性质6.2.1', '1.1-1', '3.1-2'):
            self.assertEqual(_norm_path_labelfree(k), _norm_path(k), k)

    def test_negative_shapes_not_folded(self):
        """负向守卫：没有「字母 + 分隔符 + 两段数字」形态的一律不动。"""
        for k in ('Fig1.2-3',            # 字母后不是分隔符
                  'Corollary5.1-2',      # 首分量是数字，不是字母章位
                  '性质1', '定理A.1',      # 缺 item 分量
                  'A.2', 'appendixA', '10.2-3'):
            self.assertEqual(_norm_path_labelfree(k), k, k)

    def test_distinct_letters_and_sections_stay_distinct(self):
        self.assertNotEqual(_norm_path_labelfree('定义A.2-1'),
                            _norm_path_labelfree('定义B.2-1'))
        self.assertNotEqual(_norm_path_labelfree('定义A.2-1'),
                            _norm_path_labelfree('定义A.3-1'))
        self.assertNotEqual(_norm_path_labelfree('定义A.2-1'),
                            _norm_path_labelfree('定义A.2-10'))

    def test_idempotent(self):
        for k in ('定义A.2-1', 'A.2.1', 'PropositionA.1.2', '定义1.1.1',
                  'Fig1.2-3', '性质1', 'A.2'):
            self.assertEqual(_norm_path_labelfree(_norm_path_labelfree(k)),
                             _norm_path_labelfree(k), k)

    def test_mention_domain_judgement_still_skips_letter_keys(self):
        """提及域判据（tag/figref/eqref 豁免）不得因本折顺带扫掉字母键。"""
        from item_numbering_integrity import _mention_num_regex
        self.assertIsNone(_mention_num_regex('定义A.2-1'))
        self.assertIsNotNone(_mention_num_regex('定义1.2.3'))


class TestLetterSlotAPart(unittest.TestCase):
    """A 部分端到端：同一实体不再两侧同时报错；真漏登记照旧报。"""

    def test_folded_side_reports_only_the_real_orphan(self):
        res = _run_b(CFG)
        self.assertEqual(_sorted(res, 'truly_missing'), [],
                         '契约条目都在 md 里，不该报「整条漏写」')
        ee = _sorted(res, 'extra_entry')
        self.assertTrue(any('A.2-9' in x for x in ee),
                        '契约无节点的 `定义 A.2.9` 必须仍在 EXTRA-ENTRY：%r' % ee)
        for gone in ('A.2-1', 'A.2-2', 'A.1-2', '命题A.1-2'):
            self.assertFalse(any(x.startswith(gone) or x.endswith(gone) for x in ee),
                             '已登记实体不应算孤儿条头：%r in %r' % (gone, ee))
        self.assertEqual(len(res.get('blocking') or []), 0)

    def test_without_fold_the_same_items_error_on_both_sides(self):
        """隔离证明：关掉本折 = 同一实体在 truly_missing 与 extra_entry 同时出现。"""
        orig = MOD._norm_path_labelfree
        MOD._norm_path_labelfree = _norm_path
        try:
            res = _run_b(CFG)
        finally:
            MOD._norm_path_labelfree = orig
        tm = _sorted(res, 'truly_missing')
        ee = _sorted(res, 'extra_entry')
        self.assertTrue(tm, '改前必须报 truly_missing（否则本测试没测到东西）')
        self.assertTrue(any('A.2-1' in x for x in tm), tm)
        self.assertTrue(any(x == 'A.2-1' for x in ee), ee)
        # 关掉后 A.2-9 依旧在报（本折不该影响真漏登记的可见性）
        self.assertTrue(any('A.2-9' in x for x in ee), ee)


if __name__ == '__main__':
    unittest.main()
