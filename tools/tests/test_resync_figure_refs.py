# -*- coding: utf-8 -*-
"""test_resync_figure_refs.py — 图名三处同步（单元正文 / manifest.images / 契约 image）。

场景（MSDA 实测形态）：图号指派波把 `chNN_unnamed_K.png` 改名成 `chNN_figX.X.png` 并回写了
`figure_index.json` 与交付 md，但契约 / manifest / 单元正文停在旧名 ⇒ 单元里嵌着盘上不存在
的文件，而 gate ③b 因「两侧同为旧名」自洽通过，全链隐形。

正向：dry-run 零写入；--commit 后**只有**命中的 `<img … src>` 行、manifest 该记录的 `images`
一行、契约该 `{"image": …}` 处变，其余逐字节相同；行数/换行符守恒；备份先落盘；再跑 = 0 job。
负向：①alt 无图号 ⇒ 不改（人工档）②同号在 index 多指多个活文件 ⇒ 不改 ③index 目标文件
不在盘 ⇒ 不改 ④契约同名挂两处 ⇒ 两处都改（契约尽力回写，不拦单元）⑤一个单元两条 `<img>`
共用同一旧名 ⇒ **整条不改**（含单元正文：manifest 无法判定哪条对应本 img，只改单元=半写）
⑥🔴 **同文件两条互换旧名**必须各自落对位——串行 find/replace 会命中刚写进去的那条，
净零改动且重跑仍报同样 job（MSDA ch3/ch11 首轮实测即如此）；
⑦🔴 两位数章号回归：章 14 的 alt「Figure 14.6」必须命中——前缀写成单字符类
`([0-9A-Za-z])\\.` 时正则会从 `4.` 起匹配，量出 `4.6`≠`14` ⇒ 整章全瞎，这条就是钉住那个坑；
⑧🔴 **契约独占对账**：单元/manifest/交付已归位而**契约单独 stale**（同名挂两槽）时单元侧
零 job，老版本 `if not jobs: continue` 直接跳过契约腿 ⇒ gate ③b 的两条红无人修。现在预检
放行，且新名不在 index / 盘上没有 / 正文与 manifest 不同向 / 槽数不同长 四种情形都必须拒。
"""
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "lib"))
sys.path.insert(0, os.path.join(_ROOT, "tools"))
import lib.boot as _boot  # noqa: E402
_boot.setup()
import resync_figure_refs as R  # noqa: E402

MARK = ("<!-- book-summarizer DONE unit: id=%s type=desc key=D%s "
        "name=N%s -->")


def img(src, alt):
    return ('<img src="figure/%s" alt="%s" width="60%%" height="auto">'
            % (src, alt))


def build(book, ch="1", alt_prefix="Figure"):
    """一本最小假书：figure_index 登记 `fig<N>.1`，单元/manifest/契约都写旧名 `unnamed_01`。"""
    os.makedirs(os.path.join(book, "figure"))
    label = "%s.1" % ch
    real = "ch%s_fig%s.png" % (ch, label)
    stale = "ch%s_unnamed_01.png" % ch
    for f in (real,):
        io.open(os.path.join(book, "figure", f), "w", encoding="utf-8").write("x")
    ext = os.path.join(book, "_extract")
    os.makedirs(ext)
    json.dump([{"chapter": int(ch) if ch.isdigit() else ch, "label": label,
                "file": "figure/" + real, "caption": "cap one"}],
              io.open(os.path.join(ext, "figure_index.json"), "w", encoding="utf-8"))
    for side in ("units", "units-translate"):
        ud = os.path.join(ext, "book_structure", side, "ch%s" % ch)
        os.makedirs(ud)
        alt = "%s %s cap one" % (alt_prefix, label)
        body = u"文字。\n\n%s\n\n尾注。\n" % img(stale, alt)
        io.open(os.path.join(ud, "0001_desc_D1.md"), "w",
                encoding="utf-8", newline="").write(MARK % ("0001", "1", "1") + "\n" + body)
        json.dump({"language": "en" if side == "units" else "cn",
                   "units": [{"id": "0001", "file": "0001_desc_D1.md",
                              "type": "desc", "key": "D1",
                              "images": ["figure/" + stale], "content": 3}]},
                  io.open(os.path.join(ud, "manifest.json"), "w", encoding="utf-8"))
    os.makedirs(os.path.join(ext, "book_structure"), exist_ok=True)
    io.open(os.path.join(ext, "book_structure", "ch%s.json" % ch), "w",
            encoding="utf-8").write(
        json.dumps({"nodes": [{"key": "D1", "blocks": [{"image": "figure/" + stale}]}]}))
    # 章目录名靠 chapter_map 派生；假书没有 chapter_map.json 时 unit_dir_name 回退 chN
    return real, stale


