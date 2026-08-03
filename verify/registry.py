"""
registry.py — VerifyLayer contract, LayerRegistry, ManagerConfig, VerifyManager.

ADR-VERIFY-001 §2 / §3.

The manager produces a BYTE-COMPATIBLE result dict that mirrors the legacy
`verify_one()` return contract (the exact key set consumed by `report.print_result`
and `verify_all`). This is the single guarantee that lets us decouple the 17
layers behind a registry WITHOUT touching `report.py`, `verify_all`, `main`,
or the `--fix` CLI surface.

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
import json
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from verify.context import VerifyContext


class Severity(str, Enum):
    """Finding severity. Informational for the legacy byte-level gate."""
    BLOCKING = "blocking"
    WARNING = "warning"
    INFO = "info"


@dataclass
class Finding:
    """A single finding emitted by a layer (extensibility / P-Q hook point).

    The legacy gate does NOT consume these — it consumes the verbatim legacy
    return carried in `LayerResult.metadata`. Findings are for future
    structured reporting and for P/Q layers that opt into the new contract.
    """
    code: str
    severity: Severity
    message: str
    location: Optional[str] = None


@dataclass
class LayerResult:
    """Result of running one layer.

    `legacy`  — the original return value of the relocated legacy function
                (kept for debugging / audit).
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
    changes applied. The manager merges every layer's fix_dict in fix_order,
    which yields exactly the legacy `fix_all_layers` ordering.
    """
    fix_dict: Dict[str, int] = field(default_factory=dict)


@dataclass
class VerifyReport:
    """Whole-run aggregate (extensibility)."""
    chapter: int
    status: str
    result: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ManagerConfig:
    """Per-chapter verify configuration (the 'per-book config' carrier).

    Built fresh per chapter by `verify_all` from chapter_map.json scheme +
    global/per-chapter --ignore / --ignore-figure sets, PLUS any
    <book_dir>/verify_config.json {"disable": [...]} disable set. Pure data;
    no IO here.
    """
    scheme: str = 'three-level'
    ignore_keys: Set[str] = field(default_factory=set)
    ignore_fig: Set[str] = field(default_factory=set)
    manual_path: Optional[str] = None
    disabled: Set[str] = field(default_factory=set)

    @classmethod
    def load_book_config(cls, book_dir: str) -> "ManagerConfig":
        """Read <book_dir>/verify_config.json -> {"disable": ["O", ...]}.

        Returns a config whose `disabled` set is populated from the JSON
        `disable` list (codes upper-cased). Missing/invalid file -> all layers
        enabled. EXTRACT is never disableable (it is the mandatory provider).
        """
        cfg = cls()
        p = os.path.join(book_dir, 'verify_config.json')
        if os.path.exists(p):
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                disable = data.get('disable', [])
                if isinstance(disable, list):
                    cfg.disabled = set(str(x).upper() for x in disable)
            except Exception:
                pass
        return cfg


class VerifyLayer:
    """Base class for every verification layer.

    Subclasses set `code`, `order`, `fix_order`, `auto_fixable` and override
    `run(ctx) -> LayerResult`. Auto-fixable layers also override
    `fix(ctx) -> LayerFixResult`.
    """

    code: str = 'X'
    order: int = 0
    fix_order: int = 999          # only meaningful when auto_fixable
    auto_fixable: bool = False
    depends_on: List[str] = field(default_factory=list)

    def run(self, ctx: VerifyContext) -> LayerResult:
        raise NotImplementedError

    def fix(self, ctx: VerifyContext) -> Optional[LayerFixResult]:
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


# Neutral defaults for every legacy result key. Seed for `verify_one` so that a
# DISABLED layer (per-book verify_config.json) still leaves its legacy keys
# present with correct types — report.print_result must never hit a missing key
# or wrong type. Types MUST match each layer's normal emission:
#   lists -> [], dicts -> {}, ex_proof_gaps -> 2-tuple of lists, fig_skipped -> bool.
DEFAULT_RESULT: Dict[str, Any] = {
    'ch': None, 'md': '', 'status': 'PASS',
    'truly_missing': [], 'mentioned_only': [], 'extra': [],
    'blocking': [], 'warnings': [], 'label_warns': [],
    'katex_errors': [], 'katex_lines': [],
    'entry_keys': set(), 'd_layer': {'missing_sections': [], 'tail_gaps': {}, 'suspect': {}},
    'ignored_hit': [],
    'fig_missing': [], 'fig_extra': [], 'fig_invalid': [], 'fig_invalid_warn': [], 'fig_skipped': False,
    'quote_gaps': [], 'nested_bq': [],
    'ex_proof_gaps': ([], []),
    'h_structural_bq': [], 'h_stmt_bq': [], 'h_ul_bq': [], 'h_mbq': [],
    'i_sep_gaps': [], 'j_header_dash': [], 'k_proof_list': [], 'l_sep_blanks': [], 'm_dm_gt': [], 'n_bq_empty': [],
    'o_subitem_gaps': [],
    'p_exer_block': [], 'p_noise': [], 'p_bare_item': [], 'p_missing_sec': [], 'p_extra_item': [],
    'p_verbose': [], 'p_proof_verbose': [],
    'extract_dir': None, 'items': [],
}


class VerifyManager:
    """Upper-level orchestrator: runs layers, merges results, auto-fixes.

    Produces the byte-compatible verify_one result dict and the byte-compatible
    fix_all_layers change dict.
    """

    def __init__(self, registry: LayerRegistry, config: Optional[ManagerConfig] = None):
        self.registry = registry
        self.config = config or ManagerConfig()

    @classmethod
    def from_registry(cls, registry: LayerRegistry, config: Optional[ManagerConfig] = None):
        return cls(registry, config)

    # ------------------------------------------------------------------ run
    def _build_context(self, ch, start, end, md_file, ext_dir) -> VerifyContext:
        cfg = self.config
        return VerifyContext(
            ch=ch, start=start, end=end, md_file=md_file, ext_dir=ext_dir,
            manual_path=cfg.manual_path,
            ignore_keys=cfg.ignore_keys,
            ignore_fig=cfg.ignore_fig,
            scheme=cfg.scheme,
        )

    def verify_one(self, ch, start, end, md_file, ext_dir) -> Dict[str, Any]:
        """Run all layers in `order` and merge their metadata (last-writer-wins
        by insertion order via dict.update) into the byte-compatible dict.

        Per-book disable: any layer whose code is in `self.config.disabled`
        (except the mandatory EXTRACT provider) is skipped; its legacy keys are
        seeded from DEFAULT_RESULT so print_result stays byte-safe.
        """
        ctx = self._build_context(ch, start, end, md_file, ext_dir)
        merged: Dict[str, Any] = {}
        for layer in self.registry.all_ordered():
            # Per-book disable: skip every layer except the mandatory EXTRACT provider.
            if layer.code != 'EXTRACT' and layer.code in self.config.disabled:
                continue
            res = layer.run(ctx)
            if res is None or not res.metadata:
                continue
            # last-writer-wins: later layers (e.g. B) override earlier ones
            # (e.g. EXTRACT) for the same key (blocking / ignored_hit).
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
        """Run every auto-fixable layer in `fix_order`, returning the
        byte-compatible change dict {h, h_stmt, h_ul, h_mbq, g, i, j, k, l, m, n}.

        Per-book disable: layers in `self.config.disabled` are skipped (their
        fix_dict keys are simply absent from the result).
        """
        ctx = VerifyContext(
            ch=None, start=None, end=None, md_file=md_file, ext_dir=None,
            ignore_keys=set(), ignore_fig=set(),
            scheme=self.config.scheme,
        )
        result: Dict[str, int] = {}
        for layer in self.registry.fixable_ordered():
            if layer.code in self.config.disabled:
                continue
            fr = layer.fix(ctx)
            if fr is None:
                continue
            result.update(fr.fix_dict)
        return result
