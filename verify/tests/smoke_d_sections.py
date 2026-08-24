"""Synthetic integration smoke for the D-layer nested-section feature.

The real corpus under D:\\study\\book has NO page_*.json / verify_config.json
(only .txt/.log dumps in analytic-number-theory/_extract), so a true
end-to-end run against real OCR is impossible.  Instead we build a FAITHFUL
synthetic book (real .md heading structure + crafted OCR page JSON that mirrors
the regexes the D-layer scans) and drive the actual `verify_chapter.py` CLI:

  * 3-level book  (ordinal=3) -> d_layer must contain `levels` and emit a
    REASONABLE subsection finding (gap truly present in .md, not a false +).
  * 2-level book  (ordinal=2) -> must NOT emit any subsection (LEVEL 3) finding;
    only the genuine missing section is reported (back-compat preserved).
  * gm book       (ordinal=6) -> must route through check_d_layer_gm, not crash,
    and must NOT print a per-level block (no `levels`).
  * --all summary (risk E) -> must read d_layer.continuity_sections without error.

Run:  python verify/tests/smoke_d_sections.py
"""
import os
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

import os
import sys
import io
import json
import shutil
import tempfile
import subprocess

PY = sys.executable
CLI = os.path.join(_ROOT, "verify/script/verify_chapter.py")


def _page(path, texts, y=200):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {"text": [{"text": t, "poly": [0, y, 100, y, 100, y + 10, 0, y + 10]}
                      for t in texts]}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _cfg(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f)


def _run(args):
    p = subprocess.run([PY, CLI] + args, cwd=_ROOT,
                       capture_output=True, text=True, timeout=120,
                       encoding="utf-8", errors="replace")
    return p.returncode, p.stdout, p.stderr


def build_three_level(book):
    ext = os.path.join(book, "_extract")
    os.makedirs(ext, exist_ok=True)
    _cfg(os.path.join(ext, "verify_config.json"), {"ordinal": 3})
    _cfg(os.path.join(ext, "chapter_map.json"),
         {"chapters": [{"ch": 1, "start": 1, "end": 1}]})
    md = os.path.join(book, "第1章_测度论.md")
    md_text = (
        "# 第一章 测度论\n\n"
        "## §1 可测空间\n\n"
        "### §1.1 集类\n\n"
        "#### §1.1.1 定义\n\n内容。\n\n"
        "#### §1.1.2 引理\n\n内容。\n\n"
        "#### §1.1.3 定理\n\n内容。\n\n"
        "### §1.2 生成σ代数\n\n"
        "#### §1.2.1 命题\n\n内容。\n\n"
        # §1.2.2 intentionally OMITTED from .md (gap) -> expect finding
        "#### §1.2.3 推论\n\n内容。\n"
    )
    with open(md, "w", encoding="utf-8") as f:
        f.write(md_text)
    _page(os.path.join(ext, "page_001.json"), [
        "§1.1.1 集类一", "1.1.1 定义 某集类",
        "§1.1.2 集类二", "1.1.2 引理 某引理",
        "§1.1.3 集类三", "1.1.3 定理 某定理",
        "§1.2.1 生成一", "1.2.1 命题 某命题",
        "§1.2.2 生成二", "1.2.2 定义 某定义",   # present in source, missing in md
        "§1.2.3 生成三", "1.2.3 推论 某推论",
    ])
    return md, ext


def build_two_level(book):
    ext = os.path.join(book, "_extract")
    os.makedirs(ext, exist_ok=True)
    _cfg(os.path.join(ext, "verify_config.json"), {"ordinal": 2})
    _cfg(os.path.join(ext, "chapter_map.json"),
         {"chapters": [{"ch": 1, "start": 1, "end": 1}]})
    md = os.path.join(book, "第1章_代数.md")
    md_text = (
        "# 第一章 代数\n\n"
        "## §1 群\n\n"
        "### §1.1 定义\n\n内容。\n\n"
        # §1.2 intentionally OMITTED (gap at section level)
        "### §1.3 同态\n\n内容。\n"
    )
    with open(md, "w", encoding="utf-8") as f:
        f.write(md_text)
    _page(os.path.join(ext, "page_001.json"), [
        "§1.1 群一", "1.1 定义 某定义",
        "§1.2 群二", "1.2 引理 某引理",   # section 2 present in source
        "§1.3 群三", "1.3 同态 某同态",
        # subsection-like noise: must NOT create a subsection finding
        "§1.2.1 嵌套小节", "1.2.1 定义 嵌套定义",
    ])
    return md, ext


