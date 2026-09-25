import json

import pytest

from src.team_forecast import forecast


def test_team_forecast_covers_all_remaining_fixtures():
    fixtures = json.load(open("data/current/fixtures.json", encoding="utf-8"))["matches"]
    seasons = json.load(open("data/current/team_forecast.json", encoding="utf-8"))["seasons"]
    result = forecast(fixtures, seasons)
    assert result["observed_points"] == 21
    assert result["remaining"] == 31
    assert len(result["fixtures"]) == 31
    assert result["low"] <= result["expected_final_points"] <= result["high"]
    assert all(abs(row["win"] + row["draw"] + row["loss"] - 1) < 1e-9
               for row in result["fixtures"])
    assert result["fixtures"][-1]["projected_total"] == pytest.approx(
        result["expected_final_points"])


def test_mismatched_snapshots_are_rejected():
    fixtures = json.load(open("data/current/fixtures.json", encoding="utf-8"))["matches"]
    seasons = json.load(open("data/current/team_forecast.json", encoding="utf-8"))["seasons"]
    seasons["2026-27"]["teams"]["FC Barcelona"]["games"] += 1
    with pytest.raises(ValueError, match="out of sync"):
        forecast(fixtures, seasons)
