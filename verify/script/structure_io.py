"""verify/script/structure_io.py — 统一消费 extract/structure 产物：分章契约（SSOT）。

从 verify/data_provider/script/data_provider.py 抽出的纯数据读取逻辑；
不再依赖抽取管线代码，仅读取其产物 JSON 文件（分章契约
``ch{N}.json`` / ``appendix{X}.json``，由 ``data/book_structure/book_structure.py``
的 BookStructure 模型聚合加载；旧版全书单文件已废弃）。
exercise / chapter / section 节点被排除，返回非 exercise 的编号项列表
（key / label / page / text）。
"""
import os
import sys
import json
import re
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

from data.book_structure.book_structure import BookStructure

from key_parse import keys_in_md, _first_num
from verify.script.ordinal import int_to_roman
from verify_config import (ORDINAL_EN, ORDINAL_EN3, ORDINAL_GM, ORDINAL_ROMAN,
                           ORDINAL_HUM, ORDINAL_APP, _canon_label)


TYPE_TO_LABEL = {
    'definition': '定义', 'theorem': '定理', 'lemma': '引理',
    'corollary': '推论', 'proposition': '命题', 'example': '例',
    'remark': '评注', 'uncat': 'uncat',
    'algorithm': '算法', 'property': '性质',
    # Ross 体例（ORDINAL_ROSS）：Axiom 条目独立 type，规范标签 公理，
    # 与 key_parse._canon_label('Axiom') 对齐。
    'axiom': '公理',
}


#: 附录字母章号条目键（`ORDINAL_APP` / type 13）：首字母章位 + 节号 + 条目号，
#: 分隔符与正文一致走通配集（点 / 连字符 / 全角变体）。
_APP_ITEM_RE = re.compile(
    r'^([A-Za-z])[.\-－．·–〜](\d+)[.\-－．·–〜](\d+)(?![\d.\-－．·–〜])')


def read_structure_items(ext_dir, ch, primary_type=None):
    """读分章契约，定位章节节点，展平为非 exercise 的编号项列表。

    返回 None 表示 JSON 不存在/损坏；返回 list（可能为空）表示已采用 JSON 路径。
    exercise / chapter / section 节点被排除。

    `primary_type`（可选）= `BookConfig.primary_type`。仅当它是
    `ORDINAL_APP`（13，附录字母章号体例）时启用「字母章位」键规范化
    （`A.1.1` → `定义A.1-1`）；其余取值 / 缺省一律走既有逻辑，零回归。
    🔴 该分支**必须**由 `primary_type` 显式开启：`I.2-13` 这类罗马章号键
    （Gelfand–Manin）在字形上与 `A.1-1` 同构，无类型闸门会被误判成附录键。
    """
    bs = BookStructure.load(ext_dir)
    if bs is None:
        return None
    nodes = bs.chapter_items(ch)
    if not nodes:
        return []
    items = []
    for n in nodes:
        # Canonicalize the structure key into the SAME key space that
        # `keys_in_md` emits for the .md, so the A-layer truly-missing / extra
        # comparison intersects 1:1.
        #
        # * Three-level books (ORDINAL_THREE_LEVEL, e.g. Kreyszig) store item
        #   keys as '1.1-1' (section-item, dash) and `keys_in_md` emits them
        #   BARE ('1.1-1') — no label.  The legacy code applied
        #   `TYPE_TO_LABEL + \d+(?:\.\d+)*`, which (a) prepended the label and
        #   (b) only captured the dotted section path, dropping the dash item
        #   component.  That produced '定义1.1' AND collapsed every item in a
        #   section into one key, so NOTHING matched the bare md keys and the
        #   whole chapter was falsely reported truly-missing + extra.  For any
        #   key whose numeric path carries a dash ('N.S-N') we now emit the bare
        #   dash form, normalized from any wildcard separator.
        # * Two-level / EN / EN3 books keep the legacy label-prefixed, dotted
        #   behavior ('定义1.1' / 'Remark1.1.1'), which already matches
        #   `keys_in_md`'s output for those ordinals (their keys have no dash).
        raw = (n.key or n.name or '')
        # ORDINAL_APP (type 13)：附录字母章号 `A.1.1` → 规范键 `定义A.1-1`
        # （与 key_parse.keys_in_md 的 ORDINAL_APP 分支同构）。必须先于下面的
        # 「首个数字串」通用分支，否则 `A.1.1` 会被截成 `1.1` 而丢掉字母章位。
        if primary_type == ORDINAL_APP:
            _am = _APP_ITEM_RE.match(raw.strip())
            if _am:
                _canon = (TYPE_TO_LABEL.get(n.type, 'uncat')
                          + f"{_am.group(1).upper()}.{_am.group(2)}-{_am.group(3)}")
                items.append({
                    'key': _canon,
                    'label': TYPE_TO_LABEL.get(n.type, 'uncat'),
                    'page': n.page_start,
                    'text': n.name,
                })
                continue
        # ORDINAL_HUM (Humphreys GTM 9): keys use English labels with § prefix
        # (e.g. "Theorem §4.1", "Lemma §10.2B"). The markdown uses bare labels
        # without numbers (**Theorem**: / **Corollary A**:), so strip the §+number
        # and apply _canon_label to produce keys like "定理" / "推论 A" that
        # keys_in_md's ENTRY_RE_HUM can match.
        if '§' in raw:
            # Extract letter suffix before stripping (e.g. "Lemma §10.2B" -> "B")
            _letter_m = re.search(r'§\s*\d+(?:\.\d+)*([A-Za-z])', raw)
            _letter = _letter_m.group(1) if _letter_m else ''
            # Extract slot-suffix (e.g. "Corollary §10.2-2" -> "-2")
            _slotsuffix_m = re.search(r'§\s*\d+(?:\.\d+)*-([\d]+)', raw)
            _slotsuffix = f"-{_slotsuffix_m.group(1)}" if _slotsuffix_m else ''
            # Extract number suffix for examples (e.g. "Example §22.4-1" -> "1")
            _exnum_m = re.search(r'§\s*\d+(?:\.\d+)*-(\d+)$', raw)
            _exnum = _exnum_m.group(1) if _exnum_m else ''
            # Extract appendix marker (e.g. "Lemma §23.App" -> "App")
            _app_m = re.search(r'§\s*\d+\.(App\w*)', raw)
            _app = _app_m.group(1) if _app_m else ''
            _label = re.sub(r'§\s*\d+(?:\.\d+)*[A-Za-z]?(?:-[\d]+)?(?:\.\w+)?', '', raw).strip()
            _label = re.sub(r'\s+', ' ', _label)
            _canon = _canon_label(_label)
            if _letter:
                _canon = f"{_canon} {_letter.upper()}"
            elif _exnum:
                _canon = f"{_canon}{_exnum}"
            elif _app:
                _canon = f"{_canon} {_app}"
            elif _slotsuffix:
                _canon = f"{_canon}{_slotsuffix}"
        # Ross 体例（ORDINAL_ROSS）：字母位键 "Example 2a" —— 规范键保留字母位
        # （例2a）。通用分支的 `\d+(?:[.\-…]\d+)+` 会把字母截掉（例2），与 md 侧
        # key_parse 的 例2a 永不交集 → 整书例题假性 truly-missing。故先试
        # 「标签 + 数字 + 单字母」形态，命中则直接用 公理/例/命题 规范标签。
        else:
            _ross_m = re.match(r'^[A-Za-z]+\s+(\d{1,2}(?:\.\d{1,3})?)([A-Za-z])$', raw.strip())
            if _ross_m:
                _canon = TYPE_TO_LABEL.get(n.type, 'uncat') + _ross_m.group(1) + _ross_m.group(2).lower()
            else:
                m = re.search(r'\d+(?:[.\-．·－–]\d+)+', raw)
                if not m:
                    m = re.search(r'\d+', raw)
                num_raw = m.group(0) if m else ''
                if '-' in num_raw:
                    # Three-level: emit bare dash form ('1.1-1'), no label.
                    _canon = _normalize_threelevel(num_raw)
                else:
                    _num = re.search(r'\d+(?:\.\d+)*', num_raw)
                    _number = _num.group(0) if _num else ''
                    _canon = TYPE_TO_LABEL.get(n.type, 'uncat') + _number
        items.append({
            'key': _canon,
            'label': TYPE_TO_LABEL.get(n.type, 'uncat'),
            'page': n.page_start,
            'text': n.name,
        })
    return items


