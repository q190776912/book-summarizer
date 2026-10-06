# -*- coding: utf-8 -*-
r"""B 层 EXTRA 桶的**印面确证豁免**通道（`attest_b_mention.py` + `load_b_mention_exemptions`）。

2026-10-04 动力系统书架收尾：v3 判据（`test_b_layer_mention_domain_v3.py`）把能机械归域
的残留全部收走后，书架只剩三例**形状与「正文提到一个条目而本章契约无记录」完全相同**、
只能靠回源 PDF 逐页核对定性的残留：

  · Koopman ch20 `引理 20.3`——印面 p.541/542 只有引理 20.1/20.2，正文两回
    「Based on Lemma 20.3」（物理 p.547、p.549）= 原书自己的笔误；
  · chaos ch5 `定义 5.6.5` / `5.6.5`——印面 §5.6 只有 Definition 5.6.1/5.6.2，
    p.138 的「(Definition 5.6.5)」指向 p.122 的编号公式 (5.6.5) = 原书误指；
  · Arnold 附录M `定理 3.1`——p.374 英译者脚注「Givental 指出，本文定理 3.1 不正确」
    的号属于另一篇论文。

判据侧**没有**可收窄的余地（任何放宽都会洗掉真漏登记——Apostol IANT ch9 例1 就是
「契约漏登记真条目」被当成良性交叉引用放过的实测教训），故按本机纪律开**签名取证**通道：
`<extract>/ignore_b_mention_{chapter_label}.json` = `{键: 印面取证理由}`，🔴 **空理由不生效**。

🔴 负向守卫：
  · 豁免只作用于**非阻断**的 EXTRA 三桶；`truly_missing` / `mentioned_only` / `blocking`
    逐字节不变（取证通道不是消音通道，缺项仍照旧阻断）；
  · 已豁免的键照旧进 `extra_attested` 清单（带理由）由 report 逐条打印，不静默消失；
  · 侧车缺失 / 坏 JSON / 值为空串 → 一律**不生效**（fail-open 到告警侧）。
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
import attest_b_mention as CLI  # noqa: E402


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


MD = (
    "# 第5章\n\n"
    "## §5.6 遍历算子\n\n"
    "**定义 5.6.1** 契约在册。\n\n"
    "**定义 5.6.2** 契约在册。\n\n"
    "> 于是由 (5.6.5) 即得。\n\n"
    "$$\n\\lVert P^{n}g\\rVert = \\cdots\n\\tag{5.6.5}\n$$\n\n"
    "> 对每个 $f\\in D_{0}$（$D$ 的一个稠密子集，定义 5.6.5）记轨迹为 $P^{n}f$。\n"
)


class _Harness(unittest.TestCase):
    def _setup(self, ignore=None):
        ext = tempfile.mkdtemp()
        d = os.path.join(ext, 'book_structure')
        os.makedirs(d, exist_ok=True)
        root = {'key': '5', 'type': 'chapter', 'sub_sec': [
            {'key': '5.6', 'type': 'section',
             'sub_sec': [_node('5.6.1'), _node('5.6.2')]},
        ]}
        with open(os.path.join(d, 'ch5.json'), 'w', encoding='utf-8') as f:
            json.dump(root, f, ensure_ascii=False)
        if ignore is not None:
            with open(os.path.join(ext, 'ignore_b_mention_ch5.json'), 'w',
                      encoding='utf-8') as f:
                json.dump(ignore, f, ensure_ascii=False)
        md = os.path.join(ext, 'ch5.md')
        with open(md, 'w', encoding='utf-8') as f:
            f.write(MD)
        cfg = BookConfig(ordinal=[GroupConfig(type=3, name=['uncat'], scope=3)],
                         language='cn')
        mgr = VerifyManager(_OnlyExtractB(), _Loader(cfg))
        return mgr.verify_one(5, 5, 5, md, ext)

    @staticmethod
    def _keys(res, field):
        return sorted(str(x) for x in (res.get(field) or []))


class ReportBucketTest(_Harness):
    def test_without_sidecar_key_is_reported(self):
        """无侧车 = 照旧报（fail-open 到告警侧）。"""
        res = self._setup()
        self.assertTrue(any('5.6-5' in x or '5.6.5' in x
                            for x in self._keys(res, 'extra_mention')
                            + self._keys(res, 'extra_entry')),
                        '实得 %r' % (res.get('extra_mention'),))
        self.assertEqual(self._keys(res, 'extra_attested'), [])

    def test_attested_key_leaves_buckets_and_stays_listed(self):
        res = self._setup({'定义5.6.5': '印面 p.138 系原书误指，5.6.5 为 p.122 的编号公式',
                           '5.6-5': '同上'})
        for field in ('extra_mention', 'extra_entry'):
            self.assertFalse(any('5.6-5' in x or '5.6.5' in x
                                 for x in self._keys(res, field)),
                             '%s 应已按取证豁免，实得 %r' % (field, self._keys(res, field)))
        att = self._keys(res, 'extra_attested')
        self.assertTrue(att, '豁免必须留痕（带理由打印，不静默消失）')
        reasons = res.get('extra_attested_reasons') or {}
        for k in att:
            self.assertTrue(str(reasons.get(k, '')).strip(), k + ' 的理由不得为空')

    def test_blocking_buckets_untouched(self):
        """🔴 取证通道只动非阻断桶：缺项/仅提及/阻断三桶逐字节不变。"""
        on, off = self._setup({'5.6-5': '印面 p.138 系原书误指'}), self._setup()
        for field in ('truly_missing', 'mentioned_only'):
            self.assertEqual(self._keys(on, field), self._keys(off, field), field)
        self.assertEqual(len(on.get('blocking') or []), len(off.get('blocking') or []))


class LoaderTest(unittest.TestCase):
    def test_empty_reason_never_takes_effect(self):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, 'ignore_b_mention_ch7.json'), 'w',
                  encoding='utf-8') as f:
            json.dump({'例3': '', '  ': '有理由但键为空', '定理9.9': '印面 p.200 为原文笔误'},
                      f, ensure_ascii=False)
        self.assertEqual(MOD.load_b_mention_exemptions(d, 7),
                         {'定理9.9': '印面 p.200 为原文笔误'})

    def test_missing_or_broken_sidecar_is_empty(self):
        d = tempfile.mkdtemp()
        self.assertEqual(MOD.load_b_mention_exemptions(d, 7), {})
        with open(os.path.join(d, 'ignore_b_mention_ch7.json'), 'w',
                  encoding='utf-8') as f:
            f.write('{ not json')
        self.assertEqual(MOD.load_b_mention_exemptions(d, 7), {})

    def test_key_folding_matches_report_form(self):
        """报告打 `5.6-5` 而登记写 `定义5.6.5`（或反之）也要配对上。"""
        tbl = {'定义5.6.5': 'r', '5.6-5': 'r'}
        self.assertEqual(MOD._attested_extra_keys({'5.6-5', '定理1.1', '例3'}, tbl),
                         {'5.6-5'})


class CliTest(unittest.TestCase):
    def test_refuses_empty_reason_and_writes_nothing(self):
        d = tempfile.mkdtemp()
        rc = CLI.main([d, '5', '--key', '定义5.6.5', '--reason', '  '])
        self.assertEqual(rc, 2)
        self.assertFalse(os.path.exists(
            os.path.join(d, 'ignore_b_mention_ch5.json')))

    def test_registers_key_with_reason_and_lists_it(self):
        d = tempfile.mkdtemp()
        rc = CLI.main([d, '5', '--key', '定义5.6.5',
                       '--reason', '印面 p.138 误指，5.6.5 为 p.122 编号公式'])
        self.assertEqual(rc, 0)
        self.assertEqual(MOD.load_b_mention_exemptions(d, 5),
                         {'定义5.6.5': '印面 p.138 误指，5.6.5 为 p.122 编号公式'})
        self.assertEqual(CLI.main([d, '5', '--key', '定义5.6.5',
                                   '--reason', '印面 p.138 误指，5.6.5 为 p.122 编号公式']), 0)
        self.assertEqual(len(os.listdir(d)), 1, '重复登记不得写出第二个侧车')


if __name__ == '__main__':
    unittest.main()
