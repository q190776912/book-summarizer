# -*- coding: utf-8 -*-
r"""B 层「公式回指冒充条目键」领域归属判据回归（2026-10-02 chaos ch4/ch8/ch12 根治）。

实测根因（`_probe_entry_re_match.py`，Lasota–Mackey《Chaos, Fractals and Noise》）：
`ENTRY_RE = \*\*[^*]*?(\d+SEP\d+SEP\d+)[^*]*\*+` 的收尾是 `\*+`，会在**行内数学的
星号上闭合**（`$f^{*}$` / `$\mu_*$` / `^{*}` 都是单个 `*`），于是

    > **证明**：1. 由 (4.2.6) 与定理 4.2.1 可知 $f^{*}$ 几乎处处为常数。

里从 `证明**` 的**闭合** `**` 起跨到 `$f^{*}$` 的那个 `*` 止的假粗体跨度，把公式回指
`(4.2.6)` 登记成了 **条目键**（`keys_in_md` 的 `entries`）→ 直落 `extra_entry`
=「md 有独立条头而契约无该条目」= 契约漏登记的**最强信号桶**，而全书 md 里根本不存在
`**4.2.6**` 条头（逐文件扫描 0 命中）。同形事故另有 `**性质4.** … (8.5.8) … $f_{*}$`、
`**第一步** … (12.7.3)`、`**第二步** … (12.7.17)`，CN/EN 两版各报一遍。

修法 = 把提及侧既有的**领域归属判据**（`domain_suppressed_mentions`：tag / figref /
eqref）一并作用于条目桶。安全性来自判据本身的形状：某键在 md 里的**每一处**出现都属
领域才剔除，而真条头 `**定义 4.2.6**` 自己就贡献一处 `real` 出现，不可能被洗掉。

本测试断言四条（缺一即成「靠放宽判据洗掉真漏登记」）：
  1. 假粗体跨度产出的 `(4.2.6)` 离开 `extra_entry`/`extra`，且照旧出现在
     `extra_mention_domain` 豁免清单（不静默消失）；
  2. 契约里没有的**真**条头 `**定义 4.2.9**` 必须照旧报 EXTRA-ENTRY；
  3. 同一键既有括号回指又有真条头时**不豁免**（一处 `real` 即全盘照报）；
  4. 关掉本行（monkeypatch `domain_suppressed_mentions` → 空集）只让 EXTRA 桶移动，
     `truly_missing` / `mentioned_only` / `blocking` 逐字节不变。
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

# `**证明**：… (4.2.6) … $f^{*}$` = 事故形态；`**定义 4.2.9**` = 真漏登记形态。
MD = (
    "# 第4章\n\n"
    "## §4.2 不变测度\n\n"
    "**定义 4.2.1** 不变测度的定义。\n\n"
    "> **证明**：1. 由 (4.2.6) 与定理 4.2.1 可知 $f^{*}$ 几乎处处为常数。\n\n"
    "**定义 4.2.9** 契约里没有的条头（真漏登记形态）。\n\n"
)
# 同键两处：一处括号回指 + 一处真条头 -> 一处 `real` 即不豁免。
MD_MIXED = (
    "# 第4章\n\n"
    "## §4.2 不变测度\n\n"
    "**定义 4.2.1** 不变测度的定义。\n\n"
    "> **证明**：1. 由 (4.2.6) 与定理 4.2.1 可知 $f^{*}$ 几乎处处为常数。\n\n"
    "**定义 4.2.6** 契约里没有的真条头。\n\n"
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


class EntryDomainGuardTest(unittest.TestCase):
    def _run(self, md_text, guard=True):
        ext = tempfile.mkdtemp()
        d = os.path.join(ext, 'book_structure')
        os.makedirs(d, exist_ok=True)
        root = {'key': '4', 'type': 'chapter', 'sub_sec': [
            {'key': '4.2', 'type': 'section', 'sub_sec': [
                _node('4.2.1'),
            ]},
        ]}
        with open(os.path.join(d, 'ch4.json'), 'w', encoding='utf-8') as f:
            json.dump(root, f, ensure_ascii=False)
        md = os.path.join(ext, 'ch4.md')
        with open(md, 'w', encoding='utf-8') as f:
            f.write(md_text)
        cfg = BookConfig(ordinal=[GroupConfig(type=3, name=['uncat'], scope=3)],
                         language='cn')
        mgr = VerifyManager(_OnlyExtractB(), _Loader(cfg))
        if guard:
            return mgr.verify_one(4, 4, 4, md, ext)
        orig = MOD.domain_suppressed_mentions
        MOD.domain_suppressed_mentions = lambda txt, keys: set()
        try:
            return mgr.verify_one(4, 4, 4, md, ext)
        finally:
            MOD.domain_suppressed_mentions = orig

    def test_math_asterisk_eqref_leaves_entry_bucket(self):
        """负向 1：假粗体跨度的公式回指离开条目桶，但仍在豁免清单里可见。"""
        res = self._run(MD)
        ee = [str(x) for x in (res.get('extra_entry') or [])]
        ex = [str(x) for x in (res.get('extra') or [])]
        self.assertFalse(any('4.2-6' in x for x in ee),
                         '(4.2.6) 是公式回指不是条头，实得 %r' % ee)
        self.assertFalse(any('4.2-6' in x for x in ex), ex)
        dom = [str(x) for x in (res.get('extra_mention_domain') or [])]
        self.assertTrue(any('4.2-6' in x for x in dom),
                        '豁免必须留痕，实得 %r' % dom)

    def test_real_orphan_head_still_reported(self):
        """负向 2：契约无节点的真条头照旧报，本行不是洗地机。"""
        res = self._run(MD)
        ee = [str(x) for x in (res.get('extra_entry') or [])]
        self.assertTrue(any('4.2-9' in x for x in ee),
                        '定义 4.2.9 契约无节点 -> 必须仍在 EXTRA-ENTRY，实得 %r' % ee)

    def test_one_real_occurrence_defeats_suppression(self):
        """负向 3：同键既有括号回指又有真条头 -> 一处 `real` 即全盘照报。"""
        res = self._run(MD_MIXED)
        ee = [str(x) for x in (res.get('extra_entry') or [])]
        self.assertTrue(any('4.2-6' in x for x in ee),
                        '**定义 4.2.6** 是 real 出现，不得豁免，实得 %r' % ee)

    def test_guard_moves_only_extra_buckets(self):
        """负向 4：关掉判据只动 EXTRA 三桶，判定与真漏桶逐字节不变。"""
        on, off = self._run(MD), self._run(MD, guard=False)
        ee_on = set(str(x) for x in (on.get('extra_entry') or []))
        ee_off = set(str(x) for x in (off.get('extra_entry') or []))
        self.assertTrue(ee_off - ee_on,
                        '关掉判据后 4.2-6 必须回到条目桶，否则本测试没测到东西')
        self.assertEqual(ee_on - ee_off, set(), '本行只应收窄，不应新增')
        for key in ('truly_missing', 'mentioned_only'):
            self.assertEqual(sorted(str(x) for x in (on.get(key) or [])),
                             sorted(str(x) for x in (off.get(key) or [])), key)
        self.assertEqual(len(on.get('blocking') or []), len(off.get('blocking') or []))


class DomainJudgeShapeTest(unittest.TestCase):
    """判据形状单测：星号在数学里、括号回指、标签词 + 括号。"""

    def test_eqref_with_math_asterisk_is_suppressed(self):
        txt = '> **证明**：1. 由 (4.2.6) 与定理 4.2.1 可知 $f^{*}$ 几乎处处为常数。'
        self.assertEqual(MOD.domain_suppressed_mentions(txt, {'4.2-6'}), {'4.2-6'})

    def test_label_before_paren_stays_real(self):
        txt = '**Definition (4.2.6)** 是条目引用形态，不是公式回指。'
        self.assertEqual(MOD.domain_suppressed_mentions(txt, {'4.2-6'}), set())

    def test_formula_words_route_to_eqref_not_real(self):
        """🔴 `Equation (4.2.6)` / `Eq. (4.2.6)` 是公式域回指，不是条目引用：
        这两个词曾在 `_LABEL_BEFORE_PAREN_RE`（条目词表）里，导致 EN 侧同句
        永不豁免而 CN 侧（`由 (4.2.6)`）豁免 = 双语判据不对称（chaos ch4/ch12 实测）。
        反向守卫照旧成立：真正的条目词（Definition/定理）仍判 real。"""
        for txt in ('Equation (4.2.6) follows directly from (4.2.5).',
                    'by Eq. (4.2.6) and Theorem 4.2.1 we get the result',
                    '由公式 (4.2.6) 即得结论'):
            self.assertEqual(MOD.domain_suppressed_mentions(txt, {'4.2-6'}), {'4.2-6'},
                             txt[:28])
        for txt in ('由定理（4.2.6）即得结论', 'see Theorem (4.2.6) below',
                    '**Definition (4.2.6)** 是条目引用'):
            self.assertEqual(MOD.domain_suppressed_mentions(txt, {'4.2-6'}), set(),
                             '条目词须照旧判 real: ' + txt[:24])
        for txt in ('Definition (4.2.6) is an item reference.',
                    '见定理（4.2.6）所述。'):
            self.assertEqual(MOD.domain_suppressed_mentions(txt, {'4.2-6'}), set(),
                             txt[:28])

    def test_entry_head_never_suppressed(self):
        txt = '**定义 4.2.6** 内容。\n\n另有 (4.2.6) 的括号回指。'
        self.assertEqual(MOD.domain_suppressed_mentions(txt, {'4.2-6'}), set())

    def test_entry_re_really_produces_the_fake_head(self):
        """根因留证：`ENTRY_RE` 确实把该行的公式回指收进 entries。"""
        from key_parse import keys_in_md
        from lib.regexlib import ENTRY_RE  # noqa: F401  （形态对照）
        md = os.path.join(tempfile.mkdtemp(), 'x.md')
        with open(md, 'w', encoding='utf-8') as f:
            f.write(MD)
        entries, _all = keys_in_md(md, groups=[GroupConfig(type=3, name=['uncat'],
                                                           scope=3)])
        self.assertIn('4.2-6', entries,
                      'ENTRY_RE 在数学星号上闭合 -> 4.2.6 进条目集（本判据存在的前提）')


if __name__ == '__main__':
    unittest.main()
