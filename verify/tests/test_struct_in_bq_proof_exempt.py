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


if __name__ == "__main__":
    unittest.main(verbosity=2)
