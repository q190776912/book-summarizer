"""test_translate_parity_marker_manifest.py — 判据 12「单元首行标记 ↔ 本侧 manifest」回归。

Etingof《Introduction to representation theory》步骤6 实测（2026-09-28）：翻译代理改写过
`units-translate/ch1/0063`、`0064`、`ch6/0021` 的**首行** `name=`（把拆分时截断的 60 字符
标题补全、顺手多敲字符）。第 1 项只比两侧 `manifest.json` 字段，故这一行脱账后 gate 与
parity 双双放行——「代理有没有动过首行」失去唯一证据。跨书探针又查出 real-analysis 2 文件
（`type=desc` vs manifest `description`）、Robinson 动力学 18 文件（含**源侧**首行存着 UTF-8
二次解码乱码、manifest 才是正确箭头的）。

本测试锁：
1. 四字段任一与 manifest 脱账必须报，且报出**是哪个字段**；
2. CRLF 单元文件**不得**因行尾 CR 参与比较而全书假报（工具实现踩过的坑）；
3. 逐字一致（含 `name=` 为空的 desc 单元）必须放行；首行不可解析须报。
"""
import os
import sys
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[3])
for _p in (_ROOT, os.path.join(_ROOT, "lib"),
           os.path.join(_ROOT, "flows", "write-source", "script")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

from lib.unit_markers import marker_manifest_mismatch  # noqa: E402

REC = {"id": "0063", "type": "item", "key": "1.44", "name": "Example 1.44"}
LINE = "<!-- book-summarizer DONE unit: id=0063 type=item key=1.44 name=Example 1.44 -->"


def _unit(tmp_path, line, eol="\n"):
    p = os.path.join(str(tmp_path), "u.md")
    with open(p, "wb") as f:
        f.write((line + eol + "**正文**：x\n").encode("utf-8"))
    return p


def test_exact_match_passes(tmp_path):
    assert marker_manifest_mismatch(_unit(tmp_path, LINE), REC, "译") is None


def test_crlf_file_not_falsely_flagged(tmp_path):
    r"""单元文件是 CRLF：行尾 CR 不得参与比较（否则全书误报「脱账」）。"""
    p = _unit(tmp_path, LINE, eol="\r\n")
    assert p.endswith("u.md") and b"\r\n" in open(p, "rb").read()
    assert marker_manifest_mismatch(p, REC, "译") is None


def test_tampered_name_flagged_with_field(tmp_path):
    bad = LINE.replace("name=Example 1.44", "name=Example 1.44 (a longer printed title)")
    msg = marker_manifest_mismatch(_unit(tmp_path, bad), REC, "译")
    assert msg and "name" in msg and "脱账" in msg, msg


def test_tampered_type_flagged(tmp_path):
    bad = LINE.replace("type=item", "type=desc")
    msg = marker_manifest_mismatch(_unit(tmp_path, bad), REC, "源")
    assert msg and "type" in msg and "源侧" in msg, msg


def test_truncated_name_flagged(tmp_path):
    r"""本判据要抓的**原始缺陷形态**（Shafarevich BAG1 ch1/0073）：写源期人工把
    `name=` 的印刷标题截断，前缀仍是 manifest 名的前缀，故「非前缀」类判据全盲。"""
    rec = {"id": "0073", "type": "item", "key": "1.1",
           "name": "Comment on the proof that the element Zd+1 is separable over the"}
    bad = ("<!-- book-summarizer DONE unit: id=0073 type=item key=1.1 "
           "name=Comment on the proof that the element Zd+1 is -->")
    msg = marker_manifest_mismatch(_unit(tmp_path, bad), rec, "源")
    assert msg and "name" in msg and "separable over the" in msg, msg


def test_empty_name_desc_unit_passes(tmp_path):
    rec = {"id": "0002", "type": "desc", "key": "D1", "name": ""}
    line = "<!-- book-summarizer DONE unit: id=0002 type=desc key=D1 name= -->"
    assert marker_manifest_mismatch(_unit(tmp_path, line), rec, "源") is None


def test_unparseable_marker_flagged(tmp_path):
    msg = marker_manifest_mismatch(
        _unit(tmp_path, "<!-- book-summarizer DONE unit id=0063 -->"), REC, "译")
    assert msg and "不可解析" in msg, msg


def test_body_bytes_untouched_by_comparison(tmp_path):
    """判据只看首行：正文里再出现一个同形 marker 也不得影响结论。"""
    p = os.path.join(str(tmp_path), "u.md")
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(LINE + "\n正文一行。\n\n"
                + LINE.replace("id=0063", "id=9999").replace("name=Example 1.44", "name=X")
                + "\n")
    assert marker_manifest_mismatch(p, REC, "译") is None
