r"""Q 层字母/罗马章位探针（RESERVED letter-led probe）跨段豁免回归（Lee ISM 实测，2026-10-09）。

背景：数字正文的公式段（`formula.type` 落在 digit 家族）里，源页出现字母/罗马开头
的编号时，Q 层发一条**非阻断** WARN（`Q-LAYER FORMULA LETTER-LED`），提示「可能漏配
letter_ch」。真·跟因假阳（Lee《Intro to Smooth Manifolds》2e）：**数字正文章**（ch7，
正文段 scope=2/digit）只是**交叉回指**某条**已按字母家族配置的附录段**里的编号——
`(B.3) expresses det(I + tA)`——该号本就由「附录 B 段」（`formula.letter_ch: true`）
自己机器校验，正文段不该再报警。旧探针只看「字母头在不在本书章键集」，附录 B 是
章键 → 拦不住 → 恒报警。

修复（共享 skill 源码，非 config 手改、非 attestation 消音）：探针命中**分两条正交判据**
豁免——
  (1) 头不在本书章键集 = 书外/他书交叉引用（2026-10-04 Iwaniec–Kowalski `(A.36)`），照旧丢；
  (2) 头归属某附录/补篇章、且**该段 formula 已选用 alpha 家族**（`ConfigLoader.alpha_led_special_head_keys`
      作 SSOT 路由）→ 该号已被该段自身校验 → 丢。
🔴 与 2026-10-08 判据一致：附录/补篇**自身是数字家族**（或根本没该段、静默回退正文数字
配置）时 (2) 不触发 → 告警照发——那才是「印面无人校验」的真漏配。

断言：
  A. `_detect_letter_led_formulas`：Lee 假阳消失 / 附录数字配置真未校验仍 WARN / Iwaniec
     书外引用仍静默 / 罗马头同判据；
  B. `ConfigLoader.alpha_led_special_head_keys` 按 kind→段路由只纳入真被 alpha 段接管者；
  C. `QLayer.run` 两个探针调用点均把 `ctx.loader` 的豁免集透传下去（sectioned + normal 分支）。
"""
import os
import sys
import json
import shutil
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

from formula_tag import (QLayer, _detect_letter_led_formulas,          # noqa: E402
                         _letter_led_note)
from verify_config import BookConfig, ConfigLoader                     # noqa: E402
from verify.script.base import VerifyContext                           # noqa: E402


# ---------------------------------------------------------------------------
# fixture helpers
# ---------------------------------------------------------------------------
def _mk_ext(page_texts, bs_files):
    """构造一个单册 _extract 目录：顶层直接放 page_NNN.json（→ resolve_page_dir
    返回本目录），并在 book_structure/ 下放**契约分章标记文件**（文件名即决定
    list_chapter_keys 的章键集：``ch7.json``→'7'、``appendixB.json``→'B'、
    ``appendixII.json``→'II'、``supplementS.json``→'S'）。内容无关（探针只读文件名）。
    返回 ext 绝对路径；调用方负责清理。"""
    ext = tempfile.mkdtemp(prefix='llprobe_')
    bs_dir = os.path.join(ext, 'book_structure')
    os.makedirs(bs_dir, exist_ok=True)
    for fn in bs_files:
        with open(os.path.join(bs_dir, fn), 'w', encoding='utf-8') as f:
            json.dump({}, f)
    for i, text in enumerate(page_texts, start=1):
        with open(os.path.join(ext, f'page_{i:03d}.json'), 'w',
                  encoding='utf-8') as f:
            json.dump({'text': [{'text': text}]}, f, ensure_ascii=False)
    return ext


def _mk_md(body):
    fd, path = tempfile.mkstemp(suffix='.md', prefix='llprobe_')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(body)
    return path


class _StubLoader:
    """只提供 `alpha_led_special_head_keys`——QLayer.run 的新增透传判据的唯一入口，
    其余一律不碰（config 直接经 VerifyContext 传入，run 不再回读 loader）。"""

    def __init__(self, heads):
        self._heads = set(heads)

    def alpha_led_special_head_keys(self):
        return set(self._heads)


