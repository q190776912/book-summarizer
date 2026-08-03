r"""将一个过大的章总结文件，按「节」拆分成每节一个独立总结文件。

用户规则（2026-07-28，2026-08-03 修订）：拆分粒度 = 原书小节标题的格式，
按标题首部编号识别，支持两种书中实际格式：
  1) 节标题式（`§N`，gm 风格）：标题以 § 前缀 + 单个整数开头
     （如 `## §2. Derived Categories are Triangulated`，节内条目从 1 起号，
     如 Gelfand–Manin《Methods of Homological Algebra》）。
  2) `N.M` 编号式（Vakil 风格）：标题首部编号为 N.M（恰好一个小数点），
     不论其 markdown 级数（## / ### 都算）也不论是否带 § 前缀。
     子节 N.M.P（两个小数点）留在父节文件内，不单独成文件。
两种格式可共存于同一文件，按各自匹配到的顺序拆分。
  - 阈值与配对：中文总结或英文总结「只要有一个」字符数超过 60000，就把**两者都**拆分
    （即使另一个未超阈值也要拆，保证同一章的中英文保持一致的分拆状态）。
  - 命名：中文 `第{N}章{M}{名称}.md`；英文 `Chapter{N}_{M}{名称}.md`
    （{M} = 节号——§N 式即 N，N.M 式即 N.M；名称取自标题编号之后的文本，
    剔除 Windows 非法字符与空白）。
  - 章开头的引言/导语（第一个节标题之前的内容）并入第 1 节文件。
  - 幂等：重复运行会跳过已拆分的节文件（第N章M.xxx / ChapterN_M.xxx），不会二次拆分；对已合并源文件则确定性覆盖已生成的节文件。
  - **默认在拆分成功后删除源合并文件**（节文件已 100% 覆盖其内容，无需保留）；
    加 `--keep` 可保留源文件。

用法：
    python split_chapters.py <book_dir> [--threshold 60000] [--dry-run] [--keep]

<book_dir> 下同时扫描 `第*章*.md` 与 `Chapter*.md`，按章号配对；
若某章任一语言超阈值，则中文与英文（若存在）都会按各自标题拆分。
"""
import os
import re
import sys
import argparse

DEFAULT_THRESHOLD = 60000

# 节拆分标题，两种书中实际格式（二选一）：
#   1) gm 风格节标题：`§N`，§ 必须存在（避免把节内条目 `### N. 标题` 误判为节），
#      节号后允许一个可选句点（`## §1. 标题`），其后必须是空白或行尾。
#   2) Vakil 风格：`N.M`（恰好一个小数点），§ 前缀可选；
#      lookahead 防止把 N.M.P 的 "N.M" 误判为节。
SPLIT_RE = re.compile(
    r'^(#{1,6})\s*'
    r'(?:§\s*(\d+)\s*\.?(?=\s|$)'
    r'|§?\s*(\d+)\.(\d+)(?=\s|$))'
)
H1_RE = re.compile(r'^#\s+')


def chapter_num_from_filename(fn):
    """返回 (章号 int, 语言 'zh'/'en')；无法识别或属已拆分的节文件则返回 (None, None)。"""
    m = re.match(r'^第(\d+)章', fn)
    if m:
        rest = fn[m.end():]
        if re.match(r'^\d+', rest):        # 已拆分的节文件：第N章M.xxx / 第N章N.xxx（章后紧跟数字），跳过
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
        name = name[:maxlen]
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

    for l in lines:
        m = SPLIT_RE.match(l)
        if m:
            sec = m.group(2)                     # gm 风格：§N 节标题（节内从 1 起号，无需核对章号）
            if sec is not None:
                key = sec
            elif m.group(3) and int(m.group(3)) == num:
                key = f"{m.group(3)}.{m.group(4)}"
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
        if current is None:
            if title is not None and l == title:
                continue             # 标题行稍后逐文件补回，这里跳过
            intro.append(l)
        else:
            buckets[current].append(l)

    written = []
    plan = []
    for k in order:
        key, sname = k
        content = []
        if title is not None:
            content.append(title)
        if k == first_key:
            content.extend(intro)
        content.extend(buckets[k])
        out = '\n'.join(content).rstrip('\n') + '\n'
        fname = f"第{num}章{key}{sname}.md" if lang == 'zh' else f"Chapter{num}_{key}{sname}.md"
        outpath = os.path.join(os.path.dirname(path), fname)
        plan.append(fname)
        if not dry_run:
            with open(outpath, 'w', encoding='utf-8') as f:
                f.write(out)
            written.append(outpath)

    verb = "将拆分(计划)" if dry_run else "已拆分"
    print(f"  [{verb}] {os.path.basename(path)} ({len(text)} 字符) -> {len(order)} 个节文件: {', '.join(plan)}")
    return written


def main():
    ap = argparse.ArgumentParser(description="按节拆分过大的章总结文件")
    ap.add_argument("book_dir", help="书籍目录（含 第*章*.md / Chapter*.md）")
    ap.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD, help="字符数阈值，默认 60000")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划，不写文件")
    ap.add_argument("--keep", action="store_true", help="拆分后保留源合并文件（默认删除）")
    args = ap.parse_args()

    book_dir = args.book_dir
    if not os.path.isdir(book_dir):
        print(f"错误：目录不存在 {book_dir}", file=sys.stderr)
        sys.exit(2)

    chinese, english = {}, {}
    sections = {}       # 章号 -> {'zh': bool, 'en': bool}：该语言是否已有节文件（曾拆分过）
    for fn in os.listdir(book_dir):
        if not fn.endswith('.md'):
            continue
        num, lang = chapter_num_from_filename(fn)
        if num is not None:
            (chinese if lang == 'zh' else english)[num] = os.path.join(book_dir, fn)
            continue
        # 节文件：第N章M...（zh）/ ChapterN_M...（en），识别其章号与语言
        m = re.match(r'^第(\d+)章\d', fn)
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
