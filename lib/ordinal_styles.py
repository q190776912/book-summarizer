"""Ordinal numbering-style classes for book-summarizer.

把当前「一个 ``type`` 整数 + 一堆平行字典（``ORDINAL_DEPTH`` / ``ORDINAL_NAME``
/ ``ORDINAL_CODES``）+ ``keys_in_md`` 里巨大的 ``if t == …`` 分发」重构成一个小
**类层级**：每一种编号体例是一个类，自己持有 ``code``、``depth``、正则*判别式*
（``entry_re`` / ``prose_re``）与*判断*方法（``judge`` / ``extract``）。具体风格
通过 ``__init_subclass__`` 自注册进 ``OrdinalStyle._REGISTRY``，用
``OrdinalStyle.get(code)`` 取实例。

本模块是 **PILOT**——实现 **0 / 1 / 2 / 3 / 8 / 12 / 13 / 14** 八种；type 12
（hum）为「label + 单字母序标、label 可在字母前后」的 Humphreys 体例。其余 code
（4, 9, 10, 11）仍走旧字典 + ``keys_in_md`` 分发，等对应类落地再迁移。
每个注册类都
会在定义时与 ``config/verify_config`` 的权威 ``ORDINAL_*`` 表交叉校验
（``code`` ∈ ``ORDINAL_CODES``、``depth`` == ``ORDINAL_DEPTH[code]``、
``name`` == ``ORDINAL_NAME[code]``），两套真源永不允许漂移。

正则判别式用与现管线**完全相同**的共享原语构造（``lib.regexlib.SEP_TIGHT``、
``key_parse.COMBINED_LABEL_KINDS``、``verify_config._canon_label``），所以一个
``OrdinalTwoLevelCN`` 实例产出的规范键与今天 ``keys_in_md(..., ordinal=2)``
逐字节一致——见同目录 demo 的等价性断言。

⚠️ type 3（``OrdinalThreeLevelCN``）**已改为标签感知 + 双向**，旧管线默认分支用
纯数字 ``regexlib.ENTRY_RE`` 会误收 ``**1.1.1**`` 这种节标题为条目；此处要求条头
**必须带标签**（定义/定理/引理…），且标签↔序标顺序可互换，但规范键仍保持纯数字
（``1.3-4``）以兼容中文三级书「契约键纯数字、标签另存 manifest.tags」的现状。

末位后缀：各类型均支持在末位数字后追加**小节字母 / 星号**子标记（如 ``12.1.1a``、
``12.1.1b``、``12.1.1*``），后缀原样追加到规范键末位（``12.1-1a`` / ``12.1-1*``）。
字母后缀允许前导空格（``12.1.1 a``）；星号后缀须后随 ``**``（即整体 ``***``）才判定
为后缀，以此与加粗闭合的纯 ``**`` 区分——``**定理12.1.1**`` 不会误带 ``*``。
``detect_scope`` 只读数字段（``re.findall(r'\\d+')``），后缀天然被忽略，不影响计数器
重置判定。
"""
import re
from typing import Dict, Iterable, List, NamedTuple, Optional, Type

# 技能 bootstrap：无论入口脚本是谁，保证 `verify_config` / `key_parse` 可解析。
import lib.boot as _boot
_boot.setup()

from lib.regexlib import SEP_TIGHT, SEP_SPLIT_RE
from key_parse import COMBINED_LABEL_KINDS, normkey
from verify_config import (
    ORDINAL_APP, ORDINAL_APP2, ORDINAL_CODES, ORDINAL_DEPTH, ORDINAL_NAME,
    ORDINAL_VAKIL, ORDINAL_HUM, _canon_label, SCOPE_BOOK, SCOPE_CHAPTER, SCOPE_SECTION,
)

# ---------------------------------------------------------------------------
# Separator-tolerant canonical-key normalizer (single source of truth)
# ---------------------------------------------------------------------------
# 真实书籍的序标段间分隔符不固定：``.`` / ``-`` / ``–`` / ``·`` / ``/`` / ``．`` /
# ``－`` / ``〜`` / ASCII ``~`` / OCR 下划线 ``_`` 等可任意替换。本函数把**任意
# 分隔符**的裸序标路径归一为与 md 侧（``OrdinalStyle`` 各子类 ``canon_key``）完全一致的
# 规范键：
#   * 3（及更多）段 → 裸横线型 ``N.S-N``（三级，无标签，对齐 OrdinalThreeLevelCN）
#   * 2 段          → ``<规范标签>.N.N``（两级，带标签，对齐 OrdinalTwoLevelCN）
#   * 1 段          → ``<规范标签>.N``（单级，对齐 OrdinalSingle）
# 此函数是供契约侧（verify/script/structure_io.read_structure_items 通用分支）接入时
# 代替其「``num_raw`` 含 '-' 即判三级」的错误启发式 + 过窄的
# ``_normalize_threelevel`` 切分集，从而让「标点可替换」在 契约↔md
# 校验端也成立（pilot 接入管线前的必要前提）。
def normalize_ordinal(num_raw, label=''):
    r"""把含任意分隔符的序标数字路径归一为规范键。

    ``num_raw`` 为纯数字路径串（如 ``'1.1.1'`` / ``'1-1-1'`` / ``'1·1·1'``）；
    ``label`` 为显式规范标签（契约侧由 ``TYPE_TO_LABEL[type]`` 提供，中文书
    三级传空串以产出裙横线键）。段数按 ``SEP_SPLIT_RE``（含全部
    通配分隔符）切分判定，不依赖某个固定分隔符。
    """
    parts = [p for p in SEP_SPLIT_RE.split(num_raw or '') if p and p.isdigit()]
    if len(parts) >= 3:
        return f"{parts[0]}.{parts[1]}-{parts[2]}"
    if len(parts) == 2:
        return f"{label}{parts[0]}.{parts[1]}"
    if len(parts) == 1:
        return f"{label}{parts[0]}"
    return num_raw or ''



ORDINAL_UNNUMBERED = 0


class OrdinalProfile(NamedTuple):
    """一次 ordinal 分析的结果：形式（风格实例）+ 数据派生的计数器重置窗口。

    ``style`` 由条头串的形态判定（``detect_style``）；``scope`` 由提取出来的序标
    末位重置行为判定（``detect_scope``）——二者解耦，scope 不再由 type 反查。
    """
    style: Optional['OrdinalStyle']
    scope: int


