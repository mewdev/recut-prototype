import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from recut.contracts import Plan, Review
from recut.contracts.units import check_time, db_to_gain, parse_time

PLANS = Path(__file__).parents[2] / "examples" / "summer-party" / "plans"


@pytest.mark.parametrize("s,seconds", [
    ("1/4", 0.5), ("1/8", 0.25), ("1/8.", 0.375), ("1/8t", 1 / 6), ("3 beats", 1.5),
    ("2 bars", 4.0), ("1 bar", 2.0), ("250ms", 0.25), ("3.5s", 3.5), ("1/1", 2.0),
])
def test_parse_time_at_120_bpm(s, seconds):
    assert parse_time(s, bpm=120) == pytest.approx(seconds)


@pytest.mark.parametrize("bad", ["1/7", "2", 2, "fast", "1/4..", "-1s"])
def test_bad_time_strings_rejected(bad):
    with pytest.raises(ValueError):
        check_time(bad)


def test_db_to_gain():
    assert db_to_gain(0) == 1.0
    assert db_to_gain("-inf") == 0.0
    assert db_to_gain(-6) == pytest.approx(0.501, abs=1e-3)


@pytest.mark.parametrize("name", sorted(p.name for p in PLANS.glob("*.json")))
def test_example_plans_validate(name):
    Plan.model_validate_json((PLANS / name).read_text())


def _plan(**track_overrides):
    data = json.loads((PLANS / "02-ending-transplant.json").read_text())
    data["tracks"][0].update(track_overrides)
    return data


def test_unknown_field_is_an_error():
    data = _plan()
    data["tracks"][0]["clips"][0]["wetness"] = 0.4  # old-API name, typo-like
    with pytest.raises(ValidationError, match="wetness"):
        Plan.model_validate(data)


def test_reference_errors():
    data = _plan()
    data["tracks"][0]["clips"][0]["source"] = "z"
    with pytest.raises(ValidationError, match="unknown source"):
        Plan.model_validate(data)
    data = _plan()
    data["tracks"][0]["clips"][2]["sends"] = {"B": 0}
    with pytest.raises(ValidationError, match="unknown return"):
        Plan.model_validate(data)


def test_xfade_cannot_end_track():
    data = _plan()
    data["tracks"][0]["clips"].append({"id": "x9", "type": "xfade"})
    with pytest.raises(ValidationError, match="must start and end with a clip"):
        Plan.model_validate(data)


def test_qsin_accepted_as_equal_power():
    data = _plan()
    data["tracks"][0]["clips"][3]["in_shape"] = "qsin"
    assert Plan.model_validate(data).tracks[0].clips[3].shape_in == "equal_power"


def test_review_rejects_unknown_tag():
    with pytest.raises(ValidationError):
        Review(iteration=1, verdict="ship", tags=["sounds_bad"])