# ---------------------------------------------------------------------------
# A. 探针本体两条正交豁免判据
# ---------------------------------------------------------------------------
class LetterLedProbeRulesTest(unittest.TestCase):
    def test_body_crossref_to_alpha_appendix_suppressed(self):
        # Lee ISM 跟因：正文 ch7 交叉回指附录 B 的 (B.3)，B 是本书章键（(1) 拦不住）
        # 但 B 段已 letter_ch 配置（(2) 豁免）。
        ext = _mk_ext(["... where (B.3) expresses det(I + tA) ..."],
                      ['ch7.json', 'appendixB.json'])
        self.addCleanup(shutil.rmtree, ext, ignore_errors=True)
        found = _detect_letter_led_formulas(ext, 1, 1, ch='7',
                                            alpha_led_heads={'B'})
        self.assertEqual(found, set())
        self.assertIsNone(_letter_led_note(found))

    def test_appendix_digit_configured_still_warns(self):
        # 2026-10-08 判据：B 是章键，但其管辖段是数字家族（alpha_led_heads 不含 B）
        # → 印面无人校验 (B.3) → WARN 必须照发（不得消音真漏配）。
        ext = _mk_ext(["see (B.3) for the determinant"],
                      ['ch7.json', 'appendixB.json'])
        self.addCleanup(shutil.rmtree, ext, ignore_errors=True)
        found = _detect_letter_led_formulas(ext, 1, 1, ch='7',
                                            alpha_led_heads=set())
        self.assertEqual(found, {'(B.3)'})
        note = _letter_led_note(found)
        self.assertIsNotNone(note)
        self.assertIn('letter_ch', note)   # 单字母头 → 提示设 letter_ch

    def test_out_of_book_reference_suppressed_by_rule1(self):
        # Iwaniec–Kowalski：(A.36) 指向书末 Appendix，而本书章键集里根本没有附录章
        # → (1) 丢，且与 alpha_led_heads 无关（即便误给 'A' 也仍静默）。
        ext = _mk_ext(["cf. (A.36) in the appendix"], ['ch4.json'])
        self.addCleanup(shutil.rmtree, ext, ignore_errors=True)
        self.assertEqual(
            _detect_letter_led_formulas(ext, 1, 1, ch='4',
                                        alpha_led_heads=set()), set())
        self.assertEqual(
            _detect_letter_led_formulas(ext, 1, 1, ch='4',
                                        alpha_led_heads={'A'}), set())

    def test_roman_head_alpha_appendix_suppressed(self):
        # 罗马头同一判据：II 是章键 + alpha 配置 → 豁免。
        ext = _mk_ext(["by (II.5) we conclude"],
                      ['ch3.json', 'appendixII.json'])
        self.addCleanup(shutil.rmtree, ext, ignore_errors=True)
        found = _detect_letter_led_formulas(ext, 1, 1, ch='3',
                                            alpha_led_heads={'II'})
        self.assertEqual(found, set())

    def test_roman_head_digit_configured_still_warns(self):
        # 罗马头是章键但段为数字家族 → 仍 WARN（roman 走 type 16 提示）。
        ext = _mk_ext(["by (II.5) we conclude"],
                      ['ch3.json', 'appendixII.json'])
        self.addCleanup(shutil.rmtree, ext, ignore_errors=True)
        found = _detect_letter_led_formulas(ext, 1, 1, ch='3',
                                            alpha_led_heads=set())
        self.assertEqual(found, {'(II.5)'})
        self.assertIsNotNone(_letter_led_note(found))

    def test_pure_digit_pages_produce_no_alpha_token(self):
        # 无 alpha 头命中 → 空集（回归安全：正常数字书绝不因本修复产生噪声告警）。
        ext = _mk_ext(["we have (3.1) and Eq. (7.2) and 1-11 labels"],
                      ['ch7.json'])
        self.addCleanup(shutil.rmtree, ext, ignore_errors=True)
        self.assertEqual(
            _detect_letter_led_formulas(ext, 1, 1, ch='7',
                                        alpha_led_heads=set()), set())


