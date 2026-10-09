"""Club season totals (points, goals for, goals against) from the trained match model."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import pandas as pd

from src import match_model as mm

CHECKPOINTS = (0, 7, 19, 28)
DISPERSION_FRACTIONS = (0.0, 0.25, 0.5, 0.75)


def day_before(iso: str) -> str:
    return (date.fromisoformat(iso) - timedelta(days=1)).isoformat()


def fixture_forecasts(ratings: mm.Ratings, model: mm.MatchModel, fixtures: pd.DataFrame, club: str) -> pd.DataFrame:
    """Win/draw/loss and expected goals for each unplayed club fixture (columns: home, away)."""
    out = fixtures.copy().reset_index(drop=True)
    if out.empty:
        return out.assign(win=[], draw=[], loss=[], xg_for=[], xg_against=[])
    pairs = [ratings.features(h, a) for h, a in zip(out.home, out.away)]
    lam, mu = model.goal_rates(pd.DataFrame([p[0] for p in pairs]), pd.DataFrame([p[1] for p in pairs]))
    probs = mm.outcome_probabilities(lam, mu, model.rho)
    home = (out.home == club).to_numpy()
    out["win"] = np.where(home, probs[:, 0], probs[:, 2])
    out["draw"] = probs[:, 1]
    out["loss"] = np.where(home, probs[:, 2], probs[:, 0])
    out["xg_for"] = np.where(home, lam, mu)
    out["xg_against"] = np.where(home, mu, lam)
    return out


def club_record(matches: pd.DataFrame, club: str) -> dict:
    home = (matches.home == club).to_numpy()
    goals_for = np.where(home, matches.home_goals, matches.away_goals)
    goals_against = np.where(home, matches.away_goals, matches.home_goals)
    points = np.where(goals_for > goals_against, 3, np.where(goals_for == goals_against, 1, 0))
    return {"played": int(len(matches)), "points": int(points.sum()),
            "wins": int((points == 3).sum()), "draws": int((points == 1).sum()), "losses": int((points == 0).sum()),
            "goals_for": int(goals_for.sum()), "goals_against": int(goals_against.sum())}


def totals(observed: dict, upcoming: pd.DataFrame, model: mm.MatchModel,
           low_q: float = 0.10, high_q: float = 0.90, draws: int = 4000) -> dict:
    """Combine observed totals with the forecast distribution of the remaining fixtures.

    Means come straight from the match probabilities. Ranges come from simulated seasons in
    which the club's attack and defence each drift by a gamma-distributed factor whose variance
    (the model's goal dispersion) was measured on past seasons, so they include the risk that
    the club is stronger or weaker than its current rating.
    """
    xg_for, xg_against = upcoming.xg_for.to_numpy(float), upcoming.xg_against.to_numpy(float)
    rng = np.random.default_rng(0)
    k = max(model.goal_dispersion, 1e-6)
    attack = rng.gamma(1 / k, k, size=(draws, 1))
    defence = rng.gamma(1 / k, k, size=(draws, 1))
    scored = rng.poisson(attack * xg_for[None, :])
    conceded = rng.poisson(defence * xg_against[None, :])
    points = np.where(scored > conceded, 3, np.where(scored == conceded, 1, 0)).sum(axis=1)
    quantile = lambda values, q: int(np.quantile(values, q, method="inverted_cdf")) if len(xg_for) else 0
    return {
        "points": observed["points"] + float((3 * upcoming.win + upcoming.draw).sum()),
        "points_low": observed["points"] + quantile(points, low_q),
        "points_high": observed["points"] + quantile(points, high_q),
        "goals_for": observed["goals_for"] + float(xg_for.sum()),
        "goals_for_low": observed["goals_for"] + quantile(scored.sum(axis=1), low_q),
        "goals_for_high": observed["goals_for"] + quantile(scored.sum(axis=1), high_q),
        "goals_against": observed["goals_against"] + float(xg_against.sum()),
        "goals_against_low": observed["goals_against"] + quantile(conceded.sum(axis=1), low_q),
        "goals_against_high": observed["goals_against"] + quantile(conceded.sum(axis=1), high_q),
        "remaining": int(len(upcoming)),
    }


def dispersion_requests(history: pd.DataFrame, seasons: list[int]) -> dict[tuple[int, str], pd.DataFrame]:
    """Checkpoints through past seasons, each with the league matches still to play."""
    out = {}
    for season in seasons:
        league = history[history.season == season].sort_values(["date", "home"]).reset_index(drop=True)
        for fraction in DISPERSION_FRACTIONS:
            k = int(round(fraction * len(league)))
            cutoff = day_before(league.date.iloc[0]) if k == 0 else league.date.iloc[k - 1]
            out[(season, cutoff)] = league[league.date > cutoff]
    return out


def frozen_remaining(snapshots: dict, requests: dict[tuple[int, str], pd.DataFrame]) -> pd.DataFrame:
    """Feature rows for every club's remaining fixtures, with ratings frozen at each checkpoint.

    Season forecasts freeze ratings at a cutoff, so their uncertainty includes how much team
    strength drifts afterwards. These rows measure that drift on past seasons.
    """
    rows = []
    for (season, cutoff), remaining in requests.items():
        ratings = snapshots[(season, cutoff)]
        for match in remaining.itertuples(index=False):
            home_x, away_x = ratings.features(match.home, match.away)
            rows.append({"season": season, "cutoff": cutoff, "team": match.home, **home_x, "goals": match.home_goals})
            rows.append({"season": season, "cutoff": cutoff, "team": match.away, **away_x, "goals": match.away_goals})
    return pd.DataFrame(rows)


def season_dispersion(model: mm.MatchModel, frozen: pd.DataFrame) -> float:
    """Extra-Poisson variance k of remaining-season goal totals (variance = m + k*m^2)."""
    frozen = frozen.assign(expected=model.predict_goals(frozen))
    team_totals = frozen.groupby(["season", "cutoff", "team"])[["goals", "expected"]].sum()
    excess = ((team_totals.goals - team_totals.expected) ** 2 - team_totals.expected).sum()
    return float(max(0.0, excess / (team_totals.expected ** 2).sum()))


def fit_for_season(features: pd.DataFrame, frozen: pd.DataFrame, params: dict, season: int) -> mm.MatchModel:
    """Train on seasons before `season` only, including the goal-total dispersion."""
    train = features[(features.season >= params["train_from"]) & (features.season < season)]
    model = mm.fit(train, mm.FULL, params["learner"])
    return replace(model, goal_dispersion=season_dispersion(model, frozen[frozen.season < season]))


def club_matches(history: pd.DataFrame, season: int, club: str) -> pd.DataFrame:
    played = history[(history.season == season) & ((history.home == club) | (history.away == club))]
    return played.sort_values("date").reset_index(drop=True)


def checkpoint_cutoff(played: pd.DataFrame, k: int) -> str:
    return day_before(played.date.iloc[0]) if k == 0 else played.date.iloc[k - 1]


def backtest_requests(history: pd.DataFrame, seasons: list[int]) -> set[tuple[int, str]]:
    requests = set()
    for season in seasons:
        for club in set(history[history.season == season].home):
            played = club_matches(history, season, club)
            requests |= {(season, checkpoint_cutoff(played, k)) for k in CHECKPOINTS}
    return requests


def backtest(history: pd.DataFrame, models: dict[int, mm.MatchModel], snapshots: dict,
             seasons: list[int]) -> pd.DataFrame:
    """Every club's season forecast as it would have looked at each checkpoint of past seasons."""
    rows = []
    for season in seasons:
        model = models[season]
        for club in sorted(set(history[history.season == season].home)):
            played = club_matches(history, season, club)
            final = club_record(played, club)
            previous = club_matches(history, season - 1, club)
            for k in CHECKPOINTS:
                ratings = snapshots[(season, checkpoint_cutoff(played, k))]
                upcoming = fixture_forecasts(ratings, model, played.iloc[k:][["home", "away"]], club)
                observed = club_record(played.iloc[:k], club)
                forecast = totals(observed, upcoming, model)
                if k:
                    naive_points, naive_goals = observed["points"] * 38 / k, observed["goals_for"] * 38 / k
                elif len(previous):
                    last = club_record(previous, club)
                    naive_points, naive_goals = last["points"], last["goals_for"]
                else:
                    naive_points = naive_goals = float("nan")
                rows.append({"season": season, "club": club, "matches_played": k,
                             **{f"forecast_{key}": value for key, value in forecast.items()},
                             "observed_points": observed["points"], "observed_goals_for": observed["goals_for"],
                             "actual_points": final["points"], "actual_goals_for": final["goals_for"],
                             "actual_goals_against": final["goals_against"],
                             "naive_points": naive_points, "naive_goals_for": naive_goals})
    return pd.DataFrame(rows)


def summarize_backtest(results: pd.DataFrame) -> pd.DataFrame:
    """Error and 80%-range coverage by checkpoint, against the naive baseline."""
    frame = results.assign(
        error=(results.forecast_points - results.actual_points).abs(),
        naive_error=(results.naive_points - results.actual_points).abs(),
        goals_error=(results.forecast_goals_for - results.actual_goals_for).abs(),
        naive_goals_error=(results.naive_goals_for - results.actual_goals_for).abs(),
        covered=results.actual_points.between(results.forecast_points_low, results.forecast_points_high),
        goals_covered=results.actual_goals_for.between(results.forecast_goals_for_low,
                                                        results.forecast_goals_for_high))
    return frame.groupby("matches_played").agg(
        points_mae=("error", "mean"), naive_points_mae=("naive_error", "mean"),
        goals_mae=("goals_error", "mean"), naive_goals_mae=("naive_goals_error", "mean"),
        points_coverage=("covered", "mean"), goals_coverage=("goals_covered", "mean"),
        forecasts=("error", "size")).reset_index()
