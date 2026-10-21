r"""tools/tighten_loose_math.py — 松散 OCR 数学形态的**机械档**归一（判据第 25 项的反向通道）。

门控第 25 项（`check_unit_quality.loose_math_problems`）拦「照抄 OCR 摊开的数学」：
`x _ { n }` / `\frac { a } { b }` / `\left (` / `\sqrt [ n ]` / `] {` / `3 . 1 . 1`。
此前只有判据没有修法器，返修只能给每本书写一次性正则（正则在书目录里长大，跨书不可复用，
且极易与判据口径走岔）。本工具把反转做进 skill，并**与判据共用同一份片段遍历**
（`loose_math_frag_spans`）——判据看哪儿就改哪儿，散文/表格数字列/`p. 12` 一概不碰。

🔴 分档：只反转 `LOOSE_MATH_MECHANICAL` 两档空白——①「标记/命令与开括号之间」
（`X _ { t }`→`X_{ t }`、`\left (`→`\left(`）；②括号**内侧**与 `} {` 接缝
（`X_{ t }`→`X_{t}`、`\frac{ a }{ b }`→`\frac{a}{b}`）。两档都只删紧邻括号的空白，
渲染中性、可逆。`LOOSE_MATH_SEMANTIC`（数字逐位摊开 `1 0 6` / `3 . 1 . 1`）**不改**：
焊起来遇到「OCR 真漏了一位/小数点」就是把错值钉死，须写手读印面重写。
text 模式参数（`\text{ a s }`）内侧空格是内容，同样不改。工具把残留逐条打印并非零退出。

已收官书的返修姿势（与规则「禁重 merge」一致）：**单元与交付 md 同一趟同行替换**，
不重拼、不动契约/清单；单元正文变了 → 另跑 `tools/resync_src_hash.py` 重同步 src_hash。

用法：
    python tools/tighten_loose_math.py <文件或目录>... [--commit] [--show N]
目录 = 递归收 `*.md`。默认 dry-run（打印每个文件的改动处数与样例），`--commit` 才写盘。
退出码：有机械档残留（= 反转没吃干净，属本工具缺陷）或存在语义档待人工 → 1。
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import lib.boot as boot  # noqa: E402
boot.setup()

import check_unit_quality as cq  # noqa: E402

# 🔴 落盘前的**独立**不变量（不复用修法器逻辑，故能查出修法器自己的越界）：
# 本工具只允许删空白，且每段被删空白的**任一侧**必须是定界/结构字符
# （`{` `[` `(` `}` `]` `)` `|` `_` `^`）。两侧都是记号的空白（`\in T`、`a b`、`1 0 6`）
# 一律不许动——`\inT` 改解析、`106` 把 OCR 漏位/漏小数点的错值焊死。
# `|` 在列：`\Big |`→`\Big|` 属定界符档（`\bigl/\Bigl/…` 与界符之间不留空格）。
# 🔴 `left == "\\"` 单独拒：数学模式里孤立 `\ ` 是**可打印空格命令**（array 空行写作
# `{ \ }`），右邻是 `}` 也照删的话 `{ \ }`→`{\}` 就成了 `\}` 字面闭括号——
# 括号仍配平、KaTeX 直接炸（随机过程 ch7 0024b 实测，故守卫与修法器各挡一道）。
_SAFE_R = "{[()}])_^|"
_SAFE_L = "{[(}])_^|"


def only_safe_whitespace_deletions(a, b):
    """b 由 a **只删空白**得到、且每段被删空白邻侧合规 → True；否则 False。"""
    i = j = 0
    while i < len(a) and j < len(b):
        if a[i] == b[j]:
            i += 1
            j += 1
            continue
        if not a[i].isspace():
            return False                       # 非空白的增删
        k = i
        while k < len(a) and a[k].isspace():
            k += 1
        left = a[i - 1] if i else ""
        right = a[k] if k < len(a) else ""
        if left == "\\":
            return False                       # `\ ` 是内容（转义空格），不是摊开
        if not (right in _SAFE_R or left in _SAFE_L):
            return False
        i = k
    return a[i:].strip() == "" and b[j:].strip() == ""


def audit(before, after):
    """整文件级机械证明 → 问题列表（空 = 通过）。"""
    if len(before) != len(after):
        return ["行数变了"]
    probs = []
    if "".join(before).count("$") != "".join(after).count("$"):
        probs.append("`$` 总数变了")
    nb = sum(1 for l in before if l.strip() == "---")
    na = sum(1 for l in after if l.strip() == "---")
    if nb != na:
        probs.append("`---` 行数变了 %d→%d" % (nb, na))
    for i, (a, b) in enumerate(zip(before, after), start=1):
        if a == b:
            continue
        if a.startswith("<!--") or b.startswith("<!--"):
            probs.append("L%d 首行 marker 被改" % i)
        elif re.sub(r"\s", "", a) != re.sub(r"\s", "", b):
            probs.append("L%d 非纯删空白的改动" % i)
        elif not only_safe_whitespace_deletions(a, b):
            probs.append("L%d 删了括号/上下标之外的空白" % i)
        if len(probs) >= 5:
            break
    return probs


def md_files(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            for root, _dirs, names in os.walk(p):
                out += [os.path.join(root, n) for n in sorted(names) if n.endswith(".md")]
        elif p.endswith(".md"):
            out.append(p)
        else:
            raise SystemExit("[tighten_loose_math] 只接 .md 文件或含 .md 的目录：%s" % p)
    return out


def tighten_file(path, commit, show):
    with open(path, encoding="utf-8", newline="") as f:
        raw = f.read()
    marker = raw.split("\n", 1)[0]
    new, changed, mech_left, sem_left = cq.tighten_math_text(raw)
    if marker.startswith("<!--") and new.split("\n", 1)[0] != marker:
        # 结构性首行（单元 marker）必须逐字不动——它与本侧 manifest 记录逐字对账。
        raise SystemExit("[tighten_loose_math] 🔴 首行 marker 被改动，拒绝写盘：%s" % path)
    probs = audit(raw.split("\n"), new.split("\n"))
    if probs:
        print("!! %s：机械证明不过，拒绝写盘 %s" % (path, probs))
        return changed, mech_left, sem_left, False, True
    if mech_left:
        print("!! %s：机械档反转后仍剩 %d 处（本工具缺陷，不落盘）" % (path, mech_left))
        return changed, mech_left, sem_left, False, True
    if commit and new != raw:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(new)
    if show:
        old_lines, new_lines = raw.split("\n"), new.split("\n")
        shown = 0
        for i, (a, b) in enumerate(zip(old_lines, new_lines), start=1):
            if a != b and shown < show:
                print("   L%-5d - %s" % (i, a.strip()[:110]))
                print("           + %s" % b.strip()[:110])
                shown += 1
    return changed, mech_left, sem_left, (commit and new != raw), False


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tighten_loose_math.py")
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--commit", action="store_true", help="写盘（默认 dry-run）")
    ap.add_argument("--show", type=int, default=0, help="每个文件打印前 N 条 before/after")
    a = ap.parse_args(argv)
    files = md_files(a.paths)
    if not files:
        print("[tighten_loose_math] 没有 .md 可处理")
        return 0
    tot_ch = tot_mech = tot_sem = n_written = n_refused = 0
    sem_spots = []
    for p in files:
        changed, mech, sem, wrote, refused = tighten_file(p, a.commit, a.show)
        tot_ch += changed
        tot_mech += mech
        tot_sem += sem
        n_written += 1 if wrote else 0
        n_refused += 1 if refused else 0
        if sem:
            sem_spots.append(p)
        if changed or sem:
            print("%-70s 改 %4d 处%s%s"
                  % (os.path.basename(p)[:68], changed,
                     " 已写盘" if wrote else "",
                     "  语义档 %d 处待人工" % sem if sem else ""))
    print("\n[tighten_loose_math] %s：%d 文件 / 改动 %d 处 / 写盘 %d 文件；"
          "机械档残留 %d（须为 0）；拒绝落盘 %d 文件（须为 0）；"
          "语义档 %d 处（须人工读印面重写）"
          % ("已提交" if a.commit else "dry-run", len(files), tot_ch, n_written,
             tot_mech, n_refused, tot_sem))
    for p in sem_spots[:10]:
        print("   语义档：%s" % p)
    return 1 if (tot_mech or tot_sem or n_refused) else 0


if __name__ == "__main__":
    sys.exit(main())
