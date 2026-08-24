from __future__ import annotations

import hashlib
import math
from typing import Any, Dict, Mapping, MutableMapping, Sequence

import numpy as np


MEASUREMENT_MODEL_VERSION = "atolia-instrument-measurement-v1"


def _seed64(*parts: Any) -> int:
    raw = "|".join(str(x) for x in parts)
    return int.from_bytes(hashlib.sha256(raw.encode("utf-8")).digest()[:8], "big")


def _rng(seed: int, artifact_id: str, tool: str, preparation: str) -> np.random.Generator:
    return np.random.default_rng(_seed64(seed, artifact_id, tool, preparation))


def _normal_value(rng: np.random.Generator, true: float, sigma: float, lower: float | None = None) -> float:
    value = float(rng.normal(float(true), float(sigma)))
    return max(lower, value) if lower is not None else value


def _interval(value: float, sigma: float, digits: int = 4) -> Dict[str, float]:
    return {
        "value": round(float(value), digits),
        "sigma_1s": round(float(sigma), digits),
        "ci95_low": round(float(value - 1.96 * sigma), digits),
        "ci95_high": round(float(value + 1.96 * sigma), digits),
    }


def measure_xrf(truth: Mapping[str, Any], rng: np.random.Generator, preparation: str = "surface") -> Dict[str, Any]:
    material = truth["material"]
    corrosion = truth["corrosion"]
    if preparation in {"surface", "untreated_surface"}:
        composition = dict(corrosion["surface_apparent_wt_pct"])
        systematic = .035 + .12 * float(corrosion["surface_coverage_fraction"])
        note = "Surface-sensitive composition; corrosion/encrustation bias is part of the forward model."
    elif preparation in {"cleaned_surface", "abraded_window"}:
        bulk = material["bulk_alloy_wt_pct"]
        surface = corrosion["surface_apparent_wt_pct"]
        composition = {k: .82 * float(bulk.get(k, 0.0)) + .18 * float(surface.get(k, 0.0)) for k in set(bulk) | set(surface)}
        systematic = .018 + .035 * float(corrosion["surface_coverage_fraction"])
        note = "Cleaned/abraded window; residual corrosion bias remains."
    else:
        composition = dict(material["bulk_alloy_wt_pct"])
        systematic = .012
        note = "Prepared core/bulk proxy; substantially reduced surface-corrosion bias."
    out = {}
    for element, true in composition.items():
        true = float(true)
        detection = .015 if element in {"Cu", "Sn", "Pb", "As", "Fe", "Zn"} else .05
        sigma = max(detection / 2.0, abs(true) * systematic)
        value = _normal_value(rng, true, sigma, 0.0)
        out[element + "_wt_pct"] = _interval(value, sigma, 4)
    for key, true in material.get("trace_ppm", {}).items():
        sigma = max(2.0, float(true) * (.055 if preparation == "surface" else .035))
        out[key] = _interval(_normal_value(rng, float(true), sigma, 0.0), sigma, 2)
    return {"tool": "xrf", "preparation": preparation, "measurements": out, "note": note}


def measure_lead_isotopes(truth: Mapping[str, Any], rng: np.random.Generator, preparation: str = "microdrill") -> Dict[str, Any]:
    true_iso = truth["material"]["lead_isotopes"]
    sigma = .0018 if preparation in {"microdrill", "clean_core"} else .0038
    measurements = {}
    for key, true in true_iso.items():
        measurements[key] = _interval(_normal_value(rng, float(true), sigma), sigma, 5)
    return {
        "tool": "lead_isotopes",
        "preparation": preparation,
        "measurements": measurements,
        "note": "Analytical uncertainty is explicit; mixed/recycled source provenance remains a model ambiguity, not measurement noise."
    }