def _normalize_threelevel(s):
    """Normalize a three-level numeric path to bare dash form 'N.S-N',
    regardless of the original separators (dots / dashes / fullwidth)."""
    parts = re.split(r'[.\-－．]', s)
    parts = [p for p in parts if p]
    if len(parts) >= 3:
        return f'{parts[0]}.{parts[1]}-{parts[2]}'
    return s


def md_keys_for_chapter(md_file, cfg, ch):
    """返回某章在 md 中出现过的 (entry_keys, all_keys)，已按章过滤。

    这是 EXTRACT 子流程层与 check_structure_completeness 公共脚本共用的
    「md 键集」取数缝，从 data_provider.ExtractLayer.run 抽出，避免公共
    编排脚本反向依赖 data_provider 子流程内部函数。
    """
    if cfg.primary_type in (ORDINAL_GM, ORDINAL_ROMAN):
        entry_keys, all_keys = keys_in_md(
            md_file, groups=cfg.ordinal, chapter_roman=int_to_roman(ch), chapter=ch)
    else:
        # chapter=ch：带显式异章限定词（of Chap. X / 第X章…）的正文提及不进
        # all_keys，A 层 EXTRA 不再被跨章引用刷屏（详见 key_parse._is_foreign_chapter_ref）。
        entry_keys, all_keys = keys_in_md(md_file, groups=cfg.ordinal, chapter=ch)
    # Chapter-scoping of md keys: only valid when the first number of a key
    # IS the chapter (chapter_first == True).  For chapter_first == False
    # books (e.g. Karlin & Taylor, where `Theorem 3.1` = §3 item 1 and `Example 2`
    # = chapter-2 example 2 — neither carries a chapter digit), the .md file is
    # already chapter-scoped, so applying `_first_num(k) == ch` would wrongly
    # drop every two-level key (first number == section) and every single-level
    # example whose item number ≠ chapter.  Skip the filter in that case.  This
    # mirrors the correct handling in check_structure_completeness.scan_raw_items
    # (the `if chapter_first and first != ch` guard).
    #
    # 🔴 2026-08-26 fix: 单层键（无点分隔符，如 `例1`、`Remark 2`）的首数是
    # 条目号而非章号，chapter_first 过滤会把它们全部误删（例1→首数1≠3→丢弃）。
    # 仅对点分两层键（`定理3.3`、`命题3.7`）应用章过滤；单层键不过滤。
    if cfg.primary_type in (ORDINAL_EN, ORDINAL_EN3) and cfg.chapter_first:
        entry_keys = {k for k in entry_keys if '.' not in k or _first_num(k) == ch}
        all_keys = {k for k in all_keys if '.' not in k or _first_num(k) == ch}
    return entry_keys, all_keys
