# -*- coding: utf-8 -*-
"""Negative/positive test: 老 manifest 的 `\tag` 按 key 回退须受「key 唯一单元」约束（步骤 5）。

判据本体在 `gate_units.gate_chapter`（exp = u.get("tags") 缺失时的回退分支）。

Koopman Operator ch12 实测（2026-10-01）：契约里 ``定理12.5`` 是**两个**节点
（p343 的 Theorem + p344 的 "Theorem 12.5 (continued)"），编号公式 (12.42) 挂在**前者**；
本书 manifest 是拆分早期版本、记录里没有 per-node ``tags`` 字段，于是门控退回
`chapter_tag_map`（按 key 聚合）→ 两个单元都被要求写出 ``\\tag{12.42}`` →
0029 恒报「缺编号公式」。这正是 `node_tags` 文档注释里已承认的「按 key 聚合」陷阱，
只是回退路径把它又放了回来。

根治形态与图片回退**同判据**（上方 `img_units_by_key` 那段）：只在「该 key 本章只对应
一个单元」时才按 key 回退，歧义交给章级 Q 层（`verify/formula_tag/` 按契约 tag 集合对账）
兜底——单元级不再制造假缺号，真缺号仍由 Q 层拦。

锁死：
1. 共 key 两单元、tag 只属其中一个 → **不得**报「缺编号公式」（本例即回归点）；
2. key 唯一对应一个单元、该单元未写契约 tag → **必须**报「缺编号公式」（回退没被废掉）；
3. 新 manifest（记录带 ``tags``）按节点取真值，不受回退影响。
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
import lib.boot as _boot  # noqa: E402

_boot.setup()

import gate_units  # noqa: E402

FLAG = "缺编号公式"
MARK = "<!-- book-summarizer DONE unit: id=%s type=item key=%s name=%s -->"


def _item(key, name, page, tags):
    """契约 item 节点：tags 里的编号公式作为 formula 内容块挂在 sub_sec。"""
    sub = []
    for t in tags:
        sub.append({"type": "formula", "text": "$$y = f(x).\\tag{%s}$$" % t, "tag": t})
    sub.append({"type": "text", "text": "%s body text on page %d." % (name, page)})
    return {"type": "item", "key": key, "name": name, "page_start": page,
            "page_end": page, "sub_sec": sub}


def _unit(rec_id, key, name, body):
    return MARK % (rec_id, key, name) + "\n" + body


class Base(unittest.TestCase):
    def setUp(self):
        self.ext = tempfile.mkdtemp(prefix="bks_tag_fallback_")
        bs = os.path.join(self.ext, "book_structure")
        os.makedirs(bs)
        # 公式层须开启（本书 verify_config 有 formula 块）才做 tag 对账
        with open(os.path.join(self.ext, "verify_config.json"), "w", encoding="utf-8") as f:
            json.dump({"ch": {"formula": {"type": 2}}}, f, ensure_ascii=False)
        self.dir = os.path.join(bs, "units", "ch12")
        os.makedirs(self.dir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.ext, ignore_errors=True)

    def write(self, contract_units, records):
        with open(os.path.join(self.ext, "book_structure", "ch12.json"),
                  "w", encoding="utf-8") as f:
            json.dump({"type": "chapter", "key": "12", "name": "Ch12",
                       "page_start": 300, "page_end": 400, "sub_sec": contract_units},
                      f, ensure_ascii=False)
        with open(os.path.join(self.dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"chapter_key": "12", "language": "en", "units": records}, f,
                      ensure_ascii=False)
        for r in records:
            with open(os.path.join(self.dir, r["file"]), "w", encoding="utf-8",
                      newline="") as f:
                f.write(r["_body"])

    def detail(self):
        ok, det = gate_units.gate_chapter(self.ext, "12", units_sub="units")
        self.assertNotIn("标记仍为 DRAFT", det, det)
        return det


class TagKeyFallback(Base):
    def _rec(self, i, key, name, body, with_tags=None):
        r = {"id": "%04d" % i, "type": "item", "key": key, "name": name,
             "file": "%04d_item_%s.md" % (i, key.replace(".", "_")),
             "hash": "", "_body": _unit("%04d" % i, key, name, body)}
        if with_tags is not None:
            r["tags"] = with_tags
            r["content"] = 1
        return r

    def test_shared_key_does_not_demand_other_nodes_tag(self):
        """回归点：两节点共 key `定理12.5`，(12.42) 只属第一个 → 第二个不得被判缺号。"""
        self.write(
            [_item("定理12.5", "Theorem 12.5", 343, ["12.42"]),
             _item("定理12.5", "Theorem 12.5 continued", 344, [])],
            [self._rec(27, "定理12.5", "Theorem 12.5",
                       "**定理 12.5**: $V(f(x)) \\le \\rho V(x)$.\n\n"
                       "$$V(f(x)) \\le \\rho V(x).\\tag{12.42}$$\n"),
             self._rec(29, "定理12.5", "Theorem 12.5 continued",
                       "**定理 12.5**（续）：the search is over $P \\succ 0$ only.\n")])
        det = self.detail()
        self.assertNotIn(FLAG, det, det)

    def test_unique_key_still_demands_missing_tag(self):
        """key 只对应一个单元时回退仍有效：单元未写契约编号公式 = 报缺。"""
        self.write(
            [_item("定理12.9", "Theorem 12.9", 350, ["12.77"])],
            [self._rec(31, "定理12.9", "Theorem 12.9",
                       "**定理 12.9**: the origin is globally stable.\n")])
        det = self.detail()
        self.assertIn(FLAG, det, det)
        self.assertIn("12.77", det, det)

    def test_per_node_tags_field_is_authoritative(self):
        """新 manifest（带 tags）按节点取真值：共 key 也各判各的。"""
        self.write(
            [_item("定理12.5", "Theorem 12.5", 343, ["12.42"]),
             _item("定理12.5", "Theorem 12.5 continued", 344, ["12.43"])],
            [self._rec(27, "定理12.5", "Theorem 12.5",
                       "$$a \\le b.\\tag{12.42}$$\n", with_tags=["12.42"]),
             self._rec(29, "定理12.5", "Theorem 12.5 continued",
                       "**定理 12.5**（续）：$c \\le d$ 且 $P \\succ 0$。\n",
                       with_tags=["12.43"])])
        det = self.detail()
        self.assertIn(FLAG, det, det)
        self.assertIn("12.43", det, det)
        self.assertNotIn("12.42（", det, det)   # 0027 已写出，不被重复要求


if __name__ == "__main__":
    unittest.main()
