import os, sys, re, tempfile

_ROOT = "C:/Users/ye190/.agents/skills/book-summarizer"
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()
import register_all  # triggers fixer self-registration
from verify.script.base import fixable_ordered_fixers
from format_verify import (check_nested_blockquotes, check_example_proof_gap,
                           check_heading_separators)

SAMPLE = """## 2.1 节标题

---

**定义2.1** 内容

> **例2.1-1** 叙述
一些非块引用内容在例与证明之间
> **证明思路** 证明内容

> **例2.2-1** 叙述 **证明梗概** 还是叙述

> > **例2.3-1** 嵌套的例子
> > 嵌套的内容

正文结尾
"""

class _Ctx:
    md_file = None

def run_fixers(p):
    ctx = _Ctx(); ctx.md_file = p
    for code, (fo, fn) in fixable_ordered_fixers():
        fn(ctx)

def main():
    tf = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
    tf.write(SAMPLE); tf.close()
    try:
        p = tf.name
        # ---- run the full verify --fix pipeline ----
        run_fixers(p)
        text = open(p, encoding="utf-8").read()
        # 1) nested blockquote flattened
        assert not re.search(r'^>\s+>', text, re.M), "nested bq not flattened"
        # 2) same-line example+proof split into two `>` lines
        assert "**例2.2-1** 叙述\n> **证明梗概**" in text, "same-line not split:\n" + text
        # 3) example-proof gap merged (top-level line pulled into blockquote)
        assert "> 一些非块引用内容在例与证明之间" in text, "gap not merged:\n" + text
        # 4) no `---` directly under a heading
        lines = text.split("\n")
        for i, ln in enumerate(lines):
            if ln.strip() == "---":
                j = i - 1
                while j >= 0 and lines[j].strip() == "":
                    j -= 1
                assert not (j >= 0 and re.match(r'^#{2,6}\s', lines[j])), "--- under heading remains"
        # 5) idempotency: second pass produces no change
        before = open(p, encoding="utf-8").read()
        run_fixers(p)
        after = open(p, encoding="utf-8").read()
        assert before == after, "fix not idempotent"
        # 6) detection is clean after fix
        assert check_nested_blockquotes(p) == [], check_nested_blockquotes(p)
        assert check_example_proof_gap(p) == ([], []), check_example_proof_gap(p)
        assert check_heading_separators(p) == [], check_heading_separators(p)
        print("INTEGRATION OK")
    finally:
        os.unlink(p)

if __name__ == "__main__":
    main()
