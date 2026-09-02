from __future__ import annotations

from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
ATOLIA = ROOT / "src" / "atolia"
if str(ATOLIA) not in sys.path:
    sys.path.insert(0, str(ATOLIA))

import v3_phase07_replay_capsule as replay


def test_source_context_is_authoritative_below_phase05_hash_precision() -> None:
    source = 0.6896641554771085
    planned = 0.6896641554666667

    delta = replay._source_context_delta(source, planned)

    assert delta == source - planned
    assert replay._phase05_hash_float(source) == replay._phase05_hash_float(planned)


def test_source_context_rejects_a_different_phase05_state() -> None:
    with pytest.raises(RuntimeError, match="frozen phase-05 hash precision"):
        replay._source_context_delta(0.6896641554771085, 0.6896642554666667)


def test_source_context_requires_finite_values() -> None:
    with pytest.raises(ValueError, match="must be finite"):
        replay._source_context_delta(float("nan"), 0.5)
