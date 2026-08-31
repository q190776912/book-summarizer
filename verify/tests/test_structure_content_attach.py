"""Regression tests for the per-chapter content contract (2026-08-29).

Covers the structure Step-5 content attach + write-source draft rendering:
  - flows/write-source/structure/script/attach_content.py
      _is_block / _strip_header / _splice_inline / _split_proofs (proof child
      nodes) / description aggregation / attach / fingerprint_matches
      / ensure_fresh  (content blocks {"text"} / {"formula","display"},
      description nodes "D{n}" and proof child nodes "{key}-P{n}" merged into
      sub_sec in document order; per-chapter split under
      <extract_dir>/book_structure/)
  - flows/write-source/script/render_draft.py  (单元渲染库；渲染验证在
    split_draft_units 拆出的单元产物上做)

The per-chapter contract (book_structure/ch{N}.json) stays structure-only; these tests
also pin that attach() never rewrites it and that derived nodes (description /
proof) are excluded from the structural fingerprint.
"""
import json
import os
import re
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

import attach_content as ac
import render_draft as rd
import split_draft_units as sp
import check_content_completeness as cc


def _units_md(ext, ch, lang):
    """用 split_draft_units 拆分单章，按 manifest 顺序拼接全部单元正文（去首行标记）。

    🔴 2026-08-31 起渲染验证改在单元产物上做（render_draft.py 已无整章 CLI /
    render_chapter）：草稿的 writing-rules 格式由每个单元文件承载。
    """
    mp = sp.split_chapter(ext, ch, lang, force=True)
    outdir = os.path.join(ext, "book_structure", "units", "ch" + ch)
    with open(mp, encoding="utf-8") as f:
        man = json.load(f)
    parts = []
    for u in man["units"]:
        with open(os.path.join(outdir, u["file"]), encoding="utf-8") as f:
            raw = f.read()
        m = re.search(r"<!--.*?-->\n?", raw, re.S)
        body = raw[m.end():] if m else raw
        parts.append(body.strip())
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# _is_block / _iter_blocks
# ---------------------------------------------------------------------------
def test_is_block_distinguishes_content_from_structure():
    assert ac._is_block({"text": "设 X 为度量空间"})
    assert ac._is_block({"formula": "d(x,y)\\le 1", "display": False})
    assert not ac._is_block({"key": "1.1", "type": "section", "name": "1.1"})
    assert not ac._is_block({"key": "1.1-1", "type": "definition", "sub_sec": []})
    assert not ac._is_block("not a dict")
    # 派生节点是结构节点，不是内容块
    assert not ac._is_block({"type": "description", "key": "D1", "name": "", "sub_sec": []})
    assert not ac._is_block({"type": "proof", "key": "1.1-1-P1", "name": "PROOF", "sub_sec": []})


# ---------------------------------------------------------------------------
# _strip_header（标题剥离：顺序消耗式，跨拼接段生效）
# ---------------------------------------------------------------------------
def test_strip_header_drops_exact_header_block():
    blocks = [{"kind": "text", "text": "Example 1. Let G be a group."},
              {"kind": "text", "text": "Then G is abelian."}]
    out = ac._strip_header(blocks, "Example 1 Let G be a group.")
    assert len(out) == 1
    assert out[0]["text"] == "Then G is abelian."


def test_strip_header_across_inline_formulas_keeps_formula():
    # 拼接后标题行被行内公式拆开：两段文字均属标题 → 丢弃，公式保留
    blocks = [{"kind": "text", "text": "Example 1. Let "},
              {"kind": "formula", "latex": "G", "display": False},
              {"kind": "text", "text": " be a group."},
              {"kind": "text", "text": "Then G is abelian."}]
    out = ac._strip_header(blocks, "Example 1 Let G be a group.")
    assert any(b.get("kind") == "formula" for b in out)   # 公式不丢
    assert not any(b.get("text", "").startswith("Example") for b in out)
    assert out[-1]["text"] == "Then G is abelian."   # 正文首段保留


def test_strip_header_mismatch_keeps_blocks():
    blocks = [{"kind": "text", "text": "By Example 1.2 above we see"}]
    out = ac._strip_header([dict(b) for b in blocks], "Example 1.2（收敛）")
    assert out == blocks


def test_strip_header_stops_at_display_formula():
    blocks = [{"kind": "formula", "latex": "x=1", "display": True},
              {"kind": "text", "text": "Theorem 2.1 statement"}]
    out = ac._strip_header(blocks, "Theorem 2.1")
    assert out == blocks


def test_strip_header_partial_prefix_cut():
    # 标题行延续到正文（"Theorem. Let ..." 后接正文）且契约 name 截断（…）：
    # 只剥掉 name 覆盖的前缀，保留尾部正文
    blocks = [{"kind": "text", "text": "Theorem 2.1. Let f be continuous and bounded."}]
    out = ac._strip_header(blocks, "Theorem 2.1. Let f be continuous")
    assert len(out) == 1
    assert out[0]["text"].startswith("and bounded")


# ---------------------------------------------------------------------------
# _splice_inline（行内公式拼回宿主文本行）
# ---------------------------------------------------------------------------
def _txt(page, text, x0, y0, x1, y1):
    return {"page": page, "y": y0, "x": x0, "x1": x1, "bottom": y1,
            "kind": "text", "text": text}


