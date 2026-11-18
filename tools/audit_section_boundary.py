#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""audit_section_boundary.py — S 层判据的只读全书审计 CLI。

对一本书的全部（或指定）章节跑 ``lib/section_boundary`` 的边界错位检测，
按章 / 语种列出 finding。**只读**：不修改任何交付 md、manifest 或契约。

用法
----
  python tools/audit_section_boundary.py <extract_dir>
  python tools/audit_section_boundary.py <extract_dir> --book-dir <book_dir>
  python tools/audit_section_boundary.py <extract_dir> --ch 8 13 --lang en
  python tools/audit_section_boundary.py <extract_dir> --json [out.json]

退出码：0 = 无 finding；1 = 有 finding（WARN 级，不代表 verify 失败）；
2 = 参数 / 读取错误。
"""
import argparse
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)
if SKILL_ROOT not in sys.path:
    sys.path.insert(0, SKILL_ROOT)

import lib.boot as _boot  # noqa: E402
_boot.setup()

from lib.section_boundary import scan_chapter  # noqa: E402

_CH_RE = re.compile(r'^ch(\d+)\.json$')
_APP_RE = re.compile(r'^appendix([A-Za-z])\.json$', re.I)


def _default_book_dir(extract_dir):
    e = os.path.normpath(os.path.abspath(extract_dir))
    if os.path.basename(e).lower() == '_extract':
        return os.path.dirname(e)
    return os.path.dirname(e)


def _discover_chapters(extract_dir):
    """章号/字母来自 book_structure 契约文件名（chN.json / appendixX.json）。"""
    d = os.path.join(extract_dir, 'book_structure')
    if not os.path.isdir(d):
        return []
    out = []
    for name in os.listdir(d):
        m = _CH_RE.match(name)
        if m:
            out.append(int(m.group(1)))
            continue
        m = _APP_RE.match(name)
        if m:
            out.append(m.group(1).upper())
    out.sort(key=lambda c: (0, c, '') if isinstance(c, int) else (1, 0, str(c)))
    return out


def _label(ch):
    return ('Chapter %s' % ch) if isinstance(ch, int) else ('Appendix %s' % ch)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='S 层章节边界内容错位只读审计（WARN，不阻断 verify）')
    ap.add_argument('extract_dir', help='书的 _extract 目录')
    ap.add_argument('--book-dir', default=None,
                    help='交付 md 所在目录（默认 = _extract 的父目录）')
    ap.add_argument('--ch', nargs='+', default=None,
                    help='只审计这些章（数字；附录用字母，如 A）')
    ap.add_argument('--lang', choices=('en', 'cn'), default=None,
                    help='只审计该语言组（默认中英各跑一遍）')
    ap.add_argument('--json', nargs='?', const='', default=None,
                    help='把结果写成 JSON（省略路径时写到 <extract>/section_boundary_audit.json）')
    ap.add_argument('--max-detail', type=int, default=300,
                    help='每条 finding 打印的 detail 字符数（默认 300）')
    args = ap.parse_args(argv)

    ext = os.path.abspath(args.extract_dir)
    book = os.path.abspath(args.book_dir or _default_book_dir(ext))
    if not os.path.isdir(book):
        print('ERROR: book dir not found: %s' % book, file=sys.stderr)
        return 2

    chapters = args.ch if args.ch else _discover_chapters(ext)
    if not chapters:
        print('ERROR: no chapter contracts found under %s' %
              os.path.join(ext, 'book_structure'), file=sys.stderr)
        return 2

    # 统一章号类型：纯数字 -> int，其余按字母（大写）
    norm_ch = []
    for c in chapters:
        s = str(c).strip()
        norm_ch.append(int(s) if s.isdigit() else s.upper())

    results = []
    total = 0
    for ch in norm_ch:
        try:
            rows = scan_chapter(book, ext, ch, lang=args.lang)
        except Exception as exc:  # 单章失败不拖垮全书审计，但必须显式报出
            print('ERROR: %s: %r' % (_label(ch), exc), file=sys.stderr)
            return 2
        for row in rows:
            n = len(row['findings'])
            if n:
                total += n
            results.append(row)

    for row in results:
        if not row['findings']:
            continue
        print('\n== %s [%s]  files=%d  findings=%d  page_geometry=%s'
              % (_label(row['chapter']), row['lang'] or '?', len(row['files']),
                 len(row['findings']), 'yes' if row['stats'].get('page_geometry') else 'no'))
        for f in row['findings']:
            loc = f.get('file') or '?'
            ln = f.get('file_line') or f.get('line') or 0
            print('  [%s] §%s (%s:%s) %s'
                  % (f.get('severity') or '?', f.get('section') or '?', loc, ln,
                     ','.join(f.get('kinds') or [])))
            detail = (f.get('detail') or '')[:max(0, args.max_detail)]
            if detail:
                print('      %s' % detail)

    print('\n== TOTAL: %d finding(s) in %d chapter/language group(s)'
          % (total, len(results)))
    if not total:
        print('   no section-boundary misplacement detected.')

    if args.json is not None:
        path = args.json or os.path.join(ext, 'section_boundary_audit.json')
        payload = {
            'extract_dir': ext,
            'book_dir': book,
            'lang': args.lang,
            'total': total,
            'results': results,
        }
        try:
            with io.open(path, 'w', encoding='utf-8') as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=1, sort_keys=True)
        except OSError as exc:
            print('ERROR: cannot write %s: %r' % (path, exc), file=sys.stderr)
            return 2
        print('   JSON: %s' % path)

    return 1 if total else 0


if __name__ == '__main__':
    sys.exit(main())
