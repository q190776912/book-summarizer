# -*- coding: utf-8 -*-
"""test_appendix_config_logic.py — 附录章/共享计数器相关判定逻辑的单元测试。

覆盖 2026-09 附录支持引入的判定面：
  * chapter_label / chapter_json_name / unit_dir_name（数字章 ch{N}、附录 appendix{X}）
  * make_config._contract_counter_evidence（同号去重、字母章跳过）
  * make_config._shares_main_counter（strict_reset 两档：共享计数器合并、平行计数器拆分）
  * make_config._parse_comps 字母章位解析
  * check_structure_completeness._canon_key(ORDINAL_APP)
  * structure_io.read_structure_items 的附录键规范化（字母章位 → 定义A.S-N）
"""
import json
import os
import re
from pathlib import Path

import pytest

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
import lib.boot as _boot
_boot.setup()

from data.book_structure.book_structure import (chapter_json_name, chapter_label,
                                                unit_dir_name)
import make_config as mc
import verify_config as vc
from verify_config import ORDINAL_APP


# ---------------------------------------------------------------------------
# chapter_label / 文件名
# ---------------------------------------------------------------------------
def test_chapter_label_numeric_and_appendix():
    assert chapter_label(3) == "ch3"
    assert chapter_label("10") == "ch10"
    assert chapter_label("A") == "appendixA"
    assert chapter_label("B") == "appendixB"


def test_chapter_json_name_and_unit_dir():
    assert chapter_json_name(11) == "ch11.json"
    assert chapter_json_name("A") == "appendixA.json"
    assert unit_dir_name(2) == "ch2"
    assert unit_dir_name("A") == "appendixA"


# ---------------------------------------------------------------------------
# _contract_counter_evidence：去重 + 字母章跳过
# ---------------------------------------------------------------------------
def _write_contract(ext, chapters):
    os.makedirs(os.path.join(ext, "book_structure"), exist_ok=True)
    for ch, items in chapters.items():
        node = {"key": ch, "type": "chapter", "name": f"{ch} T",
                "page_start": 1, "page_end": 9, "sub_sec": items}
        fn = f"ch{ch}.json" if str(ch)[:1].isdigit() else f"appendix{ch}.json"
        with open(os.path.join(ext, "book_structure", fn), "w",
                  encoding="utf-8") as f:
            json.dump(node, f, ensure_ascii=False)


def _item(key, typ, name=""):
    return {"key": key, "type": typ, "name": name or key,
            "page_start": 1, "page_end": 1, "sub_sec": []}


def test_contract_evidence_dedup_and_letter_skip(tmp_path):
    ext = str(tmp_path)
    # 同号不同族（Corollary 9.3-3 与 Theorem 9.3-3，来自深层子项展平）→ 去重保留首个
    # 附录字母章（A）整体跳过。
    _write_contract(ext, {
        9: [_item("9.3-3", "theorem"), _item("9.3-3", "corollary"),
            _item("9.3-4", "lemma")],
        "A": [_item("A.1-1", "definition")],
    })
    ev = mc._contract_counter_evidence(ext)
    assert ev is not None
    assert ("Theorem", (9, 3, 3)) in ev
    assert ("Corollary", (9, 3, 3)) not in ev      # 同号去重
    assert all(comps[0] != "A" for _, comps in ev)  # 字母章跳过
    assert ("Lemma", (9, 3, 4)) in ev


def test_contract_evidence_none_without_contract(tmp_path):
    assert mc._contract_counter_evidence(str(tmp_path)) is None


# ---------------------------------------------------------------------------
# _shares_main_counter：strict_reset 两档
# ---------------------------------------------------------------------------
def test_shares_main_counter_shared_counter_merges():
    # 共享计数器书：不同标签在同窗交错且无重复 → 合并（两档一致）
    ref = [("Theorem", (10, 3, 2)), ("Theorem", (10, 3, 5))]
    cand = [("Definition", (10, 3, 4))]
    assert mc._shares_main_counter([c for _, c in cand],
                                   [c for _, c in ref],
                                   strict_reset=True) is True
    assert mc._shares_main_counter([c for _, c in cand],
                                   [c for _, c in ref],
                                   strict_reset=False) is True