def _fx(page, latex, x0, y0, x1, y1, display=False):
    return {"page": page, "y": y0, "x": x0, "x1": x1, "bottom": y1,
            "kind": "formula", "latex": latex, "display": display}


def test_splice_inline_places_formula_at_x_position():
    texts = [_txt(1, "the angle t lies in the range", 200.0, 100.0, 600.0, 135.0)]
    formulas = [_fx(1, "\\theta", 300.0, 100.0, 330.0, 134.0)]
    out = ac._splice_inline(texts, formulas)
    kinds = [b["kind"] for b in out]
    assert kinds == ["text", "formula", "text"]
    assert out[1]["latex"] == "\\theta"
    # 前段含 "the angle"（公式 x 位于行内约 25% 处），后段含 "lies"
    assert "the angle" in out[0]["text"]
    assert "lies" in out[2]["text"]


def test_splice_inline_keeps_unmatched_and_display_untouched():
    texts = [_txt(1, "plain line", 200.0, 100.0, 600.0, 135.0)]
    formulas = [_fx(1, "z", 900.0, 100.0, 930.0, 134.0),   # 水平不在任何行内 → 独立
                _fx(1, "E=mc^2", 200.0, 400.0, 600.0, 600.0, display=True)]  # 行间不拼
    out = ac._splice_inline(texts, formulas)
    assert sum(1 for b in out if b["kind"] == "formula") == 2
    assert out[0]["kind"] == "text"


# ---------------------------------------------------------------------------
# _attach_formula_tags（行间公式编号挂接；2026-08-29 Koopman 书实测两种版式）
# ---------------------------------------------------------------------------
def test_attach_formula_tag_inside_full_width_bbox():
    # 居中多行公式：MFD bbox 横跨整行、把右缘编号列一并圈入，编号落在 bbox 内右侧
    # （tag.x0=1015 < fx1-5=1025）——旧判据「编号必须在 bbox 右缘之外」漏挂。
    fx = _fx(1, "\\begin{array}{rl}a&=b\\end{array}", 161.0, 300.0, 1030.0, 382.0,
             display=True)
    tag = _txt(1, "(5.1)", 1015.0, 320.0, 1074.0, 357.0)
    out = ac._attach_formula_tags([fx, tag])
    assert fx["tag"] == "5.1"                  # 存**裸编号**（三处口径统一）
    assert all(b is not tag for b in out)      # 编号块从散文流剔除（纯版面锚点）


def test_attach_formula_tag_below_tall_formula():
    # MFD bbox 偏上（带上下限 / 多行公式）：编号落在 bbox 下缘甚至略下方，
    # 与公式中心距超过 0.6 行高——靠「垂直与公式带有交集」补命中。
    fx = _fx(1, "\\lim_{t\\to\\infty}", 191.0, 1364.0, 1027.0, 1445.0, display=True)
    tag = _txt(1, "(5.15)", 1000.0, 1440.0, 1074.0, 1469.0)
    ac._attach_formula_tags([fx, tag])
    assert fx["tag"] == "5.15"


def test_attach_formula_tag_ignores_inline_and_far_blocks():
    fx = _fx(1, "a=b", 150.0, 300.0, 650.0, 400.0, display=True)
    far = _txt(1, "(2.1)", 900.0, 900.0, 990.0, 935.0)      # 垂直远离
    ac._attach_formula_tags([fx, far])
    assert "tag" not in fx                                   # 宁缺勿滥
    fx2 = _fx(1, "a=b", 150.0, 300.0, 650.0, 400.0, display=True)
    pro = _txt(1, "(2.2) is used later", 900.0, 320.0, 990.0, 355.0)  # 非整块编号
    ac._attach_formula_tags([fx2, pro])
    assert "tag" not in fx2
    # 行内公式不参与编号挂接
    fx3 = _fx(1, "a=b", 150.0, 300.0, 650.0, 400.0, display=False)
    t3 = _txt(1, "(2.3)", 900.0, 320.0, 990.0, 355.0)
    ac._attach_formula_tags([fx3, t3])
    assert "tag" not in fx3