class OrdinalStyle:
    """一种 ordinal 编号体例的基类。

    子类约定（每个具体风格必须声明）：
      * ``code``      —— ``ORDINAL_*`` 整数，必须 ∈ ``ORDINAL_CODES``。
      * ``depth``     —— 数字分量段数，必须 == ``ORDINAL_DEPTH[code]``。
      * ``name``      —— 短风格名，必须 == ``ORDINAL_NAME[code]``。
      * （``scope`` **不再**作为类属性）计数器重置窗口（book/chapter/section）
                        不再是 type 的派生量、也不再写死在本类——它由*提取出来的序标
                        末位重置行为*决定，见类方法 ``detect_scope`` / ``analyze``。
                        旧 ``SCOPE_BY_TYPE[type]`` 的「三级书必节级」假设会漏掉
                        「三级书但末位跨章连续」的真实体例。
      * ``entry_re``  —— 匹配**加粗条头**的正则（**Label N…**）；``judge`` /
                        ``extract`` 的主判别式。
      * ``prose_re``  —— 匹配散文 / 交叉引用的正则（无加粗）。

    ⚠️ 关于「语言」：本类层级**刻意不设** ``language`` 字段。一个风格吃哪些标签
    完全由 ``entry_re`` / ``prose_re`` 的标签词表决定，而词表本就是中英混排
    （如 ``COMBINED_LABEL_KINDS``、type 2 的硬编码标签同时含 ``定义/定理`` 与
    ``Definition/Theorem``）。    旧 ``type`` 整数「语言」那一条轴，在此被正则判别式
    自然吸收，不再是独立维度——这也是当初要拆类层级的原因。

    ⚠️ 关于「scope（计数器重置窗口）」：本类层级**刻意不设** ``scope`` 类属性。
    它是*数据派生量*，不是 type 的派生属性——一个三级（type 3）书完全可能让末位
    编号跨章连续（第一章 1–20、第二章 21–40 …），此时真实 scope 是 **book 级（1）**，
    而非 ``SCOPE_BY_TYPE[3]=3`` 的节级。判定见 ``detect_scope``：直接看序标末位在
    全书范围内的重置层级，与 type 彻底解耦；``analyze`` 把形式判定（``detect_style``）
    与 scope 判定（``detect_scope``）打包成 ``OrdinalProfile(style, scope)`` 一次给出。
    若已有显式的 ``(type, scope)``（如从 ``verify_config`` 迁移），用备选构造函数
    ``from_type_scope(type, scope)`` 直接生成一个绑定了 scope 的实例。

    行为：
      * ``judge(text)``       —— ``text`` 是否含本风格的加粗条头（核心*判断*方法）。
      * ``match_entry(text)`` —— 底层 ``entry_re`` 的 Match（或 None）。
      * ``extract(text)``     —— ``text`` 中首个本风格条头的规范键（或 None）。
      * ``canon_key(*parts)`` —— 由数字分量组成本风格的规范键（子类自定义分量顺序/分隔）。
    """
    code: int = 0
    depth: int = 0
    name: str = ''
    entry_re: Optional[re.Pattern] = None
    prose_re: Optional[re.Pattern] = None

    _REGISTRY: Dict[int, Type['OrdinalStyle']] = {}

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        if cls.code in cls._REGISTRY:
            raise TypeError(
                f"ordinal 风格 code={cls.code} 已被 "
                f"{cls._REGISTRY[cls.code].__name__} 注册，不可重复。")
        if cls.code not in ORDINAL_CODES:
            raise ValueError(
                f"{cls.__name__}.code={cls.code} 不在 ORDINAL_CODES"
                f"（合法码 {sorted(ORDINAL_CODES)}）。")
        if cls.depth != ORDINAL_DEPTH.get(cls.code):
            raise ValueError(
                f"{cls.__name__}.depth={cls.depth} 与 ORDINAL_DEPTH"
                f"[{cls.code}]={ORDINAL_DEPTH.get(cls.code)} 不一致。")
        if cls.name != ORDINAL_NAME.get(cls.code):
            raise ValueError(
                f"{cls.__name__}.name={cls.name!r} 与 ORDINAL_NAME"
                f"[{cls.code}]={ORDINAL_NAME.get(cls.code)!r} 不一致。")
        cls._REGISTRY[cls.code] = cls

    def __init__(self, scope: Optional[int] = None):
        """每个实例可携带一个可选的 ``scope``（计数器重置窗口 1/2/3）。

        ``None``（默认）表示「未绑定」——scope 需后续从数据派生
        （``detect_scope`` / ``analyze``）。非 ``None`` 表示由调用方显式给定
        （``from_type_scope`` 配置驱动）。scope 永远是**显式入参或数据派生量**，
        **绝不**由 type 反查（旧 ``SCOPE_BY_TYPE[type]`` 假设已废弃）。
        """
        self.scope = scope


    @classmethod
    def get(cls, code: int) -> 'OrdinalStyle':
        """返回 ``code`` 的 fresh 实例（未实现的 code 抛 KeyError）。"""
        if code not in cls._REGISTRY:
            raise KeyError(
                f"ordinal 风格 {code} 尚未实现（已注册：{sorted(cls._REGISTRY)}）。"
                f"本次 pilot 覆盖 0/1/2/3/8/12/13/14。")
        return cls._REGISTRY[code]()

    @classmethod
    def from_type_scope(cls, type_code: int, scope: int) -> 'OrdinalStyle':
        """备选构造函数：根据 ``(type, scope)`` 生成一个**绑定了 scope** 的 OrdinalStyle 实例。

        - ``type_code`` 决定*形式*（段数 / 正则判别式）→ 从注册表取对应子类。
        - ``scope``    决定*计数器重置窗口*（``SCOPE_BOOK=1`` / ``SCOPE_CHAPTER=2`` /
                      ``SCOPE_SECTION=3``），作为实例属性绑定。

        ⚠️ 与 ``analyze`` 的区别：``analyze`` 是**数据派生**（从条头串 + 规范键推断
        scope）；本方法是**配置驱动**（scope 由调用方显式给出，例如从 ``verify_config``
        的 ``ordinal`` 数组 + ``SCOPE_BY_TYPE`` 迁移而来）。scope 在此是显式入参、
        不再由 type 反查——旧 ``SCOPE_BY_TYPE[type]`` 的「三级必节级」假设已废弃，
        调用方应对 scope 负责（或委托 ``detect_scope`` 从数据算出后传入）。

        ``scope`` 必须 ∈ {1, 2, 3}，否则抛 ``ValueError``；``type_code`` 未实现抛
        ``KeyError``。
        """
        if scope not in (SCOPE_BOOK, SCOPE_CHAPTER, SCOPE_SECTION):
            raise ValueError(
                f"scope={scope} 非法（应 ∈ "
                f"{{SCOPE_BOOK={SCOPE_BOOK}, SCOPE_CHAPTER={SCOPE_CHAPTER}, "
                f"SCOPE_SECTION={SCOPE_SECTION}}}）。")
        if type_code not in cls._REGISTRY:
            raise KeyError(
                f"ordinal 风格 {type_code} 尚未实现（已注册：{sorted(cls._REGISTRY)}）。"
                f"本次 pilot 覆盖 0/1/2/3/8/12/13/14。")
        return cls._REGISTRY[type_code](scope=scope)

    @classmethod
    def registered_codes(cls):
        return sorted(cls._REGISTRY)


    def match_entry(self, text: str, *, page: bool = False) -> Optional[re.Match]:
        """匹配本风格条头。

        ``page=False``（默认）→ 用 ``entry_re``（md 加粗 ``**`` 形态），供
        ``extract`` 抽键、对齐 ``keys_in_md``。
        ``page=True``        → 用 ``page_entry_re``（无 ``**`` 纯文本形态），供
        judge / classify / detect_style **识别类型**，对齐
        ``_detect_ordinal_from_pages`` 的 page 扫描。``page=True`` 时自动剥掉
        文本里的 ``**``，故同一方法既能吃 page OCR 纯文本，也能吃 md 加粗条头。
        """
        rx = self.page_entry_re if page else self.entry_re
        if rx is None:
            return None
        if page:
            text = text.replace('**', '')
        return rx.search(text)

    def judge(self, text: str, *, page: bool = False) -> bool:
        """判断 ``text`` 是否含本风格条头（**段数严格独立**）。

        默认 ``page=False``（md 加粗形态，供 extract 抽键校验）；识别类型时用
        ``page=True``（无 ``**`` 纯文本形态，对齐 page 扫描）。

        🔴 校验相互独立：本方法只接受「恰好 ``depth`` 段数字分量」的条头，**绝不**
        把更低或更高段数的头跨认——例如 type-3 的 judge 对 ``定理2`` / ``定义1.1``
        返回 False，type-2 的 judge 对 ``定理2`` 返回 False。这是靠各正则的段数
        独立性护栏（``_TAIL_GUARD`` 拒绝末位之后再接「数字 / 分隔符+数字」、
        ``_LEAD_GUARD`` 拒绝首位之前是「数字+分隔符」）实现的，re.search 不会在
        更长头的「前缀 / 末段组件」上误匹配。"""
        return self.match_entry(text, page=page) is not None

    def extract(self, text: str) -> Optional[str]:
        """从 ``text`` 抽取首个本风格条头的规范键；不含则返回 None。

        ⚠️ 用途：**md 抽键**（对齐 ``keys_in_md``）。``entry_re`` 是**带 ``**``
        的 md 加粗形态**，所以 ``extract`` 应喂 md 行（如 ``'**定义1.1**'``）。
        **识别类型**（从 page / 条头串判断风格）请用 ``judge(page=True)`` /
        ``classify`` / ``detect_style``，它们走无 ``**`` 的 ``page_entry_re``。

        默认实现取 ``entry_re`` 首个匹配、交给 ``canon_key`` 组键；子类按自身
        捕获组顺序覆盖 ``canon_key`` 即可。"""
        m = self.match_entry(text)
        if not m:
            return None
        return self.canon_key(*m.groups())

    def canon_key(self, *parts) -> str:
        raise NotImplementedError(f"{type(self).__name__} 必须实现 canon_key()")


    @classmethod
    def classify(cls, text: str) -> Optional['OrdinalStyle']:
        """给定一行 ``text``（一个**条头串**——page OCR 纯文本 *或* md 加粗条头），
        返回最匹配的已注册风格**实例**。

        ⚠️ 输入形态：本方法用于**识别书的 ordinal 类型**，对齐 make_config 的
        ``_detect_ordinal_from_pages`` —— 它吃的是 **page 纯文本块**（无 ``**``
        加粗）。因此这里用 ``judge(page=True)``：page 形态的纯文本判别式，并在
        输入带 ``**`` 时自动剥离，所以 **无论条头串来自 page（``定义1.1.1``）还是
        md（``**定义1.1.1**``）都能识别**。这正是与旧管线一致的正确入口——
        「识别类型」从 page 扫、不读 md。

        按 **code 降序**扫描已注册类型（更具体者优先；各 type 判断互斥，
        顺序不影响结果）；无一命中
        返回 None（unnumbered —— 无编号条目靠「编号风格都不中」判定）。

        ⚠️ 返回的是风格**实例**而非裸 int —— 调用方拿到即可直接 ``.extract(text)``，
        不必再 ``.get(code)`` 反查。本方法为 pilot：认识 0/1/2/3/8/12/13/14。
        """
        for code in sorted(cls._REGISTRY, reverse=True):
            if code == ORDINAL_UNNUMBERED:
                continue
            style = cls._REGISTRY[code]()
            if style.judge(text, page=True):
                return style
        return None


    @classmethod
    def detect_style(cls, headings: Iterable[str]) -> Optional['OrdinalStyle']:
        """给定一章 / 一篇的**全部条头串** ``headings``，返回其主导编号风格的**实例**。

        ⚠️ 输入形态：``headings`` 是**已抽出的条头串**——既可以是 page OCR 纯文本
        （``'定义1.1.1'``），也可以是 md 加粗条头（``'**定义1.1.1**'``）。本方法用
        ``judge(page=True)`` 识别，**自动兼容两种形态**。这正对齐原管线
        ``_detect_ordinal_from_pages`` 的 page 扫描（它从 page 纯文本块扫描、不读
        md）；make_config 未来可直接把抽出的条头串喂给本方法做 family-vote 决策，
        而不必自带一套段数投票。

        口径与 make_config 的 family-vote 一致：specificity-first（三级 > 二级 >
        单级）—— 统计每个已注册风格在 ``headings`` 中被 ``judge(page=True)`` 命中的
        次数，取命中最多、且 depth 最具体者。无任何风格命中则返回 None（无编号书，
        调用方据此省略 ordinal 组，而非编造 type 3）。

        pilot：对 0/1/2/3/8/12/13/14 生效；其余 code（4/9/10/11）落地对应
        子类后自动纳入。"""
        tally: Dict[int, int] = {}
        for h in headings:
            for code in sorted(cls._REGISTRY, reverse=True):
                if code == ORDINAL_UNNUMBERED:
                    continue
                if cls._REGISTRY[code]().judge(h, page=True):
                    tally[code] = tally.get(code, 0) + 1
                    break
        if not tally:
            return None

        best = max(tally, key=lambda c: (tally[c], cls._REGISTRY[c].depth))
        return cls._REGISTRY[best]()


    @staticmethod
    def _key_to_tuple(key: str):
        """规范键 → 纯数字分量元组（如 ``'1.1-1'``→(1,1,1)、``'定义1.1'``→(1,1)、
        ``'定理2'``→(2,)）。标签前缀与任意分隔符都被忽略，只认数字段。"""
        nums = re.findall(r'\d+', key or '')
        return tuple(int(n) for n in nums) if nums else None

    @classmethod
    def detect_scope(cls, keys: Iterable[str]) -> int:
        """根据**提取出来的序标（规范键）**判定计数器重置窗口（scope）。

        ⚠️ scope 不是由 type 决定的派生量（旧管线用 ``SCOPE_BY_TYPE[type]`` 反查，
        会漏掉「三级书但末位跨章连续编号」这类真实体例）。这里**直接看序标末位在
        全书范围内的重置行为**：

          * 末位全程单调不减（跨章/节从不回 1）→ 书级 ``SCOPE_BOOK`` (=1)：计数器
            全书连续，如「第一章 1–20、第二章 21–40 …」。
          * 末位在某层级分量变化时回 1 → 该层级即重置窗口：仅当首分量（章）变化
            时回 1 → 章级 ``SCOPE_CHAPTER`` (=2)；当次分量（节）变化时也回 1 →
            节级 ``SCOPE_SECTION`` (=3)。取全书观察到的**最细**（粒度最小、值最大）
            重置层级为准——「末位能在一个更细的层级重置」本身就证明计数器不是按更
            粗层级重置的。
          * 单级（depth=1）：序标只有一个数字分量，没有「节」层级可供重置，故末位若
            回退只能归因为**章级**重置（``k`` 恒为 0 → 章级）；若末位全程不减则推断
            为**书级**连续。无需特判，直接走下方通用重置检测（``last = 0``）。

        输入 ``keys`` 须为**文档序**的规范键集合（与 md 出现顺序一致）；乱序会误判
        重置。无编号（depth 0）书不应调用本方法。
        """
        tuples = [cls._key_to_tuple(k) for k in keys]
        tuples = [t for t in tuples if t]
        if not tuples:
            return SCOPE_CHAPTER
        depth = len(tuples[0])


        last = depth - 1
        reset_levels: List[int] = []
        prev = None
        for t in tuples:
            if len(t) != depth:
                prev = t
                continue
            if prev is not None and t[last] < prev[last]:

                k = 0
                while k < last and t[k] == prev[k]:
                    k += 1
                reset_levels.append(k + 2)
            prev = t
        if not reset_levels:
            return SCOPE_BOOK

        counts: Dict[int, int] = {}
        for lv in reset_levels:
            counts[lv] = counts.get(lv, 0) + 1
        return max(counts, key=lambda lv: (counts[lv], lv))

    @classmethod
    def analyze(cls, headings: Iterable[str],
                keys: Iterable[str] = ()) -> 'OrdinalProfile':
        """给定一章的**条头串**与**提取出来的规范键**（可独立提供），一次性给出
        ``OrdinalProfile(style, scope)``。

          * ``headings`` 决定*形式*（段数 / 正则）→ ``detect_style``；
          * ``keys``    决定*计数器重置窗口*（scope）→ ``detect_scope``。

        ⚠️ scope 与 type 解耦：即使形式是三级（type 3），只要 ``keys`` 显示末位跨
        章连续，scope 仍是 ``SCOPE_BOOK``（1），不会 blindly 套用节级——这正是旧
        ``SCOPE_BY_TYPE`` 修不了的真实体例。
        """
        style = cls.detect_style(headings)
        if style is None or style.depth == 0:
            return OrdinalProfile(style, SCOPE_CHAPTER)
        scope = cls.detect_scope(keys) if keys else SCOPE_CHAPTER
        return OrdinalProfile(style, scope)


