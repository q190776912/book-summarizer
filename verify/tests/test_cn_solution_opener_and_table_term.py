"""test_cn_solution_opener_and_table_term.py — 译单元（EN→CN）两块判据缺口回归。

Rosen 8e ch8 译单元实测（2026-09-26）：

1. **`解` 不是 CN 块开吻词**。EN 源里 `> **Solution.**` 被 `_H_UL_OPENERS` 认作
   合法开吻（列表含 `Solution`），但按简报强制译成 `> **解。**` 之后，CN 交替式里
   没有 `解` → 整块被判「unlabeled blockquote」，连带块内每一行 `> 1.` / `> $$`
   全部重复报错（一个单元 4 处）。⇒ `解答?` 必须与 `Solution` 对等入白名单。
2. **顶级表格不是 G 层块终止符**。原书常把「例 N 题面 → 数据表 → 解答」排在一起，
   题面块与表之间是**裸空行**。`G_HEAD` 只认中文 证明/证/例，EN 源里 `**Example 1.**`
   根本不开块，所以该断裂**只在译单元**暴露：`G_TERM` 不含 `|` 开头的表行 →
   报「bare blank line breaks the `> **证明/例` block」。⇒ 顶级表行记为终止符。

两条修复都必须保留原有的**真阳**判定：无标签的 `> 普通散文` 仍要报，
证明块后接「裸空行 + 无标签中文散文」仍要报。
"""
import io
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
import lib.boot as _boot
_boot.setup()

from format_verify import (check_g_quote_continuity, check_i_prose_separator,
                           check_unlabeled_blockquotes,
                           check_labels_missing_blockquote,
                           _h_ext_is_legit_bq, G_TERM, _H_UL_OPENERS, _H_MISSING_BQ)


def _write(text):
    fd, p = tempfile.mkstemp(suffix=".md")
    os.close(fd)
    with io.open(p, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return p


class SolutionOpener(unittest.TestCase):
    def test_cn_solution_is_legit_opener(self):
        self.assertTrue(_H_UL_OPENERS.match('> **解。**'))
        self.assertTrue(_H_UL_OPENERS.match('> **解（例 4）.** 无人拿到自己那顶帽子的概率'))
        self.assertTrue(_h_ext_is_legit_bq('> **解。**'))

    def test_solution_block_inside_example_not_flagged(self):
        # 例块被题面表打断后重开的 `> **解。**` 块：不得报 unlabeled
        md = "\n".join([
            '> **例 1。** 十三世纪斐波那契提出如下问题。',
            '>',
            '> **解。**',
            '>',
            '> 1. 设 $f_n$ 为 $n$ 个月后的兔子对数。',
            '',
        ])
        p = _write(md)
        try:
            self.assertEqual(check_unlabeled_blockquotes(p), [])
        finally:
            os.remove(p)

    def test_truly_unlabeled_blockquote_still_flagged(self):
        # 负向：块首不是任何合法标签（且非粗体标签）仍必须被报
        md = "\n".join([
            '> 这里是一段没有任何结构标签的普通散文句子。',
            '',
        ])
        p = _write(md)
        try:
            self.assertTrue(check_unlabeled_blockquotes(p))
        finally:
            os.remove(p)


class TableTerminator(unittest.TestCase):
    def test_table_line_is_g_terminator(self):
        self.assertTrue(G_TERM.match('| 月份 | 幼兔对数 | 总对数 |'))

    def test_blank_before_top_level_table_not_flagged(self):
        md = "\n".join([
            '> **例 1。** 十三世纪，斐波那契在《算盘书》中提出。',
            '',
            '| 月份 | 幼兔对数 | 繁殖对数 | 总对数 |',
            '| --- | --- | --- | --- |',
            '| 1 | 1 | 0 | 1 |',
            '',
            '**图 1。** 岛上的兔子。',
            '',
        ])
        p = _write(md)
        try:
            self.assertEqual(check_g_quote_continuity(p), [])
        finally:
            os.remove(p)

    def test_blank_before_bare_prose_reported_by_prose_separator(self):
        # 「证明块 + 裸空行 + 无标签中文散文」：判据归属在 2026-09-27 的
        # Strogatz 根治里换了口径——正文完整的块到此**确实**结束（CommonMark 语义），
        # 该处缺的是 `---`（writing-rules V-F 第 316 条），故由 `check_i_prose_separator`
        # 在**中英两侧同口径**报；G 层不再以此形态报「断裂」（旧行为只在 CN 侧开块，
        # 造成 EN 源/CN 译判定不对称，见 test_g_head_bilingual_and_prose_separator）。
        # 「半包例子」（块只有头行、正文裸奔）仍由 G 层报，不在此条。
        md = "\n".join([
            '> **证明。** 对 $n$ 归纳。',
            '> 1. 基础步骤成立。',
            '',
            '下面这段散文不带任何结构标签，是块后的描述性段落。',
            '',
        ])
        p = _write(md)
        try:
            self.assertEqual(check_g_quote_continuity(p), [])
            self.assertTrue(check_i_prose_separator(p))
        finally:
            os.remove(p)


if __name__ == "__main__":
    unittest.main()