def test_attach_formula_tag_shapes_across_books():
    """编号形态按书各异——段数由 `formula.type` 派生，括号/分隔符/后缀全量支持。

    全语料实测形态（绝不可只支持 `(C.N)` 一种）：
      (1) 节级重置 / (2.17) 章.号 / (11.1-1) 章.节-号 / (8.11a) 字母后缀
      / 裸排 2.17（近半数书右缘编号不带括号）/ （2.17）全角括号
    """
    from lib.numbering import formula_tag_number

    def attach(raw, ncomp, x0=900.0):
        fx = _fx(1, "a=b", 150.0, 300.0, 650.0, 400.0, display=True)
        ac._attach_formula_tags([fx, _txt(1, raw, x0, 320.0, x0 + 70, 355.0)], ncomp)
        return fx.get("tag")

    assert attach("(2.17)", 2) == "2.17"          # 章.号（半角括号）
    assert attach("（2.17）", 2) == "2.17"        # 全角括号
    assert attach("(6)", 1) == "6"                # 节级重置单段
    assert attach("(11.1-1)", 3) == "11.1-1"      # 连字符三段
    assert attach("(8.11a)", 2) == "8.11a"        # 字母后缀子式
    assert attach("2.17", 2) == "2.17"            # 裸排编号（右缘无括号）
    assert attach("17", 1) == "17"                # 裸排单段
    # 段数不符 → 不挂（配置说了算，防止把引用号当公式号）
    assert attach("(2.17)", 1) is None
    # 裸排编号必须严格在公式右缘之外：落在公式 bbox 内的裸数字不认
    # （防列表号 / 脚注号 / 页码被误挂）
    fx = _fx(1, "a=b", 150.0, 300.0, 1050.0, 400.0, display=True)
    ac._attach_formula_tags([fx, _txt(1, "17", 500.0, 320.0, 530.0, 355.0)], 1)
    assert "tag" not in fx
    # 工具函数：整块恰为编号才返回裸编号
    assert formula_tag_number("(2.17)") == "2.17"
    assert formula_tag_number("see (2.17)") is None
    assert formula_tag_number("(A.3)") is None    # 字母开头暂不支持（Q 层同源）


def test_filter_noise_keeps_formula_tag_at_page_bottom():
    # 公式编号归一化后同为纯数字短串：排在页面下缘时不得被当作页码丢弃
    # （2026-08-29 Koopman ch7 (7.13) 实测 y=[1548,1577]，页高 1672）
    tag = _txt(1, "(7.13)", 1000.0, 1548.0, 1072.0, 1577.0)
    assert ac._filter_noise([tag], 1672.0, 30) == [tag]
    # 真页码仍须被丢弃；裸排编号不享受豁免（与页码无法区分）
    pno = _txt(1, "99", 1000.0, 1640.0, 1030.0, 1670.0)
    assert ac._filter_noise([pno], 1672.0, 30) == []
    bare = _txt(1, "7.13", 1000.0, 1548.0, 1072.0, 1577.0)
    assert ac._filter_noise([bare], 1672.0, 30) == []


# ---------------------------------------------------------------------------
# _split_proofs（证明子节点拆分）
# ---------------------------------------------------------------------------
def _blk(page, kind, **kw):
    b = {"page": page, "kind": kind}
    b.update(kw)
    return b


def test_split_proofs_en_marker_and_qed():
    blocks = [_blk(9, "text", text="Theorem 2.1. Let f be continuous."),
              _blk(9, "formula", latex="f(x)=x^2", display=True),
              _blk(9, "text", text="PROOF. Immediate from the definitions."),
              _blk(9, "text", text="口")]
    elements, trailing = ac._split_proofs("2.1-1", blocks)
    assert trailing is None                       # QED 收束，无尾随
    assert len(elements) == 3                     # 两块正文 + 1 个 proof 节点
    assert all(ac._is_block(b) for b in elements[:2])
    pr = elements[-1]
    assert pr["type"] == "proof"
    assert pr["key"] == "2.1-1-P1"
    assert pr["name"] == "PROOF"
    assert [b.get("text") for b in pr["sub_sec"]] == \
        ["PROOF. Immediate from the definitions.", "口"]   # 标记与 QED 都在证明内


def test_split_proofs_cn_marker_and_trailing_description():
    blocks = [_blk(3, "text", text="定理2.2 设函数 u 调和，则"),
              _blk(3, "formula", latex="u(M_0)=\\frac{1}{4\\pi a^2}", display=True),
              _blk(3, "text", text="证明 把公式(2.6)应用到球面上，得到"),
              _blk(3, "formula", latex="\\int_{\\Gamma} u\\,dS", display=True),
              _blk(3, "text", text="证毕"),
              _blk(3, "text", text="这就是所要证明的平均值公式，下面讨论极值原理。")]
    elements, trailing = ac._split_proofs("定理2.2", blocks)
    assert trailing is not None and len(trailing) == 1   # 证毕后的散文 → 尾随
    assert "平均值公式" in trailing[0]["text"]
    pr = [e for e in elements if not ac._is_block(e)]
    assert len(pr) == 1
    assert pr[0]["type"] == "proof" and pr[0]["key"] == "定理2.2-P1"
    assert pr[0]["name"] == "证明"
    # 陈述与证明保序：statement 块在前，proof 节点在末位（尾随散文已剥离）
    assert elements[-1] is pr[0]
    assert all(ac._is_block(b) for b in elements[:-1])


def test_split_proofs_cn_inline_marker_merged_line():
    # 中文书「证」与陈述同行被 OCR 合并："……(2.13)证 把公式……" → 内联拆分
    blocks = [_blk(5, "text", text="定理2.3 极值原理）调和函数在内部不取极值。"),
              _blk(5, "text", text="用反证法。设调和函数u不恒等于常数。证 把公式(2.6)应用到球面上，得到"),
              _blk(5, "text", text="这与平均值公式矛盾，"),
              _blk(5, "text", text="证毕")]
    elements, trailing = ac._split_proofs("定理2.3", blocks)
    pr = [e for e in elements if not ac._is_block(e)]
    assert len(pr) == 1
    assert pr[0]["name"] == "证"
    # 陈述尾段（含句末标点）留在条目正文；「证…」起进入证明
    texts = [b["text"] for b in elements if ac._is_block(b) and "text" in b]
    assert any("用反证法" in t for t in texts)
    assert any("把公式(2.6)" in t for t in [b.get("text", "") for b in pr[0]["sub_sec"]])
    assert any(b.get("text") == "证毕" for b in pr[0]["sub_sec"])   # QED 归入证明
    assert trailing is None


