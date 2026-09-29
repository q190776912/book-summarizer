"""Regression tests: F 层「结构性条目不应进入块引用」不得误伤**证明标题**
（Vakil《Rising Sea》ch10/12/18/23/24/25/26/29 CN 实测，FIX：check_katex Pass 2b）。

背景：中文译文把印刷的 "Proof of Theorem 29.2.6." 写成「> **定理 29.2.6 的证明。**」
（含（续）/（完）变体）。Pass 2b 的结构性词开头判据把它当成「被吞进 > 的定义/定理
条目」报 F-layer FAIL——但证明标题本应与证明正文一起待在块引用里（gate_units 的
> 包裹要求反而强制它进去）。根治后判据：行以「…的证明[（尾缀）]。**」收尾 = 证明
标题，豁免；真正的裸结构性条目（「> **定义 13.1.1 转移函数。**」）仍必须报。
"""
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[2])
sys.path.insert(0, _ROOT)
from lib.boot import setup  # noqa: E402
setup()

from verify.format_verify.script.check_katex import process_file  # noqa: E402

_PROOF_MSG = '结构性条目不应进入块引用'


def _hit(md: str) -> bool:
    """True when check_katex reports the struct-in-bq finding for `md`."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "t.md"
        p.write_text(md, encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            ok = process_file(str(p), fix=False)
        return (not ok) or _PROOF_MSG in buf.getvalue()


class TestProofTitleExemption(unittest.TestCase):
    def test_proof_title_in_bq_not_flagged(self):
        md = ("正文。\n\n"
              "> **定理 29.2.6 的证明。**\n"
              "> 1. 关键步骤。\n\n"
              "> **命题 23.1.2 的证明（续）。**\n"
              "> 3. 中间步骤。\n\n"
              "> **定理 29.6.2 的证明（完）。**\n"
              "> 1. 收尾。$\\square$\n")
        self.assertFalse(_hit(md), "proof titles must be exempt from struct-in-bq")

    def test_real_struct_entry_in_bq_still_flagged(self):
        md = "> **定义 13.1.1 转移函数。**\n>\n> 内容。\n"
        self.assertTrue(_hit(md),
                        "a structural entry swallowed into a quote must fail")

    def test_proof_title_with_trailing_colon_not_flagged(self):
        r"""Shafarevich《BAG 1》CN 体例（实测 5 处，ch2/0059、ch3/0057、ch4/0015、ch4/0094）：
        印刷是 `> **Proof of Theorem 2.11**:`——冒号落在闭合粗体**之外**，故译文写成
        「> **定理 2.11 的证明**：」。旧豁免要求 `**` 后即行尾，把证明标题误判为被吞条目，
        `--fix` 还会剥掉 `>` 把标题拆出证明块（与 gate_units「证明须在 `>` 内」互相打脸）。"""
        md = ("正文。\n\n"
              "> **定理 2.11 的证明**：\n"
              "> 1. 设 $f$ 正则……\n\n"
              "> **引理 4.1 的证明**：\n"
              "> 2. 逐项验证。\n\n"
              "> **命题 3.5 的证明（续）**：\n"
              "> 3. 同上。\n")
        self.assertFalse(_hit(md), "「…的证明**：」是证明标题，必须豁免")

    def test_struct_entry_with_trailing_colon_still_flagged(self):
        """反向：真正的裸结构性条目即使尾随冒号也照报——豁免只认「…的证明」收尾。"""
        md = "> **定义 4.1 射影空间**：\n>\n> 内容。\n"
        self.assertTrue(_hit(md),
                        "「> **定义 …**：」是被吞进引用的条目，必须 FAIL")

    def test_fix_does_not_unwrap_exempted_proof_title(self):
        """`--fix` 不得把豁免的证明标题从 `>` 块里剥出去（strip_bq 误伤=内容重排）。"""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.md"
            src = "> **定理 2.11 的证明**：\n> 1. 关键步骤。\n"
            p.write_text(src, encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                process_file(str(p), fix=True)
            self.assertEqual(p.read_text(encoding="utf-8"), src,
                             "豁免行被 fix 改动了")


class TestColonInsideBoldProofTitle(unittest.TestCase):
    r"""冒号落在闭合 `**` **之内**的第三种体例（Apostol《解析数论导引》CN 实测 2026-09-29）。

    ch7 四处 + ch12 一处：印面是 `> **Proof of Lemma 7.5.**`，译文按中文标点习惯写成
    「> **引理 7.5 的证明：**」——冒号在粗体**里面**。既有豁免只允许 `**` 之前出现
    `[。.．]`，于是这一形态被判成「被吞进块引用的结构性条目」，章级 verify 打回整章，
    而**同一结构在英文侧合法**（`Proof of …` 开头不是条目词）= 又一处「源过/译不过」。
    豁免只放宽「证明标题的收尾标点族」，不放宽条目本体。
    """

    def test_colon_inside_bold_is_exempt(self):
        md = ("正文。\n\n"
              "> **引理 7.5 的证明：**\n>\n"
              "> 1. 从和式出发。\n\n"
              "> **定理 12.8 的证明：**\n> 2. 分部积分。\n\n"
              "> **命题 3.4 的证明（续）：**\n> 3. 同理。\n")
        self.assertFalse(_hit(md), "「…的证明：**」是证明标题，必须豁免")

    def test_bare_item_head_with_colon_inside_bold_still_flagged(self):
        """反向：条目本体（不含「证明」）即使冒号在粗体内也照报。"""
        md = "> **定理 12.8：**\n>\n> 设 $f$ 全纯。\n"
        self.assertTrue(_hit(md), "「> **定理 N：**」是被吞进引用的条目，必须 FAIL")

    def test_item_statement_ending_in_noun_not_exempt(self):
        """反向：尾词不是「证明」的条目陈述（…有界性。**）不得借豁免逃逸。"""
        md = "> **引理 7.5 有界性。**\n>\n> 内容。\n"
        self.assertTrue(_hit(md))

    def test_fix_keeps_colon_inside_bold_title_wrapped(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.md"
            src = "> **引理 7.5 的证明：**\n> 1. 关键步骤。\n"
            p.write_text(src, encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                process_file(str(p), fix=True)
            self.assertEqual(p.read_text(encoding="utf-8"), src,
                             "豁免行被 fix 改动了")


if __name__ == "__main__":
    unittest.main(verbosity=2)
