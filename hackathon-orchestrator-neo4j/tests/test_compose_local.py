"""Local (no-Databricks) tests for the data-story scene engine + freehand tool.

Run from hackathon-orchestrator/:  python3 -m pytest tests/test_compose_local.py
(or `python3 tests/test_compose_local.py` for a quick smoke).

These cover assembly + data-shaping + validation. JS *rendering* of every
archetype is verified separately by headless-Chrome rasterization during build
(see the session notes); this layer guards the Python contract.
"""
from __future__ import annotations

import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.compose_infographic import (  # noqa: E402
    _ARCHETYPES, _assemble, _auto_archetype, _render_local, _shape_scene_data,
    build_compose_infographic_tool,
)
from tools.compose_story import (  # noqa: E402
    _inject_local, _validate, build_compose_story_tool,
)


# ── shapers ──────────────────────────────────────────────────────────────
def test_shape_ranked_bar_sorts_and_caps():
    df = pd.DataFrame({"c": ["a", "b", "c", "d"], "v": [1, 9, 5, 3]})
    d = _shape_scene_data(df, {"type": "ranked_bar", "mapping": {"label_col": "c", "value_col": "v"}, "top_n": 2})
    assert [r["label"] for r in d["rows"]] == ["b", "c"]
    assert d["rows"][0]["value"] == 9.0 and d["rows"][0]["label_fmt"] == "9"


def test_shape_line_multi_groups_series():
    df = pd.DataFrame({"year": [2020, 2021, 2020, 2021], "v": [1, 2, 3, 4], "co": ["X", "X", "Y", "Y"]})
    d = _shape_scene_data(df, {"type": "line_multi", "mapping": {"x_col": "year", "y_col": "v", "series_col": "co"}})
    names = {s["name"] for s in d["series"]}
    assert names == {"X", "Y"}
    assert all(len(s["points"]) == 2 for s in d["series"])


def test_shape_lorenz_gini_monotonic_and_bounded():
    df = pd.DataFrame({"v": [1, 1, 1, 1, 100]})  # concentrated → high Gini
    d = _shape_scene_data(df, {"type": "lorenz_gini", "mapping": {"value_col": "v"}})
    assert d["lorenz_x"][0] == 0 and abs(d["lorenz_x"][-1] - 1) < 1e-9
    assert d["lorenz_y"][0] == 0 and abs(d["lorenz_y"][-1] - 1) < 1e-9
    assert 0.5 < d["gini"] < 1.0


def test_shape_stat_sums_when_multirow():
    df = pd.DataFrame({"v": [10, 20, 30]})
    d = _shape_scene_data(df, {"type": "stat", "mapping": {"value_col": "v"}})
    assert d["value"] == 60.0


def test_inline_data_passes_through():
    payload = {"rows": [{"label": "x", "value": 1}]}
    assert _shape_scene_data(None, {"type": "ranked_bar", "data": payload}) is payload


def test_auto_archetype():
    assert _auto_archetype(pd.DataFrame({"v": [1]})) == "stat"
    assert _auto_archetype(pd.DataFrame({"year": [2020, 2021], "v": [1, 2]})) == "line_multi"
    assert _auto_archetype(pd.DataFrame({"c": ["a", "b"], "v": [1, 2]})) == "ranked_bar"


# ── assembly ─────────────────────────────────────────────────────────────
def test_assemble_injects_data_and_drops_token():
    scenes = [{"type": "stat"}]
    html = _assemble(title="T", kicker="K", lede="L",
                     scenes=scenes, scene_data=[{"value": 5}],
                     stats=[{"value": "5", "label": "things"}],
                     methodology="m", source="s")
    assert '"__DATA__"' not in html
    assert '<!DOCTYPE html>' in html and '"scenes"' in html
    assert 'fxIn' in html  # reliability keyframe present


def test_render_local_multi_scene_story():
    scenes = [
        {"type": "stat", "title": "hero", "data": {"value": 117_300_000}},
        {"type": "ranked_bar", "title": "hosts", "highlight": "Chad",
         "data": {"rows": [{"label": "Iran", "value": 3.8e6}, {"label": "Chad", "value": 1.1e6}]}},
        {"type": "lorenz_gini", "title": "conc",
         "data": {"lorenz_x": [0, 0.5, 1], "lorenz_y": [0, 0.1, 1], "gini": 0.8}},
    ]
    html = _render_local(title="Story", kicker="UNHCR", lede="lede", scenes=scenes, source="UNHCR")
    assert '"__DATA__"' not in html
    assert html.count('"type"') >= 3


def test_all_archetypes_registered():
    expected = {"ranked_bar", "line_multi", "stacked_area", "stacked_area_share",
                "lorenz_gini", "stat", "count_up", "kpi_grid", "forest_ci",
                "heatmap_matrix", "bubble_scatter", "choropleth", "dumbbell",
                "slope", "pyramid", "bar_race", "iceberg", "projection", "sankey_corridors"}
    assert expected.issubset(_ARCHETYPES)


def test_renderers_present_in_scaffold():
    # every archetype must have a RENDERERS.<type> JS function (or alias) in the scaffold
    from tools.compose_infographic import _SCAFFOLD
    for t in ("ranked_bar", "forest_ci", "heatmap_matrix", "choropleth",
              "bubble_scatter", "sankey_corridors", "pyramid", "bar_race",
              "iceberg", "projection", "dumbbell", "slope", "kpi_grid", "count_up"):
        assert f"RENDERERS.{t}" in _SCAFFOLD, f"missing renderer: {t}"


# ── factories ────────────────────────────────────────────────────────────
def test_factories_build():
    t1 = build_compose_infographic_tool(workspace_client=None, variable_store_cls=lambda **k: None, app_url="https://x")
    t2 = build_compose_story_tool(workspace_client=None, app_url="https://x")
    assert t1.name == "compose_infographic" and t2.name == "compose_story"


# ── compose_story ────────────────────────────────────────────────────────
def test_story_validate_and_inject():
    tpl = '<!DOCTYPE html><html><body><script>const DATA="__DATA__";const P="__PALETTE__";</script></body></html>'
    ok, _ = _validate("S", tpl, {"a": 1})
    assert ok
    out = _inject_local(tpl, {"a": 1})
    assert '"__DATA__"' not in out and '"a"' in out
    assert '"signal"' in out  # palette token injected


def test_story_validation_rejects_bad_input():
    assert not _validate("", "<!DOCTYPE html>const DATA=\"__DATA__\"", {})[0]            # no title
    assert not _validate("S", "no doctype const DATA=\"__DATA__\"", {})[0]               # not html
    assert not _validate("S", "<!DOCTYPE html>no token", {})[0]                          # missing token
    assert not _validate("S", '<!DOCTYPE html>const DATA="__DATA__"', None)[0]           # no data


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn(); passed += 1; print(f"  ok  {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            print(f"FAIL  {fn.__name__}: {e}")
    print(f"\n{passed}/{len(fns)} passed")
    sys.exit(0 if passed == len(fns) else 1)
