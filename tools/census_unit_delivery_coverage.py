r"""census_unit_delivery_coverage.py — 跨书普查「单元里的显示式在交付 md 里找不到」。

用途：写源链上，单元 → 交付的唯一机械保证是 `merge_units`（纯脚本按 manifest 拼接）+
verify 的 B/P/Q 层。**拼接之后**按印面做的修订轮（步骤 8）是手工同行替换，没有任何
判据回头检查「手工替换有没有顺手删掉一条式子」。本工具补的就是这个方向的单向覆盖：
逐单元取 `$$…$$` 块，在该书**全部**交付 md 里找它的归一内核；找不到 → 列进报告。

🔴 这是**报告工具，不是闸门**（exit 恒 0）。理由（实测）：交付在 merge 之后按印面手修
是**正确**结果，把它和单元逐字对齐的等式闸会把正确交付判成违规，并逼代理回头照抄单元里
残留的 OCR 粘连形（= 闸门 bug）。故只报「单元有、交付完全没有」这一个方向，交人工裁决。

三处已证的假阳机制，判据里先归一/排除（每条都有负向测试锁住）：
1. **`merge: false` 的单元**：V-I 规定「有专门小标题的集中习题块一律省略」，这类单元本就
   不进交付（real-analysis ch10/ch11 习题 336 条即此形）。
2. **排版脚手架**：`\begin{env}{cols}` / `\end{env}` / `&` / `\\` / `\left` 等不携带数学内容
   （Fraleigh ch29/0034：单元写成 `array` 对齐式、交付写成行内散文式，内容一字未丢）。
3. **只 `\tag` 形态分叉**：块体剥掉 `\tag{}` 后能在交付里对上 = `TAG_FORM`，是编号记法
   差异不是内容丢失（methods-of-homological-algebra：单元 `\tag{1.2}` vs 交付 `\tag{I.2}`；
   印面是罗马章号，交付为真）。

另有一条**踩过的坑**：交付侧**不按文件名 ASCII/非 ASCII 分侧**。Evans-SDE 的 EN 交付文件名
里带弯引号（`Chapter3_Brownian_Motion_and_“White_Noise”.md`），按名分侧会把它划进中文版，
于是全书虚报 216+21 条。两版交付的数学内容由 parity 1:1 锁定，合成一个 haystack 不丢判别力。

用法：
    python tools/census_unit_delivery_coverage.py <corpus_root|book_dir> [--book 子串]
                                                 [--side all|src|tr] [--top N] [--verbose]

🔴 只读：不改任何文件、不写台账。
"""
import argparse
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
for _p in (_ROOT, os.path.join(_ROOT, "lib"),
           os.path.join(_ROOT, "flows", "write-source", "script")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

# 归一化直接复用 parity 判据 9 的实现，避免两处各写一份而漂移
from check_translate_parity import _flatten_math                       # noqa: E402

TAG_RE = re.compile(r"\\tag\{([^}]*)\}")
DISPLAY_RE = re.compile(r"\$\$[\s\S]*?\$\$")
ENV_RE = re.compile(r"\\(?:begin|end)\{[^{}]*\}(?:\{[^{}]*\})?")
TOKEN_RE = re.compile(r"[A-Za-z0-9]{2,}|\\[A-Za-z]+")
WRAP_RE = re.compile(r"^\s*>?\s*", re.M)

# 需要人读的档：HIGH = 内核几乎都在交付里、只差一两个 token（多为单元侧 OCR 残字/记法差，
# 也可能是交付改动了一个符号）；ABSENT = 连 token 都基本找不到 = 整块疑似真丢失。
BUCKET_ABSENT = 0.40
BUCKET_HIGH = 0.95


def shape_norm(s):
    """剥掉不携带数学内容的排版脚手架。"""
    s = ENV_RE.sub("", s)
    s = re.sub(r"\\\\", "", s).replace("&", "")
    return re.sub(r"\\(?:left|right|big[lr]?[LR]?|Big[lr]?[LR]?|displaystyle|textstyle)",
                  "", s)


def untag(s):
    return TAG_RE.sub("", s)


def block_core(blk):
    """`$$…$$` 块 → 归一内核（剥行首 `>`、折空白、删 `$`、删 `\text{}` 体、剥脚手架）。"""
    return shape_norm(_flatten_math(WRAP_RE.sub("", blk)))


def token_coverage(core, hay):
    toks = TOKEN_RE.findall(core)
    if not toks:
        return 1.0, []
    miss = [t for t in toks if t not in hay]
    return 1.0 - len(miss) / float(len(toks)), miss


def delivery_haystack(book_dir):
    """该书全部交付 md 的归一文本 + tag 全集（不分中英侧，见模块 docstring）。"""
    parts = []
    for p in sorted(Path(book_dir).glob("*.md")):
        with open(p, encoding="utf-8", errors="replace") as f:
            parts.append(f.read())
    raw = "\n".join(parts)
    flat = _flatten_math(raw)
    return {"raw": flat, "shape": shape_norm(flat),
            "tags": set(TAG_RE.findall(raw))}


def block_problems(blk, hay, label):
    """单个 `$$` 块对交付的覆盖判定；返回 None = 覆盖成立（放行）。"""
    core = block_core(blk)
    if not core or core in hay["shape"]:
        return None
    tags = [t.strip() for t in TAG_RE.findall(blk)]
    if untag(core) in hay["shape"]:
        kind = "TAG_FORM"
    elif tags and not all(t in hay["tags"] for t in tags):
        kind = "TAG_LOST"
    else:
        kind = "BLOCK_LOST"
    cov, miss = token_coverage(untag(core), hay["shape"])
    bucket = ("ABSENT" if cov < BUCKET_ABSENT
              else "HIGH" if cov >= BUCKET_HIGH else "MID")
    return {"unit": label, "kind": kind, "bucket": bucket, "cov": cov,
            "core": core, "missing": miss}


def _manifest_records(udir):
    p = os.path.join(str(udir), "manifest.json")
    if not os.path.exists(p):
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            recs = json.load(f).get("units", [])
    except Exception:
        return {}
    return {r.get("file"): r for r in recs if isinstance(r, dict)}


def _skipped(rec_a, rec_b):
    """任一那侧登记 `merge: false` = 按 V-I 有意省略，不进交付。"""
    return any((r or {}).get("merge") is False for r in (rec_a, rec_b))


def unit_blocks(units_dir, other_dir=None):
    """遍历某侧单元目录，产出 (章目录, 单元文件, 正文)；跳过 `merge: false`。"""
    for cdir in sorted(Path(units_dir).glob("ch*/")):
        same = _manifest_records(cdir)
        # merge 标记只写在源侧清单上，译侧要回读源侧同名清单
        twin = _manifest_records(Path(other_dir) / cdir.name) if other_dir else {}
        for uf in sorted(cdir.glob("*.md")):
            if _skipped(same.get(uf.name), twin.get(uf.name)):
                continue
            yield cdir.name, uf.name, uf.read_text(encoding="utf-8", errors="replace")


def scan_book(book_dir, side="all"):
    hay = delivery_haystack(book_dir)
    if not hay["raw"].strip():
        return []
    bs = Path(book_dir) / "_extract" / "book_structure"
    out = []
    sides = (("src", bs / "units", None),
             ("tr", bs / "units-translate", bs / "units"))
    for name, udir, other in sides:
        if side not in ("all", name) or not udir.is_dir():
            continue
        for ch, fname, body in unit_blocks(udir, other):
            for blk in DISPLAY_RE.findall(body):
                p = block_problems(blk, hay, "%s/%s" % (ch, fname))
                if p:
                    p["side"] = name
                    out.append(p)
    return out


def _book_dirs(root):
    rp = Path(root)
    if (rp / "_extract").is_dir() or list(rp.glob("*.md")):
        return [rp]
    res = []
    for ud in sorted(rp.glob("*/*/_extract/book_structure/units")):
        res.append(ud.parents[2])
    return res


def main():
    ap = argparse.ArgumentParser(description="单元 → 交付 单向覆盖普查（只读报告）")
    ap.add_argument("root", help="corpus_root 或单本书目录")
    ap.add_argument("--book", default="", help="只跑书名含该子串的书")
    ap.add_argument("--side", default="all", choices=["all", "src", "tr"])
    ap.add_argument("--top", type=int, default=25, help="打印多少条候选明细")
    ap.add_argument("--out", default="", help="把报告另存到该路径（默认只打印；"
                                              "不往语料根目录落文件=临时文件隔离）")
    ap.add_argument("--verbose", action="store_true", help="打印 MID 档明细")
    args = ap.parse_args()

    need = 0
    per_book = []
    lines = []
    for bd in _book_dirs(args.root):
        if args.book and args.book not in str(bd):
            continue
        probs = scan_book(str(bd), args.side)
        cand = [p for p in probs if p["kind"] != "TAG_FORM"
                and (p["bucket"] != "MID" or args.verbose)]
        tagform = sum(1 for p in probs if p["kind"] == "TAG_FORM")
        if not probs:
            continue
        per_book.append((len(cand), tagform, bd))
        need += len(cand)
        for p in cand:
            lines.append("%s [%s %s cov=%.2f] %s\n    %s\n    MISS: %s" % (
                bd.name, p["side"], p["kind"], p["cov"], p["unit"],
                p["core"][:120], ",".join(p["missing"][:8])))
    buf = io.StringIO()
    print("== 按书：需人读候选 / TAG_FORM（编号记法差异，不报为丢失）==", file=buf)
    for n, tf, bd in sorted(per_book, key=lambda x: -x[0]):
        print("%5d  %5d  %s" % (n, tf, bd), file=buf)
    print("\n需人读候选合计：%d" % need, file=buf)
    print("\n== 候选明细（前 %d 条）==" % args.top, file=buf)
    print("\n".join(lines[:args.top]), file=buf)
    text = buf.getvalue()
    print(text)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print("[census_unit_delivery_coverage] 报告已写入 %s" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
