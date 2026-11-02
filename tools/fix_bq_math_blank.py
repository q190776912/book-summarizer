"""tools/fix_bq_math_blank.py — 把引用块 display math 的「围栏内空 `>` 行」搬到围栏外（删掉）。

形制（甲/乙）：
    甲（正确）  `> $$` / 公式 / `> $$` / `>` / 散文        空行在围栏**外**
    乙（本工具修）`> $$` / 公式 / `>` / `> $$` / 散文        空行在围栏**内**

🔴 为什么必须修（不是排版洁癖）：CommonMark 里块引用内的空行**结束当前块** ⇒ `$$` 围栏
被劈成两段，尾段 `> $$` 与后面的散文并进同一段。cmark-gfm（GitHub 自己的解析器）实测：
    甲 → `<p>$$ … $$</p><p>散文</p>`
    乙 → `<p>$$ … 式</p><p>$$\\n散文</p>`     ← 数学块不闭合，**散文被吞进数学段**
判据（「哪一行算违规」）与删除决策（「哪一条可以安全删」）都只在
`verify/format_verify/script/format_verify.py` 里定义一份——`bq_math_inner_blanks()` 点名违规行，
`bq_deletable_inner_blanks()` 给出可删集合 + 拒删清单；本工具直接 import 后者，不复制逻辑。
M 层 auto-fix（`verify --fix` 走的 `fix_math_blockquote_leak.fix_displaymath_gt`）读的是**同一个**
函数 ⇒ 两条修复链对同一形态只会得到同一种处置。

修法为什么是**删**而不是**搬**：全架甲形 52214 处里 100% 在开门围栏**前**已有一条空 `>` 行
（单元门控 F7c 本来就强制要求它），乙只是多了一条落在围栏内 ⇒ 围栏外那条已在位，
把内那条搬出去只会造出两条连续空 `>` 行（撞 N 层 `check_excessive_bq_empty_lines`）。
所以正确动作 = 删掉围栏内那条。

安全边界（任一不满足 = 该块不动并计一条 REFUSE，绝不猜）：
 ① 只删判据点名的行（严格位于配对成功的 `> $$ … > $$` 之间的空 `>` 行），别的行一个字节都不动；
 ② 若某块内**第一条与最后一条**被点名空行之外两侧都还有内容（= 那条空行真的在分隔两段内容），
    删它会并块 ⇒ 拒（该判定在 `bq_deletable_inner_blanks` 里，闸与工具同读；2026-11-01 全架
    普查该形态 0 处，出现即须人工分诊）；
 ③ 换行风格与 BOM 按文件**自身**守恒，不做全书翻转；
 ④ 单元首行 `<!-- book-summarizer … unit: … -->` 标记不参与（它不可能在围栏内，
    但整文件重写类工具必须验一遍：改后首行逐字节不变）；
 ⑤ 写盘后逐字节复核「除被点名的空行外，其余行逐字节相同」，不等即回滚提示（备份仍在）；
 ⑥ 幂等：复跑应为 0 处；
 ⑦ 目录递归**跳过快照面**：`_bak*` / `_pre_*` 目录段、以 `_` 开头的文件名（探针/临时件）与 `.bak` 件
    ——里面躺的正是改前的乙形件，第二趟若一起「修」掉就抹掉了回滚面与证据（2026-11-02 p1190 实测形态）。

落账：每个**书根**一份 `<book>/_extract/_bq_math_blank_fix.jsonl`，每次 `--commit` 按文件追加
（相对书根的路径、层（units/units-translate/交付）、删掉的行数、涉及围栏、备份路径）。

用法：
    python tools/fix_bq_math_blank.py <文件或目录> [...] [--commit] [--backup-dir DIR]
目录**递归**收 `.md`；默认 dry-run（只打印将要删的行）。退出码：0 = 无可改之处（或 commit 成功
且无 REFUSE）；1 = dry-run 有可改之处 / 有 REFUSE / 复核不等。

🔴 改完**源单元**（units）之后必须重同步译侧快照：`python tools/resync_src_hash.py <extract> --commit`
（`src_hash` 是源正文的裸 sha1，删一行空 `>` 行就会让它过时 ⇒ parity 判据 6 报 FAIL）。
"""
import argparse
import io
import json
import os
import re
import shutil
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))
import lib.boot as boot  # noqa: E402
boot.setup()

