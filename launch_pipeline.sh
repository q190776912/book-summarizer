#!/usr/bin/env bash
# launch_pipeline.sh — book-summarizer skill
# Start PDF-Extract-Kit extraction in the background (bash / Git-Bash safe).
# Sets the CUDA PATH inline (torch\lib must be on PATH so paddle reuses torch's
# single cudnn copy; nvidia cudnn\bin is deliberately OMITTED because it must stay empty).
# Use this instead of the .bat/.ps1 launchers — those are blocked by this env's
# security policy / silently fail on space-containing paths.
#
# Usage:  bash launch_pipeline.sh <pdf_path> [--start N] [--end N] [--force] [--deskew ...]
#   <pdf_path>  absolute path to the PDF, e.g. "D:/study/book/Koopman Operator/Koopman Operator.pdf"
#   [--start N] first page to extract (default 1).
#   [--end N]   last page to extract (inclusive). Omitted -> auto-detected PDF total page count.
#   [flags]     any flag understood by extract_pipeline.py is passed through (--force, --deskew ...)
set -e

ENV="D:/anaconda3/envs/pdfextract"
NV="$ENV/lib/site-packages/nvidia"

# CUDA PATH: torch\lib provides the single shared cudnn; add nvidia cu12 bins
# EXCEPT cudnn\bin (that folder must stay empty so paddle falls back to torch's cudnn).
export PATH="$ENV/lib/site-packages/torch/lib;$NV/cublas/bin;$NV/cuda_runtime/bin;$NV/cufft/bin;$NV/curand/bin;$NV/cusolver/bin;$NV/cusparse/bin;$NV/nvjitlink/bin;$ENV/Library/bin;$ENV/Scripts;$ENV;$PATH"

PY="$ENV/python.exe"
SKILL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$SKILL_ROOT/flows/extract/pipeline/script/extract_pipeline.py"

PDF="$1"
EXTRA=()
# $2.. are passthrough args for extract_pipeline.py (--start/--end/--force/--deskew...).
# Flags that take a value (--start/--end/--deskew) consume the following token; valueless
# flags (--force) are passed through as-is.
i=2
while [ $i -le $# ]; do
  a="${!i}"
  case "$a" in
    --force) EXTRA+=("$a") ;;
    --start|--end|--deskew) i=$((i+1)); EXTRA+=("$a" "${!i}") ;;
    --deskew=*) EXTRA+=("$a") ;;
    --*) echo "unsupported flag: $a" >&2; exit 1 ;;
    *)   echo "unexpected positional arg: $a (only <pdf_path> is positional)" >&2; exit 1 ;;
  esac
  i=$((i+1))
done

if [ -z "$PDF" ]; then
  echo "Usage: bash launch_pipeline.sh <pdf_path> [--start N] [--end N] [--force] [--deskew ...]" >&2
  exit 1
fi

# _extract lives next to the PDF's parent (see SKILL.md: PDF must be inside <书名>\<书名>.pdf)
EXTRACT_DIR="$(dirname "$PDF")/_extract"
mkdir -p "$EXTRACT_DIR"
LOG="$EXTRACT_DIR/extract_pipeline.log"

# Build args: pdf, then any passthrough flags.
ARGS=("$PDF")
ARGS+=("${EXTRA[@]}")

nohup "$PY" "$SCRIPT" "${ARGS[@]}" > "$LOG" 2>&1 &

echo "launched PID $! ; log -> $LOG"
echo "tail -f \"$LOG\"   to watch progress"