def build_pair(book, ch="1"):
    """一单元两张图，src 与 alt 号**交叉**（第一条挂 A 名 / B 题注）——互换态。

    MSDA ch3 / ch11 / ch14 的真形态：两个名字都还在盘上（都是 `figX.Y` 新名），只是彼此
    挂反了 ⇒「目标名==旧名」这类判据看不见，必须靠 alt 号定位。
    """
    os.makedirs(os.path.join(book, "figure"))
    labA, labB = "%s.1" % ch, "%s.2" % ch
    A, B = "ch%s_fig%s.png" % (ch, labA), "ch%s_fig%s.png" % (ch, labB)
    for f in (A, B):
        io.open(os.path.join(book, "figure", f), "w", encoding="utf-8").write("x")
    ext = os.path.join(book, "_extract")
    os.makedirs(ext)
    json.dump([{"chapter": int(ch), "label": labA, "file": "figure/" + A,
                "caption": "cap one"},
               {"chapter": int(ch), "label": labB, "file": "figure/" + B,
                "caption": "cap two"}],
              io.open(os.path.join(ext, "figure_index.json"), "w", encoding="utf-8"))
    for side in ("units", "units-translate"):
        ud = os.path.join(ext, "book_structure", side, "ch%s" % ch)
        os.makedirs(ud)
        body = u"图一。\n\n%s\n\n图二。\n\n%s\n" % (
            img(B, u"Figure %s cap one" % labA),      # 第一条：挂着 B 名、题注是 A
            img(A, u"Figure %s cap two" % labB))      # 第二条：挂着 A 名、题注是 B
        io.open(os.path.join(ud, "0001_desc_D1.md"), "w",
                encoding="utf-8", newline="").write(
            MARK % ("0001", "1", "1") + "\n" + body)
        json.dump({"language": "en" if side == "units" else "cn",
                   "units": [{"id": "0001", "file": "0001_desc_D1.md",
                              "type": "desc", "key": "D1",
                              "images": ["figure/" + B, "figure/" + A], "content": 3}]},
                  io.open(os.path.join(ud, "manifest.json"), "w", encoding="utf-8"))
    io.open(os.path.join(ext, "book_structure", "ch%s.json" % ch), "w",
            encoding="utf-8").write(json.dumps({"nodes": [{"key": "D1", "blocks": [
        {"image": "figure/" + B}, {"image": "figure/" + A}]}]}))
    return A, B


def build_contract_stale(book, ch="1", index_both=True, b_on_disk=True):
    u"""「单元/manifest 已归位、契约单独 stale」形态（MSDA ch3 / ch11 实测）。

    改名波回写了单元正文、manifest 与交付，**只有契约**把 B 那张的槽留在 A 名上 ⇒
    gate ③b 同章两红：「单元嵌契约外图 B」+「契约重复引用 A（2 块）」。
    单元侧零 job ⇒ 老版本 `main` 在 `if not jobs …: continue` 处直接跳过，契约腿跑不到。
    → (A, B)
    """
    os.makedirs(os.path.join(book, "figure"))
    labA, labB = "%s.1" % ch, "%s.2" % ch
    A, B = "ch%s_fig%s.png" % (ch, labA), "ch%s_fig%s.png" % (ch, labB)
    io.open(os.path.join(book, "figure", A), "w", encoding="utf-8").write("x")
    if b_on_disk:
        io.open(os.path.join(book, "figure", B), "w", encoding="utf-8").write("x")
    ext = os.path.join(book, "_extract")
    os.makedirs(ext)
    idx = [{"chapter": int(ch), "label": labA, "file": "figure/" + A,
            "caption": "cap one"}]
    if index_both:
        idx.append({"chapter": int(ch), "label": labB, "file": "figure/" + B,
                    "caption": "cap two"})
    json.dump(idx, io.open(os.path.join(ext, "figure_index.json"), "w",
                           encoding="utf-8"))
    for side in ("units", "units-translate"):
        ud = os.path.join(ext, "book_structure", side, "ch%s" % ch)
        os.makedirs(ud)
        body = u"图一。\n\n%s\n\n图二。\n\n%s\n" % (
            img(A, u"Figure %s cap one" % labA),
            img(B, u"Figure %s cap two" % labB))
        io.open(os.path.join(ud, "0001_desc_D1.md"), "w",
                encoding="utf-8", newline="").write(
            MARK % ("0001", "1", "1") + "\n" + body)
        json.dump({"language": "en" if side == "units" else "cn",
                   "units": [{"id": "0001", "file": "0001_desc_D1.md",
                              "type": "desc", "key": "D1",
                              "images": [u"figure/" + A, u"figure/" + B],
                              "content": 4}]},
                  io.open(os.path.join(ud, "manifest.json"), "w", encoding="utf-8"))
    io.open(os.path.join(ext, "book_structure", "ch%s.json" % ch), "w",
            encoding="utf-8").write(json.dumps({"nodes": [{"key": "D1", "blocks": [
                {"image": "figure/" + A}, {"image": "figure/" + A}]}]}))
    return A, B


