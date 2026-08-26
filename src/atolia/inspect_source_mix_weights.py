#!/usr/bin/env python3
from __future__ import annotations

"""Inspect source-mixture semantics in an existing ECMWF runtime.

Read-only diagnostic.  It never rewrites NetCDF, never reads the giant JSON,
and never reruns the latent world.

Questions answered:
  * What do per-cell source-weight sums actually look like?
  * How many cells are near 1.0, below 1.0, above 1.0, or zero?
  * Do sums correlate with production intensity, circulation seed, recycle mean,
    date, source count, or object class?
  * Are normalized source fractions internally well-behaved even when raw sums
    are not one?
  * Which cells are the most extreme examples?

The output is intentionally JSON so it can be pasted back into the discussion
without screenshots or ad-hoc PowerShell parsing.
"""

import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
from netCDF4 import Dataset

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import ecmwf_acquisition_campaign as ecmwf


QUANTILES = (0.0, 0.001, 0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99, 0.999, 1.0)


def _names(var: Any) -> list[str]:
    out: list[str] = []
    for value in var[:]:
        if isinstance(value, bytes):
            out.append(value.decode("utf-8"))
        else:
            out.append(str(value))
    return out


def _quantiles(x: np.ndarray) -> dict[str, float]:
    if x.size == 0:
        return {}
    values = np.quantile(x, QUANTILES)
    return {f"q{100*q:g}": float(v) for q, v in zip(QUANTILES, values)}


def _safe_corr(a: np.ndarray, b: np.ndarray) -> float | None:
    mask = np.isfinite(a) & np.isfinite(b)
    if int(mask.sum()) < 3:
        return None
    aa = a[mask]
    bb = b[mask]
    if float(np.std(aa)) <= 0.0 or float(np.std(bb)) <= 0.0:
        return None
    return float(np.corrcoef(aa, bb)[0, 1])


def _class_summary(class_ids: np.ndarray, class_names: list[str], sums: np.ndarray) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for cid, name in enumerate(class_names):
        mask = class_ids == cid
        if not np.any(mask):
            continue
        x = sums[mask]
        out[name] = {
            "cells": int(x.size),
            "mean": float(np.mean(x)),
            "median": float(np.median(x)),
            "q05": float(np.quantile(x, .05)),
            "q95": float(np.quantile(x, .95)),
            "near_one": int(np.count_nonzero(np.isclose(x, 1.0, rtol=0.0, atol=1e-10))),
        }
    return out


