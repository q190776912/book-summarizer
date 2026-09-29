"""check_exercise_coverage — 印面标题判据 + 人工印面确证登记（2026-09-29）。

动因（Iwaniec–Kowalski GTM207 的 4 处 PHANTOM，先分诊再处置）：
  * ch4 Ex4 的标题行**在** OCR 里（`ExFRCISE 4.Derive (4.23) fron1 (4.21)`），
    旧字符类 `^[A-Z]{0,2}ERC[A-Z]{1,4}` 因一个字母读歪而整体失配 → **判据漏**，
    改判据（`printed_label` 的编辑距离 ≤1 支），不许登记；
  * ch1 Ex2 / ch4 Ex7 / ch5 Ex6 的小字粗体标题**整行连展示式一起漏扫**（fitz 渲染
    目视坐实印面确有）→ 印面真值集缺号，机器无从复算 → 只能走 `--attest` 台账。
    台账必须挡住三种「拿登记当判据」的写法：页不在本章区间、号已被机械扫到、
    号在单元里根本不存在（那会把真 MISSING 永久掩盖）。

Run:  python verify/tests/test_exercise_coverage_attestation.py
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[2])
for _p in (_ROOT, os.path.join(_ROOT, "lib"),
           os.path.join(_ROOT, "flows", "write-source", "script")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lib.boot as _boot  # noqa: E402
_boot.setup()
import check_exercise_coverage as cov  # noqa: E402


# ---------------------------------------------------------------------------
# 判据：印面标题词形
# ---------------------------------------------------------------------------
def test_label_recovers_one_letter_misread():
    """🔴 正向：`ExFRCISE 4.`（E→F 一个字母读歪）必须算印面标题。"""
    assert cov.printed_label('ExFRCISE 4.Derive (4.23) fron1 (4.21)') == 4


def test_label_keeps_existing_shapes():
    assert cov.printed_label('ExERcisE 3. Prove by the hyperbola method that') == 3
    assert cov.printed_label('EXERCISE 12. Let chi be a character') == 12
    assert cov.printed_label('ExERCisE8.Assume that L(f,s)') == 8


def test_label_rejects_body_text():
    """负向：正文行、无号、号在词前都不算标题。"""
    for s in ('The exercise 3 shows that',
              'EXERCISES of this chapter are hard',
              '5.14 Theorem. The series converges',
              'sin interchanged (see (23.451.2) of [GR]), we get',
              'PROPOSITION 4. Let x be'):
        assert cov.printed_label(s) is None, s


def test_label_rejects_cross_references_and_running_heads():
    """🔴 负向（跨 51 本书普查出的 100+ 处假阳，全部来自「词首+数字」这条放宽）。

    正文互引 / 书眉「EXERCISES 113」（词形 + 页码）都长得像标题；只有「数字后紧跟
    终止符」这一道能把它们挡掉，否则会把对的单元报成 MISSING。
    """
    for s in ('Exercise 6 shows that R is nonsingular if and only if A has full rank',
              'Exercises 13 and 14. In case (b), if q is a prime ideal of B such that',
              'EXERCISES   113',
              'Exercises 137',
              'Exercise 43 of Section 1.1). Hence, (p V q V r) is satisfiable',
              'Exercise 1o.4.1 In the situation of the lemma, show that',
              'Exercise 51 asks for a proof of this fact.'):
        assert cov.printed_label(s) is None, s


def test_label_tolerance_is_exactly_one():
    """负向：容差钉在 1 个字母，不随手放宽（两位读歪即不认）。"""
    assert cov.printed_label('EXWQCISD 4. whatever') is None


# ---------------------------------------------------------------------------
# 台账：写入方校验 + 读取/合并
# ---------------------------------------------------------------------------
def _fixture():
    """一章的假 extract 目录：p50-60，OCR 扫到 Ex1/Ex3，Ex5 标题整行漏扫。"""
    ext = tempfile.mkdtemp(prefix='excov_')
    bs = os.path.join(ext, 'book_structure')
    ud = os.path.join(bs, 'units', 'ch7')
    os.makedirs(ud)
    with open(os.path.join(bs, 'ch7.json'), 'w', encoding='utf-8') as f:
        json.dump({'key': '7', 'type': 'chapter', 'name': '7 Test chapter',
                   'page_start': 50, 'page_end': 60}, f)
    with open(os.path.join(ud, '0002_desc_D1.md'), 'w', encoding='utf-8') as f:
        f.write('# 7.1\n\n**Exercise 1.** Prove it.\n\n'
                '**Exercise 3.** Show it.\n\n**Exercise 5.** Derive it.\n')
    pages = {51: ['EXERCISE 1. Prove it.'], 53: ['ExFRCISE 3. Show it.']}
    for p in range(50, 61):
        blocks = [{'text': t, 'poly': [50.0, 100.0, 800.0, 100.0, 800.0, 130.0, 50.0, 130.0]}
                  for t in pages.get(p, [])]
        with open(os.path.join(ext, 'page_%03d.json' % p), 'w', encoding='utf-8') as f:
            json.dump({'text': blocks}, f)
    with open(os.path.join(ext, 'verify_config.json'), 'w', encoding='utf-8') as f:
        json.dump({'ch': {'ordinal': 3,
                          'formula': {'known_book': ['7.1']},
                          'content_overrides': []}}, f)
    return ext


def _att(ext, ch, ex, page, ev):
    return cov.write_attestation(ext, ch, ex, page, ev)


def test_attest_refuses_three_ways():
    ext = _fixture()
    try:
        code, msg = _att(ext, 7, 5, 58, '太短')
        assert code == 2 and 'evidence' in msg, msg
        code, msg = _att(ext, 7, 5, 499, '渲染后目视见 EXERCISE 5. 标题一行')
        assert code == 2 and '区间' in msg, msg
        code, msg = _att(ext, 7, 3, 53, '印面确有 EXERCISE 3. 标题一行')
        assert code == 2 and '多余' in msg, msg
        code, msg = _att(ext, 7, 9, 58, '印面确有 EXERCISE 9. 标题一行')
        assert code == 2 and '单元' in msg, msg
        assert cov.attested_printed(ext) == {}
    finally:
        shutil.rmtree(ext, ignore_errors=True)


def test_attest_accepts_real_ocr_hole_and_preserves_config():
    ext = _fixture()
    try:
        code, msg = _att(ext, 7, 5, 58, 'fitz 渲染 p58 目视：EXERCISE 5. Derive it 标题确在印面')
        assert code == 0, msg
        assert cov.attested_printed(ext, 7)[5]['page'] == 58
        cfg = json.load(open(os.path.join(ext, 'verify_config.json'), encoding='utf-8'))
        assert cfg['ch']['ordinal'] == 3
        assert cfg['ch']['formula']['known_book'] == ['7.1']
        assert len(cfg['ch']['exercise_printed_attested']) == 1
        # 重复登记拒绝（改判须先人工重核）
        code, msg = _att(ext, 7, 5, 59, '第二次登记同一号，须先人工重核印面')
        assert code == 2 and '已登记' in msg, msg
    finally:
        shutil.rmtree(ext, ignore_errors=True)


def test_attested_number_leaves_phantom_set():
    """检测/登记共用同一谓词：登记后该号不再是 PHANTOM，也不假造 MISSING。"""
    ext = _fixture()
    try:
        md = cov.md_heads(os.path.join(ext, 'book_structure', 'units', 'ch7'))
        pr = cov.printed_heads(ext, 7, 50, 60, set())
        # Ex1 正规词形、Ex3 靠编辑距离支抓到、Ex5 整行漏扫 → 只有 5 是 PHANTOM
        assert pr == {1: 51, 3: 53}, pr
        assert md == {1, 3, 5}, md
        assert sorted(md - set(pr)) == [5]
        code, msg = _att(ext, 7, 5, 58, 'fitz 渲染 p58 目视：EXERCISE 5. 标题确在印面')
        assert code == 0, msg
        printed = cov.merge_printed(pr, cov.attested_printed(ext, 7))
        assert sorted(printed) == [1, 3, 5], printed
        assert not (md - set(printed)) and not (set(printed) - md)
    finally:
        shutil.rmtree(ext, ignore_errors=True)


def test_page_texts_survives_foreign_page_shapes():
    """🔴 负向（跨书普查实测崩过）：`text` 项形状怪异时只跳过、绝不抛。

    审计一趟要读全书每页的 `page_*.json`；某些书的 `text` 项是嵌套 dict（不是 str）
    或干脆是裸字符串。一处形状意外就把整本书的练习审计打崩 = 覆盖闸永久失明，
    比漏一题严重得多。
    """
    ext = _fixture()
    try:
        fp = os.path.join(ext, 'page_052.json')
        with open(fp, 'w', encoding='utf-8') as f:
            json.dump({'text': [
                {'text': {'blocks': [{'text': 'nested dict from another book'}]}},
                'bare string item',
                {'no_text_key': 1},
                {'text': None},
                {'text': 'EXERCISE 2. The one good line'},
            ]}, f)
        got = cov.page_texts(ext, 52)
        assert got == ['EXERCISE 2. The one good line'], got
        # 同一页喂给判据链也不崩
        assert cov.printed_heads(ext, 7, 50, 60, set()) == {1: 51, 2: 52, 3: 53}
    finally:
        shutil.rmtree(ext, ignore_errors=True)


if __name__ == '__main__':
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            try:
                fn()
                print('PASS %s' % name)
            except AssertionError as e:
                fails += 1
                print('FAIL %s: %s' % (name, e))
    print('EXERCISE COVERAGE TESTS:', 'FAIL' if fails else 'PASS')
    sys.exit(1 if fails else 0)
