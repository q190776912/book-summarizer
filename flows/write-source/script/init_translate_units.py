"""init_translate_units.py — write-source 翻译步：初始化 units-translate 清单（不复制正文）

背景（2026-09-03 翻译单元化：翻译单元按需生成，不做全量预派生）
---------------------------------------------------------------
翻译是 write-source 内的**单步**（步骤 6）：agent **看一个源单元就产出对应翻译
单元**，不做全量预复制。本脚本是翻译步内的**清单初始化器**：在
``units-translate/ch{N}/`` 生成 ``manifest.json``（章元数据 + 每单元的
id/file/type/key/name + ``src_hash`` 快照），**不复制任何正文文件**。翻译 agent
随后逐个打开源单元 ``units/ch{N}/NNNN_*.md``，把译文写到
``units-translate/ch{N}/NNNN_*.md``（文件不存在则新建；已存在则整体改写），写完置
DONE。完整性由门控机械核对——翻译单元缺文件 / 仍 DRAFT / 质量不达标，或「译文与
源文完全相同（未翻译）」，都会被 ``gate_units --units-dir units-translate`` 与
``check_translate_parity.py`` 拦下。

* ``--scaffold``（可选）：对缺失的单元文件复制源单元正文作脚手架（首行 DRAFT），
  供 agent 直接在其上改写译文（省去自造文件头；历史遗留的已复制文件亦等效于此，
  可直接改写）。默认不建脚手架 = 纯「看一个生成一个」。

🔴 **翻译硬闸**：初始化前跑源章 ``gate_units``——源单元未全部 DONE + 质量校验通过
即拒绝（防止「翻译一个还没写对的源」）。``src_hash`` = 初始化那一刻源正文哈希，
之后源单元若再被修改，``check_translate_parity`` 据此检出「译源不同步」。

适用范围
--------
只服务**源语言为外语（英文书）**的书：en → cn。中文书（源语言即中文）无翻译阶段，
整体跳过。

用法
----
    python flows/write-source/script/init_translate_units.py <extract_dir> [ch ...] [--force] [--scaffold]
    # 不传 <ch> 即全部章；--force 重建 manifest；--scaffold 顺带补齐缺失单元的源文骨架
输出
----
    <extract_dir>/book_structure/units-translate/ch{N}/manifest.json
"""
import hashlib
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
from data.book_structure.book_structure import list_chapter_keys
import split_draft_units as _split
import gate_units as _gate

# 与源单元目录同级别（book_structure/units-translate），结构一致
OUT_SUB = os.path.join(_ac.OUT_DIR_NAME, "units-translate")
UNITS_DIR = "ch%s"

# 源 → 目标语言映射（仅外语书派生翻译）
_TARGET = {"en": "cn"}


def _hash_text(text):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _target_language(src_lang):
    """源语言 → 目标语言；中文书返回 None（无翻译阶段）。"""
    return _TARGET.get((src_lang or "").lower())


def init_chapter(ext, ch_key, force=False, scaffold=False):
    """初始化单章翻译清单：生成 units-translate/ch{N}/manifest.json（元数据 +
    src_hash 快照）；不复制正文，除非 scaffold=True（补齐缺失单元为源文骨架 DRAFT）。
    返回 manifest 路径；中文书/无需翻译返回 None。
    """
    src_dir = os.path.join(ext, _ac.OUT_DIR_NAME, "units", _split.UNITS_DIR % ch_key)
    mpath = os.path.join(src_dir, "manifest.json")
    if not os.path.exists(mpath):
        raise SystemExit("[init_translate_units] ch%s 缺 units/manifest.json（先跑 "
                         "split_draft_units + agent 改好单元）。" % ch_key)
    with open(mpath, encoding="utf-8") as f:
        src_manifest = json.load(f)
    src_lang = src_manifest.get("language") or "cn"
    tgt_lang = _target_language(src_lang)
    if tgt_lang is None:
        print("[init_translate_units] ch%s 源语言=%s（中文书无翻译阶段），跳过。"
              % (ch_key, src_lang))
        return None

    # 🔴 翻译硬闸：源单元必须全部 DONE + 单元级质量校验通过
    ok_g, gdet = _gate.gate_chapter(ext, ch_key)
    if not ok_g:
        raise SystemExit("[init_translate_units] 🔴 ch%s 源单元未过门控，拒绝初始化翻译清单：\n"
                         "%s\n须先把源单元按 writing-rules 改好（DONE + 质量校验通过）。"
                         % (ch_key, gdet))

    out_dir = os.path.join(ext, OUT_SUB, UNITS_DIR % ch_key)
    os.makedirs(out_dir, exist_ok=True)

    manifest = {
        "chapter_key": str(ch_key),
        "language": tgt_lang,
        "source_language": src_lang,
        "source_units_dir": os.path.join(_ac.OUT_DIR_NAME, "units",
                                         _split.UNITS_DIR % ch_key).replace("\\", "/"),
        "final_md": "",
        "units": [],
    }
    n_scaffold = 0
    for u in src_manifest.get("units") or []:
        up = os.path.join(src_dir, u["file"])
        mark, uid, utype, key, body, _bh = _gate._read_unit(up)
        # 🔴 src_hash = 初始化「那一刻」的源正文哈希（源单元已在步骤 5 定稿；
        # 之后源单元若再被修改，check_translate_parity 据此检出「译源不同步」）。
        cur = _hash_text(body.rstrip("\n"))
        manifest["units"].append({
            "id": u.get("id") or "",
            "file": u["file"],
            "type": u.get("type") or "",
            "key": u.get("key") or "",
            "name": u.get("name") or "",
            "hash": cur,
            "src_hash": cur,
        })
        if scaffold:
            tf = os.path.join(out_dir, u["file"])
            if not os.path.exists(tf):
                text = _split.DRAFT_MARK.format(
                    id=u.get("id") or "", type=u.get("type") or "",
                    key=u.get("key") or "", name=u.get("name") or "") + "\n"
                if body.strip():
                    text += body.rstrip() + "\n"
                with open(tf, "w", encoding="utf-8") as f:
                    f.write(text)
                n_scaffold += 1
    mpath_out = os.path.join(out_dir, "manifest.json")
    with open(mpath_out, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print("[init_translate_units] ch%s manifest 已初始化（%d 单元，%s→%s）%s"
          % (ch_key, len(manifest["units"]), src_lang, tgt_lang,
             "；补齐 %d 个源文骨架" % n_scaffold if n_scaffold else ""))
    return mpath_out


def main():
    argv = [a for a in sys.argv[1:]
            if a not in ("--force", "--scaffold")]
    force = "--force" in sys.argv[1:]
    scaffold = "--scaffold" in sys.argv[1:]
    if not argv:
        print(__doc__)
        return 2
    ext = argv[0]
    try:
        chapters = [int(x) for x in argv[1:]]
    except ValueError:
        chapters = argv[1:]
    keys = [k for k in list_chapter_keys(ext)
            if not chapters or k in {str(c) for c in chapters}]
    if not keys:
        print("[init_translate_units] 无章节可初始化。")
        return 2
    made = 0
    for k in keys:
        if init_chapter(ext, k, force=force, scaffold=scaffold):
            made += 1
    print("[init_translate_units] 完成：%d/%d 章清单已初始化。" % (made, len(keys)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
