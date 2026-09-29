"""Gate wiring test: `check_body(..., translation=True)` skips the P1 proof-length
gate for step-6 TRANSLATE units (`units-translate/`), while source units keep it.

2026-09-29 Iwaniec–Kowalski《Analytic Number Theory》ch7 unit 0050: the CN translate
unit mirrors its frozen, already-gated EN source byte-for-byte in structure, but
`PROOF_OPEN_RE` matches CN `证明（梗概）` and not the printed EN word order
`Sketch of proof` — so the same prose proof passed on the source side and FAILed on
the translation side, and `gate_units --units-dir units-translate` demanded the
translator split the author's undivided argument into `1. 2. 3.`.  Structural
divergence from the verified source is not a content defect: the gate is the bug
(see `verbose_gates.is_translated_md`).  The verify P layer and the unit gate must
share that one predicate — pinning the unit-gate half here.
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

from check_unit_quality import check_body  # noqa: E402

_MARK = ("<!-- book-summarizer DONE unit: id=0050 type=item "
         "key=定理7.28 name=Theorem 7.28 -->\n")
# undivided >700-char blockquote proof (no `1.`/`(a)` step labels)
_WALL = ("对每一个不完备和逐项估计界，并逐条核对全部假设与收敛条件，"
         "于是所要求的上界成立；") * 30
_BODY = _MARK + "> **证明（梗概）。**\n" + "".join(
    "> " + _WALL + "\n" for _ in range(3))


class TestP1TranslationExemptionInUnitGate(unittest.TestCase):
    def test_source_unit_still_reported(self):
        ok, problems = check_body("item", "定理7.28", _BODY)
        self.assertFalse(ok, problems)
        self.assertTrue(any("证明" in p for p in problems), problems)

    def test_translate_unit_exempt(self):
        ok, problems = check_body("item", "定理7.28", _BODY, translation=True)
        self.assertFalse(any("证明" in p for p in problems), problems)


if __name__ == "__main__":
    unittest.main(verbosity=2)
