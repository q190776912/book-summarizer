# -*- coding: utf-8 -*-
"""Regression: `gate_units` 必须把「单元首行 ↔ 本侧 manifest 记录」当机械闸（步骤 5）。

判据本体在 `lib/unit_markers.marker_manifest_mismatch`（parity 第 12 项同源）。此前只有
步骤 7 的 `check_translate_parity` 比这一对，写源门控 `gate_units` 只判「标记在不在 /
是否 DRAFT / 有无 `-->` 泄漏」，**从不比对本侧 manifest**，于是：

- Shafarevich《BAG 1》ch1/0073：写源期人工把 `name=` 的印刷标题截断
  （`…the element Zd+1 is`，丢了 ` separable over the`），源章 gate 5/5 PASS、章 md
  merge + verify 全过，直到步骤 7 parity 才报红——返工面已从「一个首行」扩大到「重 merge
  + 重 verify 整章」。
- 无翻译阶段的中文书（units-only）根本没有第二次机会：parity 不会跑，脱账首行永久留存。

锁死：
1. 本侧 manifest 与首行逐字相同 → 报告里**不得**出现「与本侧 manifest 记录脱账」；
2. 首行 `name=` 被截断（前缀关系，纯「非前缀」判据看不见）→ 必须报，且点出 `name` 字段；
3. 源侧（`units`）与译侧（`units-translate`）两个目录各自判各自的 manifest，标签分别为
   「源侧」「译侧」。
"""
import json
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
    _ROOT = str(Path(__file__).resolve().parents[3])
for _p in (_ROOT, os.path.join(_ROOT, "lib"),
           os.path.join(_ROOT, "flows", "write-source", "script")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

import gate_units  # noqa: E402

NAME = "1.1 Definition of the projective space"
REC = {"id": "0001", "type": "item", "key": "1.1", "name": NAME,
       "file": "0001_item_1_1.md", "tags": [], "images": [], "content": 1}
GOOD = ("<!-- book-summarizer DONE unit: id=0001 type=item key=1.1 "
        "name=%s -->" % NAME)
TRUNC = ("<!-- book-summarizer DONE unit: id=0001 type=item key=1.1 "
         "name=1.1 Definition of the projective -->")
BODY = "**定义 1.1**：射影空间 $\\mathbf P^n$ 是 $k^{n+1}$ 中过原点的直线全体。\n"
FLAG = "与本侧 manifest 记录脱账"


class Base(unittest.TestCase):
    def setUp(self):
        self.ext = tempfile.mkdtemp(prefix="bks_marker_manifest_")
        bs = os.path.join(self.ext, "book_structure")
        os.makedirs(bs)
        with open(os.path.join(bs, "ch1.json"), "w", encoding="utf-8") as f:
            json.dump({"key": "1", "type": "chapter", "name": "One",
                       "sub_sec": [], "items": []}, f, ensure_ascii=False)
        self._orig = gate_units.gate_chapter

    def tearDown(self):
        gate_units.gate_chapter = self._orig
        import shutil
        shutil.rmtree(self.ext, ignore_errors=True)

    def write_unit(self, sub, line):
        d = os.path.join(self.ext, "book_structure", sub, "ch1")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"units": [REC]}, f, ensure_ascii=False)
        # CRLF：与真实单元文件一致（行尾 CR 不得参与比较）
        with open(os.path.join(d, REC["file"]), "wb") as f:
            f.write((line + "\r\n" + BODY).encode("utf-8"))
        return d

    def problems(self, sub, line):
        self.write_unit(sub, line)
        if sub == "units":
            ok, detail = gate_units.gate_chapter(self.ext, "1", units_sub="units")
        else:
            # 译侧门控会先重跑源侧硬闸：放一份逐字正确的源单元，让源侧必过。
            self.write_unit("units", GOOD)
            gate_units.gate_chapter = lambda e, c, units_sub="units": (
                (True, "") if units_sub == "units" else self._orig(e, c, units_sub=sub))
            ok, detail = gate_units.gate_chapter(self.ext, "1", units_sub=sub)
        return ok, detail


class GateMarkerManifest(Base):
    def test_verbatim_marker_not_flagged(self):
        ok, detail = self.problems("units", GOOD)
        self.assertNotIn(FLAG, detail, detail)

    def test_truncated_name_flagged_with_field(self):
        ok, detail = self.problems("units", TRUNC)
        self.assertIn(FLAG, detail, detail)
        self.assertIn("name", detail, detail)
        self.assertIn(REC["file"], detail, detail)

    def test_translate_side_checked_against_own_manifest(self):
        ok, detail = self.problems("units-translate", TRUNC)
        self.assertIn(FLAG, detail, detail)
        self.assertIn("译侧", detail, detail)

    def test_draft_units_do_not_double_report(self):
        """DRAFT 已按「仍未处理」报出并在该分支 continue：即使首行同时脱账，也只报
        一条「先改好单元」类问题，不叠加脱账噪音（判据顺序锁）。"""
        draft = TRUNC.replace("DONE", "DRAFT")
        ok, detail = self.problems("units", draft)
        self.assertIn("仍未处理", detail, detail)
        self.assertNotIn(FLAG, detail, detail)


if __name__ == "__main__":
    unittest.main()
