"""split_chapters 无编号具名节判据：`## § 名称`（Lee 式具名节）按序数 1..k 拆分，
`### § 子节` 留在父节内不单独成文件；编号式文件仍走 SPLIT_RE 路径不受影响。"""
import os
import sys
import tempfile
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[3])
for _p in (_ROOT, os.path.join(_ROOT, "lib"), os.path.join(_ROOT, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from split_chapters import NAMED_SEC_RE, split_one_file


def test_named_re_positive_negative():
    assert NAMED_SEC_RE.match("## § Smooth Structures").group(1) == "Smooth Structures"
    assert NAMED_SEC_RE.match("## § 拓扑流形 (Topological Manifolds)")
    # 字母式节号（Axler `## §2A 名称`）：前缀消费、名称组取其后文本
    m = NAMED_SEC_RE.match("## §2A Outer Measure on R")
    assert m and m.group(1) == "Outer Measure on R"
    m = NAMED_SEC_RE.match("## §11B 傅里叶级数与单位圆的 $L^p$ (Fourier Series and $L^p$ of Unit Circle)")
    assert m and m.group(1).startswith("傅里叶级数与单位圆的")
    # 负向：H3 子节 / 无 § / 编号式 均不当具名节
    assert NAMED_SEC_RE.match("### § Coordinate Charts") is None
    assert NAMED_SEC_RE.match("## Smooth Structures") is None   # 缺 §
    assert NAMED_SEC_RE.match("## §5 Numbered") is None          # 数字+空白→编号式，非具名
    assert NAMED_SEC_RE.match("## §2.1 Numbered") is None        # 点分编号→编号式
    assert NAMED_SEC_RE.match("# § Chapter Title") is None       # H1 不当节


def _write(d, name, text):
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


def test_split_one_file_named_sections_end_to_end():
    text = "\n".join([
        "# Chapter 7: Lie Groups",
        "",
        "Intro paragraph before first section.",
        "",
        "## § Basic Definitions",
        "body A line 1",
        "body A line 2",
        "",
        "## § Lie Subgroups",
        "body B line",
        "",
        "### § A Subsection",
        "sub body stays in Lie Subgroups file",
        "",
        "## § Group Actions",
        "body C line",
        "",
    ]) + "\n"
    with tempfile.TemporaryDirectory() as d:
        src = _write(d, "Chapter7_Lie_Groups.md", text)
        written = split_one_file(src, 10 ** 9, 7, "en", dry_run=False, force=True)
        names = sorted(os.path.basename(p) for p in written)
        assert names == [
            "Chapter7_1_BasicDefinitions.md",
            "Chapter7_2_LieSubgroups.md",
            "Chapter7_3_GroupActions.md",
        ], names
        # 章标题 H1 注入每个节文件
        for p in written:
            body = open(p, encoding="utf-8").read()
            assert body.startswith("# Chapter 7: Lie Groups"), p
        # 引言并入第一节
        first = open(os.path.join(d, "Chapter7_1_BasicDefinitions.md"), encoding="utf-8").read()
        assert "Intro paragraph before first section." in first
        # 子节留在父节文件内，且不成独立文件
        second = open(os.path.join(d, "Chapter7_2_LieSubgroups.md"), encoding="utf-8").read()
        assert "### § A Subsection" in second
        assert "sub body stays in Lie Subgroups file" in second


def test_split_one_file_numbered_still_uses_split_re():
    # 编号式：不受具名节分支影响，仍产 §N 键
    text = "\n".join([
        "# Chapter 2: Smooth Maps",
        "",
        "## §1 Maps",
        "a",
        "## §2 Composition",
        "b",
        "",
    ]) + "\n"
    with tempfile.TemporaryDirectory() as d:
        src = _write(d, "Chapter2_Smooth_Maps.md", text)
        written = split_one_file(src, 10 ** 9, 2, "en", dry_run=False, force=True)
        names = sorted(os.path.basename(p) for p in written)
        assert names == ["Chapter2_1_Maps.md", "Chapter2_2_Composition.md"], names


def test_split_one_file_letter_sections_end_to_end():
    # 字母式节号（Axler `## §2A 名称`）：按出现顺序赋 1..k 序数键，与
    # 英文版手工拆分 ChapterN_1..k 键位对齐（规则3 配对闸要求节号集合一致）
    text = "\n".join([
        "# 第 2 章 测度",
        "",
        "章引言并入第 1 节",
        "",
        "## §2A 实数集上的外测度 (Outer Measure on R)",
        "body A",
        "",
        "## §2B 可测空间与可测函数 (Measurable Spaces and Functions)",
        "body B",
        "",
        "### §2B.1 子节留父节",
        "sub body",
        "",
    ]) + "\n"
    with tempfile.TemporaryDirectory() as d:
        src = _write(d, "第2章_测度.md", text)
        written = split_one_file(src, 10 ** 9, 2, "zh", dry_run=False, force=True)
        names = sorted(os.path.basename(p) for p in written)
        assert names == [
            "第2章_1_实数集上的外测度(OuterMeasureonR).md",
            "第2章_2_可测空间与可测函数(MeasurableSpacesandFunctions).md",
        ], names
        first = open(written[0], encoding="utf-8").read()
        assert "章引言并入第 1 节" in first
        assert first.startswith("# 第 2 章 测度")
        second = open(written[1], encoding="utf-8").read()
        assert "### §2B.1 子节留父节" in second
