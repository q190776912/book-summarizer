"""Guard against phantom entry keys leaked by a **figure-only** ordinal group.

A Figure group (type 0, ``name=["Figure"]``) has no dedicated branch in
``keys_in_md``'s ``if/elif`` chain, so it used to fall through to the generic
three-level ``else`` branch.  That branch runs the *item-label* regexes
(``ENTRY_RE`` / ``_KEY_DEEP_RE`` / ``ENTRY_RE_EN3_C`` / ``ENTRY_RE_EN3_APP_C`` /
``_SEC_SINGLE_EX_RE``), which fire on entry labels regardless of the group's own
``name``.  Consequences:

* a figure group sitting next to the real item group **re-extracts** every item
  head (harmless dup for numeric keys, absorbed by the set union);
* for a **letter-ordinal** (appendix) head such as ``**Theorem A.1**``,
  ``ENTRY_RE_EN3_APP_C`` additionally emits the split artifacts ``定理 A.1``
  (space) and ``定理1`` (pure-digit residue).  The contract's canonical key is
  ``定理A.1`` (produced by the type-14 branch, no space), so these phantoms never
  match it and surface as false ``EXTRA-ENTRY`` (Teschl《Topics in Real and
  Functional Analysis》附录 A: 2 spurious keys, ``entries=3`` for a 1-item md).

``if _fig_only: continue`` now skips the catch-all branch entirely for figure-only
groups.  These tests pin BOTH directions:

* negative — a figure group must contribute **no** item keys (real or phantom);
  the phantom ``定理 A.1`` / ``定理1`` are gone, leaving only the contract key;
* positive — removing the figure group changes nothing, and the item group's own
  keys survive whether or not the figure sibling is present.

Monotone-safe by construction: the fix only deletes md-side EXTRA candidates that
the contract never registers, so ``truly_missing`` / blocking judgments are intact.
"""
import os
import tempfile

import lib.boot as _boot
_boot.setup()

from config.verify_config.verify_config import GroupConfig  # noqa: E402
from key_parse import keys_in_md  # noqa: E402


def _keys(text, groups, chapter=None):
    fd, path = tempfile.mkstemp(suffix=".md")
    os.close(fd)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return keys_in_md(path, groups=groups, chapter=chapter)
    finally:
        os.remove(path)


# 附录 A 真实形态：type-14 (ORDINAL_APP2) 的 Theorem 组 + type-0 (Figure) 组并排。
APP2_WITH_FIG = [GroupConfig(type=14, name=["Theorem"]),
                 GroupConfig(type=0, name=["Figure"])]
APP2_NO_FIG = [GroupConfig(type=14, name=["Theorem"])]

# 三级正文档 + figure 组并排（type 0 落通用分支的经典场景）。
THREE_WITH_FIG = [GroupConfig(type=3, name=["uncat"]),
                  GroupConfig(type=0, name=["Figure"])]
THREE_NO_FIG = [GroupConfig(type=3, name=["uncat"])]

THEOREM_A1 = ("**Theorem A.1 (Zorn's lemma).** Every partially ordered set in "
              "which every chain has an upper bound contains a maximal element.\n")


def test_figure_group_emits_no_phantom_letter_ordinal_keys():
    ent, allk = _keys(THEOREM_A1, APP2_WITH_FIG, chapter="A")
    # 契约规范键（无空格）在，且只此一个条目键。
    assert "定理A.1" in ent and "定理A.1" in allk
    # ENTRY_RE_EN3_APP_C 的拆分伪影被 figure 组泄漏 → 现已随整支跳过而消失。
    for ghost in ("定理 A.1", "定理1"):
        assert ghost not in ent, ghost
        assert ghost not in allk, ghost


def test_figure_group_presence_does_not_change_item_keys():
    """带不带 figure 兄弟组，条目组产出的键集合必须逐字相同（无重复、无丢失）。"""
    ent_with, all_with = _keys(THEOREM_A1, APP2_WITH_FIG, chapter="A")
    ent_wo, all_wo = _keys(THEOREM_A1, APP2_NO_FIG, chapter="A")
    assert ent_with == ent_wo
    assert all_with == all_wo


def test_figure_group_contributes_nothing_in_three_level_body():
    """三级正文档旁的 figure 组不得再抠出任何条目键；条目组自身键照常保留。"""
    text = ("**定义2.1.1**：设 $\\mathcal{A}$ 是集族。\n"
            "\n"
            "![fig](figure/ch2_fig2.1.1.png)\n")
    ent_f, all_f = _keys(text, THREE_WITH_FIG)
    ent_n, all_n = _keys(text, THREE_NO_FIG)
    assert "定义2.1.1" in ent_f  # 条目组照常在账
    assert ent_f == ent_n and all_f == all_n  # figure 组净贡献为零


def test_figure_only_group_alone_yields_no_entry_keys():
    """整份 config 只有一个 figure 组时，不应产出任何条目键（图号不作条目登记）。"""
    fig_only = [GroupConfig(type=0, name=["Figure"])]
    ent, allk = _keys(THEOREM_A1, fig_only, chapter="A")
    assert ent == set()
    assert "定理 A.1" not in allk and "定理1" not in allk and "定理A.1" not in allk
