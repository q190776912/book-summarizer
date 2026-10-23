r"""Guard against 复合词尾巴被当成条目标签所产生的幻影键（note-word-tail keys）.

「标签词 + 单号」的散文提及扫描（`PROSE_RE_ROSS_SINGLE` / `PROSE_RE_EN3_C` …）只按
词表切标签，遇到中文连写时会把**复合词的尾字** `注` 读成 `评注` 标签：
茆诗松《概率论与数理统计教程》ch2 印面散文「各出赌注 50 法郎」→ 幻影键 `评注50`
（2026-10-23 报出）。Kreyszig ch11「（参见脚注 2）」→ `评注2` 同族。

危害不止 A 层 EXTRA-MENTION 噪声：`all_keys` 的作用是「仅正文提及 = 不判缺」，
一个不属于本书的假键混进去，会**掩盖同一号真条目真的没写**。

`_is_note_word_tail` 只拦三件事都成立的命中：标签是单字 `注`、前字与之构成
`_NOTE_WORD_TAILS` 里的 attested 词、且该命中既不在粗体条头内也不在行首条头位。
两个豁免都是**收官书的真键唯一生产者**，拦错即造假 truly-missing：
 * 粗体内：Leinster《BCT》中文侧把 Remark 印作「备注」，词表里没有 `备注`，
   `**备注2.1.2**` 的键只能靠散文正则在 `注` 上命中 → 必须豁免。
   🔴 判「在不在粗体内」只能用 `**` 的**奇偶走趟**：正则版
   `\*\*[^*\n]*$` 一行里只要出现过**闭合**粗体段就恒真 → 整个守卫形同虚设
   （本测试的第一版就是这样假过的，`test_bold_parity_not_regex` 钉住这一点）。
 * 行首位：Weibel `附注 1　$H_0(B)=…`、Kreyszig `脚注 10. …`、数学物理方程
   `附注 1　本教材…` 都是**不带粗体直接起行**的笔记条头（2026-10-20 那本书的修法
   是把键登记进契约，md 侧一直是裸行首形态）。「行首」按复合词**整体**判：
   若只看标签之前，`附注 1` 的前字 `附` 会让它显得在句中。

跨语料回归口径（58 本 / 719 章，见 概率论与数理统计教程 第三版/_extract/
_census_guard_regression_20261023.txt）：新增缺项 0，砍掉 8 个键
（`评注50`、Kreyszig `评注2`/`评注3`、Rising Sea 5 个跨章 `旁注`/`附注` 提及）。
"""
import os
import tempfile

import lib.boot as _boot
_boot.setup()

from config.verify_config.verify_config import GroupConfig  # noqa: E402
from key_parse import (_in_bold_span, _is_note_word_tail,  # noqa: E402
                       keys_in_md)

# 茆诗松 ch2 的真实分组：三级条目 + 单级练习组（`注` 走单号散文正则）。
GROUPS = [GroupConfig(type=3, name=["uncat"]), GroupConfig(type=1, name=["练习"])]


def _keys(text, groups=GROUPS, ch=2):
    fd, path = tempfile.mkstemp(suffix=".md")
    os.close(fd)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return keys_in_md(path, groups=groups, chapter=ch)
    finally:
        os.remove(path)


def test_gambling_stake_phrase_emits_no_phantom_remark():
    """印面原句：闭合粗体条头之后的「各出赌注 50 法郎」不得造 `评注50`。"""
    ent, allk = _keys(
        "> **例2.2.1（分赌本问题）** 甲、乙两赌徒赌技不相上下，各出赌注 50 法郎，"
        "每局中无平局。\n"
        "\n"
        "**例2.2.2** 续上题。\n")
    assert "例2.2.1" in ent and "例2.2.2" in ent
    for ghost in ("评注50", "注50"):
        assert ghost not in ent, ghost
        assert ghost not in allk, ghost


def test_mid_sentence_footnote_citation_is_noise_not_key():
    """句中「参见脚注 2」：该书的契约里没有 注 族条目 → 键就是噪声。"""
    _ent, allk = _keys(
        "$h$ 非常小（参见脚注 2），所以在宏观物理中可忽略。\n"
        "\n"
        "绝对连续性在 10.7 节的脚注 3 中说明。\n")
    for ghost in ("评注2", "评注3"):
        assert ghost not in allk, ghost


