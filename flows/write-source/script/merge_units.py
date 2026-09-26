"""merge_units.py — write-source 步骤 7 收尾：把全部单元拼接成最终章 md

背景
----
拆分脚本 ``split_draft_units.py`` 把整章草稿切成按写作顺序的单元文件
（``units/ch{N}/NNNN_<type>_<key>.md``，4 位编号；附录章目录 ``units/appendix{X}/``）；agent 经 ``gate_units.py`` 强制门控逐个改好后，
本脚本把这些单元**按 manifest 顺序拼接**成最终的源语言章 md
（``ChapterN_*.md`` / ``第N章_*.md``），并按 ``docs/writing-rules.md`` V-F 的
「条目级 ``---`` 分隔线」规则在单元之间重建分隔线。

🔴 **强制门控到脚本层**：拼接前**默认先跑 ``gate_units`` 门控**——
任一单元未改好（首行非 DONE / 质量校验未过 / 缺失）即**直接报错拒绝拼接**，防止
agent 绕过门控直接 merge。仅调试可传 ``require_gate=False``（本脚本不暴露该开关，
供测试 / 库调用方显式使用）。

翻译版拼接（英文书；同一流程内）
-------------------------------------------------------------
同一脚本拼接翻译单元目录，只加 ``--units-dir units-translate``：
    python flows/write-source/script/merge_units.py <extract_dir> <ch> --units-dir units-translate
  * 输出文件名由翻译 manifest 的 ``language`` 决定（cn → ``第N章_*.md``）；
  * **优先**使用翻译 manifest 的 ``final_md`` 字段（agent 可在其中写定中文标题文件名，
    如 ``第9章_非线性动力系统的Koopman模型预测控制.md``），其次 ``-o``，最后按契约章名
    自动生成（契约章名是源语言，自动生成的中文文件名会是英文标题，故推荐填 ``final_md``）；
  * 🔴 翻译版**不清 CJK**（按 manifest language 自动判定，仅 ``en`` 才清）——
    ``--no-clean-cjk`` 对翻译目录自动生效。

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
from data.book_structure.book_structure import (chapter_json_path, chapter_label,
                                                unit_dir_name, chapter_ordinal)
import render_draft as _rd
import split_draft_units as _split
import gate_units as _gate
from verify.script.struct_labels import insert_item_separators as _insert_item_seps

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


# CJK（含全/半角标点）字符类：文件名语种守卫与正文 clean_cjk 共用同一口径。
_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]")


def _map_name_en(ext, ch_key):
    """chapter_map 里该章的**英文名**（无则空串）。英文版文件名用它，避免中文契约
    标题被拼进 `ChapterN_*.md`（见 _final_md_name）。取不到一律静默回退，不报错。"""
    try:
        from data.chapter_map.chapter_map import load_chapter_records
        for rec in load_chapter_records(ext):
            if str(rec.get("num")) == str(ch_key):
                return str(rec.get("name_en") or "")
    except Exception:
        pass
    return ""


def _final_md_name(ch_key, language, chapter_name, name_en=""):
    """由章号 + 语种 + 契约章名生成最终文件名。

    三类走向（🔴 按 kind 判定，2026-09-08 起 Supplement 不再被称作 Appendix）：
      章 kind=1      Chapter4_*.md        / 第4章_*.md
      附录 kind=2    AppendixA_*.md       / 附录A_*.md
      附录无号 kind=2 Appendix.md          / 附录.md         （无印刷序标 → 裸名）
      补篇 kind=3    SupplementS_*.md     / 补篇S_*.md
    无编号附录（键 "appendix"，序标空）不得伪造序标（2026-09-21 用户裁定）。

    🔴 **源语言为英文的书，其英文版文件名不得带中文**（`name_en` 参数，2026-09-26
    Kreyszig 实测）：契约 `ch{N}.json` 的 `name` 常按中文标题登记（本书 `name` =
    「5 进一步应用：巴拿赫不动点定理」），旧实现不分语种直接拿它拼名，于是英文版
    产出 `Chapter5_进一步应用：巴拿赫不动点定理.md`——**同书其余 82 个英文文件都是
    拆节时按文内英文标题生成的 ASCII 名**，只有未被拆分的章露出中文，形同一本书
    两套语言规则。故 `language == "en"` 时优先用 chapter_map 的 `name_en`，并在
    兜底处剥掉残留 CJK（宁可短名，也不要跨语种文件名）。
    """
    ordinal = ""
    rest = ""
    m = _CH_NAME.match(chapter_name or "")
    if m:
        tok, rest = m.group(1), m.group(2).strip()
        # name 若以占位键开头（无号附录契约名 "appendix …"）→ 序标归空
        ordinal = "" if chapter_ordinal(tok) == "" else tok
    else:
        ordinal = chapter_ordinal(ch_key)     # 无编号附录 → ""
    if language == "en" and (_CJK_RE.search(rest or "")
                             or _CJK_RE.search(chapter_name or "")):
        # 契约名带中文（标题整体或 CJK 前缀形如「附录 A 提示」）→ 英文版改用 chapter_map
        # 的英文名；**契约名本就 ASCII 时一律不动**（旧形态逐字保持，含 "Appendix A
        # Hints" 把字母留在标题里的情况）。无英文名可退时剥掉中文，宁可短名。
        rest = (name_en or "").strip() or _CJK_RE.sub(" ", rest or "").strip()
    rest = re.sub(r'[\\/:*?"<>|\r\n\s]+', "_", rest).strip(" _")
    kind = 2
    try:
        from data.book_structure.book_structure import chapter_kind
        _k = str(ch_key)
        kind = chapter_kind(int(_k) if _k.isdigit() else _k)
    except Exception:
        kind = 1 if str(ch_key)[:1].isdigit() else 2
    if kind == 3:
        head = "Supplement%s" % ordinal if language == "en" else "补篇%s" % ordinal
    elif kind == 1:
        head = "Chapter%s" % ordinal if language == "en" else "第%s章" % ordinal
    else:
        head = "Appendix%s" % ordinal if language == "en" else "附录%s" % ordinal
    return (head + ("_" + rest if rest else "") + ".md")


def _assemble(ext, ch_key, units_sub="units", clean_cjk=None, require_gate=True):
    """拼接单章为 ``(lines, owners)``。

    ``lines`` 为最终章 md 行序列；``owners`` 等长并行，``owners[i]`` = 该行归属的
    单元文件（相对 ``out_dir`` 的文件名），或 ``None``（分割线 / 空行）。

    🔴 与 ``merge_chapter`` 共用同一拼接逻辑（分隔线状态机 + ``_tidy_separators`` +
    ``clean_cjk``），**不**另起炉灶——确保 ``owners`` 与真实合并 md 逐行对齐，
    回填时才能把「合并 md 上的序标缺口」精确映射回源单元。
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

    lines, owners = [], []
    prev = None          # heading / desc / item
    for u in manifest.get("units") or []:
        up = os.path.join(out_dir, u["file"])
        if not os.path.exists(up):
            raise SystemExit("[merge_units] %s 缺单元文件 %s（须先 gate_units 门控）。"
                             % (chapter_label(ch_key), u["file"]))
        utype = u["type"]
        body = _read_body(up)
        rel = u["file"]  # 单元文件名（相对 out_dir）；回填据此定位源单元
        # 分隔线状态机（V-F：条目级 ---，标题下第一元素不加）
        if utype == "section":
            # 非首单元的节标题之前总是 ---（等价原「每节末 ---」）
            if lines:
                lines.append("---"); lines.append(""); owners.append(None); owners.append(None)
        elif utype in ("item", "exercise"):
            if prev in ("desc", "item", "exercise"):
                lines.append("---"); lines.append(""); owners.append(None); owners.append(None)
        elif utype == "desc":
            if prev == "item":            # 条目尾随散文
                lines.append("---"); lines.append(""); owners.append(None); owners.append(None)
        # chapter 标题/其他：无前置分隔
        if body:
            lines.extend(body)
            owners.extend([rel] * len(body))
            lines.append(""); owners.append(None)
        prev = {"section": "heading", "chapter": "heading",
                "item": "item", "desc": "desc", "exercise": "item"}.get(utype, prev)

    # 🔴 条目级 `---` 分隔线补齐（I-LAYER 归一化，与 check_i_separators /
    # fix_i_separators 共用 struct_labels.insert_item_separators 同一检测逻辑）：
    # 单元之间的分隔线状态机不覆盖**单元内部**——当一个契约节点打包了「定义 + 例1 +
    # 例2 …」多个条目时，条目之间缺 `---` 会让 step-8 verify 的 I 层报错。故在拼接
    # 产物上统一补齐。对已满足分隔线的章节是**空操作**（跨书 / 幂等安全）。
    # owners 同步插入 None 以保持逐行对齐（回填据此定位源单元）。
    lines, owners = _insert_item_seps(lines, owners)

    # 整理分隔线 + 空行（复用 render_draft，并同步 owners）
    lines, owners = _rd._tidy_separators(lines, owners)
    if clean_cjk is None:
        clean_cjk = (language == "en")     # 翻译版（cn）自动不清 CJK
    if clean_cjk:
        lines = [re.sub(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]+", "", ln) for ln in lines]
        # owners 不受影响（行数不变，仅内容去 CJK）
    return lines, owners


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
        out_md = os.path.join(book_dir, _final_md_name(ch_key, language, chapter_name,
                                                       _map_name_en(ext, ch_key)))

    lines, _owners = _assemble(ext, ch_key, units_sub, clean_cjk, require_gate)
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip() + "\n")
    print("[merge_units] %s (%s) -> %s" % (chapter_label(ch_key), units_sub, out_md))
    return out_md


