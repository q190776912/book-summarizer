#!/usr/bin/env bash
# launch_pipeline.sh — book-summarizer skill
# Start PDF-Extract-Kit extraction in the background (bash / Git-Bash safe).
# Sets the CUDA PATH inline (torch\lib must be on PATH so paddle reuses torch's
# single cudnn copy; nvidia cudnn\bin is deliberately OMITTED because it must stay empty).
# Use this instead of the .bat/.ps1 launchers — those are blocked by this env's
# security policy / silently fail on space-containing paths.
#
# Usage:  bash launch_pipeline.sh <pdf_path> [--start N] [--end N] [--force] [--deskew ...] [--extract-dir <dir>]
#   <pdf_path>  absolute path to the PDF, e.g. "D:/study/book/Koopman Operator/Koopman Operator.pdf"
#   [--start N] first page to extract (default 1).
#   [--end N]   last page to extract (inclusive). Omitted -> auto-detected PDF total page count.
#   [--extract-dir <dir>]  override output dir (default <pdf_parent>/_extract); multi-volume
#                          books pass <book_dir>/_extract/<vol>/ so volumes never share pages.
#   [flags]     any flag understood by extract_pipeline.py is passed through (--force, --deskew ...)
set -e

# --- resolve the conda env path: BKS_CONDA_ENV_PATH > user_config.json > example ---
SKILL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

resolve_env_path() {
  if [ -n "$BKS_CONDA_ENV_PATH" ]; then echo "$BKS_CONDA_ENV_PATH"; return 0; fi
  local py="" v=""
  for py in python py; do
    if command -v "$py" >/dev/null 2>&1; then
      v="$("$py" "$SKILL_ROOT/lib/user_config.py" conda.env_path 2>/dev/null)" || v=""
      [ -n "$v" ] && echo "$v" && return 0
    fi
  done
  return 1
}

ENV="$(resolve_env_path)" || {
  echo "ERROR: cannot resolve conda env path. Set BKS_CONDA_ENV_PATH (e.g. D:/anaconda3/envs/pdfextract) or" >&2
  echo "       configure conda.env_path in $SKILL_ROOT/user_config.json (see README)." >&2
  exit 1
}
NV="$ENV/lib/site-packages/nvidia"

# CUDA PATH: torch\lib provides the single shared cudnn; add nvidia cu12 bins
# EXCEPT cudnn\bin (that folder must stay empty so paddle falls back to torch's cudnn).
export PATH="$ENV/lib/site-packages/torch/lib;$NV/cublas/bin;$NV/cuda_runtime/bin;$NV/cufft/bin;$NV/curand/bin;$NV/cusolver/bin;$NV/cusparse/bin;$NV/nvjitlink/bin;$ENV/Library/bin;$ENV/Scripts;$ENV;$PATH"

PY="$ENV/python.exe"
SCRIPT="$SKILL_ROOT/flows/extract/pipeline/script/extract_pipeline.py"

PDF="$1"
EXTRA=()
EXTRACT_DIR_OVERRIDE=""
# $2.. are passthrough args for extract_pipeline.py (--start/--end/--force/--deskew/--extract-dir...).
# Flags that take a value (--start/--end/--deskew/--extract-dir) consume the following token;
# valueless flags (--force) are passed through as-is.
i=2
while [ $i -le $# ]; do
  a="${!i}"
  case "$a" in
    --force) EXTRA+=("$a") ;;
    --start|--end|--deskew) i=$((i+1)); EXTRA+=("$a" "${!i}") ;;
    --deskew=*) EXTRA+=("$a") ;;
    --extract-dir) i=$((i+1)); EXTRA+=("$a" "${!i}"); EXTRACT_DIR_OVERRIDE="${!i}" ;;
    --extract-dir=*) EXTRACT_DIR_OVERRIDE="${a#*=}"; EXTRA+=("$a") ;;
    --*) echo "unsupported flag: $a" >&2; exit 1 ;;
    *)   echo "unexpected positional arg: $a (only <pdf_path> is positional)" >&2; exit 1 ;;
  esac
  i=$((i+1))
done

if [ -z "$PDF" ]; then
  echo "Usage: bash launch_pipeline.sh <pdf_path> [--start N] [--end N] [--force] [--deskew ...] [--extract-dir <dir>]" >&2
  exit 1
fi

# _extract lives next to the PDF's parent by default (see SKILL.md contract);
# --extract-dir overrides it (multi-volume books: <book_dir>/_extract/<vol>/).
if [ -n "$EXTRACT_DIR_OVERRIDE" ]; then
  EXTRACT_DIR="$EXTRACT_DIR_OVERRIDE"
else
  EXTRACT_DIR="$(dirname "$PDF")/_extract"
fi
mkdir -p "$EXTRACT_DIR"
LOG="$EXTRACT_DIR/extract_pipeline.log"

# Build args: pdf, then any passthrough flags.
ARGS=("$PDF")
ARGS+=("${EXTRA[@]}")

nohup "$PY" "$SCRIPT" "${ARGS[@]}" > "$LOG" 2>&1 &

echo "launched PID $! ; log -> $LOG"
echo "tail -f \"$LOG\"   to watch progress"