# ---------------------------------------------------------------------------
# Type 0 —— unnumbered（未编号）
# ---------------------------------------------------------------------------
class OrdinalUnnumbered(OrdinalStyle):
    """未编号条目：条目不带任何数字分量（depth 0）。

    无数字判别式——``judge`` 永远 False（条目靠「其它编号风格都不中」判定为无编号）。
    ``extract`` 恒返回 None：无编号条目不产数字键。
    """
    code = ORDINAL_UNNUMBERED
    depth = 0
    name = ORDINAL_NAME[ORDINAL_UNNUMBERED]
    entry_re = None
    prose_re = None

    def judge(self, text):
        return False

    def extract(self, text):
        return None

    def canon_key(self, *parts):
        raise NotImplementedError("unnumbered 风格无编号键")


# ---------------------------------------------------------------------------
# Type 1 —— single（单级，单数字分量）
# ---------------------------------------------------------------------------
# 复用 COMBINED_LABEL_KINDS（中英标签单一来源），与 ENTRY_RE_EN_SINGLE_C 同构，
# 并补充「数字 + 标签」序标在前的反向形态：旧管线 type 1 只认标签在前；这里补齐
# 双向以便与 type 2/3 一致（负向断言仍拒绝两级 N.M，避免与两级键冲突）。
# 单一真源 COMBINED_LABEL_KINDS，按长度降序排列 —— 关键：``示例`` 必须排在 ``例`` 前、
# ``注记/评注/注释`` 必须排在 ``注`` 前，否则无空格形态（``**示例1.1**`` /
# ``**注释1.1**``）会被前缀标签抢匹配。set 去重，长度相同者顺序无关（不存在等长前缀冲突）。
_LABEL_ALT = '|'.join(sorted(set(COMBINED_LABEL_KINDS), key=len, reverse=True))




