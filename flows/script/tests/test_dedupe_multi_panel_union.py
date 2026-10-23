"""判据：同图号的**不相交**检测框是「一幅多面板图」，必须并集重裁，不得丢面板。

缺陷根因（Lehmann《Elements of Large-Sample Theory》p46 实测 2026-10-15）：
`FIGURE 1.6.1(a): y = F(x)` 与 `FIGURE 1.6.1(b): x = F⁻¹(y)` 左右并排，版面检测
各框一个 box（两个都带标号 caption → 各自裁成 det_p046_01/02）。旧
`assign_chapter` 的去重注释写着「一本书不可能两个不同的图共用一个号」，于是
按面积只保留大框、`os.remove` 掉另一个 —— 面板 (b) 从此在 figure_index、契约
image 块、最终笔记里整体消失（**静默内容丢失**，E 层还全绿，因为它只数得下
一个 1.6.1）。

修复形态：`_dedupe_by_label`
  * 同页、同图号、框**重叠**（IoU ≥ `_IOU_DUP`）→ 检测噪声，保留最大框（旧行为）；
  * 同页、同图号、框**互不相交** → 多面板，用 PDF 重渲染并集区域覆盖保留框的
    裁图，条目 `bbox` 改为并集，其余条目折叠进这张并集图；
  * 跨页同号 / 无 PDF 可用 → 退回旧行为（并集在物理上不可能，宁可保留大框）。

正向：合成 PDF 上两个左右并排的实心矩形 → 1 条目、bbox 为并集、裁图像素宽 ≈
      并集宽（即两块都在图里）。
负向：①两个高度重叠的同号框 → 1 条目、bbox 不变、不触发重裁（pdf_path=None 也
        要成立）；②同号但分处两页 → 保留最大框；③无标号（label=None）条目一律
        原样保留，不参与去重；④并集重裁不可用（无 PDF）→ 旧行为且不留下悬空文件。

跨书校准（47 书 / 4647 检测框 / 2787 带号框，按同源判据 parse_fig_label 重建去重前
分组）：同号多框 179 组，其中 144 组仍是「重叠噪声 → 保留最大框」（行为不变），
35 组（14 书）落入并集分支；这 35 组里 31 组的并集严格大于最大单框，即旧实现**每
组都裁掉了一块同编号图面**（其余 4 组是嵌套框，并集 == 最大框，无变化）。已收官
的书不受影响（重跑分配须先重跑检测，det_ 裁图会被消耗），此数据只用于确认阈值
IoU 0.30 的方向没有误判。

Runs under stdlib unittest:
  python flows/script/tests/test_dedupe_multi_panel_union.py
"""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[3])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
import lib.boot  # noqa: E402
lib.boot.setup()

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from flows.script.assign_figures import (  # noqa: E402
    _dedupe_by_label, _IOU_DUP, _DETECT_DPI, _overlap_clusters, _union_box, _iou)

SCALE = _DETECT_DPI / 72.0          # pt -> px at the detection render dpi
PAGE_PT = (400, 500)                # synthetic page size (pt)


def _mk_pdf(path):
    """One page with two solid black rectangles, side by side (a two-panel plot)."""
    import pymupdf as fitz
    doc = fitz.open()
    pg = doc.new_page(width=PAGE_PT[0], height=PAGE_PT[1])
    for (x0, y0, x1, y1) in (_px2pt(60, 200, 160, 320), _px2pt(240, 200, 340, 320)):
        pg.draw_rect(fitz.Rect(x0, y0, x1, y1), color=None, fill=(0, 0, 0))
    doc.save(path)
    doc.close()


def _px2pt(*box):
    return [v / SCALE for v in box]


def _e(label, page, bbox, fname):
    return {"chapter": 1, "page": page, "label": label, "bbox": list(bbox),
            "file": f"figure/{fname}", "fig_idx": 1, "caption": None}


class _Tmp(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="mpu_")
        self.fig = os.path.join(self.dir, "figure")
        os.makedirs(self.fig, exist_ok=True)
        self.pdf = os.path.join(self.dir, "book.pdf")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _crop(self, fname, box):
        """Write a solid crop matching `box` so a stale file is distinguishable."""
        x0, y0, x1, y1 = box
        arr = np.zeros((max(1, y1 - y0), max(1, x1 - x0), 3), dtype=np.uint8)
        arr[:, :, :] = (255, 0, 0)
        Image.fromarray(arr).save(os.path.join(self.fig, fname))
        return os.path.join(self.fig, fname)


