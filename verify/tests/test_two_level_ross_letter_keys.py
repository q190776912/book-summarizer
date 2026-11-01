"""Letter-suffixed counters in TWO-LEVEL books (S. Ross《A First Course in
Probability》, measured 2026-10-29).

Ross numbers items per section with a LETTER sub-counter on the examples
(`Example 2a`..`2e` under §1.2) while propositions stay dotted (`Proposition 4.1`).
Its `verify_config.json` used to route the whole chapter through
`ORDINAL_SINGLE` (the former ORDINAL_ROSS=11 folded into type 1), whose md parser
carries the letter branch; the `ORDINAL_TWO_LEVEL` arm — the one that actually
builds this book's contract keys — did NOT, so:

  * `lib/key_parse.keys_in_md` minted no key for `**Example 2a**` / `**例 2a**`,
    and the A layer reported the contract's 41 letter items across all 10
    chapters as `TRULY MISSING` (blocking) the moment the book was read as
    two-level;
  * both arms now emit the SAME canonical key (`例2a` = canonical label + digits
    + lowercase letter) via `_ross_canon`, so a head is byte-identically keyed
    whichever ordinal the config declares.

Negative guards: a bare `**Example 2**` must not sprout a letter key, `2ab` must
not be read as `2a`, a dotted `1.2a` must not be split into `1` + `2a`, and a
figure-only group (`Fig 2a` = sub-caption panel labels, figure pipeline's
jurisdiction) must contribute nothing.
"""
import os
import sys
import tempfile
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

from key_parse import keys_in_md, ENTRY_RE_ROSS_LETTER_C
from verify_config import GroupConfig, ORDINAL_TWO_LEVEL


def _md_keys(text, groups=None):
    fd, path = tempfile.mkstemp(suffix=".md")
    os.close(fd)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        if groups is None:
            groups = [GroupConfig(type=ORDINAL_TWO_LEVEL)]
        return keys_in_md(path, groups=groups)
    finally:
        os.remove(path)


# --- positive ---------------------------------------------------------------

def test_two_level_letter_head_mints_contract_key():
    entries, allk = _md_keys(
        "## §1.2 Permutations and Combinations\n\n"
        "**Example 2a**: A small community consists of 10 women.\n"
        "**Example 2b**: A college planning committee consists of 3 freshmen.\n")
    assert {"例2a", "例2b"} <= entries, entries
    assert {"例2a", "例2b"} <= allk


def test_two_level_letter_head_chinese_side_same_key():
    entries, _ = _md_keys(
        "**例 2a**: 一个小社区由 10 名妇女组成。\n"
        "**命题 4.1**：设 $A_1, A_2$ 为事件。\n")
    assert entries == {"例2a", "命题4.1"}, entries


def test_letter_and_dotted_branches_coexist():
    entries, _ = _md_keys(
        "**Proposition 4.1**: something.\n"
        "**Example 4a**: consider a set of $n$ antennas.\n"
        "**Axiom 1**: $P(A) \\ge 0$.\n")
    assert {"命题4.1", "例4a", "公理1"} <= entries, entries


def test_single_and_two_level_arms_agree_on_the_same_head():
    """同一物理条头在两分支必须逐字同键（否则换体例码就整书错位）。"""
    from key_parse import ORDINAL_SINGLE
    line = "**Example 2a**: text.\n**Proposition 4.1**: text.\n"
    a, _ = _md_keys(line, groups=[GroupConfig(type=ORDINAL_TWO_LEVEL)])
    b, _ = _md_keys(line, groups=[GroupConfig(type=ORDINAL_SINGLE)])
    assert a == b == {"例2a", "命题4.1"}, (a, b)


# --- negative guards --------------------------------------------------------

def test_digit_only_head_does_not_sprout_letter_key():
    entries, allk = _md_keys("**Example 2**: plain counter.\n"
                             "**Theorem 3.14**: dotted.\n")
    assert entries == {"例2", "定理3.14"} or {"例2", "定理3.14"} <= entries, entries
    assert not any(k.endswith(("a", "b")) and k.startswith("例") and len(k) > 2
                   and k not in ("例",) for k in entries), entries


def test_multi_letter_tail_is_not_split():
    assert ENTRY_RE_ROSS_LETTER_C.search("**Example 2ab**") is None
    assert ENTRY_RE_ROSS_LETTER_C.search("**Example 1.2a**") is None
    assert ENTRY_RE_ROSS_LETTER_C.search("see **Proof of Example 2a**") is None


def test_figure_only_group_contributes_nothing():
    entries, allk = _md_keys(
        "**Figure 2a** shows the panel.\n",
        groups=[GroupConfig(type=ORDINAL_TWO_LEVEL, name=["Figure", "Fig"])])
    assert entries == set(), entries
    assert allk == set(), allk


def test_letter_regex_still_accepts_the_real_shapes():
    assert ENTRY_RE_ROSS_LETTER_C.search("**Example 2a**") is not None
    assert ENTRY_RE_ROSS_LETTER_C.search("**例 5o**:") is not None
