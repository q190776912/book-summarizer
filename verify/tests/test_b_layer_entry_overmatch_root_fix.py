# -*- coding: utf-8 -*-
r"""B 层条目抽取 over-match 根治回归（2026-10-26：elements / lie）。

两条独立根因，均只污染非阻断 EXTRA 桶（extra_entry），不碰 truly_missing/阻断：

1. elements《Large Sample Theory》(ORDINAL_THREE_LEVEL / type 3, else 分支)：
   `> **Proof of (2.1.9).**` / `**证明 (4.1.15).**` 是**证明块引用**的粗体标题，
   非编号条目；标签无关 `ENTRY_RE` 把其中 N.N.N 收成条目键（2.1-9 / 4.1-15）。
   修法：else 分支对 ENTRY_RE 命中做「Proof of / **证明」守卫，剔除证明块引用头。

2. lie《Introduction to Lie Algebras...》(Humphreys GTM 9, ORDINAL_HUM=12)：
   裸 `**Example**` / `**Definition**` 是散文条目标签（契约从不登记裸例/定义节点），
   ENTRY_RE_HUM 把它们收成 `例`/`定义`。修法：ORDINAL_HUM 分支仅剔除「裸 Example/
   Definition」（无字母位且无数字）；带号 `**Example 1**`→`例1`、字母位 `**Lemma A**`
   →`引理 A`、裸 `**Theorem**`→`定理` 一律保留（其契约已登记，属合法条目）。

断言（缺一成「放宽判据洗掉真漏登记」）：
  A. elements：`> **Proof of (2.1.9).**` 不再产出 `2.1-9`；真条头 `**Theorem 2.1.9**` /
     `**Lemma 2.1.9**` 照旧产出 `定理2.1.9` / `引理2.1.9`。
  B. lie 裸例/定义：`<**Example**` / `**Definition**` 不再产出 `例`/`定义`；
  C. lie 带号/字母/裸定理保留：`**Example 1**`→`例1`、`**Lemma A**`→`引理 A`、
     `**Theorem**`→`定理`、`**Proposition**`→`命题`、`**Corollary A**`→`推论 A`。
  D. ORDINAL_HUM 全库仅 lie 一本使用（已 grep 核实），本守卫零跨书回归。
"""
import os
import sys
import tempfile
import unittest
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
import lib.boot as _boot  # noqa: E402
_boot.setup()

from lib.key_parse import keys_in_md  # noqa: E402
from verify_config import ORDINAL_THREE_LEVEL, ORDINAL_HUM  # noqa: E402


def _keys(md_text, ordinal):
    fd, path = tempfile.mkstemp(suffix='.md', prefix='kb_overmatch_')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(md_text)
        return keys_in_md(path, ordinal=ordinal)
    finally:
        os.unlink(path)


class TestElementsProofOfOvermatch(unittest.TestCase):
    def test_proof_of_blockquote_not_an_entry(self):
        # 仅证明块引用头：不应冒充条目键（2.1-9 在 md 里根本无真条头）。
        md = (
            "# 第2章\n\n"
            "## §2.1 收敛\n\n"
            "> **Proof of (2.1.9).** From the above we conclude the result.\n"
        )
        entries, _ = _keys(md, ORDINAL_THREE_LEVEL)
        self.assertNotIn('2.1-9', entries)
        self.assertNotIn('定理2.1.9', entries)

    def test_chinese_proof_blockquote_not_an_entry(self):
        # 仅中文证明块引用头：不应冒充条目键。
        md = (
            "# 第4章\n\n"
            "## §4.1 区间\n\n"
            "**证明 (4.1.15).** 中文证明块引用头，不应冒充条目。\n"
        )
        entries, _ = _keys(md, ORDINAL_THREE_LEVEL)
        self.assertNotIn('4.1-15', entries)
        self.assertNotIn('定理4.1.15', entries)

    def test_legit_labeled_entry_still_captured(self):
        # 守卫只针对「Proof of / 证明」；真条头 `**Theorem 2.1.9**` 照旧产出
        # `定理2.1.9`（标签感知 ENTRY_RE_EN3_C 分支，非被守卫的 ENTRY_RE）。
        md = "# 第2章\n\n## §2.1\n\n**Theorem 2.1.9** 真条头。\n"
        entries, _ = _keys(md, ORDINAL_THREE_LEVEL)
        self.assertIn('定理2.1.9', entries)

    def test_legit_label_free_entry_still_captured(self):
        # 普通标签无关三段号（如裸编号条目）不受守卫影响。
        md = "> **2.1.9** 一个标签无关的三段号粗体头（非证明）。\n"
        entries, _ = _keys(md, ORDINAL_THREE_LEVEL)
        self.assertIn('2.1-9', entries)


class TestLieBareExampleDefinitionOvermatch(unittest.TestCase):
    def test_bare_example_definition_skipped_but_numbered_kept(self):
        md = (
            "> **Example** Let $L = \\mathfrak{sl}(2)$.（散文例，应剔除）\n\n"
            "**Definition** A Lie algebra over $F$.（未编号定义，应剔除）\n\n"
            "> **Example 1** $L = \\mathfrak{sl}(3)$.（带号例，应保留）\n\n"
            "**Lemma A** 字母位引理，应保留。\n\n"
            "**Theorem** 裸定理，应保留。\n\n"
            "**Proposition** 裸命题，应保留。\n\n"
            "**Corollary A** 字母位推论，应保留。\n"
        )
        entries, _ = _keys(md, ORDINAL_HUM)
        # 裸 Example / Definition 是散文，不再冒充条目
        self.assertNotIn('例', entries)
        self.assertNotIn('定义', entries)
        # 带号 / 字母位 / 裸陈述型条目全部保留
        self.assertIn('例1', entries)
        self.assertIn('引理 A', entries)
        self.assertIn('定理', entries)
        self.assertIn('命题', entries)
        self.assertIn('推论 A', entries)

    def test_numbered_example_still_entry(self):
        # ch6 契约登记 `Example §22.4-1`；带号 `**Example 1**` 必须仍产出 `例1`。
        md = "> **Example 1** Some explicit computation.\n"
        entries, _ = _keys(md, ORDINAL_HUM)
        self.assertIn('例1', entries)


if __name__ == '__main__':
    unittest.main()
