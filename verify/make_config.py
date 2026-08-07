"""verify/make_config.py — 存量书「书级配置」best-effort 引导脚本

为还没有 / 想快速重建 `_extract/verify_config.json` 的书生成一份**起始**配置。
这是 BEST-EFFORT 检测，明确标注「需人工核对」，不声称自动正确。

用法：
    python verify/make_config.py <extract_dir> [--force]

行为：
  1. 若 <extract_dir>/verify_config.json 已存在且非 --force：打印跳过并 exit 0。
  2. best-effort 检测 ordinal：
     - chapter_map.json 章号全是罗马数字（I/II/III…）→ 候选 5（roman）
     - 否则抽样前若干页 page_*.json 的 text[]，用轻量正则判断条目标签形态：
         * EN 两级（Theorem/Lemma/Definition/Proposition/Corollary N.M）→ 候选 4（en）
         * CN 三级（定义|定义|引理|推论|命题 N.M.K）→ 候选 3
         * CN 两级（定义|定义|引理|推论|命题 N.M）→ 候选 2
       - 按特异性优先（CN 三级 > EN > CN 两级），都无命中则默认 3（three_level）。
  3. 写出 {"ordinal": <候选>, "language": <en if 候选 in (4,5,6,7) else cn>}，
     并打印醒目提示：四级子小节书（1.1.1.1）需手动补 section_types/section_depths；
     ordinal 检测不准请修正后再跑 verify。

⚠️ 本脚本只生成「起始」配置，不覆盖任何已有文件（除非 --force），也不声称正确。
   判定不清时以 references/book_patterns.md 判定树为准，人工核对后再跑校验。
"""
import os
import sys
import json
import re
import glob

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
from lib.config import ORDINAL_DEPTH, ORDINAL_LANGUAGE_DEFAULT

# 罗马数字章号形态（chapter_map 的 key / ch 字段全为罗马字母且无阿拉伯数字）
ROMAN_RE = re.compile(r'^[IVXLCDM]+$')

# EN 两级条目标签（无章号位）：Theorem/Lemma/Definition/Proposition/Corollary N.M
EN_TWO_RE = re.compile(
    r'\b(Theorem|Lemma|Definition|Proposition|Corollary)\s+\d+\.\d+')

# CN 条目标签：定义|定义|引理|推论|命题 ... N.M（两级）或 N.M.K（三级）
CN_TWO_RE = re.compile(r'(定理|定义|引理|推论|命题)\s*\d+\.\d+(?!\.\d)')
CN_THREE_RE = re.compile(r'(定理|定义|引理|推论|命题)\s*\d+\.\d+\.\d+')


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


def _detect_ordinal_from_pages(extract_dir, max_pages=20):
    """Sample the first `max_pages` page_*.json and vote on the label shape.

    Specificity-first priority (CN three-level patterns also match the CN
    two-level regex, so raw counts would bias toward two-level): CN three >
    EN two > CN two; no hits -> default 3.
    """
    pages = sorted(glob.glob(os.path.join(extract_dir, 'page_*.json')))[:max_pages]
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

    with open(cfg_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    print(f"⚠️ 已生成起始配置（best-effort 检测 ordinal={ordinal}，depth={depth}）。")
    print(f"   文件路径: {cfg_path}")
    print(f"   文件内容: {json.dumps(config, ensure_ascii=False)}")
    print("   请人工核对后再跑 verify：")
    print("     · 若原 verify_config.json 是【整型 ordinal】旧格式，校验会直接报错")
    print("       exit 2；必须用本脚本 --force 重新生成（见")
    print("       references/verify_config_schema_v2_design.md）。")
    print("     · 默认产出为「单 uncat 合并计数」组；若要 定理/定义/练习 各自")
    print("       独立计数，须手动把 ordinal 拆成多个 group（含一个")
    print('       name=["uncat"] 兜底组）。')
    print("     · 若为四级子小节书（1.1.1.1），需手动加")
    print('       "section_types": [1,2,3,4], "section_depths": [1,2,3,4]。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
