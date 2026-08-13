"""config/verify_config/make_config.py — 存量书「书级配置」best-effort 引导脚本

为还没有 / 想快速重建 `_extract/verify_config.json` 的书生成一份**起始**配置。
这是 BEST-EFFORT 检测，明确标注「需人工核对」，不声称自动正确。

用法：
    python config/verify_config/make_config.py <extract_dir> [--force]

行为：
  1. 若 <extract_dir>/verify_config.json 已存在且非 --force：打印跳过并 exit 0。
  2. best-effort 检测 ordinal 与 formula（两者都**全量**扫描整本书，整书聚合后
     确认全局配置，**禁止抽样前 N 页**）：
     - chapter_map.json 章号全是罗马数字（I/II/III…）→ 候选 5（roman）
     - 否则**全量**扫描整本书所有 page_*.json（sorted(glob)，不切片前 N 页），
       用轻量正则判断条目标签形态：
         * EN 两级（Theorem/Lemma/Definition/Proposition/Corollary N.M）→ 候选 4（en）
         * CN 三级（定义|定义|引理|推论|命题 N.M.K）→ 候选 3
         * CN 两级（定义|定义|引理|推论|命题 N.M）→ 候选 2
       - 按特异性优先（CN 三级 > EN > CN 两级），都无命中则默认 3（three_level）。
     - formula：detect_formula() **全量**扫描所有 page_*.json 的 text[]，统计
       standalone (N)/（N）与 (C.N)/Eq. C.N/式（C.N）的数量，整书聚合并确认全局
       公式配置（type/depth/scope）。单分量 ≫ 多分量 → type1/depth1（scope 由
       是否「全书数值回落」判定：回落→scope3 节级重排，否则→scope1 全书）；多分量
       多 → type4/depth2/scope2；都抽不到返回 None（不写 formula 键）。
  3. 写出 {"ordinal": <候选>, "language": <en if 候选 in (4,5,6,7) else cn>}，
     若 detect_formula 非 None 再写入 "formula": {...}；并打印醒目提示：四级子
     小节书（1.1.1.1）需手动补 section_types/section_depths；ordinal/formula 检测
     不准请修正后再跑 verify。

⚠️ 相位护栏：ordinal/formula 探测均要求 MM Repair 已完成（完成标记 _extraction_done.json
   存在；该标记仅在 MM Repair 模式 A+B 全部 apply 回 page_*.json 后由主 Agent 写出，不等同
   后台文本流水线"文本 100%"中间信号），否则跳过探测、打印提示并返回默认值——**禁止**在
   MM Repair 未完成（尤其模式 A 视觉审读未做）时对前若干页抽样降级。判定不清时以
   `verify/verify.md` 与各层 `ref/*.md` 的语义为准，人工核对后再跑校验。

⚠️ 本脚本只生成「起始」配置，不覆盖任何已有文件（除非 --force），也不声称正确。
"""
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

import os
import sys
import json
import re
import glob

sys.stdout.reconfigure(encoding='utf-8')
from verify_config import ORDINAL_DEPTH, ORDINAL_LANGUAGE_DEFAULT

# 罗马数字章号形态（chapter_map 的 key / ch 字段全为罗马字母且无阿拉伯数字）
ROMAN_RE = re.compile(r'^[IVXLCDM]+$')

# EN 两级条目标签（无章号位）：Theorem/Lemma/Definition/Proposition/Corollary N.M
EN_TWO_RE = re.compile(
    r'\b(Theorem|Lemma|Definition|Proposition|Corollary)\s+\d+\.\d+')

# CN 条目标签：定义|定义|引理|推论|命题 ... N.M（两级）或 N.M.K（三级）
CN_TWO_RE = re.compile(r'(定理|定义|引理|推论|命题)\s*\d+\.\d+(?!\.\d)')
CN_THREE_RE = re.compile(r'(定理|定义|引理|推论|命题)\s*\d+\.\d+\.\d+')

# ---- formula detection (full-book, whole-book aggregation) ----------------
# Reuse q_layer.norm's "（）→()" ASCII-normalisation idea: a standalone formula
# number may appear in either full-width or half-width parens, so we match both.

# Formula-number detectors — patterns shared from lib/regexlib.py
from lib.regexlib import F_SINGLE_RE as _F_SINGLE_RE, F_DOT_RE as _F_DOT_RE, F_EQ_RE as _F_EQ_RE, F_CN_EQ_RE as _F_CN_EQ_RE


