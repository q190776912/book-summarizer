"""h_mbq_debt_scan.py — 全库「顶级注释类标签」欠账清单（2026-09-27 h_mbq 双语对称根治的配套盘点）。

背景：`_H_MISSING_BQ`（F/H 层 h_mbq，见 `verify/format_verify/format_verify.md` 检测规则8）于
2026-09-27 补齐 `Remarks?` 与 CN `评注`，使「附属块标签必须包进 `>`」这条约定**按语义而非按语言**成立。
判据一翻，存量书里所有顶级 `**Remark N.M**` / `**评注 N.M**` 行在下一次 gate/verify 即 FAIL。
本脚本用**改动前的基线正则**（硬编码在下方 `OLD`，逐字符 = 补词前的 `_H_MISSING_BQ`）与现行判据对比，
只报**新增命中**，即真正需要整改的清单。

只读：不改任何文件。`--report <path>` 另存 UTF-8 文本。

    python tools/h_mbq_debt_scan.py                      # 打到 stdout（CJK 走 backslashreplace）
    python tools/h_mbq_debt_scan.py --report _h_mbq_debt.txt

整改口径（每本书一遍）：`verify --fix --fix-force`（H 修法器现已连正文一起包，见
`verify/tests/test_h_mbq_fix_wraps_body_run.py`）→ 重 `init_translate_units` 同步 src_hash
（🔴 该脚本会把 manifest `final_md` 重置成空，跑完必须回填）→ 重 gate → 重 merge → 重 split → 重 verify → 重落账。
"""
import io
import os
import re
import sys
from collections import defaultdict

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SKILL)
import lib.boot as _boot  # noqa: E402
_boot.setup()
from format_verify import _H_MISSING_BQ as NEW  # noqa: E402
from user_config import load as _load_cfg  # noqa: E402

CORPUS = _load_cfg().get("corpus_root") or r"D:/study/book"

# 补词之前的 `_H_MISSING_BQ`，逐字符留档，勿改（改了基线就对不上）
OLD = re.compile(
    r'^\s*\*\*(?:'
    r'(?:证明|证|证明思路|证明概要|解答?|注记|说明'
    r'|Proof|Example|Solution|Note)(?![\w\-])'
    r'|例(?:\s*\d[\d.]*)?'
    r'|注(?:\s*\d[\d.]*)?'
    r'|\d{1,3}(?:[.．\-－]\d{1,3}){1,2}\s*'
    r'(?:例|例子|Example|Solution|Proof|Note|Remark|证明|证|说明|注)'
    r')'
)


def flag_lines(path, pat):
    """Same line filter as `check_labels_missing_blockquote` (headers / `>` / display math skipped)."""
    with io.open(path, encoding="utf-8", errors="replace") as f:
        lines = f.read().split("\n")
    out, in_math = [], False
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s == "$$":
            in_math = not in_math
            continue
        if (s.startswith("$$") and s.endswith("$$")) or in_math or s.startswith(">") \
                or re.match(r"^#{1,6}\s", ln):
            continue
        if pat.match(s):
            out.append((i + 1, s[:80]))
    return out


def main():
    hits = defaultdict(lambda: defaultdict(list))
    words = defaultdict(int)
    for root, dirs, names in os.walk(CORPUS):
        dirs[:] = [d for d in dirs if d not in ("figure", "__pycache__")]
        for n in names:
            if not n.endswith(".md"):
                continue
            fp = os.path.join(root, n)
            rel = os.path.relpath(fp, CORPUS).replace("\\", "/")
            parts = rel.split("/")
            book = "/".join(parts[:2])
            if "/units-translate/" in rel:
                kind = "unit-cn"
            elif "/units/" in rel:
                kind = "unit-src"
            elif "/_extract/" in rel or len(parts) > 4:
                continue                      # 只看单元与章级交付 md
            else:
                kind = "deliverable"
            try:
                old = {i for i, _ in flag_lines(fp, OLD)}
                new = [(i, t) for i, t in flag_lines(fp, NEW) if i not in old]
            except Exception:
                continue
            for i, t in new:
                hits[book][kind].append((rel, i, t))
                m = re.match(r"^\*\*(\S+)", t)
                if m:
                    words[m.group(1).strip("*（(")] += 1

    out = io.StringIO()
    uniq = sum(len(v) for b in hits.values() for k, v in b.items() if k != "deliverable")
    tot = sum(len(v) for b in hits.values() for v in b.values())
    out.write("h_mbq newly-required top-level annotation labels (2026-09-27 symmetry fix)\n")
    out.write("corpus=%s  hits=%d  unique-in-units=%d  books=%d\n" % (CORPUS, tot, uniq, len(hits)))
    out.write("（deliverable 与其 units 是同一内容，去重看 unique-in-units）\n\n")
    out.write("by label word:\n")
    for w, c in sorted(words.items(), key=lambda kv: -kv[1])[:20]:
        out.write("  %-22s %d\n" % (w.encode("unicode_escape").decode(), c))
    out.write("\nby book (total / unit-src / unit-cn / deliverable):\n")
    for book in sorted(hits, key=lambda b: -sum(len(v) for v in hits[b].values())):
        n = sum(len(v) for v in hits[book].values())
        kinds = " ".join("%s=%d" % (k, len(v)) for k, v in sorted(hits[book].items()))
        out.write("  %-60s %4d  %s\n" % (book.encode("unicode_escape").decode()[:58], n, kinds))
    text = out.getvalue()
    if "--report" in sys.argv:
        dest = sys.argv[sys.argv.index("--report") + 1]
        with io.open(dest, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print("written", dest)
    print(text)


main()
