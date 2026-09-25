"""Transparent fixture-by-fixture La Liga team-points projection."""
from __future__ import annotations

from math import exp, factorial

import numpy as np

CLUB = "FC Barcelona"
PRIOR_GAMES = 20.0
NEW_CLUB_PRIOR_GAMES = 8.0


def _rate(team: str, field: str, previous: dict, current: dict, league_average: float) -> float:
    past = previous["teams"].get(team)
    now = current["teams"].get(team, {"games": 0, "gf": 0, "ga": 0})
    prior_games = PRIOR_GAMES if past and past["games"] >= 20 else NEW_CLUB_PRIOR_GAMES
    prior_rate = past[field] / past["games"] if past and past["games"] >= 20 else league_average
    return (prior_games * prior_rate + now[field]) / (prior_games + now["games"])


def _poisson(lam: float) -> np.ndarray:
    # The last cell contains the 10+ goal tail so the probabilities sum to one.
    values = [exp(-lam) * lam ** goals / factorial(goals) for goals in range(10)]
    return np.array(values + [max(0.0, 1.0 - sum(values))])


def _outcome(home_goals: float, away_goals: float, barca_home: bool) -> tuple[float, float, float]:
    joint = np.outer(_poisson(home_goals), _poisson(away_goals))
    home_win = float(np.tril(joint, -1).sum())
    draw = float(np.trace(joint))
    away_win = float(np.triu(joint, 1).sum())
    return (home_win, draw, away_win) if barca_home else (away_win, draw, home_win)


def forecast(fixtures: list[dict], seasons: dict) -> dict:
    previous, current = seasons["2025-26"], seasons["2026-27"]
    finished = [row for row in fixtures if row["status"] == "final"]
    scored = sum(row["home_goals"] if row["home"] == CLUB else row["away_goals"]
                 for row in finished)
    conceded = sum(row["away_goals"] if row["home"] == CLUB else row["home_goals"]
                   for row in finished)
    current_barca = current["teams"].get(CLUB, {})
    if (len(fixtures) != 38 or current_barca.get("games") != len(finished)
            or current_barca.get("gf") != scored or current_barca.get("ga") != conceded):
        raise ValueError("League score summary and Barcelona fixtures are out of sync; refresh both")
    prev_totals = previous["totals"]
    league_average = (prev_totals["home_goals"] + prev_totals["away_goals"]) / (2 * prev_totals["matches"])
    home_base = prev_totals["home_goals"] / prev_totals["matches"]
    away_base = prev_totals["away_goals"] / prev_totals["matches"]
    expected = 0.0
    observed = 0
    for fixture in fixtures:
        if fixture["status"] != "final":
            continue
        barca_home = fixture["home"] == CLUB
        goals_for = fixture["home_goals"] if barca_home else fixture["away_goals"]
        goals_against = fixture["away_goals"] if barca_home else fixture["home_goals"]
        observed += 3 if goals_for > goals_against else 1 if goals_for == goals_against else 0
    distribution = np.array([1.0])
    projected = []
    for fixture in sorted(fixtures, key=lambda m: (m["date"], m.get("time", ""), m["round"])):
        barca_home = fixture["home"] == CLUB
        opponent = fixture["away"] if barca_home else fixture["home"]
        if fixture["status"] == "final":
            continue
        home, away = fixture["home"], fixture["away"]
        home_goals = home_base * _rate(home, "gf", previous, current, league_average) / league_average \
            * _rate(away, "ga", previous, current, league_average) / league_average
        away_goals = away_base * _rate(away, "gf", previous, current, league_average) / league_average \
            * _rate(home, "ga", previous, current, league_average) / league_average
        home_goals = float(np.clip(home_goals, 0.15, 4.5))
        away_goals = float(np.clip(away_goals, 0.15, 4.5))
        win, draw, loss = _outcome(home_goals, away_goals, barca_home)
        mean = 3 * win + draw
        expected += mean
        distribution = np.convolve(distribution, np.array([loss, draw, 0.0, win]))
        projected.append({
            "round": fixture["round"], "date": fixture["date"], "opponent": opponent,
            "venue": "Home" if barca_home else "Away", "win": win, "draw": draw,
            "loss": loss, "expected_points": mean, "projected_total": observed + expected,
        })
    cdf = np.cumsum(distribution)
    low = observed + int(np.searchsorted(cdf, 0.10))
    high = observed + int(np.searchsorted(cdf, 0.90))
    return {"observed_points": observed, "remaining": len(projected),
            "expected_final_points": observed + expected, "low": low, "high": high,
            "fixtures": projected, "prior_result_coverage": prev_totals["matches"],
            "current_result_coverage": current["totals"]["matches"]}
