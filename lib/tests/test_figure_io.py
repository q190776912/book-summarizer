"""Tests for lib/figure_io.py — figure component-count derivation.

Focus: the "no figures" case is now an EXPLICIT figure-group `type` (0 =
UNNUMBERED), and there is NO silent default `2`.  Every book must declare its
figure status, or `load_fig_components` raises `ConfigError`.

Runs under stdlib unittest (no pytest dependency for the harness itself):
    python lib/tests/test_figure_io.py
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
    _ROOT = str(Path(__file__).resolve().parents[2])
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

from lib.figure_io import (  # noqa: E402
    load_fig_components,
    load_fig_labels,
    load_fig_label_re,
    build_fig_label_re,
    _NEVER_RE,
)


def _write_cfg(out_dir, data):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "verify_config.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


class FigureComponentsTest(unittest.TestCase):
    def test_no_figure_config_raises(self):
        """No figure group AND no legacy block -> ConfigError (no silent default)."""
        with tempfile.TemporaryDirectory() as d:
            _write_cfg(d, {"ordinal": [{"type": 3, "name": ["Theorem"]}]})
            with self.assertRaises(Exception) as ctx:
                load_fig_components(d)
            self.assertIn("figure", str(ctx.exception).lower())

    def test_figure_group_missing_type_raises(self):
        """A figure group present but without `type` -> ConfigError, not default."""
        with tempfile.TemporaryDirectory() as d:
            _write_cfg(d, {"ordinal": [
                {"type": 3, "name": ["Theorem"]},
                {"name": ["Figure"]},  # figure group, no type
            ]})
            with self.assertRaises(Exception):
                load_fig_components(d)

    def test_unregistered_type_raises(self):
        """An unregistered figure `type` surfaces OrdinalDepthError, not a phantom depth."""
        with tempfile.TemporaryDirectory() as d:
            _write_cfg(d, {"ordinal": [
                {"type": 99, "name": ["Figure"]},
            ]})
            with self.assertRaises(Exception):
                load_fig_components(d)

    def test_type0_is_explicit_no_figures(self):
        """figure group `type: 0` (UNNUMBERED) == explicit 'no figure numbering'."""
        with tempfile.TemporaryDirectory() as d:
            _write_cfg(d, {"ordinal": [
                {"type": 3, "name": ["Theorem"]},
                {"type": 0, "name": ["Figure"]},
            ]})
            self.assertEqual(load_fig_components(d), 0)
            # components=0 -> never-matching regex (no false figure matches)
            self.assertIs(build_fig_label_re(["Figure"], 0), _NEVER_RE)
            self.assertIs(load_fig_label_re(d), _NEVER_RE)

    def test_type2_real_regex(self):
        """figure group `type: 2` -> 2 components, real chapter.figure regex."""
        with tempfile.TemporaryDirectory() as d:
            _write_cfg(d, {"ordinal": [
                {"type": 2, "name": ["Figure"]},
            ]})
            self.assertEqual(load_fig_components(d), 2)
            reobj = build_fig_label_re(["Figure"], 2)
            self.assertIsNot(reobj, _NEVER_RE)
            self.assertIsNotNone(reobj.search("Figure 3.1"))

    def test_type3_real_regex(self):
        with tempfile.TemporaryDirectory() as d:
            _write_cfg(d, {"ordinal": [{"type": 3, "name": ["Fig"]}]})
            self.assertEqual(load_fig_components(d), 3)
            reobj = build_fig_label_re(["Fig"], 3)
            self.assertIsNotNone(reobj.search("Fig. 3.1.2"))

    def test_legacy_components_honored(self):
        """Transitional `figure.components` block still works (depth 1..3 clamped)."""
        with tempfile.TemporaryDirectory() as d:
            _write_cfg(d, {"figure": {"components": 1}})
            self.assertEqual(load_fig_components(d), 1)

    def test_legacy_components_clamped(self):
        with tempfile.TemporaryDirectory() as d:
            _write_cfg(d, {"figure": {"components": 9}})
            self.assertEqual(load_fig_components(d), 3)

    def test_build_fig_label_re_none_never(self):
        """Explicit None components -> never-matching (no phantom 2)."""
        self.assertIs(build_fig_label_re(["Figure"], None), _NEVER_RE)

    def test_labels_empty_never(self):
        """Empty labels marker -> never-matching regardless of components."""
        self.assertIs(build_fig_label_re([], 2), _NEVER_RE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