def test_split_proofs_no_false_positive_on_prose():
    # 「证明了 / 验证 / 保证」等非标记词不得触发拆分
    blocks = [_blk(1, "text", text="这就证明了u满足(1.12)式。还可以进一步验证,若p满足条件，"),
              _blk(1, "text", text="则可以保证解的存在性。")]
    elements, trailing = ac._split_proofs("1.1-9", blocks)
    assert trailing is None
    assert all(ac._is_block(b) for b in elements)


def test_split_proofs_no_marker_passthrough():
    blocks = [_blk(1, "text", text="A definition body without any proof."),
              _blk(1, "formula", latex="x>0", display=False)]
    elements, trailing = ac._split_proofs("1.1-1", blocks)
    assert trailing is None
    assert len(elements) == 2 and all(ac._is_block(b) for b in elements)


def test_make_description_node():
    blocks = [_blk(7, "text", text="This chapter is a very rapid introduction."),
              _blk(8, "text", text="More details can be found in any good introductory text.")]
    node = ac._make_description("D1", blocks)
    assert node["type"] == "description" and node["key"] == "D1"
    assert node["name"] == ""                        # 无序标 → name 恒空
    assert node["page_start"] == 7 and node["page_end"] == 8
    assert all(ac._is_block(b) for b in node["sub_sec"])
    assert not ac._is_block(node)                    # 它本身是结构节点


# ---------------------------------------------------------------------------
# _mark_line_geometry（几何事实字段：line_start / indent；不烘焙段落判断）
# ---------------------------------------------------------------------------
def test_mark_line_geometry_fields():
    # 页几何：左边界 100，字高 30 → 缩进 60 ≈ 2.0 字高
    blocks = [
        _txt(1, "正文第一行顶格续写。", 100.0, 100.0, 500.0, 130.0),
        _txt(1, "段落首（缩进两字符）。", 160.0, 140.0, 500.0, 170.0),   # Δ=60=2h → 缩进行首
        _txt(1, "同行 OCR 右碎片", 260.0, 141.0, 400.0, 170.0),          # 与上行 y 重合 → 无字段
        _txt(1, "续行顶格。", 100.0, 180.0, 500.0, 210.0),               # Δ=0 → 仅 line_start
        _txt(1, "居中公式行", 600.0, 220.0, 900.0, 250.0),               # Δ=500 → line_start + 大 indent
        _txt(2, "跨页续行顶格。", 100.0, 40.0, 500.0, 70.0),             # page 2 页首块 → 恒为新行
        _txt(2, "跨页段落首（缩进）。", 165.0, 80.0, 500.0, 110.0),      # page 2 left=100 Δ=65
    ]
    ac._mark_line_geometry(blocks)
    f = [(b["text"][:6], "line_start" in b, b.get("indent")) for b in blocks]
    assert f[0][1] is True and f[0][2] is None            # 页首块：新行、无缩进
    assert f[1][1] is True and f[1][2] == 2.0             # 缩进行首：两字段都写
    assert f[2][1] is False and f[2][2] is None           # 同行碎片：都没有 → 续前一句
    assert f[3][1] is True and f[3][2] is None            # 顶格新行：仅 line_start
    assert f[4][1] is True and f[4][2] == 16.7            # 居中行：事实照写，由消费方判断
    assert f[5][1] is True and f[5][2] is None            # 跨页续行：新行、顶格
    assert f[6][1] is True and f[6][2] == 2.2             # 跨页段落首（按本页边界）


def test_to_content_carries_line_geometry():
    b = _txt(1, "段落首（缩进）。", 160.0, 140.0, 500.0, 170.0)
    b["line_start"] = True
    b["indent"] = 2.0
    assert ac._to_content(b) == {"text": "段落首（缩进）。",
                                 "line_start": True, "indent": 2.0}
    # 顶格新行：仅 line_start；同行碎片：都没有
    assert ac._to_content(_txt(1, "续行。", 100.0, 140.0, 500.0, 170.0)) == {"text": "续行。"}
    c = _txt(1, "续行。", 100.0, 140.0, 500.0, 170.0)
    c["line_start"] = True
    assert ac._to_content(c) == {"text": "续行。", "line_start": True}


def test_render_display_formula_emits_tag():
    # 带编号的行间公式：\tag{} 独立一行落在 $$ 块内（书无号不编造）
    for stored, want in (("2.17", "\\tag{2.17}"), ("(2.17)", "\\tag{2.17}"),
                         ("11.1-1", "\\tag{11.1-1}"), ("8.11a", "\\tag{8.11a}"),
                         ("6", "\\tag{6}")):
        out, buf = [], []
        rd._emit_blocks([{"formula": "a=b", "display": True, "tag": stored}], out, buf)
        rd._flush(buf, out)
        assert out[:4] == ["$$", "a=b", want, "$$"], stored
    # 无编号公式不带 \tag；行内公式永不带 \tag
    out2, buf2 = [], []
    rd._emit_blocks([{"formula": "a=b", "display": True},
                     {"formula": "x", "display": False, "tag": "2.18"}], out2, buf2)
    rd._flush(buf2, out2)
    assert "\\tag" not in "\n".join(out2)


