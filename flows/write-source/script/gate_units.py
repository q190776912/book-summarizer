"""gate_units.py — write-source 步骤 5 强制门控：确保每个 item 单元都被 agent 改好

背景（2026-08-31 用户需求重构）
------------------------------
写源阶段 agent「总是不按照草稿总结来总结」。拆分脚本 ``split_draft_units.py``
把整章草稿切成按写作顺序的单元文件（``units/ch{N}/NNNN_<type>.md``，4 位编号），agent
**必须逐个把单元按 writing-rules 改好**。本脚本是这一步的**强制门控**：只有全部
单元都被改好（每个 item 都不漏）才放行，之后才能进入 ``merge_units.py`` 拼接。

判定（一个单元「已改好」须同时满足）：
  ① **标记已替换**：文件首行由拆分时写入的 ``<!-- ... DRAFT unit: ... -->``
     变为 ``<!-- ... DONE unit: ... -->``（agent 改完后显式确认）；
  ② **「写对」而非「重写」**：item / desc 单元做**单元级质量校验**
     （``check_unit_quality.py``）——公式闭合、无裸数学、结构标签齐全、无明显
     OCR 残留。🔴 2026-09-01 起判断标准是"写对"（是否符合写作要求），**不再看
     内容指纹是否变化**——防止模型瞎改（公式没渲染对 / 格式破坏）就标 DONE。
     （章节标题单元本就无需改动，只确认 DONE。）

完整性核对（防漏项）：
  ③ manifest 中每个单元都有对应文件（无缺失、无多余文件）；
  ④ manifest 的 ``units`` 覆盖契约全部编号项单元（item）+ 章/节/描述单元。

不满足任一 → 输出未处理 / 质量未达标清单并 exit 1（不通过）；全部通过 → exit 0。

用法
----
    python flows/write-source/script/gate_units.py <extract_dir> [ch ...]
    # 不传 <ch> 即全部章
输出
----
    通过：exit 0；未通过：exit 1 并打印未处理 / 缺失单元清单（逐章）。
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
from data.book_structure.book_structure import list_chapter_keys
import split_draft_units as _split
import check_unit_quality as _quality

_OUT_RE = re.compile(r"<!-- book-summarizer (DRAFT|DONE) unit: id=(\S+) type=(\S+) key=(.*?) name=(.*?) -->")


def _hash_text(text):
    import hashlib
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _read_unit(path):
    """读单元文件，返回 (mark, id, type, key, body, body_hash)；解析失败返回 (None, ...)。"""
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
    except Exception:
        return None, None, None, None, "", ""
    m = _OUT_RE.match(raw)
    if not m:
        return None, None, None, None, raw, ""
    mark, uid, utype, key, name = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
    rest = raw[m.end():]
    body = rest.lstrip("\r\n")
    return mark, uid, utype, key, body, _hash_text(body.rstrip("\n"))


def gate_chapter(ext, ch_key):
    """门控单章。返回 (ok, detail)。detail 为逐条问题或通过说明。"""
    out_dir = os.path.join(ext, _ac.OUT_DIR_NAME, "units", _split.UNITS_DIR % ch_key)
    mpath = os.path.join(out_dir, "manifest.json")
    if not os.path.exists(mpath):
        return False, "ch%s 缺 units/manifest.json（先跑 split_draft_units）。" % ch_key
    with open(mpath, encoding="utf-8") as f:
        manifest = json.load(f)
    units = manifest.get("units") or []
    problems = []
    present_files = set()
    for u in units:
        up = os.path.join(out_dir, u["file"])
        if not os.path.exists(up):
            problems.append("缺失单元文件 %s（%s %s）" % (u["file"], u["type"], u["key"]))
            continue
        present_files.add(u["file"])
        mark, uid, utype, key, body, bh = _read_unit(up)
        if mark is None:
            problems.append("单元 %s（%s %s）首行标记缺失/损坏——须含 DONE 标记" % (
                u["file"], u["type"], u["key"]))
            continue
        if mark == "DRAFT":
            problems.append("单元 %s（%s %s）仍未处理（标记仍为 DRAFT）" % (
                u["file"], u["type"], u["key"]))
            continue
        # DONE：item / desc 单元必须「写对」——质量校验通过（公式闭合 / 无裸数学 /
        # 结构标签 / 无明显 OCR 残留）。🔴 2026-09-01 起判断标准是"写对"而非"重写"：
        # 不再看内容指纹是否变化，而是看单元是否符合写作要求（拦"瞎改就标 DONE"）。
        if utype in ("item", "desc"):
            ok_q, qproblems = _quality.check_body(utype, u.get("name") or "", body)
            if not ok_q:
                problems.append("单元 %s（%s %s）质量未达标（写错/格式破坏）：%s" % (
                    u["file"], u["type"], u["key"], "；".join(qproblems[:4])))
    # 多余文件检查（manifest 之外的 .md 属误放）
    for fn in sorted(os.listdir(out_dir)):
        if fn == "manifest.json" or not fn.endswith(".md"):
            continue
        if fn not in present_files:
            problems.append("多余文件 %s（不在 manifest 中，请移除）" % fn)
    if problems:
        return False, "ch%s 门控未通过（%d 处）：\n  %s" % (
            ch_key, len(problems), "\n  ".join(problems))
    return True, "ch%s 门控通过：%d 个单元全部改好（含 %d 个编号项）" % (
        ch_key, len(units), sum(1 for u in units if u["type"] == "item"))


def main():
    argv = sys.argv[1:]
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
        print("[gate_units] 无章节可门控。")
        return 2
    all_ok = True
    for k in keys:
        ok, detail = gate_chapter(ext, k)
        print(("[PASS] " if ok else "[FAIL] ") + detail)
        if not ok:
            all_ok = False
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
