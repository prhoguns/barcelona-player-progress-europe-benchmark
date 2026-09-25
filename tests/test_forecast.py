import pandas as pd
import pytest

from src.forecast import ForecastModel, make_training_rows


@pytest.fixture(scope="module")
def goals_model():
    history = pd.read_csv("data/derived/appearances.csv")
    recent = pd.read_csv("data/training/leverkusen_2023_24_appearances.csv")
    assert recent.match_id.nunique() == 34
    assert recent.date.min().startswith("2023")
    assert recent.date.max().startswith("2024")
    history = pd.concat([history, recent], ignore_index=True)
    return ForecastModel(history, ("goals",))


def test_historical_training_excludes_barcelona_and_has_holdout(goals_model):
    assert goals_model.training_sizes["goals"] > 1000
    assert goals_model.training_seasons == [2015, 2023]
    assert len(goals_model.holdout["goals"]) > 100
    assert goals_model.holdout["goals"].error.abs().mean() < 10


def test_future_uploaded_row_cannot_change_earlier_forecast(goals_model):
    rows = pd.DataFrame({"matchday": range(1, 8), "minutes": [90] * 7,
                         "goals": [1, 0, 2, 1, 0, 1, 1], "role": ["FWD"] * 7})
    rounds = list(range(1, 8))
    first = goals_model.predict(rows, "goals", rounds, 5)
    rows.loc[rows.matchday == 6, "goals"] = 100
    again = goals_model.predict(rows, "goals", rounds, 5)
    assert first == again
    assert first["observed"] == 4
    assert first["remaining_matches"] == 33
    assert first["observed"] <= first["lower"] <= first["projected"] <= first["upper"]


def test_missing_metric_and_short_exposure_are_not_forecast(goals_model):
    data = pd.DataFrame({"matchday": [1], "minutes": [30], "goals": [0]})
    with pytest.raises(ValueError, match="90 observed"):
        goals_model.predict(data, "goals", [1, 2, 3, 4, 5], 5)


def test_same_club_in_two_seasons_is_kept_separate():
    rows = []
    for year in (2015, 2023):
        for game in range(6):
            rows.append({"club": "Bayer Leverkusen", "match_id": year * 100 + game,
                         "date": f"{year}-08-{game + 1:02d}", "player_id": 1,
                         "minutes": 90, "goals": 1 if game == 0 else 0,
                         "role": "FWD"})
    training = make_training_rows(pd.DataFrame(rows), "goals")
    assert sorted(training.season.tolist()) == [2015, 2023]
    assert training.checkpoint.tolist() == [5, 5]
    assert training.observed.tolist() == [1, 1]
