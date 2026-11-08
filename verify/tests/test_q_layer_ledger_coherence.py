"""Q 层「书侧配对账本自洽率」闸的判据回归（2026-11-08 线性系统根治）。

判据：`tag_formula_pairing.ledger_coherence` 量「整章书侧账本能否自证」，
低于 `LEDGER_COHERENCE_MIN` 时 Q 层三个 WARN 支按「无证据不判」降级。
本文件锁住三件事：
  1. 纯函数口径（干净账本高 / 烂账本低 / 样本不足不降级）；
  2. 闸只减少告警、绝不新增，且 **关掉闸必须复现真 TAG_MISMATCH**（负向锁，
     防止把真移位一起静音）；
  3. `ncomp == 1` 与「不传 coherence」的直接调用保持 OLD 行为。
"""
import os
import sys
from pathlib import Path
from unittest import mock

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[2])
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot
lib.boot.setup()

import tag_formula_pairing as tfp


def _printed_clean():
    return {
        "1.1": ["a" * 24, "b" * 24],
        "1.2": ["c" * 24, "d" * 24],
        "1.3": ["e" * 24, "f" * 24],
        "1.4": ["g" * 24, "h" * 24],
        "1.5": ["i" * 24, "j" * 24],
        "1.6": ["k" * 24, "l" * 24],
        "1.7": ["m" * 24, "n" * 24],
        "1.8": ["o" * 24, "p" * 24],
    }


def test_clean_ledger_is_coherent():
    printed = _printed_clean()
    summary = [(n, v[0]) for n, v in printed.items()]
    rate = tfp.ledger_coherence(printed, summary)
    assert rate == 1.0, rate


def test_corrupt_ledger_is_incoherent():
    printed = _printed_clean()
    # 每一号的印面账身都被 OCR 读成与总结正文无关的另一串
    summary = [(n, "z" * 24) for n in printed]
    rate = tfp.ledger_coherence(printed, summary)
    assert rate == 0.0, rate
    assert rate < tfp.LEDGER_COHERENCE_MIN


def test_too_few_samples_does_not_degrade():
    printed = _printed_clean()
    summary = [(n, v[0]) for n, v in list(printed.items())[:3]]
    assert tfp.ledger_coherence(printed, summary) is None
    assert tfp.ledger_coherence({}, []) is None


def test_threshold_is_between_real_books():
    # 线性系统 0.191~0.476 / 对照书最低 0.592（analytic-NT ch26）
    assert 0.476 < tfp.LEDGER_COHERENCE_MIN < 0.592


def _shifted_scenario():
    """构造一例**真** TAG_MISMATCH：1.1 那格装了 1.2 的式子，反之亦然。"""
    printed = {
        "1.1": ["aaaaaaaaaaaaaaaaaaaaaaaa"],
        "1.2": ["bbbbbbbbbbbbbbbbbbbbbbbb"],
        "1.3": ["cccccccccccccccccccccccc"],
    }
    summary = [
        ("1.1", "bbbbbbbbbbbbbbbbbbbbbbbb"),
        ("1.2", "aaaaaaaaaaaaaaaaaaaaaaaa"),
        ("1.3", "cccccccccccccccccccccccc"),
    ]
    return printed, summary


def test_low_coherence_gate_returns_empty():
    printed, summary = _shifted_scenario()
    with mock.patch.object(tfp, "summary_tag_bodies", return_value=summary):
        rows = tfp.pairing_problems(
            "", 1, 1, 1, "dummy.md", ncomp=2, printed=printed,
            ledger_coherence_val=0.20)
    assert rows == []


def test_high_coherence_still_reports_real_mismatch():
    """负向锁：账本自洽率达标时必须照常报出真错位，闸不得吃掉真缺陷。"""
    printed, summary = _shifted_scenario()
    with mock.patch.object(tfp, "summary_tag_bodies", return_value=summary):
        rows = tfp.pairing_problems(
            "", 1, 1, 1, "dummy.md", ncomp=2, printed=printed,
            ledger_coherence_val=0.90)
    assert any(r["status"] == "TAG_MISMATCH" for r in rows), rows


def test_default_call_is_unchanged():
    """不传 coherence 的直接调用 = OLD 行为（既有测试/普查脚本零回归）。"""
    printed, summary = _shifted_scenario()
    with mock.patch.object(tfp, "summary_tag_bodies", return_value=summary):
        rows = tfp.pairing_problems(
            "", 1, 1, 1, "dummy.md", ncomp=2, printed=printed)
    assert any(r["status"] == "TAG_MISMATCH" for r in rows), rows


def test_ncomp1_short_circuit_unchanged():
    with mock.patch.object(tfp, "summary_tag_bodies") as m:
        rows = tfp.pairing_problems(
            "", 1, 1, 1, "dummy.md", ncomp=1, printed=_printed_clean(),
            ledger_coherence_val=0.0)
    assert rows == []
    m.assert_not_called()
