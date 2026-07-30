#!/usr/bin/env bash
# launch_pipeline.sh — book-summarizer skill
# Start PDF-Extract-Kit extraction in the background (bash / Git-Bash safe).
# Sets the CUDA PATH inline (torch\lib must be on PATH so paddle reuses torch's
# single cudnn copy; nvidia cudnn\bin is deliberately OMITTED because it must stay empty).
# Use this instead of the .bat/.ps1 launchers — those are blocked by this env's
# security policy / silently fail on space-containing paths.
#
# Usage:  bash launch_pipeline.sh <pdf_path> <total_pages> [--force]
#   <pdf_path>  absolute path to the PDF, e.g. "D:/study/book/Koopman Operator/Koopman Operator.pdf"
#   <total_pages> page count, e.g. 568
#   --force      optional, re-run from page 1 ignoring existing JSON
set -e

ENV="D:/anaconda3/envs/pdfextract"
NV="$ENV/lib/site-packages/nvidia"

# CUDA PATH: torch\lib provides the single shared cudnn; add nvidia cu12 bins
# EXCEPT cudnn\bin (that folder must stay empty so paddle falls back to torch's cudnn).
export PATH="$ENV/lib/site-packages/torch/lib;$NV/cublas/bin;$NV/cuda_runtime/bin;$NV/cufft/bin;$NV/curand/bin;$NV/cusolver/bin;$NV/cusparse/bin;$NV/nvjitlink/bin;$ENV/Library/bin;$ENV/Scripts;$ENV;$PATH"

PY="$ENV/python.exe"
SCRIPT="C:/Users/ye190/.workbuddy/skills/book-summarizer/pipeline/extract_pipeline.py"

PDF="$1"
PAGES="$2"
FORCE="${3:-}"

if [ -z "$PDF" ] || [ -z "$PAGES" ]; then
  echo "Usage: bash launch_pipeline.sh <pdf_path> <total_pages> [--force]" >&2
  exit 1
fi

# _extract lives next to the PDF's parent (see SKILL.md: PDF must be inside <书名>\<书名>.pdf)
EXTRACT_DIR="$(dirname "$PDF")/_extract"
mkdir -p "$EXTRACT_DIR"
LOG="$EXTRACT_DIR/extract_pipeline.log"

if [ -n "$FORCE" ]; then
  nohup "$PY" "$SCRIPT" "$PDF" "$PAGES" "$FORCE" > "$LOG" 2>&1 &
else
  nohup "$PY" "$SCRIPT" "$PDF" "$PAGES" > "$LOG" 2>&1 &
fi

echo "launched PID $! ; log -> $LOG"
echo "tail -f \"$LOG\"   to watch progress"
