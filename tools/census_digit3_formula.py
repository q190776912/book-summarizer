r"""census_digit3_formula.py — 跨书普查「数字三段落公式序标」`(C.S.N)`（如 `(1.1.5)`）。

用途：`make_config.detect_formula` 的数字探针只有**两段**核 `F_DOT_RE`
（`\((\d+\.\d+)\)`，在第二个数字段后就要求闭括号），三段体例的书对它的命中为零，
而散文中成对的括号年份 `(1979)` / `(1994)` 会被 `F_SINGLE_RE` 大量收走 →
择族落到 `{"type": 1}`，Q 层按单段核对 `(1)`，全书 `(C.S.N)` 序标全部失明。
实测成因：Lehmann《Elements of Large-Sample Theory》(Springer 1999) 印
`(1.1.5)`…`(7.9.14)`，右缘编号 4000+ 条，探测却给出 type 1 / scope 3。

本工具在写判据前先取证（项目规程：任何判据的松紧必须跨语料普查校准）：
逐书逐页按「块末右缘干净收尾」纪律（`_formula_tail_clean`）数
三段 / 两段 / 单段命中，打印每本书当前的 `formula.type`（若有）与
三段 (chapter, section) 分桶 + 最长连升串，供人工确定置信阈值与 scope。
判据落进 `make_config` 后本工具即其**回归对照台**：逐书用同一判据算「会不会择成
type 3」，与存量 `ch.formula.type` 比差集——存量 type3 不再被择 = 回归，存量非
type3 被择成 type3 = 重生成会改写该书选型，须逐本回印面核实后才能放行。

用法：
    python tools/census_digit3_formula.py <corpus_root> [--min 30] [--book 子串]

🔴 只读：不改任何文件、不写台账。
"""
import io
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
    _ROOT = str(Path(__file__).resolve().parents[1])
