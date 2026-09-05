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
from data.book_structure.book_structure import chapter_label

# review_tool.py - Automated Chapter Review Tool (book-agnostic)
# All execution lives inside main(), guarded by `if __name__ == "__main__"`,
# so importing this module as a library has NO import-time side effects
# (no sys.exit, no subprocess, no file reads at import time).

import subprocess

# Python interpreter used to spawn skill-internal scripts (constant; no side effect).
from lib.user_config import get as _uc_get
PY = _uc_get("conda.env_path", r"D:\anaconda3\envs\pdfextract") + r"\python.exe"


def resolve_md_file(book_dir, chapter_map, chapter_md_groups, merge_section_files, chapter):
    """Resolve this chapter's verification .md: the merged file if it still
    exists, otherwise merge the rule-D section files into a temp file."""
    groups = chapter_md_groups(book_dir, chapter)
    if not groups:
        return None
    grp = groups[0]
    if len(grp) == 1:
        return grp[0]
    tmp = os.path.join(book_dir, f'._review_merged_ch{chapter}.md')
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(merge_section_files(grp))
    return tmp


def run_extract_items(extract_items, chapter_map, chapter, extract_dir):
    """Run extract_items for a chapter (no ignore — ignore belongs to verify)."""
    command = [
        PY, "-X", "utf8", extract_items,
        str(chapter),
        str(chapter_map[str(chapter)]["start"]),
        str(chapter_map[str(chapter)]["end"]),
        extract_dir,
    ]
    return subprocess.run(command, capture_output=True, text=True, encoding='utf-8')


def run_verify_chapter(verify_chapter, chapter_map, chapter, md_file, extract_dir, ignore_file=None):
    """Run verify_chapter for a chapter, optionally with an ignore file."""
    command = [
        PY, "-X", "utf8", verify_chapter,
        str(chapter),
        str(chapter_map[str(chapter)]["start"]),
        str(chapter_map[str(chapter)]["end"]),
        md_file,
        extract_dir,
    ]
    if ignore_file:
        command.extend(["--ignore", ignore_file])
    return subprocess.run(command, capture_output=True, text=True, encoding='utf-8')


def review_chapter(extract_items, verify_chapter, chapter_map, book_dir, extract_dir,
                   chapter_md_groups, merge_section_files, chapter):
    """Process a single chapter and handle review."""
    print(f"\n{'='*60}")
    print(f"=== CHAPTER {chapter} REVIEW ===")
    print(f"{'='*60}")

    # Step1: Extract items (ignore is NOT an extract_items flag)
    result = run_extract_items(extract_items, chapter_map, chapter, extract_dir)
    print("\n--- EXTRACT ITEMS OUTPUT ---")
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)

    # Step2: Locate this chapter's ignore file (in the book's _extract folder)
    ignore_file = None
    ig_path = os.path.join(extract_dir, f"ignore_{chapter_label(chapter)}.json")
    if os.path.exists(ig_path):
        ignore_file = ig_path

    # Step3: Run verification (pass ignore here)
    md_file = resolve_md_file(book_dir, chapter_map, chapter_md_groups, merge_section_files, chapter)
    if not md_file:
        print(f"\n✗ Chapter {chapter} markdown file not found in {book_dir}")
        return False
    verify_result = run_verify_chapter(verify_chapter, chapter_map, chapter, md_file, extract_dir, ignore_file)
    print("\n--- VERIFY CHAPTER OUTPUT ---")
    print(verify_result.stdout)
    if verify_result.stderr:
        print("STDERR:", verify_result.stderr)

    # Step4: Check if verification passed
    if verify_result.returncode == 0:
        print(f"\n✓ CHAPTER {chapter} PASSED VERIFICATION")
        print("✓ No A-layer missing items / B-layer blocking / C-layer KaTeX errors")
        return True
    else:
        print(f"\n✗ CHAPTER {chapter} FAILED VERIFICATION")
        print("Manual interventions required:")
        print("  1. Review A-layer missing items (add to .md)")
        print("  2. Review B-layer blocking issues (add real item via --manual, or ignore if OCR/ref)")
        print("  3. Fix C-layer KaTeX errors ($$ blank lines / inline $ / unsupported macros)")
        print("  4. Re-run verification after manual fixes")
        return False


def main():
    # Skill-internal script imports are deferred into main() so that importing
    # this module as a library does not trigger import-time side effects.
    import chapter_map
    from verify_chapter import chapter_md_groups, _merge_section_files

    # Paths (skill-internal scripts only; book data is resolved from argv).
    # _ROOT is the skill root computed at module load. Restructuring moved these
    # scripts, so reference their current locations under flows/ and verify/.
    extract_items = os.path.join(_ROOT, "flows", "extract", "structure", "script", "extract_items.py")
    verify_chapter = os.path.join(_ROOT, "verify", "script", "verify_chapter.py")

    # Book directory: REQUIRED as argv[1] — this tool is book-agnostic.
    if len(sys.argv) < 2:
        print("Usage: python review_tool.py <book_dir>")
        print("  <book_dir> is REQUIRED — the book root folder (e.g. D:\\study\\book\\<书名>).")
        sys.exit(1)
    book_dir = sys.argv[1]
    extract_dir = os.path.join(book_dir, "_extract")
    chapter_map_path = os.path.join(extract_dir, "chapter_map.json")

    # Load chapter map
    chapter_map_data = chapter_map.load_chapter_map_raw(chapter_map_path)

    print("Chapter Review Tool")
    print("===================")
    print("1. Review all chapters")
    print("2. Exit")

    choice = input("\nSelect option (1-2): ").strip()

    if choice == "1":
        print(f"\nReviewing {len(chapter_map_data)} chapters...")
        all_passed = True
        for ch in sorted([int(k) for k in chapter_map_data.keys()]):
            md_file = resolve_md_file(book_dir, chapter_map_data, chapter_md_groups, _merge_section_files, ch)
            if md_file:
                if not review_chapter(extract_items, verify_chapter, chapter_map_data, book_dir,
                                      extract_dir, chapter_md_groups, _merge_section_files, ch):
                    all_passed = False
                if os.path.basename(md_file).startswith('._review_merged'):
                    try:
                        os.remove(md_file)
                    except OSError:
                        pass
            else:
                print(f"\n✗ Chapter {ch} markdown file not found in {book_dir}")
                all_passed = False

        if all_passed:
            print(f"\n{'='*60}")
            print("ALL CHAPTERS PASSED VERIFICATION")
            print(f"{'='*60}")
        else:
            print(f"\n{'='*60}")
            print("SOME CHAPTERS FAILED VERIFICATION")
            print("Manual intervention required")
            print(f"{'='*60}")
    elif choice == "2":
        print("Exiting...")
        return
    else:
        print("Invalid choice")


if __name__ == "__main__":
    main()
