from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence, Tuple


@dataclass(frozen=True)
class CurriculumSlot:
    index: int
    level: int
    slot_in_level: int
    competency: str
    allowed_classes: Tuple[str, ...]
    allowed_materials: Tuple[str, ...]
    required_tests: Tuple[str, ...]
    target_difficulty: float
    max_spoiler: float
    min_network_information: float
    max_network_information: float
    background_probability: float
    recurrence_role: str
    destructive_sampling_policy: str


LEVEL_THEMES: Dict[int, Dict[str, object]] = {
    1: {"competency": "bulk composition and uncertainty", "classes": ("awl", "bead", "pin", "ring", "fitting"), "materials": ("copper", "bronze"), "tests": ("xrf",), "difficulty": .05, "spoiler": .05, "background": .72},
    2: {"competency": "intentional alloy versus impurity", "classes": ("awl", "pin", "axe", "dagger", "ring"), "materials": ("copper", "bronze"), "tests": ("xrf",), "difficulty": .08, "spoiler": .06, "background": .66},
    3: {"competency": "casting versus working", "classes": ("axe", "dagger", "spearhead", "fitting", "awl"), "materials": ("copper", "bronze"), "tests": ("metallography", "morphometrics"), "difficulty": .11, "spoiler": .07, "background": .58},
    4: {"competency": "simple object comparison", "classes": ("axe", "dagger", "spearhead", "pin", "knife"), "materials": ("copper", "bronze"), "tests": ("xrf", "morphometrics"), "difficulty": .14, "spoiler": .09, "background": .52},
    5: {"competency": "alloy families and property tradeoffs", "classes": ("axe", "spearhead", "knife", "sickle", "chisel"), "materials": ("bronze", "copper_zinc"), "tests": ("xrf", "metallography"), "difficulty": .17, "spoiler": .10, "background": .46},
    6: {"competency": "trace-element reading", "classes": ("axe", "dagger", "pin", "ring", "fitting"), "materials": ("copper", "bronze"), "tests": ("xrf",), "difficulty": .20, "spoiler": .12, "background": .42},
    7: {"competency": "trace fingerprints without overclaiming provenance", "classes": ("axe", "dagger", "spearhead", "ingot", "fitting"), "materials": ("copper", "bronze"), "tests": ("xrf", "lead_isotopes"), "difficulty": .24, "spoiler": .14, "background": .38},
    8: {"competency": "smelting products and process residues", "classes": ("scrap", "ingot", "fitting"), "materials": ("copper", "bronze"), "tests": ("xrf", "metallography"), "difficulty": .27, "spoiler": .15, "background": .34},
    9: {"competency": "ingots, charge preparation and remelting", "classes": ("ingot", "scrap", "fitting"), "materials": ("copper", "bronze", "tin_pewter", "lead"), "tests": ("xrf", "lead_isotopes"), "difficulty": .30, "spoiler": .17, "background": .32},
    10: {"competency": "casting structure", "classes": ("axe", "spearhead", "dagger", "figurine", "fitting"), "materials": ("bronze", "copper"), "tests": ("metallography", "morphometrics"), "difficulty": .33, "spoiler": .19, "background": .30},
    11: {"competency": "working and annealing sequences", "classes": ("vessel", "sickle", "knife", "ring", "pin"), "materials": ("bronze", "copper"), "tests": ("metallography", "morphometrics"), "difficulty": .36, "spoiler": .21, "background": .28},
    12: {"competency": "inclusions and process contamination", "classes": ("scrap", "ingot", "axe", "knife", "fitting"), "materials": ("bronze", "copper", "iron_steel"), "tests": ("metallography", "xrf"), "difficulty": .39, "spoiler": .23, "background": .26},
    13: {"competency": "manufacturing sequence reconstruction", "classes": ("axe", "dagger", "spearhead", "vessel", "ornament"), "materials": ("bronze", "copper"), "tests": ("manufacturing_sequence", "metallography"), "difficulty": .42, "spoiler": .25, "background": .24},
    14: {"competency": "mould families and repeated technical habits", "classes": ("axe", "spearhead", "dagger", "figurine", "fitting"), "materials": ("bronze", "copper"), "tests": ("morphometrics", "manufacturing_sequence"), "difficulty": .45, "spoiler": .28, "background": .22},
    15: {"competency": "source versus workshop", "classes": ("axe", "dagger", "spearhead", "vessel", "ornament"), "materials": ("bronze", "copper"), "tests": ("lead_isotopes", "metallography", "morphometrics"), "difficulty": .48, "spoiler": .31, "background": .20},
    16: {"competency": "repair and layered biography", "classes": ("vessel", "sword", "dagger", "axe", "fitting"), "materials": ("bronze", "copper", "iron_steel"), "tests": ("xrf", "metallography", "manufacturing_sequence"), "difficulty": .51, "spoiler": .34, "background": .18},
    17: {"competency": "recycling and mixed metal histories", "classes": ("scrap", "ingot", "axe", "vessel", "fitting"), "materials": ("bronze", "copper", "copper_zinc"), "tests": ("xrf", "lead_isotopes"), "difficulty": .54, "spoiler": .37, "background": .17},
    18: {"competency": "workshop-lineage inference", "classes": ("axe", "spearhead", "dagger", "vessel", "ornament"), "materials": ("bronze", "copper"), "tests": ("metallography", "morphometrics", "manufacturing_sequence"), "difficulty": .57, "spoiler": .40, "background": .16},
    19: {"competency": "technical recurrence across object classes", "classes": ("axe", "vessel", "ornament", "spearhead", "ring", "pin"), "materials": ("bronze", "copper"), "tests": ("metallography", "morphometrics"), "difficulty": .60, "spoiler": .44, "background": .15},
    20: {"competency": "material movement versus craft movement", "classes": ("axe", "sword", "dagger", "vessel", "ornament"), "materials": ("bronze", "copper"), "tests": ("lead_isotopes", "morphometrics", "metallography"), "difficulty": .63, "spoiler": .47, "background": .14},
    21: {"competency": "hoard structure and biased assemblages", "classes": ("axe", "spearhead", "ornament", "scrap", "ingot"), "materials": ("bronze", "copper"), "tests": ("xrf", "lead_isotopes", "morphometrics"), "difficulty": .66, "spoiler": .50, "background": .13},
    22: {"competency": "surface layers versus bulk history", "classes": ("vessel", "ornament", "fitting", "figurine", "ring"), "materials": ("bronze", "copper_zinc", "gold_precious", "silver_precious"), "tests": ("xrf", "metallography"), "difficulty": .69, "spoiler": .53, "background": .12},
    23: {"competency": "technical genealogy under material substitution", "classes": ("knife", "sword", "axe", "chisel", "ornament"), "materials": ("bronze", "iron_steel", "silver_precious"), "tests": ("metallography", "manufacturing_sequence"), "difficulty": .72, "spoiler": .56, "background": .11},
    24: {"competency": "regional source fields and isotope overlap", "classes": ("ingot", "axe", "spearhead", "dagger", "ornament"), "materials": ("bronze", "copper", "silver_precious"), "tests": ("lead_isotopes", "xrf"), "difficulty": .75, "spoiler": .60, "background": .10},
    25: {"competency": "long-distance tails and competing routes", "classes": ("ingot", "sword", "dagger", "ornament", "axe"), "materials": ("bronze", "copper", "gold_precious", "silver_precious"), "tests": ("lead_isotopes", "morphometrics", "metallography"), "difficulty": .78, "spoiler": .64, "background": .09},
    26: {"competency": "provenance under recycling", "classes": ("axe", "spearhead", "ingot", "vessel", "ornament"), "materials": ("bronze", "copper", "silver_precious"), "tests": ("xrf", "lead_isotopes", "metallography"), "difficulty": .81, "spoiler": .68, "background": .08},
    27: {"competency": "multi-source Bayesian comparison", "classes": ("axe", "spearhead", "dagger", "vessel", "ornament"), "materials": ("bronze", "copper", "silver_precious", "gold_precious"), "tests": ("xrf", "lead_isotopes", "metallography", "morphometrics"), "difficulty": .84, "spoiler": .72, "background": .07},
    28: {"competency": "predictive network hypothesis", "classes": ("axe", "sword", "dagger", "vessel", "ornament", "ingot"), "materials": ("bronze", "copper", "silver_precious", "gold_precious"), "tests": ("xrf", "lead_isotopes", "metallography", "morphometrics"), "difficulty": .88, "spoiler": .77, "background": .06},
    29: {"competency": "precious and non-destructive multi-layer analysis", "classes": ("ornament", "vessel", "ring", "figurine", "sword"), "materials": ("gold_precious", "silver_precious", "bronze"), "tests": ("xrf", "morphometrics", "manufacturing_sequence"), "difficulty": .93, "spoiler": .82, "background": .05},
    30: {"competency": "museum-grade integrated inference under sampling limits", "classes": ("vessel", "ornament", "sword", "ring", "figurine"), "materials": ("gold_precious", "silver_precious", "bronze", "iron_steel"), "tests": ("xrf", "lead_isotopes", "metallography", "morphometrics", "manufacturing_sequence"), "difficulty": .98, "spoiler": .88, "background": .04},
}


