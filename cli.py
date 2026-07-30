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
    "extract-items": "extract/extract_items.py",
    "extract-items-hom": "extract/extract_items_hom.py",
    "scan-items": "extract/scan_items.py",
    "write-chapter-map": "extract/write_chapter_map.py",
    "check-katex": "format/check_katex.py",
    "fmt-proofs": "format/fmt_proofs.py",
    "fmt-extras": "format/fmt_extras.py",
    "mathify": "format/mathify_plaintext.py",
    "unwrap-bq": "format/unwrap_blockquote_items.py",
    "wrap-examples": "format/wrap_examples_bq.py",
    "extract-figures": "figure/extract_figures.py",
    "assign-figures": "figure/assign_figures.py",
    "embed-figures": "figure/embed_figures.py",
    "apply-manual-figures": "figure/apply_manual_figures.py",
    "inspect-figures": "figure/inspect_tool.py",
    "verify-chapter": "verify/verify_chapter.py",
    "verify-hom": "verify/verify_hom.py",
    "manage-ignore": "verify/manage_ignore.py",
    "review": "verify/review_tool.py",
    "extract-book": "pipeline/extract_book.py",
    "extract-pipeline": "pipeline/extract_pipeline.py",
    "make-summary": "pipeline/make_summary.py",
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