def run(book, ch, commit=False, extra=()):
    argv = [sys.argv[0], book, ch] + list(extra) + (["--commit"] if commit else [])
    old = sys.argv
    sys.argv = argv
    buf = io.StringIO()
    real_out = sys.stdout
    sys.stdout = buf
    try:
        R.main()
    finally:
        sys.stdout = real_out
        sys.argv = old
    return buf.getvalue()


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rfr_")
        self.book = os.path.join(self.tmp, "B")
        os.makedirs(self.book)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _unit_srcs(self, path):
        return re.findall(r'src="([^"]+)"', io.open(path, encoding="utf-8").read())

    def _unit_alts(self, path):
        return re.findall(r'alt="([^"]+)"', io.open(path, encoding="utf-8").read())

    def _unit_src(self, side, book):
        p = os.path.join(book, "_extract", "book_structure", side,
                         "ch%s" % self.ch, "0001_desc_D1.md")
        t = io.open(p, encoding="utf-8").read()
        return t.split('src="')[1].split('"')[0]

    def _man_imgs(self, side, book):
        p = os.path.join(book, "_extract", "book_structure", side,
                         "ch%s" % self.ch, "manifest.json")
        return json.load(io.open(p, encoding="utf-8"))["units"][0]["images"]

    def _contract(self, book):
        p = os.path.join(book, "_extract", "book_structure",
                         "ch%s.json" % self.ch)
        return json.load(io.open(p, encoding="utf-8"))["nodes"][0]["blocks"][0]["image"]

    def _contract_imgs(self, cp):
        return [b["image"] for n in json.load(io.open(cp, encoding="utf-8"))["nodes"]
                for b in n["blocks"] if "image" in b]

    def test_dry_run_writes_nothing(self):
        self.ch = "1"
        real, stale = build(self.book, self.ch)
        before = self._unit_src("units", self.book)
        run(self.book, self.ch, commit=False)
        self.assertEqual(before, self._unit_src("units", self.book))
        self.assertEqual([u"figure/" + stale], self._man_imgs("units", self.book))
        self.assertFalse(os.path.isdir(os.path.join(
            self.book, "_extract", "_bak_resync_figure_refs")))

    def test_commit_syncs_three_places_and_idempotent(self):
        self.ch = "1"
        real, stale = build(self.book, self.ch)
        unit_p = os.path.join(self.book, "_extract", "book_structure", "units",
                              "ch1", "0001_desc_D1.md")
        raw_before = io.open(unit_p, encoding="utf-8").read()
        run(self.book, self.ch, commit=True)
        for side in ("units", "units-translate"):
            self.assertEqual(self._unit_src(side, self.book), "figure/" + real)
            self.assertEqual(self._man_imgs(side, self.book), ["figure/" + real])
        self.assertEqual(self._contract(self.book), "figure/" + real)
        # 只动 src 值：行数守恒，正文其余逐字不变
        raw_after = io.open(unit_p, encoding="utf-8").read()
        self.assertEqual(raw_before.count("\n"), raw_after.count("\n"))
        self.assertEqual(raw_before.replace(stale, real), raw_after)
        self.assertTrue(os.path.isdir(os.path.join(
            self.book, "_extract", "_bak_resync_figure_refs")))
        out = run(self.book, self.ch, commit=True)      # 再跑 = 0 job
        self.assertEqual(io.open(unit_p, encoding="utf-8").read(), raw_after)

    def test_two_digit_chapter_label_is_not_blind(self):
        u"""🔴 回归：章 14 的 alt「Figure 14.6」必须能命中（单字符前缀类会读成 4.6）。"""
        self.ch = "14"
        real, stale = build(self.book, "14")
        run(self.book, "14", commit=True)
        self.assertEqual(self._unit_src("units", self.book), "figure/" + real)

    def test_alt_without_label_skipped(self):
        self.ch = "1"
        real, stale = build(self.book, self.ch)
        p = os.path.join(self.book, "_extract", "book_structure", "units", "ch1",
                         "0001_desc_D1.md")
        t = io.open(p, encoding="utf-8").read().replace(
            'alt="Figure 1.1 cap one"', 'alt="a scatter plot"')
        io.open(p, "w", encoding="utf-8", newline="").write(t)
        run(self.book, "1", commit=True)
        self.assertIn(stale, self._unit_src("units", self.book))

    def test_ambiguous_label_skipped(self):
        self.ch = "1"
        real, stale = build(self.book, self.ch)
        second = "ch1_fig1.1_b.png"
        io.open(os.path.join(self.book, "figure", second), "w",
                encoding="utf-8").write("x")
        jp = os.path.join(self.book, "_extract", "figure_index.json")
        d = json.load(io.open(jp, encoding="utf-8"))
        d.append({"chapter": 1, "label": "1.1", "file": "figure/" + second,
                  "caption": "cap dup"})
        json.dump(d, io.open(jp, "w", encoding="utf-8"))
        run(self.book, "1", commit=True)
        self.assertIn(stale, self._unit_src("units", self.book))

    def test_index_target_missing_on_disk_skipped(self):
        self.ch = "1"
        real, stale = build(self.book, self.ch)
        os.remove(os.path.join(self.book, "figure", real))
        run(self.book, "1", commit=True)
        self.assertIn(stale, self._unit_src("units", self.book))

    def test_contract_duplicate_name_lands_everywhere(self):
        u"""契约是尽力回写：同一旧名挂在两个节点 ⇒ 两处都换成新名，且照常改单元/manifest。"""
        self.ch = "1"
        real, stale = build(self.book, self.ch)
        cp = os.path.join(self.book, "_extract", "book_structure", "ch1.json")
        io.open(cp, "w", encoding="utf-8").write(json.dumps(
            {"nodes": [{"key": "D1", "blocks": [{"image": "figure/" + stale}]},
                      {"key": "D9", "blocks": [{"image": "figure/" + stale}]}]}))
        run(self.book, "1", commit=True)
        self.assertEqual(self._unit_src("units", self.book), "figure/" + real)
        self.assertEqual(self._man_imgs("units", self.book), ["figure/" + real])
        raw = io.open(cp, encoding="utf-8").read()
        self.assertEqual(raw.count(stale), 0)
        self.assertEqual(raw.count("figure/" + real), 2)

    def test_swapped_names_in_one_file_land_positionally(self):
        u"""🔴 回归：同文件两条 src **互换**（MSDA ch3 `3.9↔3.10`、ch11 `11.3↔11.4` 实测）。
        串行 find/replace 会先命中刚写进去的那条 ⇒ 净零改动，重跑仍报同样两个 job；
        并行按字符区间落才把两行各自改对。"""
        self.ch = "1"
        A, B = build_pair(self.book, "1")
        p = os.path.join(self.book, "_extract", "book_structure", "units", "ch1",
                         "0001_desc_D1.md")
        self.assertEqual(self._unit_srcs(p), [u"figure/" + B, u"figure/" + A])
        crossed = io.open(p, encoding="utf-8").read()      # 互换态快照（工具跑之前）
        run(self.book, "1", commit=True)
        self.assertEqual(self._unit_srcs(p), [u"figure/" + A, u"figure/" + B])
        self.assertEqual(self._man_imgs("units", self.book),
                         [u"figure/" + A, u"figure/" + B])
        raw = io.open(os.path.join(self.book, "_extract", "book_structure",
                                   "ch1.json"), encoding="utf-8").read()
        self.assertEqual(raw.count(A), 1)
        self.assertEqual(raw.count(B), 1)
        self.assertIn(u"改名 0 处", run(self.book, "1", commit=True))   # 幂等
        # 控件：把「串行 find 再 replace」（旧实现）跑在同一份互换态数据上，必须**净零改动**
        # ⇒ 证明上面的绿是并行落位换来的，不是数据本来就没互换。
        serial = crossed
        for old, new in ((B, A), (A, B)):
            pat = 'src="figure/%s"' % old
            i = serial.find(pat)
            if i >= 0:
                serial = serial[:i] + ('src="figure/%s"' % new) + serial[i + len(pat):]
        self.assertEqual(serial, crossed)

    def test_channel_m_repairs_surplus_array_slot(self):
        u"""通道 M：上一轮串行写把 manifest 数组写成「同名两遍、另一个零遍」而**顺序不
        对齐正文**（MSDA ch3/ch11 首轮实测形态）⇒ 用文档序里缺失的那个名补最早的多余槽，
        数组与正文多重集必须对齐（数组顺序不载荷，闸按 set 比）。"""
        self.ch = "1"
        A, B = build_pair(self.book, "1")
        ud = os.path.join(self.book, "_extract", "book_structure", "units", "ch1")
        p = os.path.join(ud, "0001_desc_D1.md")
        mp = os.path.join(ud, "manifest.json")
        d = json.load(io.open(mp, encoding="utf-8"))
        d["units"][0]["images"] = [u"figure/" + A, u"figure/" + A]
        json.dump(d, io.open(mp, "w", encoding="utf-8"))
        out = run(self.book, "1", commit=True, extra=("--side", "units"))
        self.assertIn(u"通道 M", out)
        self.assertEqual(self._unit_srcs(p), [u"figure/" + A, u"figure/" + B])
        got = sorted(x.rsplit("/", 1)[-1] for x in self._man_imgs("units", self.book))
        self.assertEqual(got, sorted([A, B]))

    def _misembed(self, A, B):
        u"""把 build_pair 的互换态改成 MSDA ch14 0010 的真形态：**两条 src 与 alt 全挂第一张**
        （第二条其实是印面 Figure 14.7 那张，只有 width 不同）⇒ 机械锚一条 job 也量不到。"""
        ud = os.path.join(self.book, "_extract", "book_structure", "units", "ch1")
        p = os.path.join(ud, "0001_desc_D1.md")
        t = io.open(p, encoding="utf-8").read()
        t = t.replace(u'src="figure/%s" alt="Figure 1.1' % B,
                      u'src="figure/%s" alt="Figure 1.1' % A)
        t = t.replace(u'Figure 1.2 cap two', u'Figure 1.1 cap one')
        io.open(p, "w", encoding="utf-8", newline="").write(t)
        mp = os.path.join(ud, "manifest.json")
        d = json.load(io.open(mp, encoding="utf-8"))
        d["units"][0]["images"] = [u"figure/" + A, u"figure/" + A]
        json.dump(d, io.open(mp, "w", encoding="utf-8"))
        cp = os.path.join(self.book, "_extract", "book_structure", "ch1.json")
        io.open(cp, "w", encoding="utf-8").write(json.dumps(
            {"nodes": [{"key": "D1", "blocks": [{"image": "figure/" + A},
                                                {"image": "figure/" + A}]}]}))
        return p, cp

    def _pin(self, entries):
        io.open(os.path.join(self.book, "_extract", "figure_pins.json"), "w",
                encoding="utf-8").write(json.dumps(entries, ensure_ascii=False))

    def test_pin_lands_misembedded_duplicate_by_rank(self):
        u"""人工裁定档 `figure_pins.json` 把嵌错的第二条落回 Figure 1.2（src + 印面题注）。
        🔴 必须按**正文序号**改第二条：通道 M 的「最早多余槽」在这种「同名两遍、多重集也要
        同名两遍变一遍」的形态上会改错一半，数组/契约都会留下 [B, A] 的反序。"""
        self.ch = "1"
        A, B = build_pair(self.book, "1")
        p, cp = self._misembed(A, B)
        self.assertEqual(self._unit_srcs(p), [u"figure/" + A, u"figure/" + A])
        self.assertIn(u"改名 0 处", run(self.book, "1"))          # 机械锚：完全隐形
        self._pin([{"chapter": "1", "file": "0001_desc_D1.md", "old": A, "new": B,
                    "occurrence": 2, "alt": u"Figure 1.2 cap two", "why": "印面 p552"}])
        out = run(self.book, "1", commit=True, extra=("--side", "units"))
        self.assertIn(u"按正文序号落", out)
        self.assertEqual(self._unit_srcs(p), [u"figure/" + A, u"figure/" + B])
        self.assertEqual(self._unit_alts(p), [u"Figure 1.1 cap one", u"Figure 1.2 cap two"])
        self.assertEqual(self._man_imgs("units", self.book),
                         [u"figure/" + A, u"figure/" + B])        # 改的是**第二**槽
        raw = io.open(cp, encoding="utf-8").read()
        self.assertEqual(re.findall(r'"image": "figure/([^"]+)"', raw), [A, B])
        self.assertIn(u"改名 0 处", run(self.book, "1", extra=("--side", "units")))  # 幂等

    def test_pin_without_occurrence_on_duplicate_refuses(self):
        u"""负向：旧名在该单元出现两遍而 pin 没写 occurrence ⇒ 拒（不猜哪一条），零写入。"""
        self.ch = "1"
        A, B = build_pair(self.book, "1")
        p, _cp = self._misembed(A, B)
        self._pin([{"chapter": "1", "file": "0001_desc_D1.md", "old": A, "new": B,
                    "alt": u"Figure 1.2 cap two"}])
        out = run(self.book, "1", commit=True, extra=("--side", "units"))
        self.assertIn(u"pin 未定 occurrence", out)
        self.assertIn(u"单元 0 行", out)
        self.assertEqual(self._unit_srcs(p), [u"figure/" + A, u"figure/" + A])

    def test_already_landed_pin_is_not_rejobbed(self):
        u"""负向/幂等：pin 的 new 与旧名同、alt 与现文同（MSDA ch14 0026 落位后的形态）⇒
        既不出 src job 也不出 ALT job，只记「pin 与现状一致」。钉住两件事：
        ① dry-run 不会每轮都拿一条净零改动冒充「还有活」；
        ② 收窄只砍净零，不砍真差异（换一条不同的 alt 仍须报 题注回补 1 处）。"""
        self.ch = "1"
        A, B = build_pair(self.book, "1")
        up = os.path.join(self.book, "_extract", "book_structure", "units",
                          "ch1", "0001_desc_D1.md")
        run(self.book, "1", commit=True)                    # 先让机械锚把互换态落正
        self.assertEqual(self._unit_alts(up),
                         [u"Figure 1.1 cap one", u"Figure 1.2 cap two"])
        self._pin([{"chapter": "1", "file": "0001_desc_D1.md", "old": A, "new": A,
                    "alt": u"Figure 1.1 cap one", "why": "已按印面落位"}])
        out = run(self.book, "1", commit=True, extra=("--side", "units"))
        self.assertIn(u"改名 0 处", out)
        self.assertIn(u"题注回补 0 处", out)
        self.assertIn(u"pin 与现状一致", out)
        self.assertIn(u"备份 0 文件", out)
        self._pin([{"chapter": "1", "file": "0001_desc_D1.md", "old": A, "new": A,
                    "alt": u"Figure 1.1 cap ONE (印面措辞)", "why": "真差异仍须落"}])
        out2 = run(self.book, "1", commit=True, extra=("--side", "units"))
        self.assertIn(u"题注回补 1 处", out2)
        self.assertEqual(self._unit_alts(up)[0], u"Figure 1.1 cap ONE (印面措辞)")
        self.assertEqual(self._unit_srcs(up), [u"figure/" + A, u"figure/" + B])

    def test_pin_target_missing_on_disk_refuses_whole_chapter(self):
        u"""负向：pin 的 new 盘上没有 ⇒ 落它等于造一条新死链 ⇒ 整章拒（SystemExit），不写。"""
        self.ch = "1"
        A, _B = build_pair(self.book, "1")
        self._misembed(A, _B)
        self._pin([{"chapter": "1", "file": "0001_desc_D1.md", "old": A,
                    "new": "ch1_fig9.9.png"}])
        self.assertRaises(SystemExit, run, self.book, "1", True, ("--side", "units"))

    def _duppair(self, A, B):
        u"""build_pair 改成 MSDA ch10 0027 的真形态：**同一张图在单元里连挂两遍**
        （印面 p400 只有一张 FIGURE 10.11），manifest 数组与契约 image 块跟着记两遍。
        图改名波的去重只回写了交付 ⇒ 单元侧多出来的那一遍是纯账外内容。"""
        ud = os.path.join(self.book, "_extract", "book_structure", "units", "ch1")
        p = os.path.join(ud, "0001_desc_D1.md")
        io.open(p, "w", encoding="utf-8", newline="").write(
            MARK % ("0001", "1", "1") + u"\n" + u"图一。\n\n%s\n\n%s\n\n图二。\n\n%s\n" % (
                img(A, u"Figure 1.1 cap one"),
                img(A, u"Figure 1.1 cap one"),
                img(B, u"Figure 1.2 cap two")))
        mp = os.path.join(ud, "manifest.json")
        d = json.load(io.open(mp, encoding="utf-8"))
        d["units"][0]["images"] = [u"figure/" + A, u"figure/" + A, u"figure/" + B]
        d["units"][0]["content"] = 3
        json.dump(d, io.open(mp, "w", encoding="utf-8"))
        cp = os.path.join(self.book, "_extract", "book_structure", "ch1.json")
        io.open(cp, "w", encoding="utf-8").write(json.dumps(
            {"nodes": [{"key": "D1", "blocks": [
                {"image": "figure/" + A}, {"image": "figure/" + A},
                {"image": "figure/" + B}]}]}))
        return p, cp

    def test_pin_drop_removes_line_slot_and_block(self):
        u"""`"drop": true` 的人工裁定：删正文那一整行 + manifest 同序号那格 + 契约同序号
        那个 image 块，并把该记录的 `content` 减 1（契约节点少了一个内容块）。
        🔴 三处必须同进退：只删正文 = gate ③b（正文 vs manifest.images）当场翻 FAIL。"""
        self.ch = "1"
        A, B = build_pair(self.book, "1")
        p, cp = self._duppair(A, B)
        self.assertEqual(self._unit_srcs(p), [u"figure/" + A] * 2 + [u"figure/" + B])
        self.assertIn(u"去重 0 处", run(self.book, "1"))          # 没登记 ⇒ 机械锚不动
        self._pin([{"chapter": "1", "file": "0001_desc_D1.md", "old": A,
                    "occurrence": 2, "drop": True, "why": "印面 p400 只有一张"}])
        out = run(self.book, "1", commit=True, extra=("--side", "units"))
        self.assertIn(u"去重 1 处", out)
        self.assertIn(u"去重删槽 ×1＋content 回退", out)
        self.assertIn(u"契约去重：删第 2 槽", out)
        self.assertIn(u"去重 1 行", out)
        self.assertEqual(self._unit_srcs(p), [u"figure/" + A, u"figure/" + B])
        self.assertEqual(self._man_imgs("units", self.book),
                         [u"figure/" + A, u"figure/" + B])
        self.assertEqual(self._man_field("units", "content"), 2)
        raw = io.open(cp, encoding="utf-8").read()
        self.assertEqual(re.findall(r'"image": "figure/([^"]+)"', raw), [A, B])
        json.loads(raw)                     # 删块后仍是合法 JSON
        out2 = run(self.book, "1", extra=("--side", "units"))
        self.assertIn(u"去重 0 处", out2)
        self.assertIn(u"备份 0 文件", out2)                      # 幂等

    def _man_field(self, side, key):
        p = os.path.join(self.book, "_extract", "book_structure", side,
                         "ch%s" % self.ch, "manifest.json")
        return json.load(io.open(p, encoding="utf-8"))["units"][0][key]

    def test_pin_drop_refuses_when_name_appears_once(self):
        u"""负向：旧名在该单元只出现一遍 ⇒ drop 拒（删掉就是丢一张图，不是去重）。"""
        self.ch = "1"
        A, B = build_pair(self.book, "1")
        p, _cp = self._duppair(A, B)
        io.open(p, "w", encoding="utf-8", newline="").write(
            MARK % ("0001", "1", "1") + u"\n" + u"图一。\n\n%s\n\n图二。\n\n%s\n" % (
                img(A, u"Figure 1.1 cap one"), img(B, u"Figure 1.2 cap two")))
        self._pin([{"chapter": "1", "file": "0001_desc_D1.md", "old": A,
                    "occurrence": 1, "drop": True}])
        out = run(self.book, "1", commit=True, extra=("--side", "units"))
        self.assertIn(u"drop 拒：旧名在该单元只出现 1 次", out)
        self.assertIn(u"单元 0 行", out)
        self.assertEqual(self._unit_srcs(p), [u"figure/" + A, u"figure/" + B])

    def test_pin_drop_refuses_when_array_not_mirror(self):
        u"""负向：manifest 数组与正文 img 序不同（这里被写成 [A, B, A]）⇒ 不敢按序号删槽，
        整条不改（正文/数组/契约三处都保持原样）。删错一格不可逆。"""
        self.ch = "1"
        A, B = build_pair(self.book, "1")
        p, cp = self._duppair(A, B)
        mp = os.path.join(self.book, "_extract", "book_structure", "units",
                          "ch1", "manifest.json")
        d = json.load(io.open(mp, encoding="utf-8"))
        d["units"][0]["images"] = [u"figure/" + A, u"figure/" + B, u"figure/" + A]
        json.dump(d, io.open(mp, "w", encoding="utf-8"))
        self._pin([{"chapter": "1", "file": "0001_desc_D1.md", "old": A,
                    "occurrence": 2, "drop": True}])
        out = run(self.book, "1", commit=True, extra=("--side", "units"))
        self.assertIn(u"manifest 数组与正文 img 序不同", out)
        self.assertIn(u"单元 0 行", out)
        self.assertEqual(self._unit_srcs(p), [u"figure/" + A] * 2 + [u"figure/" + B])
        self.assertEqual(self._man_imgs("units", self.book),
                         [u"figure/" + A, u"figure/" + B, u"figure/" + A])
        self.assertEqual(re.findall(r'"image": "figure/([^"]+)"',
                                    io.open(cp, encoding="utf-8").read()), [A, A, B])

    def test_pin_drop_schema_refusals(self):
        u"""负向：drop 与 new 并存 / drop 不写 occurrence ⇒ 直接 SystemExit（不猜）。"""
        self.ch = "1"
        A, B = build_pair(self.book, "1")
        self._duppair(A, B)
        self._pin([{"chapter": "1", "file": "0001_desc_D1.md", "old": A,
                    "occurrence": 2, "drop": True, "new": B}])
        self.assertRaises(SystemExit, run, self.book, "1", True, ("--side", "units"))
        self._pin([{"chapter": "1", "file": "0001_desc_D1.md", "old": A,
                    "drop": True}])
        self.assertRaises(SystemExit, run, self.book, "1", True, ("--side", "units"))

    def test_manifest_length_mismatch_refuses_whole_job(self):
        u"""负向：记录比正文多一条图（结构性差异，不是本次改名造成的重复槽）⇒ 通道 M 因
        「长度不等」拒，整条不改（含单元正文）。钉住「不越界修别人弄坏的账」——
        只改单元正文 = 半写，gate ③b 由 PASS 翻 FAIL。"""
        self.ch = "1"
        A, B = build_pair(self.book, "1")
        ud = os.path.join(self.book, "_extract", "book_structure", "units", "ch1")
        mp = os.path.join(ud, "manifest.json")
        d = json.load(io.open(mp, encoding="utf-8"))
        d["units"][0]["images"] = [u"figure/" + A, u"figure/" + B, u"figure/x.png"]
        json.dump(d, io.open(mp, "w", encoding="utf-8"))
        out = run(self.book, "1", commit=True, extra=("--side", "units"))
        self.assertIn(u"整条不改", out)
        self.assertIn(u"长度不等", out)
        self.assertIn(u"单元 0 行", out)
        self.assertEqual(self._unit_srcs(os.path.join(ud, "0001_desc_D1.md")),
                         [u"figure/" + B, u"figure/" + A])

    def test_contract_only_lane_lands_contract_only(self):
        u"""契约独占对账：单元侧零活时**只**改契约那一槽，正文/manifest 逐字节不动。

        钉两件事：① 老版本「jobs 空 ⇒ continue」把这类账整个看漏（gate ③b 两红无人修）；
        ② 落的是**后一槽**（升序裁定）——前一槽是 A 自己的块，改它就把两张图都写成 B。
        """
        self.ch = "1"
        A, B = build_contract_stale(self.book, "1")
        up = os.path.join(self.book, "_extract", "book_structure", "units", "ch1",
                          "0001_desc_D1.md")
        mp = os.path.join(self.book, "_extract", "book_structure", "units", "ch1",
                          "manifest.json")
        raw_u, raw_m = io.open(up, encoding="utf-8").read(), io.open(mp, encoding="utf-8").read()
        out = run(self.book, "1", commit=True)
        self.assertIn(u"契约独占对账", out)
        self.assertIn(u"第 2 槽", out)
        cp = os.path.join(self.book, "_extract", "book_structure", "ch1.json")
        self.assertEqual(self._contract_imgs(cp), [u"figure/" + A, u"figure/" + B])
        self.assertEqual(io.open(up, encoding="utf-8").read(), raw_u)
        self.assertEqual(io.open(mp, encoding="utf-8").read(), raw_m)
        self.assertIn(u"单元 0 行", out)
        self.assertIn(u"契约 1 处", out)
        # 幂等：再跑一次不再落（多重集已一致 ⇒ 预检拒，契约不再被写）
        out2 = run(self.book, "1", commit=True)
        self.assertIn(u"契约独占对账不落", out2)
        self.assertIn(u"无需修", out2)
        self.assertEqual(self._contract_imgs(cp), [u"figure/" + A, u"figure/" + B])

    def test_contract_only_dry_run_writes_nothing(self):
        self.ch = "1"
        A, B = build_contract_stale(self.book, "1")
        cp = os.path.join(self.book, "_extract", "book_structure", "ch1.json")
        before = self._contract_imgs(cp)
        out = run(self.book, "1", commit=False)
        self.assertIn(u"契约独占对账", out)
        self.assertEqual(self._contract_imgs(cp), before)
        self.assertFalse(os.path.isdir(os.path.join(
            self.book, "_extract", "_bak_resync_figure_refs")))

    def test_contract_only_refuses_when_new_name_not_in_index(self):
        u"""负向：新名没在 figure_index 登记 ⇒ 无印面依据，不落（不拿单元序当唯一证）。"""
        self.ch = "1"
        A, B = build_contract_stale(self.book, "1", index_both=False)
        cp = os.path.join(self.book, "_extract", "book_structure", "ch1.json")
        out = run(self.book, "1", commit=True)
        self.assertIn(u"契约独占对账不落", out)
        self.assertIn(u"不在 figure_index", out)
        self.assertEqual(self._contract_imgs(cp), [u"figure/" + A, u"figure/" + A])

    def test_contract_only_refuses_when_new_name_missing_on_disk(self):
        u"""负向：index 有而 `figure/` 盘上没这个文件 ⇒ 落了就是断链，不落。"""
        self.ch = "1"
        A, B = build_contract_stale(self.book, "1", b_on_disk=False)
        cp = os.path.join(self.book, "_extract", "book_structure", "ch1.json")
        out = run(self.book, "1", commit=True)
        self.assertIn(u"契约独占对账不落", out)
        self.assertIn(u"盘上没有", out)
        self.assertEqual(self._contract_imgs(cp), [u"figure/" + A, u"figure/" + A])

    def test_contract_only_refuses_when_manifest_and_body_disagree(self):
        u"""负向：manifest 把两格都写成 A 而正文是 A、B ⇒ 两个见证不同向，契约不是「孤证 stale」
        而是三处各说各话，交通道 C 的机械前提不成立 ⇒ 整章不落。"""
        self.ch = "1"
        A, B = build_contract_stale(self.book, "1")
        for side in ("units", "units-translate"):
            mp = os.path.join(self.book, "_extract", "book_structure", side, "ch1",
                              "manifest.json")
            d = json.load(io.open(mp, encoding="utf-8"))
            d["units"][0]["images"] = [u"figure/" + A, u"figure/" + A]
            json.dump(d, io.open(mp, "w", encoding="utf-8"))
        cp = os.path.join(self.book, "_extract", "book_structure", "ch1.json")
        out = run(self.book, "1", commit=True)
        self.assertIn(u"契约独占对账不落", out)
        self.assertIn(u"不同向", out)
        self.assertEqual(self._contract_imgs(cp), [u"figure/" + A, u"figure/" + A])

    def _set_blocks(self, imgs):
        """改写契约的 image 块序列（负向用例的「另一种坏法」）。"""
        cp = os.path.join(self.book, "_extract", "book_structure",
                          "ch%s.json" % self.ch)
        io.open(cp, "w", encoding="utf-8").write(json.dumps(
            {"nodes": [{"key": "D1", "blocks": [{"image": "figure/" + i}
                                                for i in imgs]}]}))
        return cp

    def test_contract_only_refuses_when_slots_not_one_to_one(self):
        u"""负向：契约 3 槽 vs 单元 2 条 ⇒ 位置不载荷，无法按文档序定位，不落。"""
        self.ch = "1"
        A, B = build_contract_stale(self.book, "1")
        cp = self._set_blocks([A, A, B])
        out = run(self.book, "1", commit=True)
        self.assertIn(u"契约独占对账不落", out)
        self.assertIn(u"无法按文档序定位", out)
        self.assertEqual(self._contract_imgs(cp),
                         [u"figure/" + A, u"figure/" + A, u"figure/" + B])

    def test_contract_only_refuses_when_old_name_hangs_once(self):
        u"""负向：契约不是「并图」形态（旧名只挂 1 处，另一槽是别的名字）⇒ 不归本通道，不落。"""
        self.ch = "1"
        A, B = build_contract_stale(self.book, "1")
        cp = self._set_blocks([A, "x.png"])
        out = run(self.book, "1", commit=True)
        self.assertIn(u"契约独占对账不落", out)
        self.assertEqual(self._contract_imgs(cp), [u"figure/" + A, u"figure/x.png"])