RECURRENCE_PATTERN = (
    "background", "independent", "independent", "easy_recurrence", "false_friend",
    "independent", "medium_recurrence", "background", "independent", "hard_recurrence",
)


def build_contract() -> List[CurriculumSlot]:
    slots: List[CurriculumSlot] = []
    index = 0
    for level in range(1, 31):
        spec = LEVEL_THEMES[level]
        for position in range(1, 11):
            index += 1
            difficulty = float(spec["difficulty"]) + (position - 5.5) * .006
            spoiler = float(spec["spoiler"]) + max(0, position - 7) * .008
            role = RECURRENCE_PATTERN[position - 1]
            if level <= 5 and role in {"easy_recurrence", "medium_recurrence", "hard_recurrence"}:
                role = "independent"
            if level <= 9 and role == "false_friend":
                role = "independent"
            destructive = "allowed"
            if level >= 29:
                destructive = "forbidden"
            elif level >= 22 and position in {4, 9}:
                destructive = "restricted"
            slots.append(CurriculumSlot(
                index=index,
                level=level,
                slot_in_level=position,
                competency=str(spec["competency"]),
                allowed_classes=tuple(spec["classes"]),
                allowed_materials=tuple(spec["materials"]),
                required_tests=tuple(spec["tests"]),
                target_difficulty=max(0.01, min(.99, difficulty)),
                max_spoiler=max(.03, min(.95, spoiler)),
                min_network_information=max(0.0, (level - 9) / 30.0 * .15),
                max_network_information=max(.04, min(.95, float(spec["spoiler"]) + .10)),
                background_probability=float(spec["background"]),
                recurrence_role=role,
                destructive_sampling_policy=destructive,
            ))
    return slots


def as_jsonable(slots: Sequence[CurriculumSlot] | None = None) -> Dict[str, object]:
    slots = list(slots or build_contract())
    return {
        "schema": "dr-corrosion.archaeometallurgy.curriculum.v1",
        "slot_count": len(slots),
        "levels": 30,
        "objects_per_level": 10,
        "slots": [
            {
                "index": slot.index,
                "level": slot.level,
                "slot_in_level": slot.slot_in_level,
                "competency": slot.competency,
                "allowed_classes": list(slot.allowed_classes),
                "allowed_materials": list(slot.allowed_materials),
                "required_tests": list(slot.required_tests),
                "target_difficulty": round(slot.target_difficulty, 4),
                "max_spoiler": round(slot.max_spoiler, 4),
                "min_network_information": round(slot.min_network_information, 4),
                "max_network_information": round(slot.max_network_information, 4),
                "background_probability": round(slot.background_probability, 4),
                "recurrence_role": slot.recurrence_role,
                "destructive_sampling_policy": slot.destructive_sampling_policy,
            }
            for slot in slots
        ],
    }