def test_render_breaks_paragraph_on_indent_band():
    # 渲染消费方判断：line_start + indent ∈ [0.8, 3.5] → 另起一段；顶格续行不另起
    out, buf = [], []
    blocks = [{"text": "第一段第一句。"},
              {"text": "第一段第二句续行。", "line_start": True},
              {"text": "第二段第一句。", "line_start": True, "indent": 2.0},
              {"text": "同行碎片不另起。"}]
    rd._emit_blocks(blocks, out, buf)
    rd._flush(buf, out)
    paras = [ln for ln in out if ln.strip()]
    assert len(paras) == 2
    assert paras[0].startswith("第一段第一句。")
    assert paras[1].startswith("第二段第一句。")


# ---------------------------------------------------------------------------
# attach 端到端（临时 extract 目录：page json + 单文件契约 → 分章内容契约）
# ---------------------------------------------------------------------------
def _make_book_structure():
    return {
        "key": -1, "type": -1, "name": "T", "page_start": 1, "page_end": 2,
        "sub_sec": [{
            "key": "1", "type": "chapter", "name": "1 Intro", "page_start": 1,
            "page_end": 2, "sub_sec": [{
                "key": "1.1", "type": "section", "name": "1.1 Basics",
                "page_start": 1, "page_end": 2, "sub_sec": [
                    {"key": "1.1-1", "type": "definition",
                     "name": "1.1-1 Definition (Metric).",
                     "page_start": 1, "page_end": 1, "sub_sec": []},
                    {"key": "1.1.A", "type": "exercise", "name": "1.1.A",
                     "page_start": 2, "page_end": 2, "sub_sec": []},
                    {"key": "1.1-E1", "type": "example",
                     "name": "1.1-E1 Example (Dirac mass).",
                     "page_start": 2, "page_end": 2, "sub_sec": []},
                    # 章末集中习题块练习：consolidated=true → 草稿省略
                    {"key": "1.1.B", "type": "exercise", "name": "1.1.B",
                     "page_start": 2, "page_end": 2, "consolidated": True,
                     "sub_sec": []},
                ]}]}],
    }


def _make_page(p, blocks, formulas):
    return {"page": p, "text": blocks, "formulas": formulas, "deskew": 0.0}