def test_shares_main_counter_strict_reset_false_merges_opener_family():
    # 共享计数器书，候选族 owns 窗口首号（min==1）而参考族在该窗从 2 起：
    # strict_reset=True（OCR 路径）误拆；strict_reset=False（契约路径）合并。
    ref = [("Theorem", (10, 3, 2)), ("Theorem", (10, 3, 5))]
    cand = [("Definition", (10, 3, 1)), ("Definition", (10, 3, 4))]
    assert mc._shares_main_counter([c for _, c in cand],
                                   [c for _, c in ref]) is False
    assert mc._shares_main_counter([c for _, c in cand],
                                   [c for _, c in ref],
                                   strict_reset=False) is True


def test_shares_main_counter_duplicate_splits_exercise_family():
    # 平行计数器：练习 10.3.1 与 Definition 10.3.1 同窗同号 → 拆分（两档一致）
    ref = [("Definition", (10, 3, 1)), ("Definition", (10, 3, 2))]
    cand = [("Exercise", (10, 3, 1)), ("Exercise", (10, 3, 2))]
    assert mc._shares_main_counter([c for _, c in cand],
                                   [c for _, c in ref]) is False
    assert mc._shares_main_counter([c for _, c in cand],
                                   [c for _, c in ref],
                                   strict_reset=False) is False


# ---------------------------------------------------------------------------
# _parse_comps 字母章位
# ---------------------------------------------------------------------------
def test_parse_comps_letter_chapter():
    assert mc._parse_comps("A.1.1", letter_chapter=True) == ("A", 1, 1)
    assert mc._parse_comps("A.1", letter_chapter=True) == ("A", 1)
    # 非字母章位路径不认字母首段
    assert mc._parse_comps("A.1.1", letter_chapter=False) is None
    assert mc._parse_comps("1.2.3") == (1, 2, 3)


# ---------------------------------------------------------------------------
# _canon_key(ORDINAL_APP) + 练习号豁免正则
# ---------------------------------------------------------------------------
def test_canon_key_app_letter_forms():
    import check_structure_completeness as csc
    assert csc._canon_key(ORDINAL_APP, "A.1-1") == ("A", 1, 1)
    assert csc._canon_key(ORDINAL_APP, "A.1.1") == ("A", 1, 1)
    assert csc._canon_key(ORDINAL_APP, "A.1") == ("A", 1)
    assert csc._canon_key(ORDINAL_APP, "1.1-1") is None  # 数字键不归 APP canon


def test_exercise_gap_exemption_regex():
    # 与 step4_gate 同源的正则：从 blocking 行提取 (节, 号)
    rx = re.compile(r"(\d+(?:\.\d+)*)\s*缺号\s*(\d+)")
    line = "  WARN (BLOCKING): 0:10.3 缺号 5（序列 4..7 不连续 — 严格模式）"
    m = rx.search(line)
    assert m and (m.group(1), m.group(2)) == ("10.3", "5")


# ---------------------------------------------------------------------------
# structure_io.read_structure_items 附录键规范化
# ---------------------------------------------------------------------------
def test_read_structure_items_app_key_canon(tmp_path):
    from verify.script.structure_io import read_structure_items
    ext = str(tmp_path)
    _write_contract(ext, {
        "A": [_item("A.1-1", "definition", "A.1-1 A.1.1 A category"),
              _item("A.1-2", "exercise", "Exercise A.1.1")],
    })
    items = read_structure_items(ext, "A", primary_type=ORDINAL_APP)
    keys = [it["key"] for it in items]
    # 练习被排除（include_exercise=False）；Definition → 定义A.1-1
    assert keys == ["定义A.1-1"]
