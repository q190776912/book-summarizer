"""verify/script/structure_io.py — 统一消费 extract/structure 产物 book_structure.json（SSOT）。

从 verify/data_provider/script/data_provider.py 抽出的纯数据读取逻辑；
不再依赖抽取管线代码，仅读取其产物 JSON 文件（单文件书对象，由
``data/book_structure/book_structure.py`` 的 BookStructure 模型加载）。
exercise / chapter / section 节点被排除，返回非 exercise 的编号项列表
（key / label / page / text）。
"""
import os
import sys
import json
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
from verify_config import ORDINAL_EN, ORDINAL_GM, ORDINAL_ROMAN


TYPE_TO_LABEL = {
    'definition': '定义', 'theorem': '定理', 'lemma': '引理',
    'corollary': '推论', 'proposition': '命题', 'example': '例',
    'remark': '评注', 'uncat': 'uncat',
}


def read_structure_items(ext_dir, ch):
    """读 book_structure.json，定位章节节点，展平为非 exercise 的编号项列表。

    返回 None 表示 JSON 不存在/损坏；返回 list（可能为空）表示已采用 JSON 路径。
    exercise / chapter / section 节点被排除。
    """
    bs = BookStructure.load(ext_dir)
    if bs is None:
        return None
    nodes = bs.chapter_items(ch)
    if not nodes:
        return []
    items = []
    for n in nodes:
        items.append({
            'key': n.key,
            'label': TYPE_TO_LABEL.get(n.type, 'uncat'),
            'page': n.page_start,
            'text': n.name,
        })
    return items


def md_keys_for_chapter(md_file, cfg, ch):
    """返回某章在 md 中出现过的 (entry_keys, all_keys)，已按章过滤。

    这是 EXTRACT 子流程层与 check_structure_completeness 公共脚本共用的
    「md 键集」取数缝，从 data_provider.ExtractLayer.run 抽出，避免公共
    编排脚本反向依赖 data_provider 子流程内部函数。
    """
    if cfg.primary_type in (ORDINAL_GM, ORDINAL_ROMAN):
        entry_keys, all_keys = keys_in_md(
            md_file, groups=cfg.ordinal, chapter_roman=int_to_roman(ch))
    else:
        entry_keys, all_keys = keys_in_md(md_file, groups=cfg.ordinal)
    if cfg.primary_type == ORDINAL_EN:
        entry_keys = {k for k in entry_keys if _first_num(k) == ch}
        all_keys = {k for k in all_keys if _first_num(k) == ch}
    return entry_keys, all_keys
