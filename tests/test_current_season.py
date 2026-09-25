from datetime import date

import pandas as pd
import pytest

from scripts.build_current_fixtures import normalize_matches
from src.current_season import load_player_csv


def test_current_fixture_snapshot_has_one_club_match_per_round():
    import json

    with open("data/current/fixtures.json", encoding="utf-8") as handle:
        payload = json.load(handle)
    matches = payload["matches"]
    assert payload["season"] == "2026/27"
    assert len(matches) == 38
    assert len({match["round"] for match in matches}) == 38
    assert sum(match["status"] == "final" for match in matches) == 7
    assert all("FC Barcelona" in (match["home"], match["away"]) for match in matches)


def test_fixture_normalization_rejects_missing_round():
    with pytest.raises(ValueError, match="38 distinct"):
        normalize_matches({"matches": []})


def test_authorized_player_csv_validates_matchdays_and_missing_metrics():
    valid = b"matchday,date,player,minutes,goals\n1,2026-08-27,Test Player,90,1\n2,2026-08-23,Test Player,45,0\n"
    frame = load_player_csv(valid, {1, 2}, date(2026, 9, 25))
    assert frame.goals.sum() == 1
    assert "xg" not in frame.columns
    bad = b"matchday,date,player,minutes\n8,2026-10-10,Test Player,90\n"
    with pytest.raises(ValueError, match="completed"):
        load_player_csv(bad, {1, 2}, date(2026, 9, 25))


def test_duplicate_player_match_is_rejected():
    duplicate = b"matchday,date,player,minutes\n1,2026-08-27,Test Player,90\n1,2026-08-27,Test Player,30\n"
    with pytest.raises(ValueError, match="one nonblank"):
        load_player_csv(duplicate, {1}, date(2026, 9, 25))