def test_attach_split_fingerprint_and_draft_roundtrip():
    tmp = tempfile.mkdtemp(prefix="bks_attach_")
    ext = os.path.join(tmp, "_extract")
    os.makedirs(ext)

    # page 1：页眉噪声 + 章首序言 + 节标题 + 节导语 + 条目正文（含行内/行间公式）+ 证明
    p1 = _make_page(1,
        [{"poly": [100, 55, 700, 55, 700, 85, 100, 85],
          "text": "CHAPTER 1. INTRO", "score": 0.9},
         {"poly": [100, 92, 700, 92, 700, 96, 100, 96],
          "text": "This chapter introduces the basic notions.", "score": 0.9},
         {"poly": [100, 100, 700, 100, 700, 135, 100, 135],
          "text": "1.1 Basics", "score": 0.9},
         {"poly": [100, 140, 700, 140, 700, 158, 100, 158],
          "text": "In this section we study the basic notions.", "score": 0.9},
         {"poly": [100, 160, 700, 160, 700, 195, 100, 195],
          "text": "1.1-1 Definition (Metric). A metric on a set X is a map", "score": 0.9},
         {"poly": [100, 210, 700, 210, 700, 900, 100, 900],
          "text": "satisfying positivity and symmetry.", "score": 0.9},
         {"poly": [100, 760, 700, 760, 700, 790, 100, 790],
          "text": "PROOF. Immediate from the definitions.", "score": 0.9},
         {"poly": [100, 860, 700, 860, 700, 885, 100, 885],
          "text": "口", "score": 0.9}],
        [{"bbox": [400, 160, 470, 194], "cls": 0, "conf": 0.9, "latex": "d: X\\times X\\to R"},
         {"bbox": [150, 400, 650, 700], "cls": 1, "conf": 0.9,
          "latex": "d(x,y)\\ge 0"}])
    # page 2：页眉（与 page 1 重复 → 噪声过滤）+ 练习
    p2 = _make_page(2,
        [{"poly": [100, 60, 700, 60, 700, 90, 100, 90],
          "text": "CHAPTER 1. INTRO", "score": 0.9},
         {"poly": [100, 160, 700, 160, 700, 195, 100, 195],
          "text": "1.1.A Show that d is continuous.", "score": 0.9}],
        [])
    with open(os.path.join(ext, "page_001.json"), "w", encoding="utf-8") as f:
        json.dump(p1, f, ensure_ascii=False)
    with open(os.path.join(ext, "page_002.json"), "w", encoding="utf-8") as f:
        json.dump(p2, f, ensure_ascii=False)
    with open(os.path.join(ext, "_extraction_done.json"), "w", encoding="utf-8") as f:
        json.dump({"ok": True}, f)
    # 图检测产物：page 1 一张图（y=300 → 落在定义条目正文中间）
    with open(os.path.join(ext, "figure_index.json"), "w", encoding="utf-8") as f:
        json.dump([{"chapter": 1, "page": 1, "fig_idx": 1, "label": None,
                    "bbox": [200, 300, 600, 500], "conf": 0.9,
                    "file": "figure/ch01_unnamed_01.png",
                    "caption": "A SAMPLE PATH", "source": "detect"}], f, ensure_ascii=False)
    # 骨架分章文件（build_structure 产物形态）：ch1.json 顶层即该章节点
    single = ac.chapter_json_path(ext, "1")
    os.makedirs(os.path.dirname(single), exist_ok=True)
    book = _make_book_structure()
    with open(single, "w", encoding="utf-8") as f:
        json.dump(book["sub_sec"][0], f, ensure_ascii=False)

    written = ac.attach(ext)
    assert len(written) == 1
    per_ch = ac.out_path(ext, "1")
    assert os.path.exists(per_ch)

    with open(per_ch, encoding="utf-8") as f:
        ch = json.load(f)
    assert ch["type"] == "chapter" and ch["key"] == "1"

    # 章首序言 → description 节点（key D1，置于章 sub_sec 最前）
    pre = ch["sub_sec"][0]
    assert pre["type"] == "description" and pre["key"] == "D1" and pre["name"] == ""
    assert any("introduces the basic notions" in b.get("text", "") for b in pre["sub_sec"])

    # 节：sub_sec = [节导语 description(D2), 定义条目（含 proof 子节点）, 练习]
    sec = ch["sub_sec"][1]
    assert sec["type"] == "section"
    assert sec["sub_sec"][0]["type"] == "description"
    assert sec["sub_sec"][0]["key"] == "D2"
    assert any("In this section" in b.get("text", "") for b in sec["sub_sec"][0]["sub_sec"])

    # 条目：正文块 + proof 子节点（statement 在前、proof 在后，保序）
    item = sec["sub_sec"][1]
    assert item["key"] == "1.1-1"
    blocks = [b for b in item["sub_sec"] if ac._is_block(b)]
    proofs = [n for n in item["sub_sec"] if n.get("type") == "proof"]
    assert len(proofs) == 1
    pr = proofs[0]
    assert pr["type"] == "proof" and pr["key"] == "1.1-1-P1" and pr["name"] == "PROOF"
    assert any("Immediate from the definitions" in b.get("text", "") for b in pr["sub_sec"])
    assert any(b.get("text") == "口" for b in pr["sub_sec"])      # QED 收尾块归入证明
    latexes = [b["formula"] for b in ac._iter_blocks(item) if "formula" in b]
    assert "d(x,y)\\ge 0" in latexes            # 行间公式保留（在 statement 内）
    assert any("d: X" in s for s in latexes)    # 行内公式（拼接或独立）保留
    assert any("positivity" in b.get("text", "") for b in blocks)
    # 图片块：内容即裁剪图路径（书根相对 figure/xxx.png，2026-09-01 起），
    # 落在其 bbox 对应的阅读位置（条目正文内）
    imgs = [b for b in ac._iter_blocks(item) if "image" in b]
    assert imgs and imgs[0]["image"] == "figure/ch01_unnamed_01.png"

    # 页眉噪声被过滤
    ex_texts = [b["text"] for b in ac._iter_blocks(ch) if "text" in b]
    assert not any("CHAPTER 1. INTRO" in t for t in ex_texts)
    # 练习内容也在（全量纳入）
    ex = [n for n in sec["sub_sec"] if n.get("type") == "exercise"][0]
    assert any("continuous" in b.get("text", "") for b in ex["sub_sec"])

    # attach 幂等：对已挂内容的契约重复 attach，块多重集不变
    def block_sig(n):
        import collections
        sig = collections.Counter()
        for b in ac._iter_blocks(n):
            sig[(("image" if "image" in b else "formula" if "formula" in b else "text"),
                 b.get("image") or b.get("formula") or b.get("text"))] += 1
        return sig
    before_sig = block_sig(ch)
    ac.attach(ext, ["1"])
    with open(per_ch, encoding="utf-8") as f:
        ch_re = json.load(f)
    assert block_sig(ch_re) == before_sig

    # 回填模拟：骨架加一个条目（改 ch1.json）→ attach 后新条目同样获得内容
    with open(per_ch, encoding="utf-8") as f:
        ch2 = json.load(f)
    sec2 = [n for n in ch2["sub_sec"] if n.get("type") == "section"][0]
    sec2["sub_sec"].append(
        {"key": "1.1-2", "type": "theorem", "name": "1.1-2 Theorem",
         "page_start": 2, "page_end": 2, "sub_sec": []})
    json.dump(ch2, open(per_ch, "w", encoding="utf-8"), ensure_ascii=False)
    ac.attach(ext, ["1"])
    with open(per_ch, encoding="utf-8") as f:
        ch3 = json.load(f)
    sec3 = [n for n in ch3["sub_sec"] if n.get("type") == "section"][0]
    th = [n for n in sec3["sub_sec"] if n.get("key") == "1.1-2"][0]
    assert isinstance(th.get("sub_sec"), list)   # 新条目也进入 attach 管线

    # 渲染验证（2026-08-31 起在单元产物上做）：writing-rules 书写格式——标签冒号
    # 接正文、例块 > 包裹、证明思路块引用、图片行、序言纯段落、consolidated 练习省略
    md = _units_md(ext, "1", "en")
    assert "# Chapter 1: Intro" in md
    assert "## §1.1 Basics" in md
    assert "**1.1-1 Definition (Metric).**:" in md              # 标签冒号接正文（EN）
    assert "$$\nd(x,y)\\ge 0\n$$" in md
    assert "**1.1.A**:" in md                                   # 穿插练习保留
    assert "1.1.B" not in md                                    # 集中习题块省略
    assert "> **1.1-E1 Example (Dirac mass).**:" in md          # 例块 > 包裹
    assert '<div style="display:flex; gap:6px; flex-wrap:wrap; justify-content:center">' in md  # 原嵌图格式
    assert '<img src="figure/ch01_unnamed_01.png"' in md   # 书根相对路径（figure 与 md 同级）
    assert 'height="auto">' in md                                  # bbox 比例 width
    assert "This chapter introduces the basic notions." in md   # 章首序言纯段落
    assert "In this section we study the basic notions." in md  # 节导语纯段落
    assert "Immediate from the definitions." in md
    # 证明：完整原文逐块输出（草稿零压缩 → 标签是「Proof」而非「Proof sketch」）
    assert "> **Proof**:" in md
    assert "Proof sketch" not in md


