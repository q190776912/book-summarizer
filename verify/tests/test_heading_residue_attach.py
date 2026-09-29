"""attach_content._drop_heading_residue — 节题残块判据（2026-09-29）。

动因（Iwaniec–Kowalski GTM207 实测 8 处）：印面上一行节题，OCR 常因行内公式被切成
两块（`9.7. Large values of D(s,` + `x).`），而 `build_structure` 收割 `name` 用的是
另一套转写（`$Q(\\sqrt{D})$` vs `Q(VD)`、`$\\Lambda^{(g)}(½)$` vs `A(9)(Ω)`），
`_strip_header` 只能吃掉对得上的一截，剩下的那截就成了本节 description 里的正文块。
磁盘契约按印面把它删掉后，① 复算闸又把它重算出来 → 假「契约缺块」。

判据按**几何拼回印刷行**，所以这里同时钉住两版误删的失败形态：
  * 只按单块判序数 → 序数 `5` 前缀匹配条目行 `5.14 Theorem. …` → 全书误删 60+ 块；
  * 按「相邻块拼接」而不按 y 带拼行 → 标题行与紧随其后的正文行并成一条候选，
    整句正文成了候选尾部 → 误删 15+ 块。

Run:  python verify/tests/test_heading_residue_attach.py
"""
import os
import sys
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[2])
for _p in (_ROOT, os.path.join(_ROOT, "lib"),
           os.path.join(_ROOT, "flows", "write-source", "structure", "script")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lib.boot as _boot  # noqa: E402
_boot.setup()
import attach_content as ac  # noqa: E402


def _blk(text, page=1, y=100.0, bottom=120.0, x=50.0, x1=400.0):
    return {"page": page, "y": y, "bottom": bottom, "x": x, "x1": x1,
            "kind": "text", "text": text}


def _kept(stripped, originals, name):
    return [b.get("text") for b in ac._drop_heading_residue(stripped, originals, name)]


def test_split_heading_tail_is_dropped():
    """`9.7. Large values of D(s,` + `x).` 同一行 → 尾块是标题残块。"""
    head = _blk("9.7. Large values of D(s,", x1=300.0)
    tail = _blk("x).", x=305.0, x1=360.0)
    body = _blk("The notation from previous section holds here.", y=140.0,
                bottom=160.0)
    stripped = [head, tail, body]
    assert _kept(stripped, stripped, r"9.7 Large values of $D(s,\chi)$.") == \
        ["The notation from previous section holds here."]


def test_heading_repeat_whole_line_is_dropped():
    """`24.1. A lower bound for No` 是标题行本体（尾部 `(T).` 另成一块）。"""
    head = _blk("24.1. A lower bound for No", x1=320.0)
    tail = _blk("(T).", x=325.0, x1=360.0)
    stripped = [head, tail]
    assert _kept(stripped, stripped, r"24.1 A lower bound for $N_0(T)$.") == []


def test_item_line_is_not_heading_residue():
    """🔴 负向：章名序数 `5` 不许前缀匹配条目行 `5.14 Theorem. …`（v1 误删 60+ 块）。"""
    item = _blk("5.14 Theorem.", x1=200.0)
    prose = _blk("Let the series converge uniformly.", x=210.0, x1=500.0)
    stripped = [item, prose]
    assert _kept(stripped, stripped, "5 Classical analytic theory") == [
        "5.14 Theorem.", "Let the series converge uniformly."]


def test_ordinal_guard_alone_rejects_longer_number():
    """🔴 负向：首词与章名相同时，只剩「序数后不得再接数字/点」这一道闸。

    v1 在 `_norm` 后的文本上比序数，`_norm` 把点全剥了（`5.14` → `514`），序数 `5`
    于是前缀匹配 `514theory…` → 整行正文被当成节题残块删除。
    """
    body = _blk("5.14 Theory of the zeta function is classical.", x1=260.0)
    tail = _blk("and follows Riemann.", x=265.0, x1=420.0)
    stripped = [body, tail]
    assert _kept(stripped, stripped, "5 Theory of L-functions") == [
        "5.14 Theory of the zeta function is classical.", "and follows Riemann."]


def test_prose_line_after_heading_is_not_dropped():
    """🔴 负向：正文行在标题行的**下一行**（y 带不重叠）→ 不许并进候选吞掉。"""
    head = _blk("22.5. Splitting primes in Q", x1=300.0)
    tail = _blk("(VD).", x=305.0, x1=360.0)
    prose = _blk("If the class number h = h(D) is small, then there are only few",
                 y=140.0, bottom=160.0)
    stripped = [head, tail, prose]
    assert _kept(stripped, stripped, r"22.5 Splitting primes in $Q(\sqrt{D})$.") == [
        "If the class number h = h(D) is small, then there are only few"]


def test_first_word_mismatch_keeps_the_block():
    """负向：同一行但实词与 `name` 不同 → 不是本节标题，留。"""
    a = _blk("9.7. Some other sentence entirely,", x1=300.0)
    b = _blk("and here is the rest.", x=305.0, x1=420.0)
    stripped = [a, b]
    assert _kept(stripped, stripped, r"9.7 Large values of $D(s,\chi)$.") == [
        "9.7. Some other sentence entirely,", "and here is the rest."]


def test_long_line_is_not_a_heading():
    """负向：>70 归一化字符的长行是正文，哪怕以本节序数开头。"""
    long_line = _blk("9.7. Large values of D(s,chi) are estimated by the mean value theorem "
                     "together with the reflection method of Section 9.6, as required.",
                     x1=700.0)
    tail = _blk("required.", x=640.0, x1=700.0)
    stripped = [long_line, tail]
    assert _kept(stripped, stripped, r"9.7 Large values of $D(s,\chi)$.") == [
        long_line["text"], "required."]


def test_no_geometry_blocks_are_kept():
    """负向：块没有 page/y（外部构造的树）→ 判据不启用，一律保留。"""
    stripped = [{"kind": "text", "text": "x)."}]
    assert _kept(stripped, stripped, r"9.7 Large values of $D(s,\chi)$.") == ["x)."]


def test_name_without_ordinal_disables_the_rule():
    stripped = [_blk("x).")]
    assert _kept(stripped, stripped, "Introduction.") == ["x)."]


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS %s" % name)
            except AssertionError as e:
                fails += 1
                print("FAIL %s: %s" % (name, e))
    print("HEADING RESIDUE TESTS:", "FAIL" if fails else "PASS")
    sys.exit(1 if fails else 0)
