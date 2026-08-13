"""verify/script/base.py — layer contract, registry, orchestration, and the
slim VerifyContext runtime carrier.

Relocated from verify/registry.py (layer contract + orchestration) and
verify/context.py (VerifyContext).  The CONFIG itself now lives in
`config` (ConfigLoader / BookConfig); this module is purely about the
layer execution machinery, NOT config loading.

The manager produces a BYTE-COMPATIBLE result dict that mirrors the legacy
`verify_one()` return contract (the exact key set consumed by
`report.print_result` and `verify_all`).  This is the single guarantee that
lets us decouple the layers behind a registry WITHOUT touching report.py or
the --fix CLI surface.

Result-dict contract (must stay identical to the old `verify_one` return):
    ch, md, status, truly_missing, mentioned_only, extra, blocking, warnings,
    label_warns, katex_errors, katex_lines, entry_keys, d_layer, ignored_hit,
    fig_missing, fig_extra, fig_invalid, fig_invalid_warn, fig_skipped,
    quote_gaps, nested_bq, ex_proof_gaps, h_structural_bq, h_stmt_bq, h_ul_bq,
    h_mbq, i_sep_gaps, j_header_dash, k_proof_list, l_sep_blanks, m_dm_gt,
    n_bq_empty, o_subitem_gaps,
    p_exer_block, p_noise, p_bare_item, p_missing_sec, p_extra_item,
    p_verbose, p_proof_verbose,
    extract_dir, items

Fix-dict contract (must stay identical to the old `fix_all_layers` return order):
    h, h_stmt, h_ul, h_mbq, g, i, j, k, l, m, n
"""
import os
import sys
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

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from verify_config import BookConfig, ConfigLoader


class Severity(str, Enum):
    """Finding severity. Informational for the legacy byte-level gate."""
    BLOCKING = "blocking"
    WARNING = "warning"
    INFO = "info"


@dataclass
class Finding:
    """A single finding emitted by a layer (extensibility / P-Q hook point)."""
    code: str
    severity: Severity
    message: str
    location: Optional[str] = None


@dataclass
class LayerResult:
    """Result of running one layer.

    `legacy`  — the original return value of the relocated legacy function.
    `metadata`— the subset of keys this layer contributes to the merged
                verify_one result dict. Last-writer-wins on key collision.
    `findings`— optional structured findings (unused by legacy gate).
    """
    code: str
    legacy: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    findings: List[Finding] = field(default_factory=list)


@dataclass
class LayerFixResult:
    """Result of an auto-fix pass for one layer.

    `fix_dict` maps a fix-key (e.g. 'h', 'h_stmt', 'g') to the number of
    changes applied."""
    fix_dict: Dict[str, int] = field(default_factory=dict)


@dataclass
class VerifyReport:
    """Whole-run aggregate (extensibility)."""
    chapter: int
    status: str
    result: Dict[str, Any] = field(default_factory=dict)


class VerifyLayer:
    """Base class for every verification layer.

    Subclasses set `code`, `order`, `fix_order`, `auto_fixable` and override
    `run(ctx) -> LayerResult`. Auto-fixable layers also override
    `fix(ctx) -> Optional[LayerFixResult]`.
    """

    code: str = 'X'
    order: int = 0
    fix_order: int = 999          # only meaningful when auto_fixable
    auto_fixable: bool = False
    depends_on: List[str] = field(default_factory=list)

    def run(self, ctx) -> LayerResult:
        raise NotImplementedError

    def fix(self, ctx) -> Optional[LayerFixResult]:
        return None


class LayerRegistry:
    """Registry of available layers, ordered for run / fix scheduling."""

    def __init__(self):
        self._layers: Dict[str, VerifyLayer] = {}

    def register(self, layer: VerifyLayer) -> VerifyLayer:
        self._layers[layer.code] = layer
        return layer

    def get(self, code: str) -> Optional[VerifyLayer]:
        return self._layers.get(code)

    def all_ordered(self) -> List[VerifyLayer]:
        return sorted(self._layers.values(), key=lambda l: l.order)

    def fixable_ordered(self) -> List[VerifyLayer]:
        return sorted(
            (l for l in self._layers.values() if l.auto_fixable),
            key=lambda l: (l.fix_order, l.order),
        )

    def by_code(self) -> Dict[str, VerifyLayer]:
        return dict(self._layers)