def test_render_draft_keeps_full_proof_and_description():
    """草稿零压缩：证明与描述信息的**每一块**都必须原样出现在 md 里。

    Tier 压缩只发生在最终 md 的调整步骤（且只压表述不删内容），渲染器**不得**
    摘要化 / 跳步 / 截断。此测试钉死该契约，防后续"优化"悄悄丢内容。
    """
    tmp = tempfile.mkdtemp(prefix="bks_nocompress_")
    ext = os.path.join(tmp, "_extract")
    os.makedirs(os.path.join(ext, "book_structure"), exist_ok=True)
    proof_body = ["Step one of a long derivation.",
                  "Step two uses the substitution above.",
                  "Step three concludes the argument."]
    desc_body = ["Motivation for the whole section.",
                 "Second descriptive paragraph, kept verbatim."]
    node = {
        "key": "1", "type": "chapter", "name": "1 Intro",
        "page_start": 1, "page_end": 1, "sub_sec": [
            {"type": "description", "key": "D1", "name": "",
             "page_start": 1, "page_end": 1,
             "sub_sec": [{"text": t} for t in desc_body]},
            {"key": "1.1-1", "type": "theorem", "name": "1.1-1 Theorem",
             "page_start": 1, "page_end": 1, "sub_sec": [
                 {"text": "Statement of the theorem."},
                 {"type": "proof", "key": "1.1-1-P1", "name": "PROOF",
                  "page_start": 1, "page_end": 1,
                  # QED 用 ASCII 形态：英文书草稿会剔除 CJK 字形（双语铁律），
                  # 写「口」会被清掉、测不出"QED 是否保留"
                  "sub_sec": ([{"text": "PROOF."}]
                              + [{"text": t} for t in proof_body]
                              + [{"formula": "a=b", "display": True},
                                 {"text": "Q.E.D."}])},
             ]}]}
    json.dump(node, open(ac.chapter_json_path(ext, "1"), "w", encoding="utf-8"),
              ensure_ascii=False)
    md = _units_md(ext, "1", "en")
    # 描述信息：每个源段都在
    for t in desc_body:
        assert t in md
    # 证明：每一步、每个公式、QED 都在，且顺序不改
    pos = [md.find(t) for t in proof_body]
    assert all(p >= 0 for p in pos) and pos == sorted(pos)
    assert "a=b" in md and "Q.E.D." in md       # 公式与 QED 一块不少
    # 零压缩 → 不出现省略号式截断标记
    assert "…" not in md and "..." not in md

