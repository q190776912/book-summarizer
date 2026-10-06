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

r"""将一个过大的章总结文件，按「节」拆分成每节一个独立总结文件。

用户规则（2026-07-28，2026-08-03 修订）：拆分粒度 = 原书小节标题的格式，
按标题首部编号识别，支持两种书中实际格式：
  1) 节标题式（`§N` 章内节标题风格）：标题以 § 前缀 + 单个整数开头
     （如 `## §2. Derived Categories are Triangulated`，节内条目从 1 起号）。
  2) `N.M` 编号式（Vakil 风格）：标题首部编号为 N.M（恰好一个小数点），
     不论其 markdown 级数（## / ### 都算）也不论是否带 § 前缀。
     子节 N.M.P（两个小数点）留在父节文件内，不单独成文件。
  3) dash 节号式（do Carmo 风格）：标题编号为 `§N-M`（§ 必须存在），N 须等于章号。
三种格式可共存于同一文件，按各自匹配到的顺序拆分。
  - 阈值与配对：中文总结或英文总结「只要有一个」字符数超过 60000，就把**两者都**拆分
    （即使另一个未超阈值也要拆，保证同一章的中英文保持一致的分拆状态）。
  - 命名：中文 `第{N}章_{M}_{名称}.md`；英文 `Chapter{N}_{M}_{名称}.md`
    （{M} = 节号——§N 式即 N，N.M 式即 N.M，§N-M 式即 N-M；名称取自标题编号之后的文本，
    剔除 Windows 非法字符与空白。节号与名称之间也有一个下划线）。
  - 章开头的引言/导语（第一个节标题之前的内容）并入第 1 节文件。
  - 幂等：重复运行会跳过已拆分的节文件（第N章_M_... / ChapterN_M_...），不会二次拆分；对已合并源文件则确定性覆盖已生成的节文件。
  - **默认在拆分成功后删除源合并文件**（节文件已 100% 覆盖其内容，无需保留）；
    加 `--keep` 可保留源文件。

用法：
    python split_chapters.py <book_dir> [--threshold 60000] [--dry-run] [--keep]
    python split_chapters.py <book_dir> --reconcile [--dry-run]   # 只回收旧名残档（节号 + 同章重复合并稿）

<book_dir> 下同时扫描 `第*章*.md` 与 `Chapter*.md`，按章号配对；
若某章任一语言超阈值，则中文与英文（若存在）都会按各自标题拆分。
"""
import os
import re
import sys
import time
import argparse

DEFAULT_THRESHOLD = 60000

# 节拆分标题，三种书中实际格式（三选一）：
#   1) `§N` 章内节标题风格：§ 必须存在（避免把节内条目 `### N. 标题` 误判为节），
#      节号后允许一个可选句点（`## §1. 标题`），其后必须是空白或行尾。
#   2) Vakil 风格：`N.M`（恰好一个小数点），§ 前缀可选；
#      lookahead 防止把 N.M.P 的 "N.M" 误判为节。
#   3) do Carmo 风格：`§N-M`（dash 节号），§ 必须存在；首数字须等于章号，
#      lookahead 防止把子节 `§N-M.P` 误判。
SPLIT_RE = re.compile(
    r'^(#{1,6})\s*'
    r'(?:§\s*(\d+)\s*\.?(?=\s|$)'
    r'|§\s*(\d+)-(\d+)(?=\s|$)'
    r'|§?\s*(\d+)\.(\d+)(?=\s|$))'
)
# 4) 无编号具名节（Lee《Smooth Manifolds》等）：顶级节以 `## § 名称` 印出、
#    名称不以数字开头（子节为 `### § …`，不参与拆分）。原书以节名（非序号）
#    交叉引用，故无 `§N` / `N.M` 号可锚；拆分时按出现顺序赋 1..k 序数作节号，
#    仅用于文件名（正文标题原样保留 `## § 名称`，不伪造印刷序号）。
NAMED_SEC_RE = re.compile(r'^##(?!#)\s+§\s+(\D[^\n]*?)\s*$')
H1_RE = re.compile(r'^#\s+')


def chapter_num_from_filename(fn):
    """返回 (章号 int, 语言 'zh'/'en')；无法识别或属已拆分的节文件则返回 (None, None)。"""
    m = re.match(r'^第(\d+)章', fn)
    if m:
        rest = fn[m.end():]
        if re.match(r'^_?\d', rest):       # 已拆分的节文件：第N章_M...（新）/ 第N章M...（旧），跳过
            return None, None
        return int(m.group(1)), 'zh'
    m = re.match(r'^Chapter(\d+)', fn)
    if m:
        rest = fn[m.end():]
        if re.match(r'^_\d+', rest):       # 已拆分的英文节文件：ChapterN_M.xxx，跳过
            return None, None
        return int(m.group(1)), 'en'
    return None, None


