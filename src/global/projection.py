#!/usr/bin/env python3
"""Projection helpers for the global watershed map.

The visual target is a United-Nations-emblem-like north-polar azimuthal map.
This module keeps projection logic separate from hydrological classification so
we can later switch from GeoJSON to SVG/TopoJSON without rewriting the builder.
"""

from __future__ import annotations

import math
from typing import Iterable, Tuple

# Spherical radius used only for display coordinates, not measurement.
DISPLAY_RADIUS = 1.0


def lonlat_to_un_azimuthal(lon: float, lat: float, radius: float = DISPLAY_RADIUS) -> Tuple[float, float]:
    """Project lon/lat into a simple north-polar azimuthal equidistant plane.

    Formula:
        rho = R * (pi/2 - phi)
        x = rho * sin(lambda)
        y = -rho * cos(lambda)

    This places the North Pole at (0, 0), Greenwich downward, and the equator
    approximately at radius pi/2. The frontend can scale/translate this to a
    circular UN-symbol-style map.
    """
    lam = math.radians(lon)
    phi = math.radians(lat)
    rho = radius * (math.pi / 2.0 - phi)
    x = rho * math.sin(lam)
    y = -rho * math.cos(lam)
    return x, y


def project_ring(coords: Iterable[Tuple[float, float]]) -> list[list[float]]:
    """Project one GeoJSON ring from lon/lat to display x/y."""
    return [[*lonlat_to_un_azimuthal(float(lon), float(lat))] for lon, lat in coords]


def project_geometry_mapping(geom: dict) -> dict:
    """Project a GeoJSON geometry mapping.

    Supports Polygon, MultiPolygon, LineString, MultiLineString, Point and
    MultiPoint. Geometry collections are intentionally not handled yet.
    """
    gtype = geom.get("type")
    coords = geom.get("coordinates")

    if gtype == "Point":
        x, y = lonlat_to_un_azimuthal(coords[0], coords[1])
        return {"type": "Point", "coordinates": [x, y]}
    if gtype == "MultiPoint":
        return {"type": "MultiPoint", "coordinates": [[*lonlat_to_un_azimuthal(lon, lat)] for lon, lat in coords]}
    if gtype == "LineString":
        return {"type": "LineString", "coordinates": project_ring(coords)}
    if gtype == "MultiLineString":
        return {"type": "MultiLineString", "coordinates": [project_ring(line) for line in coords]}
    if gtype == "Polygon":
        return {"type": "Polygon", "coordinates": [project_ring(ring) for ring in coords]}
    if gtype == "MultiPolygon":
        return {"type": "MultiPolygon", "coordinates": [[project_ring(ring) for ring in poly] for poly in coords]}

    raise ValueError(f"Unsupported geometry type for global projection: {gtype}")