# ---------------------------------------------------------------------------
# Fixer registry — 把「自动修复实现」与 VerifyLayer（现仅含检测逻辑）彻底解耦。
# 每个可自动修的层，其修复逻辑放在独立的 `fix_<snake>.py` 模块，暴露
# `apply_fix(ctx) -> LayerFixResult`，并在模块顶层调用
# `register_fixer(code, fix_order, apply_fix)` 完成注册。修复字典
# {h, h_stmt, h_ul, h_mbq, g, i, j, k, l, m, n} 字节兼容不变。
# ---------------------------------------------------------------------------
FIXERS: Dict[str, tuple] = {}  # code -> (fix_order, apply_fix_fn)


def register_fixer(code: str, fix_order: int, fn) -> None:
    """注册某层的自动修复实现（在 fix_<snake>.py 顶层调用）。"""
    FIXERS[code] = (fix_order, fn)


def fixable_ordered_fixers():
    """按 fix_order 排序的 (code, (fix_order, fn)) 列表。"""
    return sorted(FIXERS.items(), key=lambda kv: (kv[1][0], kv[0]))


# Neutral defaults for every legacy result key. Seed for `verify_one` so that a
# layer that does not emit a key still leaves it present with correct types.
# Types MUST match each layer's normal emission:
#   lists -> [], dicts -> {}, ex_proof_gaps -> 2-tuple of lists, fig_skipped -> bool.
DEFAULT_RESULT: Dict[str, Any] = {
    'ch': None, 'md': '', 'status': 'PASS',
    'truly_missing': [], 'mentioned_only': [], 'extra': [],
    'blocking': [], 'warnings': [], 'label_warns': [],
    'katex_errors': [], 'katex_lines': [],
    'b_gap_warnings': [], 'b_tail_warnings': [],
    'entry_keys': set(), 'd_layer': {'continuity_sections': [], 'missing_sections': [], 'levels': {}},
    # Top-level mirror of d_layer['levels'] (declared in verify/section_continuity/section_continuity.md's
    # contract-keys block so the doc/code key-set parity test stays green given
    # `levels` is also surfaced there; the live value lives nested in `d_layer`).
    'levels': {},
    'ignored_hit': [],
    'fig_missing': [], 'fig_extra': [], 'fig_invalid': [], 'fig_invalid_warn': [], 'fig_skipped': False,
    'quote_gaps': [], 'nested_bq': [],
    'ex_proof_gaps': ([], []),
    'h_structural_bq': [], 'h_stmt_bq': [], 'h_ul_bq': [], 'h_mbq': [],
    'i_sep_gaps': [], 'j_header_dash': [], 'k_proof_list': [], 'l_sep_blanks': [], 'm_dm_gt': [], 'n_bq_empty': [],
    'o_subitem_gaps': [],
    'p_exer_block': [], 'p_noise': [], 'p_bare_item': [], 'p_missing_sec': [], 'p_extra_item': [],
    'p_verbose': [], 'p_proof_verbose': [],
    # Q-LAYER: formula sequence-label audit (opt-in via `formula` map; see q_layer.py).
    'q_checked': False,
    'q_fabricated': [], 'q_inconsistent': [], 'q_missing': [],
    'q_rows': [],
    'extract_dir': None, 'items': [],
}