def _extreme_rows(
    ids: np.ndarray,
    sums: np.ndarray,
    counts: np.ndarray,
    production: np.ndarray,
    seed: np.ndarray,
    recycle: np.ndarray,
    dates: np.ndarray,
    classes: np.ndarray,
    class_names: list[str],
    source_ptr: np.ndarray,
    source_ids: np.ndarray,
    source_weights: np.ndarray,
    source_names: list[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for cid in ids:
        a, z = int(source_ptr[cid]), int(source_ptr[cid + 1])
        weights = source_weights[a:z]
        sids = source_ids[a:z]
        total = float(sums[cid])
        normalized = weights / total if total > 0 else weights
        rows.append({
            "cell_id": int(cid),
            "object_class": class_names[int(classes[cid])],
            "date_bc": int(dates[cid]),
            "raw_source_sum": total,
            "source_count": int(counts[cid]),
            "production_intensity": float(production[cid]),
            "circulation_seed_intensity": float(seed[cid]),
            "recycle_mean": float(recycle[cid]),
            "sources": [
                {
                    "source": source_names[int(sid)],
                    "raw_weight": float(w),
                    "normalized_fraction": float(nw) if total > 0 else None,
                }
                for sid, w, nw in zip(sids, weights, normalized)
            ],
        })
    return rows


def inspect(runtime_path: Path, extremes: int = 8) -> dict[str, Any]:
    runtime_path = Path(runtime_path)
    if not runtime_path.exists():
        raise FileNotFoundError(runtime_path)

    with Dataset(runtime_path, "r") as ds:
        schema = str(getattr(ds, "schema", ""))
        if schema != ecmwf.RUNTIME_SCHEMA:
            raise ValueError(f"not an Atolia ECMWF runtime: schema={schema!r}")

        source_ptr = np.asarray(ds.variables["cell_source_ptr"][:], dtype=np.int64)
        source_ids = np.asarray(ds.variables["cell_source_id"][:], dtype=np.int64)
        source_weights = np.asarray(ds.variables["cell_source_weight"][:], dtype=np.float64)
        production = np.asarray(ds.variables["cell_production_intensity"][:], dtype=np.float64)
        seed = np.asarray(ds.variables["cell_circulation_seed_intensity"][:], dtype=np.float64)
        recycle = np.asarray(ds.variables["cell_recycle_mean"][:], dtype=np.float64)
        dates = np.asarray(ds.variables["cell_date_bc"][:], dtype=np.float64)
        classes = np.asarray(ds.variables["cell_object_class"][:], dtype=np.int64)
        class_names = _names(ds.variables["object_class_name"])
        source_names = _names(ds.variables["source_name"])

        cell_count = production.size
        if source_ptr.size != cell_count + 1:
            raise ValueError(f"cell_source_ptr length {source_ptr.size} != cell_count+1 {cell_count+1}")
        if int(source_ptr[-1]) != source_weights.size or source_ids.size != source_weights.size:
            raise ValueError("source CSR terminal/count mismatch")

        counts = np.diff(source_ptr).astype(np.int64)
        sums = np.add.reduceat(source_weights, source_ptr[:-1]) if source_weights.size else np.zeros(cell_count)
        # reduceat is wrong for empty CSR rows because it samples the next entry.
        # Correct those explicitly and handle a possible terminal empty row.
        sums = np.asarray(sums, dtype=np.float64)
        sums[counts == 0] = 0.0

        finite = np.isfinite(sums)
        positive = sums > 0.0
        near_one = np.isclose(sums, 1.0, rtol=0.0, atol=1e-10)

        raw_entropy = np.zeros(cell_count, dtype=np.float64)
        normalized_entropy = np.zeros(cell_count, dtype=np.float64)
        max_fraction = np.zeros(cell_count, dtype=np.float64)
        for cid in range(cell_count):
            a, z = int(source_ptr[cid]), int(source_ptr[cid + 1])
            w = source_weights[a:z]
            if w.size == 0:
                continue
            safe = w[w > 0.0]
            raw_entropy[cid] = float(-np.sum(safe * np.log(safe))) if safe.size else 0.0
            total = float(sums[cid])
            if total > 0.0:
                p = w / total
                psafe = p[p > 0.0]
                normalized_entropy[cid] = float(-np.sum(psafe * np.log(psafe))) if psafe.size else 0.0
                max_fraction[cid] = float(np.max(p))

        ratios: dict[str, dict[str, float]] = {}
        for name, x in {
            "sum_over_production": sums / np.maximum(production, 1e-300),
            "sum_over_circulation_seed": sums / np.maximum(seed, 1e-300),
            "production_over_sum": production / np.maximum(sums, 1e-300),
            "circulation_seed_over_sum": seed / np.maximum(sums, 1e-300),
        }.items():
            valid = np.isfinite(x) & positive
            ratios[name] = _quantiles(x[valid])

        by_source_count: dict[str, Any] = {}
        for count in sorted(set(int(x) for x in counts)):
            mask = counts == count
            x = sums[mask]
            by_source_count[str(count)] = {
                "cells": int(mask.sum()),
                "mean_sum": float(np.mean(x)),
                "median_sum": float(np.median(x)),
                "near_one": int(np.count_nonzero(np.isclose(x, 1.0, rtol=0.0, atol=1e-10))),
            }

        n = max(1, int(extremes))
        low_ids = np.argsort(sums)[:n]
        high_ids = np.argsort(sums)[-n:][::-1]
        off_ids = np.argsort(np.abs(sums - 1.0))[-n:][::-1]

        report = {
            "schema": "atolia.source-mix-inspection.v1",
            "runtime": str(runtime_path),
            "runtime_schema": schema,
            "production_cells": int(cell_count),
            "source_entries": int(source_weights.size),
            "source_vocabulary": source_names,
            "sum_distribution": {
                "finite": int(finite.sum()),
                "zero": int(np.count_nonzero(sums == 0.0)),
                "positive": int(np.count_nonzero(positive)),
                "below_one": int(np.count_nonzero(sums < 1.0 - 1e-10)),
                "near_one": int(np.count_nonzero(near_one)),
                "above_one": int(np.count_nonzero(sums > 1.0 + 1e-10)),
                "quantiles": _quantiles(sums[finite]),
                "mean": float(np.mean(sums[finite])),
                "std": float(np.std(sums[finite])),
            },
            "source_count_distribution": {
                str(k): int(v) for k, v in sorted(Counter(counts.tolist()).items())
            },
            "correlations": {
                "sum_vs_production_intensity": _safe_corr(sums, production),
                "sum_vs_circulation_seed_intensity": _safe_corr(sums, seed),
                "sum_vs_recycle_mean": _safe_corr(sums, recycle),
                "sum_vs_date_bc": _safe_corr(sums, dates),
                "sum_vs_source_count": _safe_corr(sums, counts.astype(np.float64)),
                "sum_vs_normalized_entropy": _safe_corr(sums, normalized_entropy),
                "sum_vs_max_normalized_fraction": _safe_corr(sums, max_fraction),
            },
            "ratio_distributions_positive_cells": ratios,
            "normalized_composition_diagnostics": {
                "entropy_quantiles": _quantiles(normalized_entropy[positive]),
                "max_fraction_quantiles": _quantiles(max_fraction[positive]),
                "all_positive_raw_weights": bool(np.all(source_weights >= 0.0)),
                "all_finite_raw_weights": bool(np.all(np.isfinite(source_weights))),
            },
            "by_source_count": by_source_count,
            "by_object_class": _class_summary(classes, class_names, sums),
            "extremes": {
                "lowest_sums": _extreme_rows(low_ids, sums, counts, production, seed, recycle, dates, classes, class_names, source_ptr, source_ids, source_weights, source_names),
                "highest_sums": _extreme_rows(high_ids, sums, counts, production, seed, recycle, dates, classes, class_names, source_ptr, source_ids, source_weights, source_names),
                "farthest_from_one": _extreme_rows(off_ids, sums, counts, production, seed, recycle, dates, classes, class_names, source_ptr, source_ids, source_weights, source_names),
            },
            "interpretation_keys": {
                "normalized_fraction": "raw source weight divided by that cell's raw source-weight sum; diagnostic only, file is not modified",
                "what_to_look_for": [
                    "If raw sums cluster at a meaningful non-1 scale or correlate strongly with production/seed intensity, weights are likely intensities or partial contributions.",
                    "If raw sums vary arbitrarily while normalized fractions look sensible and no physical quantity tracks the sum, normalization may have been omitted upstream.",
                    "If source_count explains sum strongly, the writer may be storing per-source scores rather than a mixture simplex.",
                ],
            },
        }
        return report


def main() -> None:
    ap = argparse.ArgumentParser(description="Inspect raw source-mixture weight semantics in the ECMWF runtime.")
    ap.add_argument("--runtime", type=Path, default=ecmwf.DEFAULT_RUNTIME)
    ap.add_argument("--extremes", type=int, default=8)
    args = ap.parse_args()
    print(json.dumps(inspect(args.runtime, args.extremes), indent=2))


if __name__ == "__main__":
    main()
