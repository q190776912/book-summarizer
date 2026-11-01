"""test_sync_unit_from_delivery.py — 「交付对、单元错」的整块回灌通道（正负向判据）。

场景（2026-10-30 数值分析 11 处实测）：收官书禁重 merge，单元正文却留着写源期的 OCR 残渣／
串挂，而交付 md 后来按印面清理过。合法出口只有「让单元重新成为交付的逐字镜像」这一条，
但它抹的是**单元侧的行**，所以判据必须拦住「跨度圈不住的内容被静默抹掉」。

🔴 本文件守的核心负向 = `--span` 取短了：对照集若是**整份交付**，一句只存在于跨度之外的
行会「在交付里找得到」→ 闸放行 → 写盘把该行从单元里永久删掉（首轮实测：ch6 定理12 少圈
4 行，dry-run 照样「1 条 / 拒绝 0 条」）。修 = 对照集改按**跨度**，另把「该句在交付 L 几」
打进拒绝消息，让下一个人去改跨度而不是补 `--evidence`。
"""
import io
import json
import os
import sys
import tempfile
import unittest
import importlib.util
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "lib"))
import lib.boot as _boot  # noqa: E402
_boot.setup()

_SPEC = importlib.util.spec_from_file_location(
    "sync_unit_from_delivery",
    os.path.join(_ROOT, "tools", "sync_unit_from_delivery.py"))
sud = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(sud)

MARK1 = "<!-- book-summarizer DONE unit: id=0001 type=item key=定理1 name=定理1 -->"
MARK2 = "<!-- book-summarizer DONE unit: id=0002 type=desc key=说明 name=说明 -->"
TAIL = "   故该分解在单位下三角约束下唯一，证毕。"
MD_NAME = "第2章_插值.md"

# 交付 md：L1..L7 = 定理1 的跨度，L9 是 merge 的结构件 `---`，L11 起是下一条。
MD_LINES = [
    "**定理1** 设 $A$ 为正定矩阵，则存在唯一的分解。",   # 1
    "",                                                # 2
    "> $$",                                            # 3
    ">    A = L L^{\\mathrm{T}}. \\tag{1.1}",          # 4
    "> $$",                                            # 5
    "",                                                # 6
    TAIL,                                              # 7
    "",                                                # 8
    "---",                                             # 9
    "",                                                # 10
    "**定理2** 另一条定理，其条头在交付里另起一段。",     # 11
]


def _unit_body(extra=()):
    return "\n".join([MARK1, ""] + MD_LINES[:7] + list(extra)) + "\n"


def _w(path, text):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def _mk(book, unit_text=_unit_body(), manifest=None):
    """→ (extract_dir, unit_path)。`manifest=None` 时用默认两条记录。"""
    ext = os.path.join(book, "_extract")
    bs = os.path.join(ext, "book_structure")
    udir = os.path.join(bs, "units", "ch2")
    _w(os.path.join(book, MD_NAME), "\n".join(MD_LINES) + "\n")
    _w(os.path.join(bs, "ch2.json"), json.dumps(
        {"key": "2", "type": "chapter", "name": "2 插值", "sub_sec": []},
        ensure_ascii=False, indent=2))
    _w(os.path.join(udir, "0001_item_定理1.md"), unit_text)
    _w(os.path.join(udir, "manifest.json"), json.dumps(
        manifest if manifest is not None else
        {"language": "zh-CN", "units": [
            {"id": "0001", "file": "0001_item_定理1.md", "type": "item",
             "ntype": "theorem", "key": "定理1", "name": "定理1"},
            {"id": "0002", "file": "0002_desc_说明.md", "type": "desc",
             "ntype": "desc", "key": "说明", "name": "说明"}]},
        ensure_ascii=False, indent=2))
    return ext, os.path.join(udir, "0001_item_定理1.md")


def _rb(path):
    with open(path, "rb") as f:
        return f.read()


def _snap(book):
    out = {}
    for root, _dirs, files in os.walk(book):
        for fn in files:
            p = os.path.join(root, fn)
            out[os.path.relpath(p, book)] = _rb(p)
    return out


def _run(ext, book, files, span=None, evidence=None, commit=False, side=None):
    argv = [ext, "2"] + list(files)
    if span:
        argv += ["--span", span]
    if evidence:
        argv += ["--evidence", evidence]
    if side:
        argv += ["--side", side]
    argv += ["--book-dir", book]
    if commit:
        argv.append("--commit")
    return sud.main(argv)


