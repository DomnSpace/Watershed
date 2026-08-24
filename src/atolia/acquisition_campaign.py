from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple

import numpy as np

import archaeological_condensation_v3 as condensation
import artifact_physical_truth as physical_truth
import intensity_circulation as intensity
import instrument_measurement_model as instruments
import physical_poari_sampler as physical_sampler
import provenance_field as base
import provenance_field_mediterranean as med


ACQUISITION_VERSION = "atolia-acquisition-campaign-v1"
DEFAULT_INTENSITY_STEPS = 28
EARLY_TAIL_TARGET = .75


@dataclass(frozen=True)
class CareerRegime:
    name: str
    start: int
    end: int
    p: float
    site_block_min: int
    site_block_max: int
    description: str


REGIMES: Tuple[CareerRegime, ...] = (
    CareerRegime("stray_tail", 1, 50, -1.0, 1, 1, "Accidental/legacy finds; predominantly exceptional circulation tails."),
    CareerRegime("context_followup", 51, 70, -1.0, 2, 4, "Weak contextual follow-up around puzzling early material."),
    CareerRegime("random_hoard", 71, 100, 0.0, 30, 30, "One genuinely random coherent hoard episode."),
    CareerRegime("post_hoard_comparison", 101, 130, 0.0, 3, 5, "Local and museum comparison around the hoard context."),
    CareerRegime("exploratory_dig", 131, 190, 0.0, 5, 8, "High-temperature information-seeking excavation."),
    CareerRegime("discriminating_dig", 191, 250, 1.0, 4, 7, "Digs chosen to distinguish competing circulation explanations."),
    CareerRegime("network_reconstruction", 251, 290, 2.0, 3, 6, "Integrated bridge-site programme across unresolved systems."),
    CareerRegime("falsification_probe", 291, 300, -1.0, 1, 2, "Adversarial weak-link tests chosen to challenge the current reconstruction."),
)


def regime_for_index(index: int) -> CareerRegime:
    for regime in REGIMES:
        if regime.start <= int(index) <= regime.end:
            return regime
    raise ValueError(f"career index outside 1..300: {index}")


def p_measure(values: Mapping[str, float], weights: Mapping[str, float], p: float) -> float:
    """Weighted generalized mean used as the POARI action-coherence operator.

    p=-1 harmonic/weak-link-sensitive, p=0 geometric, p=1 arithmetic,
    p=2 quadratic. Inputs are positive coherence dimensions, not probabilities.
    """
    keys = [k for k in values if k in weights and float(weights[k]) > 0]
    if not keys:
        return 0.0
    x = np.asarray([max(1e-6, float(values[k])) for k in keys], dtype=float)
    w = np.asarray([max(0.0, float(weights[k])) for k in keys], dtype=float)
    w /= w.sum()
    if abs(float(p)) < 1e-12:
        return float(math.exp(float(np.sum(w * np.log(x)))))
    return float(max(0.0, np.sum(w * np.power(x, float(p)))) ** (1.0 / float(p)))


ACTION_WEIGHTS: Dict[str, Dict[str, float]] = {
    "context_followup": {
        "information_gain": .19, "archaeological_yield": .16, "recoverability": .18,
        "novelty": .10, "bridge": .10, "feasibility": .14, "anti_leak": .13,
    },
    "post_hoard_comparison": {
        "information_gain": .21, "archaeological_yield": .17, "recoverability": .15,
        "novelty": .08, "bridge": .15, "feasibility": .13, "anti_leak": .11,
    },
    "exploratory_dig": {
        "information_gain": .24, "archaeological_yield": .16, "recoverability": .12,
        "novelty": .18, "bridge": .13, "feasibility": .10, "anti_leak": .07,
    },
    "discriminating_dig": {
        "information_gain": .28, "archaeological_yield": .13, "recoverability": .12,
        "novelty": .10, "bridge": .22, "feasibility": .08, "anti_leak": .07,
    },
    "network_reconstruction": {
        "information_gain": .22, "archaeological_yield": .10, "recoverability": .11,
        "novelty": .08, "bridge": .31, "feasibility": .08, "anti_leak": .10,
    },
    "falsification_probe": {
        "information_gain": .13, "archaeological_yield": .08, "recoverability": .16,
        "novelty": .11, "bridge": .10, "feasibility": .11, "anti_leak": .10,
        "falsification": .21,
    },
}


