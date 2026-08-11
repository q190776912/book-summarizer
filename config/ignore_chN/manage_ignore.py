#!/usr/bin/env python3
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

r"""
Ignore list manager for book-summarizer skill.

Usage:
    python manage_ignore.py --add <keys> --chapter <N> --extract <dir>
    python manage_ignore.py --remove <keys> --chapter <N> --extract <dir>
    python manage_ignore.py --list --chapter <N> --extract <dir>
    python manage_ignore.py --list-all --extract <dir>

Examples:
    python manage_ignore.py --add "11.6-2,11.7-5" --chapter 11 --extract D:\study\book\...\ _extract
    python manage_ignore.py --remove "11.6-2" --chapter 11 --extract ...
    python manage_ignore.py --list --chapter 11 --extract ...
    python manage_ignore.py --list-all --extract ...
"""
import sys
import os
import json

# Add skill directory to path to import verify_chapter functions

from verify.script.key_parse import normkey


def load_ignore_dict(path):
    """Load ignore file as dict {key: reason}. Returns empty dict if missing/invalid."""
    if not path or not os.path.exists(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if isinstance(data, dict):
        return {normkey(str(k)): v for k, v in data.items()}
    elif isinstance(data, list):
        return {normkey(str(k)): '' for k in data}
    else:
        return {}


def save_ignore(path, ignore_dict):
    """Save ignore dict (key -> reason) to JSON file."""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(ignore_dict, f, ensure_ascii=False, indent=2)


def load_ignore_raw(path):
    """Load ignore file as dict (key -> reason) without normalizing keys."""
    if not os.path.exists(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data
    elif isinstance(data, list):
        return {k: '' for k in data}
    return {}


def add_keys(ext, ch, keys):
    """Add keys to ignore_ch{N}.json."""
    ipath = os.path.join(ext, f'ignore_ch{ch}.json')
    ignore = load_ignore_dict(ipath)
    added = []
    for k in keys:
        k = normkey(k.strip())
        if k and k not in ignore:
            ignore[k] = 'added via manage_ignore.py'
            added.append(k)
    if added:
        save_ignore(ipath, ignore)
        print(f"[ignore_ch{ch}.json] Added {len(added)} key(s): {', '.join(added)}")
    else:
        print(f"[ignore_ch{ch}.json] No new keys added (all already present)")
    return added


def remove_keys(ext, ch, keys):
    """Remove keys from ignore_ch{N}.json."""
    ipath = os.path.join(ext, f'ignore_ch{ch}.json')
    if not os.path.exists(ipath):
        print(f"[ignore_ch{ch}.json] File does not exist")
        return []
    ignore = load_ignore_dict(ipath)
    removed = []
    for k in keys:
        k = normkey(k.strip())
        if k in ignore:
            del ignore[k]
            removed.append(k)
    if removed:
        save_ignore(ipath, ignore)
        print(f"[ignore_ch{ch}.json] Removed {len(removed)} key(s): {', '.join(removed)}")
    else:
        print(f"[ignore_ch{ch}.json] No matching keys to remove")
    return removed


def list_keys(ext, ch):
    """List all keys in ignore_ch{N}.json."""
    ipath = os.path.join(ext, f'ignore_ch{ch}.json')
    if not os.path.exists(ipath):
        print(f"[ignore_ch{ch}.json] File does not exist (empty)")
        return []
    ignore = load_ignore_dict(ipath)
    if ignore:
        print(f"[ignore_ch{ch}.json] {len(ignore)} key(s):")
        for k in sorted(ignore.keys()):
            reason = ignore[k]
            if reason:
                print(f"  {k}  # {reason}")
            else:
                print(f"  {k}")
    else:
        print(f"[ignore_ch{ch}.json] Empty")
    return list(ignore.keys())


def list_all(ext):
    """List all ignore_ch{N}.json files in extract dir."""
    for fname in sorted(os.listdir(ext)):
        if fname.startswith('ignore_ch') and fname.endswith('.json'):
            ch = fname[len('ignore_ch'):-len('.json')]
            list_keys(ext, ch)
            print()


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Manage per-chapter ignore lists (ignore_ch{N}.json)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python manage_ignore.py --add "11.6-2,11.7-5" --chapter 11 --extract /path/to/_extract
  python manage_ignore.py --remove "11.6-2" --chapter 11 --extract /path/to/_extract
  python manage_ignore.py --list --chapter 11 --extract /path/to/_extract
  python manage_ignore.py --list-all --extract /path/to/_extract
"""
    )
    parser.add_argument('--extract', required=True, help='Path to book _extract directory')
    parser.add_argument('--chapter', type=int, help='Chapter number (required for add/remove/list)')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--add', help='Comma-separated keys to add to ignore list')
    group.add_argument('--remove', help='Comma-separated keys to remove from ignore list')
    group.add_argument('--list', action='store_true', help='List keys for given chapter')
    group.add_argument('--list-all', action='store_true', help='List all ignore files')

    args = parser.parse_args()

    if args.list_all:
        list_all(args.extract)
        return

    if args.chapter is None:
        parser.error('--chapter is required for add/remove/list')

    if args.add:
        keys = [k.strip() for k in args.add.split(',') if k.strip()]
        add_keys(args.extract, args.chapter, keys)
    elif args.remove:
        keys = [k.strip() for k in args.remove.split(',') if k.strip()]
        remove_keys(args.extract, args.chapter, keys)
    elif args.list:
        list_keys(args.extract, args.chapter)


if __name__ == '__main__':
    main()