def sanitize_name(name, maxlen=60):
    """生成合法、可读的文件名：
    - 去掉 § 前缀；
    - 去掉 $...$ 数学块（文件名里不能带反斜杠/$，正文标题仍保留完整 LaTeX）；
    - 去掉 Windows 非法字符 <>:"/\\|?* 及残留 $；
    - 去掉空白；长度封顶 maxlen（此时已无 LaTeX，截断安全）。
    """
    name = name.replace('§', '')
    name = re.sub(r'\$[^$]*\$', '', name)        # 行内/块级数学
    name = re.sub(r'[<>:"/\\|?*$]', '', name)    # Windows 非法字符 + 残留 $
    name = re.sub(r'\s+', '', name)
    name = name.strip()
    name = name.lstrip('.。;；:：,，')              # §N. 标题编号后残留的句点
    if len(name) > maxlen:
        cut = name[:maxlen]
        # 截断点落在括号英文段名内 → 不把尾 `)` 截丢（Koopman 实测：
        # `第5章_5.3_…(TheKoopman…Eigenfunctions).md` 生成 dangling 尾括号名）
        if cut.count("(") > cut.count(")"):
            shortened = name[:maxlen - 1]
            cut = shortened + ")" if shortened.count("(") > shortened.count(")") \
                else cut.rstrip("(")
        name = cut
    return name