# 末位后缀（小节字母 / 星号）：某些书在末位数字后追加 ''a''、''b''、''*'' 等子标记，
# 例如 ''12.1.1a'' / ''12.1.1b'' / ''12.1.1*''。两种形态：
#   * 字母后缀 ``([a-z]+)``，允许前导空格（''12.1.1 a''）；
#   * 星号后缀 ``\*(?=\*\*)``——**须后随 ''**''（即整体 ''***''）才判定为后缀**，以此与
#     纯 ''**'' 闭合区分；否则 ''**12.1.1**'' 会被误判带 ''*'' 后缀。
# 规范键把后缀原样追加到末位数字分量之后（如 ''12.1-1a''）；``detect_scope`` 只读
# 数字段（``\d+``），后缀天然被忽略，不影响计数器重置判定。
_SUFFIX_RE = r'(?:\s*([a-z]+)|(\*(?=\*\*)))?'

# 段数独立性护栏：type-k 的 judge 只认「恰好 k 段数字分量」，不被更长头跨认。
#   * ``_TAIL_GUARD``：末位之后不能再接「数字」或「分隔符 + 数字」
#     （``定理12.1`` 不得被 type 1 认成单级）。
#   * ``_LEAD_GUARD``：首位之前不能是「数字 + 分隔符」（``1.2.3`` 的 ``2.3``
#     不得被认成二级），**也不能是「独立单字母 + 分隔符」**——附录字母章位
#     体例（type 13/14）的条头 ``A.1.1 Definition`` / ``B.2 Theorem`` 的数字
#     尾巴不得被 type 1/2 截走。内层 ``(?<![A-Za-z])`` 限定该字母是**独立
#     单字母**，故 ``cf.`` / ``No.`` / ``Fig.`` 这类多字母缩写不受影响。
#   * 第三条 ``(?!SEP[A-Za-z])``：末位之后也不能**紧贴**「分隔符 + 字母」——
#     type 8（``Exercise 2.3.A``）的字母序标尾巴不得被 type 2 截成
#     ``Exercise 2.3``。刻意**不允许分隔符与字母之间有空格**，故
#     ``Definition 1.1. Some text`` 这类「句点 + 空格」的普通句子不受影响。
_TAIL_GUARD = (r'(?!\d)(?!\s*' + SEP_TIGHT + r'\s*\d+)'
               r'(?!' + SEP_TIGHT + r'[A-Za-z])')
_LEAD_GUARD = (r'(?<!\d' + SEP_TIGHT + r')'
               r'(?<!(?<![A-Za-z])[A-Za-z]' + SEP_TIGHT + r')')

# --- page 形态判别式（无 markdown 加粗 ``**``） ---------------------------------
# 🔴 关键定位修正：原管线「识别书中 ordinal 类型」的入口是
# ``config/verify_config/make_config.py`` 的 ``_detect_ordinal_from_pages``，它
# 扫描的是 **page_*.json 的 OCR 纯文本块**（``blk_text`` 抽纯文本，**没有**
# ``**`` 加粗包裹），用的是 *纯文本* 正则（CN_THREE_RE / EN_THREE_RE /
# CN_TWO_RE / EN_TWO_RE / _build_label_heading_regexes）+ 位置护栏
# （HEADING_LEAD_MAX / _is_header_boundary / _is_crossref_prefix）——**不是**
# 从 md 加粗条头识别。
#
# 因此「识别类型」的判断方法（judge / classify / detect_style）必须吃 **page
# 纯文本形态（无 ``**``）**，与下面带 ``**`` 的 ``entry_re``（md 抽键用，对齐
# ``keys_in_md``）彻底解耦：
#   * ``page_entry_re``（无 ``**``）→ judge / classify / detect_style（识别类型，
#     对齐 page 扫描；judge 时自动剥掉文本里的 ``**``，故同一方法既能吃 page
#     OCR 纯文本，也能吃 md 加粗条头）。
#   * ``entry_re``（带 ``**``）→ extract（md 抽键，对齐 keys_in_md 逐字节等价）。
#
# page 形态同样双向 + 标签感知（type3 必须带标签，否则 ``1.1.1`` 这种节号会被
# 误判），段数特异度由 classify 的 depth 降序保证。CN 三级「标签紧贴编号」
# （原 type10 / cn3lab，已弃用并入 type3）在纯文本下与 type3 同形，故 detect_style
# 直接把它选为 type3（裸 ``C.S-N`` 键、丢按标签独立计数），不再单设探针
# （与 _detect_ordinal_from_pages 默认 type3 一致）。
_PAGE_RE_SINGLE = re.compile(
    r'(?:(' + _LABEL_ALT + r')\s*(\d+)' + _SUFFIX_RE +
    r'|' + _LEAD_GUARD + r'(\d+)' + _SUFFIX_RE + r'\s*(' + _LABEL_ALT + r'))'
    + _TAIL_GUARD, re.IGNORECASE)
_PAGE_RE_TWO = re.compile(
    r'(?:(' + _LABEL_ALT + r')\s*(\d+)' + SEP_TIGHT + r'(\d+)' + _SUFFIX_RE +
    r'|' + _LEAD_GUARD + r'(\d+)' + SEP_TIGHT + r'(\d+)' + _SUFFIX_RE + r'\s*(' + _LABEL_ALT + r'))'
    + _TAIL_GUARD, re.IGNORECASE)
_PAGE_RE_THREE = re.compile(
    r'(?:(' + _LABEL_ALT + r')\s*(\d+)' + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'(\d+)' + _SUFFIX_RE +
    r'|' + _LEAD_GUARD + r'(\d+)' + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'(\d+)' + _SUFFIX_RE + r'\s*(' + _LABEL_ALT + r'))'
    + _TAIL_GUARD, re.IGNORECASE)

