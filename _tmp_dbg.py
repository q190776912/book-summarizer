import os, sys, tempfile, difflib
_ROOT = "C:/Users/ye190/.agents/skills/book-summarizer"
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()
import register_all
from verify.script.base import fixable_ordered_fixers

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

def run(p):
    ctx = _Ctx(); ctx.md_file = p
    for code, (fo, fn) in fixable_ordered_fixers():
        fn(ctx)

tf = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
tf.write(SAMPLE); tf.close()
p = tf.name
run(p)
t1 = open(p, encoding="utf-8").read()
print("=== t1 (after pass 1) ===")
for n, line in enumerate(t1.split("\n"), 1):
    print(f"{n:2}: {line!r}")
run(p)
t2 = open(p, encoding="utf-8").read()
print("=== DIFF (t1 -> t2) ===")
for line in difflib.unified_diff(t1.splitlines(), t2.splitlines(), lineterm="", fromfile="after-pass1", tofile="after-pass2"):
    print(line)
print("=== idempotent:", t1 == t2, "===")
os.unlink(p)
