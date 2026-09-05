"""merge_units.py — write-source 步骤 6 收尾：把全部单元拼接成最终章 md

背景（2026-08-31 用户需求重构）
------------------------------
拆分脚本 ``split_draft_units.py`` 把整章草稿切成按写作顺序的单元文件
（``units/ch{N}/NNNN_<type>.md``，4 位编号；附录章目录 ``units/appendix{X}/``）；agent 经 ``gate_units.py`` 强制门控逐个改好后，
本脚本把这些单元**按 manifest 顺序拼接**成最终的源语言章 md
（``ChapterN_*.md`` / ``第N章_*.md``），并按 ``docs/writing-rules.md`` V-F 的
「条目级 ``---`` 分隔线」规则在单元之间重建分隔线。

🔴 **强制门控到脚本层（2026-09-01 强化）**：拼接前**默认先跑 ``gate_units`` 门控**——
任一单元未改好（首行非 DONE / 质量校验未过 / 缺失）即**直接报错拒绝拼接**，防止
agent 绕过门控直接 merge。仅调试可传 ``require_gate=False``（本脚本不暴露该开关，
供测试 / 库调用方显式使用）。

翻译版拼接（2026-09-03 起，翻译并入本流程）
-------------------------------------------------------------
同一脚本拼接翻译单元目录，只加 ``--units-dir units-translate``：
    python flows/write-source/script/merge_units.py <extract_dir> <ch> --units-dir units-translate
  * 输出文件名由翻译 manifest 的 ``language`` 决定（cn → ``第N章_*.md``）；
  * **优先**使用翻译 manifest 的 ``final_md`` 字段（agent 可在其中写定中文标题文件名，
    如 ``第9章_非线性动力系统的Koopman模型预测控制.md``），其次 ``-o``，最后按契约章名
    自动生成（契约章名是源语言，自动生成的中文文件名会是英文标题，故推荐填 ``final_md``）；
  * 🔴 翻译版**不清 CJK**（按 manifest language 自动判定，仅 ``en`` 才清）——原来的
    ``--no-clean-cjk`` 行为对翻译目录自动生效。

分隔线状态机（与 render_draft 的 ``_CTX`` 等价，逐字对齐 V-F）：
  * ``section`` 标题之前（非首单元）**总是**加 ``---``（等价原「每节末 ``---``」）；
  * ``item`` 之前：prev=``desc``/``item`` 时加 ``---``；prev=``heading``/``None`` 不加；
  * ``desc`` 之前：prev=``item`` 时加 ``---``（条目尾随散文）；prev=``desc``/``heading`` 不加；
  * ``chapter`` 章标题在最前，无前置分隔；
  * 拼接后再用 render_draft 的 ``_tidy_separators`` 合并堆叠 ``---``、保证上下空行。

用法
----
    python flows/write-source/script/merge_units.py <extract_dir> <ch> [-o <out_md>]
           [--units-dir <sub>] [--no-clean-cjk]
    # <sub>：units（源语言，默认）| units-translate（翻译版）
    # 输出文件名优先级：manifest.final_md > -o > 按 language + 契约章名自动生成
输出
----
    <book_dir>/ChapterN_<name>.md   （英文书源版）
    <book_dir>/第N章_<name>.md       （中文书源版 / 英文书翻译版）
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
from data.book_structure.book_structure import chapter_json_path, chapter_label, unit_dir_name
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


def merge_chapter(ext, ch_key, out_md=None, clean_cjk=None, require_gate=True,
                  units_sub="units"):
    """拼接单章；返回最终 md 路径。

    ``units_sub``：``units``（源语言，默认）| ``units-translate``（翻译版，
    2026-09-03 起翻译并入本流程，与源版共用同一拼接器）。
    ``clean_cjk``：``None`` = **按 manifest language 自动判定**（仅 ``en`` 清 CJK，
    故翻译版 cn 自动不清）；True / False 显式覆盖（兼容旧行为）。

    🔴 **强制门控（死规则）**：默认 ``require_gate=True``——拼接前先跑
    ``gate_units.gate_chapter``，任一单元未改好（首行非 DONE / 质量校验未过 /
    缺失）即**直接抛错拒绝拼接**，防止 agent 绕过门控直接 merge。仅调试场景
    可传 ``require_gate=False`` 跳过。
    """
    out_dir = os.path.join(ext, _ac.OUT_DIR_NAME, units_sub, unit_dir_name(ch_key))
    mpath = os.path.join(out_dir, "manifest.json")
    if not os.path.exists(mpath):
        raise SystemExit("[merge_units] %s 缺 %s/manifest.json（先 "
                         "split_draft_units / init_translate_units 初始化清单）。" % (chapter_label(ch_key), units_sub))
    if require_gate:
        ok_g, gdet = _gate.gate_chapter(ext, ch_key, units_sub=units_sub)
        if not ok_g:
            raise SystemExit(
                "[merge_units] 🔴 强制门控未通过（%s / %s），拒绝拼接：\n%s\n"
                "须先把全部单元按 writing-rules 改好 / 译好（首行 DONE + 质量校验通过）、"
                "重跑 gate_units 通过后再 merge。" % (chapter_label(ch_key), units_sub, gdet))
    with open(mpath, encoding="utf-8") as f:
        manifest = json.load(f)
    language = manifest.get("language") or "cn"
    book_dir = os.path.dirname(os.path.abspath(ext.rstrip("/\\")))
    # 输出文件名优先级：manifest.final_md > -o > 按 language + 契约章名自动生成
    if not out_md:
        want = (manifest.get("final_md") or "").strip()
        if want:
            out_md = want if os.path.isabs(want) else os.path.join(book_dir, want)
    if not out_md:
        try:
            with open(chapter_json_path(ext, ch_key), encoding="utf-8") as f:
                chapter_name = (json.load(f).get("name") or "")
        except Exception:
            chapter_name = ""
        out_md = os.path.join(book_dir, _final_md_name(ch_key, language, chapter_name))

    lines = []
    prev = None          # heading / desc / item
    for u in manifest.get("units") or []:
        up = os.path.join(out_dir, u["file"])
        if not os.path.exists(up):
            raise SystemExit("[merge_units] %s 缺单元文件 %s（须先 gate_units 门控）。"
                             % (chapter_label(ch_key), u["file"]))
        utype = u["type"]
        body = _read_body(up)
        # 分隔线状态机（V-F：条目级 ---，标题下第一元素不加）
        if utype == "section":
            # 非首单元的节标题之前总是 ---（等价原「每节末 ---」）
            if lines:
                lines.append("---")
                lines.append("")
        elif utype in ("item", "exercise"):
            if prev in ("desc", "item", "exercise"):
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
                "item": "item", "desc": "desc", "exercise": "item"}.get(utype, prev)

    # 整理分隔线 + 空行（复用 render_draft）
    lines = _rd._tidy_separators(lines)
    if clean_cjk is None:
        clean_cjk = (language == "en")     # 翻译版（cn）自动不清 CJK
    if clean_cjk:
        lines = [re.sub(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]+", "", ln) for ln in lines]
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip() + "\n")
    print("[merge_units] %s (%s) -> %s" % (chapter_label(ch_key), units_sub, out_md))
    return out_md


def main():
    argv = list(sys.argv[1:])
    units_sub = "units"
    if "--units-dir" in argv:
        i = argv.index("--units-dir")
        if i + 1 >= len(argv):
            print("[merge_units] --units-dir 缺参数（units | units-translate）。")
            return 2
        units_sub = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    clean_cjk = None if "--no-clean-cjk" not in argv else False
    argv = [a for a in argv if a != "--no-clean-cjk"]
    merge_all = "--all" in argv
    argv = [a for a in argv if a != "--all"]
    if len(argv) < 2 and not merge_all:
        print(__doc__)
        return 2
    ext = argv[0]
    if merge_all:
        # 🔴 全章批量拼接（flow_runner merge_all 步模板）：源版 + 翻译版各跑一遍。
        # 翻译版（units-translate）对缺 manifest 的章自动跳过（中文源书 / 未派生章）。
        from data.book_structure.book_structure import list_chapter_keys
        fails, done, skipped = [], 0, 0
        for k in list_chapter_keys(ext):
            if units_sub != "units" and not os.path.exists(os.path.join(
                    ext, _ac.OUT_DIR_NAME, units_sub, unit_dir_name(k), "manifest.json")):
                skipped += 1
                continue
            try:
                merge_chapter(ext, k, out_md=None, clean_cjk=clean_cjk, units_sub=units_sub)
                done += 1
            except SystemExit as e:
                print("[merge_units] %s 拼接失败: %s" % (chapter_label(k), e))
                fails.append(k)
        if fails:
            print("[merge_units] 🔴 %d 章拼接失败: %s（须修复单元后重跑）" % (len(fails), fails))
            return 1
        print("[merge_units] --all 完成: %d 章拼接, %d 章跳过（无翻译单元）" % (done, skipped))
        return 0
    ch = argv[1]
    out_md = None
    if len(argv) > 2 and argv[2] == "-o":
        out_md = argv[3] if len(argv) > 3 else None
    merge_chapter(ext, ch, out_md=out_md, clean_cjk=clean_cjk, units_sub=units_sub)
    return 0


if __name__ == "__main__":
    sys.exit(main())
