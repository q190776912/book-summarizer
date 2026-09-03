"""check_translate_parity.py — 翻译单元「1:1 同构」闸门（write-source 步骤 7 门控之一）

背景（2026-09-03 翻译单元化：翻译并入 write-source，单元粒度 1:1）
------------------------------------------------------------------
翻译下沉到单元粒度后，需要一道**机械的同构闸门**来保证「翻译版没漏东西」——
单元级质量校验（``gate_units`` / ``check_unit_quality``）只管「写得对不对」，
管不了「翻得全不全」。本脚本补上后者：逐项比对源单元目录与翻译单元目录。

检查项（任一为 FAIL 即 exit 1）
----------------------------
1. **单元序列一致**：`id` / `type` / `key` / `name` / `file` 逐一对应（缺 / 多 / 错位）。
2. **公式序标一致**：`\\tag{...}` 编号集合逐单元相同（漏公式 / 擅自改号 → FAIL）。
3. **图片一致**：`<img src="...">` 集合逐单元相同（漏图 → FAIL）。
4. **节号一致**：`section` 单元的 `§N.M` 编号集合相同（D 层靠 `§` 认节，错位即 FAIL）。
5. **编号项标签一致**：item 单元的条目编号（`**定理9.2**` / `**Theorem 9.2**` 中的 `9.2`）
   集合相同（漏条目 / 改号 → FAIL）。
6. **源单元漂移**：`manifest.units[].src_hash` ≠ 源单元当前哈希 → 源在派生后被改，
   须先同步翻译单元（单向修复：先修源 → 再同步译），FAIL。
7. **未翻译残留（WARN 升 FAIL）**：item / desc 单元译文哈希 == 源文哈希，即整单元未翻译。

用法
----
    python flows/write-source/script/check_translate_parity.py <extract_dir> [ch ...]
    # 不传 <ch> 即全部章（中文书源整体跳过，无翻译目录）
输出
----
    通过 exit 0；不通过 exit 1 并打印逐章问题清单。
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

SRC_SUB = "units"
TGT_SUB = "units-translate"

_TAG_RE = re.compile(r"\\tag\{([^}]*)\}")
_IMG_RE = re.compile(r'<img[^>]+src="([^"]+)"')
_SEC_RE = re.compile(r"§\s*([0-9]+(?:\.[0-9]+)*)")
# 条目编号：**定理9.2** / **Theorem 9.2** / **定义 9.2（名称）**
# 🔴 必须「先取粗体标签内部、再在内部找编号」——早期写法直接从 `**` 起惰性扫 40 字符，
# 会从闭合粗体的后半段一路扫到正文里的参考文献编号（源文 `**Remark 9.3**: … Sect.
# 9.4.1.1` 因英文冗长侥幸躲过，中文译文变短即命中）→ 假 FAIL。
_BOLD_RE = re.compile(r"\*\*([^*\n]+)\*\*")
_NUM_IN_LABEL_RE = re.compile(r"([0-9]+(?:\.[0-9]+)+)")


def _labels(body):
    """粗体标签内部的条目编号集合（只认标签内，不认正文里的数字编号）。"""
    out = set()
    for m in _BOLD_RE.finditer(body):
        n = _NUM_IN_LABEL_RE.search(m.group(1))
        if n:
            out.add(n.group(1))
    return sorted(out)


def _prose_lines(body):
    """散文行（不在 $$ 块内、非 img/div、非空）——纯公式/纯图单元无散文行。"""
    out = []
    in_math = False
    for ln in body.split("\n"):
        s = ln.strip()
        if s.startswith("$$"):
            in_math = (not in_math) if s == "$$" else in_math
            continue
        if in_math or not s:
            continue
        if "<img" in s or "<div" in s or "</div>" in s or s.startswith("<!--"):
            continue
        out.append(s)
    return out


def _hash_text(text):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _read_body(path):
    """读单元正文（去掉首行标记）——复用 ``gate_units._read_unit``，不重复实现。"""
    _mark, _uid, _utype, _key, body, _h = _gate._read_unit(path)
    return body or ""


def _collect(body, rx):
    return sorted(set(rx.findall(body)))


def check_chapter_parity(ext, ch_key):
    """比对单章源单元与翻译单元。返回 (ok, problems)。"""
    src_dir = os.path.join(ext, _ac.OUT_DIR_NAME, SRC_SUB, _split.UNITS_DIR % ch_key)
    tgt_dir = os.path.join(ext, _ac.OUT_DIR_NAME, TGT_SUB, _split.UNITS_DIR % ch_key)
    problems = []
    if not os.path.isdir(tgt_dir):
        return False, ["ch%s 缺 units-translate 目录（先跑 init_translate_units.py 初始化清单）。" % ch_key]
    smp, tmp = (os.path.join(d, "manifest.json") for d in (src_dir, tgt_dir))
    if not (os.path.exists(smp) and os.path.exists(tmp)):
        return False, ["ch%s 源/译 manifest.json 缺失。" % ch_key]
    with open(smp, encoding="utf-8") as f:
        src_m = json.load(f)
    with open(tmp, encoding="utf-8") as f:
        tgt_m = json.load(f)
    su, tu = src_m.get("units") or [], tgt_m.get("units") or []

    # 1) 单元序列一致
    if len(su) != len(tu):
        problems.append("单元数不一致：源 %d / 译 %d（漏译或多余单元）" % (len(su), len(tu)))
    for i, (a, b) in enumerate(zip(su, tu)):
        for fld in ("id", "type", "key", "name", "file"):
            if str(a.get(fld) or "") != str(b.get(fld) or ""):
                problems.append("单元 #%d（%s）%s 不一致：源 %r / 译 %r"
                                % (i + 1, a.get("file"), fld, a.get(fld), b.get(fld)))
                break

    for i, (a, b) in enumerate(zip(su, tu)):
        sp = os.path.join(src_dir, a["file"])
        tp = os.path.join(tgt_dir, b["file"])
        if not (os.path.exists(sp) and os.path.exists(tp)):
            problems.append("单元 %s 文件缺失（源/译之一不存在）" % a["file"])
            continue
        sb, tb = _read_body(sp), _read_body(tp)
        utype = a.get("type")

        # 7) 未翻译残留（仅对该翻译的散文：纯公式 / 纯图单元译文与源文一致是正确的）
        if utype in ("item", "desc") and sb.strip() and tb.strip() \
                and _prose_lines(sb) \
                and _hash_text(sb.rstrip("\n")) == _hash_text(tb.rstrip("\n")):
            problems.append("单元 %s 译文与源文完全相同（未翻译）" % a["file"])

        # 2) \tag 一致
        st, tt = _collect(sb, _TAG_RE), _collect(tb, _TAG_RE)
        if st != tt:
            miss = [x for x in st if x not in tt]
            extra = [x for x in tt if x not in st]
            problems.append("单元 %s 公式序标不一致：缺 %s / 多 %s"
                            % (a["file"], miss or "-", extra or "-"))
        # 3) 图片一致
        si, ti = _collect(sb, _IMG_RE), _collect(tb, _IMG_RE)
        if si != ti:
            problems.append("单元 %s 图片不一致：源 %s / 译 %s" % (a["file"], si, ti))
        # 4) 节号一致（section 单元）
        if utype == "section":
            ss, ts = _collect(sb, _SEC_RE), _collect(tb, _SEC_RE)
            if ss != ts:
                problems.append("单元 %s 节号不一致：源 %s / 译 %s" % (a["file"], ss, ts))
        # 5) 编号项标签编号一致（item / exercise 单元）
        if utype in ("item", "exercise"):
            sl, tl = _labels(sb), _labels(tb)
            if sl != tl:
                problems.append("单元 %s 条目编号不一致：源 %s / 译 %s" % (a["file"], sl, tl))
        # 6) 源单元漂移（派生后源又被改 → 译文与源已不同步）
        src_now = _hash_text(sb.rstrip("\n"))
        if b.get("src_hash") and b["src_hash"] != src_now:
            problems.append("单元 %s 源单元已被修改（派生后漂移）——须按单向修复规则"
                            "先定稿源单元，再重新派生/同步翻译单元" % a["file"])

    if problems:
        return False, problems
    return True, ["ch%s 翻译同构通过：%d 个单元（tag / 图 / 节号 / 条目号 / 无漂移）"
                  % (ch_key, len(su))]


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
        print("[check_translate_parity] 无章节可校验。")
        return 2
    all_ok = True
    for k in keys:
        ok, detail = check_chapter_parity(ext, k)
        if ok:
            print("[PASS] " + detail[0])
        else:
            all_ok = False
            print("[FAIL] ch%s 翻译同构未通过（%d 处）：" % (k, len(detail)))
            for d in detail[:40]:
                print("  - " + d)
            if len(detail) > 40:
                print("  … 另有 %d 处" % (len(detail) - 40))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
