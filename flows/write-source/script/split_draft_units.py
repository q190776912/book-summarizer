"""split_draft_units.py — write-source 步骤 4：把草稿拆分为「每 item 一单元」的目录

背景（2026-08-31 用户需求重构）
------------------------------
写源阶段 agent「总是不按照草稿总结来总结」。为根治，把整章草稿 ``draft_ch{N}.md``
**细分为按写作顺序排列的单元文件目录** ``units/ch{N}/``：每个单元是一个独立 md
文件（章标题 / 节标题 / 描述散文 / 单个编号项 各一单元），agent **必须逐个改好**
（强制门控，见 ``gate_units.py``），最后用 ``merge_units.py`` 拼接成最终章 md。

本脚本取代原 ``render_draft.py`` 的输出（整章 ``draft_ch{N}.md``）。单元粒度与
``docs/writing-rules.md`` 的「item」一致：

  * ``chapter`` 单元：``# 章标题``（章首序言是其后独立的 ``desc`` 单元）；
  * ``section`` 单元：``## §...`` 标题行（其下描述/编号项各为独立单元）；
  * ``desc`` 单元：描述散文（章首序言 / 节导语 / 条目尾随段，无标题纯段落）；
  * ``item`` 单元：单个编号项（定义/定理/例等，含其内部 proof 子节点）。

单元按文档顺序编号（``0001``、``0002`` …，4 位零填充防超千单元），文件名
``NNNN_<type>.md``，文件首行为 HTML 标记（``<!-- book-summarizer DRAFT
unit: ... -->``）。门控依据此标记判断「该单元是否已被 agent 改好」；拼接依据
manifest 的单元序列 + 单元类型重建 ``---`` 分隔线。

数据源与门控
------------
与 ``render_draft`` 同一硬闸：缺 ``_extraction_done.json``（MM Repair 未完成）
拒绝拆分。读取 ``<extract_dir>/book_structure/ch{N}.json``（内容化分章契约，
由 build_structure + attach_content 产出），渲染逻辑复用 ``render_draft`` 的纯
渲染函数（``_chapter_heading`` / ``_item_header_name`` / ``_render_item`` /
``_walk_mixed``），但**单元内部不做跨单元 ``---`` 决策**——分隔线全部由
``merge_units.py`` 按 V-F 规则统一重建（见 ``docs/writing-rules.md`` V-F）。

用法
----
    python flows/write-source/script/split_draft_units.py <extract_dir> [ch ...] [--force]
    # 不传 <ch> 即全部章；--force 覆盖已存在的 units 目录（否则已存在则跳过）
输出
----
    <extract_dir>/book_structure/units/ch{N}/manifest.json
    <extract_dir>/book_structure/units/ch{N}/NNNN_<type>.md  （每单元一个）
"""
import hashlib
import json
import os
import re
import shutil
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
from data.book_structure.book_structure import (chapter_json_path, list_chapter_keys)
import render_draft as _rd

OUT_SUB = os.path.join(_ac.OUT_DIR_NAME, "units")     # book_structure/units
UNITS_DIR = "ch%s"                                    # units/ch{N}


def _is_block(el):
    return _ac._is_block(el)


# ---------------------------------------------------------------------------
# 单元文件命名与标记
# ---------------------------------------------------------------------------
# 拆分时写入的 DRAFT 标记（门控据此判断"未处理"；agent 改好后须改为 DONE）
DRAFT_MARK = "<!-- book-summarizer DRAFT unit: id={id} type={type} key={key} name={name} -->"
DONE_MARK = "<!-- book-summarizer DONE unit: id={id} type={type} key={key} name={name} -->"

_DRAFT_RE = re.compile(r"<!-- book-summarizer DRAFT unit: id=(\S+) type=(\S+) key=(.*?) name=(.*?) -->")
_DONE_RE = re.compile(r"<!-- book-summarizer DONE unit: id=(\S+) type=(\S+) key=(.*?) name=(.*?) -->")


def _sanitize(name):
    """文件名安全化：去路径分隔符与控制字符（保留中文/字母数字/下划线）。"""
    return re.sub(r'[^\w\u4e00-\u9fff-]+', '_', str(name or "")).strip("_")


def _unit_filename(idx, utype, key, name):
    """``NNNN_<type>.md``（4 位零填充，防超千单元；item 追加 key 便于辨识）。"""
    base = "%04d_%s" % (idx, utype)
    if utype == "item" and key:
        base += "_" + _sanitize(key)
    return base + ".md"


def _hash_text(text):
    """单元正文指纹（不含首行标记），供门控对比"是否被改过"。"""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 单元渲染（复用 render_draft 纯函数；不做跨单元 --- 决策）
# ---------------------------------------------------------------------------
def _render_chapter(node, lang):
    return [_rd._chapter_heading(node, lang), ""]


def _render_section(node, lang):
    """仅标题行：无序号标小节 ``## § name``，有号 ``## §name``（name 自带序标）。"""
    key = str(node.get("key") or "")
    name = (node.get("name") or "").strip()
    if re.fullmatch(r"U\d+", key):
        return ["## § " + name, ""]
    return ["## §" + name, ""]


def _render_desc(node, lang):
    out = []
    _rd._walk_mixed(node, out, False, lang, top=False)
    return out


def _render_item(node, lang):
    out = []
    _rd._render_item(node, out, lang)
    return out