def merge_chapter_map(ext, ch_key, units_sub="units", require_gate=False, tmp_dir=None):
    """拼接单章并返回 ``(tmp_md, owners, out_dir)``——供回填定位序标缺口。

    * ``tmp_md``：拼接产物写入 ``ext`` 下的临时文件（``_bf_merged_tmp_<章>.md``），
      **不覆盖**最终章 md；
    * ``owners``：与 ``tmp_md`` 逐行对齐，``owners[i]`` = 该行归属单元文件名
      （相对 ``out_dir``）或 ``None``；
    * ``out_dir``：单元目录绝对路径，用于把 ``owners`` 中的相对文件名解析为真实路径。

    🔴 与 ``merge_chapter`` 共用 ``_assemble``，保证 owners 与真实合并 md 逐行一致。
    回填（backfill_ordinals）据此把「合并 md 上的序标缺口」映射回源单元文件。
    """
    out_dir = os.path.join(ext, _ac.OUT_DIR_NAME, units_sub, unit_dir_name(ch_key))
    tmp = os.path.join(tmp_dir or ext,
                       "_bf_merged_tmp_%s_%d.md" % (unit_dir_name(ch_key), os.getpid()))
    lines, owners = _assemble(ext, ch_key, units_sub, clean_cjk=None, require_gate=require_gate)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip() + "\n")
    return tmp, owners, out_dir


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
    # 🔴 灌注 kind 注册表：文件名/H1 的 Chapter / Appendix / Supplement 三分 relying
    # 于 chapter_map 的显式 kind（而非「章号是否数字」猜测）。未灌注会静默回落旧
    # 形态判据，把 Supplement 写成 Appendix。
    try:
        from data.book_structure.book_structure import prime_chapter_kinds
        prime_chapter_kinds(ext)
    except Exception:
        pass
    if merge_all:
        # 🔴 全章批量拼接（flow_runner 的 merge_source / merge_translation 步模板）：
        # ``--all`` 只拼**所选的这一个** units 组（``--units-dir``，默认 ``units``）；
        # 英文书要出源 + 译两版，必须按账本两步各调一次（merge_source 用默认组，
        # merge_translation 用 ``--units-dir units-translate``，见 RUN_COMMANDS）。
        # 翻译组（units-translate）对缺 manifest 的章自动跳过（中文源书 / 未派生章）。
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
    ch = argv[1].strip()
    m_ch = re.match(r"^(?:ch|appendix)(.+)$", ch, re.I)
    if m_ch:                       # 容错 "ch3" / "appendixA" → "3" / "A"
        ch = m_ch.group(1)
    from data.book_structure.book_structure import norm_chapter_key
    ch = norm_chapter_key(ch)      # "3" → int 3，"A" → "A"（unit_dir_name 契约键型）
    out_md = None
    if len(argv) > 2 and argv[2] == "-o":
        out_md = argv[3] if len(argv) > 3 else None
    merge_chapter(ext, ch, out_md=out_md, clean_cjk=clean_cjk, units_sub=units_sub)
    return 0


if __name__ == "__main__":
    sys.exit(main())
