import json
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

from verify.script.verify_chapter import chapter_md_groups, _group_lang


def _touch(dirpath, name):
    p = os.path.join(dirpath, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write("# t\n")
    return p


def _langs(book, ch):
    return [_group_lang(g) for g in chapter_md_groups(book, ch)]


class TestUnletteredAppendixMdGroup:
    """无字母序标附录（chapter_map 键就是 `appendix`）的中文带标题文件名必须进 verify。

    根因（Serre GTM42 实测，2026-09-29）：`merge_units` 按翻译 manifest 的 `final_md`
    写出 `附录_Artin环.md`，而 `chapter_md_groups` 的无编号分支只认裸名 `附录.md`，
    于是 `verify --all` 报 39/39 而磁盘上有 40 个 md——中文版附录**整本静默漏检**。
    `flows/_flow_contract.py::_md_group` 早就同时认 `附录.md` 与 `附录_*.md`，
    两个命名 SSOT 不一致才是病根，此处把 verify 侧补齐。
    """

    def test_titled_cn_appendix_is_picked_up(self):
        with tempfile.TemporaryDirectory() as d:
            _touch(d, "附录_Artin环.md")
            _touch(d, "Appendix.md")
            groups = chapter_md_groups(d, "appendix")
            assert _langs(d, "appendix").count("cn") == 1, groups
            assert _langs(d, "appendix").count("en") == 1, groups

    def test_bare_cn_appendix_still_picked_up(self):
        """负向守卫：补通配形制不得把旧裸名形态挤掉。"""
        with tempfile.TemporaryDirectory() as d:
            _touch(d, "附录.md")
            _touch(d, "Appendix.md")
            assert _langs(d, "appendix") == ["cn", "en"] or set(_langs(d, "appendix")) == {"cn", "en"}

    def test_titled_cn_supplement_is_picked_up(self):
        """补篇同理补通配，但 kind=3 要 chapter_map 登记才走补篇分支——
        无 chapter_map 时回退成 kind=2（附录分支），故此处在临时目录里写最小 A 形态 map。"""
        from data.book_structure import book_structure as _bs
        saved = dict(_bs._PRIMED_KINDS)
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "_extract"), exist_ok=True)
            with open(os.path.join(d, "_extract", "chapter_map.json"), "w", encoding="utf-8") as f:
                json.dump({"chapters": [{"kind": 3, "num": "supplement", "name": "补篇"}]}, f)
            _touch(d, "补篇_勘误.md")
            _touch(d, "Supplement.md")
            try:
                assert "cn" in _langs(d, "supplement")
            finally:
                _bs._PRIMED_KINDS.clear()
                _bs._PRIMED_KINDS.update(saved)

    def test_lettered_appendix_not_matched_by_wildcard(self):
        """字母附录 `附录A_*.md` 不得被无编号的 `附录_*.md` 误抓成同一组之外的重复组。"""
        with tempfile.TemporaryDirectory() as d:
            _touch(d, "附录A_Background.md")
            _touch(d, "AppendixA_Background.md")
            langs = _langs(d, "A")
            assert "cn" in langs and "en" in langs, langs
            # 无编号章位不应看到字母附录文件
            assert chapter_md_groups(d, "appendix") == [], chapter_md_groups(d, "appendix")
