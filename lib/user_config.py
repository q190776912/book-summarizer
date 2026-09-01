"""book-summarizer user configuration loader.

Priority (highest first):
  1. ``BKS_*`` environment variables (script / CI friendly, no config file needed)
  2. ``<skill root>/user_config.json``   (user's own overrides; GITIGNORED, not uploaded)
  3. built-in ``_DEFAULTS``              (author's machine values, committed in code)

On a fresh machine the loader silently falls back to the built-in defaults,
and :func:`discover` probes common locations for the missing pieces, so the
first-use flow (see SKILL.md「首次使用配置」) can present discovered paths to
the user as defaults and ask for confirmation instead of guessing.

Derived model paths (from ``model_root``) are provided by :func:`weight_paths`,
so a per-user install only needs to set ``model_root`` to its own
PDF-Extract-Kit checkout; individual weight subpaths are never configured
by hand.

CLI (used by bash launchers and the agent):

    python lib/user_config.py get <dotted.key>     # prints the resolved value
    python lib/user_config.py <dotted.key>         # short form (same as `get`)
    python lib/user_config.py status               # JSON: resolved + missing + discovered
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

#: Built-in defaults (author's machine). Fallback when user_config.json is absent.
_DEFAULTS = {
    "corpus_root": "D:/study/book",
    "model_root": "D:/study/model/PDF-Extract-Kit",
    "conda": {
        "env_name": "pdfextract",
        "env_path": "D:/anaconda3/envs/pdfextract",
    },
    "paddleocr_cache": str(Path.home() / ".paddleocr").replace("\\", "/"),
}

#: dotted config key -> environment variable override
_ENV_KEYS = {
    "corpus_root": "BKS_CORPUS_ROOT",
    "model_root": "BKS_MODEL_ROOT",
    "conda.env_name": "BKS_CONDA_ENV_NAME",
    "conda.env_path": "BKS_CONDA_ENV_PATH",
    "paddleocr_cache": "BKS_PADDLEOCR_CACHE",
}

#: required keys (must resolve to something real for extraction to work)
_REQUIRED = ("corpus_root", "model_root", "conda.env_path")

#: keys whose value must be an EXISTING path to count as resolved
_PATH_KEYS = ("corpus_root", "model_root", "conda.env_path")

_cache = None
_discover_cache = None


def root():
    """Skill root (the directory containing ``SKILL.md``), self-contained."""
    here = Path(__file__).resolve()
    for cand in (here, *here.parents):
        if (cand / "SKILL.md").exists():
            return cand
    return here.parents[1]


def _load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _deep_merge(base, overlay):
    out = dict(base)
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _set_dotted(cfg, dotted, value):
    parts = dotted.split(".")
    node = cfg
    for p in parts[:-1]:
        node = node.setdefault(p, {})
    node[parts[-1]] = value


def load():
    """Merged config dict (env > user_config.json > built-in defaults).

    Cached after the first call; safe to call from any entry point.
    """
    global _cache
    if _cache is not None:
        return _cache
    cfg = _deep_merge(_DEFAULTS, _load_json(root() / "user_config.json"))
    for key, env in _ENV_KEYS.items():
        val = os.environ.get(env)
        if val:
            _set_dotted(cfg, key, val)
    _cache = cfg
    return cfg


def get(key, default=None):
    """Resolve a dotted config key (e.g. ``conda.env_path``)."""
    node = load()
    for p in key.split("."):
        if not isinstance(node, dict) or p not in node:
            return default
        node = node[p]
    return node


def weight_paths(model_root=None):
    """Derive the PDF-Extract-Kit weight / package paths from ``model_root``."""
    mr = (model_root or get("model_root") or "").rstrip("/\\")
    return {
        "pek_root": mr,
        "pek_pkg": f"{mr}/pdf_extract_kit",
        "mfd_weight": (f"{mr}/models/models/opendatalab--PDF-Extract-Kit/snapshots/master/"
                       "models/MFD/models/MFD/YOLO/yolo_v8_ft.pt"),
        "mfr_dir": f"{mr}/models/MFR/unimernet_tiny",
        "mfr_cfg": f"{mr}/pdf_extract_kit/configs/unimernet.yaml",
        "ocr_det": f"{mr}/models/OCR/PaddleOCR/det/ch_PP-OCRv4_det",
        "ocr_rec": f"{mr}/models/OCR/PaddleOCR/rec/ch_PP-OCRv4_rec",
        "layout_weight": f"{mr}/models/Layout/YOLO/doclayout_yolo_ft.pt",
    }


# ---------------------------------------------------------------------------
# Auto-discovery: conservative probes of common locations, used by the
# first-use flow to offer defaults before asking the user.
# ---------------------------------------------------------------------------

def _probe(path):
    return str(path).replace("\\", "/") if path and Path(path).exists() else None


def _find_conda_env(env_name):
    """Locate <conda_root>/envs/<env_name> via `conda info --base` or common roots."""
    base = None
    conda = shutil.which("conda")
    if conda:
        try:
            out = subprocess.run([conda, "info", "--base"], capture_output=True,
                                 text=True, timeout=30)
            if out.returncode == 0 and out.stdout.strip():
                base = Path(out.stdout.strip())
        except (OSError, subprocess.TimeoutExpired):
            base = None
    if base is None:
        user = Path.home()
        for cand in (Path("D:/anaconda3"), Path("D:/miniconda3"),
                     user / "anaconda3", user / "miniconda3",
                     Path("C:/ProgramData/anaconda3"), Path("C:/ProgramData/miniconda3")):
            if cand.exists():
                base = cand
                break
    if base is None:
        return None
    return _probe(base / "envs" / env_name / "python.exe").rsplit("/python.exe", 1)[0] if \
        (base / "envs" / env_name / "python.exe").exists() else None


def _find_model_root():
    user = Path.home()
    for cand in (Path("D:/study/model/PDF-Extract-Kit"), Path("D:/models/PDF-Extract-Kit"),
                 user / "models/PDF-Extract-Kit", user / "PDF-Extract-Kit"):
        if (cand / "pdf_extract_kit").is_dir():
            return _probe(cand)
    return None


def _find_corpus_root():
    user = Path.home()
    for cand in (Path("D:/study/book"), Path("D:/books"),
                 user / "study/book", user / "books"):
        if cand.is_dir():
            return _probe(cand)
    return None


def _find_paddleocr_cache():
    cand = Path.home() / ".paddleocr"
    return _probe(cand) if cand.is_dir() else None


def discover():
    """Probe common locations for each key; returns ``{dotted_key: path|None}``.

    Only checks what is NOT already configured/resolved, so a configured
    machine is untouched. Cached; cheap (pure filesystem probes).
    """
    global _discover_cache
    if _discover_cache is not None:
        return _discover_cache
    env_name = get("conda.env_name")
    res = {
        "conda.env_path": _find_conda_env(env_name),
        "model_root": _find_model_root(),
        "corpus_root": _find_corpus_root(),
        "paddleocr_cache": _find_paddleocr_cache(),
    }
    _discover_cache = res
    return res


def _resolved(key):
    """True when the key has a value that actually works (path keys must exist)."""
    val = get(key)
    if not val:
        return False
    if key in _PATH_KEYS:
        return Path(val).exists()
    return True


def _default_of(dotted):
    """Resolve a dotted key against the built-in ``_DEFAULTS`` tree (None when absent)."""
    node = _DEFAULTS
    for p in dotted.split("."):
        if not isinstance(node, dict) or p not in node:
            return None
        node = node[p]
    return node


def missing():
    """Return ``{dotted_key: {...}}`` for every required key that is not
    resolved: unset, or a configured path that does not exist. Each entry
    carries the current value, the built-in default, and any auto-discovered
    candidate, so the first-use flow can present options before asking."""
    out = {}
    disc = discover()
    for key in _REQUIRED:
        if _resolved(key):
            continue
        val = get(key)
        out[key] = {
            "configured": val or None,
            "default": _default_of(key),
            "discovered": disc.get(key) or None,
            "exists": bool(val) and Path(val).exists() if key in _PATH_KEYS else None,
        }
    return out


if __name__ == "__main__":
    argv = sys.argv[1:]
    # `get <dotted.key>` (documented) and bare `<dotted.key>` (used by
    # launchers) are both accepted; anything else is a usage error.
    if len(argv) == 2 and argv[0] == "get":
        key = argv[1]
    elif len(argv) == 1 and argv[0] != "get":
        key = argv[0]
    else:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    if key == "status":
        cfg = load()
        disc = discover()
        print(json.dumps({
            "resolved": {k: {"value": get(k), "exists": _resolved(k)}
                         for k in _REQUIRED},
            "all": {k: v for k, v in cfg.items()},
            "discovered": disc,
            "missing": missing(),
        }, ensure_ascii=False, indent=2))
        sys.exit(0)
    val = get(key)
    if val is None:
        print(f"config key not found: {key}", file=sys.stderr)
        sys.exit(1)
    print(val)