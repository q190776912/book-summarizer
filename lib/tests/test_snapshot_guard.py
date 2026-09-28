"""tests for lib.snapshot_guard (mark 时快照 + 已完成步证据复演).

背景（负向测试要钉住的行为，全部来自 2026-09-28 Apostol IANT 事故：一个子代理
`rm -rf` 抹掉整棵书树，台账却仍然显示步骤 5 已收官，55 分钟内没有任何机械告警）：

  * 快照必须覆盖**重跑代价最高**的产物：`book_structure/`（契约 + units +
    units-translate + manifest）、`_extract` 顶层 JSON/MD、台账、书目录根级章 md；
  * `page_*.json` / 图像目录只进 `.full` 快照（默认不 archive，避免每次 mark 复制几十 MB）；
  * `_snapshots/` 里只允许本模块自己的归档被修剪，修剪数量有上限；
  * ``audit`` 只复演**台账里 DONE** 且**有证据谓词**的步：无谓词（agent 自证）跳过，
    未完成步不查，产物消失的步必须报出来——这就是缺失的那道告警。
"""
import glob
import json
import os
import shutil
import tarfile
import tempfile

import lib.boot as b
b.setup()

from lib import snapshot_guard as sg  # noqa: E402
from lib.flow_gate import mark as gate_mark, status as gate_status  # noqa: E402


def _book(tmp, pages=True, units=True, root_md=True):
    ext = os.path.join(tmp, "_extract")
    os.makedirs(ext, exist_ok=True)
    if units:
        u = os.path.join(ext, "book_structure", "units", "ch1")
        os.makedirs(u, exist_ok=True)
        with open(os.path.join(u, "0001_item_定理1_1.md"), "w", encoding="utf-8") as f:
            f.write("<!-- book-summarizer DONE unit -->\n**定理 1.1** $p\\mid a$\n")
        with open(os.path.join(ext, "book_structure", "ch1.json"), "w", encoding="utf-8") as f:
            json.dump({"key": "1", "type": "chapter", "sub_sec": []}, f)
    with open(os.path.join(ext, "chapter_map.json"), "w", encoding="utf-8") as f:
        json.dump({"chapters": [{"ch": 1, "name": "X"}]}, f)
    with open(os.path.join(ext, ".flow_gate.json"), "w", encoding="utf-8") as f:
        json.dump({"steps": {}}, f)
    if pages:
        for i in (1, 2):
            with open(os.path.join(ext, "page_%03d.json" % i), "w", encoding="utf-8") as f:
                json.dump({"text": []}, f)
        fig = os.path.join(ext, "figure")
        os.makedirs(fig, exist_ok=True)
        with open(os.path.join(fig, "ch1_fig1.png"), "wb") as f:
            f.write(b"\x89PNG\r\n")
    if root_md:
        with open(os.path.join(tmp, "Chapter1_X.md"), "w", encoding="utf-8") as f:
            f.write("# Chapter 1\n")
    return tmp, ext


def _names(path):
    with tarfile.open(path, "r:gz") as tf:
        return sorted(m.name for m in tf.getmembers() if m.isfile())


# ------------------------------------------------------------------ snapshot contents
def test_lite_snapshot_covers_units_and_skips_ocr():
    tmp = tempfile.mkdtemp()
    try:
        book, ext = _book(tmp)
        dest = sg.snapshot(book, ext, "write_source.draft")
        assert dest and os.path.isfile(dest)
        names = _names(dest)
        assert any("units/ch1/" in n for n in names), names
        assert any(n.endswith("ch1.json") for n in names), names
        assert any(n == "chapter_map.json" for n in names), names
        assert any(n.startswith("_book_root/") for n in names), names
        assert not any("page_00" in n for n in names), names
        assert not any("figure/" in n for n in names), names
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_full_snapshot_includes_ocr_and_figures():
    tmp = tempfile.mkdtemp()
    try:
        book, ext = _book(tmp)
        dest = sg.snapshot(book, ext, "extract.mm_repair.full")
        names = _names(dest)
        assert any(n.startswith("page_") and n.endswith(".json") for n in names), names
        assert any("figure/ch1_fig1.png" in n for n in names), names
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_prune_only_touches_its_own_archives():
    tmp = tempfile.mkdtemp()
    try:
        book, ext = _book(tmp)
        sd = os.path.join(ext, sg.SNAP_SUBDIR)
        os.makedirs(sd, exist_ok=True)
        with open(os.path.join(sd, "keepme.txt"), "w", encoding="utf-8") as f:
            f.write("not mine")
        for _ in range(sg.KEEP_LITE + 3):
            sg.snapshot(book, ext, "write_source.draft")
        group = glob.glob(os.path.join(sd, "*_write_source.draft.tar.gz"))
        assert len(group) <= sg.KEEP_LITE, len(group)
        assert os.path.isfile(os.path.join(sd, "keepme.txt"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------------ audit
def _predicate(marker_name):
    def fn(book_dir, extract_dir):
        ok = os.path.isfile(os.path.join(extract_dir, marker_name))
        return ok, ("present" if ok else "missing %s" % marker_name)
    return fn


def _check_fn(evidence_map):
    def fn(flow, step, book_dir, extract_dir):
        return evidence_map["%s.%s" % (flow, step)](book_dir, extract_dir)
    return fn


def test_audit_flags_deleted_artifacts_only_for_done_steps():
    tmp = tempfile.mkdtemp()
    try:
        book, ext = _book(tmp)
        ev = {
            "write_source.draft": _predicate("marker_draft.txt"),
            "write_source.structure": _predicate("marker_struct.txt"),
            "prep.env": None,                       # agent 自证 → 永不参与复演
            "write_source.config": _predicate("marker_config.txt"),
        }
        gate_mark(book, "write_source", "draft", extract_dir=ext)
        gate_mark(book, "write_source", "structure", extract_dir=ext)
        # draft 的产物在位，structure 的产物已被抹掉；config 未 DONE 故不查
        with open(os.path.join(ext, "marker_draft.txt"), "w", encoding="utf-8") as f:
            f.write("x")
        bad = sg.audit(book, ext, gate_status, ev, _check_fn(ev))
        assert [s for s, _ in bad] == ["write_source.structure"], bad
        assert "missing" in bad[0][1]
        # 恢复后复演应当干净
        with open(os.path.join(ext, "marker_struct.txt"), "w", encoding="utf-8") as f:
            f.write("x")
        assert sg.audit(book, ext, gate_status, ev, _check_fn(ev)) == []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_restore_hint_points_at_newest_archive():
    tmp = tempfile.mkdtemp()
    try:
        book, ext = _book(tmp)
        assert "无快照" in sg.restore_hint(ext)
        d1 = sg.snapshot(book, ext, "write_source.draft")
        d2 = sg.snapshot(book, ext, "write_source.merge_source")
        hint = sg.restore_hint(ext)
        assert d2 in hint and d1 not in hint, hint
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