for _p in (_ROOT, os.path.join(_ROOT, "lib"), os.path.join(_ROOT, "config")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

from lib.regexlib import F_SINGLE_RE, F_DOT_RE, F_DIGIT3_RE   # noqa: E402
from make_config import (_formula_tail_clean, _alpha3_confident,   # noqa: E402
                         _digit3_scope, _FORMULA_MIN_COUNT)


def _page_files(book_dir):
    for base, _dirs, files in os.walk(os.path.join(book_dir, "_extract")):
        for fn in files:
            if re.fullmatch(r'page_\d{3}\.json', fn):
                yield os.path.join(base, fn)


def current_formula_types(book_dir):
    """该书 verify_config.json 各段现有 formula 选型（无配置返回 {}）。"""
    out = {}
    for base, _dirs, files in os.walk(os.path.join(book_dir, "_extract")):
        if "verify_config.json" not in files:
            continue
        try:
            d = json.load(io.open(os.path.join(base, "verify_config.json"),
                                  encoding="utf-8-sig"))
        except Exception:
            continue
        segs = d if isinstance(d.get("ch"), dict) else {"ch": d}
        for kind, seg in segs.items():
            if isinstance(seg, dict) and isinstance(seg.get("formula"), dict):
                f = seg["formula"]
                out[kind] = (f.get("type"), f.get("scope"),
                             bool(f.get("letter_ch")))
        break
    return out


def scan_book(book_dir):
    h3, h2, h1 = [], [], []
    pages = 0
    for fp in _page_files(book_dir):
        pages += 1
        try:
            data = json.load(io.open(fp, encoding="utf-8"))
        except Exception:
            continue
        raw = data.get("text") or []
        if isinstance(raw, str):
            texts = [raw]
        else:
            texts = []
            for b in raw:
                if isinstance(b, str):
                    texts.append(b)
                elif isinstance(b, dict):
                    t = b.get("text")
                    if isinstance(t, str):
                        texts.append(t)
        for text in texts:
            if not text:
                continue
            # 与 make_config.detect_formula 同纪律：每族各看各的「块末右缘」，
            # 不再三族互斥短路（互斥计数会把 d1 噪声算成 0，无法复现真实择族）。
            m3 = list(F_DIGIT3_RE.finditer(text))
            if m3:
                last = m3[-1]
                if _formula_tail_clean(text[last.end():]):
                    h3.append((int(last.group(1)), int(last.group(2)),
                               int(last.group(3))))
            m2 = list(F_DOT_RE.finditer(text))
            if m2:
                last = m2[-1]
                if _formula_tail_clean(text[last.end():]):
                    h2.append((last.group(1),))
            m1 = list(F_SINGLE_RE.finditer(text))
            if m1:
                last = m1[-1]
                if _formula_tail_clean(text[last.end():]):
                    h1.append((last.group(1),))
    return dict(pages=pages, d3=h3, d2=h2, d1=h1)


def _series(hits):
    buckets = {}
    for c, s, n in hits:
        buckets.setdefault((c, s), set()).add(n)
    longest = 0
    for nums in buckets.values():
        uniq = sorted(nums)
        cur = run = 1
        for i in range(1, len(uniq)):
            cur = cur + 1 if uniq[i] == uniq[i - 1] + 1 else 1
            run = max(run, cur)
        longest = max(longest, run)
    return buckets, longest


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    root = argv[0]
    sub = argv[argv.index("--book") + 1] if "--book" in argv else None
    min_hits = int(argv[argv.index("--min") + 1]) if "--min" in argv else 30
    books = fired = would_flip = 0
    rows = []
    flags = []
    for kind in sorted(os.listdir(root)):
        shelf = os.path.join(root, kind)
        if not os.path.isdir(shelf):
            continue
        for name in sorted(os.listdir(shelf)):
            bd = os.path.join(shelf, name)
            if not os.path.isdir(os.path.join(bd, "_extract")):
                continue
            if sub and sub.lower() not in bd.lower():
                continue
            books += 1
            st = scan_book(bd)
            cur = current_formula_types(bd)
            # 与 detect_formula 的新分支同一判据（条数闸 + 对全家族占优 + 形状）
            wins = (len(st["d3"]) >= _FORMULA_MIN_COUNT
                    and len(st["d3"]) > (len(st["d2"]) + len(st["d1"]))
                    and _alpha3_confident(st["d3"]))
            cur_ch = cur.get("ch", (None, None, None))[0]
            flags.append((name, wins, cur_ch))
            if len(st["d3"]) < min_hits:
                continue
            fired += 1
            b3, run3 = _series(st["d3"])
            sc = _digit3_scope(st["d3"]) if wins else "-"
            if wins:
                would_flip += 1
            rows.append((name, st["pages"], len(st["d3"]), len(st["d2"]),
                         len(st["d1"]), len(b3), run3, wins, sc, cur))
    print("%-52s %6s %6s %6s %6s %6s %5s %-6s %-4s %s"
          % ("book", "pages", "d3", "d2", "d1", "bckts", "run", "elects",
             "scope", "current formula"))
    for r in sorted(rows, key=lambda x: -x[2]):
        print("%-52s %6d %6d %6d %6d %6d %5d %-6s %-4s %s"
              % (r[0][:52], r[1], r[2], r[3], r[4], r[5], r[6],
                 "YES" if r[7] else "no", r[8], r[9]))
    print("\nbooks=%d  d3>=%d: %d  会择三段: %d"
          % (books, min_hits, fired, would_flip))
    lost = [n for n, w, c in flags if c == 3 and not w]
    gained = [n for n, w, c in flags if w and c not in (3, None)]
    print("存量 ch.formula.type==3 却不被新判据择出: %s" % (lost or "无"))
    print("  ↑ 🔴 这不是本次改动引入的回归：改动前的 detect_formula **从不** emit "
          "type 3（唯一出口就是新分支），故这些书的存量 3 本来就不可由探测器复现"
          "（老探针/手填遗留）。它们的处置是「别再 --force 该书」，而不是放宽阈值。")
    print("存量非 type3 却被择成 type3（重生成会改写选型，需逐本人工核印面）: %s"
          % (gained or "无"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
