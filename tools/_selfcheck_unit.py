#!/usr/bin/env python3
import os
import sys
import json
import re
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[2])
for _p in (_ROOT, os.path.join(_ROOT, "lib"),
           os.path.join(_ROOT, "flows", "write-source", "script")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

"""单元质量自检：对单个单元文件跑 check_unit_quality.check_body 并打印问题。"""
from check_unit_quality import check_body

def main():
    unit_path = sys.argv[1]
    with open(unit_path, encoding="utf-8") as f:
        raw = f.read()
    m = re.match(r"<!-- book-summarizer (DRAFT|DONE) unit: id=(\S+) type=(\S+) key=(.*?) name=(.*?) -->", raw)
    if not m:
        print("BAD first line")
        return 1
    body = raw[m.end():].lstrip("\r\n")
    ch_dir = os.path.dirname(unit_path)
    mpath = os.path.join(ch_dir, "manifest.json")
    fname = os.path.basename(unit_path)
    exp_tags = exp_imgs = content = None
    name = m.group(5)
    utype = m.group(3)
    if os.path.exists(mpath):
        man = json.load(open(mpath, encoding="utf-8"))
        for u in man.get("units", []):
            if u.get("file") == fname:
                exp_tags = u.get("tags")
                exp_imgs = u.get("images")
                content = u.get("content")
                name = u.get("name") or name
                utype = u.get("type") or utype
                break
    ok, probs = check_body(
        utype, name, body,
        expected_tags=exp_tags if exp_tags is not None else None,
        expected_images=exp_imgs if exp_imgs is not None else None,
        content_blocks=content,
    )
    print("MARK", m.group(1))
    for p in probs:
        print("PROB", p)
    good = ok and m.group(1) == "DONE"
    print("RESULT", "OK" if good else "FAIL")
    return 0 if good else 1

if __name__ == "__main__":
    sys.exit(main())