# ---------------------------------------------------------------------------
# B. ConfigLoader.alpha_led_special_head_keys（kind→段路由 SSOT）
# ---------------------------------------------------------------------------
class AlphaLedSpecialHeadKeysTest(unittest.TestCase):
    def _loader(self, verify_cfg, chapter_map):
        root = tempfile.mkdtemp(prefix='llcfg_')
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        ext = os.path.join(root, '_extract')
        os.makedirs(ext, exist_ok=True)
        with open(os.path.join(ext, '_extraction_done.json'), 'w',
                  encoding='utf-8') as f:
            json.dump({'done': True}, f)
        with open(os.path.join(ext, 'verify_config.json'), 'w',
                  encoding='utf-8') as f:
            json.dump(verify_cfg, f)
        with open(os.path.join(ext, 'chapter_map.json'), 'w',
                  encoding='utf-8') as f:
            json.dump(chapter_map, f)
        return ConfigLoader(ext, root)

    _CM = {'chapters': [
        {'ch': '7', 'start': 1, 'end': 1, 'kind': 1},
        {'ch': 'B', 'start': 2, 'end': 2, 'kind': 2},
    ]}

    def test_appendix_alpha_configured_is_included(self):
        # 附录段 letter_ch:true（Lee 附录）→ 'B' 纳入豁免集。
        cfg = {'ch': {'formula': {'type': 2, 'scope': 2}},
               'appendix': {'formula': {'type': 2, 'scope': 2,
                                        'letter_ch': True}}}
        loader = self._loader(cfg, self._CM)
        self.assertEqual(loader.alpha_led_special_head_keys(), {'B'})

    def test_appendix_absent_silent_fallback_not_included(self):
        # 没有 appendix 子配置 → 附录章静默回退正文数字配置 → 真漏配，**不纳入**
        # （探针据此照发 WARN，守住 2026-10-08 判据）。
        cfg = {'ch': {'formula': {'type': 2, 'scope': 2}}}
        loader = self._loader(cfg, self._CM)
        self.assertEqual(loader.alpha_led_special_head_keys(), set())

    def test_appendix_digit_configured_not_included(self):
        # 附录段显式数字家族（letter_ch:false）→ 不纳入。
        cfg = {'ch': {'formula': {'type': 2, 'scope': 2}},
               'appendix': {'formula': {'type': 2, 'scope': 2,
                                        'letter_ch': False}}}
        loader = self._loader(cfg, self._CM)
        self.assertEqual(loader.alpha_led_special_head_keys(), set())

    def test_supplement_roman_included_body_never(self):
        # 补篇段 roman（type 16）纳入；数字正文章（kind=1）无论何配置绝不纳入。
        cfg = {'ch': {'formula': {'type': 15, 'scope': 2}},   # 正文就算 letter 也不纳
               'supplement': {'formula': {'type': 16, 'scope': 1}}}
        cm = {'chapters': [
            {'ch': '5', 'start': 1, 'end': 1, 'kind': 1},
            {'ch': 'S', 'start': 2, 'end': 2, 'kind': 3},
        ]}
        loader = self._loader(cfg, cm)
        self.assertEqual(loader.alpha_led_special_head_keys(), {'S'})


# ---------------------------------------------------------------------------
# C. QLayer.run 透传 ctx.loader 豁免集（sectioned + normal 两个调用点）
# ---------------------------------------------------------------------------
class LoaderWiringIntegrationTest(unittest.TestCase):
    def _run_body(self, formula, md_body, heads):
        ext = _mk_ext(["... where (B.3) expresses det(I + tA) ..."],
                      ['ch7.json', 'appendixB.json'])
        self.addCleanup(shutil.rmtree, ext, ignore_errors=True)
        md = _mk_md(md_body)
        self.addCleanup(lambda: os.path.exists(md) and os.remove(md))
        ctx = VerifyContext(ch='7', start=1, end=1, md_file=md, ext_dir=ext,
                            config=BookConfig(formula=formula),
                            loader=_StubLoader(heads))
        return QLayer().run(ctx)

    def test_normal_branch_scope2_suppressed_when_loader_alpha(self):
        # scope==2 → 走 normal 分支探针；loader 报 'B' 已 alpha → 无 q_letter_led。
        res = self._run_body({'type': 2, 'scope': 2, 'bare_number': False},
                             "just prose, no numbered formulas here\n", {'B'})
        self.assertEqual(res.metadata.get('q_letter_led', []), [])

    def test_normal_branch_scope2_warns_when_loader_empty(self):
        # loader 空（附录段数字配置）→ (B.3) 印面无校验 → 仍 q_letter_led。
        res = self._run_body({'type': 2, 'scope': 2, 'bare_number': False},
                             "just prose, no numbered formulas here\n", set())
        self.assertTrue(res.metadata.get('q_letter_led'))

    def test_sectioned_branch_scope3_suppressed_when_loader_alpha(self):
        # scope==3 且 md 有 `## 7.1` 节头 → 走 sectioned 分支探针；loader 'B' → 静默。
        res = self._run_body({'type': 2, 'scope': 3, 'bare_number': False},
                             "## 7.1 Tangent Spaces\n\nprose\n", {'B'})
        self.assertEqual(res.metadata.get('q_letter_led', []), [])

    def test_sectioned_branch_scope3_warns_when_loader_empty(self):
        res = self._run_body({'type': 2, 'scope': 3, 'bare_number': False},
                             "## 7.1 Tangent Spaces\n\nprose\n", set())
        self.assertTrue(res.metadata.get('q_letter_led'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