_ENTRY_RE_SINGLE = re.compile(
    r'\*\*'
    r'(?:(' + _LABEL_ALT + r')\s*(\d+)' + _SUFFIX_RE +
    r'|' + _LEAD_GUARD + r'(\d+)' + _SUFFIX_RE + r'\s*(' + _LABEL_ALT + r'))'
    + _TAIL_GUARD,
    re.IGNORECASE)


class OrdinalSingle(OrdinalStyle):
    """单级编号（ORDINAL_SINGLE = 1）：条目仅一个数字分量。

    形如 ``**Theorem 1**`` / ``**定理2**``；无节.项拆分。规范键 = 规范中文标签 +
    数字（例：``定理2``）。与 keys_in_md 的 ORDINAL_SINGLE 分支同构。末位数字后
    可追加字母 / 星号子标记（``定理2a`` / ``定理2*``），作为后缀追加到规范键。
    """
    code = 1
    depth = 1
    name = ORDINAL_NAME[1]
    entry_re = _ENTRY_RE_SINGLE
    page_entry_re = _PAGE_RE_SINGLE

    prose_re = None

    def extract(self, text):
        m = self.match_entry(text)
        if not m:
            return None
        if m.group(1) is not None:
            label, num = m.group(1), m.group(2)
            suf = m.group(3) or m.group(4) or ''
        else:
            label, num = m.group(8), m.group(5)
            suf = m.group(6) or m.group(7) or ''
        return f"{_canon_label(label)}{num}{suf}"

    def canon_key(self, label, num, suffix=''):
        return f"{_canon_label(label)}{num}{suffix}"

    @staticmethod
    def _key_to_tuple(key):
        r"""type 1 规范键 → 分量元组，**保留末位字母后缀**（``例2a``→(2,1)）。

        基类 ``_key_to_tuple`` 用 ``re.findall(r'\d+')`` 会把字母后缀整个丢掉
        （``例2a`` / ``例2b`` 都折成 ``(2,)``），于是 Ross 类单级书「同一父号 2
        下的 2a/2b/2c 是三条不同序标」这一重置信号消失 —— ``detect_scope`` 误判
        书级、B 层稀疏号检查把它们当「编号 2 重复」误报。末位字母折成序号
        （a→1, b→2 …）后，2a<2b<2c<3a 才被正确识别为「父号级重置」，与
        Vakil/App 的字母折序号同思路。
        ⚠️ 无后缀时仍返回**单分量** ``(n,)``（而非 ``(n,0)``）——否则普通单级书
        （无后缀）会被逼成 depth=2，导致 ``detect_scope`` 末位恒 0、永远检测不到
        重置、scope 误判书级。后缀是*可选*的第二维，缺省时不强行凑维度。"""
        m = __import__('re').search(r'(\d+)\s*([a-z]+)?', key or '')
        if not m:
            return None
        n = int(m.group(1))
        suf = m.group(2)
        return (n,) if not suf else (n, ord(suf[0]) - ord('a') + 1)


# ---------------------------------------------------------------------------
# Type 2 —— two_level（中文二级，N.M 节.项）
# ---------------------------------------------------------------------------
# 标签词表复用 COMBINED_LABEL_KINDS（与 type 1/3 同一真源，含 注释/断言/猜想 等
# type 2 旧手写子集漏收的标签），并补充「数字 + 标签」序标在前的反向形态：旧
# ENTRY_RE_2 仅认标签在前，但 EN 两级书（如 Fraleigh "0.12 Definition"）实际印成
# 序标在前——旧管线靠 ORDINAL_EN 分支的 ENTRY_RE_EN_NF_C 覆盖；此处把同一反向形态
# 并入 type 2，使单风格自洽、不再依赖 type 4 分支救场。_LABEL_ALT 已按长度降序，
# 故 ``示例``/``注记`` 等不会被前缀 ``例``/``注`` 抢匹配（无空格形态也正确）。
_ENTRY_RE_TWO = re.compile(
    r'\*\*'
    r'(?:(' + _LABEL_ALT + r')\s*(\d+)' + SEP_TIGHT + r'(\d+)' + _SUFFIX_RE +
    r'|' + _LEAD_GUARD + r'(\d+)' + SEP_TIGHT + r'(\d+)' + _SUFFIX_RE + r'\s*(' + _LABEL_ALT + r'))'
    + _TAIL_GUARD + r'\s*(?:' + SEP_TIGHT + r')?\s*\*+',
    re.IGNORECASE)
_PROSE_RE_TWO = re.compile(
    r'(?<![A-Za-z0-9])'
    r'(?:(' + _LABEL_ALT + r')(?![A-Za-z])\s*(\d+)' + SEP_TIGHT + r'(\d+)(?:\s*([a-z]+))?'
    r'|(\d+)' + SEP_TIGHT + r'(\d+)(?:\s*([a-z]+))?\s*(' + _LABEL_ALT + r')(?![A-Za-z]))',
    re.IGNORECASE)


class OrdinalTwoLevelCN(OrdinalStyle):
    """中文二级编号（ORDINAL_TWO_LEVEL = 2）：节.项两段数字。

    形如 ``**定义1.1**`` / ``**定理3.2**``。规范键 = 规范中文标签 + ``.`` 连接的两段
    （例：``定义1.1``）。与 keys_in_md 的 ORDINAL_TWO_LEVEL 分支同构。末位（项）后
    可追加字母 / 星号子标记（``定义1.1a`` / ``定义1.1*``），作为后缀追加到规范键。
    """
    code = 2
    depth = 2
    name = ORDINAL_NAME[2]
    entry_re = _ENTRY_RE_TWO
    page_entry_re = _PAGE_RE_TWO
    prose_re = _PROSE_RE_TWO

    def extract(self, text):
        m = self.match_entry(text)
        if not m:
            return None
        if m.group(1) is not None:
            label, sec, num = m.group(1), m.group(2), m.group(3)
            suf = m.group(4) or m.group(5) or ''
        else:
            label, sec, num = m.group(10), m.group(6), m.group(7)
            suf = m.group(8) or m.group(9) or ''
        return f"{_canon_label(label)}{sec}.{num}{suf}"

    def canon_key(self, label, sec, num, suffix=''):
        return f"{_canon_label(label)}{sec}.{num}{suffix}"


# ---------------------------------------------------------------------------
# Type 3 —— three_level（中文三级，标签感知 + 双向，N.M.K → N.M-K）
# ---------------------------------------------------------------------------
# 🔴 关键修正：中文三级书**必须带条目标签**（定义/定理/引理…），否则 ``**1.1.1**``
# 这种纯数字加粗行会被误判为条目（实为节标题）。旧 keys_in_md 默认分支用
# regexlib.ENTRY_RE（纯数字、无标签）会漏掉这个区分——此处改为**标签感知 +
# 双向**（标签在前 / 序标在前皆可），但规范键仍保持纯数字（``1.3-4``），以兼容
# 中文三级书「契约键为纯数字、标签另存 manifest.tags」的现状（见 MEMORY：序标真值
# 按契约节点取）。prose 同样标签感知 + 双向。
_ENTRY_RE_THREE = re.compile(
    r'\*\*'
    r'(?:[^*]*?(' + _LABEL_ALT + r')[^*]*?(\d+)' + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'(\d+)' + _SUFFIX_RE +
    r'|' + _LEAD_GUARD + r'(\d+)' + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'(\d+)' + _SUFFIX_RE + r'[^*]*?(' + _LABEL_ALT + r')[^*]*?'
    r')'
    + _TAIL_GUARD + r'[^*]*\*+',
    re.IGNORECASE)
_PROSE_RE_THREE = re.compile(
    r'(?<![A-Za-z0-9])'
    r'(?:[^*]*?(' + _LABEL_ALT + r')[^*]*?(\d+)' + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'(\d+)(?:\s*([a-z]+))?'
    r'|(\d+)' + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'(\d+)(?:\s*([a-z]+))?[^*]*?(' + _LABEL_ALT + r')[^*]*?)',
    re.IGNORECASE)