def detect_formula(extract_dir):
    """Full-scan EVERY page_*.json and infer the book's formula numbering.

    Counts standalone single-component ``(N)``/``（N）`` vs two-component
    ``(C.N)``/``Eq. C.N``/``式（C.N）`` occurrences across the WHOLE book, then
    decides the global formula config by whole-book aggregation (never by
    sampling the first N pages).

    Returns a ``{"type", "depth", "scope", "ignore"}`` dict, or ``None`` when
    neither shape is detected (caller then simply omits the ``formula`` key).

    Phase guard: requires MM Repair to be finished (``_extraction_done.json``
    present — written only after mode A+B are applied back to ``page_*.json``,
    NOT merely when background text extraction reaches 100%); otherwise returns
    None rather than guessing from a partial / un-repaired extraction.
    """
    if not os.path.exists(os.path.join(extract_dir, '_extraction_done.json')):
        print('[make_config] MM Repair 未完成（缺 _extraction_done.json），'
              '跳过 formula 探测；请完成 MM Repair（模式 A+B 写回 page_*.json）后再生成配置。')
        return None

    pages = sorted(glob.glob(os.path.join(extract_dir, 'page_*.json')))
    single_count = 0
    dotted_count = 0
    single_nums = []  # ints in page order, for per-section-reset fallback
    for pg in pages:
        try:
            with open(pg, encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            continue
        texts = [b.get('text', '') for b in data.get('text', [])
                 if isinstance(b, dict)]
        for text in texts:
            if not text:
                continue
            for m in _F_SINGLE_RE.finditer(text):
                single_count += 1
                try:
                    single_nums.append(int(m.group(1)))
                except ValueError:
                    pass
            dotted_count += len(_F_DOT_RE.findall(text))
            dotted_count += len(_F_EQ_RE.findall(text))
            dotted_count += len(_F_CN_EQ_RE.findall(text))

    if single_count > dotted_count and single_count > 0:
        # Single-component book.  Decide scope by whether the numeric sequence
        # "falls back" (resets to a smaller number) somewhere in the book:
        #   reset seen  -> per-section numbering  -> scope 3
        #   monotonic   -> book-wide numbering      -> scope 1
        scope = 1
        seen_max = 0
        for n in single_nums:
            if n < seen_max:
                scope = 3
                break
            seen_max = max(seen_max, n)
        return {"type": 1, "depth": 1, "scope": scope, "ignore": []}
    if dotted_count > single_count and dotted_count > 0:
        # Two-component book -> chapter-level numbering (scope 2).
        return {"type": 4, "depth": 2, "scope": 2, "ignore": []}
    return None


def _chapter_keys_are_roman(extract_dir):
    """Return (is_roman, keys) — True if ALL chapter keys are roman-numeral
    shaped and none contain arabic digits (a roman-chapter book)."""
    cm_path = os.path.join(extract_dir, 'chapter_map.json')
    if not os.path.exists(cm_path):
        return False, None
    try:
        with open(cm_path, encoding='utf-8-sig') as f:
            cm = json.load(f)
    except Exception:
        return False, None

    keys = []
    if isinstance(cm, dict) and 'chapters' in cm:
        for e in cm['chapters']:
            ch = e.get('ch', e.get('num', e.get('chapter')))
            if ch is not None:
                keys.append(str(ch))
    elif isinstance(cm, dict):
        keys = [str(k) for k in cm.keys()]
    elif isinstance(cm, list):
        for e in cm:
            ch = e.get('ch', e.get('num', e.get('chapter')))
            if ch is not None:
                keys.append(str(ch))
    else:
        return False, None

    if not keys:
        return False, keys
    arabic = [k for k in keys if re.search(r'\d', k)]
    roman = [k for k in keys if ROMAN_RE.match(k.strip())]
    return bool(roman) and not bool(arabic), keys


def _detect_ordinal_from_pages(extract_dir):
    """Full-scan EVERY page_*.json of the book and vote on the label shape.

    Specificity-first priority (CN three-level patterns also match the CN
    two-level regex, so raw counts would bias toward two-level): CN three >
    EN two > CN two; no hits -> default 3.

    Phase guard: only runs AFTER MM Repair is finished (`_extraction_done.json`
    present — written only after mode A+B applied back to ``page_*.json``, NOT
    merely when background text extraction reaches 100%).  If MM Repair is
    incomplete we MUST NOT sample the first N pages and downgrade — we skip and
    return the safe default instead.
    """
    if not os.path.exists(os.path.join(extract_dir, '_extraction_done.json')):
        print('[make_config] MM Repair 未完成（缺 _extraction_done.json），'
              '跳过探测；请完成 MM Repair（模式 A+B 写回 page_*.json）后再生成配置。')
        return 3  # default three_level (不降级抽样)
    pages = sorted(glob.glob(os.path.join(extract_dir, 'page_*.json')))
    counts = {'cn_three': 0, 'en': 0, 'cn_two': 0}
    for pg in pages:
        try:
            with open(pg, encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            continue
        text = ' '.join(b.get('text', '') for b in data.get('text', []))
        if not text:
            continue
        counts['cn_three'] += len(CN_THREE_RE.findall(text))
        counts['en'] += len(EN_TWO_RE.findall(text))
        counts['cn_two'] += len(CN_TWO_RE.findall(text))

    if counts['cn_three'] > 0:
        return 3
    if counts['en'] > 0:
        return 4
    if counts['cn_two'] > 0:
        return 2
    return 3  # default three_level


def detect_ordinal(extract_dir):
    """Best-effort ordinal detection for a book's _extract dir."""
    is_roman, _ = _chapter_keys_are_roman(extract_dir)
    if is_roman:
        return 5
    return _detect_ordinal_from_pages(extract_dir)


def main():
    args = sys.argv[1:]
    force = '--force' in args
    pos = [a for a in args if not a.startswith('-')]
    if not pos:
        print(__doc__)
        return 2

    extract_dir = pos[0]
    if not os.path.isdir(extract_dir):
        print(f"[make_config] 目录不存在: {extract_dir}")
        return 2

    cfg_path = os.path.join(extract_dir, 'verify_config.json')
    if os.path.exists(cfg_path) and not force:
        print(f"[make_config] 已存在 {cfg_path}，跳过（用 --force 覆盖）。")
        return 0

    ordinal = detect_ordinal(extract_dir)
    # ORDINAL_LANGUAGE_DEFAULT already maps en-family ordinals (4/5/6/7) -> 'en'
    # and cn-family (1/2/3) -> 'cn', matching the spec's "<en if 候选==4/5/6/7>".
    language = ORDINAL_LANGUAGE_DEFAULT.get(ordinal, 'cn')
    depth = ORDINAL_DEPTH.get(ordinal, 3)

    # best-effort formula detection (full-book, whole-book aggregation; only
    # when the whole extraction is done — see detect_formula's phase guard).
    formula_cfg = detect_formula(extract_dir)
    # v2 schema: `ordinal` is a LIST of GroupConfig dicts.  The default is a
    # SINGLE uncat merged counter (one group).  `scope` and `depth` are two
    # DISTINCT axes:
    #   * `depth` = number of numbering components (form-driven from ORDINAL_DEPTH).
    #   * `scope` = ascending-range / counter-reset boundary:
    #       1 = book-wide, 2 = chapter-wide reset, 3 = section-wide reset.
    #   scope is NOT mechanically tied to depth — it is form-driven per book,
    #   derived from the book's actual ordinal labels (same family as type/depth).
    #   make_config's best-effort default is chapter (2).  A deeper (e.g. three-
    #   level) book whose counters reset per chapter stays at scope=2; only bump
    #   to 3 when the book genuinely recounts per section.
    # Different groups NEVER merge; a book needing per-label independent counters
    # must declare multiple groups explicitly (always keeping one
    # name=["uncat"] fallback).  Default behavior stays a single merged counter
    # (R2 behavior change: NOT per-type independent).
    config = {
        "ordinal": [
            {
                "type": ordinal,
                "name": ["uncat"],
                "depth": depth,
                "scope": 2,
            }
        ],
        "strict": True,
        "language": language,
    }
    if formula_cfg is not None:
        config["formula"] = formula_cfg

    with open(cfg_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    print(f"⚠️ 已生成起始配置（best-effort 检测 ordinal={ordinal}，depth={depth}）。")
    print(f"   文件路径: {cfg_path}")
    print(f"   文件内容: {json.dumps(config, ensure_ascii=False)}")
    print("   请人工核对后再跑 verify：")
    print("     · 若原 verify_config.json 是【整型 ordinal】旧格式，校验会直接报错")
    print("       exit 2；必须用本脚本 --force 重新生成（见")
    print("       config/config_schema.md §配置字段说明）。")
    print("     · 若需公式序标校验（Q 层），formula 键已按书源公式形态 best-effort 写入；")
    print("       多分量书 scope 默认 2（章级跨章守卫），单分量且每节从 1 重排的书")
    print("       应 scope 3（如 Kreyszig 式 (N)），请核对 scope 是否正确。")
    print("     · 默认产出为「单 uncat 合并计数」组；若要 定理/定义/练习 各自")
    print("       独立计数，须手动把 ordinal 拆成多个 group（含一个")
    print('       name=["uncat"] 兜底组）。')
    print("     · 若为四级子小节书（1.1.1.1），需手动加")
    print('       "section_types": [1,2,3,4], "section_depths": [1,2,3,4]。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