class SyncUnitFromDeliveryTest(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.B = self._td.name
        self.E, self.U = _mk(self.B)

    def tearDown(self):
        self._td.cleanup()

    def _quiet(self, fn):
        import io as _io
        buf, real = _io.StringIO(), sys.stdout
        sys.stdout = buf
        try:
            rc = fn()
        finally:
            sys.stdout = real
        return rc, buf.getvalue()

    # ── 🔴 跨度取短 = 静默截断，必须拒 ──────────────────────────────────────
    def test_span_too_short_refuses_and_names_the_delivery_line(self):
        before = _snap(self.B)
        rc, out = self._quiet(lambda: _run(
            self.E, self.B, ["0001_item_定理1.md"], span="%s:1:5" % MD_NAME))
        self.assertEqual(rc, 1)
        self.assertIn("落在跨度之外", out)
        self.assertIn(TAIL[:20], out)
        self.assertIn("跨度没圈进来", out)          # 指路：改跨度，不是补证据
        self.assertIn("L7", out)
        self.assertEqual(_snap(self.B), before)     # 零写入

    def test_span_too_short_still_writes_when_evidence_given(self):
        # 给了 --evidence 就按「判用人确认这些行该抹」处理：可写，但台账记下丢了几行。
        rc, out = self._quiet(lambda: _run(
            self.E, self.B, ["0001_item_定理1.md"], span="%s:1:5" % MD_NAME,
            evidence="印面 p12：定理1 块止于 (1.1)，收尾句属下一条", commit=True))
        self.assertEqual(rc, 0)
        self.assertNotIn(TAIL, _rb(self.U).decode("utf-8"))
        led = _rb(os.path.join(self.E, "_sync_unit_fixes.jsonl")).decode("utf-8")
        self.assertEqual(json.loads(led)["dropped_unit_only"], 1)

    def test_full_span_writes_and_keeps_marker_bytes(self):
        raw_before = _rb(self.U)
        rc, out = self._quiet(lambda: _run(
            self.E, self.B, ["0001_item_定理1.md"], span="%s:1:7" % MD_NAME,
            commit=True))
        self.assertEqual(rc, 0)
        after = _rb(self.U).decode("utf-8")
        self.assertEqual(after.split("\n")[0], raw_before.decode("utf-8").split("\n")[0])
        self.assertIn("\\tag{1.1}", after)
        self.assertIn(TAIL, after)

    def test_span_strips_the_structural_separator(self):
        rc, out = self._quiet(lambda: _run(
            self.E, self.B, ["0001_item_定理1.md"], span="%s:1:9" % MD_NAME,
            commit=True))
        self.assertEqual(rc, 0)
        body = _rb(self.U).decode("utf-8").split("\n")[1:]
        self.assertNotIn("---", [l.strip() for l in body])

    # ── 单元独有内容（交付里根本没有）───────────────────────────────────────
    def test_unit_only_line_needs_evidence(self):
        extra = "   这一句在交付里完全没有对应，属于单元独有的旧稿残渣内容。"
        _w(self.U, _unit_body(extra=[ "", extra]))
        rc, out = self._quiet(lambda: _run(
            self.E, self.B, ["0001_item_定理1.md"], span="%s:1:7" % MD_NAME))
        self.assertEqual(rc, 1)
        self.assertIn(extra[:12], out)
        self.assertNotIn("跨度没圈进来", out)        # 交付里查无此句 → 不指路
        rc, out = self._quiet(lambda: _run(
            self.E, self.B, ["0001_item_定理1.md"], span="%s:1:7" % MD_NAME,
            evidence="印面 p12 目视：该句为旧稿残留，交付已按印面删除", commit=True))
        self.assertEqual(rc, 0)
        self.assertNotIn(extra, _rb(self.U).decode("utf-8"))

    def test_math_fragment_below_floor_is_not_content_loss(self):
        # 短于 _MIN_LOSS_CHARS 的行（`> $$` 之类）不触发闸——否则每个跨度都要补证据。
        _w(self.U, _unit_body(extra=["", "> $$"]))
        rc, out = self._quiet(lambda: _run(
            self.E, self.B, ["0001_item_定理1.md"], span="%s:1:7" % MD_NAME))
        self.assertEqual(rc, 0)

    # ── 跨度定位的拒绝面 ────────────────────────────────────────────────────
    def test_desc_key_without_span_is_refused_with_hint(self):
        ext, upath = _mk(self.B)
        _w(os.path.join(os.path.dirname(upath), "0002_desc_说明.md"),
           MARK2 + "\n\n**说明** 这是一段说明文字，交付里并没有这个条头。\n")
        rc, out = self._quiet(lambda: _run(ext, self.B, ["0002_desc_说明.md"]))
        self.assertEqual(rc, 1)
        self.assertIn("交付里没有以条头", out)
        self.assertIn("--span", out)

    def test_span_out_of_bounds_refused(self):
        for spec in ("%s:5:3" % MD_NAME, "%s:1:9999" % MD_NAME, "%s:0:4" % MD_NAME):
            rc, out = self._quiet(lambda: _run(
                self.E, self.B, ["0001_item_定理1.md"], span=spec))
            self.assertEqual(rc, 1, spec)
            self.assertIn("越界", out)

    def test_span_md_name_must_be_in_the_chapter_group(self):
        rc, out = self._quiet(lambda: _run(
            self.E, self.B, ["0001_item_定理1.md"], span="第9章_不存在.md:1:7"))
        self.assertEqual(rc, 1)
        self.assertIn("认不到", out)

    def test_span_with_multiple_units_refused(self):
        # 参数级错误走 SystemExit（CLI 直接非零退出），不是一句「拒绝」继续跑。
        with self.assertRaises(SystemExit) as cm:
            self._quiet(lambda: _run(
                self.E, self.B, ["0001_item_定理1.md", "0002_desc_说明.md"],
                span="%s:1:7" % MD_NAME))
        self.assertIn("单个单元文件", str(cm.exception))

    def test_dry_run_writes_nothing(self):
        before = _snap(self.B)
        rc, out = self._quiet(lambda: _run(
            self.E, self.B, ["0001_item_定理1.md"], span="%s:1:7" % MD_NAME))
        self.assertEqual(rc, 0)
        self.assertIn("拟改", out)
        self.assertEqual(_snap(self.B), before)
        self.assertFalse(os.path.exists(os.path.join(self.E, "_sync_unit_fixes.jsonl")))

    def test_automatic_span_from_head_key(self):
        # 不给 --span：起点认条头、终点遇 `---` 停 → 跨度 = L1..L8（含收尾句）。
        rc, out = self._quiet(lambda: _run(
            self.E, self.B, ["0001_item_定理1.md"], commit=True))
        self.assertEqual(rc, 0)
        self.assertIn("L1..L8", out)
        self.assertIn(TAIL, _rb(self.U).decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
