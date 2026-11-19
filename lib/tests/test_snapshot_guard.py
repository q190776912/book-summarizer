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


# ------------------------------------------- lightweight presence projection (audit fix)
# 背景：discrete-mathematics-8th（2146 单元）上 `flow_runner audit` 因逐步重跑四个
# 重量级 EVIDENCE 谓词（单元质量门控 ~190s / 翻译同构闸 ~330s / 两次 verify --all
# ~70s each）而十分钟不返回，形同死锁。audit/status/mark 前置护栏改走轻量产物在位
# 投影；落账当下仍由 EVIDENCE 深度判定。下列测试钉住两条不变量。


def test_presence_evidence_is_a_projection_of_evidence():
    from flows._flow_contract import EVIDENCE, PRESENCE_EVIDENCE
    # 步骤集合必须完全一致（否则 audit 覆盖不到某些 DONE 步）
    assert set(PRESENCE_EVIDENCE) == set(EVIDENCE)
    # 轻量步骤直接复用同一函数对象，杜绝判据漂移
    reused = ("extract.extract_text", "extract.mm_repair", "write_source.config",
              "write_source.build_chapter_map", "write_source.figure_detection",
              "write_source.structure", "write_source.draft")
    for k in reused:
        assert PRESENCE_EVIDENCE[k] is EVIDENCE[k], k
    # 四个重步必须换成轻量投影，不能还是深度函数
    heavy = ("write_source.write_chapters", "write_source.merge_source",
             "write_source.translate_chapters", "write_source.merge_translation")
    for k in heavy:
        assert PRESENCE_EVIDENCE[k] is not EVIDENCE[k], k


def _presence_book(tmp, lang=None, translated=False):
    """造一本最小书：chapter_map + units(/units-translate) manifest + 单元文件。"""
    ext = os.path.join(tmp, "_extract")
    bs = os.path.join(ext, "book_structure")
    ud = os.path.join(bs, "units", "ch1")
    os.makedirs(ud, exist_ok=True)
    with open(os.path.join(ext, "chapter_map.json"), "w", encoding="utf-8") as f:
        json.dump({"chapters": [{"num": 1, "name": "X"}]}, f)
    unit = os.path.join(ud, "0001_item_x.md")
    with open(unit, "w", encoding="utf-8") as f:
        f.write("**定理 1.1**\n")
    with open(os.path.join(ud, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump({"language": lang, "units": [{"file": "0001_item_x.md",
                                                "type": "item", "key": "1.1"}]}, f)
    tunit = None
    if translated:
        td = os.path.join(bs, "units-translate", "ch1")
        os.makedirs(td, exist_ok=True)
        tunit = os.path.join(td, "0001_item_x.md")
        with open(tunit, "w", encoding="utf-8") as f:
            f.write("**Theorem 1.1**\n")
        with open(os.path.join(td, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"units": [{"file": "0001_item_x.md",
                                  "type": "item", "key": "1.1"}]}, f)
    return tmp, ext, unit, tunit


def test_presence_write_chapters_flags_deleted_unit_without_running_quality_gate(monkeypatch):
    from flows import _flow_contract as fc
    tmp = tempfile.mkdtemp()
    try:
        book, ext, unit, _ = _presence_book(tmp)
        # 深度门控若被触发就炸——轻量投影绝不该调用它
        def explode(*a, **kw):
            raise AssertionError("presence 不应调用 _units_gate_ok")
        monkeypatch.setattr(fc.physical_evidence, "_units_gate_ok", explode)

        ok, detail = fc.check_presence("write_source", "write_chapters", book, ext)
        assert ok, detail
        os.remove(unit)
        ok, detail = fc.check_presence("write_source", "write_chapters", book, ext)
        assert not ok and "单元文件" in detail, detail
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_presence_translate_flags_deleted_translated_unit(monkeypatch):
    from flows import _flow_contract as fc
    tmp = tempfile.mkdtemp()
    try:
        book, ext, _, tunit = _presence_book(tmp, lang="en", translated=True)
        def explode(*a, **kw):
            raise AssertionError("presence 不应调用 check_translate_parity subprocess")
        monkeypatch.setattr(fc.subprocess, "call", explode)

        ok, detail = fc.check_presence("write_source", "translate_chapters", book, ext)
        assert ok, detail
        os.remove(tunit)
        ok, detail = fc.check_presence("write_source", "translate_chapters", book, ext)
        assert not ok and "译文单元文件" in detail, detail
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_flow_runner_audit_defaults_to_presence_deep_is_optin():
    import importlib.util
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "tools", "flow_runner.py")
    spec = importlib.util.spec_from_file_location("flow_runner_under_test", path)
    fr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fr)
    ev, chk = fr._evidence_for(False)
    from flows._flow_contract import PRESENCE_EVIDENCE, check_presence
    assert ev is PRESENCE_EVIDENCE and chk is check_presence
    ev, chk = fr._evidence_for(True)
    from flows._flow_contract import EVIDENCE, check_evidence
    assert ev is EVIDENCE and chk is check_evidence
