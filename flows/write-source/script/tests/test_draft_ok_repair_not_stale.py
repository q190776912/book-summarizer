"""`draft_ok` 新鲜度判据：mtime 只是代理，过期与否由闸⑩定夺（Arnold ch10 实测 2026-09-29）。

缺陷现场：`merge_source` 落账被拒
    🔴 write_source.draft: 单元 manifest 早于契约（attach 后未重拆）: ['10']
而 ch10 的实际情况是**写源后的定点修补**（SKILL.md「结构修复」条目）：§51 里
`build_structure` 把同页两段块挂反，修补=「契约里把两个兄弟节点互换位置（内容/键/
页码一律不动）+ 把该节点的 manifest 记录移到同一位置」，**先改清单（03:26）、后改
契约（03:32）**——方向恰好与 `attach_content` 重跑相反。纯 mtime 判据分不清这两件事，
于是：单元明明与契约一致（gate_units ⑩/⑪、verify 26/26 全绿），落账却被永久卡死，
而唯一能"通过"它的动作是**重拆单元**——那会把已写毕的 DONE 正文全部作废。

根治 = 报警前先跑权威判据：`gate_units._check_contract_unit_coverage`（章级闸 ⑩，
契约 → manifest 反向对账）。无孤儿节点 ⇒ 定点修补，放行；有孤儿 ⇒ 真过期，照旧拒。
判据不复制第二份（检测趟与修复趟共用同一个谓词）。

负向（必须仍然成立，否则放行等于拆闸）：
  * 契约在拆分**之后**新增了没有单元记录的编号项（attach 重跑的真实形态）⇒ 仍 FAIL；
  * 契约 / 清单 / ⑩ 判据任一读不到 ⇒ fail-closed，按过期处理（见 `_contract_unit_orphans`）。

Runs under stdlib unittest:
  python flows/write-source/script/tests/test_draft_ok_repair_not_stale.py
"""
import json
import os
import sys
import tempfile
import time
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

from flows._flow_contract import physical_evidence  # noqa: E402


def _item(key, name, page):
    # 内容块挂在节点自己的 `sub_sec` 下（`node_content_count` 只数子块，
    # 与真契约形态一致：`{"text": …}` / `{"formula": …, "display": …}`）。
    return {"key": key, "type": "item", "name": name, "page_start": page,
            "page_end": page, "consolidated": False,
            "sub_sec": [{"text": name + " 的正文"}]}


def _mk(book, items, manifest_keys, contract_newer):
    """items = [(key, page)] 契约登记序；manifest_keys = 清单记录序。"""
    ex = os.path.join(book, "_extract")
    bs = os.path.join(ex, "book_structure")
    os.makedirs(os.path.join(bs, "units", "ch1"), exist_ok=True)
    with open(os.path.join(ex, "chapter_map.json"), "w", encoding="utf-8") as f:
        json.dump({"chapters": [{"kind": 1, "num": "1", "name": "第一章",
                                 "start": 1, "end": 9}]}, f)
    contract = {"key": "1", "type": "chapter", "name": "第一章",
                "page_start": 1, "page_end": 9,
                "sub_sec": [_item(k, "标题" + k, p) for k, p in items]}
    cp = os.path.join(bs, "ch1.json")
    with open(cp, "w", encoding="utf-8") as f:
        json.dump(contract, f, ensure_ascii=False)
    man = {"units": [{"id": f"{i:04d}", "type": "item", "key": k,
                      "file": f"{i:04d}_item_{k}.md"}
                     for i, k in enumerate(manifest_keys)]}
    mp = os.path.join(bs, "units", "ch1", "manifest.json")
    with open(mp, "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False)
    now = time.time()
    if contract_newer:
        os.utime(mp, (now - 600, now - 600))
        os.utime(cp, (now, now))
    else:
        os.utime(cp, (now - 600, now - 600))
        os.utime(mp, (now, now))
    return ex


class FreshManifest(unittest.TestCase):
    def test_manifest_newer_passes(self):
        with tempfile.TemporaryDirectory() as d:
            ex = _mk(d, [("定理1", 3), ("定理2", 4)], ["定理1", "定理2"],
                     contract_newer=False)
            ok, detail = physical_evidence.draft_ok(d, ex)
            self.assertTrue(ok, detail)
            self.assertIn("1 章内容化契约", detail)


class RepairedContractNotStale(unittest.TestCase):
    def test_pure_reorder_after_split_is_not_stale(self):
        # 现场：契约与清单**同一批键**，只是互换位置；清单 mtime 早于契约。
        with tempfile.TemporaryDirectory() as d:
            ex = _mk(d, [("系2", 237), ("系1", 237)], ["系2", "系1"],
                     contract_newer=True)
            ok, detail = physical_evidence.draft_ok(d, ex)
            self.assertTrue(ok, detail)
            self.assertIn("定点修补", detail)


class GenuineStalenessStillFails(unittest.TestCase):
    def test_contract_node_without_manifest_record_is_stale(self):
        # attach 重跑的真实形态：契约多出编号项，清单里没有它的记录。
        with tempfile.TemporaryDirectory() as d:
            ex = _mk(d, [("定理1", 3), ("定理2", 4), ("定理9", 5)],
                     ["定理1", "定理2"], contract_newer=True)
            ok, detail = physical_evidence.draft_ok(d, ex)
            self.assertFalse(ok, detail)
            self.assertIn("孤儿", detail)

    def test_unreadable_manifest_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            ex = _mk(d, [("定理1", 3)], ["定理1"], contract_newer=True)
            mp = os.path.join(ex, "book_structure", "units", "ch1", "manifest.json")
            cp = os.path.join(ex, "book_structure", "ch1.json")
            open(mp, "w", encoding="utf-8").write("{ not json")
            # 重写会把清单 mtime 顶到当下——必须还原成「清单早于契约」，
            # 否则根本进不了新鲜度分支，测的就不是 fail-closed。
            older = os.path.getmtime(cp) - 600
            os.utime(mp, (older, older))
            ok, detail = physical_evidence.draft_ok(d, ex)
            self.assertFalse(ok, detail)


if __name__ == "__main__":
    unittest.main(verbosity=2)