class TestMultiPanelUnion(_Tmp):
    def test_disjoint_same_page_panels_are_unioned(self):
        _mk_pdf(self.pdf)
        a, b = [60, 200, 160, 320], [240, 200, 340, 320]
        self._crop("ch01_fig1.6.1.png", a)
        self._crop("ch01_fig1.6.1_2.png", b)
        entries = [_e("1.6.1", 1, a, "ch01_fig1.6.1.png"),
                   _e("1.6.1", 1, b, "ch01_fig1.6.1_2.png")]

        kept = _dedupe_by_label(entries, self.fig, pdf_path=self.pdf)

        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["bbox"], _union_box([a, b]))
        # The surviving crop must actually contain BOTH panels: black pixels in
        # its left and right thirds (the union re-crop), not the red stale crop.
        im = np.array(Image.open(os.path.join(self.fig,
                                              os.path.basename(kept[0]["file"]))))
        self.assertEqual(im.shape[1], b[2] - a[0])
        dark = im.mean(axis=2) < 128
        self.assertTrue(dark[:, : im.shape[1] // 3].any(), "panel (a) missing")
        self.assertTrue(dark[:, -im.shape[1] // 3:].any(), "panel (b) missing")
        self.assertFalse(os.path.exists(os.path.join(self.fig,
                                                     "ch01_fig1.6.1_2.png")))

    def test_overlapping_duplicates_keep_largest_without_recrop(self):
        a = [100, 100, 400, 400]
        b = [110, 110, 380, 360]          # inside a -> duplicate box
        self._crop("ch02_fig2.4.1.png", a)
        self._crop("ch02_fig2.4.1_2.png", b)
        entries = [_e("2.4.1", 7, b, "ch02_fig2.4.1_2.png"),
                   _e("2.4.1", 7, a, "ch02_fig2.4.1.png")]

        kept = _dedupe_by_label(entries, self.fig, pdf_path=None)

        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["bbox"], a)   # largest kept, unchanged
        self.assertTrue(os.path.exists(os.path.join(self.fig, "ch02_fig2.4.1.png")))

    def test_cross_page_same_label_keeps_largest(self):
        a, b = [60, 200, 160, 320], [240, 200, 340, 400]
        self._crop("ch03_fig3.1.1.png", a)
        self._crop("ch03_fig3.1.1_2.png", b)
        kept = _dedupe_by_label([_e("3.1.1", 11, a, "ch03_fig3.1.1.png"),
                                 _e("3.1.1", 12, b, "ch03_fig3.1.1_2.png")],
                                self.fig, pdf_path=None)
        self.assertEqual([e["bbox"] for e in kept], [b])

    def test_unnamed_entries_are_never_deduped(self):
        a, b = [10, 10, 50, 50], [80, 80, 120, 120]
        self._crop("ch04_unnamed_01.png", a)
        self._crop("ch04_unnamed_02.png", b)
        kept = _dedupe_by_label([_e(None, 5, a, "ch04_unnamed_01.png"),
                                 _e(None, 5, b, "ch04_unnamed_02.png")],
                                self.fig, pdf_path=None)
        self.assertEqual(len(kept), 2)

    def test_recrop_unavailable_falls_back_and_leaves_no_dangling_file(self):
        a, b = [60, 200, 160, 320], [240, 200, 340, 320]
        self._crop("ch01_fig1.6.1.png", a)
        self._crop("ch01_fig1.6.1_2.png", b)
        kept = _dedupe_by_label([_e("1.6.1", 1, a, "ch01_fig1.6.1.png"),
                                 _e("1.6.1", 1, b, "ch01_fig1.6.1_2.png")],
                                self.fig, pdf_path=None)   # no PDF -> no union
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["bbox"], a)               # larger box kept
        self.assertFalse(os.path.exists(os.path.join(self.fig,
                                                     "ch01_fig1.6.1_2.png")))


class TestOverlapClusters(_Tmp):
    def test_three_boxes_two_clusters(self):
        a = [0, 0, 100, 100]
        a2 = [5, 5, 95, 90]                 # duplicate of a
        b = [300, 0, 400, 100]              # second panel
        es = [_e("9.9.9", 1, a, "f1.png"), _e("9.9.9", 1, a2, "f2.png"),
              _e("9.9.9", 1, b, "f3.png")]
        clusters = _overlap_clusters(es)
        self.assertEqual(len(clusters), 2)
        self.assertEqual(len(clusters[0]), 2)

    def test_iou_threshold_is_the_split(self):
        a = [0, 0, 100, 100]
        half = [0, 0, 100, 60]              # IoU = 6000/(10000+6000-6000) = 0.6
        self.assertGreaterEqual(_iou(a, half), _IOU_DUP)
        thin = [0, 0, 100, 20]              # IoU = 2000/12000 < 0.3
        self.assertLess(_iou(a, thin), _IOU_DUP)

    def test_disjoint_boxes_do_not_cluster(self):
        self.assertEqual(_iou([0, 0, 10, 10], [50, 50, 60, 60]), 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