class OrdinalThreeLevelCN(OrdinalStyle):
    """中文三级编号（ORDINAL_THREE_LEVEL = 3）：标签感知的三段数字。

    条头形如 ``**定理1.1.1**`` / ``**1.1.1 定理**``（标签与序标顺序可互换），且
    **必须带条目标签**——标签取自 ``_LABEL_ALT``（= ``COMBINED_LABEL_KINDS``）。
    ⚠️ 旧 ``regexlib.ENTRY_RE`` 是**标签无关**的（只要求加粗行里出现「数字 + 分隔
    符 + 数字 + 分隔符 + 数字」），因此 ``**1.1.1**``（节标题，误收）、
    ``**练习1.2.3**``、``**Exercise 2.3.1**``、``**第1.2.3节**`` 四类它**全都收**。
    本类改为标签感知后这四类**一起不收**（不只是纯数字）—— 其中 ``**练习1.2.3**``
    是真条目、属**减法**，登记为「与 legacy 的有意偏差」第 6 条。
    规范键 = normkey(token)
    （例：``1.3-4``），不带标签前缀，以兼容中文三级书「契约键纯数字、标签另存
    manifest.tags」的现状。末位（第三段）后可追加字母 / 星号子标记
    （``**定理12.1.1a**`` → ``12.1-1a``、``**定理12.1.1***`` → ``12.1-1*``），
    后缀原样追加到规范键末位。prose 同样标签感知 + 双向（字母后缀）。
    """
    code = 3
    depth = 3
    name = ORDINAL_NAME[3]
    entry_re = _ENTRY_RE_THREE
    page_entry_re = _PAGE_RE_THREE
    prose_re = _PROSE_RE_THREE

    def extract(self, text):
        m = self.match_entry(text)
        if not m:
            return None
        if m.group(1) is not None:
            a, b, c = m.group(2), m.group(3), m.group(4)
            suf = m.group(5) or m.group(6) or ''
        else:
            a, b, c = m.group(7), m.group(8), m.group(9)
            suf = m.group(10) or m.group(11) or ''
        return normkey(f"{a}.{b}.{c}") + suf

    def canon_key(self, a, b, c, suffix=''):
        return normkey(f"{a}.{b}.{c}") + suffix


# ---------------------------------------------------------------------------
# Type 8 —— vakil（EN 三级：标签在前 + 第三维**字母**序标，``Label C.S.A``）
# ---------------------------------------------------------------------------
# 🔴 用户口径（**覆盖** verify_config 里 ORDINAL_VAKIL 的旧描述）：type 8 的条头是
# **标签在前**的 ``Label C.S.A`` —— 章 . 节 . **字母**序标，第三维**必须是字母、
# 不能是数字**。旧描述（"number-first, N.M.item + N.M.A exercises"）与
# ``extract_items_vakil`` 的 ``VAKIL_ITEM`` / ``VAKIL_EXER``（两个都是**序标在前**，
# 且 ``VAKIL_ITEM`` 第三段是数字）**均不适用**；``keys_in_md`` 也根本没有 type 8
# 分支（会落进默认三级数字分支），所以本类**没有 legacy 等价性基线可对拍**——
# 属「按用户口径重新定义」，见 ordinal_styles.md「与 legacy 的有意偏差」。
#
# 标签词表用 ``_LABEL_ALT``（= ``COMBINED_LABEL_KINDS``，38 词；``Exercise`` 已于
# 2026-09-21「选项 B」补入 EN_LABEL_KINDS，故 COMBINED 已含之）。Vakil 的字母序标
# 条目绝大多数是 **Exercise**，现已被统一词表覆盖，与 type 1/2/3 同源。
# **复数（``Exercises``）刻意不收** —— ``_canon_label('Exercises')`` 无规范映射，
# 收进来只会产出非规范键；type 8 不挂 ``_APP_PLURAL``（与 13/14 不同）。
#
# 🔴 段数独立：第三维是字母 ⇒ ``Exercise 2.3.A`` 的数字尾巴 ``Exercise 2.3``
# 不得被 type 2 截走，靠 ``_TAIL_GUARD`` 第三条断言 ``(?!SEP[A-Za-z])`` 拦住；
# 反过来本类也绝不认两级（``Exercise 2.3``）与三段数字（``Theorem 2.3.4``）。
_ENTRY_RE_VAKIL = re.compile(
    r'\*\*'
    r'(' + _LABEL_ALT + r')\s*(\d+)' + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'([A-Za-z])'
    + _TAIL_GUARD + r'[^*]*\*+',
    re.IGNORECASE)
# page 形态（识别类型，对齐 make_config 页扫）：只收标签在前 —— 序标在前
# （``2.3.A Exercise``）按用户口径**不属于**本类。
_PAGE_RE_VAKIL = re.compile(
    r'(' + _LABEL_ALT + r')\s*(\d+)' + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'([A-Za-z])'
    + _TAIL_GUARD,
    re.IGNORECASE)


def _vakil_key_to_tuple(key):
    r"""type 8 规范键 → 分量元组，**第三维是字母序标折成的序号**（A→1, B→2 …）。

    基类 ``_key_to_tuple`` 用 ``re.findall(r'\d+')`` 会把字母序标整个丢掉
    （``练习2.3-A`` 与 ``练习2.3-B`` 都折成 ``(2, 3)``），于是「换条目、字母回 A」
    这一重置信号完全消失、scope 会被误判。字母折成序号后才能正确判定重置窗口
    （与附录体例 ``_app_key_to_tuple`` 同思路：字母位也是一维序标）。
    """
    m = re.search(r'(\d+)\s*' + SEP_TIGHT + r'\s*(\d+)\s*-\s*([A-Za-z])', key or '')
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)),
            ord(m.group(3).upper()) - ord('A') + 1)


class OrdinalVakil(OrdinalStyle):
    r"""EN 三级·字母序标（ORDINAL_VAKIL = 8）：``Label C.S.A`` → 键 ``<规范标签>C.S-A``。

    md 条头形如 ``**Exercise 2.3.A**`` / ``**Theorem 2.3.B**`` / ``**Lemma 1.2.C**``。
    规范键 = 规范中文标签 + 章号 + ``.`` + 节号 + ``-`` + **大写**字母序标
    （``练习2.3-A``）。键里**保留标签**：同节的 ``Theorem 2.3.A`` 与
    ``Exercise 2.3.A`` 是两条不同条目，纯数字键会碰撞（与 type 3 的纯数字
    ``1.3-4`` 刻意不同）。

    🔴 段数独立：只认「标签 + 数字 . 数字 . **字母**」。两级（``Exercise 2.3``）
    归 type 2、三段数字（``Theorem 2.3.4``）归 type 3、字母章位（``Exercise A.1.1``）
    归 type 13，本类**均不认**；序标在前（``2.3.A Exercise``）按用户口径也不收。
    """
    code = ORDINAL_VAKIL
    depth = 3
    name = ORDINAL_NAME[ORDINAL_VAKIL]
    entry_re = _ENTRY_RE_VAKIL
    page_entry_re = _PAGE_RE_VAKIL

    prose_re = None
    _key_to_tuple = staticmethod(_vakil_key_to_tuple)

    def extract(self, text):
        m = self.match_entry(text)
        if not m:
            return None
        return self.canon_key(m.group(1), m.group(2), m.group(3), m.group(4))

    def canon_key(self, label, ch, sec, letter, suffix=''):
        return f"{_canon_label(label)}{ch}.{sec}-{letter.upper()}{suffix}"


