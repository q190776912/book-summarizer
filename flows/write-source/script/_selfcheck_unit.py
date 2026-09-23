"""临时：单元质量自检（write_chapters 用）"""
import sys, io, os, json, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
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
