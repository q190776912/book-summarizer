# -*- coding: utf-8 -*-
r"""B 层 EXTRA-ENTRY 桶 2026-10-04 三项收窄的判据回归（Iwaniec–Kowalski 实测）。

1. 题集条头桶豁免：节末 `**练习1**`（契约无节点、单元体内内容）不再落
   extra_entry——「register it」救济在数据侧无落点（ctx.items 只读契约）。
2. 句中加粗降级：`…下述 **命题19.5**：…` 的行内强调不是独立条头。
3. 字母序标条头（`**定义A.1**`）在数字体例书不判（与 Q 层 LETTER-LED 同哲学）。
4. 题集键分隔符同口径归一：契约 `问题7-19` ↔ md `问题7.19` 覆盖。
负向守卫：契约无节点的**普通**条头（`例题9.2.5`）必须照旧报出。
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
from item_numbering_integrity import _ex_canon_key  # noqa: E402

MD = (
    "# 第7章\n\n"
    "## §7.1 双线性型\n\n"
    "**定理7.1** 内容。\n\n"
    "**练习1** 证明定理7.1。\n\n"
    "**例题7.2.5** 契约里没有的普通条头（真漏登记形态）。\n\n"
    "对特殊的系数，上式即给出下述 **命题19.5**：对任意 $X$ 有界。\n\n"
    "## §7.2 附录\n\n"
    "**定义A.1**。设 $f$ 是整函数。\n\n"
)


def _node(key, type_):
    return {'key': key, 'type': type_, 'name': key, 'page_start': 100,
            'page_end': 100,
            'sub_sec': [{'type': 'text', 'text': '内容'}]}


class _Loader:
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


class ExtraBucketRefinementTest(unittest.TestCase):
    def _run(self, contract=None):
        ext = tempfile.mkdtemp()
        if contract is not None:
            d = os.path.join(ext, 'book_structure')
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, 'ch7.json'), 'w', encoding='utf-8') as f:
                json.dump(contract, f, ensure_ascii=False)
        md = os.path.join(ext, 'ch7.md')
        with open(md, 'w', encoding='utf-8') as f:
            f.write(MD)
        cfg = BookConfig(ordinal=[GroupConfig(type=3, name=['uncat'], scope=3)],
                         language='cn')
        mgr = VerifyManager(_OnlyExtractB(), _Loader(cfg))
        return mgr.verify_one(7, 7, 7, md, ext)

    def test_section_exercise_head_leaves_extra_entry(self):
        res = self._run()
        ee = [str(x) for x in (res.get('extra_entry') or [])]
        self.assertFalse(any('练习1' in x for x in ee),
                         '节末题集条头不得报 EXTRA-ENTRY，实得 %r' % ee)

    def test_inline_bold_leaves_extra_entry(self):
        res = self._run()
        ee = [str(x) for x in (res.get('extra_entry') or [])]
        self.assertFalse(any('19.5' in x for x in ee),
                         '句中加粗不是独立条头，实得 %r' % ee)

    def test_letter_led_head_leaves_extra_entry(self):
        res = self._run()
        ee = [str(x) for x in (res.get('extra_entry') or [])]
        self.assertFalse(any('A.1' in x for x in ee),
                         '字母序标条头在数字体例书不判，实得 %r' % ee)

    def test_genuine_orphan_still_reported(self):
        """负向：契约无节点的普通条头必须照旧报出（不得被豁免洗掉）。"""
        res = self._run()
        ee = [str(x) for x in (res.get('extra_entry') or [])]
        self.assertTrue(any('7.2-5' in x or '例题7.2.5' in x for x in ee),
                        '例题7.2.5 必须仍在 EXTRA-ENTRY，实得 %r' % ee)

    def test_registered_problem_key_covered_via_canon(self):
        """契约登记 `问题7.19`（key=7-19 形），md 条头 `问题7.19` → 覆盖。"""
        contract = {'key': '7', 'type': 'chapter', 'sub_sec': [
            {'key': '7.1', 'type': 'section', 'sub_sec': [
                _node('7.1', 'definition'),
                {'key': '7-19', 'type': 'problem', 'name': '问题7.19',
                 'page_start': 100, 'page_end': 100,
                 'sub_sec': [{'type': 'text', 'text': '题面'}]},
            ]}]}
        md = MD.replace('**例题7.2.5** 契约里没有的普通条头（真漏登记形态）。\n\n', '')
        ext = tempfile.mkdtemp()
        d = os.path.join(ext, 'book_structure')
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, 'ch7.json'), 'w', encoding='utf-8') as f:
            json.dump(contract, f, ensure_ascii=False)
        p = os.path.join(ext, 'ch7.md')
        with open(p, 'w', encoding='utf-8') as f:
            f.write(md)
        cfg = BookConfig(ordinal=[GroupConfig(type=3, name=['uncat'], scope=3)],
                         language='cn')
        res = VerifyManager(_OnlyExtractB(), _Loader(cfg)).verify_one(7, 7, 7, p, ext)
        ee = [str(x) for x in (res.get('extra_entry') or [])]
        self.assertFalse(any('7.19' in x for x in ee),
                         '契约已登记的章末问题不得报 EXTRA-ENTRY，实得 %r' % ee)


class ExCanonKeyTest(unittest.TestCase):
    def test_both_forms_collide(self):
        self.assertEqual(_ex_canon_key('问题7.19'), _ex_canon_key('问题7-19'))
        self.assertEqual(_ex_canon_key('Problem 7-19'), '7.19')
        self.assertEqual(_ex_canon_key('练习1'), '1')

    def test_distinct_keys_stay_distinct(self):
        self.assertNotEqual(_ex_canon_key('问题7.19'), _ex_canon_key('问题7.25'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
