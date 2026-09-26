"""判据测试：make_config._detect_exercise_counter 的习题区识别。

背景（Fraleigh 2026-09-26 实测坑）：集中习题块（V-I 规定整块省略、不校验）的块标题
被 OCR 粘成 ``EXERCISESO`` / ``InExercises21through6,determine…``，旧的词边界正则
看不见它 → 习题页被当正文页 → 配置里凭空多出一个 type:1 练习组 → verify B 层为每个
被省略的题号报「缺号」（本书 79 条假 BLOCKING）。

跑法：python config/verify_config/tests/test_exercise_counter_detect.py
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
        sys.path.insert(0, str(_c))
        sys.path.insert(0, str(_c / "lib"))
        break
import lib.boot as _boot
_boot.setup()
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import make_config as mc


def _pages(tmp, blocks_by_page):
    """blocks_by_page: {页号: [块文本, ...]} → 排序后的 page_*.json 路径列表。"""
    paths = []
    for pno, blocks in sorted(blocks_by_page.items()):
        p = os.path.join(tmp, "page_%03d.json" % pno)
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"page": pno, "text": [{"text": t} for t in blocks]}, f,
                      ensure_ascii=False)
        paths.append(p)
    return paths


class TestDetectExerciseCounter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bks_exer_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def detect(self, blocks_by_page):
        return mc._detect_exercise_counter(self.tmp, pages=_pages(self.tmp, blocks_by_page))

    def test_glued_ocr_consolidated_block_is_not_a_counter(self):
        """粘连块标题 + 跨 4 页的题号 1..12：整片都是习题区 → 不检出计数器。"""
        self.assertFalse(self.detect({
            10: ["2. Suppose $H$ is a subgroup.", "3. Prove the cancellation law.",
                 "4. List the elements of $\\langle a \\rangle$."],
            11: ["EXERCISESO", "InExercisesI through4,describe"],
            12: ["5. Determine whether $*$ is associative.", "6. Find the identity.",
                 "7. Show that no such element exists.", "8. Prove the converse.",
                 "9. Give a counterexample."],
            13: ["10. Show that the map is a homomorphism.", "11. Is $\\phi$ injective?",
                 "12. Determine the kernel."],
        }))

    def test_section_exercises_title_page_not_counted(self):
        """干净印刷体「EXERCISES 20」标题 + 其后题号，同样不得检出。"""
        self.assertFalse(self.detect({
            5: ["EXERCISES 20"],
            6: ["1. Prove that every group of order 4 is abelian.",
                "2. Show that $H$ is a subgroup.", "3. Find all left cosets.",
                "4. Define a map.", "5. Is it well defined?", "6. Conclude."],
        }))

    def test_body_enumerations_are_not_a_counter(self):
        """正文枚举（定义内公理表 / 判断题分项）：短链、不足 6 处 → 不检出。"""
        self.assertFalse(self.detect({
            20: ["An operation on $S$ is associative if", "1. closure holds.",
                 "2. associativity holds.", "3. an identity exists."],
            21: ["4. every element has an inverse."],
            40: ["Which of the following are true?", "1. Every subgroup is normal.",
                 "2. The trivial subgroup is normal.", "3. $G$ is abelian."],
        }))

    def test_long_preserved_run_is_detected(self):
        """无标题、跨块连排的 1..6 保留习题 → 检出（真计数器）。"""
        self.assertTrue(self.detect({
            30: ["1. Prove the statement.", "2. Give an example.", "3. Disprove it.",
                 "4. Generalize.", "5. Discuss.", "6. Conclude the argument."],
        }))

    def test_many_short_preserved_runs_are_detected(self):
        """每节只列 3 题、但全书多处重排 → 靠「多处短链」分支检出。"""
        pages = {10 + i: ["1. First item.", "2. Second item.", "3. Third item."]
                 for i in range(6)}
        self.assertTrue(self.detect(pages))


if __name__ == "__main__":
    unittest.main(verbosity=2)