# ---------------------------------------------------------------------------
# 深度优先遍历，产出 (type, key, name, lines) 单元流
# ---------------------------------------------------------------------------
def _emit_units(node, lang):
    units = []

    def emit(utype, key, name, lines):
        units.append({"type": utype, "key": key or "", "name": name or "",
                      "lines": lines})

    def walk_container(container):
        for child in container.get("sub_sec") or []:
            if _is_block(child):
                # 章/节直接裸内容块（attach 一般已聚合为 description，此处兜底）
                emit("desc", "", "", [_to_lines(child)])
                continue
            t = child.get("type")
            if t == "section":
                emit("section", str(child.get("key") or ""),
                     (child.get("name") or "").strip(),
                     _render_section(child, lang))
                walk_container(child)
            elif t == "description":
                emit("desc", str(child.get("key") or ""), "",
                     _render_desc(child, lang))
            elif t == "proof":
                continue            # proof 是 item 内部附属，由 item 单元渲染
            elif t == "exercise":
                if child.get("consolidated"):
                    continue        # 章末集中习题块省略（writing-rules 习题收录规则）
                # 🔴 独立 exercise 单元类型：Weibel 等书「结果项」与「习题项」共用
                # 同节编号空间（如 Definition 1.2.2 与 Exercise 1.2.2 同号），若也发
                # 成 item 单元会与结果项同名文件互覆盖。故习题用专属 exercise 单元
                # 类型（文件名 NNNN_exercise_*.md），不与其他 item 冲突；merge/gate
                # 均识别该类型（习题单元门控只需 DONE 标记，不做 item 级质量校验）。
                emit("exercise", str(child.get("key") or ""),
                     (child.get("name") or "").strip(),
                     _render_item(child, lang))
            else:
                emit("item", str(child.get("key") or ""),
                     (child.get("name") or "").strip(),
                     _render_item(child, lang))

    emit("chapter", str(node.get("key") or ""), (node.get("name") or "").strip(),
         _render_chapter(node, lang))
    walk_container(node)
    return units


def _to_lines(block):
    """单个内容块 → 渲染行（兜底，正常路径经 desc/item 渲染）。"""
    if "text" in block:
        return (block.get("text") or "").strip()
    if "formula" in block:
        return "$$" + (block.get("formula") or "") + "$$"
    return ""


def _body_lines(lines):
    """单元正文：去尾随空行（首行标记 + 正文由写文件时拼接）。"""
    out = list(lines)
    while out and not out[-1].strip():
        out.pop()
    return out


def split_chapter(ext, ch_key, language, force=False):
    """拆分单章：产出 units/ch{N}/ 目录 + manifest.json。返回 manifest 路径。"""
    cpath = chapter_json_path(ext, ch_key)
    if not os.path.exists(cpath):
        raise SystemExit("[split_draft_units] 缺 %s——先跑 build_structure + attach_content。" % cpath)
    with open(cpath, encoding="utf-8") as f:
        node = json.load(f)
    # 复用 render_draft 的图片上下文（figure_index 索引 + 图号标签 + 书根）
    _rd._FIGCTX.clear()
    fp = os.path.join(ext, "figure_index.json")
    try:
        with open(fp, encoding="utf-8") as f:
            idx = json.load(f)
    except Exception:
        idx = []
    _rd._FIGCTX["index_by_basename"] = {
        os.path.basename(e.get("file") or ""): e
        for e in (idx if isinstance(idx, list) else [])}
    _rd._FIGCTX["labels"] = _rd._load_fig_labels(ext)
    _rd._FIGCTX["book_dir"] = os.path.dirname(os.path.abspath(ext.rstrip("/\\")))
    _rd._CTX["prev"] = "heading"

    units = _emit_units(node, language)
    out_dir = os.path.join(ext, OUT_SUB, UNITS_DIR % ch_key)
    if os.path.isdir(out_dir) and any(True for _ in os.scandir(out_dir)) and not force:
        print("[split_draft_units] ch%s 已存在 units 目录，跳过（--force 覆盖）。" % ch_key)
        return os.path.join(out_dir, "manifest.json")
    # 🔴 --force 必须清空旧 units 目录，否则上一 run 残留的孤儿/内容 bleed 文件
    # 会留存在磁盘（manifest 已不含它们，但文件仍在），造成 merge/verify 噪声。
    if force and os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    manifest = {
        "chapter_key": str(ch_key),
        "language": language,
        "final_md": "",                       # 由 merge_units 生成/填充
        "units": [],
    }
    for i, u in enumerate(units, start=1):
        fn = _unit_filename(i, u["type"], u["key"], u["name"])
        body = _body_lines(u["lines"])
        text = DRAFT_MARK.format(id="%04d" % i, type=u["type"], key=u["key"],
                                 name=u["name"]) + "\n" + "\n".join(body).rstrip() + "\n"
        with open(os.path.join(out_dir, fn), "w", encoding="utf-8") as f:
            f.write(text)
        manifest["units"].append({
            "id": "%04d" % i,
            "file": fn,
            "type": u["type"],
            "key": u["key"],
            "name": u["name"],
            "hash": _hash_text("\n".join(body)),
        })
    mpath = os.path.join(out_dir, "manifest.json")
    with open(mpath, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print("[split_draft_units] ch%s -> %d units (%s)" % (ch_key, len(units), out_dir))
    return mpath


def main():
    argv = [a for a in sys.argv[1:] if a != "--force"]
    force = "--force" in sys.argv[1:]
    if not argv:
        print(__doc__)
        return 2
    ext = argv[0]
    if not os.path.exists(os.path.join(ext, "_extraction_done.json")):
        print("[split_draft_units] BLOCKED: 缺 _extraction_done.json（MM Repair 未完成）。")
        return 2
    try:
        chapters = [int(x) for x in argv[1:]]
    except ValueError:
        chapters = argv[1:]
    keys = [k for k in list_chapter_keys(ext)
            if not chapters or k in {str(c) for c in chapters}]
    language = _rd._book_language(ext)
    for k in keys:
        split_chapter(ext, k, language, force=force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
