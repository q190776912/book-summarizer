import os, re, sys, io

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if SKILL_ROOT not in sys.path:
    sys.path.insert(0, SKILL_ROOT)

from verify.layers.base import DEFAULT_RESULT

LAYERS_DIR = os.path.join(SKILL_ROOT, "references", "layers")
REPORT = os.path.join(SKILL_ROOT, "verify", "report.py")

# 管理器注入、不归属任何层的键（稳定基础设施，加层不受影响）。
# 各层自己的键声明在 references/layers/<code>.md 的 ```contract-keys 块中。
MANAGER_INJECTED = {"ch", "md", "status", "extract_dir"}


def load_doc_keys():
    """Aggregate every layer's declared contract keys from references/layers/*.md."""
    keys = set()
    for fn in sorted(os.listdir(LAYERS_DIR)):
        if not fn.endswith(".md"):
            continue
        text = io.open(os.path.join(LAYERS_DIR, fn), encoding="utf-8").read()
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
    assert doc_keys, "no contract-keys parsed from references/layers/*.md"
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
    from verify.report import print_result
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
