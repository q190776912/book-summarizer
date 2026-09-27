"""Rule #17 bare-call check must decide identically for EN and CN.

English prints "cf. Lemma A (10.3)" and passes; the translation "引理 A (10.3)"
was flagged as a bare function call because Chinese has no space delimiters, so
`pre.split()[-1]` swallowed the whole run.  Same structure ⇒ same verdict.
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
    _ROOT = str(Path(__file__).resolve().parents[2])
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

from verify.format_verify.script.katex_heuristics import find_bare_math_errors


def _flagged(line):
    return bool(find_bare_math_errors([line]))


class TestLabelWordBilingual(unittest.TestCase):
    def test_cn_xref_not_flagged(self):
        for line in ('（参见引理 A (10.3)）恒等式成立。',
                     '由定理 B (12.1) 可知结论成立。',
                     '如注记 3 所述：见推论 C (2.4)，此处略。',
                     '对照式 (5.1) 与图 2 (7) 可得结果。'):
            self.assertFalse(_flagged(line), 'CN cross-reference flagged: %r' % line)

    def test_en_xref_still_not_flagged(self):
        for line in ('This follows from Lemma A (10.3) as usual.',
                     'See Theorem B (12.1) for the details here.'):
            self.assertFalse(_flagged(line), 'EN cross-reference flagged: %r' % line)

    def test_bilingual_same_verdict(self):
        pairs = [('cf. Lemma A (10.3)', '参见引理 A (10.3)'),
                 ('by Theorem B (12.1)', '由定理 B (12.1)'),
                 ('as in Corollary C (2.4)', '如推论 C (2.4) 所示')]
        for en, cn in pairs:
            self.assertEqual(_flagged(en), _flagged(cn),
                             'EN/CN verdict differ for %r vs %r' % (en, cn))
            self.assertFalse(_flagged(en), 'label ref must pass: %r' % en)

    def test_real_bare_call_still_flagged(self):
        # 标签词必须在紧邻位置；隔了正文的单字母调用仍是裸公式
        self.assertTrue(_flagged('引理很多，故考虑映射 f (x) 的像。'))
        self.assertTrue(_flagged('There are many lemmas, so f (x) is considered.'))
        # 非标签词收尾不得被豁免
        self.assertTrue(_flagged('其中定义的映射 g (x) 是单射。'))


class TestProbOpGloss(unittest.TestCase):
    """`E (` inside a CN label gloss (`**推论 E (Corollary)**`) is prose.

    The EN original writes `**Corollary E**` — no paren — so before the fix the
    same structure passed in EN and failed in CN.
    """

    def test_label_gloss_not_flagged(self):
        for line in ('**推论 E (Corollary)** 设 $W$ 是子空间。',
                     '**引理 E (Lemma)** 结论成立。',
                     '**命题 Cov (Variance-cancellation)** 见下。'):
            self.assertFalse(_flagged(line), 'label gloss flagged: %r' % line)

    def test_real_operator_still_flagged(self):
        self.assertTrue(_flagged('计算可得 E (X ∪ Y) 的上界。'))
        self.assertTrue(_flagged('We have Pr (A ∩ B) bounded by one.'))
        self.assertTrue(_flagged('The variance Var (X) is finite here.'))

    def test_bilingual_same_verdict(self):
        # 印刷式 `Corollary E` / `推论 E (Corollary)` 都必须放行
        self.assertEqual(_flagged('**Corollary E** Let W be a subspace.'),
                         _flagged('**推论 E (Corollary)** 设 $W$ 是子空间。'))



if __name__ == '__main__':
    unittest.main()
