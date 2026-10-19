# -*- coding: utf-8 -*-
r"""B 层 uncat 两段键「数字同号」覆盖判据回归（2026-10-19 Axler 根治）。

实测根因（Axler《Measure, Integration & Real Analysis》ch2/ch4–ch12，verify
报告 46 键 × 中英 89 行 EXTRA-ENTRY 全为该型假信号）：结构探测对「标签词被 OCR
粘连/缺失」的两段真实条目落 `key = 'uncat' + 号`（`uncat5.11`，名内实证
`5.11Examplecollection…` = Example 被粘进数字），而 md 条头照印面带标签
（CN blockquote `> **例5.19**（…）`、EN `**2.39 condition …**` → `条件2.39`）。
`_norm_path` 只折三段键 → 两侧归一后 'uncat5.11' vs '例5.11' 永不相交，契约
**已登记**的条目被逐条报成「契约漏登记印面条目」（2026-10-08 老修复只覆盖三段
裸键，正是此因）。label='uncat' = 类型未知，本就无类型可对账，故两侧统一剥
`uncat`/条目标签后按数字同号判同一实体。

本测试断言四条（缺一即成「靠放宽判据洗掉真漏登记」）：
  1. CN 带标签条头 `**例5.11**` 与 EN 数字在前条头 `**5.60 condition …**`
     在契约有 `uncat5.11` / `uncat5.60` 时离开 extra/extra_entry；
  2. 契约无节点的真孤儿条头 `**例5.99**` 必须照旧报 EXTRA-ENTRY；
  3. 关掉本判据（monkeypatch `_digit_entity` → None）只让 EXTRA 桶移动，
     `truly_missing` / `mentioned_only` / `blocking` 逐字节不变；
  4. `_digit_entity` 纯函数形态：`uncat5.11`/`例5.11`/`5.11` → `5.11`，
     三级 `1.1-1` / 字母位 `A.2-1` / 题集 `问题7-19` → None（各归各的通道）。
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
from verify.script.base import VerifyManager  # noqa: E402
from verify.script.register_all import LAYER_REGISTRY  # noqa: E402
from verify_config import BookConfig, GroupConfig  # noqa: E402

# 契约：uncat 两段节点（真实键形 `uncat5.11`，见 ch5.json 原文）+ 一个三段
# typed 条目充当「正常在账」锚点。
MD = (
    "# 第5章\n\n"
    "## §5.2 乘积测度\n\n"
    "**定义5.2.1** 契约登记的三段条目。\n\n"
    "> **例5.11**（区间有限并的族是代数）：契约有 uncat5.11，同一实体。\n\n"
    "**5.60 condition for measurable function**: 契约有 uncat5.60。\n\n"
    "**例5.99** 契约里没有的条头（真孤儿形态）。\n\n"
)


def _node(key, type_='definition'):
    return {'key': key, 'type': type_, 'name': key, 'page_start': 100,
            'page_end': 100, 'sub_sec': [{'type': 'text', 'text': '内容'}]}


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


class UncatDigitEntityTest(unittest.TestCase):
    def _run(self, md_text=MD, digit_fix=True):
        ext = tempfile.mkdtemp()
        d = os.path.join(ext, 'book_structure')
        os.makedirs(d, exist_ok=True)
        root = {'key': '5', 'type': 'chapter', 'sub_sec': [
            {'key': '5.2', 'type': 'section', 'sub_sec': [
                _node('5.2.1'),
                _node('uncat5.11', type_='uncat'),
                _node('uncat5.60', type_='uncat'),
            ]},
        ]}
        with open(os.path.join(d, 'ch5.json'), 'w', encoding='utf-8') as f:
            json.dump(root, f, ensure_ascii=False)
        md = os.path.join(ext, 'ch5.md')
        with open(md, 'w', encoding='utf-8') as f:
            f.write(md_text)
        cfg = BookConfig(ordinal=[GroupConfig(type=2, name=['Definition', 'Example'],
                                              scope=2),
                                  GroupConfig(type=0, name=['Figure'], scope=2)],
                         language='en')
        mgr = VerifyManager(_OnlyExtractB(), _Loader(cfg))
        if digit_fix:
            return mgr.verify_one(5, 5, 5, md, ext)
        orig = MOD._digit_entity
        MOD._digit_entity = lambda k: None
        try:
            return mgr.verify_one(5, 5, 5, md, ext)
        finally:
            MOD._digit_entity = orig

    def test_registered_labeled_heads_leave_extra(self):
        """负向 1：契约有同号 uncat 节点的带标签条头离开 EXTRA 两桶。"""
        res = self._run()
        ee = [str(x) for x in (res.get('extra_entry') or [])]
        ex = [str(x) for x in (res.get('extra') or [])]
        for k in ('5.11', '5.60'):
            self.assertFalse(any(k in x for x in ee),
                             '%s 契约已登记(uncat) -> 不得在 extra_entry，实得 %r'
                             % (k, ee))
            self.assertFalse(any(k in x for x in ex), (k, ex))

    def test_true_orphan_head_still_reported(self):
        """负向 2：契约无节点的真条头照旧报，本行不是洗地机。"""
        res = self._run()
        ee = [str(x) for x in (res.get('extra_entry') or [])]
        self.assertTrue(any('5.99' in x for x in ee),
                        '例5.99 契约无节点 -> 必须仍在 EXTRA-ENTRY，实得 %r' % ee)

    def test_registering_keeps_other_buckets_byte_identical(self):
        """负向 3：开/关本判据只动 EXTRA 桶，其余判定逐字节不变。"""
        on, off = self._run(), self._run(digit_fix=False)
        ee_on = set(str(x) for x in (on.get('extra_entry') or []))
        ee_off = set(str(x) for x in (off.get('extra_entry') or []))
        self.assertTrue(any('5.11' in x for x in ee_off),
                        '关掉判据后例5.11 必须回到条目桶，实得 %r' % ee_off)
        self.assertTrue(any('5.60' in x for x in ee_off),
                        '关掉判据后条件5.60 必须回到条目桶，实得 %r' % ee_off)
        self.assertFalse(any(('5.11' in x) or ('5.60' in x) for x in ee_on),
                         '本行只应收窄，不应新增 %r' % ee_on)
        self.assertTrue(any('5.99' in x for x in ee_off), ee_off)
        for key in ('truly_missing', 'mentioned_only', 'blocking'):
            self.assertEqual(sorted(str(x) for x in (on.get(key) or [])),
                             sorted(str(x) for x in (off.get(key) or [])), key)


class DigitEntityShapeTest(unittest.TestCase):
    """判据形状单测：剥标签后的点分数字同号。"""

    def test_labeled_and_bare_two_level(self):
        for src, want in (('uncat5.11', '5.11'), ('例5.11', '5.11'),
                          ('5.11', '5.11'), ('条件2.39', '2.39'),
                          ('示例1.2', '1.2'), ('Example 5.3', None),
                          ('定义4.2.9', '4.2.9')):
            self.assertEqual(MOD._digit_entity(src), want, src)

    def test_other_channels_stay_out(self):
        """三级/字母位/题集短横各归各的通道，不经本判据。"""
        for src in ('1.1-1', 'A.2-1', '问题7-19', '7-19', '', None, 'uncat'):
            self.assertIsNone(MOD._digit_entity(src), repr(src))


if __name__ == '__main__':
    unittest.main()