class VerifyContext:
    """Slim per-run runtime carrier (relocated from context.py).

    Holds ONLY runtime state + a reference to the immutable per-chapter
    BookConfig (built by ConfigLoader.config_for_chapter).  It does NOT load
    any config from disk.  Layers read `ctx.config` (whose `ordinal` is now an
    INTEGER style code — see config ORDINAL_*) / `ctx.language` / `ctx.ignore`.

    Design rules (ADR-VERIFY-001 §3.5):
      * No module-level mutable state anywhere in the verify package.
      * Layers re-read the .md each call via `read_md_lines()` so a `--fix`
        mutation followed by a re-check sees the freshest bytes.
      * Derived fields (items / entry_keys / ... / ignored_hit / ...) are
        populated by the EXTRACT provider + B layer, never by globals.
    """

    def __init__(self, ch, start, end, md_file, ext_dir, config: BookConfig,
                 figure_index=None, manual_overrides=None, ignore_fig=None):
        self.ch = ch
        self.start = start
        self.end = end
        self.md_file = md_file
        self.ext_dir = ext_dir
        self.config = config
        self.figure_index = figure_index
        self.manual_overrides = manual_overrides
        self.ignore_fig = ignore_fig or set()

        # --- derived (populated by EXTRACT provider + B layer) ---
        # EXTRACT 供水：items / entry_keys / all_keys / label_warns
        # B 层查漏：ignored_hit / extraction_blocking
        self.items = None
        self.entry_keys = None
        self.all_keys = None
        self.ignored_hit = None
        self.extraction_blocking = None
        self.label_warns = None
        self.provided = set()
        self.skipped = set()

    def read_md_lines(self):
        """Read the .md fresh from disk (UTF-8). Called by structural layers."""
        with open(self.md_file, encoding='utf-8') as f:
            return f.read().split('\n')

    # --- config-forwarding properties (single read path) ---
    # NOTE: `BookConfig.ordinal` is now a List[GroupConfig].  `ctx.ordinal`
    # forwards the PRIMARY style code (an int) for legacy consumers that still
    # branch on the integer; use `ctx.config.ordinal` for the group array and
    # `ctx.primary_type` for the int.
    @property
    def ordinal(self) -> int:
        return self.config.primary_type

    @property
    def primary_type(self) -> int:
        return self.config.primary_type

    @property
    def language(self) -> str:
        return self.config.language

    @property
    def ignore(self) -> Set[str]:
        return set(self.config.ignore)


class VerifyManager:
    """Upper-level orchestrator: runs layers, merges results, auto-fixes.

    Produces the byte-compatible verify_one result dict and the byte-compatible
    fix_all_layers change dict.  Reads configuration exclusively through a
    ConfigLoader (constructed once by the caller).
    """

    def __init__(self, registry: LayerRegistry, loader: ConfigLoader):
        self.registry = registry
        self.loader = loader

    # ------------------------------------------------------------------ run
    def verify_one(self, ch, start, end, md_file, ext_dir) -> Dict[str, Any]:
        """Run all layers in `order` and merge their metadata (last-writer-wins
        by insertion order via dict.update) into the byte-compatible dict.

        Every layer ALWAYS runs (the old `disable` mechanism is gone).  Suppression
        of known noise is via the unified `ignore` set, surfaced as a WARNING
        gate rather than by skipping a layer.
        """
        cfg = self.loader.config_for_chapter(ch)
        manual = self.loader.manual_for_chapter(ch)
        ctx = VerifyContext(
            ch=ch, start=start, end=end, md_file=md_file, ext_dir=ext_dir,
            config=cfg,
            figure_index=self.loader.figure_index,
            manual_overrides=manual,
        )
        merged: Dict[str, Any] = {}
        for layer in self.registry.all_ordered():
            res = layer.run(ctx)
            if res is None or not res.metadata:
                continue
            merged.update(res.metadata)

        final = dict(DEFAULT_RESULT)
        final.update({
            'ch': ch,
            'md': md_file,
            'status': 'PASS',
            'extract_dir': ext_dir,
            'items': ctx.items if ctx.items is not None else [],
        })
        final.update(merged)
        return final

    # ------------------------------------------------------------------ fix
    def fix(self, md_file) -> Dict[str, int]:
        """Run every auto-fix in `fix_order`, returning the byte-compatible
        change dict {h, h_stmt, h_ul, h_mbq, g, i, j, k, l, m, n}.

        修复实现位于独立的 `fix_<snake>.py` 模块（经 FIXERS 注册）。当 FIXERS 为空
        （过渡期 / 尚未迁移修复器）时，回退到各层的 `layer.fix`（旧路径），保证 --fix 不回归。
        """
        cfg = self.loader.book
        ctx = VerifyContext(
            ch=None, start=None, end=None, md_file=md_file, ext_dir=None,
            config=cfg, figure_index=self.loader.figure_index,
        )
        result: Dict[str, int] = {}
        if FIXERS:
            for code, (fix_order, fn) in fixable_ordered_fixers():
                fr = fn(ctx)
                if fr is None:
                    continue
                result.update(fr.fix_dict)
            return result
        # 过渡回退：FIXERS 未注册任何修复器时，使用各层自身 fix()。
        for layer in self.registry.fixable_ordered():
            fr = layer.fix(ctx)
            if fr is None:
                continue
            result.update(fr.fix_dict)
        return result