def split_one_file(path, threshold, num, lang, dry_run=False, force=False):
    """拆分单个章节文件。返回生成的文件路径列表（dry_run 时返回空列表但打印计划）。

    force=True 时忽略该文件自身的字符数检查（用于章级「任一语言超标 →
    两种语言都拆」的配对规则；force=False 时若自身未超阈值则跳过）。
    """
    text = open(path, encoding='utf-8').read()
    if not force and len(text) <= threshold:
        return []

    lines = text.split('\n')

    # 定位章标题（H1），每个节文件都带上它，保证各自独立可渲染。
    title = None
    for l in lines:
        if H1_RE.match(l):
            title = l
            break

    buckets = {}          # (key, sname) -> 该节正文行（含自身节标题行）
    order = []            # 节首次出现顺序
    intro = []            # 章开头引言（第一个节之前、标题之后的内容）
    current = None
    first_key = None
    named_ctr = 0         # 无编号具名节的序数计数器（1..k）

    for l in lines:
        m = SPLIT_RE.match(l)
        if m:
            sec = m.group(2)                     # `§N` 章内节标题（节内从 1 起号，无需核对章号）
            if sec is not None:
                key = sec
            elif m.group(3) is not None:         # `§N-M` dash 式（do Carmo）
                key = f"{m.group(3)}-{m.group(4)}" if int(m.group(3)) == num else None
            elif m.group(5) and int(m.group(5)) == num:
                key = f"{m.group(5)}.{m.group(6)}"
            else:
                key = None                       # N.M 式但首数字≠章号：属于其它章的标题，跳过
            if key is not None:
                sname = sanitize_name(l[m.end():].strip())
                fk = (key, sname)
                if fk not in buckets:
                    buckets[fk] = [l]
                    order.append(fk)
                    if first_key is None:
                        first_key = fk
                else:
                    buckets[fk].append(l)   # 错序重复编号：追加到同一节
                current = fk
                continue
        nm = NAMED_SEC_RE.match(l)
        if nm:
            named_ctr += 1
            key = str(named_ctr)
            sname = sanitize_name(nm.group(1))
            fk = (key, sname)
            if fk not in buckets:
                buckets[fk] = [l]
                order.append(fk)
                if first_key is None:
                    first_key = fk
            else:
                buckets[fk].append(l)
            current = fk
            continue
        if current is None:
            if title is not None and l == title:
                continue             # 标题行稍后逐文件补回，这里跳过
            intro.append(l)
        else:
            buckets[current].append(l)

    written = []
    plan = []
    new_content = {}
    for k in order:
        key, sname = k
        content = []
        if title is not None:
            content.append(title)
        body = intro + buckets[k] if k == first_key else buckets[k]
        # H1 与首个内容行（通常是 `## §` 节标题）之间必须有一个空行，
        # 否则 verify F 层 heading-blank-above 报警（且按节重拼的合并视图
        # 里标题会被并进上一块渲染）。
        if title is not None and body and body[0].strip() != '':
            content.append('')
        if k == first_key:
            content.extend(intro)
        content.extend(buckets[k])
        out = '\n'.join(content).rstrip('\n') + '\n'
        fname = f"第{num}章_{key}_{sname}.md" if lang == 'zh' else f"Chapter{num}_{key}_{sname}.md"
        outpath = os.path.join(os.path.dirname(path), fname)
        plan.append(fname)
        if not dry_run:
            with open(outpath, 'w', encoding='utf-8') as f:
                f.write(out)
            written.append(outpath)
        new_content[fname] = out

    # 🔴 同名节旧残档回收：节文件名含标题截断，标题一改（如节名统一轮）就换名，
    # 旧名文件不会被动到 → 同一节留下两份交付物，章级重拼视图里内容/`\tag` 双份，
    # Q 层判「duplicate \tag number」硬 FAIL（Katok ch1 1.5 实测）。凡本节号下
    # 与本轮所写不同名、且内容与本轮所写逐字相同的残档，移入
    # `<book>/_extract/_superseded_split_md/<日期>/`（**移动不删**，可回滚）；
    # 内容不同者一律保留并打印告警——那意味着正文真的分叉了，须人工裁决。
    prefix = f"第{num}章_" if lang == 'zh' else f"Chapter{num}_"
    stems = {prefix + key + '_' for (key, _sn) in order}
    superseded, diverged = [], []
    book_dir = os.path.dirname(path)
    for name in sorted(os.listdir(book_dir)):
        if not name.endswith('.md') or name in plan:
            continue
        stem = next((s for s in stems if name.startswith(s)), None)
        if stem is None:
            continue                        # 不属于本轮任何节号：不动
        newf = next((f for f in plan if f.startswith(stem)), None)
        new = new_content.get(newf or '')
        if new is None:
            diverged.append(name)
            continue
        try:
            old = open(os.path.join(book_dir, name), encoding='utf-8').read()
        except OSError:
            continue
        (superseded if old == new else diverged).append(name)

    if superseded or diverged:
        arch = os.path.join(book_dir, '_extract', '_superseded_split_md',
                            time.strftime('%Y%m%d'))
        print(f"  [节号回收] {prefix}{len(superseded)} 个同节旧名残档 / "
              f"{len(diverged)} 个内容分叉（分叉不动）")
        for name in diverged:
            print(f"     ⚠ 保留（内容与本轮所写不一致，须人工裁决）: {name}")
        for name in superseded:
            print(f"     → 移入归档: {name}")
            if not dry_run:
                os.makedirs(arch, exist_ok=True)
                os.replace(os.path.join(book_dir, name), os.path.join(arch, name))

    verb = "将拆分(计划)" if dry_run else "已拆分"
    print(f"  [{verb}] {os.path.basename(path)} ({len(text)} 字符) -> {len(order)} 个节文件: {', '.join(plan)}")
    return written


SEC_FILE_RE = re.compile(r'^(?:(?:第(\d+)章)|(?:Chapter(\d+)))_(\d+(?:[.-]\d+)*)_.+\.md$')


def section_file_key(fn):
    """节文件名 -> (lang, 章号, 节号)；非节文件（合并稿/附录/补篇）返回 None。"""
    m = SEC_FILE_RE.match(fn)
    if not m:
        return None
    lang = 'zh' if m.group(1) is not None else 'en'
    return (lang, int(m.group(1) or m.group(2)), m.group(3))


def _delivery_rank(book_dir, name):
    """「当前交付」排序键（配合 `list.sort(..., reverse=True)`）。

    主键 = mtime（最新者为当前交付）；mtime 并列时（文件被复制/还原过，时间戳
    拉平）以字节数更多者为次键——更完整的一份才是真正交付，且裁决确定可回演，
    不受文件名先后这类偶然因素影响。
    """
    st = os.stat(os.path.join(book_dir, name))
    return (st.st_mtime, st.st_size)


