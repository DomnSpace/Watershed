#!/usr/bin/env python3
"""Build the deliberately falsifiable Atolia / Atesis 200 kt copper-flow overlay.

This does NOT assert 200,000 t as archaeological fact. It turns the scenario
hypothesis into machine-readable map layers so later tests can attack it.
"""
from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
from shapely.geometry import LineString, Point

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "hypotheses" / "atolia_atesis_1800_1000_v0.json"
OUT = ROOT / "site" / "data"


def main() -> None:
    cfg = json.loads(SCENARIO.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)

    pts = cfg["corridor_waypoints"]
    coords = [(p["lon"], p["lat"]) for p in pts]

    trunk = gpd.GeoDataFrame(
        [{
            "scenario_id": cfg["scenario_id"],
            "label": "Atesis copper corridor hypothesis",
            "target_tonnes": cfg["claim"]["target_tonnes"],
            "mean_tonnes_per_year": cfg["claim"]["mean_tonnes_per_year"],
            "start_bc": cfg["claim"]["start_bc"],
            "end_bc": cfg["claim"]["end_bc"],
            "status": cfg["status"],
            "geometry": LineString(coords),
        }],
        crs="EPSG:4326",
    )

    nodes = gpd.GeoDataFrame(
        [{**p, "scenario_id": cfg["scenario_id"], "geometry": Point(p["lon"], p["lat"])} for p in pts],
        crs="EPSG:4326",
    )

    anchors = gpd.GeoDataFrame(
        [{**a, "scenario_id": cfg["scenario_id"], "geometry": Point(a["lon"], a["lat"])} for a in cfg["evidence_anchors"]],
        crs="EPSG:4326",
    )

    # One feature per phase, all sharing the trunk geometry. The frontend can
    # select by date and scale line width by tonnes/year.
    phases = gpd.GeoDataFrame(
        [{
            **phase,
            "scenario_id": cfg["scenario_id"],
            "target_total_tonnes": cfg["claim"]["target_tonnes"],
            "geometry": LineString(coords),
        } for phase in cfg["time_prior"]],
        crs="EPSG:4326",
    )

    trunk.to_file(OUT / "atolia_atesis_trunk.geojson", driver="GeoJSON")
    nodes.to_file(OUT / "atolia_atesis_nodes.geojson", driver="GeoJSON")
    anchors.to_file(OUT / "atolia_copper_evidence_anchors.geojson", driver="GeoJSON")
    phases.to_file(OUT / "atolia_atesis_phases.geojson", driver="GeoJSON")

    summary = {
        "scenario_id": cfg["scenario_id"],
        "claim": cfg["claim"],
        "time_prior": cfg["time_prior"],
        "tests": cfg["tests"],
    }
    (OUT / "atolia_atesis_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Built Atolia copper hypothesis overlay in {OUT}")


if __name__ == "__main__":
    main()
