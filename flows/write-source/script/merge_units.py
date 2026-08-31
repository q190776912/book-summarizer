"""merge_units.py — write-source 步骤 6 收尾：把全部单元拼接成最终章 md

背景（2026-08-31 用户需求重构）
------------------------------
拆分脚本 ``split_draft_units.py`` 把整章草稿切成按写作顺序的单元文件
（``units/ch{N}/NNNN_<type>.md``，4 位编号）；agent 经 ``gate_units.py`` 强制门控逐个改好后，
本脚本把这些单元**按 manifest 顺序拼接**成最终的源语言章 md
（``ChapterN_*.md`` / ``第N章_*.md``），并按 ``docs/writing-rules.md`` V-F 的
「条目级 ``---`` 分隔线」规则在单元之间重建分隔线。

🔴 **强制门控到脚本层（2026-09-01 强化）**：拼接前**默认先跑 ``gate_units`` 门控**——
任一单元未改好（首行非 DONE / 内容未改写 / 缺失）即**直接报错拒绝拼接**，防止
agent 绕过门控直接 merge。仅调试可传 ``require_gate=False``（本脚本不暴露该开关，
供测试 / 库调用方显式使用）。

分隔线状态机（与 render_draft 的 ``_CTX`` 等价，逐字对齐 V-F）：
  * ``section`` 标题之前（非首单元）**总是**加 ``---``（等价原「每节末 ``---``」）；
  * ``item`` 之前：prev=``desc``/``item`` 时加 ``---``；prev=``heading``/``None`` 不加；
  * ``desc`` 之前：prev=``item`` 时加 ``---``（条目尾随散文）；prev=``desc``/``heading`` 不加；
  * ``chapter`` 章标题在最前，无前置分隔；
  * 拼接后再用 render_draft 的 ``_tidy_separators`` 合并堆叠 ``---``、保证上下空行。

用法
----
    python flows/write-source/script/merge_units.py <extract_dir> <ch> [-o <out_md>] [--no-clean-cjk]
    # 缺省输出文件名按 language + 契约章名自动生成（数字章 / 附录章）
输出
----
    <book_dir>/ChapterN_<name>.md   （英文书源版）
    <book_dir>/第N章_<name>.md       （中文书源版）
"""
import json
import os
import re
import sys
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

sys.stdout.reconfigure(encoding="utf-8")

import attach_content as _ac
from data.book_structure.book_structure import chapter_json_path
import render_draft as _rd
import split_draft_units as _split
import gate_units as _gate

_DONE_RE = re.compile(r"<!-- book-summarizer (?:DRAFT|DONE) unit: id=\S+ type=\S+ key=(.*?) name=(.*?) -->")
_CH_NAME = re.compile(r"^([0-9A-Za-z]+)\s+(.+)$", re.DOTALL)


def _read_body(path):
    """读单元文件正文：去掉首行标记注释，返回正文行列表。"""
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
    except Exception:
        return []
    m = _DONE_RE.match(raw)
    body = raw[m.end():] if m else raw
    return body.lstrip("\r\n").rstrip("\n").split("\n")


def _final_md_name(ch_key, language, chapter_name):
    """由章号 + 语种 + 契约章名生成最终文件名（数字章 / 附录章）。"""
    rest = ""
    m = _CH_NAME.match(chapter_name or "")
    num = str(ch_key)
    if m:
        num = m.group(1)
        rest = m.group(2).strip()
    rest = re.sub(r'[\\/:*?"<>|\r\n\s]+', "_", rest).strip(" _")
    if num[:1].isdigit():
        return ("Chapter%s_%s.md" % (num, rest)) if language == "en" \
            else ("第%s章_%s.md" % (num, rest))
    return ("Appendix%s_%s.md" % (num, rest)) if language == "en" \
        else ("附录%s_%s.md" % (num, rest))


def merge_chapter(ext, ch_key, out_md=None, clean_cjk=True, require_gate=True):
    """拼接单章；返回最终 md 路径。

    🔴 **强制门控（死规则）**：默认 ``require_gate=True``——拼接前先跑
    ``gate_units.gate_chapter``，任一单元未改好（首行非 DONE / 内容未改写 /
    缺失）即**直接抛错拒绝拼接**，防止 agent 绕过门控直接 merge。仅调试场景
    可传 ``require_gate=False`` 跳过。
    """
    out_dir = os.path.join(ext, _ac.OUT_DIR_NAME, "units", _split.UNITS_DIR % ch_key)
    mpath = os.path.join(out_dir, "manifest.json")
    if not os.path.exists(mpath):
        raise SystemExit("[merge_units] ch%s 缺 units/manifest.json（先 split_draft_units）。" % ch_key)
    if require_gate:
        ok_g, gdet = _gate.gate_chapter(ext, ch_key)
        if not ok_g:
            raise SystemExit(
                "[merge_units] 🔴 强制门控未通过（ch%s），拒绝拼接：\n%s\n"
                "须先把全部单元按 writing-rules 改好（首行 DONE + 内容改写）、"
                "重跑 gate_units 通过后再 merge。" % (ch_key, gdet))
    with open(mpath, encoding="utf-8") as f:
        manifest = json.load(f)
    language = manifest.get("language") or "cn"
    # 最终文件名：默认由契约章名生成，可用 -o 覆盖
    if not out_md:
        try:
            with open(chapter_json_path(ext, ch_key), encoding="utf-8") as f:
                chapter_name = (json.load(f).get("name") or "")
        except Exception:
            chapter_name = ""
        book_dir = os.path.dirname(os.path.abspath(ext.rstrip("/\\")))
        out_md = os.path.join(book_dir, _final_md_name(ch_key, language, chapter_name))

    lines = []
    prev = None          # heading / desc / item
    for u in manifest.get("units") or []:
        up = os.path.join(out_dir, u["file"])
        if not os.path.exists(up):
            raise SystemExit("[merge_units] ch%s 缺单元文件 %s（须先 gate_units 门控）。"
                             % (ch_key, u["file"]))
        utype = u["type"]
        body = _read_body(up)
        # 分隔线状态机（V-F：条目级 ---，标题下第一元素不加）
        if utype == "section":
            # 非首单元的节标题之前总是 ---（等价原「每节末 ---」）
            if lines:
                lines.append("---")
                lines.append("")
        elif utype == "item":
            if prev in ("desc", "item"):
                lines.append("---")
                lines.append("")
        elif utype == "desc":
            if prev == "item":            # 条目尾随散文
                lines.append("---")
                lines.append("")
        # chapter 标题/其他：无前置分隔
        if body:
            lines.extend(body)
            lines.append("")
        prev = {"section": "heading", "chapter": "heading",
                "item": "item", "desc": "desc"}.get(utype, prev)

    # 整理分隔线 + 空行（复用 render_draft）
    lines = _rd._tidy_separators(lines)
    if language == "en" and clean_cjk:
        lines = [re.sub(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]+", "", ln) for ln in lines]
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip() + "\n")
    print("[merge_units] ch%s -> %s" % (ch_key, out_md))
    return out_md


def main():
    argv = [a for a in sys.argv[1:] if a != "--no-clean-cjk"]
    clean_cjk = "--no-clean-cjk" not in sys.argv[1:]
    if len(argv) < 2:
        print(__doc__)
        return 2
    ext = argv[0]
    ch = argv[1]
    out_md = None
    if len(argv) > 2 and argv[2] == "-o":
        out_md = argv[3] if len(argv) > 3 else None
    merge_chapter(ext, ch, out_md=out_md, clean_cjk=clean_cjk)
    return 0


if __name__ == "__main__":
    sys.exit(main())
