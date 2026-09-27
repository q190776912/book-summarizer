"""test_sync_translate_markers.py — 首行复位工具的三条机械判据（CRLF 判定 + 契约裁决）。

两条都是实测踩过的坑：
1. 🔴 **CRLF**：`raw.split(b"\\n",1)[0]` 已经把换行符当分隔吃掉，段内**永远**不含 CRLF，
   用 `in` 判行尾会恒定得出 LF，于是首行留着一个 CR 参与比较——dry-run 时把整本书
   （real-analysis 1560 文件里 757 个、Robinson 全部 1644 个）误报成「脱账」。
2. 🔴 **manifest 不是永远是对的一侧**：Robinson 动力学 `ch3/0051_section_3_6` 的
   manifest `name=3.6 Substitutions2`（多一个 2），而**契约与单元首行都是正确的**
   `3.6 Substitutions`。无脑按 manifest 复位 = 把对的一侧改成错的，故工具必须先按契约
   裁决，manifest 与契约脱账者只报告不动盘。
"""
import io
import json
import os
import sys
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[3])
for _p in (_ROOT, os.path.join(_ROOT, "lib"), os.path.join(_ROOT, "tools"),
           os.path.join(_ROOT, "flows", "write-source", "script")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

import sync_translate_markers as stm  # noqa: E402

LINE = ("<!-- book-summarizer DONE unit: id=0001 type=item key=1.1 "
        "name=1.1 Definition -->")
REC = {"id": "0001", "type": "item", "key": "1.1", "name": "1.1 Definition",
       "file": "0001_item_x.md"}


def _mk(p, line, eol="\n", body="**定义 1.1**：正文。\n"):
    with open(p, "wb") as f:
        f.write((line + eol + body).encode("utf-8"))
    return p


# ── 1) CRLF 判定 ──────────────────────────────────────────────────────────

def test_crlf_matching_marker_is_not_a_diff(tmp_path):
    p = _mk(str(tmp_path / "u.md"), LINE, eol="\r\n")
    assert b"\r\n" in open(p, "rb").read()
    assert stm._diff(p, REC) is None, "CRLF 首行被误判脱账（CR 参与了比较）"


def test_lf_matching_marker_is_not_a_diff(tmp_path):
    assert stm._diff(_mk(str(tmp_path / "u.md"), LINE), REC) is None


def test_single_line_file_without_trailing_newline(tmp_path):
    p = str(tmp_path / "u.md")
    with open(p, "wb") as f:
        f.write(LINE.encode("utf-8"))
    assert stm._diff(p, REC) is None


def test_drifted_name_reports_expected_line(tmp_path):
    p = _mk(str(tmp_path / "u.md"), LINE.replace("name=1.1 Definition", "name=1.1 Def"))
    r = stm._diff(p, REC)
    assert r and r[2] != r[3] and r[3].endswith("name=1.1 Definition -->"), r
    assert r[1] == b"\n"


# ── 2) 契约裁决（真值 = 契约 → manifest → 首行）────────────────────────────

def _book(tmp_path, manifest_name, marker_name):
    ext = tmp_path / "ex"
    d = ext / "book_structure" / "units" / "ch1"
    d.mkdir(parents=True)
    json.dump({"chapters": [{"key": "1", "name": "Chapter 1", "children": [
        {"key": "1.1", "name": "1.1 Definition", "items": []}]}]},
        io.open(str(ext / "book_structure" / "ch1.json"), "w", encoding="utf-8"),
        ensure_ascii=False)
    rec = dict(REC, name=manifest_name)
    json.dump({"units": [rec]}, io.open(str(d / "manifest.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    _mk(str(d / REC["file"]),
        marker_name, eol="\r\n")
    return str(ext)


def test_manifest_agreeing_with_contract_repairs_the_file(tmp_path):
    ext = _book(tmp_path, "1.1 Definition", "<!-- book-summarizer DONE unit: id=0001 type=item key=1.1 name=1.1 Definitio -->")
    c, m, diffs = stm.sync_side(ext, "units", "1", apply_changes=True)
    assert (c, m) == (1, 1), diffs
    line = io.open(os.path.join(ext, "book_structure/units/ch1", REC["file"]),
                   encoding="utf-8").readline().rstrip("\r\n")
    assert line == LINE and stm._diff(
        os.path.join(ext, "book_structure/units/ch1", REC["file"]), REC) is None


def test_manifest_contradicting_contract_is_never_written(tmp_path):
    """Robinson `Substitutions2` 形：manifest 错、首行对 → 只报告，不动盘。"""
    good = "<!-- book-summarizer DONE unit: id=0001 type=item key=1.1 name=1.1 Definition -->"
    ext = _book(tmp_path, "1.1 DefinitionX", good)
    p = os.path.join(ext, "book_structure/units/ch1", REC["file"])
    c, m, diffs = stm.sync_side(ext, "units", "1", apply_changes=True)
    assert m == 0 and len(diffs) == 1, diffs
    assert "跳过" in diffs[0]
    assert io.open(p, encoding="utf-8").readline().rstrip("\r\n") == good, "把对的一侧改坏了"


def test_body_bytes_untouched_after_repair(tmp_path):
    ext = _book(tmp_path, "1.1 Definition",
                "<!-- book-summarizer DONE unit: id=0001 type=item key=1.1 name=WRONG -->")
    p = os.path.join(ext, "book_structure/units/ch1", REC["file"])
    before = open(p, "rb").read()
    stm.sync_side(ext, "units", "1", apply_changes=True)
    after = open(p, "rb").read()
    assert after.split(b"\r\n", 1)[1] == before.split(b"\r\n", 1)[1], "正文/行尾被改动"


# ── 3) type 归一裁决（real-analysis ch22/0014 形）───────────────────────────

def _book_type(tmp_path, manifest_type, marker_type, contract_type="description"):
    """契约节点 type=`description`（拆分时归一成 `desc`），两侧 type 各给一个。"""
    ext = tmp_path / "ex"
    d = ext / "book_structure" / "units" / "ch1"
    d.mkdir(parents=True)
    json.dump({"chapters": [{"key": "1", "name": "Chapter 1", "children": [
        {"key": "1.1", "name": "", "type": contract_type, "items": []}]}]},
        io.open(str(ext / "book_structure" / "ch1.json"), "w", encoding="utf-8"),
        ensure_ascii=False)
    rec = dict(REC, name="", type=manifest_type, key="1.1")
    json.dump({"units": [rec]}, io.open(str(d / "manifest.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    line = ("<!-- book-summarizer DONE unit: id=0001 type=%s key=1.1 name= -->"
            % marker_type)
    _mk(str(d / REC["file"]), line, eol="\r\n")
    return str(ext)


def test_manifest_type_not_normalized_is_never_written(tmp_path):
    """🔴 契约 description→desc 归一在 manifest 里漏做：错的一侧是 manifest，首行不得改。"""
    ext = _book_type(tmp_path, manifest_type="description", marker_type="desc")
    p = os.path.join(ext, "book_structure/units/ch1", REC["file"])
    good = "<!-- book-summarizer DONE unit: id=0001 type=desc key=1.1 name= -->"
    c, m, diffs = stm.sync_side(ext, "units", "1", apply_changes=True)
    assert (c, m) == (1, 0), diffs
    assert len(diffs) == 1 and "type 脱账" in diffs[0] and "首行才是契约那一侧" in diffs[0], diffs
    assert io.open(p, encoding="utf-8").readline().rstrip("\r\n") == good, "把归一对的首行改回未归一"


def test_marker_type_that_ignores_contract_is_repaired(tmp_path):
    """反向：首行写成契约没有的乱值、manifest 才是归一后的真值 → 复位首行。"""
    ext = _book_type(tmp_path, manifest_type="desc", marker_type="description")
    c, m, diffs = stm.sync_side(ext, "units", "1", apply_changes=True)
    assert (c, m) == (1, 1), diffs
    p = os.path.join(ext, "book_structure/units/ch1", REC["file"])
    line = io.open(p, encoding="utf-8").readline().rstrip("\r\n")
    assert line == "<!-- book-summarizer DONE unit: id=0001 type=desc key=1.1 name= -->"


def test_unknown_contract_key_skips_conservatively(tmp_path):
    """契约里查不到该键（老书契约残缺）→ 无法裁定，宁可跳过不误写。"""
    ext = _book_type(tmp_path, manifest_type="item", marker_type="desc",
                    contract_type="theorem")
    json.dump({"units": [dict(REC, name="", type="item", key="9.9")]},
              io.open(os.path.join(ext, "book_structure/units/ch1/manifest.json"),
                      "w", encoding="utf-8"), ensure_ascii=False)
    c, m, diffs = stm.sync_side(ext, "units", "1", apply_changes=True)
    assert (c, m) == (1, 0) and "两侧均不在契约账上" in diffs[0], diffs
