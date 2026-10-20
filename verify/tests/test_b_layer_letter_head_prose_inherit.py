# -*- coding: utf-8 -*-
r"""B 层 EXTRA-ENTRY 2026-10-20 收窄：**纯字母条头 · 未宣告类型**。

Rice《Mathematical Statistics and Data Analysis》实测：全书条目为字母序标
（THEOREM A / PROPERTY A–D，逐章重起），config 只宣告 Figure 计数器，抽取器按
体例散文继承、契约不开槽。此时纯字母条头（`**定理 A**`）报 EXTRA-ENTRY 无救济
落点（register 反而触发闸⑩），应与 `_untyped_single_mention` 同哲学降级不判。

三道守卫：
1. 只吃纯字母键；数字号形（`定理7.1`）照报。
2. 按标签门控：config 宣告了定理计数器时 `定理 A` 照报。
3. 词表不闭合（uncat 兜底）→ 整支关闭，照报。
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
from item_numbering_integrity import _letter_head_label  # noqa: E402

MD = (
    "# 第7章\n\n"
    "## §7.1 双线性型\n\n"
    "**定理A** 字母序标内容。\n\n"
    "**定理7.1** 数字号条头（类型未宣告也不得豁免）。\n\n"
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


class LetterHeadProseInheritTest(unittest.TestCase):
    def _run(self, cfg, contract=None):
        ext = tempfile.mkdtemp()
        if contract is not None:
            d = os.path.join(ext, 'book_structure')
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, 'ch7.json'), 'w', encoding='utf-8') as f:
                json.dump(contract, f, ensure_ascii=False)
        md = os.path.join(ext, 'ch7.md')
        with open(md, 'w', encoding='utf-8') as f:
            f.write(MD)
        mgr = VerifyManager(_OnlyExtractB(), _Loader(cfg))
        return mgr.verify_one(7, 7, 7, md, ext)

    @staticmethod
    def _figure_only():
        return BookConfig(
            ordinal=[GroupConfig(type=2, name=['Figure', 'Fig'], scope=2)],
            language='en')

    @staticmethod
    def _with_theorem_counter():
        return BookConfig(
            ordinal=[GroupConfig(type=2, name=['Figure'], scope=2),
                     GroupConfig(type=2, name=['Theorem'], scope=2)],
            language='en')

    def test_pure_letter_head_untracked_type_is_suppressed(self):
        res = self._run(self._figure_only())
        ee = [str(x) for x in (res.get('extra_entry') or [])]
        self.assertFalse(any(_letter_head_label(k) for k in ee),
                         '未宣告类型的纯字母条头应降级不判，实得 %r' % ee)

    def test_numeric_head_still_reported(self):
        res = self._run(self._figure_only())
        ee = [str(x) for x in (res.get('extra_entry') or [])]
        self.assertTrue(any('7.1' in x or '7-1' in x for x in ee),
                        '数字号条头不得借未宣告类型豁免，实得 %r' % ee)

    def test_declared_counter_keeps_letter_head(self):
        res = self._run(self._with_theorem_counter())
        ee = [str(x) for x in (res.get('extra_entry') or [])]
        self.assertTrue(any(_letter_head_label(k) == '定理' for k in ee),
                        'config 已宣告定理计数器时字母条头必须照报，实得 %r' % ee)

    def test_uncat_vocab_fail_closed(self):
        cfg = BookConfig(
            ordinal=[GroupConfig(type=2, name=['uncat'], scope=2)],
            language='en')
        res = self._run(cfg)
        ee = [str(x) for x in (res.get('extra_entry') or [])]
        self.assertTrue(any(_letter_head_label(k) == '定理' for k in ee),
                        'uncat 兜底时词表不闭合，纯字母条头必须照报，实得 %r' % ee)

    def test_registered_letter_head_is_covered_not_extra(self):
        contract = {'key': '7', 'type': 'chapter', 'sub_sec': [
            {'key': '7.1', 'type': 'section', 'sub_sec': [
                _node('定理 A', 'theorem'),
            ]},
        ]}
        res = self._run(self._with_theorem_counter(), contract=contract)
        ee = [str(x) for x in (res.get('extra_entry') or [])]
        self.assertFalse(any(_letter_head_label(k) == '定理' for k in ee),
                         '契约已登记的字母条头不得报 EXTRA-ENTRY，实得 %r' % ee)


if __name__ == '__main__':
    unittest.main()
