"""unit_order.py — U 层：总结单元「结构阅读顺序」校验（步骤 8 合并后终检）。

与 gate_units 章级闸 ⑪ 复用同一核心实现 ``lib/unit_order.check_unit_order``，是
「合并前门控」之后的**常跑安全网**：门控（步骤 5）可被跳过或单元事后被改，
verify_chapter --all（步骤 8）每次都会跑，故在此再断言一次合并顺序正确。

真值 = 分章契约节点的 ``page_start``（源书物理页序）；被测顺序 = 该章**源单元 manifest
的 units 数组**（``merge_units`` 严格以此顺序拼接，故 manifest 顺序 == 合并 md 阅读
顺序）。译文单元由 ``check_translate_parity`` 保证与源 manifest 索引逐条对齐，源有序
⇒ 译有序，故本层统一以源 manifest 为准（同一章的中/英两份 md 各报一次相同问题，属预期
的双重呈现）。

判据（细节见 lib/unit_order.py）：页码单调不减、相等允许、章末 dash 习题（``N-M``）
豁免、锚点缺失单元跳过。契约 / manifest 任一缺失 → 静默返回 []（无从判真值不误报）。

**两条被测顺序**（同一套锚点判据，``_monotonic_problems`` 单实现）：
* ``unit_order_problems`` = 源 manifest 的 ``units`` 数组顺序（合并前自证，原有口径）；
* ``md_order_problems``   = **交付 md 文本里实际读到的**单元顺序（缺陷① 根治，2026-10-23）——
  manifest 转绿只证明「拼接时次序对」，证明不了「交付 md 现在次序对」：收官书的交付侧
  普遍在合并之后做过内容级修订（整块搬移 / 单元换文件 / 按节拆文件后按节号重排），
  茆诗松《概率论与数理统计教程》实测就是靠镜像交付 md 修好的顺序，而本层当时一片绿。
  每条单元的身份（契约节点 / 页码 / 前序）仍按 manifest 顺序解析，只有**先后**换成
  「该单元正文在交付文本里的偏移」（``lib/unit_order.md_unit_positions``）。
  🔴 定位不到的单元跳过 = 宁可不测不误报，所以本层同时输出 ``md_order_stats``
  （located / expected / coverage），零覆盖绝不显示成通过。

🔴 命名：核心模块在 ``lib/unit_order.py``，本层目录亦名 ``unit_order``；两者 import 名
冲突（boot 把 lib 与 verify/**/script 都注入 sys.path）。故一律用包路径
``from lib.unit_order import …`` 取核心，避免 `import unit_order` 解析到本层自身。
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

from verify.script.base import VerifyLayer, LayerResult
from data.book_structure.book_structure import (
    chapter_json_path, unit_dir_name, prime_chapter_kinds)
from lib.unit_markers import is_unit_marker_line
from lib.unit_order import (check_delivered_order, check_unit_order,
                            md_unit_positions, norm_text)

#: 源语言单元目录（``units``）与翻译单元目录（``units-translate``）；与
#: ``merge_units --units-dir`` 的取值同一份拼写。
UNITS_SUBS = ("units", "units-translate")


def _units_dir(ext, ch, units_sub="units"):
    return os.path.join(os.path.dirname(chapter_json_path(ext, ch) or ""),
                        units_sub, unit_dir_name(ch))


def _read_manifest(units_dir):
    """``(units 列表 | None, manifest dict | None)``——缺文件 / 坏 JSON 一律 None。"""
    mpath = os.path.join(units_dir, "manifest.json")
    if not os.path.exists(mpath):
        return None, None
    try:
        with open(mpath, encoding="utf-8") as f:
            man = json.load(f)
    except Exception:
        return None, None
    return (man.get("units") or []), man


def _locate(ext, ch, units_sub="units"):
    """返回 (contract_dict_or_None, units_list_or_None)。契约/清单任一缺失 → (None, None)。"""
    cpath = chapter_json_path(ext, ch)
    if not cpath or not os.path.exists(cpath):
        return None, None
    units, _man = _read_manifest(_units_dir(ext, ch, units_sub))
    if units is None:
        return None, None
    try:
        with open(cpath, encoding="utf-8") as f:
            contract = json.load(f)
    except Exception:
        return None, None
    return contract, units


def _md_lang(md_file):
    """本 md 组的语种（cn/en/None）。判据单源 ``verify_chapter._group_lang``（延迟导入
    避免 verify_chapter ↔ 层注册的循环导入，与 report.py 同一手法）；取不到 → None。"""
    try:
        from verify.script.verify_chapter import _group_lang
        return _group_lang([md_file])
    except Exception:
        return None


def _pick_units_sub(ext, ch, lang):
    """交付 md 语种 → 该语种单元的 manifest 目录名（无匹配 → ``units`` = 旧口径）。

    源版 md 由 ``units`` 拼出、译版 md 由 ``units-translate`` 拼出（同一 ``merge_units``，
    语种取自各自 manifest 的 ``language``），所以「拿哪一侧单元去交付文本里定位」必须按
    语种配对：拿英文单元正文在中文交付 md 里找，结果只会是整章定位失败 = 假绿。
    """
    if lang:
        for sub in UNITS_SUBS:
            _units, man = _read_manifest(_units_dir(ext, ch, sub))
            if _units and str((man or {}).get("language") or "").strip().lower() == lang:
                return sub
    return "units"


def _unit_bodies(units_dir, units):
    """每条单元文件的**正文**（首行标记剥掉、空白归一化后的非空行序列）。

    与 ``merge_units._read_body`` 同一口径（首行 ``<!-- book-summarizer … unit: … -->``
    是登记处抄本、不进交付 md），标记识别单源 ``lib/unit_markers``。
    """
    out = []
    for u in units:
        fn = (u or {}).get("file") if isinstance(u, dict) else None
        p = os.path.join(units_dir, fn) if fn else None
        if not p or not os.path.exists(p):
            out.append([])
            continue
        try:
            with open(p, encoding="utf-8") as f:
                raw = f.read().split("\n")
        except Exception:
            out.append([])
            continue
        if raw and is_unit_marker_line(raw[0]):
            raw = raw[1:]
        out.append([norm_text(l) for l in raw if norm_text(l)])
    return out


class UnitOrderLayer(VerifyLayer):
    code = 'U'
    name = 'unit-order'
    order = 18               # 在 Q (17) 之后；纯顺序复检，与其它层无数据依赖
    auto_fixable = False     # 顺序错乱是结构缺陷，修复=重排单元，不可盲目自动改
    depends_on = []

    def run(self, ctx):
        ext = ctx.ext_dir
        try:
            prime_chapter_kinds(ext)   # 让 unit_dir_name 正确区分附录/章
        except Exception:
            pass
        contract, units = _locate(ext, ctx.ch)
        problems = check_unit_order(contract, units) if (contract and units) else []
        md_problems, md_stats = [], {}
        if contract and units:
            md_problems, md_stats = _delivered_order(ext, ctx.ch, ctx.md_file, contract)
        return LayerResult(code=self.code, metadata={
            'unit_order_problems': problems,
            'md_order_problems': md_problems,
            'md_order_stats': md_stats})


def _delivered_order(ext, ch, md_file, contract):
    """按**文件路径**跑交付顺序复检（verify 层入口，`ctx.md_file` 已是合并视图）。"""
    try:
        with open(md_file, encoding="utf-8") as f:
            md_text = f.read()
    except Exception:
        return [], {}
    return _delivered_order_text(ext, ch, md_text, _md_lang(md_file), contract)


def _delivered_order_text(ext, ch, md_text, lang, contract):
    """交付 md **文本**自身顺序复检 → ``(problems, stats)``。

    ``lang``：本段文本的语种（cn/en/None），决定拿哪一侧单元目录正文去定位
    （见 :func:`_pick_units_sub`）。文本由调用方给出，是因为按节拆分的章在 verify 里
    先并成 `._verify_merged_*` 视图——判据测的就是那份读者实际读到的拼接文本。
    """
    stats = {}
    sub = _pick_units_sub(ext, ch, lang)
    m_units, _man = _read_manifest(_units_dir(ext, ch, sub))
    # 🔴 被测序列 = **本语种那一侧**的 manifest 记录：单元身份（契约节点 / 页码 / 前序）
    # 的出现序消费依赖顺序，而译版的单元顺序可以与源版不同（Kreyszig ch4 实测两侧文件
    # 集合相同、D-注与节标题先后差 26 位），中文交付 md 的真实拼接序就是译版 manifest 顺序。
    if not m_units:
        return [], stats
    bodies = _unit_bodies(_units_dir(ext, ch, sub), m_units)
    positions = md_unit_positions(bodies, md_text)
    # `merge:false` 单元按书写要求（V-I 集中习题块省略）本就不进交付 md →
    # 既不该被定位，也不该进覆盖率分母（否则每本省略习题的书都显示「覆盖不足」）。
    expected = [i for i, u in enumerate(m_units)
                if isinstance(u, dict) and u.get("merge") is not False]
    located = [i for i in expected if positions[i] is not None]
    stats = {"units": len(m_units), "expected": len(expected),
             "located": len(located), "units_dir": sub,
             "coverage": (round(100.0 * len(located) / len(expected), 1) if expected else 100.0),
             "unlocated": ["%s«%s»" % ((m_units[i].get("type") or "?"),
                                       str(m_units[i].get("key") or ""))
                           for i in expected if positions[i] is None]}
    if not expected:
        return [], stats
    return check_delivered_order(contract, m_units, positions), stats