sys.path.insert(0, os.path.join(os.path.dirname(_HERE),
                                "verify", "format_verify", "script"))
from format_verify import bq_deletable_inner_blanks  # noqa: E402  （判据+删除决策同一份 SSOT）

LEDGER = "_bq_math_blank_fix.jsonl"
BAK_DIR = "_bak_fix_bq_math_blank"
BAK_DIR_PREFIX = "_bak"
_UNIT_MARK_RE = re.compile(r"^<!-- book-summarizer (?:DRAFT|DONE) unit:")


def _is_backup_path(path):
    """路径含**快照段**（`_bak*` / `_pre_*`）或文件名以 `_` 开头 = 证据/回滚资产，绝不进修复面。

    为什么必须在 collect 里挡：按书根递归喂目录是本工具的标准用法，而快照目录里躺的正是
    **改前**的乙形件——第二趟会把「上一次 commit 的备份」也修掉，等于亲手抹掉回滚面。
    2026-11-02 全架普查（p1190 B 档）实测的非 `_bak` 快照形态有三种：`_bak_*`、
    `_pre_fix_20261022/`（手工改前快照目录）、`_probe_ch4.md` / `_gate_ordinal_tmp_*.md`
    （探针与临时件，文件名以 `_` 开头）⇒ 三种都按「不参与修复面」处理。
    """
    parts = os.path.abspath(path).replace("\\", "/").split("/")
    return (any(p.startswith("_bak") or p.startswith("_pre_") for p in parts[:-1])
            or parts[-1].startswith("_")
            or ".bak" in parts[-1].lower())


def _rb(path):
    with io.open(path, "rb") as f:
        return f.read()


def read_file(path):
    """→ (lines, sep, bom)。sep = 该文件**自身**换行风格，bom = 是否带 BOM。"""
    raw = _rb(path)
    bom = raw.startswith(b"\xef\xbb\xbf")
    body = raw[3:] if bom else raw
    sep = "\r\n" if (b"\r\n" in body and body.count(b"\r\n") * 2 >= body.count(b"\n")) else "\n"
    text = body.decode("utf-8").replace(sep, "\n")
    return text.split("\n"), sep, bom


def write_file(path, lines, sep, bom):
    text = sep.join(lines)
    data = text.encode("utf-8")
    if bom:
        data = b"\xef\xbb\xbf" + data
    with io.open(path, "wb") as f:
        f.write(data)
    return _rb(path) == data


def plan_file(path):
    """→ (planned 删除下标集合, refuses, blocks_hit, sample_lines)。

    refuses：``[(围栏开行号, 说明)]``——该块**不动**，交人工分诊（判据 ②）。

    🔴 「哪条空行能安全删」不在本文件判：`format_verify.bq_deletable_inner_blanks` 是唯一一份，
    M 层 auto-fix（`verify --fix`）读的也是它。两份决策迟早分叉——分叉的后果是闸照判据整条删、
    工具却拒删，同一形态在两条链上得到相反处置。
    """
    lines, _sep, _bom = read_file(path)
    drop_ln, refuses, blocks = bq_deletable_inner_blanks(lines)
    if not drop_ln and not refuses:
        return set(), [], 0, lines
    return {d - 1 for d in drop_ln}, refuses, blocks, lines


