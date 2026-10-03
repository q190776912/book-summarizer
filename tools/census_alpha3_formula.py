r"""census_alpha3_formula.py — 跨书普查「字母/罗马三段落公式序标」`(A.2.1)` / `(II.1.3)`。

用途：`make_config.detect_formula` 的字母/罗马探测只认**两段**核 `(A.3)`
（`lib/regexlib.F_LETTER_RE` 在第一个数字段后就要闭括号），于是三段体例的书
（Katok《现代动力系统导论》附录A `(A.2.1)`…、补篇S `(S.2.1)`…，2026-10-03 实测）
打印的公式序标**一个也收不到** → 该段 `verify_config.json` 无 `formula` 键 →
Q 层 no-op WARN，公式序标从未校验。

本工具在写判据前先取证（项目规程：任何判据的松紧必须跨语料普查校准）：
逐书逐页扫描三段（以及两段，作对照）字母/罗马命中，按「右缘干净收尾」纪律
（`_formula_tail_clean`）计数，并打印每本书的 (head, section) 分桶序列，供人工
确定置信阈值与 scope（每节重启 vs 全书连续）。

用法：
    python tools/census_alpha3_formula.py <corpus_root> [--min 5] [--book 子串] [--verbose]

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

from lib.regexlib import (F_LETTER_RE, F_ROMAN_RE,         # noqa: E402
                          F_LETTER3_RE, F_ROMAN3_RE)
from make_config import _formula_tail_clean               # noqa: E402

# 三段候选的探针与 `lib/regexlib` 同源（唯一真源），此处只留别名。
_F_LETTER3 = F_LETTER3_RE
_F_ROMAN3 = F_ROMAN3_RE


def _page_files(book_dir):
    for base, _dirs, files in os.walk(os.path.join(book_dir, "_extract")):
        for fn in files:
            if re.fullmatch(r'page_\d{3}\.json', fn):
                yield os.path.join(base, fn)


def _block_text(b):
    if not isinstance(b, dict):
        return ""
    t = b.get("text")
    return t if isinstance(t, str) else ""


def scan_book(book_dir):
    hits3, hits2 = [], []
    r3, r2 = [], []
    n_pages = 0
    for fp in _page_files(book_dir):
        n_pages += 1
        try:
            data = json.load(io.open(fp, encoding="utf-8"))
        except Exception:
            continue
        for text in [_block_text(b) for b in (data.get("text") or [])]:
            if not text:
                continue
            for rx, sink in ((_F_LETTER3, hits3), (_F_ROMAN3, r3)):
                ms = list(rx.finditer(text))
                if ms:
                    last = ms[-1]
                    if _formula_tail_clean(text[last.end():]):
                        sink.append((last.group(1), int(last.group(2)),
                                     int(last.group(3))))
            for rx, sink in ((F_LETTER_RE, hits2), (F_ROMAN_RE, r2)):
                ms = list(rx.finditer(text))
                if ms:
                    last = ms[-1]
                    if _formula_tail_clean(text[last.end():]):
                        sink.append((last.group(1), int(last.group(2))))
    return dict(pages=n_pages, letter3=hits3, roman3=r3,
                letter2=hits2, roman2=r2)


def _series(hits):
    """(head, section) -> sorted unique numbers, plus longest consecutive run."""
    buckets = {}
    for h, s, n in hits:
        buckets.setdefault((h.upper(), s), set()).add(n)
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
    verbose = "--verbose" in argv
    min_hits = int(argv[argv.index("--min") + 1]) if "--min" in argv else 5
    books = 0
    fired = 0
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
            if not st["letter3"] and not st["roman3"]:
                continue
            fired += 1
            b3, run3 = _series(st["letter3"])
            rb3, rrun3 = _series(st["roman3"])
            print("== %-58s pages=%d L3=%d(run %d, buckets %d) R3=%d(run %d) "
                  "L2=%d R2=%d" % (os.path.relpath(bd, root)[:58], st["pages"],
                                   len(st["letter3"]), run3, len(b3),
                                   len(st["roman3"]), rrun3,
                                   len(st["letter2"]), len(st["roman2"])))
            if verbose:
                for k in sorted(b3):
                    print("     %s.%s -> %s" % (k[0], k[1], sorted(b3[k])))
                for k in sorted(rb3):
                    print("     R %s.%s -> %s" % (k[0], k[1], sorted(rb3[k])))
    print("\ncensus: %d books scanned | %d with any alpha-led 3-comp hit "
          "(threshold --min %d)" % (books, fired, min_hits))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