class NoFreeNamesInDedupBranch(unittest.TestCase):
    """🔴 负向锁：契约去重分支旧写法 `want_en = [c if …]` 必须被静态检查器点名。

    `c` 是 722 行 `cur = [c for c, _t in srows]` 的**推导式目标**（Python 3
    独立作用域），895 行引用它在运行时是 NameError；旧检查器把它误当函数
    局部绑定而全库零报。此例同时钉住「修好的写法」与「检查器抓得住旧写法」。
    """

    def test_fixed_source_is_clean_and_old_wording_is_caught(self):
        import check_undefined_names as C
        src = (Path(_ROOT) / "tools" / "resync_figure_refs.py").read_text(
            encoding="utf-8-sig")
        # 该分支已抽成纯函数 undropped_want；锁住「显式取 cur[i]」这一形态。
        self.assertIn("want_en, gone_en = undropped_want(", src)
        old = "return ([cur[i] if (i in gone and i not in gone_ok) else t"
        self.assertIn(old, src)
        self.assertEqual(C.check_source(src), [])
        broken = src.replace(old,
                             "return ([c if (i in gone and i not in gone_ok) else t")
        self.assertNotEqual(broken, src)
        probs = C.check_source(broken)
        self.assertTrue(any(p[0] == "c" for p in probs), probs)


