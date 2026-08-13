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

import os, sys

import os
import subprocess


def _find_node():
    import shutil as _s
    cands = [
        r'C:\Users\ye190\.workbuddy\binaries\node\versions\22.22.2\node.exe',
        r'C:\Users\ye190\.workbuddy\binaries\node\versions\22.22.2\node',
    ]
    p = _s.which('node')
    if p:
        cands.insert(0, p)
    for c in cands:
        if os.path.exists(c):
            return c
    return None


def _find_node_modules():
    here = os.path.dirname(os.path.abspath(__file__))
    cands = [
        # skill-local node_modules lives with the katex tooling under
        # verify/format_verify/script/node_modules
        os.path.normpath(os.path.join(here, 'node_modules')),
        r'C:\Users\ye190\.workbuddy\binaries\node\workspace\node_modules',
        os.path.normpath(os.path.join(here, '..', '..', '..', 'binaries', 'node',
                                       'workspace', 'node_modules')),
    ]
    for c in cands:
        if os.path.isdir(c):
            return c
    return None


def run_render_check(md_file):
    """Run katex_validate.js (REAL KaTeX render) on md_file. Returns a list of
    error strings. If node/katex is unavailable, returns a WARNING (heuristic
    only) instead of silently passing — so a missing toolchain is visible."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # katex_validate.js lives at the skill ROOT (parent of format/), not in
    # format/ — search both so the real render check is found either way.
    js_cands = [
        os.path.join(script_dir, 'katex_validate.js'),
        os.path.normpath(os.path.join(script_dir, '..', 'katex_validate.js')),
    ]
    js = next((c for c in js_cands if os.path.exists(c)), None)
    if not js:
        return ['[render] katex_validate.js missing — genuine LaTeX syntax '
                'errors NOT checked (heuristic-only fallback)']
    node = _find_node()
    if not node:
        return ['[render] node not found — genuine LaTeX syntax errors NOT '
                'checked (heuristic-only fallback)']
    nm = _find_node_modules()
    if not nm:
        return ['[render] katex node_modules missing — run: npm install katex '
                'in bin/node/workspace — genuine LaTeX syntax errors NOT '
                'checked (heuristic-only fallback)']
    env = dict(os.environ)
    env['NODE_PATH'] = nm
    try:
        r = subprocess.run([node, js, md_file], capture_output=True,
                           text=True, encoding='utf-8', env=env, timeout=180)
    except Exception as e:
        return [f'[render] failed to run node: {e}']
    if r.returncode != 0:
        out = (r.stdout + r.stderr)
        return [l for l in out.splitlines()
                if l.strip() and not l.startswith('KATEX RENDER')]
    return []
