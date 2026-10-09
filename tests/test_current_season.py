from datetime import date

import pandas as pd
import pytest

from src.current_season import load_player_csv


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


def test_role_and_whole_matchday_are_validated():
    invalid_round = b"matchday,date,player,role,minutes\n1.5,2026-08-27,Test Player,FWD,90\n"
    with pytest.raises(ValueError, match="whole number"):
        load_player_csv(invalid_round, {1}, date(2026, 9, 25))
    invalid_role = b"matchday,date,player,role,minutes\n1,2026-08-27,Test Player,STRIKER,90\n"
    with pytest.raises(ValueError, match="FWD"):
        load_player_csv(invalid_role, {1}, date(2026, 9, 25))