@dataclass
class SiteOpportunity:
    node_id: str
    region: str
    kind: str
    lon: float
    lat: float
    strata: List[int] = field(default_factory=list)
    archaeological_intensity: float = 0.0
    loss_intensity: float = 0.0
    class_mass: Counter = field(default_factory=Counter)
    deposition_mass: Counter = field(default_factory=Counter)
    route_km_sum: float = 0.0
    physical_cross_sum: float = 0.0
    field_cross_sum: float = 0.0
    route_km_sq_sum: float = 0.0

    @property
    def weight(self) -> float:
        return max(1e-12, self.archaeological_intensity)

    def class_entropy(self) -> float:
        return _counter_entropy(self.class_mass)

    def deposition_entropy(self) -> float:
        return _counter_entropy(self.deposition_mass)

    def mean_route_km(self) -> float:
        return self.route_km_sum / self.weight

    def mean_physical_crossings(self) -> float:
        return self.physical_cross_sum / self.weight

    def mean_field_crossings(self) -> float:
        return self.field_cross_sum / self.weight

    def route_variability(self) -> float:
        mean = self.mean_route_km()
        var = max(0.0, self.route_km_sq_sum / self.weight - mean * mean)
        return math.sqrt(var)


@dataclass
class ResearchAction:
    action_id: str
    regime: str
    site_node: str
    p: float
    dimensions: Dict[str, float]
    poari_score: float
    temperature: float
    block_size: int
    question: str


def _seed64(*parts: Any) -> int:
    raw = "|".join(str(x) for x in parts)
    return int.from_bytes(hashlib.sha256(raw.encode("utf-8")).digest()[:8], "big")


def _counter_entropy(counter: Mapping[str, float]) -> float:
    arr = np.asarray([float(v) for v in counter.values() if float(v) > 0], dtype=float)
    if len(arr) <= 1:
        return 0.0
    arr /= arr.sum()
    return float(-np.sum(arr * np.log(arr)) / math.log(len(arr)))


def _normalize_map(m: Mapping[str, float]) -> Dict[str, float]:
    out = {str(k): max(0.0, float(v)) for k, v in m.items()}
    total = sum(out.values()) or 1.0
    return {k: v / total for k, v in out.items()}


def _stratum_observation_rate(s: intensity.LossStratum) -> float:
    total = 0.0
    for mode, p_mode in s.deposition_mode_weights.items():
        total += float(p_mode) * condensation.MODE_SURVIVAL.get(mode, .46) * condensation.MODE_DISCOVERY.get(mode, .018) * condensation.MODE_RECORD.get(mode, .44)
    return max(1e-8, float(total))


def _archaeological_intensity(s: intensity.LossStratum) -> float:
    return float(s.loss_intensity * _stratum_observation_rate(s))


def _context_completeness(s: intensity.LossStratum) -> float:
    # Context quality is an acquisition property; it does not inspect source/guild truth.
    values = {
        "grave_assemblage": .92, "workshop_debris": .90, "catastrophic_abandonment": .84,
        "finished_object_hoard": .88, "founder_scrap_hoard": .84, "personal_wealth_deposit": .78,
        "settlement_loss": .58, "selective_ritual_deposit": .55, "river_wetland_deposit": .28,
    }
    return float(sum(float(p) * values.get(mode, .50) for mode, p in s.deposition_mode_weights.items()))


def _is_tail(world: Any, s: intensity.LossStratum) -> bool:
    cell = s.production_cell
    incidence = float(getattr(world, "bundle_incidence", {}).get(cell.bundle_id, 1.0))
    return bool(
        incidence < .50
        or s.route_distance_from_origin_km >= 520.0
        or s.expected_physical_crossings >= .80
        or s.expected_field_crossings >= .12
        or med.REGION_BY_NODE.get(cell.origin, "other") != med.REGION_BY_NODE.get(s.node_id, "other")
    )


def _exceptionality(world: Any, s: intensity.LossStratum) -> float:
    cell = s.production_cell
    incidence = float(getattr(world, "bundle_incidence", {}).get(cell.bundle_id, 1.0))
    return float(np.clip(
        .32 * min(1.0, s.route_distance_from_origin_km / 1400.0)
        + .22 * min(1.0, s.expected_physical_crossings / 2.5)
        + .18 * min(1.0, s.expected_field_crossings / .25)
        + .18 * float(incidence < .5)
        + .10 * (1.0 - _context_completeness(s)),
        0.0, 1.0,
    ))


def _distance_nodes(world: Any, a: str, b: str) -> float:
    na, nb = world.nodes[a], world.nodes[b]
    return float(base.haversine_km(na.lon, na.lat, nb.lon, nb.lat))


def _sample_source_mix(rng: np.random.Generator, base_mix: Mapping[str, float], recycle_count: int) -> Dict[str, float]:
    keys = [str(k) for k, v in base_mix.items() if float(v) > 0]
    if not keys:
        return {"recycled_external_mix": 1.0}
    p = np.asarray([float(base_mix[k]) for k in keys], dtype=float); p /= p.sum()
    concentration = max(4.0, 28.0 / (1.0 + .55 * recycle_count))
    draw = rng.dirichlet(np.maximum(.04, p * concentration))
    out = {k: float(v) for k, v in zip(keys, draw)}
    if recycle_count > 0:
        external = float(np.clip(rng.beta(1.2, 9.0) * min(.30, .055 * recycle_count), 0, .24))
        if external > 0:
            out = {k: v * (1.0 - external) for k, v in out.items()}; out["recycled_external_mix"] = external
    return _normalize_map(out)