def owner_book(path):
    """最近的、含 `_extract` 子目录的祖先 = 书根；找不到 → None。"""
    d = os.path.dirname(os.path.abspath(path))
    for _ in range(8):
        if os.path.isdir(os.path.join(d, "_extract")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent
    return None


def layer_of(path, book):
    rel = os.path.relpath(path, book).replace("\\", "/")
    for name in ("units-translate", "units"):
        if ("/" + name + "/") in ("/" + rel):
            return name
    return "交付"


def collect(args):
    out = []
    for a in args:
        p = os.path.abspath(a)
        if os.path.isfile(p) and p.endswith(".md"):
            if _is_backup_path(p):
                print("!! 跳过备份件（回滚资产，一个字节都不许动）：%s" % a)
            else:
                out.append(p)
        elif os.path.isdir(p):
            for base, dirs, files in os.walk(p):
                dirs[:] = [d for d in sorted(dirs)
                           if not (d.startswith(BAK_DIR_PREFIX) or d.startswith("_pre_"))]
                for f in sorted(files):
                    if f.endswith(".md") and not _is_backup_path(os.path.join(base, f)):
                        out.append(os.path.join(base, f))
        else:
            print("!! 跳过（不是 .md 也不是目录）：%s" % a)
    return sorted(set(out))


def main():
    ap = argparse.ArgumentParser(description="删除引用块 display math 的围栏内空 `>` 行")
    ap.add_argument("paths", nargs="+", help="md 文件或目录（目录递归）")
    ap.add_argument("--commit", action="store_true", help="写盘（默认 dry-run）")
    ap.add_argument("--backup-dir", default=None)
    ap.add_argument("--show", type=int, default=6, help="dry-run 每文件最多打印几处")
    a = ap.parse_args()

    files = collect(a.paths)
    n_files = n_blocks = n_lines = n_refuse = n_write = 0
    for p in files:
        drop, refuses, blocks, lines = plan_file(p)
        n_refuse += len(refuses)
        for ln, why in refuses:
            print("REFUSE %s L%d：%s" % (p, ln, why))
        if not drop:
            continue
        n_files += 1
        n_blocks += blocks
        n_lines += len(drop)
        book = owner_book(p)
        rel = os.path.relpath(p, book) if book else os.path.basename(p)
        print("%s %s ｜ %s ｜ %d 个围栏内空行（涉及 %d 块）"
              % ("删" if a.commit else "可删", book and os.path.basename(book) or "?",
                 rel.replace("\\", "/"), len(drop), blocks))
        shown = 0
        for k in sorted(drop):
            if shown >= a.show:
                print("      …（共 %d 行）" % len(drop))
                break
            print("      - L%-5d %r" % (k + 1, lines[k]))
            shown += 1
        if not a.commit:
            continue
        # ④ 首行标记守恒 + ③ 换行/BOM 守恒 + ⑤ 写后复核
        lines2, sep, bom = read_file(p)
        new = [l for i, l in enumerate(lines2) if i not in drop]
        if _UNIT_MARK_RE.match(lines2[0]) and new[0] != lines2[0]:
            print("!! 首行标记被移动，跳过：%s" % p)
            n_refuse += 1
            continue
        bak = None
        if book:
            broot = a.backup_dir or os.path.join(book, "_extract", BAK_DIR)
            stamp = time.strftime("%Y%m%dT%H%M%S")
            bak = os.path.join(broot, stamp, rel)
            os.makedirs(os.path.dirname(bak), exist_ok=True)
            shutil.copy2(p, bak)
        if not write_file(p, new, sep, bom):
            print("!! 写后复核失败：%s（备份 %s）" % (p, bak))
            return 1
        check, _s, _b = read_file(p)
        if new != check:
            print("!! 写后逐行复核不等：%s（备份 %s）" % (p, bak))
            return 1
        n_write += 1
        if book:
            rec = {"ts": time.strftime("%Y%m%dT%H%M%S"), "book": book,
                   "md": rel.replace("\\", "/"), "layer": layer_of(p, book),
                   "removed_lines": len(drop), "blocks": blocks,
                   "lines": [k + 1 for k in sorted(drop)], "backup": bak}
            with io.open(os.path.join(book, "_extract", LEDGER), "a",
                         encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print("\n== 文件 %d ｜ 围栏 %d ｜ 删行 %d ｜ REFUSE %d ｜ %s"
          % (n_files, n_blocks, n_lines, n_refuse,
             ("已写 %d 件" % n_write) if a.commit else "dry-run（未写）"))
    if not a.commit:
        return 1 if (n_lines or n_refuse) else 0
    return 0 if n_refuse == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
