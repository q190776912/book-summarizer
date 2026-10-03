# -*- coding: utf-8 -*-
r"""B 层「契约习题节点键算已在账」判据回归（2026-10-02 Katok 264 行 EXTRA-ENTRY 根治）。

实测：`load_contract` 对 `exercise` / `problem` 直接 return，于是 EXTRACT 供水的
`ctx.items`（书真相集）**永不含**习题节点。md 照印面写的习题条头（Katok 每节后段成排的
`**练习 0.2.1**` / `**Exercise 0.2.1**`）因此不可能被 `_covered` 折掉，每一条都落进
`extra_entry` = 「md 有独立条头而契约无该条目」= 契约漏登记印面条目的**真信号**桶
（Katok 264 行、Introduction-to-Dynamical-Systems 383 行）。假信号把上一条根治
（Apostol 例1 分桶）的判读文案淹掉，故必须在源头堵住。

修法 = `_ext_norm`（EXTRA 覆盖集）并上 `_contract_exercise_keys(ext_dir, ch)`，即
`book_structure/ch{N}.json` 里 type=exercise/problem 的节点键。

负向守卫（本测试断言的四条，缺一即成「靠放宽判据洗掉真漏登记」）：
  1. 契约**没有**该键的条头（`例题 9.2.5`）必须照旧报 EXTRA-ENTRY；
  2. 契约文件读不到时行为**逐字节回到改前**（习题头仍报，判据不静默生效）；
  3. `truly_missing` / `mentioned_only` 不受本行影响（只进 `_ext_norm`，不进
     `extracted`）——consolidated 习题块按 writing-rules 不进总结，塞进书真相集会
     造出假的「整条漏写」；
  4. consolidated 节点不进覆盖集（`exercise_node_windows` 已按设计排除）。
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

from verify.script.base import VerifyManager  # noqa: E402
from verify.script.register_all import LAYER_REGISTRY  # noqa: E402
from verify_config import BookConfig, GroupConfig  # noqa: E402

MD = (
    "# 第9章\n\n"
    "## §9.1 三角范畴\n\n"
    "**定义 9.1.1** 三角的定义。\n\n"
    "**练习 9.1.3** 验证 (TR1)。\n\n"
    "**习题 9.1.4** 证明八面体公理推出 TR4。\n\n"
    "**例题 9.2.5** 契约里没有的条头（真漏登记形态）。\n\n"
)


def _node(key, type_, consolidated=False):
    n = {'key': key, 'type': type_, 'name': key, 'page_start': 100,
         'page_end': 100,
         'sub_sec': [{'type': 'text', 'text': '内容'}]}
    if consolidated:
        n['consolidated'] = True
    return n


class _Loader:
    """VerifyManager 只用 `config_for_chapter` / `manual_for_chapter` /
    `figure_index`（base.py），故此处按鸭子类型给最小实现。"""

    def __init__(self, cfg):
        self._cfg = cfg
        self.figure_index = []

    def config_for_chapter(self, ch):
        return self._cfg

    def manual_for_chapter(self, ch):
        return []


class _OnlyExtractB:
    def all_ordered(self):
        return [l for l in LAYER_REGISTRY.all_ordered() if l.code in ('EXTRACT', 'B')]

    def fixable_ordered(self):
        return []


class ContractExerciseCoverageTest(unittest.TestCase):
    def _run_b(self, with_contract=True):
        ext = tempfile.mkdtemp()
        if with_contract:
            d = os.path.join(ext, 'book_structure')
            os.makedirs(d, exist_ok=True)
            root = {'key': '9', 'type': 'chapter', 'sub_sec': [
                {'key': '9.1', 'type': 'section', 'sub_sec': [
                    _node('9.1.1', 'definition'),
                    _node('9.1.3', 'exercise'),
                    _node('9.1.4', 'problem'),
                    _node('9.1.5', 'exercise', consolidated=True),
                ]},
            ]}
            with open(os.path.join(d, 'ch9.json'), 'w', encoding='utf-8') as f:
                json.dump(root, f, ensure_ascii=False)
        md = os.path.join(ext, 'ch9.md')
        with open(md, 'w', encoding='utf-8') as f:
            f.write(MD)
        cfg = BookConfig(ordinal=[GroupConfig(type=3, name=['uncat'], scope=3)],
                         language='cn')
        mgr = VerifyManager(_OnlyExtractB(), _Loader(cfg))
        res = mgr.verify_one(9, 9, 9, md, ext)
        return res

    def test_contract_exercise_heads_leave_extra_entry(self):
        res = self._run_b(True)
        ee = [str(x) for x in (res.get('extra_entry') or [])]
        for k in ('练习9.1.3', '习题9.1.4', '9.1-3', '9.1-4'):
            self.assertNotIn(k, ee,
                             '契约登记为 exercise/problem 的条头不是孤儿：%s' % k)

    def test_unregistered_head_still_reported(self):
        """负向 1：契约里没有的条头必须照旧报出，否则就是放宽判据洗真信号。"""
        res = self._run_b(True)
        ee = [str(x) for x in (res.get('extra_entry') or [])]
        self.assertTrue(any('9.2-5' in x or '例题9.2.5' in x for x in ee),
                        '例题 9.2.5 契约无节点 -> 必须仍在 EXTRA-ENTRY，实得 %r' % ee)

    def test_no_contract_behaves_as_before(self):
        """负向 2：契约读不到 → 逐字节回到改前（习题头照旧报）。"""
        res = self._run_b(False)
        ee = [str(x) for x in (res.get('extra_entry') or [])]
        self.assertTrue(any('9.1-3' in x for x in ee),
                        '无契约时不得静默豁免，实得 %r' % ee)

    def test_coverage_line_moves_only_the_extra_bucket(self):
        """负向 3（同源隔离）：同一磁盘契约下**只**关掉 `_ext_norm` 并集这一步
        （把 `_contract_exercise_keys` 打成空集），其余供水逐字节相同。
        两侧必须只差在 EXTRA 桶：`truly_missing` / `mentioned_only` / `blocking`
        完全一致——证明本行没有把习题键塞进书真相集 `extracted`
        （consolidated 成堆块按 writing-rules 不进总结，进了就是造假的「整条漏写」）。"""
        import item_numbering_integrity as MOD
        base = self._run_b(True)
        orig = MOD._contract_exercise_keys
        MOD._contract_exercise_keys = lambda ext_dir, ch: set()
        try:
            disabled = self._run_b(True)
        finally:
            MOD._contract_exercise_keys = orig
        ee_on = set(str(x) for x in (base.get('extra_entry') or []))
        ee_off = set(str(x) for x in (disabled.get('extra_entry') or []))
        self.assertTrue(ee_off - ee_on,
                        '关掉并集后习题头必须回到 EXTRA-ENTRY（否则本测试没测到东西）')
        for k in sorted(ee_off - ee_on):
            self.assertTrue('9.1-3' in k or '9.1-4' in k or '练习' in k or '习题' in k,
                            '被本行豁免的键必须是习题键，实得 %r' % k)
        for key in ('truly_missing', 'mentioned_only'):
            self.assertEqual(sorted(str(x) for x in (base.get(key) or [])),
                             sorted(str(x) for x in (disabled.get(key) or [])), key)
        self.assertEqual(len(base.get('blocking') or []),
                         len(disabled.get('blocking') or []))
        # 其余报告桶逐字节不动
        for key in ('extra_mention',):
            self.assertEqual(sorted(str(x) for x in (base.get(key) or [])),
                             sorted(str(x) for x in (disabled.get(key) or [])), key)

    def test_consolidated_node_not_in_coverage(self):
        """负向 4：consolidated 习题块不进覆盖集（md 本就不写它，若在覆盖集里也无害，
        但键集必须与 `exercise_node_windows` 的排除口径一致）。"""
        from item_numbering_integrity import _contract_exercise_keys
        ext = tempfile.mkdtemp()
        d = os.path.join(ext, 'book_structure')
        os.makedirs(d, exist_ok=True)
        root = {'key': '9', 'type': 'chapter', 'sub_sec': [
            {'key': '9.1', 'type': 'section', 'sub_sec': [
                _node('9.1.3', 'exercise'),
                _node('9.1.5', 'exercise', consolidated=True),
            ]}]}
        with open(os.path.join(d, 'ch9.json'), 'w', encoding='utf-8') as f:
            json.dump(root, f, ensure_ascii=False)
        self.assertEqual(_contract_exercise_keys(ext, 9), {'9.1-3'})


if __name__ == '__main__':
    unittest.main()