def reconcile_section_files(book_dir, dry_run=False):
    """回收「同一节号多份交付物」的残档（标题改名后旧文件名不会被覆盖）。

    每组（同节号 ≥2 份）以「当前交付」= mtime 最新者为保留者，mtime 并列
    （复制/还原过的文件）时取字节更多者，保证裁决确定可回演；其余**逐字相同**者移入
    `<book>/_extract/_superseded_split_md/<日期>/`（移动不删，可回滚）；
    内容分叉者保留并报告——那需要人工判断哪一份才是正文。
    """
    groups = {}
    for fn in sorted(os.listdir(book_dir)):
        if not fn.endswith('.md'):
            continue
        k = section_file_key(fn)
        if k:
            groups.setdefault(k, []).append(fn)
    dup = {k: v for k, v in groups.items() if len(v) > 1}
    if not dup:
        print(f"[reconcile] 无同节号残档（共 {len(groups)} 个节文件）。")
        return 0, 0
    arch = os.path.join(book_dir, '_extract', '_superseded_split_md',
                        time.strftime('%Y%m%d'))
    moved = kept_diverged = 0
    for (lang, num, key), names in sorted(dup.items()):
        names.sort(key=lambda f: _delivery_rank(book_dir, f), reverse=True)
        cur, rest = names[0], names[1:]
        cur_text = open(os.path.join(book_dir, cur), encoding='utf-8').read()
        print(f"  {lang} ch{num} sec{key}: 保留 {cur}")
        for name in rest:
            other = open(os.path.join(book_dir, name), encoding='utf-8').read()
            if other != cur_text:
                kept_diverged += 1
                print(f"     ⚠ 分叉保留（内容与所保留者不同，须人工裁决）: {name}")
                continue
            moved += 1
            print(f"     → 同节旧名残档，移入归档: {name}")
            if not dry_run:
                os.makedirs(arch, exist_ok=True)
                os.replace(os.path.join(book_dir, name), os.path.join(arch, name))
    print(f"[reconcile] 移动 {moved} 个同节残档，保留 {kept_diverged} 个内容分叉。"
          + ("（dry-run 未写入）" if dry_run else f" 归档目录: {arch}"))
    return moved, kept_diverged


MERGED_HEAD_RE = re.compile(r'^(第\d+章|Chapter\d+|附录[0-9A-Za-z]*|Appendix[0-9A-Za-z]*'
                            r'|补篇[0-9A-Za-z]*|Supplement[0-9A-Za-z]*)(?:[_.]|$)')
TAG_RE = re.compile(r'\\tag\{([^}]*)\}')


def merged_file_head(fn):
    """合并稿文件名 -> (lang, 章前缀)；节文件 / 非章文件返回 None。

    与 verify_chapter.duplicate_merged_deliveries 同源：交付契约是每个
    (章, 语种) 只有一种形态（一份合并稿 或 一组节文件）。
    """
    if not fn.endswith('.md'):
        return None
    if SEC_FILE_RE.match(fn):
        return None
    m = MERGED_HEAD_RE.match(fn[:-3])
    if not m:
        return None
    head = m.group(1)
    return ('zh' if head[:1] in ('第', '附', '补') else 'en', head)


