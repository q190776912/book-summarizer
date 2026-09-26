"""split_chapters 节标题判据测试：§N / N.M / §N-M 三式与负向用例。"""
import os
import re
import sys
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

from split_chapters import SPLIT_RE, chapter_num_from_filename


def _key(line, num):
    """复刻 split_one_file 的 key 判定（组号与工具同步）。"""
    m = SPLIT_RE.match(line)
    if not m:
        return None
    if m.group(2) is not None:
        return m.group(2)
    if m.group(3) is not None:
        return f"{m.group(3)}-{m.group(4)}" if int(m.group(3)) == num else None
    if m.group(5) and int(m.group(5)) == num:
        return f"{m.group(5)}.{m.group(6)}"
    return None


def test_dashed_section_headings():
    assert _key("## §5-1 Introduction", 5) == "5-1"
    assert _key("## §4-3 The Gauss Theorem", 4) == "4-3"
    assert _key("### §5-10 Abstract Surfaces", 5) == "5-10"


def test_dashed_wrong_chapter_skipped():
    assert _key("## §4-2 Isometries", 5) is None  # 首数字≠章号，不当节


def test_dashed_subsection_not_matched():
    assert _key("## §5-10.1 Something", 5) is None  # 子节不误判


def test_plain_headings_not_dashed_sections():
    assert _key("### 5-10. Exercise 5-10", 5) is None  # 无 § 不认 dash 式
    assert _key("**Theorem 5-1.**", 5) is None


def test_existing_styles_still_work():
    assert _key("## §2. Derived Categories", 2) == "2"
    assert _key("## 1.3 Triangulated", 1) == "1.3"
    assert _key("### §4.4 Parallel Transport", 4) == "4.4"
    assert _key("## 1.3.4 Subsection", 1) is None  # N.M.P 不当节


def test_splitter_matches_full_heading_line_format():
    m = SPLIT_RE.match("## §5-1 Introduction")
    assert m and m.group(3) == "5" and m.group(4) == "1"


def test_filename_pairing_recognizes_dashed_sections():
    assert chapter_num_from_filename("Chapter5_5-1_Introduction.md") == (None, None)
    assert chapter_num_from_filename("Chapter5_Global.md") == (5, "en")
