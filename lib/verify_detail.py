"""verify_detail.py — 非阻断明细的**机器可读旁路**（缺陷③的根治处）。

动机
----
`report.print_result` 为控制日志长度会对长清单截断（旧实现只截
`extra_mention_domain`，`…（其余 N 个从略）`）。日志是给人看的，截断本身合理；
不合理的是**被截掉的那部分在盘上不留任何副本**：
2026-10-23 修茆诗松时，B 层「领域归属豁免」有 228 个键，日志只印出 40 个，
剩下的既要靠人回忆、又要靠重跑探针脚本才能复核——「非阻断 ≠ 不可审计」这条
要求当时没有任何机械出口。

本模块把 `print_result` 手里已经算好的**全部非阻断桶**原样落成一份 JSON
（`<extract>/verify_detail/<md 名>.json`，只写非空桶），并让截断行点名该路径。
判定与阻断口径一律不变：本文件只读 `r`、只写旁路产物，不参与 PASS/FAIL。

写失败（只读盘 / 权限）也不影响 verify：返回 None，调用方按「无旁路」出文案。
"""
import io
import json
import os

# 桶名 → r 里的键。逐条与 report.print_result 的展示段对齐，新增非阻断桶时同步。
# 阻断项（truly_missing / blocking / F 层 / U 层…）**不进旁路**：它们必须整条看，
# 截断即判据缺陷，不该用「反正 JSON 里有」来兜。
NONBLOCKING_BUCKETS = (
    ("label_warns", "label_warns"),
    ("mentioned_only", "mentioned_only"),
    ("extra_mention", "extra"),
    ("extra_entry", "extra_entry"),
    ("extra_mention_domain", "extra_mention_domain"),
    ("extra_attested", "extra_attested"),
    ("extra_attested_reasons", "extra_attested_reasons"),
    ("b_gap_warnings", "b_gap_warnings"),
    ("warnings", "warnings"),
    ("ignored_hit", "ignored_hit"),
    ("fig_extra", "fig_extra"),
    ("fig_unembedded", "fig_unembedded"),
    ("fig_invalid_warn", "fig_invalid_warn"),
    ("long_formula_rows", "long_formula_rows"),
    ("o_subitem_tail_warnings", "o_subitem_tail_warnings"),
    ("q_order_mismatch", "q_order_mismatch"),
    ("q_misplaced", "q_misplaced"),
    ("q_tag_mismatch", "q_tag_mismatch"),
    ("q_letter_led", "q_letter_led"),
    # U 层「交付 md 自身顺序」= 非阻断 WARN（判据见 lib/unit_order.check_delivered_order）。
    ("md_order_problems", "md_order_problems"),
)


def _computed(r):
    """不能直接从 `r` 取一个键就落盘的桶（与 report 的展示口径同源）。"""
    out = {}
    gaps = r.get("o_subitem_gaps") or []
    tail = [g for g in gaps if str(g).strip().startswith("~")]
    if tail:
        out["o_subitem_tail_warnings"] = _plain(tail)
    # U 层交付顺序的**定位明细**：只在「有问题」或「有单元没定位上」时才是信息——
    # 否则每章每语种都会多出一个小 JSON（收官书满 corpus 的零信息产物）。
    st = r.get("md_order_stats") or {}
    if st and (r.get("md_order_problems")
               or int(st.get("located") or 0) != int(st.get("expected") or 0)):
        out["md_order_stats"] = _plain(st)
    return out

SUBDIR = "verify_detail"


def _plain(v):
    """JSON 可序列化：dict/list 原样，其余转 str（键/警告行本就是 str 或 int）。"""
    if isinstance(v, dict):
        return {str(k): _plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [_plain(x) for x in v]
    return v if isinstance(v, (str, int, float, bool)) or v is None else str(v)


def detail_path(extract_dir, md_file):
    """旁路文件的绝对路径；extract_dir 为空时返回 None（无落点，不猜）。

    🔴 名字必须**不以 `.` / `_` 起头**（`lstrip("._")`）：按节拆分的章是并成
    `._verify_merged_ch{N}_{lang}.md` 临时视图再验的，直接取它的 stem 会产出一批
    `ls` / `glob("*.json")` 默认看不见的旁路——「机器可读」的产物反而要人记得加点
    才找得到（茆诗松 8 章实测 7 个隐身心）。
    """
    if not extract_dir or not md_file:
        return None
    stem = os.path.splitext(os.path.basename(md_file))[0].lstrip("._")
    return os.path.join(extract_dir, SUBDIR, stem + ".json")


def dump(r):
    """把 `r` 的非阻断明细写成 JSON，返回**相对 extract_dir** 的展示路径或 None。

    全部桶为空 → 不建目录、不写文件（收官书绝大多数章节如此，避免零信息产物）。
    """
    path = detail_path(r.get("extract_dir"), r.get("md"))
    if not path:
        return None
    detail = {}
    for name, key in NONBLOCKING_BUCKETS:
        val = r.get(key)
        if isinstance(val, (list, tuple, set, dict)) and len(val):
            detail[name] = _plain(val)
    detail.update(_computed(r))
    if not detail:
        return None
    payload = {
        "md": os.path.basename(r["md"]),
        "chapter": r.get("ch"),
        "counts": {k: len(v) for k, v in detail.items()},
        "detail": detail,
    }
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with io.open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1, sort_keys=True)
    except OSError:
        return None
    return f"{SUBDIR}/{os.path.basename(path)}"