def measure_xrd(truth: Mapping[str, Any], rng: np.random.Generator, preparation: str = "corrosion_powder") -> Dict[str, Any]:
    phase = truth["corrosion"]["phase_fraction"]
    keys = list(phase)
    alpha = np.asarray([max(.02, float(phase[k]) * 180.0) for k in keys])
    draw = rng.dirichlet(alpha)
    measurements = {}
    for k, v, t in zip(keys, draw, [phase[k] for k in keys]):
        sigma = max(.008, math.sqrt(max(1e-6, float(t) * (1 - float(t))) / 180.0))
        measurements[k] = _interval(float(v), sigma, 4)
    return {
        "tool": "xrd",
        "preparation": preparation,
        "measurements": measurements,
        "note": "Phase fractions describe sampled corrosion mineralogy, not bulk metal composition."
    }


def measure_ct(truth: Mapping[str, Any], rng: np.random.Generator, preparation: str = "whole_object") -> Dict[str, Any]:
    ident = truth["identity"]; micro = truth["manufacture"]["microstructure"]; corr = truth["corrosion"]
    dims = ident["dimensions"]
    out = {}
    for key in ("length_mm", "width_mm", "thickness_mm"):
        true = float(dims[key]); sigma = max(.08, true * .0035)
        out[key] = _interval(_normal_value(rng, true, sigma, .01), sigma, 3)
    por = float(micro["porosity_fraction"]); sigma_p = max(.002, .10 * por)
    out["internal_porosity_fraction"] = _interval(_normal_value(rng, por, sigma_p, 0.0), sigma_p, 5)
    crack = float(corr["crack_fraction"]); sigma_c = max(.004, .12 * crack)
    out["crack_fraction"] = _interval(_normal_value(rng, crack, sigma_c, 0.0), sigma_c, 5)
    return {"tool": "ct", "preparation": preparation, "measurements": out,
            "note": "Geometry/void/crack observations; no direct provenance inference is emitted."}


def measure_metallography(truth: Mapping[str, Any], rng: np.random.Generator, preparation: str = "polished_section") -> Dict[str, Any]:
    micro = truth["manufacture"]["microstructure"]
    specs = {
        "grain_size_um": (.08, 2.0),
        "dendrite_arm_spacing_um": (.10, 2.5),
        "porosity_fraction": (.12, .002),
        "cold_work_fraction": (.08, .015),
        "recrystallized_fraction": (.08, .015),
    }
    out = {}
    for key, (rel, floor) in specs.items():
        true = float(micro[key]); sigma = max(floor, abs(true) * rel)
        out[key] = _interval(_normal_value(rng, true, sigma, 0.0), sigma, 4 if "fraction" in key else 2)
    return {"tool": "metallography", "preparation": preparation, "measurements": out,
            "note": "Destructive section measurement of manufacturing microstructure."}


def measure_hardness(truth: Mapping[str, Any], rng: np.random.Generator, preparation: str = "polished_spot") -> Dict[str, Any]:
    true = float(truth["manufacture"]["microstructure"]["hardness_hv"])
    sigma = max(3.5, .045 * true)
    return {"tool": "hardness", "preparation": preparation,
            "measurements": {"HV": _interval(_normal_value(rng, true, sigma, 0), sigma, 1)},
            "note": "Local hardness; spatial heterogeneity is represented in the uncertainty."}


def measure_morphometrics(truth: Mapping[str, Any], rng: np.random.Generator, preparation: str = "whole_object") -> Dict[str, Any]:
    dims = truth["identity"]["dimensions"]
    corr = truth["corrosion"]
    loss = float(corr["metal_loss_fraction"])
    out = {}
    for key in ("length_mm", "width_mm", "thickness_mm"):
        true = float(dims[key]) * (1.0 - (.04 if key != "thickness_mm" else .12) * loss)
        sigma = max(.25, true * .006)
        out[key] = _interval(_normal_value(rng, true, sigma, .01), sigma, 2)
    return {"tool": "morphometrics", "preparation": preparation, "measurements": out,
            "note": "Present-object dimensions; corrosion/material loss can shift them from manufacture dimensions."}


