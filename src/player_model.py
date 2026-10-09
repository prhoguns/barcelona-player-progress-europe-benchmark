"""Player league-goal forecasts: each scorer's share of the club's goals, shrunk toward a prior.

A player's final total = goals so far + (share of club goals) x (club goals the
team model still expects). The share is an empirical-Bayes estimate:

    share = (player goals + k * prior) / (club goals + k)

where the prior blends the player's share for the same club last season with a
league-wide baseline. k, the blend weight and the baseline are fitted on past
seasons by minimising the absolute error of final totals.
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd
from scipy.stats import nbinom

CHECKPOINTS = (7, 19, 28)
GRID = {"strength": (4, 8, 12, 16, 24, 32, 48, 64, 96), "weight": (0.0, 0.25, 0.5, 0.75, 1.0),
        "baseline": (0.0, 0.005, 0.01, 0.02, 0.04, 0.06, 0.08)}


def valid_club_seasons(coverage: pd.DataFrame) -> set[tuple]:
    """Club seasons where every played league match was found on Wikipedia with complete scorers."""
    ok = coverage.groupby(["league", "season", "club"]).complete.all()
    return set(ok[ok].index)


def previous_shares(events: pd.DataFrame, coverage: pd.DataFrame, valid: set[tuple]) -> dict[tuple, dict]:
    """(league, season, club) -> {player_id: share of club league goals in the season before}."""
    league = events[(events.competition == "league") & ~events.own_goal]
    goals = coverage.groupby(["league", "season", "club"]).goals.sum()
    shares = {}
    for key, frame in league.groupby(["league", "season", "club"]):
        if key in valid and goals[key] > 0:
            counts = frame.groupby("player_id").size() / goals[key]
            shares[(key[0], key[1] + 1, key[2])] = counts.to_dict()
    return shares


def checkpoint_rows(events: pd.DataFrame, coverage: pd.DataFrame, key: tuple, k: int,
                    prior: dict, remaining_goals: float, final: bool) -> pd.DataFrame:
    """One row per player who has scored by the club's k-th league match."""
    matches = coverage.sort_values("date")
    dates = matches.date.iloc[:k]
    club_goals = int(matches.goals.iloc[:k].sum())
    league = events[(events.competition == "league") & ~events.own_goal & (events.player_id != "")]
    so_far = league[league.date.isin(set(dates))].groupby(["player_id", "player"]).size()
    if so_far.empty:
        return pd.DataFrame()
    rows = pd.DataFrame({"player_id": so_far.index.get_level_values(0),
                         "player": so_far.index.get_level_values(1), "goals": so_far.to_numpy()})
    rows = rows.groupby("player_id", as_index=False).agg(player=("player", "first"), goals=("goals", "sum"))
    rows["previous_share"] = rows.player_id.map(prior).astype(float)
    rows["club_goals"], rows["matches_played"], rows["remaining_goals"] = club_goals, k, remaining_goals
    rows["league"], rows["season"], rows["club"] = key
    if final:
        totals = league.groupby("player_id").size()
        rows["actual"] = rows.player_id.map(totals).fillna(0).astype(int)
    return rows


def predict(rows: pd.DataFrame, params: dict) -> np.ndarray:
    """Expected remaining league goals for each row."""
    prior = np.where(rows.previous_share.notna(),
                     params["weight"] * rows.previous_share.fillna(0) + (1 - params["weight"]) * params["baseline"],
                     params["baseline"])
    share = (rows.goals + params["strength"] * prior) / (rows.club_goals + params["strength"])
    return share.to_numpy() * rows.remaining_goals.to_numpy()


def fit(rows: pd.DataFrame) -> dict:
    """Grid search for the parameters with the lowest mean absolute final-total error."""
    best = None
    for strength, weight, baseline in itertools.product(*GRID.values()):
        params = {"strength": strength, "weight": weight, "baseline": baseline}
        error = np.abs(rows.goals + predict(rows, params) - rows.actual).mean()
        if best is None or error < best[0]:
            best = (error, params)
    params = best[1]
    expected = predict(rows, params)
    remaining = rows.actual - rows.goals
    excess = ((remaining - expected) ** 2 - expected).sum()
    params["dispersion"] = float(max(0.0, excess / (expected ** 2).sum()))
    return params


def interval(expected: np.ndarray, dispersion: float, q: float) -> np.ndarray:
    if dispersion <= 0:
        dispersion = 1e-6
    size = 1 / dispersion
    return nbinom.ppf(q, size, size / (size + np.maximum(expected, 1e-9)))


def forecast(rows: pd.DataFrame, params: dict) -> pd.DataFrame:
    expected = predict(rows, params)
    out = rows.copy()
    out["projected"] = rows.goals + expected
    out["low"] = rows.goals + interval(expected, params["dispersion"], 0.10)
    out["high"] = rows.goals + interval(expected, params["dispersion"], 0.90)
    return out


def evaluate(rows: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Error by checkpoint against two baselines: keep current pace, and score no more."""
    out = forecast(rows, params)
    out["model_error"] = (out.projected - out.actual).abs()
    out["pace_error"] = (out.goals * 38 / out.matches_played - out.actual).abs()
    out["stop_error"] = (out.goals - out.actual).abs()
    out["covered"] = out.actual.between(out.low, out.high)
    return out.groupby("matches_played").agg(
        model_mae=("model_error", "mean"), pace_mae=("pace_error", "mean"),
        no_more_goals_mae=("stop_error", "mean"), coverage=("covered", "mean"),
        players=("model_error", "size")).reset_index()