def test_bare_note_head_at_line_start_still_produces_key():
    """行首裸条头（Weibel / 数学物理方程 形态）必须照常出键。

    `附注 1　…`（全角空格起题、**不带粗体**）才是守卫拦得到的裸行首形态：
    `脚注 10. …` 尾随句点被单号正则的 `(?![.\\-…])` 断言挡掉，本就不产键。
    所以「行首豁免」是 `附注 1　` 这一族真键的承重墙，见下方句中对照。
    """
    _ent, allk = _keys(
        "附注 1　$H_0(B) = \\mathbb{Z}$，故沿正实轴的积分路径收敛。\n"
        "\n"
        "本教材不引入外测度，见\n"
        "附注 2　本教材的处理与常规不同。\n")
    assert "评注1" in allk and "评注2" in allk, "行首裸条头被拦 = 收官书新增假 truly-missing"
    # 对照：同一个词前头一旦有正文（不再是行首修饰符）就当噪声拦掉。
    assert _is_note_word_tail("见附注 1　说明。", 2, "注") is True
    assert _is_note_word_tail("附注 1　说明。", 1, "注") is False


def test_bold_note_head_still_produces_key():
    """🔴 粗体条头内的 `注` 必须豁免：Leinster 词表无 `备注`，散文正则是唯一生产者。"""
    _ent, allk = _keys(
        "**备注2.1.2**：(a) 自然性公理看起来可能是特设的。\n"
        "\n"
        "评注（备注 1.1.2(b)、1.2.2(a)）与伴随性无关。\n")
    assert "评注2.1.2" in allk, "粗体条头被拦 = 该书 remark 全族假 truly-missing"
    # 句中那次 `备注 1.1.2(b)` 在粗体之外 → 当噪声拦掉；键由粗体条头那份产出，不丢。
    # （断言必须打在**真的会被守卫切断**的那个号上：`1.2.2(a)` 前面是顿号、没有标签，
    #  两态都不产键，拿它作断言是假绿。）
    assert "评注1.1.2" not in allk


def test_genuine_citations_are_kept():
    """词表外的复合词（回顾注/话题注/蕴含注/根据注）都是真引用，一律不得拦。"""
    _ent, allk = _keys(
        "回顾注 4.5.5 的记号。\n"
        "\n"
        "（笑话题注 1.3.11 与 21.5.2 的作者是 Miklós Abért。）\n"
        "\n"
        "根据注 12.2.1，序列弱收敛。\n"
        "\n"
        "它要用到例 1.28 中解释过的描述。\n")
    assert "评注4.5.5" in allk and "评注1.3.11" in allk
    assert "评注12.2.1" in allk
    assert "例1.28" in allk or "例1.28" in _ent


def test_non_note_labels_are_untouched():
    """守卫只对单字 `注` 生效：`例`/`性质`/`条件` 前字为中文的命中全为真引用。"""
    _ent, allk = _keys(
        "行列式性质 6 成立。\n"
        "\n"
        "由定理 5.2 与检验条件 2 可知。\n"
        "\n"
        "它要用到例 2 中解释过的描述。\n")
    assert "性质6" in allk and "定理5.2" in allk and "例2" in allk


def test_bold_parity_not_regex():
    """`_in_bold_span` 的口径：奇偶走趟，而非「前面出现过 `**`」。"""
    line = "**例2.2.1（分本问题）** 各出赌注 50 法郎"
    pos = line.index("注")
    assert _in_bold_span(line, pos) is False, "闭合粗体**之后**不算粗体内"
    assert _is_note_word_tail(line, pos, "注") is True
    assert _in_bold_span("**备注2.1.2**：x", 3) is True
    assert _in_bold_span("普通行，无粗体 注 5", 8) is False
    # 两个闭合段之后仍是偶数 → 守卫照常生效（正则版此处必假 = 守卫形同虚设）
    two = "**A** 文字 **B** 各出赌注 50"
    assert _in_bold_span(two, two.index("注")) is False
    assert _is_note_word_tail(two, two.index("注"), "注") is True


def test_guard_scope_predicates():
    """守卫的四个前置条件各自单独生效，缺一个就不拦。"""
    line = "各出赌注 50 法郎"
    pos = line.index("注")
    assert _is_note_word_tail(line, pos, "注") is True
    assert _is_note_word_tail(line, pos, "例") is False, "只拦单字 注"
    assert _is_note_word_tail("赌注 50", 1, "注") is False, "行首按复合词整体判"
    assert _is_note_word_tail("下注 50", 1, "注") is False, "词表外（下注）不拦"
    assert _is_note_word_tail("回顾注 4.5.5", 3, "注") is False, "词表外不拦"
