"""Backend half of the shared GPS decision vectors (the Android half asserts the same file)."""
import json
import math
from pathlib import Path

import pytest

from app.services import geo_decision as g

VECTORS = Path(__file__).resolve().parents[2] / "fieldtrackpro-android" / "app" / "src" / "test" / "resources" / "gps_decision_vectors.json"
DATA = json.loads(VECTORS.read_text(encoding="utf-8"))


def test_constants_match_the_vector_file():
    assert DATA["radius_m"] == 75.0
    assert g.K == DATA["k"] and g.MAX_ACCURACY_M == DATA["max_accuracy_m"] and g.LIVE_MAX_AGE_S == DATA["live_max_age_s"]


@pytest.mark.parametrize("case", DATA["cases"], ids=[c["name"] for c in DATA["cases"]])
def test_vector(case):
    acc = case["accuracy_m"]
    d = g.decide(case["distance_m"], acc, case["pin_accuracy_m"], DATA["radius_m"],
                 age_s=case["age_s"], coords_valid=case["coords_valid"])
    assert d.outcome.value == case["expected"], case
    assert d.reason == case["reason"]
    assert d.point_inside == case["point_inside"]


def test_combined_uncertainty_formula():
    assert g.combined_uncertainty(40.0, 30.0) == pytest.approx(50.0)
    assert g.combined_uncertainty(40.0, None) == 40.0
    assert g.combined_uncertainty(40.0, 0.0) == 40.0


def test_offline_queued_fix_skips_only_the_freshness_test():
    old = g.decide(10.0, 10.0, None, 75.0, age_s=3 * 3600, max_age_s=None)
    assert old.outcome is g.Outcome.INSIDE
    assert g.decide(10.0, 464.0, None, 75.0, age_s=3 * 3600, max_age_s=None).outcome is g.Outcome.POOR_FIX


def test_spec_examples_from_the_report():
    """10/50/75/100 m against 5/20/40/70/100 m accuracy, no pin accuracy (the 'K = 0.5' table)."""
    expect = {
        10: ["INSIDE", "INSIDE", "INSIDE", "INSIDE", "INSIDE"],
        50: ["INSIDE", "INSIDE", "INSIDE", "UNCERTAIN", "UNCERTAIN"],
        75: ["UNCERTAIN", "UNCERTAIN", "UNCERTAIN", "UNCERTAIN", "UNCERTAIN"],
        100: ["OUTSIDE", "OUTSIDE", "UNCERTAIN", "UNCERTAIN", "UNCERTAIN"],
    }
    for dist, row in expect.items():
        got = [g.decide(float(dist), float(a), None, 75.0, age_s=1.0).outcome.value for a in (5, 20, 40, 70, 100)]
        assert got == row, (dist, got)
    assert math.isclose(g.EPS, 1e-9)
