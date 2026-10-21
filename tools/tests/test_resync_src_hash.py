"""test_resync_src_hash.py — `tools/resync_src_hash.py`：源单元机械返修后重同步 `src_hash` 快照。

场景：已收官书的**形态类**返修（补 `---` / 标签包进 `>`）改了源单元正文 → parity 判据 6
报「派生后漂移」，而 `init_translate_units` 这条路走不通（要求源章门控全绿、且把
`final_md` 清零、重写整份清单）。合法出口 = 只把快照对齐当前源正文哈希。

正向：dry-run 零写入；--commit 后**只有**漂移记录的 `src_hash` 一行变，其余每一行逐字节
相同，CRLF + 无尾换行守恒，复核残差为 0；再跑为 NO-OP；两条 src_hash 相同的记录只改漂移
那一条（配对靠 `file` 身份，不靠下标）。
负向：①缺 `src_hash` 快照 → 报错且不写（不代建快照）②源单元文件缺失 → 报错不写
③漂移记录里没有可替换的 `src_hash` 行 → SystemExit 且磁盘零改动（拒绝半写）。
"""
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "lib"))
import lib.boot as _boot  # noqa: E402
_boot.setup()

_SPEC = importlib.util.spec_from_file_location(
    "resync_src_hash", os.path.join(_ROOT, "tools", "resync_src_hash.py"))
rsh = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rsh)

MARK = "<!-- book-summarizer DONE unit: id=%s type=item key=K%s name=N%s -->"


def _h(text):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _write_unit(path, uid, body):
    """真实单元形态：全文件 CRLF（首行 marker + 正文），正文里不掺裸 LF。"""
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write((MARK % (uid, uid, uid) + "\n" + body + "\n").replace("\n", "\r\n"))


def _snap(path):
    """init_translate_units 记录 src_hash 的同一算式（借工具用的 `_read_unit`，不重实现）。"""
    return rsh._gate._read_unit(path)[5]


def _bh(body):
    """该正文落成单元文件后的哈希（CRLF 形态由 _write_unit 决定，不手算）。"""
    fd, p = tempfile.mkstemp(suffix=".md")
    os.close(fd)
    _write_unit(p, "9999", body)
    try:
        return _snap(p)
    finally:
        os.unlink(p)


def _tree(bodies, drop_src=(), missing=()):
    """构造 units/ch1 + units-translate/ch1（清单 CRLF + 无尾换行 = 真实形态）。"""
    root = tempfile.mkdtemp()
    src = os.path.join(root, "units", "ch1")
    tgt = os.path.join(root, "units-translate", "ch1")
    os.makedirs(src)
    os.makedirs(tgt)
    recs = []
    for i, (fname, body) in enumerate(sorted(bodies.items()), start=1):
        uid = "%04d" % i
        sp = os.path.join(src, fname)
        _write_unit(sp, uid, body)
        cur = _snap(sp)                      # init 时刻的源正文快照
        rec = {"id": uid, "file": fname, "type": "item", "key": "K" + uid,
               "name": "N" + uid, "hash": cur, "src_hash": cur}
        if fname in drop_src:
            rec.pop("src_hash")
        recs.append(rec)
        if fname not in missing:
            _write_unit(os.path.join(tgt, fname), uid, "译文正文")
    lines = ["{", '  "chapter_key": "1",', '  "language": "cn",',
             '  "source_language": "en",', '  "final_md": "",', '  "units": [']
    for i, rec in enumerate(recs):
        lines.append("    {")
        keys = [k for k in ("id", "file", "type", "key", "name", "hash", "src_hash")
                if k in rec]
        for j, k in enumerate(keys):
            lines.append('      "%s": "%s"%s'
                         % (k, rec[k], "," if j < len(keys) - 1 else ""))
        lines.append("    }" + ("," if i < len(recs) - 1 else ""))
    lines += ["  ]", "}"]
    with open(os.path.join(tgt, "manifest.json"), "w", encoding="utf-8",
              newline="") as f:
        f.write("\r\n".join(lines))
    return root, src, tgt


def _manifest(tgt):
    return os.path.join(tgt, "manifest.json")


