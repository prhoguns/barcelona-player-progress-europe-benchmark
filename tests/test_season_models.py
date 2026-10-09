import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src import match_model as mm
from src import player_model as pm
from src import season_forecast as sf
from src import wiki_season as ws
from src.leagues import LEAGUES
from src.schedule import final_score, name_map

DATA = Path("data/current")


def toy_league(seasons=(2020, 2021, 2022), seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    clubs = [f"Club {i}" for i in range(6)]
    strength = np.linspace(0.6, 1.8, len(clubs))
    rows = []
    for season in seasons:
        day = date(season, 8, 1)
        for i, home in enumerate(clubs):
            for j, away in enumerate(clubs):
                if i == j:
                    continue
                hg, ag = rng.poisson(strength[i] * 1.2), rng.poisson(strength[j])
                rows.append({"season": season, "date": day.isoformat(), "home": home, "away": away,
                             "home_goals": hg, "away_goals": ag, "home_sot": hg * 2 + 2, "away_sot": ag * 2 + 2})
                day += timedelta(days=1)
    return pd.DataFrame(rows)


def test_final_score_accepts_bare_list_results():
    assert final_score({"score": {"ft": [2, 1]}}) == [2, 1]
    assert final_score({"score": [0, 0]}) == [0, 0]
    assert final_score({"score": {}}) is None
    assert final_score({}) is None


def test_name_map_aligns_sources_from_shared_scores():
    played = pd.DataFrame({"date": ["2026-08-20", "2026-08-21"], "home": ["Barca", "Madrid"],
                           "away": ["Madrid", "Barca"], "home_goals": [3, 0], "away_goals": [1, 0]})
    raw = [{"date": "2026-08-20", "team1": "FC Barcelona", "team2": "Real Madrid CF", "score": {"ft": [3, 1]}},
           {"date": "2026-08-21", "team1": "Real Madrid CF", "team2": "FC Barcelona", "score": [0, 0]}]
    assert name_map(raw, played) == {"FC Barcelona": "Barca", "Real Madrid CF": "Madrid"}


def test_outcome_probabilities_sum_to_one_and_favour_stronger_side():
    probs = mm.outcome_probabilities(np.array([2.5, 0.6]), np.array([0.6, 2.5]), -0.05)
    assert np.allclose(probs.sum(axis=1), 1)
    assert probs[0, 0] > probs[0, 2] and probs[1, 2] > probs[1, 0]


def test_scores_reward_confident_correct_forecasts():
    outcome = np.array([0, 1, 2])
    sharp = mm.scores(np.array([[0.8, 0.1, 0.1], [0.1, 0.8, 0.1], [0.1, 0.1, 0.8]]), outcome)
    flat = mm.scores(np.full((3, 3), 1 / 3), outcome)
    assert sharp["log_loss"] < flat["log_loss"] and sharp["rps"] < flat["rps"]


def test_features_use_only_earlier_matches():
    league = toy_league()
    features = mm.pre_match_features(league, 0.1, 0.8)
    first = features.iloc[0]
    assert first.attack_goals == pytest.approx(np.log(mm.DEFAULT["gf"]))
    snaps = mm.ratings_snapshots(league, 0.1, 0.8, {(2021, "2021-08-01")})
    replay = mm.Ratings(0.1, 0.8)
    clubs = mm.season_clubs(league)
    for row in league[league.date <= "2021-08-01"].itertuples(index=False):
        replay.start_season(row.season, clubs[row.season])
        replay.update(row)
    replay.start_season(2021, clubs[2021])
    assert snaps[(2021, "2021-08-01")].teams == replay.teams


def test_trained_model_ranks_clubs_and_season_totals_are_consistent():
    league = toy_league()
    features = mm.pre_match_features(league, 0.1, 0.8)
    model = mm.fit(features[features.season < 2022])
    ratings = mm.ratings_snapshots(league, 0.1, 0.8, {(2022, "2022-07-31")})[(2022, "2022-07-31")]
    fixtures = league[league.season == 2022][["home", "away"]]
    strong = sf.fixture_forecasts(ratings, model, fixtures[(fixtures.home == "Club 5") | (fixtures.away == "Club 5")], "Club 5")
    weak = sf.fixture_forecasts(ratings, model, fixtures[(fixtures.home == "Club 0") | (fixtures.away == "Club 0")], "Club 0")
    assert strong.win.mean() > weak.win.mean()
    observed = {"points": 0, "goals_for": 0, "goals_against": 0}
    total = sf.totals(observed, strong, model)
    assert total["points_low"] <= total["points"] <= total["points_high"]
    assert total["goals_for_low"] <= total["goals_for"] <= total["goals_for_high"]


def test_goal_template_reads_minutes_even_without_empty_modifiers():
    events = ws.goal_events("*[[Raphinha]] {{goal|25|pen.|42|67|pen.}}\n*[[Asier Villalibre|Villalibre]] {{goal|36|o.g.}}")
    assert [e["minute"] for e in events] == ["25", "42", "67", "36"]
    assert [e["penalty"] for e in events] == [True, False, True, False]
    assert events[-1]["own_goal"] and events[-1]["player"] == "Asier Villalibre"


def test_club_season_flags_matches_whose_scorers_do_not_add_up():
    page = """==La Liga==
{{football box collapsible
|date = 23 August 2026
|team1 = [[Elche CF|Elche]]
|score = 0–2
|team2 = Barcelona
|goals2 = *[[Raphinha]] {{goal|14}}
}}"""
    matches = pd.DataFrame({"date": ["2026-08-23"], "home": ["Elche"], "away": ["Barcelona"],
                            "home_goals": [0], "away_goals": [2]})
    events, coverage = ws.club_season(page, "Barcelona", matches)
    assert coverage.found.all() and not coverage.complete.any()
    assert len(events) == 1


def test_player_projection_shrinks_hot_starts_and_never_goes_below_observed():
    rows = pd.DataFrame({"goals": [6, 1], "club_goals": [10, 10], "previous_share": [np.nan, 0.3],
                         "remaining_goals": [50.0, 50.0], "matches_played": [7, 7]})
    params = {"strength": 20, "weight": 0.5, "baseline": 0.05, "dispersion": 0.3}
    result = pm.forecast(rows, params)
    assert (result.projected >= rows.goals).all()
    assert result.projected.iloc[0] < 6 + 0.6 * 50  # below the raw 60% share
    assert (result.low <= result.projected).all() and (result.projected <= result.high).all()


@pytest.mark.parametrize("league", sorted(LEAGUES))
def test_built_outputs_are_consistent(league):
    clubs = json.loads((DATA / league / "clubs.json").read_text())
    model = json.loads((DATA / league / "model.json").read_text())
    assert len(clubs["clubs"]) == 20
    for name, info in clubs["clubs"].items():
        assert info["record"]["played"] + len(info["fixtures"]) == 38
        assert info["projection"]["remaining"] == len(info["fixtures"])
        assert info["projection"]["points_low"] <= info["projection"]["points"] <= info["projection"]["points_high"]
        assert all(abs(f["win"] + f["draw"] + f["loss"] - 1) < 1e-3 for f in info["fixtures"])
    scores = {row["model"]: row["log_loss"] for row in model["evaluation"]["overall"]}
    assert scores["Trained model (goals + shots on target)"] < scores["Base rates (home/draw/away frequencies)"]
