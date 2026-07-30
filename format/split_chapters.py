r"""将一个过大的章总结文件，按「节」(N.M 级编号) 拆分成每节一个独立总结文件。

用户规则（2026-07-28）：
  - 阈值：中文总结或英文总结「只要有一个」字符数超过 30000，就把两者都拆分。
  - 拆分粒度：「节」= 标题首部编号为 N.M（恰好一个小数点）的标题，
    不论其 markdown 级数（## / ### 都算）也不论是否带 § 前缀。
    子节 N.M.P（两个小数点）留在父节文件内，不单独成文件。
  - 命名：中文 `第{N}章{M}{名称}.md`；英文 `Chapter{N}_{M}{名称}.md`
    （名称取自标题编号之后的文本，剔除 Windows 非法字符与空白）。
  - 章开头的引言/导语（第一个节标题之前的内容）并入第 1 节文件。
  - 幂等：重复运行会跳过已拆分的节文件（第N章M.xxx / ChapterN_M.xxx），不会二次拆分；对已合并源文件则确定性覆盖已生成的节文件。
  - **默认在拆分成功后删除源合并文件**（节文件已 100% 覆盖其内容，无需保留）；
    加 `--keep` 可保留源文件。

用法：
    python split_chapters.py <book_dir> [--threshold 30000] [--dry-run] [--keep]

<book_dir> 下同时扫描 `第*章*.md` 与 `Chapter*.md`，按章号配对；
若某章需拆分，则中文与英文（若存在）都会按各自标题拆分。
"""
import os
import re
import sys
import argparse

DEFAULT_THRESHOLD = 30000

# 节拆分标题：可选 § 前缀，后接 N.M（恰好一个小数点），其后必须是空白或行尾
# （用 lookahead 防止把 N.M.P 的 "N.M" 误判为节）。
SPLIT_RE = re.compile(r'^(#{1,6})\s*§?\s*(\d+)\.(\d+)(?=\s|$)')
H1_RE = re.compile(r'^#\s+')


def chapter_num_from_filename(fn):
    """返回 (章号 int, 语言 'zh'/'en')；无法识别或属已拆分的节文件则返回 (None, None)。"""
    m = re.match(r'^第(\d+)章', fn)
    if m:
        rest = fn[m.end():]
        if re.match(r'^\d+\.', rest):      # 已拆分的节文件：第N章M.xxx（章后紧跟 数字.），跳过
            return None, None
        return int(m.group(1)), 'zh'
    m = re.match(r'^Chapter(\d+)', fn)
    if m:
        rest = fn[m.end():]
        if re.match(r'^_\d+\.', rest):     # 已拆分的英文节文件：ChapterN_M.xxx，跳过
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
    if len(name) > maxlen:
        name = name[:maxlen]
    return name


def split_one_file(path, threshold, num, lang, dry_run=False):
    """拆分单个章节文件。返回生成的文件路径列表（dry_run 时返回空列表但打印计划）。"""
    text = open(path, encoding='utf-8').read()
    if len(text) <= threshold:
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
        if m and int(m.group(2)) == num:
            key = f"{m.group(2)}.{m.group(3)}"
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
        else:
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
    ap.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD, help="字符数阈值，默认 30000")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划，不写文件")
    ap.add_argument("--keep", action="store_true", help="拆分后保留源合并文件（默认删除）")
    args = ap.parse_args()

    book_dir = args.book_dir
    if not os.path.isdir(book_dir):
        print(f"错误：目录不存在 {book_dir}", file=sys.stderr)
        sys.exit(2)

    chinese, english = {}, {}
    for fn in os.listdir(book_dir):
        if not fn.endswith('.md'):
            continue
        num, lang = chapter_num_from_filename(fn)
        if num is None:
            continue
        (chinese if lang == 'zh' else english)[num] = os.path.join(book_dir, fn)

    all_nums = sorted(set(chinese) | set(english))
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
        if zh_len > args.threshold or en_len > args.threshold:
            any_split = True
            print(f"章 {num}: 中={zh_len} 英={en_len} -> 超过阈值，执行拆分")
            if zh:
                w = split_one_file(zh, args.threshold, num, 'zh', args.dry_run)
                if w and not args.dry_run and not args.keep:
                    os.remove(zh)
                    print(f"  [已删除源文件] {os.path.basename(zh)}")
            if en:
                w = split_one_file(en, args.threshold, num, 'en', args.dry_run)
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
