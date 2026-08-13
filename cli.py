#!/usr/bin/env python3
"""Single-entry CLI for the book-summarizer skill.

Thin router only: every subcommand forwards its trailing arguments verbatim to
the corresponding script under the skill root via subprocess. Because the target
scripts run as separate processes, no heavy imports (torch, cv2, etc.) are
triggered at CLI load time -- `cli.py --help` and every `cli.py <command>
--help` work in a bare Python environment.

Note on forwarding: we forward the raw trailing argv (sys.argv[2:]) rather than
argparse's parsed `REMAINDER`, so that `-h`/`--help` is NOT intercepted by
argparse and instead reaches the underlying script's own help handler.
"""

import argparse
import os
import subprocess
import sys

SKILL_ROOT = os.path.dirname(os.path.abspath(__file__))

# subcommand name -> script path relative to SKILL_ROOT
DISPATCH = {
    "extract-items": "flows/extract/structure/script/extract_items.py",
    "extract-items-hom": "flows/extract/structure/script/extract_items_hom.py",
    "write-chapter-map": "data/chapter_map/chapter_map.py",
    "check-katex": "verify/format_verify/script/check_katex.py",
    "fmt-proofs": "flows/write-source/format/script/fmt_proofs.py",
    "fmt-extras": "flows/write-source/format/script/fmt_extras.py",
    "wrap-examples": "flows/write-source/format/script/wrap_examples_bq.py",
    "extract-figures": "flows/script/extract_figures.py",
    "assign-figures": "flows/script/assign_figures.py",
    "embed-figures": "flows/script/embed_figures.py",
    "apply-manual-figures": "config/figure_manual_chN/apply_manual_figures.py",
    "inspect-figures": "flows/script/inspect_tool.py",
    "verify-chapter": "verify/script/verify_chapter.py",
    "verify-hom": "verify/script/verify_hom.py",
    "manage-ignore": "config/ignore_chN/manage_ignore.py",
    "review": "verify/script/review_tool.py",
    "mathfix": "tools/normalize_math_cli.py",
    "extract-book": "flows/extract/pipeline/script/extract_book.py",
    "extract-pipeline": "flows/extract/pipeline/script/extract_pipeline.py",
    "make-summary": "flows/extract/pipeline/script/make_summary.py",
}


def build_parser():
    # Subparsers exist mainly so that top-level --help lists every subcommand.
    # add_help=False on subparsers avoids argparse intercepting -h/--help,
    # which we forward to the target scripts instead.
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description=(
            "book-summarizer single entry point: route subcommands to the "
            "skill's extract/format/figure/verify/pipeline scripts."
        ),
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    for name, rel in DISPATCH.items():
        p = sub.add_parser(name, help="run {}".format(rel), add_help=False)
        p.add_argument(
            "args",
            nargs=argparse.REMAINDER,
            help="arguments forwarded verbatim to the underlying script",
        )
    return parser


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)

    # Bare invocation or top-level help.
    if not argv or argv[0] in ("-h", "--help"):
        build_parser().print_help()
        return 0

    command = argv[0]
    if command not in DISPATCH:
        sys.stderr.write("error: unknown command {!r}\n".format(command))
        build_parser().print_help()
        return 2

    # Forward everything after the subcommand name verbatim, including -h/--help.
    script = os.path.join(SKILL_ROOT, DISPATCH[command])
    result = subprocess.run([sys.executable, script, *argv[1:]])
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
