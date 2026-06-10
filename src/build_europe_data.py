#!/usr/bin/env python3
"""Build Europe watershed data into site/data/europe without writing index.html.

This lets the tabbed site shell be generated separately while preserving the
existing Europe hydrology builder and hover-debugging behavior.
"""

from pathlib import Path

from build_pages import build_regions, build_rivers, write_geojson


def main() -> None:
    site = Path("site")
    data = site / "data" / "europe"
    regions, basins, terminals, basin_debug = build_regions(level=7, channel_as="Atlantic Europe")
    rivers = build_rivers(regions)
    write_geojson(regions, data / "regions.geojson", simplify=0.006)
    write_geojson(basins, data / "basins.geojson", simplify=0.004)
    write_geojson(rivers, data / "rivers.geojson", simplify=0.006)
    terminals.to_csv(data / "terminal_debug_points.csv", index=False)
    basin_debug.to_csv(data / "basin_debug_points.csv", index=False)
    print("Built Europe tab data in ./site/data/europe")


if __name__ == "__main__":
    main()