class UndroppedWantBranch(unittest.TestCase):
    """🔴 契约去重分支的**运行时**覆盖（此前只有静态负向锁）。

    `undropped_want` 是 main() 里「manifest 腿拒绝某条去重」时执行的纯函数：
    拒绝的槽位必须把目标从 DROP 还原成当前图名，否则契约会被误删 image 块。
    """

    def test_rejected_drop_restores_current_name(self):
        cur = [u"figure/a.png", u"figure/b.png"]
        want = [u"figure/a.png", R.DROP]
        out, keep = R.undropped_want(cur, want, {1}, set())
        self.assertEqual(out, [u"figure/a.png", u"figure/b.png"])
        self.assertEqual(keep, set())

    def test_accepted_drop_keeps_drop_sentinel(self):
        """负向锁：manifest 腿接受时不得回写，否则删槽会被跳过。"""
        cur = [u"figure/a.png", u"figure/b.png"]
        want = [u"figure/a.png", R.DROP]
        out, keep = R.undropped_want(cur, want, {1}, {1})
        self.assertEqual(out, [u"figure/a.png", R.DROP])
        self.assertEqual(keep, {1})

    def test_no_gone_is_identity(self):
        cur = [u"figure/a.png", u"figure/b.png"]
        out, keep = R.undropped_want(cur, list(cur), set(), set())
        self.assertEqual(out, cur)
        self.assertEqual(keep, set())

    def test_unit_seq_gone_indices_are_in_range(self):
        """gone 来自 unit_seq 的槽号，必须恒可索引 cur（防 IndexError 回归）。"""
        rows = {(u"units", u"0001.md"): [
            (u"figure/a.png", u"figure/a.png"),
            (u"figure/b.png", R.DROP)]}
        cur, want, gone = R.unit_seq(rows, u"units")
        self.assertEqual(gone, {1})
        self.assertTrue(all(i < len(cur) for i in gone))
        out, _keep = R.undropped_want(cur, want, gone, set())
        self.assertEqual(out, cur)


if __name__ == "__main__":
    unittest.main(verbosity=2)
