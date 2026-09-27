"""test_p_exer_block_name_exemption.py — P 层「习题归拢块」契约**节名**豁免回归。

Etingof《Introduction to representation theory》步骤8 实测（2026-09-28）：
契约里 §5.1 / §5.9 的节名印的就是 `5.9 Problems`。告警正则 `EXER_HEADING_RE` 行尾
只认 `练习|习题|exercises?`，于是——
  * 英文版保留 `## §5.9 Problems` → `problems` 不在词表 → **放行**；
  * 中文版忠实译成 `## §5.9 习题` → 命中 → **假阳 FAIL**。
「源过 / 译不过」把译者逼向唯一出路（把节题改回英文），直接与「正文必须译」冲突。

根治 = 豁免侧新增**语言无关**的契约真值源：该节的契约名本身就是习题集标题词
（`_CONTRACT_EXER_NAME_RE`，含 problems/questions/习题/练习/问题），则任何语言的
等价译题都不是「无中生有的归拢块」。只放宽**豁免**、不放宽**告警**，故不会给别的书
新增违规（Leinster ch4 / Weibel ch5 那类契约无据的自建块照拦——本测试第 3、4 例锁死）。
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

from verbose_gates import check_exer_blocks


def _ext(contract):
    """把一棵分章契约写进临时 extract 目录，返回 ext_dir。"""
    d = tempfile.mkdtemp(prefix="bks_pexer_")
    bs = os.path.join(d, "book_structure")
    os.makedirs(bs)
    with open(os.path.join(bs, "ch5.json"), "w", encoding="utf-8") as fh:
        json.dump(contract, fh, ensure_ascii=False)
    return d


def _contract(sec_name):
    return {"key": "5", "type": "chapter", "name": "5 Quiver Representations",
            "sub_sec": [{"key": "5.9", "type": "section", "name": sec_name,
                         "text": [{"text": "some body"}]}]}


LINES_ZH = ["## §5.9 习题", "", "**问题 5.39**：设 $Q_n$ 是长度为 $n$ 的循环 quiver。"]
LINES_EN = ["## §5.9 Problems", "", "**Problem 5.39**: Let $Q_n$ be the cyclic quiver."]


def test_printed_problems_section_exempt_in_chinese():
    """事故本体：契约名 `5.9 Problems`，中文节题 `## §5.9 习题` → 不得报。"""
    ext = _ext(_contract("5.9 Problems"))
    assert check_exer_blocks(LINES_ZH, ext, "5") == []


def test_printed_problems_section_exempt_in_english():
    ext = _ext(_contract("5.9 Problems"))
    assert check_exer_blocks(LINES_EN, ext, "5") == []


def test_no_contract_evidence_still_flagged():
    """🔴 不得过度豁免：契约节名与习题无关时，自建归拢标题块照旧被抓。"""
    ext = _ext(_contract("5.9 Further results of representation theory"))
    probs = check_exer_blocks(LINES_ZH, ext, "5")
    assert any("练习归拢块" in p for p in probs), probs


def test_no_contract_at_all_still_flagged():
    """老书/无契约目录：行为不变（fail 侧不放松）。"""
    assert any("练习归拢块" in p for p in check_exer_blocks(LINES_ZH, None, None))


def test_bold_standalone_heading_respects_evidence():
    """独立加粗 `**习题**` 形态同样按节名豁免；无据时照拦。"""
    lines = ["## §5.9 表示的构造", "", "**习题**", "", "**问题 5.39**：设 $Q_n$ 是循环 quiver。"]
    ext_no = _ext(_contract("5.9 表示的构造"))
    assert any("练习归拢块" in p for p in check_exer_blocks(lines, ext_no, "5"))
    ext_yes = _ext(_contract("5.9 Exercises"))
    lines_yes = ["## §5.9 习题", "", "**习题**", "", "**问题 5.39**：设 $Q_n$ 是循环 quiver。"]
    assert check_exer_blocks(lines_yes, ext_yes, "5") == []