# ---------------------------------------------------------------------------
# Type 13 —— app（附录字母章位三级，``Label A.S.N`` → ``<规范标签>A.S-N``）
# ---------------------------------------------------------------------------
# 附录体例的**章位是字母**而非数字（Weibel 附录 A：``Definition A.1.1`` /
# ``Theorem A.6.2``；节标题 ``A.1 Categories`` 不是条目）。字母章位与罗马数字
# 章位（多字符、只取 IVXLCDM）正则不可混用，故独立成码 13（三级）/ 14（两段）。
#
# 标签词表 = ``_LABEL_ALT``（= ``COMBINED_LABEL_KINDS``，38 词；``Exercise`` 已被
# 2026-09-21「选项 B」纳入 COMBINED，故与 type 1/2/3/8 完全同源）。另允许**复数**
# ``(?:es|s)?``（``_APP_PLURAL``）—— 对齐 make_config
# ``_build_label_heading_regexes(letter_chapter=True)`` 的页扫（它明确支持
# ``Examples A.1.3``）。旧 ``keys_in_md`` 的 ``ENTRY_RE_APP_C`` 用无复数词表会
# **漏收**复数形态，属已确认的 legacy 缺陷，本层级按页扫口径修正（有意偏差，见
# 同目录 ordinal_styles.md「与 legacy 的有意偏差」）。
#
# 🔴 段数独立性：13 只认「字母 + 两段数字」，14 只认「字母 + 一段数字」且末位后
# 不得再接「分隔符 + 数字」（``(?!SEP\d)``）—— 两段书绝不判成 13，反之亦然。
# 旧 type 13 分支里那段「两段宽容回退」是 type 14 落地前的历史兼容，本层级
# **刻意不继承**（与「type 间校验相互独立」硬要求直接冲突）。
_APP_PLURAL = r'(?:es|s)?'

# md 抽键：三分支，按优先级排列（同一行只取最左分支命中的那条）
#   1. 标签在前 ``**Definition A.1.1**``           → 键 ``定义A.1-1``
#   2. 序标在前 ``**A.1.1 Definition**``           → 键 ``定义A.1-1``（带标签）
#   3. 裸号    ``**A.1.5**``（原书只印编号）        → 键 ``A.1-5``（无标签前缀）
# 分支 2 是**识别↔抽键自洽**的必需项：page 形态认得出序标在前（make_config 双臂
# 页扫），md 抽键就必须抽得出，否则 classify→extract 链路会断。末位挂
# ``_TAIL_GUARD`` 保证「恰好字母 + 两段数字」。
_ENTRY_RE_APP = re.compile(
    r'\*\*'
    r'(?:(' + _LABEL_ALT + r')' + _APP_PLURAL + r'\s*([A-Za-z])'
    + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'(\d+)' + _TAIL_GUARD +
    r'|([A-Za-z])' + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'(\d+)' + _TAIL_GUARD
    + r'\s+(' + _LABEL_ALT + r')' + _APP_PLURAL +
    r'|([A-Za-z])' + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'(\d+)' + _TAIL_GUARD +
    r')',
    re.IGNORECASE)
# page 形态（识别类型，对齐 make_config 的双臂页扫）：标签在前 / 序标在前，
# **不含裸号** —— page 散文里 ``A.1.5`` 与矩阵元 / 公式号 / 小节号同形，旧页扫
# 与 ``keys_in_md`` 的 prose 分支同样**刻意不收裸号**。
_PAGE_RE_APP = re.compile(
    r'(?:(' + _LABEL_ALT + r')' + _APP_PLURAL + r'\s*([A-Za-z])'
    + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'(\d+)' + _TAIL_GUARD +
    r'|([A-Za-z])' + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'(\d+)' + _TAIL_GUARD
    + r'\s+(' + _LABEL_ALT + r')' + _APP_PLURAL + r')',
    re.IGNORECASE)


def _app_key_to_tuple(key):
    """附录规范键 → 分量元组，**首分量是字母章位的序号**（A→1, B→2 …）。

    基类 ``_key_to_tuple`` 用 ``re.findall(r'\\d+')`` 会把字母章位整个丢掉
    （``定义A.1-1`` 与 ``定义B.1-1`` 都折成 ``(1, 1)``），于是「换字母章、号回 1」
    这一重置信号完全消失、scope 被误判成书级。附录体例的**首分量是字母**，折算
    成序号后才能正确判定重置窗口（对齐 make_config：首分量与章键 'A'/'B'… 比对）。
    """
    m = re.search(r'([A-Za-z])\s*' + SEP_TIGHT + r'\s*(\d+)(?:\s*-\s*(\d+))?',
                  key or '')
    if not m:
        return None
    comps = [ord(m.group(1).upper()) - ord('A') + 1, int(m.group(2))]
    if m.group(3):
        comps.append(int(m.group(3)))
    return tuple(comps)


class OrdinalApp(OrdinalStyle):
    """附录字母章位三级（ORDINAL_APP = 13）：``Label A.S.N`` → 键 ``<规范标签>A.S-N``。

    md 条头形如 ``**Definition A.1.1**`` / ``**Theorem A.6.2**`` /
    ``**Exercise A.4.1**``；裸号条目（原书只印编号）形如 ``**A.1.5**``。
    规范键 = 规范中文标签 + **大写**字母章位 + ``.`` + 节号 + ``-`` + 条目号
    （``定义A.1-1``）；裸号键无标签前缀（``A.1-5``）。字母章位在键里保留为字母
    ——与数字章位体例（type 3 纯数字 ``1.3-4``）刻意不同，避免与正文键碰撞。

    🔴 段数独立：只认「字母 + 两段数字」。两段体例（``Theorem B.2``）归 type 14，
    本类不认。
    """
    code = ORDINAL_APP
    depth = 3
    name = ORDINAL_NAME[ORDINAL_APP]
    entry_re = _ENTRY_RE_APP
    page_entry_re = _PAGE_RE_APP

    prose_re = None
    _key_to_tuple = staticmethod(_app_key_to_tuple)

    def extract(self, text):
        m = self.match_entry(text)
        if not m:
            return None
        if m.group(1) is not None:                       # 标签在前
            return self.canon_key(m.group(1), m.group(2), m.group(3), m.group(4))
        if m.group(5) is not None:                       # 序标在前（带标签）
            return self.canon_key(m.group(8), m.group(5), m.group(6), m.group(7))
        return self.canon_key(None, m.group(9), m.group(10), m.group(11))  # 裸号

    def canon_key(self, label, letter, sec, num, suffix=''):
        head = _canon_label(label) if label else ''
        return f"{head}{letter.upper()}.{sec}-{num}{suffix}"


# ---------------------------------------------------------------------------
# Type 14 —— app2（附录字母章位两段，``Label B.N`` → 键 ``<规范标签>B.N``）
# ---------------------------------------------------------------------------
# Lee ISM 2e 附录 A-D 实测体例：条目/练习均无节段（``Theorem D.1`` /
# ``Example A.5`` / 练习 ``A.1``），计数器跨全附录连续、每字母章从 1 重开 →
# scope=2（章级，首分量=字母与章键 'A'/'B'… 比对）。
# 🔴 ``(?!SEP\d)`` 是 14 对 13 的段数护栏：``A.1`` 后面还跟着 ``.1`` 就不属本类。
# 裸号两段（``**D.1**``）与公式号 / 小节标题无形态区别，旧管线与本类**均不收**。
_ENTRY_RE_APP2 = re.compile(
    r'\*\*'
    r'(?:(' + _LABEL_ALT + r')' + _APP_PLURAL + r'\s*([A-Za-z])'
    + SEP_TIGHT + r'(\d+)(?!' + SEP_TIGHT + r'\d)' + _TAIL_GUARD +
    r'|([A-Za-z])' + SEP_TIGHT + r'(\d+)(?!' + SEP_TIGHT + r'\d)' + _TAIL_GUARD
    + r'\s+(' + _LABEL_ALT + r')' + _APP_PLURAL + r')',
    re.IGNORECASE)
