"""
Regression guard against the recurring `page_json.PageJson.load` NameError bug.

Root cause: a file that does `from page_json import PageJson` binds the name
`PageJson` but NOT the module name `page_json`. Calling `page_json.PageJson.load(...)`
then raises NameError -- and the error is often swallowed by a surrounding
`except Exception` block, so the code silently degrades (e.g. the Q/formula-tag
layer used to run as a no-op for every book).

This test enforces a simple invariant for every .py file in the skill:
  * if a file calls `page_json.PageJson.load`, it MUST `import page_json`
    (module name bound);
  * if a file calls `PageJson.load` (unqualified), it MUST do
    `from ... page_json import ... PageJson` (class name bound).
"""
import pathlib
import re

SKILL_ROOT = pathlib.Path(__file__).resolve().parents[2]  # verify/tests -> skill root

# Any reference through the module name (load / dump / constructor / attribute).
MODULE_CALL_RE = re.compile(r'page_json\.PageJson\b')
# Any unqualified reference to the class (load / dump / constructor / attribute).
CLASS_CALL_RE = re.compile(r'(?<![.\w])PageJson\b')

IMPORT_MODULE_RE = re.compile(
    r'^\s*(import\s+page_json(\s+as\s+\w+)?|from\s+[\w.]+\s+import\s+\(?\s*page_json\b)',
    re.M,
)
IMPORT_CLASS_RE = re.compile(
    r'^\s*from\s+[\w.]*page_json\s+import\s+.*\bPageJson\b',
    re.M,
)


def _python_files():
    for p in SKILL_ROOT.rglob("*.py"):
        if ".git" in p.parts or "__pycache__" in p.parts:
            continue
        # Skip test scaffolding: a page_json misuse in a test crashes loudly,
        # it does not silently degrade behind an `except` like production code.
        # (This guard's own docstring quotes the pattern strings on purpose.)
        if "tests" in p.parts:
            continue
        # Skip the module that DEFINES PageJson -- it legitimately references
        # the class unqualified inside its own classmethod bodies.
        if p.name == "page_json.py":
            continue
        yield p


def test_page_json_import_invariant():
    violations = []
    for f in _python_files():
        text = f.read_text(encoding="utf-8", errors="ignore")
        module_bound = bool(IMPORT_MODULE_RE.search(text))
        class_bound = bool(IMPORT_CLASS_RE.search(text))
        module_calls = MODULE_CALL_RE.findall(text)
        class_calls = CLASS_CALL_RE.findall(text)
        if module_calls and not module_bound:
            violations.append(
                f"{f.relative_to(SKILL_ROOT)}: calls page_json.PageJson.load "
                f"but does not `import page_json` (module name unbound)"
            )
        if class_calls and not class_bound:
            violations.append(
                f"{f.relative_to(SKILL_ROOT)}: calls PageJson.load "
                f"but does not `from ... page_json import PageJson`"
            )
    assert not violations, (
        "page_json import invariant violated:\n" + "\n".join(violations)
    )