def _read_md(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def reconcile_merged_files(book_dir, dry_run=False):
    """回收「同一章同语种两份合并稿」的旧名残档（改名后旧文件不会被覆盖）。

    「当前交付」= mtime 最新者；mtime 并列（复制/还原过的文件）时取字节更多者，
    保证裁决确定可重演。其余者**当且仅当其 `\tag` 集合是保留者的子集**（= 同一
    交付的较早版本，不含保留者没有的编号公式）时移入
    `<book>/_extract/_superseded_split_md/<日期>/`（**移动不删**，可回滚）。
    tag 集合不是子集关系者一律保留并报告——那两份正文真的分叉，须人工裁决。
    """
    buckets = {}
    for fn in sorted(os.listdir(book_dir)):
        k = merged_file_head(fn)
        if k:
            buckets.setdefault(k, []).append(fn)
    dup = {k: v for k, v in buckets.items() if len(v) > 1}
    if not dup:
        print(f"[reconcile] 无同章重复合并稿（共 {len(buckets)} 个章-语种桶）。")
        return 0, 0
    arch = os.path.join(book_dir, '_extract', '_superseded_split_md',
                        time.strftime('%Y%m%d'))
    moved = kept = 0
    for (lang, head), names in sorted(dup.items()):
        names.sort(key=lambda f: _delivery_rank(book_dir, f), reverse=True)
        cur, rest = names[0], names[1:]
        cur_tags = set(TAG_RE.findall(_read_md(os.path.join(book_dir, cur))))
        print(f"  {lang} {head}: 保留 {cur}")
        for name in rest:
            other = set(TAG_RE.findall(_read_md(os.path.join(book_dir, name))))
            if not other <= cur_tags:
                kept += 1
                print(f"     ⚠ 分叉保留（含保留者没有的 tag: "
                      f"{sorted(other - cur_tags)[:6]}，须人工裁决）: {name}")
                continue
            moved += 1
            print(f"     → 同章旧名残档（tag 集合为其子集），移入归档: {name}")
            if not dry_run:
                os.makedirs(arch, exist_ok=True)
                os.replace(os.path.join(book_dir, name), os.path.join(arch, name))
    print(f"[reconcile] 合并稿回收：移动 {moved} 份，分叉保留 {kept} 份。"
          + ("（dry-run 未写入）" if dry_run else f" 归档目录: {arch}"))
    return moved, kept


def main():
    ap = argparse.ArgumentParser(description="按节拆分过大的章总结文件")
    ap.add_argument("book_dir", help="书籍目录（含 第*章*.md / Chapter*.md）")
    ap.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD, help="字符数阈值，默认 60000")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划，不写文件")
    ap.add_argument("--keep", action="store_true", help="拆分后保留源合并文件（默认删除）")
    ap.add_argument("--reconcile", action="store_true",
                    help="只回收旧名残档（同节号多份 / 同章同语种两份合并稿），移入 _extract/_superseded_split_md/ 不删除；有内容分叉则 exit 1，不做拆分")
    args = ap.parse_args()

    book_dir = args.book_dir
    if not os.path.isdir(book_dir):
        print(f"错误：目录不存在 {book_dir}", file=sys.stderr)
        sys.exit(2)

    if args.reconcile:
        m1, k1 = reconcile_section_files(book_dir, dry_run=args.dry_run)
        m2, k2 = reconcile_merged_files(book_dir, dry_run=args.dry_run)
        sys.exit(1 if (k1 + k2) else 0)

    chinese, english = {}, {}
    sections = {}       # 章号 -> {'zh': bool, 'en': bool}：该语言是否已有节文件（曾拆分过）
    for fn in os.listdir(book_dir):
        if not fn.endswith('.md'):
            continue
        num, lang = chapter_num_from_filename(fn)
        if num is not None:
            (chinese if lang == 'zh' else english)[num] = os.path.join(book_dir, fn)
            continue
        # 节文件：第N章_M...（zh，旧式无下划线亦兼容）/ ChapterN_M...（en），识别其章号与语言
        m = re.match(r'^第(\d+)章_?\d', fn)
        lang2 = 'zh'
        if not m:
            m = re.match(r'^Chapter(\d+)_\d', fn)
            lang2 = 'en'
        if m:
            snum = int(m.group(1))
            sections.setdefault(snum, {})[lang2] = True

    all_nums = sorted(set(chinese) | set(english) | set(sections))
    if not all_nums:
        print("未发现任何 第*章 / Chapter* 文件。")
        return

    print(f"阈值 = {args.threshold} 字符；扫描到章号: {all_nums}")
    any_split = False
    for num in all_nums:
        zh = chinese.get(num)
        en = english.get(num)
        zh_len = len(open(zh, encoding='utf-8').read()) if zh else 0
        en_len = len(open(en, encoding='utf-8').read()) if en else 0
        # 章级配对触发：任一语言超阈值 → 两种语言都拆；若该章已有任一节文件
        # （上次运行已拆过）但某语言仍留合并文件，也补拆以保持配对一致。
        over = zh_len > args.threshold or en_len > args.threshold
        pair = (zh and sections.get(num, {}).get('en')) or (en and sections.get(num, {}).get('zh'))
        if over or pair:
            any_split = True
            reason = "任一超过阈值，两种语言都拆" if over else "配对语言已拆，补拆剩余合并文件"
            print(f"章 {num}: 中={zh_len} 英={en_len} -> {reason}")
            if zh:
                w = split_one_file(zh, args.threshold, num, 'zh', args.dry_run, force=True)
                if w and not args.dry_run and not args.keep:
                    os.remove(zh)
                    print(f"  [已删除源文件] {os.path.basename(zh)}")
            if en:
                w = split_one_file(en, args.threshold, num, 'en', args.dry_run, force=True)
                if w and not args.dry_run and not args.keep:
                    os.remove(en)
                    print(f"  [已删除源文件] {os.path.basename(en)}")
        else:
            print(f"章 {num}: 中={zh_len} 英={en_len} -> 未超阈值，跳过")

    if not any_split:
        print("没有超过阈值的章节，无需拆分。")
    elif args.dry_run:
        print("\n(dry-run 完成，未写入任何文件)")
    else:
        print("\n完成。已拆分的源合并文件默认已删除（--keep 可保留）。")


if __name__ == '__main__':
    main()
