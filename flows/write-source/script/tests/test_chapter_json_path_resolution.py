"""回归：按章契约路径必须按**磁盘物理证据**解析，不得只信进程级 kind 注册表。

事故（2026-09-28，本 skill 全量测试同进程运行）：`test_appendix_letter_tag_chain.py`
用临时 chapter_map 灌注 `{"5": 附录}` 后只回滚了**裸名** `book_structure` 那份注册表，
而 `attach_content` / 门控走的是包内 `data.book_structure.book_structure` 那份——同源文件
被 `lib.boot` 以两个名字注入 sys.path，进程级 `_PRIMED_KINDS` 因此有**两份**，回滚错对象
等于没回滚。残留的 `{"5": 附录}` 让 `chapter_json_path(ext, "5")` 算出
`appendix5.json`，而临时目录里写的是 `ch5.json` → 契约「读不到」→ 依赖契约真值的
**豁免静默失效**，verify 的 P 层习题节名豁免凭空假阳（2 failed / 1163 passed）。

根治两步（本文件锁死）：
① 新增 `resolve_chapter_json_path`：先取命名 SSOT 候选，缺失时按目录里**实际存在**的
   别种章型文件回退；两处都不存在仍返回 SSOT 候选，调用方 `isfile` 照旧失败
   （**fail-closed 不放宽**——绝不凭空造契约）。
② verbose_gates 的 `_load_chapter_contract` 改用①，P 层豁免不再被注册表污染失明。
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[4])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
import lib.boot  # noqa: E402
lib.boot.setup()

from data.book_structure.book_structure import (  # noqa: E402
    chapter_json_path, prime_chapter_kinds, resolve_chapter_json_path)
from verbose_gates import contract_exer_heading_sections  # noqa: E402

# 同一源文件的两个模块身份（裸名 / 包内名）各持一份注册表：快照 + 回滚必须覆盖全部，
# 否则本文件自己就成了下一个污染源。
import book_structure as _bs_bare  # noqa: E402
from data.book_structure import book_structure as _bs_pkg  # noqa: E402
_COPIES = list({id(_bs_bare): _bs_bare, id(_bs_pkg): _bs_pkg}.values())


class _Registry(unittest.TestCase):
    def setUp(self):
        saved = {id(m): dict(m._PRIMED_KINDS) for m in _COPIES}
        self.addCleanup(lambda: [
            (m._PRIMED_KINDS.clear(),
             m._PRIMED_KINDS.update(saved.get(id(m), {}))) for m in _COPIES])

    def _prime(self, entries):
        """写临时 chapter_map 并灌注 kind（真实判据：name 含 Appendix → kind=附录）。"""
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(d, ignore_errors=True))
        with open(os.path.join(d, "chapter_map.json"), "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False)
        prime_chapter_kinds(d)
        return d

    def _ext(self, fname, contract):
        """建 <ext>/book_structure/<fname>，返回 ext_dir。"""
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(d, ignore_errors=True))
        bs_dir = os.path.join(d, "book_structure")
        os.makedirs(bs_dir)
        with open(os.path.join(bs_dir, fname), "w", encoding="utf-8") as f:
            json.dump(contract, f, ensure_ascii=False)
        return d


_CONTRACT = {"key": "5", "type": "chapter", "name": "5 Algebraic Appendix",
             "sub_sec": [{"key": "5.9", "type": "section",
                         "name": "5.9 Problems",
                         "text": [{"text": "1. Exercise."}]}]}


class PathResolutionTest(_Registry):
    def test_stale_appendix_priming_still_finds_existing_ch_file(self):
        """污染本体：注册表说 5 是附录，目录里只有 ch5.json → 必须拿到 ch5.json。"""
        self._prime({"5": {"name": "Algebraic Appendix", "start": 299, "end": 312}})
        ext = self._ext("ch5.json", _CONTRACT)
        self.assertTrue(chapter_json_path(ext, "5").endswith("appendix5.json"))
        self.assertTrue(resolve_chapter_json_path(ext, "5").endswith("ch5.json"))

    def test_stale_chapter_priming_still_finds_existing_appendix_file(self):
        """反方向：注册表当 5 是正文章，目录里只有 appendix5.json → 拿到附录文件。"""
        self._prime({"5": {"name": "Algebraic", "start": 299, "end": 312}})
        ext = self._ext("appendix5.json", _CONTRACT)
        self.assertTrue(chapter_json_path(ext, "5").endswith("ch5.json"))
        self.assertTrue(resolve_chapter_json_path(ext, "5").endswith("appendix5.json"))

    def test_letter_key_appendix_zero_regression(self):
        self._prime({"A": {"name": "Appendix", "start": 91, "end": 100}})
        ext = self._ext("appendixA.json", _CONTRACT)
        self.assertTrue(resolve_chapter_json_path(ext, "A").endswith("appendixA.json"))

    def test_unnumbered_appendix_bare_name(self):
        """无号附录（序标为空 → 裸名 appendix.json）也得按物理证据找到。"""
        ext = self._ext("appendix.json", _CONTRACT)
        self.assertTrue(resolve_chapter_json_path(ext, "appendix")
                        .endswith("appendix.json"))

    def test_fail_closed_when_no_contract_file(self):
        """🔴 不得凭空造契约：两处都没有文件 → 返回 SSOT 候选（不存在），
        调用方 isfile 仍为假 → 豁免集合空（严格侧不放宽）。"""
        ext = self._ext("ch5.json", _CONTRACT)
        got = resolve_chapter_json_path(ext, "9")
        self.assertFalse(os.path.isfile(got))
        self.assertEqual(got, chapter_json_path(ext, "9"))

    def test_prefers_ssot_candidate_when_both_present(self):
        """两个文件都在（老书残留）→ 仍按命名 SSOT 取，不引入歧义。"""
        self._prime({"5": {"name": "Algebraic", "start": 1, "end": 9}})
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(d, ignore_errors=True))
        bs_dir = os.path.join(d, "book_structure")
        os.makedirs(bs_dir)
        for fn in ("ch5.json", "appendix5.json"):
            with open(os.path.join(bs_dir, fn), "w", encoding="utf-8") as f:
                json.dump(_CONTRACT, f, ensure_ascii=False)
        self.assertTrue(resolve_chapter_json_path(d, "5").endswith("ch5.json"))


class LayerExemptionImmunityTest(_Registry):
    def test_p_layer_exemption_survives_stale_priming(self):
        """端到端（② 的本体）：注册表被污染时 P 层豁免仍取到契约节名真值。"""
        self._prime({"5": {"name": "Algebraic Appendix", "start": 299, "end": 312}})
        ext = self._ext("ch5.json", _CONTRACT)
        self.assertEqual(contract_exer_heading_sections(ext, "5"), {"5.9"})

    def test_no_contract_file_still_yields_no_exemption(self):
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(d, ignore_errors=True))
        self.assertEqual(contract_exer_heading_sections(d, "5"), set())


if __name__ == "__main__":
    unittest.main(verbosity=2)
