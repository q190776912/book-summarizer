"""test_p_missing_sec_glued_exercise_title.py — P 层「缺节」对**题号粘连**的习题节的豁免回归。

Lehmann《Elements of Large-Sample Theory》步骤8 实测（2026-10-19）：分章契约里两节的名字
印的是 `4.5 Problems269` / `5.8 Problems349` —— OCR 把节末的**印刷页码**直接接在标题词后面，
`'s'` 与数字同为 word char，于是 `problems?\b` 失配，该节被当成「骨架必写节」，
`p_missing_sec` 要求补 `## §4.5` 标题；而习题收录规则恰恰规定
「章末集中题集块一律省略」（见 `docs/writing-rules.md` / `verbose_gates.md` 习题收录规则）。
两条判据互斥 ⇒ 唯一出路是无中生有写一个原书不存在的标题块 = 闸门 bug。

根治 = `EXER_SEC_TITLE_RE` 只新增「习题词 + 尾随数字直至词尾」一支放行形态。
跨书目普查（`_extract/_tmp_exer_title_census.py` 判据，751 份分章契约）新增命中恰为该书这两条，
即对既有全部书目零行为变化。

负向锁死（不得过度豁免）：节名与习题无关时，即使同样带尾随数字（`4.5 Examples269`），
缺节照旧报。
"""
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
    _ROOT = str(Path(__file__).resolve().parents[3])
for _p in (_ROOT, os.path.join(_ROOT, "lib"),
           os.path.join(_ROOT, "verify", "verbose_gates", "script")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

from verbose_gates import check_missing_sections  # noqa: E402


def _ext(last_title):
    """写一棵 5 节的章契约（第 5 节名可变）进临时 extract 目录。"""
    d = tempfile.mkdtemp(prefix="bks_pmiss_")
    bs = os.path.join(d, "book_structure")
    os.makedirs(bs)
    contract = {
        "key": "4", "type": "chapter", "name": "4 Estimation",
        "sub_sec": [
            {"key": "4.1", "type": "section", "name": "4.1 Introduction",
             "sub_sec": [{"text": "body one"}]},
            {"key": "4.2", "type": "section", "name": "4.2 Some estimates",
             "sub_sec": [{"text": "body two"}]},
            {"key": "4.3", "type": "section", "name": "4.3 Comparison",
             "sub_sec": [{"text": "body three"}]},
            {"key": "4.4", "type": "section", "name": "4.4 Asymptotics",
             "sub_sec": [{"text": "body four"}]},
            {"key": "4.5", "type": "section", "name": last_title,
             "sub_sec": [{"text": "body five"}]},
        ],
    }
    with open(os.path.join(bs, "ch4.json"), "w", encoding="utf-8") as fh:
        json.dump(contract, fh, ensure_ascii=False)
    return d


# md 写到 §4.4 为止：题集节 §4.5 按收录规则整块省略
MD = [
    "# Chapter 4 Estimation",
    "",
    "## §4.1 Introduction",
    "",
    "text",
    "",
    "## §4.2 Some estimates",
    "",
    "text",
    "",
    "## §4.3 Comparison",
    "",
    "text",
    "",
    "## §4.4 Asymptotics",
    "",
    "text",
    "",
]


def test_glued_problems_page_number_is_exempt():
    """事故本体：契约名 `4.5 Problems269` ⇒ 省略该节不得报缺节。"""
    assert check_missing_sections(MD, _ext("4.5 Problems269"), "4") == []


def test_glued_exercises_page_number_is_exempt():
    assert check_missing_sections(MD, _ext("4.5 EXERCISES349"), "4") == []


def test_plain_problems_title_still_exempt():
    """旧形态零回归：不带尾随数字的题集节名一向豁免。"""
    assert check_missing_sections(MD, _ext("4.5 Problems"), "4") == []


def test_non_exercise_title_with_digits_still_required():
    """🔴 不得过度豁免：与习题无关的节名即使带尾随数字，缺节照旧报。"""
    out = check_missing_sections(MD, _ext("4.5 Examples269"), "4")
    assert any("§4.5" in p for p in out), out


def test_content_section_still_required():
    out = check_missing_sections(MD, _ext("4.5 Further results"), "4")
    assert any("§4.5" in p for p in out), out


def test_glued_title_section_present_is_silent():
    """放行只针对「省略」；该节真在位时同样不报（present 集合按号命中）。"""
    md = MD + ["## §4.5 Problems", "", "Problems 4.1–4.20 omitted per rule.", ""]
    assert check_missing_sections(md, _ext("4.5 Problems269"), "4") == []