_PAGE_RE_APP2 = re.compile(
    r'(?:(' + _LABEL_ALT + r')' + _APP_PLURAL + r'\s*([A-Za-z])'
    + SEP_TIGHT + r'(\d+)(?!' + SEP_TIGHT + r'\d)' + _TAIL_GUARD +
    r'|([A-Za-z])' + SEP_TIGHT + r'(\d+)(?!' + SEP_TIGHT + r'\d)' + _TAIL_GUARD
    + r'\s+(' + _LABEL_ALT + r')' + _APP_PLURAL + r')',
    re.IGNORECASE)


class OrdinalApp2(OrdinalStyle):
    r"""附录字母章位两段（ORDINAL_APP2 = 14）：``Label B.N`` → 键 ``<规范标签>B.N``。

    md 条头形如 ``**Theorem B.2**`` / ``**Example A.5**`` / ``**Exercise B.4**``。
    规范键 = 规范中文标签 + 大写字母章位 + ``.`` + 条目号（``定理B.2``），**无节段**。
    裸号两段（``**D.1**``）与公式号 / 小节标题同形，刻意不收。

    🔴 段数独立：只认「字母 + 一段数字」；``A.1.1`` 这类两段数字的归 type 13，
    本类不认（``(?!SEP\d)`` 护栏）。
    """
    code = ORDINAL_APP2
    depth = 2
    name = ORDINAL_NAME[ORDINAL_APP2]
    entry_re = _ENTRY_RE_APP2
    page_entry_re = _PAGE_RE_APP2

    prose_re = None
    _key_to_tuple = staticmethod(_app_key_to_tuple)

    def extract(self, text):
        m = self.match_entry(text)
        if not m:
            return None
        if m.group(1) is not None:                       # 标签在前
            return self.canon_key(m.group(1), m.group(2), m.group(3))
        return self.canon_key(m.group(6), m.group(4), m.group(5))   # 序标在前

    def canon_key(self, label, letter, num, suffix=''):
        return f"{_canon_label(label)}{letter.upper()}.{num}{suffix}"





# ---------------------------------------------------------------------------
# Type 12 —— hum（Humphreys：label + 单字母序标，label 可在字母前后）
# ---------------------------------------------------------------------------
# 真实体例（Humphreys GTM 9《Introduction to Lie Algebras》）：条目头印
# ``**Theorem**`` / ``**Corollary A**`` / ``**Lemma A**`` / ``**Example 1**``…
# 其中「label + 单字母序标」(``**Corollary A**``) 是本书最具特征、也是用户
# 2026-09-21 要求明确定义的形态。本 pilot 类**只覆盖「字母序标」这一形态**，且支持
# label 在字母前后都可：
#   * label 在前 ``**Corollary A**``   → 规范键 ``Corollary A``（label + 空格 + 字母）
#   * label 在后 ``**A Corollary**``   → 归一为同一键 ``Corollary A``（双向等价）
# 数字序标 (``**Example 1**``) 与纯 label (``**Theorem**``) 两种 legacy 形态**刻意不收**
# 入本 pilot 类——它们会走 legacy type-12 配置分支，或由 type 1（单级数字）覆盖；若
# 一并收进本类，``classify`` 会把任意「单级 EN 书 (``**Theorem 1**``)」误判成 type 12，
# 破坏自动类型识别。字母折序号 (A→1, B→2) 用于 scope 重置判定，与 Vakil/App 同思路。
# 🔴 段数独立 + 防越界：本类只认「label + 单字母」，**绝不**认数字（归 type 1/2/3）、
# 绝不认「字母章位 + 数字」(归 type 13/14)、绝不认「数字.数字 + 字母」序标（归 type 8）。
# ``_TAIL_GUARD`` 拒绝字母之后再接「数字 / 分隔符+数字 / 分隔符+字母」，避免
# ``**Corollary A.1**`` 这类被本类误吞（应归 type 13/14）。
_ENTRY_RE_HUM = re.compile(
    r'\*\*'
    r'(?:(' + _LABEL_ALT + r')\s+([A-Za-z])' + _TAIL_GUARD +
    r'|([A-Za-z])\s+(' + _LABEL_ALT + r')' + _TAIL_GUARD + r')'
    r'[^*]*\*+',
    re.IGNORECASE)
_PAGE_RE_HUM = re.compile(
    r'(?:(' + _LABEL_ALT + r')\s+([A-Za-z])' + _TAIL_GUARD +
    r'|([A-Za-z])\s+(' + _LABEL_ALT + r')' + _TAIL_GUARD + r')',
    re.IGNORECASE)


def _hum_key_to_tuple(key):
    r"""type 12 字母序标 → 单分量元组（``Corollary A``→(1,)、``定理B``→(2,)）。

    字母折成序号 (A→1, B→2 …) 后，``detect_scope`` 才能正确判定重置窗口——否则基类
    ``re.findall(r'\d+')`` 把字母丢光，``Corollary A/B/C`` 全塌缩成空、scope 误判。
    ``_TAIL_GUARD`` 保证末位字母后无数字/分隔符，键里不会混进数字分量，单分量语义稳定。"""
    last = (key or '').rsplit(' ', 1)[-1]
    if len(last) == 1 and last.isalpha():
        return (ord(last.upper()) - ord('A') + 1,)
    return None


class OrdinalHum(OrdinalStyle):
    r"""字母序标（ORDINAL_HUM = 12）：``Label A`` ↔ ``A Label`` → 键 ``<规范标签> A``。

    md 条头形如 ``**Corollary A**`` / ``**Lemma B**`` / ``**定理 A**``；也支持 label
    在字母之后（``**A Corollary**`` / ``**A 定理**``），两种顺序**归一为同一规范键**
    （``Corollary A``），以便不论 OCR 捕获哪种顺序都能对上号。规范键 = 规范中文标签
    + 空格 + **大写**字母序标（与 legacy ``f"{label} {letter}"`` 同形）。

    🔴 段数独立：只认「label + 单字母」。单级数字（``Theorem 1``）归 type 1、字母章位
    + 数字（``Definition A.1.1``）归 type 13/14、数字.数字+字母（``Exercise 2.3.A``）
    归 type 8，本类**均不认**。数字序标（``Example 1``）与纯 label（``Theorem``）留待
    legacy type-12 配置分支，不进 pilot 自动识别，避免误判单级 EN 书为 type 12。
    """
    code = ORDINAL_HUM
    depth = ORDINAL_DEPTH[ORDINAL_HUM]   # = 1（单字母序标，仅一个维度：字母折序号
                                         #  (A→1, B→2, …)；_key_to_tuple 返回单分量，
                                         #  detect_scope 按末位字母重置判定章/书级）
    name = ORDINAL_NAME[ORDINAL_HUM]
    entry_re = _ENTRY_RE_HUM
    page_entry_re = _PAGE_RE_HUM

    prose_re = None
    _key_to_tuple = staticmethod(_hum_key_to_tuple)

    def extract(self, text):
        m = self.match_entry(text)
        if not m:
            return None
        if m.group(1) is not None:                 # label 在前
            return self.canon_key(m.group(1), m.group(2))
        return self.canon_key(m.group(4), m.group(3))   # label 在后

    def canon_key(self, label, letter):
        return f"{_canon_label(label)} {letter.upper()}"


__all__ = [
    'OrdinalStyle', 'OrdinalUnnumbered', 'OrdinalSingle',
    'OrdinalTwoLevelCN', 'OrdinalThreeLevelCN', 'OrdinalVakil',
    'OrdinalApp', 'OrdinalApp2', 'OrdinalHum',
    'normalize_ordinal',
    'OrdinalProfile', 'ORDINAL_UNNUMBERED',
]
