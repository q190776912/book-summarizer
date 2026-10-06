"""test_o_tail_printed_attestation.py — O 层 TAIL 行的「印面确证豁免」判据。

成因（Katok 2026-10-03 实测两条假阳）：`_o_tail_ocr_scan` 以「含同一上下文关键词的
**整页** OCR」为窗口搜更大编号，于是同页**另一张清单**的号必然命中——
  · Theorem 5.5.21 `Then: (1)(2)(3)` 被印面 p.228 习题 5.5.3 的 `(4)` 判成尾缺；
  · 补篇 Definition S.3.3 `Remarks (1)(2)(3)` 被同页 Theorem S.3.1 的 `(4)` 判成尾缺。
两处逐页核对印面均无第 (4) 项 → 属告警而非缺陷，但每次 verify 都要重跑一遍印面考古。
本测试钉住豁免通道的四条边界：登记后静默、**空理由不生效**、**签名不符不生效**
（防把整章 TAIL 通道一次关掉）、CLI 拒绝无取证登记。

Run with stdlib unittest:
    python verify/tests/test_o_tail_printed_attestation.py
"""
import json
import os
import shutil
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
for _p in (_ROOT, os.path.join(_ROOT, "lib"),
           os.path.join(_ROOT, "verify", "subitem_continuity", "script")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

import subitem_continuity as O      # noqa: E402
import attest_o_tail as CLI         # noqa: E402

MD = """# Chapter 5

**Theorem 5.5.21** (Liouville-Arnold): Suppose the hypotheses hold.

Then:

(1) $M_z$ is a smooth Lagrangian submanifold.

(2) If $M_z$ is compact and connected then $M_z$ is a torus.

(3) Via this diffeomorphism the flow is conjugate to a linear flow.
"""

# 印面同页另有习题清单 5.5.3 的 (1)…(4)：关键词 'Then:' 也在同一页 → 判据扫到 (4)
OCR_PAGE = {"text": [{"text": (
    "Theorem 5.5.21. ... Then: (1) M is Lagrangian (2) compact gives torus "
    "(3) conjugate to a linear flow. Exercises 5.5.3. Let A be a collection: "
    "(1) A contains an even number of 1's. (2) If lambda is real then 1/lambda. "
    "(3) If |lambda| = 1 then lambda bar. (4) If |lambda| != 1 then inverse."
)}]}


class OTailAttestationTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='bks_otail_')
        self.ext = os.path.join(self.dir, '_extract')
        os.makedirs(self.ext)
        self.md = os.path.join(self.dir, 'ch5.md')
        with open(self.md, 'w', encoding='utf-8') as f:
            f.write(MD)
        with open(os.path.join(self.ext, 'page_248.json'), 'w', encoding='utf-8') as f:
            json.dump(OCR_PAGE, f, ensure_ascii=False)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _rows(self):
        return O.check_ordinal_subitem_gaps(self.md, ext_dir=self.ext, ch=5,
                                            start=248, end=248)

    def _write_sidecar(self, table):
        with open(os.path.join(self.ext, 'ignore_o_tail_ch5.json'), 'w',
                  encoding='utf-8') as f:
            json.dump(table, f, ensure_ascii=False, indent=2)

    # ── 判据基线 ────────────────────────────────────────────────────────
    def test_fixture_actually_fires_tail_row(self):
        rows = self._rows()
        self.assertEqual(len([r for r in rows if r.strip().startswith('~')]), 1, rows)
        self.assertIn('TAIL gap', rows[0])
        self.assertIn('attest_o_tail.py', rows[0])   # 告警行自带登记命令

    def test_signature_shape(self):
        self.assertEqual(O.o_tail_signature('Then:', 3, [5, 4]), 'Then|3|4,5')
        self.assertEqual(O.o_tail_signature('Remarks：', 3, [4]), 'Remarks|3|4')

    # ── 豁免生效侧 ──────────────────────────────────────────────────────
    def test_attested_signature_silences_the_row(self):
        self._write_sidecar({'Then|3|4': 'VERIFIED 印面 p.227 只有 (1)(2)(3)；'
                                         '(4) 是同页习题 5.5.3 列表'})
        self.assertEqual(self._rows(), [])

    def test_cli_registration_then_verify_silent(self):
        rc = CLI.main([self.ext, '5', '--sig', 'Then|3|4',
                       '--reason', '印面 p.248 核对：Then: 只有 (1)(2)(3)'])
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.exists(os.path.join(self.ext, 'ignore_o_tail_ch5.json')))
        self.assertEqual(self._rows(), [])

    def test_cli_refuses_registration_without_reason(self):
        rc = CLI.main([self.ext, '5', '--sig', 'Then|3|4', '--reason', '   '])
        self.assertEqual(rc, 2)
        self.assertFalse(os.path.exists(os.path.join(self.ext, 'ignore_o_tail_ch5.json')))
        self.assertEqual(len(self._rows()), 1)   # 未登记 → 照常告警

    # ── 护栏：不得被泛化使用 ────────────────────────────────────────────
    def test_blank_reason_does_not_exempt(self):
        self._write_sidecar({'Then|3|4': '   '})
        self.assertEqual(len(self._rows()), 1)

    def test_other_signature_does_not_exempt(self):
        # 登记了别的清单/别的号段，不能顺手关掉本行
        self._write_sidecar({'Remarks|3|4': '别处的印面确证'})
        self.assertEqual(len(self._rows()), 1)

    def test_head_and_internal_rows_are_not_exemptible(self):
        # 豁免通道只作用于 TAIL `~`：HEAD/INTERNAL 的 `x` 行不受侧车影响
        self._write_sidecar({'Then|3|4': 'VERIFIED'})
        md = os.path.join(self.dir, 'ch5_head.md')
        with open(md, 'w', encoding='utf-8') as f:
            f.write('# Chapter 5\n\nThen:\n\n(2) b\n\n(3) c\n\n(4) d\n')
        rows = O.check_ordinal_subitem_gaps(md, ext_dir=self.ext, ch=5,
                                            start=248, end=248)
        self.assertTrue([r for r in rows if r.strip().startswith('x')], rows)

    def test_broken_sidecar_fails_open_to_warning(self):
        fp = os.path.join(self.ext, 'ignore_o_tail_ch5.json')
        with open(fp, 'w', encoding='utf-8') as f:
            f.write('{not json')
        self.assertEqual(len(self._rows()), 1)


if __name__ == '__main__':
    unittest.main()