def measure_visual(truth: Mapping[str, Any], rng: np.random.Generator, preparation: str = "as_found") -> Dict[str, Any]:
    corr = truth["corrosion"]
    phases = corr["phase_fraction"]
    green = float(phases.get("malachite", 0) + phases.get("atacamite_paratacamite", 0))
    dark = float(phases.get("cuprite", 0) + phases.get("tenorite", 0))
    return {
        "tool": "visual",
        "preparation": preparation,
        "measurements": {
            "surface_coverage_fraction": _interval(_normal_value(rng, float(corr["surface_coverage_fraction"]), .035, 0), .035, 3),
            "green_corrosion_index": _interval(_normal_value(rng, green, .06, 0), .06, 3),
            "dark_red_black_corrosion_index": _interval(_normal_value(rng, dark, .06, 0), .06, 3),
            "integrity_fraction": _interval(_normal_value(rng, float(corr["integrity_fraction"]), .04, 0), .04, 3),
        },
        "note": "Macroscopic condition observation; phase identity requires XRD or microscopy."
    }


def measure_corrosion_microscopy(truth: Mapping[str, Any], rng: np.random.Generator, preparation: str = "cross_section") -> Dict[str, Any]:
    corr = truth["corrosion"]
    out = {}
    specs = {
        "mean_layer_thickness_um": (.11, 12.0),
        "pit_depth_um_p50": (.14, 10.0),
        "pit_depth_um_p95": (.16, 18.0),
        "crack_fraction": (.12, .012),
    }
    for key, (rel, floor) in specs.items():
        true = float(corr[key]); sigma = max(floor, abs(true) * rel)
        out[key] = _interval(_normal_value(rng, true, sigma, 0.0), sigma, 4 if "fraction" in key else 1)
    return {"tool": "microscopy", "preparation": preparation, "measurements": out,
            "note": "Local cross-section corrosion morphology; sampling location creates irreducible spatial variation."}


TOOL_FUNCS = {
    "xrf": measure_xrf,
    "surface_xrf": measure_xrf,
    "lead_isotopes": measure_lead_isotopes,
    "isotopes": measure_lead_isotopes,
    "xrd": measure_xrd,
    "ct": measure_ct,
    "metallography": measure_metallography,
    "hardness": measure_hardness,
    "morphometrics": measure_morphometrics,
    "visual": measure_visual,
    "microscopy": measure_corrosion_microscopy,
}

DEFAULT_PREPARATION = {
    "xrf": "surface", "surface_xrf": "surface", "lead_isotopes": "microdrill", "isotopes": "microdrill",
    "xrd": "corrosion_powder", "ct": "whole_object", "metallography": "polished_section",
    "hardness": "polished_spot", "morphometrics": "whole_object", "visual": "as_found",
    "microscopy": "cross_section",
}


def measure_tool(artifact_truth: Mapping[str, Any], tool: str, measurement_seed: int,
                 preparation: str | None = None) -> Dict[str, Any]:
    tool = str(tool)
    if tool not in TOOL_FUNCS:
        return {"tool": tool, "available": False, "reason": "No physical forward model registered for this tool."}
    prep = preparation or DEFAULT_PREPARATION[tool]
    artifact_id = str(artifact_truth.get("artifact_id", "unknown"))
    rng = _rng(measurement_seed, artifact_id, tool, prep)
    payload = TOOL_FUNCS[tool](artifact_truth, rng, prep)
    payload["available"] = True
    payload["measurement_model_version"] = MEASUREMENT_MODEL_VERSION
    payload["artifact_id"] = artifact_id
    return payload


def measure_tools(artifact_truth: Mapping[str, Any], tools: Sequence[str], measurement_seed: int) -> Dict[str, Any]:
    return {tool: measure_tool(artifact_truth, tool, measurement_seed) for tool in tools}
