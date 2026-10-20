"""节限定字母条目引用（`例 8.4A`）不得截成编号条目提及键。

Rice《Mathematical Statistics and Data Analysis》ch8 实测：本书条目是字母序标
（Example A/B/C），正文引用写 `例 8.4A` = §8.4 的 Example A。二级 prose 正则把
号截到 `8.4` 后照收，all_keys 里凭空出现 `例8.4` → B 层 EXTRA-MENTION 幻影；
且若契约真登记了编号例 8.4，幻影提及会让 truly_missing 误判「已提及」。

守卫（`_is_letter_slot_tail`）只丢「号后紧跟单个大写字母」的 prose 键；
无字母尾巴的真实编号提及、以及字母条头本身，必须原样保留。
"""
import os
import tempfile

import lib.boot as _boot
_boot.setup()

from config.verify_config.verify_config import GroupConfig  # noqa: E402
from key_parse import keys_in_md  # noqa: E402

TWO_LEVEL = [GroupConfig(type=2, name=["Example"])]


def _keys(text):
    fd, path = tempfile.mkstemp(suffix=".md")
    os.close(fd)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return keys_in_md(path, groups=TWO_LEVEL)
    finally:
        os.remove(path)


def test_section_qualified_letter_ref_not_truncated():
    ent, allk = _keys(
        "## §8.6 贝叶斯方法\n\n"
        "**例 A** 内容。\n\n"
        "我们考虑例 8.4A 与例 8.5A 的数据。\n")
    assert "例 A" in ent
    for ghost in ("例8.4", "例8.5"):
        assert ghost not in allk, ghost


def test_plain_numbered_mention_still_kept():
    _, allk = _keys("见例 8.4。\n\n另见 Theorem 8.5 与例 8.4A。\n")
    assert "例8.4" in allk
    assert "定理8.5" in allk
    assert "例8.5" not in allk          # 带字母尾巴的那处不造键


def test_lowercase_and_long_tails_untouched():
    """小写字母（Ross 式 `Example 2a`）与多字母尾巴不归本守卫管。"""
    _, allk = _keys("见例 8.4b. 另见定理 8.5AB 与定义 8.6A1。\n")
    assert "例8.4" in allk
    assert "定理8.5" in allk
    assert "定义8.6" in allk
