"""Guard against 三段号截断产生的幻影二级键 (prefix-phantom keys).

A two-level entry/prose regex anchored only on `label + N + SEP + N` also fires
on the FIRST TWO components of a three-level head (`**定义2.1.1**` → `定义2.1`),
so `keys_in_md` used to emit both the real key and a truncated one.  The
contract registers three-level items as bare dash keys (`2.1-1`), which
`_norm_path` can fold back from `定义2.1.1` but NOT from `定义2.1` — so every
chapter surfaced the truncation as EXTRA-ENTRY ("md carries a head the contract
never registered"), hiding genuine unregistered print items.

`_NOT_DEEPER` suppresses the truncation.  These tests pin BOTH directions:
 * negative — three-level heads/mentions must not yield a two-level prefix key;
 * positive — a genuinely two-level book (and a two-level group living next to a
   three-level one, e.g. exercises) must keep parsing exactly as before.
"""
import os
import tempfile

import lib.boot as _boot
_boot.setup()

from config.verify_config.verify_config import GroupConfig  # noqa: E402
from key_parse import keys_in_md  # noqa: E402


def _keys(text, groups):
    fd, path = tempfile.mkstemp(suffix=".md")
    os.close(fd)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return keys_in_md(path, groups=groups)
    finally:
        os.remove(path)


THREE_AND_TWO = [GroupConfig(type=3, name=["uncat"]), GroupConfig(type=2, name=["练习"])]
TWO_ONLY = [GroupConfig(type=2, name=["uncat"])]


def test_three_level_head_emits_no_two_level_prefix():
    ent, allk = _keys(
        "**定义2.1.1**：设 $\\mathcal{A}$ 是集族。\n"
        "\n"
        "**Remark 2.1.2.** This definition of a measure.\n"
        "\n"
        "由评注 2.1.3 与引理 2.1.4 可知结论成立。\n",
        THREE_AND_TWO)
    # real three-level keys survive (label + three components)
    assert "定义2.1.1" in ent
    assert "评注2.1.2" in ent
    assert "评注2.1.3" in allk and "引理2.1.4" in allk
    # ... and the truncated prefixes are gone from BOTH buckets
    for ghost in ("定义2.1", "评注2.1", "引理2.1"):
        assert ghost not in ent, ghost
        assert ghost not in allk, ghost


def test_head_with_parenthetical_or_trailing_dot_still_parses():
    ent, _ = _keys(
        "**Definition 2.1.** A collection $\\mathcal{A}$.\n"
        "\n"
        "**定理 3.2（存在性）**：设 $X$ 为紧集。\n"
        "\n"
        "**Exercise 12.3.** 证明之。\n"
        "\n"
        "**练习 4.1**：计算积分。\n",
        TWO_ONLY)
    assert "定义2.1" in ent
    assert "定理3.2" in ent
    assert "练习12.3" in ent
    assert "练习4.1" in ent


def test_two_level_group_coexists_with_three_level_body():
    """两级练习组不得被三级正文条头带出幻影键，也不得丢掉自己的键。"""
    text = ("**定义2.1.1**：设 $\\mathcal{A}$ 是集族。\n"
            "\n"
            "**练习2.1**：证明 $\\mu$ 可数可加。\n")
    ent, _ = _keys(text, THREE_AND_TWO)
    assert "定义2.1.1" in ent and "练习2.1" in ent
    assert "定义2.1" not in ent


def test_range_style_number_is_not_truncated():
    """`2.1-3` 这类跨段引用：dash 后仍有数字 → 不是二级号，两级键不得出现。"""
    ent, allk = _keys("**定义2.1-3**：见定义 2.1-5。\n", THREE_AND_TWO)
    assert "定义2.1" not in ent and "定义2.1" not in allk


def test_two_digit_section_does_not_backtrack_into_prefix():
    r"""🔴 `**定义5.10.1**`：`(\d+)` 贪心吞 `10` 后由 SEP 断言拒；**回退成 `1`** 时后面
    跟的是数字 `0`，只靠 SEP 断言拦不住 → 必须另有 `(?!\d)`。"""
    ent, allk = _keys(
        "**定义5.10.1**：设 $\\mathcal{A}$ 是集族。\n"
        "\n"
        "由定理 5.10.2 与评注 5.100 可知。\n",
        THREE_AND_TWO)
    assert "定义5.10.1" in ent and "定理5.10.2" in allk
    for ghost in ("定义5.1", "定理5.10", "定理5.1", "评注5.10", "评注5.1"):
        assert ghost not in ent, ghost
        assert ghost not in allk, ghost
