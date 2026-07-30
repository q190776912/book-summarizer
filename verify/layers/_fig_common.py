import re, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    import cv2
except Exception:
    cv2 = None
from verify.key_parse import sortkey
FIG_CAP_RE = re.compile(r'图\s*([0-9]+(?:\.[0-9]+){1,2})')
def normfig(s):
    return str(s).strip().replace(' ', '')
def load_figure_index(ext):
    p = os.path.join(ext, 'figure_index.json')
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None
