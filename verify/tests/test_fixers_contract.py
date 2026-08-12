"""Temporary smoke test: confirm FIXERS registry is fully populated, ordered,
and that the merged fix-dict key order matches the legacy byte contract
{h, h_stmt, h_ul, h_mbq, g, i, j, k, l, m, n}.  Deleted after verification.
"""
import os
import sys
import tempfile
from pathlib import Path

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

import register_all  # noqa: F401  (triggers discovery + fix registration)
from verify.layers.script.base import FIXERS, fixable_ordered_fixers


def test_fixers_registered_and_ordered():
    expected = {"H", "G", "I", "J", "K", "L", "M", "N"}
    assert set(FIXERS) == expected, ("FIXERS codes", set(FIXERS))
    ordered = [c for c, _ in fixable_ordered_fixers()]
    assert ordered == ["H", "G", "I", "J", "K", "L", "M", "N"], ordered


def test_fix_dict_key_order_byte_compatible():
    # Replicate VerifyManager.fix's FIXERS merge path on a temp .md.
    tf = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
    tf.write("**定义1.1**\n\n正文\n\n> 例：foo\n\n> 证明：bar\n")
    tf.close()
    try:
        class _Ctx:
            md_file = tf.name
        result = {}
        for code, (fo, fn) in fixable_ordered_fixers():
            fr = fn(_Ctx())
            if fr is None:
                continue
            result.update(fr.fix_dict)
        legacy = ["h", "h_stmt", "h_ul", "h_mbq", "g", "i", "j", "k", "l", "m", "n"]
        assert list(result.keys()) == legacy, ("order", list(result.keys()))
    finally:
        os.unlink(tf.name)


if __name__ == "__main__":
    test_fixers_registered_and_ordered()
    test_fix_dict_key_order_byte_compatible()
    print("SMOKE OK: fixers", [c for c, _ in fixable_ordered_fixers()])
