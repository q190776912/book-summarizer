# -*- coding: utf-8 -*-
"""test_upgrade_flat_same_style_declaration.py — legacy 扁平配置的 [CONFIG] 警告消除通道。

实测成因（Arnold《经典力学的数学方法》，2026-10-03）：16 个字母附录章按 kind 路由到
`'appendix'` 子配置，而 `verify_config.json` 是**扁平（legacy）格式**（顶层即正文体例、
没有 `ch` 包裹）→ 每轮 verify 打 32 行 `[CONFIG] 附录/补篇配置缺失` 回退警告。
下游 prescribed 的出路 `--force` 对这类书**不安全**：整份重扫会洗掉人工账
（`section_types [1,1,5]→[1,2]`、`sections_global true→丢失`、凭空多出英文标签 group）。

本文件锁死窄通道的三条判据：
1. **只写声明**：判明同体例 → 顶层补 `_special_same_style`，其余键**逐字节不动**；
2. **幂等**：声明已在账 → 不重写文件；
3. **不写惰性键**：判明附录需要独立子配置时**绝不**往扁平文件里塞 `appendix` 字典
   （扁平分支不消费它，写了等于假装有配置），只打印转换指引。

运行：
  python config/verify_config/tests/test_upgrade_flat_same_style_declaration.py
"""
import json
import os
import subprocess
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

MAKE_CONFIG_DIR = os.path.join(_ROOT, "config", "verify_config")

# 一份**人工登记过**的扁平配置（形状照 Arnold 实测）：这些键在增量升级里必须原样活着。
FLAT_CFG = {
    "ordinal": [
        {"name": ["图"], "type": 1, "scope": 1},
        {"name": ["定理"], "type": 1, "scope": 3},
        {"name": ["定义"], "type": 1, "scope": 3},
    ],
    "strict": True,
    "language": "cn",
    "chapter_first": True,
    "section_scoped": False,
    "formula": {"type": 1, "scope": 3, "bare_number": True, "ignore": [],
                "known_book": ["2"]},
    "section_types": [1, 1, 5],
    "sections_global": True,
    "_provenance": {"generated_by": "make_config.py", "mm_repair_done": True},
}

# 探测器结论 canned（`_generate_special_verify_configs` 的返回形状）。
SAME_STYLE = {"appendix": None, "supplement": None, "same_style": ["appendix"]}
NEEDS_SUB = {"appendix": {"ordinal": [{"name": ["定理"], "type": 13, "scope": 3}]},
             "supplement": None, "same_style": []}

_DRIVER = """
import json, sys
sys.path.insert(0, %r)
import make_config as mc
mc._generate_special_verify_configs = lambda ext: json.loads(sys.argv[2])
declared = mc._upgrade_missing_special_keys(sys.argv[1], sys.argv[3])
print("DECLARED:" + json.dumps(declared))
"""


def _run(ext, special, cfg_path):
    r = subprocess.run([sys.executable, "-c", _DRIVER % MAKE_CONFIG_DIR,
                        ext, json.dumps(special), cfg_path],
                       capture_output=True, text=True, timeout=120,
                       encoding="utf-8", errors="replace")
    assert r.returncode == 0, "driver failed: %s\n%s" % (r.stdout, r.stderr)
    return r.stdout, r.stderr


class FlatDeclaration(unittest.TestCase):
    def setUp(self):
        d = tempfile.mkdtemp()
        self.ext = os.path.join(d, "_extract")
        os.makedirs(self.ext, exist_ok=True)
        self.cfg = os.path.join(self.ext, "verify_config.json")
        with open(self.cfg, "w", encoding="utf-8") as f:
            json.dump(FLAT_CFG, f, ensure_ascii=False, indent=2)

    def _read(self):
        with open(self.cfg, encoding="utf-8-sig") as f:
            return json.load(f)

    def test_declaration_written_and_every_other_key_untouched(self):
        out, _err = _run(self.ext, SAME_STYLE, self.cfg)
        self.assertIn('DECLARED:["appendix"]', out.replace(" ", ""))
        data = self._read()
        self.assertEqual(data.get("_special_same_style"), ["appendix"])
        for k, v in FLAT_CFG.items():
            self.assertEqual(json.dumps(data.get(k), sort_keys=True),
                             json.dumps(v, sort_keys=True),
                             "扁平增量升级改写了人工登记的 %s 键" % k)

    def test_idempotent_no_rewrite_when_already_declared(self):
        _run(self.ext, SAME_STYLE, self.cfg)
        before = self._read()
        mtime = os.path.getmtime(self.cfg)
        out, _err = _run(self.ext, SAME_STYLE, self.cfg)
        self.assertIn('DECLARED:[]', out.replace(" ", "").replace("\n", ""))
        self.assertEqual(os.path.getmtime(self.cfg), mtime,
                         "已在账的声明被重复重写（应幂等跳过）")
        self.assertEqual(self._read(), before)

    def test_letter_led_appendix_never_written_as_inert_key(self):
        _run(self.ext, NEEDS_SUB, self.cfg)
        data = self._read()
        self.assertNotIn("appendix", data,
                         "往扁平文件塞了 `appendix` 字典——扁平分支不消费它，"
                         "这条惰性键会让下游以为附录有配置")
        self.assertNotIn("_special_same_style", data,
                         "结论是「需要独立子配置」却登记了同体例声明")

    def test_no_conclusion_keeps_warning_channel_open(self):
        _run(self.ext, {"appendix": None, "supplement": None, "same_style": []},
             self.cfg)
        self.assertNotIn("_special_same_style", self._read(),
                         "从没扫出结论却写了声明 → 会把真错配的警告错误消音")


class LoaderConsumesFlatDeclaration(unittest.TestCase):
    """消费侧必须读扁平配置的顶层声明，否则写了也白写。"""

    def test_loader_silences_fallback_for_flat_config(self):
        d = tempfile.mkdtemp()
        ext = os.path.join(d, "_extract")
        os.makedirs(ext, exist_ok=True)
        cfg = os.path.join(ext, "verify_config.json")
        with open(os.path.join(ext, "_extraction_done.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"done": True}, f)
        data = dict(FLAT_CFG)
        data["_special_same_style"] = ["appendix"]
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        sys.path.insert(0, MAKE_CONFIG_DIR)
        from verify_config import ConfigLoader
        loader = ConfigLoader(ext, os.path.dirname(ext))
        self.assertIn("appendix", getattr(loader, "special_same_style", set()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
