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
    # 负向：H3 子节 / 无 § / 编号式 均不当具名节
    assert NAMED_SEC_RE.match("### § Coordinate Charts") is None
    assert NAMED_SEC_RE.match("## Smooth Structures") is None   # 缺 §
    assert NAMED_SEC_RE.match("## §5 Numbered") is None          # 数字开头→编号式，非具名
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