def build_gm(book):
    ext = os.path.join(book, "_extract")
    os.makedirs(ext, exist_ok=True)
    _cfg(os.path.join(ext, "verify_config.json"), {"ordinal": 6})
    _cfg(os.path.join(ext, "chapter_map.json"), {"chapters": [{
        "num": 1, "sections": [
            {"sec": 1, "start": 1, "end": 1},
            {"sec": 2, "start": 1, "end": 1}]}]})
    md = os.path.join(book, "第1章_同调代数.md")
    md_text = (
        "# Homological Algebra Ch1\n\n"
        "## §1. Triangulated Spaces\n\n"
        "### 1. Main Definitions\n\n"
        "### 3. Proposition\n\n"
    )
    with open(md, "w", encoding="utf-8") as f:
        f.write(md_text)
    _page(os.path.join(ext, "page_001.json"), [
        "§1. Triangulated Spaces", "1. Main Definitions",
        "§2. Simplicial Sets", "2. Auxiliary. Some statement",
        "3. Proposition. A statement",
    ])
    return md, ext


def main():
    base = tempfile.mkdtemp(prefix="d_smoke_")
    results = []

    # --- Scenario 1: 3-level book (ordinal=3) ---
    b3 = os.path.join(base, "book3")
    md3, ext3 = build_three_level(b3)
    rc, out, err = _run([str(1), "1", "1", md3, ext3])
    ok = ("D-LAYER LEVEL 3" in out) and ("§1.2.2" in out) and ("LEVEL 3 CONTINUITY" in out)
    results.append(("3-level ordinal=3: levels present + reasonable subsection finding",
                    ok, rc, out, err))

    # --- Scenario 2: 2-level book (ordinal=2) ---
    b2 = os.path.join(base, "book2")
    md2, ext2 = build_two_level(b2)
    rc, out, err = _run([str(1), "1", "1", md2, ext2])
    # MUST report the missing section (§1.2) but MUST NOT emit any LEVEL 3 block
    ok = ("D-LAYER LEVEL 3" not in out) and ("§1.2" in out)
    results.append(("2-level ordinal=2: no subsection(LEVEL 3) finding, section gap kept",
                    ok, rc, out, err))

    # --- Scenario 3: gm book (ordinal=6) ---
    bg = os.path.join(base, "bookgm")
    mdg, extg = build_gm(bg)
    rc, out, err = _run([str(1), "1", "1", mdg, extg])
    ok = ("D-LAYER LEVEL" not in out) and ("Traceback" not in err) and ("Traceback" not in out)
    results.append(("gm ordinal=6: routes via check_d_layer_gm, no per-level block, no crash",
                    ok, rc, out, err))

    # --- Scenario 4: --all summary (risk E) ---
    rc, out, err = _run(["--all", ext3, b3])
    ok = ("Dc:" in out) and ("Traceback" not in err) and ("Traceback" not in out)
    results.append(("verify_chapter.py --all compact summary reads d_layer (risk E)",
                    ok, rc, out, err))

    # ---- report ----
    print("=" * 70)
    print("D-LAYER SECTION SMOKE  (synthetic-but-realistic integration)")
    print("=" * 70)
    all_ok = True
    for name, ok, rc, out, err in results:
        status = "PASS" if ok else "FAIL"
        all_ok = all_ok and ok
        print(f"[{status}] {name}  (cli_rc={rc})")
        if not ok:
            print("   --- stdout (tail) ---")
            print("\n".join(out.splitlines()[-25:]))
            if err.strip():
                print("   --- stderr (tail) ---")
                print("\n".join(err.splitlines()[-15:]))
    print("=" * 70)
    print("SMOKE RESULT:", "ALL PASS" if all_ok else "FAILURES PRESENT")
    shutil.rmtree(base, ignore_errors=True)
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
