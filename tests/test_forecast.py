import pandas as pd
import pytest

from src.forecast import ForecastModel


@pytest.fixture(scope="module")
def goals_model():
    history = pd.read_csv("data/derived/appearances.csv")
    return ForecastModel(history, ("goals",))


def test_historical_training_excludes_barcelona_and_has_holdout(goals_model):
    assert goals_model.training_sizes["goals"] > 1000
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
