
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))

import json, sys, os
if len(sys.argv) < 2:
    print("Usage: python write_chapter_map.py <extract_dir>")
    sys.exit(1)
out_dir = sys.argv[1]
cm = {
    "1": {"name": "曲线", "name_en": "Curves", "start": 9, "end": 58},
    "2": {"name": "正则曲面", "name_en": "Regular Surfaces", "start": 59, "end": 141},
    "3": {"name": "高斯映射的几何", "name_en": "The Geometry of the Gauss Map", "start": 142, "end": 224},
    "4": {"name": "曲面的内蕴几何", "name_en": "The Intrinsic Geometry of Surfaces", "start": 225, "end": 322},
    "5": {"name": "全局微分几何", "name_en": "Global Differential Geometry", "start": 323, "end": 478},
}
with open(os.path.join(out_dir, "chapter_map.json"), "w", encoding="utf-8") as f:
    json.dump(cm, f, ensure_ascii=False, indent=2)
print(f"chapter_map.json written to {os.path.join(out_dir, 'chapter_map.json')}")
