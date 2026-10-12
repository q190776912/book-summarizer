#!/usr/bin/env bash
# tools/remediate_anchor_gate.sh <_extract_dir> [id]
#   逐本「锚点/节序」门控 contract-only 修复 + fail-closed 复扫回滚。
#   流程：备份 book_structure/*.json → 对每个契约跑 clamp_anchor_pages.py + fix_section_ties.py
#         → 复扫 check_structure_completeness → 若 锚点/归属/节序 任一恶化 或 units md5 变化 → 整体回滚。
#   只改契约，绝不 merge_units、绝不动 units/交付。
set -u
EXT="${1:?usage: remediate_anchor_gate.sh <_extract_dir> [id]}"
ID="${2:-book}"
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SK="$(cd "$SELF_DIR/.." && pwd)"          # skill root (contains SKILL.md)
CLAMP="$SK/tools/clamp_anchor_pages.py"
TIES="$SK/tools/fix_section_ties.py"
GATE_PY="$SK/verify/script/check_structure_completeness.py"
BK="$EXT/book_structure"
[ -d "$BK" ] || { echo "[$ID] 没有 $BK 目录，退出"; exit 3; }

GATE() { ( cd "$EXT" && python -X utf8 "$GATE_PY" . </dev/null ) 2>&1; }
units_md5() { ( cd "$BK" && find units units-translate -name '*.md' -type f 2>/dev/null | sort | xargs -r md5sum 2>/dev/null | md5sum | awk '{print $1}'); }

TS=$(date +%Y%m%d_%H%M%S); BKP="$EXT/_bak_anchor_fix/${ID}_${TS}"
mkdir -p "$BKP"; cp -f "$BK"/*.json "$BKP/"
U0=$(units_md5)
L0=$(GATE)
a0=$(printf '%s' "$L0"|grep -c 'BLOCKING(锚点'); t0=$(printf '%s' "$L0"|grep -c 'BLOCKING(归属'); o0=$(printf '%s' "$L0"|grep -c 'BLOCKING(节序'); f0=$(printf '%s' "$L0"|grep -c 'GATE=FAIL')
echo "[$ID] BEFORE anchor=$a0 attrib=$t0 order=$o0 failch=$f0  (备份 $BKP)"

for j in "$BK"/*.json; do
  python -X utf8 "$CLAMP" "$j" --commit </dev/null 2>&1 | grep -E 'COMMITTED|拒绝' | sed "s#^#[$ID] $(basename "$j") clamp: #"
  python -X utf8 "$TIES"  "$j" --commit </dev/null 2>&1 | grep -E 'COMMITTED|拒绝' | sed "s#^#[$ID] $(basename "$j") ties: #"
done

L1=$(GATE)
a1=$(printf '%s' "$L1"|grep -c 'BLOCKING(锚点'); t1=$(printf '%s' "$L1"|grep -c 'BLOCKING(归属'); o1=$(printf '%s' "$L1"|grep -c 'BLOCKING(节序'); f1=$(printf '%s' "$L1"|grep -c 'GATE=FAIL')
U1=$(units_md5)
same=$([ "$U0" = "$U1" ] && echo YES || echo NO)
echo "[$ID] AFTER  anchor=$a1 attrib=$t1 order=$o1 failch=$f1  units_md5_same=$same"

if [ "$U0" != "$U1" ] || [ "$a1" -gt "$a0" ] || [ "$t1" -gt "$t0" ] || [ "$o1" -gt "$o0" ]; then
  cp -f "$BKP"/*.json "$BK/"
  echo "[$ID] >>> 指标恶化或正文变动，已 fail-closed 回滚（保留原契约）。残留多为「真冲突」需回源核页码/去提升，见两工具文档旁注。"
  exit 1
fi
echo "[$ID] >>> KEEP。锚点 $a0->$a1，归属 $t0->$t1，节序 $o0->$o1，FAIL章 $f0->$f1（剩余 FAIL 多为缺项，另一类）。"