# ---------------------------------------------------------------------------
# check_content_completeness（内容完整性闸门）
# ---------------------------------------------------------------------------
def test_content_gate_pass_fail_roundtrip():
    tmp = tempfile.mkdtemp(prefix="bks_gate_")
    ext = os.path.join(tmp, "_extract")
    os.makedirs(ext)
    p1 = {"page": 1, "text": [
        {"poly": [100, 100, 700, 100, 700, 135, 100, 135],
         "text": "1.1 Basics", "score": 0.9},
        {"poly": [100, 160, 700, 160, 700, 195, 100, 195],
         "text": "1.1-1 Definition (Metric). A metric orders a set.", "score": 0.9}],
        "formulas": [
            {"bbox": [150, 300, 650, 400], "cls": 1, "conf": .9,
             "latex": "d(x,y)\\ge 0"}], "deskew": 0}
    json.dump(p1, open(os.path.join(ext, "page_001.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    json.dump({"ok": 1}, open(os.path.join(ext, "_extraction_done.json"), "w"))
    json.dump([{"chapter": 1, "page": 1, "fig_idx": 1, "label": None,
                "bbox": [150, 300, 650, 400], "conf": .9,
                "file": "figure/ch01_fig.png", "caption": "", "source": "detect"}],
              open(os.path.join(ext, "figure_index.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    os.makedirs(os.path.join(ext, "book_structure"), exist_ok=True)
    json.dump({"key": "1", "type": "chapter", "name": "1 Intro",
               "page_start": 1, "page_end": 1, "sub_sec": [
                   {"key": "1.1", "type": "section", "name": "1.1 Basics",
                    "page_start": 1, "page_end": 1, "sub_sec": [
                        {"key": "1.1-1", "type": "definition",
                         "name": "1.1-1 Definition (Metric).",
                         "page_start": 1, "page_end": 1, "sub_sec": []}]}]},
              open(ac.chapter_json_path(ext, "1"), "w", encoding="utf-8"),
              ensure_ascii=False)

    ac.attach(ext)
    assert cc.main([ext, "1"]) == 0                    # 脚本输出原样 → PASS

    per = ac.out_path(ext, "1")
    ch = json.load(open(per, encoding="utf-8"))

    def strip_img(n):
        n["sub_sec"] = [c for c in n.get("sub_sec") or [] if "image" not in c]
        for c in n.get("sub_sec") or []:
            if not ac._is_block(c):
                strip_img(c)

    strip_img(ch)
    json.dump(ch, open(per, "w", encoding="utf-8"), ensure_ascii=False)
    assert cc.main([ext, "1"]) == 1                    # 缺图片块 → FAIL

    ac.attach(ext, ["1"])                              # 重挂恢复
    ch = json.load(open(per, encoding="utf-8"))

    def drop_text(n):
        for i, c in enumerate(n.get("sub_sec") or []):
            if "text" in c:
                del n["sub_sec"][i]
                return True
            if not ac._is_block(c) and drop_text(c):
                return True
        return False

    assert drop_text(ch)
    json.dump(ch, open(per, "w", encoding="utf-8"), ensure_ascii=False)
    assert cc.main([ext, "1"]) == 1                    # 丢文字块 → FAIL


def test_content_gate_detects_dropped_formula_tags():
    """内容完整性闸门必须感知公式序标丢失（2026-08-29 Koopman 盲区修复）。

    旧实现的公式块签名只含 latex+display，且校验①是「同管线自复算 vs 磁盘」的
    自证比对——把契约里全部 tag 抹掉后两侧同样缺失，闸门仍报 PASS。
    """
    tmp = tempfile.mkdtemp(prefix="bks_gate_tag_")
    ext = os.path.join(tmp, "_extract")
    os.makedirs(ext)
    p1 = {"page": 1, "text": [
        {"poly": [100, 100, 700, 100, 700, 135, 100, 135],
         "text": "1.1 Basics", "score": .9},
        {"poly": [100, 160, 700, 160, 700, 195, 100, 195],
         "text": "1.1-1 Definition (Metric). A metric orders a set.", "score": .9},
        # 右缘独立编号块：须挂到下面的行间公式上
        {"poly": [800, 318, 900, 318, 900, 353, 800, 353],
         "text": "(1.1)", "score": .9}],
        "formulas": [{"bbox": [150, 300, 650, 400], "cls": 1, "conf": .9,
                      "latex": "d(x,y)\\ge 0"}], "deskew": 0}
    json.dump(p1, open(os.path.join(ext, "page_001.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    json.dump({"ok": 1}, open(os.path.join(ext, "_extraction_done.json"), "w"))
    os.makedirs(os.path.join(ext, "book_structure"), exist_ok=True)
    json.dump({"key": "1", "type": "chapter", "name": "1 Intro",
               "page_start": 1, "page_end": 1, "sub_sec": [
                   {"key": "1.1", "type": "section", "name": "1.1 Basics",
                    "page_start": 1, "page_end": 1, "sub_sec": [
                        {"key": "1.1-1", "type": "definition",
                         "name": "1.1-1 Definition (Metric).",
                         "page_start": 1, "page_end": 1, "sub_sec": []}]}]},
              open(ac.chapter_json_path(ext, "1"), "w", encoding="utf-8"),
              ensure_ascii=False)

    ac.attach(ext)
    per = ac.out_path(ext, "1")
    ch = json.load(open(per, encoding="utf-8"))
    tagged = [b for b in ac._iter_blocks(ch) if b.get("tag")]
    assert [b["tag"] for b in tagged] == ["1.1"]          # 编号已挂上（裸编号）
    assert cc.main([ext, "1"]) == 0                       # 齐备 → PASS

    # 独立真值：书源有 1.1 这块编号（裸编号口径）
    assert cc._source_formula_tags(ext, 1, 1, "1") == {"1.1"}

    # 抹掉全部 tag（等价旧盲区场景）→ 闸门必须 FAIL
    ch = json.load(open(per, encoding="utf-8"))
    for b in ac._iter_blocks(ch):
        b.pop("tag", None)
    json.dump(ch, open(per, "w", encoding="utf-8"), ensure_ascii=False)
    assert cc.main([ext, "1"]) == 1
