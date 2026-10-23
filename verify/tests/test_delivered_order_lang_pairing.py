# -*- coding: utf-8 -*-
"""交付顺序复检（U 层 md 侧）的**语种配对**回归。

根因（Weibel ch10 实跑，2026-10-23）：verify 把按节拆分的章并成一个临时视图
`._verify_merged_<章>_<lang>.md` 再交给各层，而 `_group_lang` 只认「第N章/附录/补篇」
与「Chapter/Appendix/Supplement」两类**真实交付文件名**。视图名以 `.` 起头 → 返回 None
→ ``_pick_units_sub`` 回退源侧 ``units``，于是中文合并视图拿**英文单元正文**去定位：
实测 1/152 命中（0.7%），交付顺序判据在整章中文侧一条都没测，却照样打印覆盖率行——
「测不到」被伪装成「测过了」。修法 = 视图文件名本来就携带语种（见
``_merged_temp_path`` 文档），把它读回来。
"""
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[2])
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

from verify.script.verify_chapter import _group_lang, _merged_temp_path


def _layer():
    """按路径加载 U 层脚本（模块名与 ``lib.unit_order`` 冲突，只能显式加载）。"""
    p = os.path.join(_ROOT, "verify", "unit_order", "script", "unit_order.py")
    spec = importlib.util.spec_from_file_location("u_layer_script", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- _group_lang
def test_merged_view_filename_keeps_its_language():
    assert _group_lang(["._verify_merged_ch10_cn.md"]) == "cn"
    assert _group_lang(["._verify_merged_ch10_en.md"]) == "en"
    assert _group_lang(["/tmp/x/._verify_merged_appendixA_cn.md"]) == "cn"


def test_view_without_language_suffix_stays_unknown():
    """老命名（无语种后缀）不猜：宁可不配对，也不把中文侧当英文侧。"""
    assert _group_lang(["._verify_merged_ch10.md"]) is None


def test_real_delivery_names_are_unchanged():
    assert _group_lang(["第10章_10.1_范畴.md"]) == "cn"
    assert _group_lang(["Chapter10_10.1_TheCategory.md"]) == "en"
    assert _group_lang(["附录A_范畴论语言.md"]) == "cn"
    assert _group_lang(["notes.md"]) is None


def test_merged_temp_path_round_trips_through_group_lang():
    """`_merged_temp_path` 写出的名字必须能被 `_group_lang` 读回同一语种——两侧同源。"""
    with tempfile.TemporaryDirectory() as d:
        files = []
        for name, body in (("第10章_10.1_a.md", "第一节正文\n"),
                           ("第10章_10.2_b.md", "第二节正文\n")):
            p = os.path.join(d, name)
            with open(p, "w", encoding="utf-8") as f:
                f.write(body)
            files.append(p)
        view = _merged_temp_path(d, 10, files)
        try:
            assert _group_lang([view]) == "cn"
        finally:
            os.remove(view)


# ------------------------------------------------- U 层：视图 → 单元侧配对
def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _fake_book(root):
    """一章两节：契约 10.1=p100 / 10.2=p101；源侧英文正文、译侧中文正文。"""
    ext = os.path.join(root, "_extract")
    contract = {
        "key": "10", "type": "chapter", "name": "Ch10",
        "sub_sec": [
            {"key": "10.1", "type": "item", "name": "10.1",
             "page_start": 100, "page_end": 100},
            {"key": "10.2", "type": "item", "name": "10.2",
             "page_start": 101, "page_end": 101},
        ],
    }
    _write(os.path.join(ext, "book_structure", "ch10.json"),
           json.dumps(contract, ensure_ascii=False))
    sides = {"units": ("en", ("Section 10.1 begins here.",
                              "Section 10.2 begins here.")),
             "units-translate": ("cn", ("本节是 10.1 的中文正文。",
                                        "本节是 10.2 的中文正文。"))}
    for sub, (lang, bodies) in sides.items():
        udir = os.path.join(ext, "book_structure", sub, "ch10")
        manifest = {"language": lang,
                    "units": [{"key": "10.%d" % (i + 1), "type": "item",
                               "file": "000%d_item.md" % (i + 1)}
                              for i in range(len(bodies))]}
        _write(os.path.join(udir, "manifest.json"),
               json.dumps(manifest, ensure_ascii=False))
        for i, body in enumerate(bodies):
            _write(os.path.join(udir, "000%d_item.md" % (i + 1)), body + "\n")
    return ext


def test_chinese_merged_view_is_located_with_translated_units():
    """中文视图必须拿译侧单元定位：倒退一条也要报出来。"""
    layer = _layer()
    with tempfile.TemporaryDirectory() as d:
        ext = _fake_book(d)
        contract, _ = layer._locate(ext, "10")
        assert contract
        view = os.path.join(d, "._verify_merged_ch10_cn.md")
        # 交付次序 10.2 → 10.1（契约页码 101 → 100）= 真倒退
        _write(view, "本节是 10.2 的中文正文。\n\n本节是 10.1 的中文正文。\n")
        probs, stats = layer._delivered_order(ext, "10", view, contract)
        assert stats.get("units_dir") == "units-translate", stats
        assert stats.get("located") == 2, stats
        assert len(probs) == 1, probs
        assert "10.1" in probs[0] and "10.2" in probs[0]


def test_english_merged_view_is_located_with_source_units():
    layer = _layer()
    with tempfile.TemporaryDirectory() as d:
        ext = _fake_book(d)
        contract, _ = layer._locate(ext, "10")
        view = os.path.join(d, "._verify_merged_ch10_en.md")
        _write(view, "Section 10.2 begins here.\n\nSection 10.1 begins here.\n")
        probs, stats = layer._delivered_order(ext, "10", view, contract)
        assert stats.get("units_dir") == "units", stats
        assert stats.get("located") == 2, stats
        assert len(probs) == 1, probs