class AcquisitionCampaignSampler(physical_sampler.PhysicalArchaeologyPOARICareerSampler):
    """300-object career generated by research actions over latent loss intensities.

    The 30k archaeological catalogue is a separate validation projection and is not
    the candidate pool used here. POARI ranks acquisition actions/sites; only after an
    action is selected is a concrete physical artefact instantiated.
    """

    def __init__(self, *args: Any, intensity_steps: int = DEFAULT_INTENSITY_STEPS, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.intensity_steps = int(intensity_steps)
        self.flow_reports: List[intensity.CellFlowReport] = []
        self.flow_summary: Dict[str, Any] = {}
        self.loss_strata: List[intensity.LossStratum] = []
        self.sites: Dict[str, SiteOpportunity] = {}
        self.acquisition_by_object: Dict[str, Dict[str, Any]] = {}
        self.research_actions: List[ResearchAction] = []
        self._known_site_counts: Counter = Counter()
        self._known_region_counts: Counter = Counter()
        self._known_class_counts: Counter = Counter()
        self._active_action: ResearchAction | None = None
        self._active_action_remaining = 0
        self._active_regime: str | None = None
        self._hoard: Dict[str, Any] | None = None
        self._hoard_class_counts: Counter = Counter()
        self._observed_numeric_signatures: List[Dict[str, float]] = []
        self._prepared = False

    def prepare_candidates(self) -> None:
        # Intentionally overrides the old "30k catalogue -> candidate list" path.
        if not getattr(self.world, "workshops", None) or not getattr(self.world, "sources", None):
            raise RuntimeError("Acquisition campaign requires a fully built world with real workshops and sources")
        self.flow_reports, self.flow_summary = intensity.propagate_world(self.world, max_steps=self.intensity_steps)
        self.loss_strata = [s for r in self.flow_reports for s in r.loss_strata if s.loss_intensity > 0]
        if not self.loss_strata:
            raise RuntimeError("Intensity world produced no loss strata")
        self.sites = self._build_sites()
        self._prepared = True

    def _build_sites(self) -> Dict[str, SiteOpportunity]:
        sites: Dict[str, SiteOpportunity] = {}
        for idx, s in enumerate(self.loss_strata):
            node = self.world.nodes[s.node_id]
            site = sites.setdefault(s.node_id, SiteOpportunity(
                node_id=s.node_id, region=med.REGION_BY_NODE.get(s.node_id, "other"),
                kind=str(node.kind), lon=float(node.lon), lat=float(node.lat),
            ))
            arch = _archaeological_intensity(s)
            site.strata.append(idx); site.archaeological_intensity += arch; site.loss_intensity += float(s.loss_intensity)
            site.class_mass[s.production_cell.object_class] += arch
            for mode, p in s.deposition_mode_weights.items():
                site.deposition_mass[mode] += arch * float(p)
            site.route_km_sum += arch * float(s.route_distance_from_origin_km)
            site.route_km_sq_sum += arch * float(s.route_distance_from_origin_km) ** 2
            site.physical_cross_sum += arch * float(s.expected_physical_crossings)
            site.field_cross_sum += arch * float(s.expected_field_crossings)
        return sites

    def sample(self) -> List[Dict[str, Any]]:
        if not self._prepared:
            self.prepare_candidates()
        for career_no, slot in enumerate(self.slots, start=1):
            regime = regime_for_index(career_no)
            candidate, acquisition = self._acquire_one(career_no, slot, regime)
            self.candidates.append(candidate)
            self._candidate_by_id[candidate.object_id] = candidate
            self.selected.append(candidate); self.selected_by_slot[slot.index] = candidate
            self.acquisition_by_object[candidate.object_id] = acquisition
            self._register(candidate); self._update_recurrence_anchor(slot, candidate)
            self._update_evidence_state(slot, candidate)
        return [self._project_player_object(slot, self.selected_by_slot[slot.index]) for slot in self.slots]

    def _acquire_one(self, career_no: int, slot: Any, regime: CareerRegime) -> Tuple[Any, Dict[str, Any]]:
        if regime.name == "stray_tail":
            s, action = self._sample_stray(career_no)
            return self._candidate_from_stratum(s, career_no, slot, action)
        if regime.name == "random_hoard":
            return self._acquire_hoard_object(career_no, slot)

        if self._active_regime != regime.name or self._active_action_remaining <= 0 or self._active_action is None:
            self._active_action = self._choose_research_action(career_no, regime)
            self._active_regime = regime.name
            self._active_action_remaining = self._active_action.block_size
            self.research_actions.append(self._active_action)
        action = self._active_action
        self._active_action_remaining -= 1
        s = self._sample_stratum_at_site(action.site_node, regime.name)
        return self._candidate_from_stratum(s, career_no, slot, action)

    def _sample_stray(self, career_no: int) -> Tuple[intensity.LossStratum, ResearchAction]:
        want_tail = bool(self.rng.random() < EARLY_TAIL_TARGET)
        pool = [s for s in self.loss_strata if _is_tail(self.world, s) == want_tail]
        if not pool:
            pool = list(self.loss_strata)
        weights = []
        dims_by_id: Dict[int, Dict[str, float]] = {}
        for s in pool:
            arch = _archaeological_intensity(s)
            exception = _exceptionality(self.world, s)
            dims = {
                "archaeological_yield": float(np.clip(.15 + .85 * math.log1p(arch) / 12.0, .05, 1.0)),
                "recoverability": float(np.clip(_stratum_observation_rate(s) / .03, .05, 1.0)),
                "novelty": float(np.clip(.20 + .80 * exception, .05, 1.0)),
                "anti_leak": float(np.clip(1.08 - _context_completeness(s), .05, 1.0)),
                "exceptional_loss": float(np.clip(.12 + .88 * exception, .05, 1.0)),
            }
            poari = p_measure(dims, {"archaeological_yield": .14, "recoverability": .15, "novelty": .22, "anti_leak": .19, "exceptional_loss": .30}, -1.0)
            kernel = math.sqrt(max(1e-12, arch)) * (0.18 + poari) ** 2
            if want_tail and _is_tail(self.world, s):
                kernel *= 3.0
            if (not want_tail) and (not _is_tail(self.world, s)):
                kernel *= 1.8
            weights.append(kernel); dims_by_id[id(s)] = dims
        p = np.asarray(weights, dtype=float); p /= p.sum()
        s = pool[int(self.rng.choice(len(pool), p=p))]
        dims = dims_by_id[id(s)]
        action = ResearchAction(
            action_id=f"A-{career_no:03d}", regime="stray_tail", site_node=s.node_id, p=-1.0,
            dimensions=dims, poari_score=p_measure(dims, {"archaeological_yield": .14, "recoverability": .15, "novelty": .22, "anti_leak": .19, "exceptional_loss": .30}, -1.0),
            temperature=.80, block_size=1, question="What kind of world could have put this poorly contextualized object here?",
        )
        self.research_actions.append(action)
        return s, action

    def _choose_hoard(self, career_no: int) -> None:
        hoard_modes = {"founder_scrap_hoard", "finished_object_hoard", "personal_wealth_deposit", "selective_ritual_deposit"}
        pool: List[intensity.LossStratum] = []
        weights = []
        for s in self.loss_strata:
            p_hoard = sum(float(s.deposition_mode_weights.get(m, 0.0)) for m in hoard_modes)
            if p_hoard <= .02:
                continue
            lam = max(1e-12, float(s.loss_intensity) * p_hoard * _stratum_observation_rate(s))
            pool.append(s); weights.append(lam ** .70)
        if not pool:
            pool = list(self.loss_strata); weights = [max(1e-12, _archaeological_intensity(s)) ** .70 for s in pool]
        p = np.asarray(weights, dtype=float); p /= p.sum()
        anchor = pool[int(self.rng.choice(len(pool), p=p))]
        event_bc = max(950, int(anchor.production_cell.date_bc - self.rng.integers(45, 125)))
        node = self.world.nodes[anchor.node_id]
        discovery_year = int(np.clip(round(self.rng.normal(1972, 32)), 1870, 2025))
        hoard_id = f"H-CAM-{_seed64(self.seeds.career_seed, anchor.node_id, event_bc) % 100000:05d}"
        site_id = f"SITE-H-{_seed64(anchor.node_id, hoard_id) % 100000:05d}"
        self._hoard = {
            "hoard_id": hoard_id, "node_id": anchor.node_id, "region": med.REGION_BY_NODE.get(anchor.node_id, "other"),
            "event_bc": event_bc, "discovery_year_ce": discovery_year, "site_id": site_id,
            "lon": float(node.lon + self.rng.normal(0, .0025)), "lat": float(node.lat + self.rng.normal(0, .0018)),
            "anchor_bundle_family": anchor.production_cell.bundle_family,
        }
        self._hoard_class_counts.clear()
        self.research_actions.append(ResearchAction(
            action_id=f"A-{career_no:03d}-HOARD", regime="random_hoard", site_node=anchor.node_id, p=0.0,
            dimensions={"random_archaeological_draw": 1.0}, poari_score=1.0, temperature=1.0, block_size=30,
            question="What structure, if any, recurs inside one context that was not chosen for explanatory value?",
        ))

    def _acquire_hoard_object(self, career_no: int, slot: Any) -> Tuple[Any, Dict[str, Any]]:
        if self._hoard is None:
            self._choose_hoard(career_no)
        assert self._hoard is not None
        event_bc = int(self._hoard["event_bc"]); node_id = str(self._hoard["node_id"])
        site = self.sites.get(node_id)
        pool = [self.loss_strata[i] for i in site.strata] if site else []
        pool = [s for s in pool if event_bc <= s.production_cell.date_bc <= event_bc + 260]
        if not pool:
            # Keep the hoard spatially coherent; intensity strata can represent many
            # objects, so repeated draws from one stratum are legitimate.
            pool = [s for s in self.loss_strata if s.node_id == node_id] or list(self.loss_strata)
        weights = []
        for s in pool:
            cls = s.production_cell.object_class
            diversity = 1.0 / (1.0 + .55 * self._hoard_class_counts[cls])
            hoard_p = sum(float(s.deposition_mode_weights.get(m, 0.0)) for m in ("founder_scrap_hoard", "finished_object_hoard", "personal_wealth_deposit", "selective_ritual_deposit"))
            weights.append(max(1e-10, _archaeological_intensity(s)) ** .58 * (0.20 + hoard_p) * diversity)
        p = np.asarray(weights, dtype=float); p /= p.sum(); s = pool[int(self.rng.choice(len(pool), p=p))]
        self._hoard_class_counts[s.production_cell.object_class] += 1
        action = self.research_actions[-1]
        return self._candidate_from_stratum(s, career_no, slot, action, hoard=self._hoard)

    def _choose_research_action(self, career_no: int, regime: CareerRegime) -> ResearchAction:
        candidates = list(self.sites.values())
        if regime.name == "context_followup" and self._known_site_counts:
            recent = [n for n, _ in self._known_site_counts.most_common(12)]
            nearby = [s for s in candidates if min(_distance_nodes(self.world, s.node_id, n) for n in recent) <= 360.0]
            if nearby:
                candidates = nearby
        elif regime.name == "post_hoard_comparison" and self._hoard:
            hnode = str(self._hoard["node_id"])
            nearby = [s for s in candidates if s.node_id != hnode and _distance_nodes(self.world, s.node_id, hnode) <= 520.0]
            if nearby:
                candidates = nearby

        rows: List[Tuple[SiteOpportunity, Dict[str, float], float]] = []
        for site in candidates:
            dims = self._site_dimensions(site, regime.name)
            score = p_measure(dims, ACTION_WEIGHTS[regime.name], regime.p)
            rows.append((site, dims, score))
        temperature = {
            "context_followup": .34, "post_hoard_comparison": .30, "exploratory_dig": .38,
            "discriminating_dig": .22, "network_reconstruction": .14, "falsification_probe": .18,
        }[regime.name]
        scores = np.asarray([r[2] for r in rows], dtype=float)
        # Soft POARI choice: strategic, but never an omniscient argmax.
        logits = (scores - scores.max()) / max(.03, temperature)
        probs = np.exp(np.clip(logits, -40, 20))
        # Mild survey/yield prior prevents a theoretically interesting zero-yield point
        # from becoming the automatic answer.
        probs *= np.asarray([max(1e-12, r[0].archaeological_intensity) ** .06 for r in rows])
        probs /= probs.sum()
        site, dims, score = rows[int(self.rng.choice(len(rows), p=probs))]
        block = int(self.rng.integers(regime.site_block_min, regime.site_block_max + 1))
        block = min(block, regime.end - career_no + 1)
        return ResearchAction(
            action_id=f"A-{career_no:03d}", regime=regime.name, site_node=site.node_id, p=regime.p,
            dimensions=dims, poari_score=score, temperature=temperature, block_size=block,
            question=self._research_question(site, regime.name),
        )

    def _site_dimensions(self, site: SiteOpportunity, regime_name: str) -> Dict[str, float]:
        known_total = max(1, sum(self._known_site_counts.values()))
        region_seen = self._known_region_counts[site.region]
        region_novel = 1.0 / (1.0 + .35 * region_seen)
        if self._known_site_counts:
            nearest = min(_distance_nodes(self.world, site.node_id, n) for n in self._known_site_counts)
            geographic_novel = float(np.clip(nearest / 900.0, 0, 1))
        else:
            geographic_novel = .7
        class_entropy = site.class_entropy(); dep_entropy = site.deposition_entropy()
        route_var = float(np.clip(site.route_variability() / 800.0, 0, 1))
        bridge = float(np.clip(.18 + .35 * min(1, site.mean_physical_crossings() / 1.7) + .27 * min(1, site.mean_field_crossings() / .18) + .20 * min(1, site.mean_route_km() / 1100.0), .05, 1))
        info = float(np.clip(.16 + .36 * class_entropy + .20 * dep_entropy + .16 * route_var + .12 * region_novel, .05, 1))
        recover = float(np.clip(.10 + .90 * math.sqrt(min(.05, site.archaeological_intensity / max(1e-9, site.loss_intensity))) / math.sqrt(.05), .05, 1))
        log_y = math.log1p(site.archaeological_intensity)
        yield_score = float(np.clip(.10 + .90 * log_y / 14.0, .05, 1))
        feasibility = {"river": .72, "coast": .68, "pass": .50, "hub": .84, "source": .70}.get(site.kind, .78)
        novelty = float(np.clip(.46 * region_novel + .54 * geographic_novel, .05, 1))
        # Anti-leak is deliberately based on observable acquisition diversity only;
        # no source, workshop or guild identity is inspected here.
        max_class = max(site.class_mass.values(), default=0.0) / site.weight
        anti_leak = float(np.clip(1.02 - .42 * max_class - .10 * self._known_site_counts[site.node_id], .05, 1))
        dims = {
            "information_gain": info, "archaeological_yield": yield_score, "recoverability": recover,
            "novelty": novelty, "bridge": bridge, "feasibility": feasibility, "anti_leak": anti_leak,
        }
        if regime_name == "falsification_probe":
            current_region_share = self._known_region_counts[site.region] / known_total
            class_overlap = sum(
                (site.class_mass[k] / site.weight) * (self._known_class_counts[k] / max(1, sum(self._known_class_counts.values())))
                for k in site.class_mass
            )
            dims["falsification"] = float(np.clip(.30 + .34 * (1 - current_region_share) + .24 * (1 - class_overlap) + .12 * bridge, .05, 1))
        return dims

    def _research_question(self, site: SiteOpportunity, regime: str) -> str:
        if regime == "context_followup":
            return f"Does contextual material around {site.region} make the early stray pattern more ordinary or more anomalous?"
        if regime == "post_hoard_comparison":
            return f"Does nearby material reproduce the hoard's measurable techniques outside its closed context?"
        if regime == "exploratory_dig":
            return f"What independent structure appears if we excavate a high-information site in {site.region}?"
        if regime == "discriminating_dig":
            return f"Can material from {site.region} distinguish local manufacture from transferred objects?"
        if regime == "network_reconstruction":
            return f"Does this bridge site connect previously separate measurable recurrences without assuming a common source?"
        return f"If the current reconstruction is wrong, is {site.region} a place where it should fail?"

    def _sample_stratum_at_site(self, node_id: str, regime_name: str) -> intensity.LossStratum:
        site = self.sites[node_id]
        pool = [self.loss_strata[i] for i in site.strata]
        weights = []
        local_class = Counter()
        if self._active_action:
            action_objects = [oid for oid, meta in self.acquisition_by_object.items() if meta.get("action_id") == self._active_action.action_id]
            for oid in action_objects:
                c = self._candidate_by_id.get(oid)
                if c:
                    local_class[c.object_class] += 1
        for s in pool:
            w = max(1e-12, _archaeological_intensity(s)) ** .62
            w *= 1.0 / (1.0 + .42 * local_class[s.production_cell.object_class])
            if regime_name in {"discriminating_dig", "network_reconstruction"}:
                w *= 1.0 + .35 * min(1.0, s.expected_physical_crossings) + .30 * min(1.0, s.expected_field_crossings / .18)
            elif regime_name == "falsification_probe":
                w *= 1.0 + .50 * float(not _is_tail(self.world, s)) + .35 * (1.0 - _context_completeness(s))
            weights.append(w)
        p = np.asarray(weights, dtype=float); p /= p.sum()
        return pool[int(self.rng.choice(len(pool), p=p))]

    def _candidate_from_stratum(self, s: intensity.LossStratum, career_no: int, slot: Any, action: ResearchAction,
                                hoard: Mapping[str, Any] | None = None) -> Tuple[Any, Dict[str, Any]]:
        cell = s.production_cell
        object_id = f"CAR-{career_no:06d}"
        rng = np.random.default_rng(_seed64(self.seeds.archaeology_seed, "campaign_object", career_no, cell.bundle_id, s.node_id))
        recycle_count = max(0, int(rng.poisson(max(0.0, s.expected_recycle_count))))
        repair_count = max(0, int(rng.poisson(max(0.0, s.expected_repair_count + .16 * recycle_count))))
        source_mix = _sample_source_mix(rng, cell.source_mix, recycle_count)
        route = physical_truth.shortest_physical_path(self.world, cell.origin, s.node_id)
        artifact = physical_truth.build_artifact_truth(
            self.world, artifact_id=object_id, object_class=cell.object_class,
            production_bc=int(cell.date_bc), source_mix=source_mix, recycle_count=recycle_count,
            repair_count=repair_count, production_node=cell.origin, loss_node=s.node_id,
            deposition_mode=self._sample_deposition_mode(s, rng), route_nodes=route,
            workshop_id=None, mass_kg=None, seed=self.seeds.archaeology_seed,
        )
        hoard_id = None
        if hoard is not None:
            hoard_id = str(hoard["hoard_id"])
            self._force_hoard_context(artifact, hoard)
        row = self._row_from_artifact(artifact, s, cell, object_id, hoard_id)
        candidate = self._candidate_from_row(row)
        meta = {
            "action_id": action.action_id, "regime": action.regime, "site_node": action.site_node,
            "research_question": action.question, "poari_p": action.p,
            "poari_action_score_truth": round(float(action.poari_score), 6),
            "poari_dimensions_truth": {k: round(float(v), 6) for k, v in action.dimensions.items()},
            "action_temperature_truth": action.temperature, "tail_event_truth": _is_tail(self.world, s),
            "stratum_archaeological_intensity_truth": _archaeological_intensity(s),
        }
        return candidate, meta

    @staticmethod
    def _sample_deposition_mode(s: intensity.LossStratum, rng: np.random.Generator) -> str:
        keys = list(s.deposition_mode_weights)
        p = np.asarray([max(0.0, float(s.deposition_mode_weights[k])) for k in keys], dtype=float); p /= p.sum()
        return str(rng.choice(keys, p=p))

    def _force_hoard_context(self, artifact: MutableMapping[str, Any], hoard: Mapping[str, Any]) -> None:
        event_bc = min(int(artifact["timeline"]["production_bc"]), int(hoard["event_bc"]))
        artifact["timeline"]["loss_bc"] = event_bc; artifact["loss"]["date_bc"] = event_bc
        artifact["loss"]["deposition_mode"] = "finished_object_hoard"
        node = self.world.nodes[str(hoard["node_id"])]
        common_site = {
            "node_id": str(hoard["node_id"]), "label": str(node.label), "region": med.REGION_BY_NODE.get(str(hoard["node_id"]), "other"),
            "kind": str(node.kind), "lon": round(float(hoard["lon"]), 6), "lat": round(float(hoard["lat"]), 6),
        }
        artifact["loss"]["site"] = deepcopy(common_site)
        artifact["find_context"] = {
            "find_site_id": str(hoard["site_id"]), "site": deepcopy(common_site),
            "discovery_year_ce": int(hoard["discovery_year_ce"]), "recovery_method": "coherent hoard excavation",
        }

    def _row_from_artifact(self, artifact: Mapping[str, Any], s: intensity.LossStratum, cell: intensity.ProductionCell,
                           object_id: str, hoard_id: str | None) -> Dict[str, Any]:
        alloy = artifact["material"]["bulk_alloy_wt_pct"]
        material = "bronze object" if float(alloy.get("Sn", 0.0)) >= 2.0 else "arsenical copper object" if float(alloy.get("As", 0.0)) >= .7 else "copper object"
        corr = artifact["corrosion"]; integrity = float(corr["integrity_fraction"])
        preservation = "good; coherent corrosion layers" if integrity > .72 else "moderate; surface alteration" if integrity > .48 else "fragmentary; substantial corrosion"
        find = artifact["find_context"]["site"]
        guild_aff = artifact["manufacture"].get("guild_affinities", {})
        source_entropy = float(artifact["material"].get("source_entropy", 0.0))
        recycle_fraction = float(artifact["material"].get("recycled_fraction_proxy", 0.0))
        exception = _exceptionality(self.world, s)
        complexity = float(np.clip(.21 * source_entropy + .20 * recycle_fraction + .17 * min(1, s.expected_physical_crossings / 2) + .16 * min(1, s.expected_field_crossings / .2) + .16 * min(1, len(artifact["manufacture"].get("operations", [])) / 7) + .10 * exception, 0, 1))
        primary_guild = artifact["manufacture"].get("primary_guild_id")
        return {
            "object_id": object_id, "display_name": f"Copper-alloy {cell.object_class}", "class": cell.object_class,
            "mass_kg": round(float(artifact["identity"]["mass_kg_present"]), 5),
            "date_center_bc": int(cell.date_bc), "date_uncertainty_years": int(self.rng.choice([25, 40, 60, 80, 100])),
            "findspot": {"lon": find["lon"], "lat": find["lat"], "node_label": find["label"]},
            "deposition_mode_truth": artifact["loss"]["deposition_mode"], "hoard_id": hoard_id,
            "preservation": preservation, "catalogue_material": material,
            "tests": {"manufacturing_sequence": list(artifact["manufacture"].get("operations", []))},
            "artifact_truth": deepcopy(artifact),
            "truth": {
                "bundle_id": cell.bundle_id, "bundle_family": cell.bundle_family,
                "source_mix": deepcopy(artifact["material"]["source_mix"]),
                "workshop_id": artifact["manufacture"]["workshop_id"], "lineage_id": artifact["manufacture"]["lineage_id"],
                "workshop_node": artifact["manufacture"]["workshop_node_id"],
                "recycle_fraction": round(recycle_fraction, 5), "repair_count": len(artifact["timeline"].get("repair_events", [])),
                "surface_complexity": round(float(corr["surface_coverage_fraction"]), 5),
                "technical_vector": deepcopy(artifact["manufacture"]["technical_vector"]), "route": deepcopy(artifact["timeline"]["route_nodes_representative"]),
                "route_nodes_truth": deepcopy(artifact["timeline"]["route_nodes_representative"]),
                "source_entropy": round(source_entropy, 5), "complexity": round(complexity, 5),
                "macro_region": med.REGION_BY_NODE.get(s.node_id, "other"),
                "long_distance_tail": _is_tail(self.world, s), "route_km": round(float(s.route_distance_from_origin_km), 3),
                "corridor_crossings": round(float(s.expected_physical_crossings), 5), "field_crossings": round(float(s.expected_field_crossings), 5),
                "exceptionality": round(exception, 5), "guild_id": primary_guild,
                "guild_strength": round(max([float(v) for v in guild_aff.values()] or [0.0]), 5),
            },
        }

    def _update_evidence_state(self, slot: Any, c: Any) -> None:
        meta = self.acquisition_by_object[c.object_id]
        site = str(meta["site_node"]); self._known_site_counts[site] += 1
        self._known_region_counts[c.region] += 1; self._known_class_counts[c.object_class] += 1
        artifact = c.row.get("artifact_truth")
        if not artifact:
            return
        # Campaign state receives only machine outputs that the current curriculum
        # makes available; it never reads guild/source truth to choose the next dig.
        tools = [t for t in self._available_tests(slot, c) if t in instruments.TOOL_FUNCS]
        if not tools:
            tools = ["visual"]
        signature: Dict[str, float] = {}
        for tool in tools[:3]:
            payload = instruments.measure_tool(artifact, tool, self.seeds.measurement_seed)
            for key, val in payload.get("measurements", {}).items():
                if isinstance(val, Mapping) and isinstance(val.get("value"), (int, float)):
                    signature[f"{tool}/{key}"] = float(val["value"])
        if signature:
            self._observed_numeric_signatures.append(signature)

    def _project_player_object(self, slot: Any, c: Any) -> Dict[str, Any]:
        public = super()._project_player_object(slot, c)
        meta = self.acquisition_by_object.get(c.object_id, {})
        public["acquisition"] = {
            "regime": meta.get("regime"), "action_id": meta.get("action_id"),
            "research_question": meta.get("research_question"),
            "context": "hoard" if c.hoard_id else "stray/legacy" if meta.get("regime") == "stray_tail" else "excavation/research",
        }
        return public

    def career_report(self) -> Dict[str, Any]:
        report = super().career_report()
        by_regime: Dict[str, List[Any]] = defaultdict(list)
        for c in self.selected:
            by_regime[self.acquisition_by_object[c.object_id]["regime"]].append(c)
        report["acquisition_version"] = ACQUISITION_VERSION
        report["career_source"] = "latent loss/intensity world; not 30k catalogue"
        report["intensity_world"] = self.flow_summary
        report["acquisition_regimes_truth"] = {
            name: {
                "objects": len(rows),
                "tail_share": round(float(np.mean([bool(self.acquisition_by_object[c.object_id]["tail_event_truth"]) for c in rows])), 4),
                "regions": dict(sorted(Counter(c.region for c in rows).items())),
                "classes": dict(sorted(Counter(c.object_class for c in rows).items())),
            }
            for name, rows in by_regime.items()
        }
        report["random_hoard_truth"] = deepcopy(self._hoard)
        report["research_actions_truth"] = [
            {
                "action_id": a.action_id, "regime": a.regime, "site_node": a.site_node, "p": a.p,
                "dimensions": a.dimensions, "poari_score": a.poari_score, "temperature": a.temperature,
                "block_size": a.block_size, "question": a.question,
            } for a in self.research_actions
        ]
        report["poari_action_rule"] = "POARI ranks research actions/sites. Artefacts are instantiated only after the action is selected."
        return report

    def debug_truth(self) -> List[Dict[str, Any]]:
        out = super().debug_truth()
        for item in out:
            oid = item["object_id"]
            item["acquisition_truth"] = deepcopy(self.acquisition_by_object.get(oid, {}))
        return out
