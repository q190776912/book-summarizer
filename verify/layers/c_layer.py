"""
c_layer.py — C-LAYER (order 4): KaTeX validation.

Self-contained implementation (bodies relocated from verify_chapter.py during the per-layer split). Runs check_katex.py as a subprocess
against the chapter .md.
"""
import os
import sys
import subprocess

from verify.registry import VerifyLayer, LayerResult


def check_katex(md_file):
    """Run check_katex.py on the markdown file, return (has_errors, error_lines)."""
    script_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    check_path = os.path.join(script_dir, 'format', 'check_katex.py')
    r = subprocess.run([
        sys.executable, '-X', 'utf8', check_path, md_file
    ], capture_output=True, text=True, encoding='utf-8')
    lines = [l for l in r.stdout.strip().splitlines()
             if l.strip() and not l.strip().startswith('KATEX ERRORS') and not l.startswith('KATEX CHECK')]
    has_errors = bool(lines) and r.returncode != 0
    return has_errors, lines


class CLayer(VerifyLayer):
    code = 'C'
    order = 4
    auto_fixable = False

    def run(self, ctx):
        katex_errors, katex_lines = check_katex(ctx.md_file)
        return LayerResult(code=self.code, legacy=(katex_errors, katex_lines), metadata={
            'katex_errors': katex_errors,
            'katex_lines': katex_lines,
        })
