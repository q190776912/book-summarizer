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

import os, re, sys, io

if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from verify.layers.script.base import DEFAULT_RESULT

LAYERS_DIR = os.path.join(_ROOT, "verify/layers")
REPORT = os.path.join(_ROOT, "verify/script/report.py")

# 管理器注入、不归属任何层的键（稳定基础设施，加层不受影响）。
# 各层自己的键声明在 verify/layers/<snake>/<snake>.md 的 ```contract-keys 块中
# （层文档 verify/layers/<snake>/<snake>.md 位于 <snake>/ 目录内；脚本 verify/layers/<snake>/script/<snake>.py）。
MANAGER_INJECTED = {"ch", "md", "status", "extract_dir"}


def load_doc_keys():
    """Aggregate every layer's declared contract keys from verify/layers/<snake>/<snake>.md
    (per-layer sub-flow docs live INSIDE each <snake>/ directory; scripts under <snake>/script/).
    NOTE: layer docs are one level deeper than the verify/layers/ root, so walk each <snake>/ subdir."""
    keys = set()
    layers_dir = LAYERS_DIR
    if not os.path.isdir(layers_dir):
        return keys
    for sub in sorted(os.listdir(layers_dir)):
        subp = os.path.join(layers_dir, sub)
        if not os.path.isdir(subp) or sub.startswith("_"):
            continue
        for fn in sorted(os.listdir(subp)):
            if not fn.endswith(".md"):
                continue
            text = io.open(os.path.join(subp, fn), encoding="utf-8").read()
            for m in re.finditer(r"```contract-keys\s*\n(.*?)```", text, re.S):
                body = m.group(1)
                for line in re.split(r"[\n,]", body):
                    k = line.strip()
                    if k:
                        keys.add(k)
    return keys


def load_report_keys():
    src = io.open(REPORT, encoding="utf-8").read()
    keys = set()
    for mm in re.finditer(r"r\.get\(\s*['\"]([^'\"]+)['\"]", src):
        keys.add(mm.group(1))
    for mm in re.finditer(r"r\[\s*['\"]([^'\"]+)['\"]", src):
        keys.add(mm.group(1))
    return keys


def test_layer_docs_match_default_result():
    doc_keys = load_doc_keys()
    assert doc_keys, "no contract-keys parsed from verify/layers/*.md"
    expected = doc_keys | MANAGER_INJECTED
    only_doc = expected - set(DEFAULT_RESULT.keys())
    only_code = set(DEFAULT_RESULT.keys()) - expected
    assert not only_doc and not only_code, (
        "DEFAULT_RESULT keys must equal (layer-declared keys + manager-injected). "
        "Missing-in-code: %s ; missing-in-docs: %s"
        % (sorted(only_code), sorted(only_doc))
    )


def test_report_reads_only_known_keys():
    report_keys = load_report_keys()
    missing = report_keys - set(DEFAULT_RESULT.keys())
    assert not missing, (
        "report.print_result reads keys absent from DEFAULT_RESULT "
        "(forgot to add them to registry.DEFAULT_RESULT?): %s" % sorted(missing)
    )


def test_print_result_runs_on_default():
    from verify.script.report import print_result
    import contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        print_result(dict(DEFAULT_RESULT))


def _main():
    funcs = [
        test_layer_docs_match_default_result,
        test_report_reads_only_known_keys,
        test_print_result_runs_on_default,
    ]
    failed = []
    for f in funcs:
        try:
            f()
            print("PASS", f.__name__)
        except Exception as e:
            failed.append(f.__name__)
            print("FAIL", f.__name__, "->", repr(e))
    if failed:
        print("\n%d/%d checks FAILED: %s" % (len(failed), len(funcs), ", ".join(failed)))
        sys.exit(1)
    print("\nALL %d checks passed" % len(funcs))


if __name__ == "__main__":
    _main()