class ResyncSrcHash(unittest.TestCase):
    def test_dry_run_detects_and_writes_nothing(self):
        root, src, tgt = _tree({"0001_item.md": "A\n\nB\n", "0002_item.md": "C\n"})
        before = open(_manifest(tgt), "rb").read()
        self.assertEqual(rsh.chapter_drift(src, tgt), ([], []))
        _write_unit(os.path.join(src, "0001_item.md"), "0001", "A\n\n---\n\nB\n")
        drift, errs = rsh.chapter_drift(src, tgt)
        self.assertEqual([d[0] for d in drift], ["0001_item.md"])
        self.assertEqual(errs, [])
        self.assertEqual(open(_manifest(tgt), "rb").read(), before)

    def test_commit_touches_only_the_drifted_lines(self):
        root, src, tgt = _tree({"0001_item.md": "A\n", "0002_item.md": "C\n",
                               "0003_item.md": "E\n"})
        before = open(_manifest(tgt), "rb").read().decode("utf-8").split("\r\n")
        _write_unit(os.path.join(src, "0001_item.md"), "0001", "A\n\n---\n")
        _write_unit(os.path.join(src, "0003_item.md"), "0003", "E\n\n> F\n")
        self.assertEqual(rsh.resync_chapter(src, tgt, commit=True), ([], []))
        raw = open(_manifest(tgt), "rb").read()
        after = raw.decode("utf-8").split("\r\n")
        self.assertEqual(len(before), len(after))
        changed = [i for i in range(len(before)) if before[i] != after[i]]
        self.assertEqual(len(changed), 2, [after[i] for i in changed])
        for i in changed:
            self.assertRegex(after[i], r'^\s*"src_hash": "[0-9a-f]{40}",?\s*$')
        self.assertIn(b"\r\n", raw)                    # 换行风格守恒
        self.assertFalse(raw.endswith(b"\n"))          # 无尾换行守恒
        self.assertEqual(rsh.chapter_drift(src, tgt), ([], []))   # 幂等

    def test_same_old_hash_only_drifted_record_changes(self):
        """两条记录 src_hash 相同（同正文）→ 只改漂移那条，不按下标串账。"""
        root, src, tgt = _tree({"0001_item.md": "S\n", "0002_item.md": "S\n"})
        shared = {r["file"]: r["src_hash"]
                  for r in json.load(open(_manifest(tgt), encoding="utf-8"))["units"]}
        _write_unit(os.path.join(src, "0002_item.md"), "0002", "S\n\n---\n")
        self.assertEqual(rsh.resync_chapter(src, tgt, commit=True), ([], []))
        got = {r["file"]: r["src_hash"]
               for r in json.load(open(_manifest(tgt), encoding="utf-8"))["units"]}
        self.assertEqual(got["0001_item.md"], shared["0001_item.md"])
        self.assertEqual(got["0002_item.md"], _bh("S\n\n---\n"))

    def test_missing_snapshot_refuses_write(self):
        root, src, tgt = _tree({"0001_item.md": "A\n"}, drop_src=("0001_item.md",))
        before = open(_manifest(tgt), "rb").read()
        _write_unit(os.path.join(src, "0001_item.md"), "0001", "A\n\n---\n")
        drift, errs = rsh.resync_chapter(src, tgt, commit=True)
        self.assertEqual(drift, [])
        self.assertEqual(len(errs), 1)
        self.assertIn("src_hash", errs[0])
        self.assertEqual(open(_manifest(tgt), "rb").read(), before)

    def test_missing_source_file_refuses_write(self):
        root, src, tgt = _tree({"0001_item.md": "A\n", "0002_item.md": "C\n"},
                              missing=("0002_item.md",))
        before = open(_manifest(tgt), "rb").read()
        os.remove(os.path.join(src, "0002_item.md"))
        _write_unit(os.path.join(src, "0001_item.md"), "0001", "A\n\n---\n")
        drift, errs = rsh.resync_chapter(src, tgt, commit=True)
        self.assertEqual(len(errs), 1)
        self.assertIn("源单元文件缺失", errs[0])
        self.assertEqual(open(_manifest(tgt), "rb").read(), before)

    def test_unlocatable_line_refuses_half_write(self):
        """漂移记录里没有可替换的 `src_hash` 行 → SystemExit 且磁盘零改动。"""
        root, src, tgt = _tree({"0001_item.md": "A\n"})
        lines = open(_manifest(tgt), encoding="utf-8", newline="").read().split("\r\n")
        for i, ln in enumerate(lines):
            if '"src_hash"' in ln:                    # 快照形不是 40 位十六进制
                lines[i] = '      "src_hash": "NOT-A-HEX-VALUE"'
        with open(_manifest(tgt), "w", encoding="utf-8", newline="") as f:
            f.write("\r\n".join(lines))
        before = open(_manifest(tgt), "rb").read()
        with self.assertRaises(SystemExit):
            rsh.rewrite_manifest(tgt, {"0001_item.md": _bh("A\n\n---\n")})
        self.assertEqual(open(_manifest(tgt), "rb").read(), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
