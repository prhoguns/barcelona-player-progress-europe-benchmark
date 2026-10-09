"""Season fixture lists from openfootball (CC0), aligned to football-data.co.uk club names.

football-data.co.uk only lists matches already played, so the remaining
schedule comes from openfootball. Club names differ between the two sources;
they are matched automatically from games both sources have scored.
"""
from __future__ import annotations

import difflib
from collections import Counter, defaultdict
from datetime import date

import pandas as pd
import requests

URL = "https://raw.githubusercontent.com/openfootball/football.json/master/{season}/{code}.json"


def final_score(raw: dict) -> list[int] | None:
    """Return [home, away] goals; the source writes some results as a bare list."""
    score = raw.get("score")
    if isinstance(score, dict):
        score = score.get("ft")
    if isinstance(score, list) and len(score) == 2 and all(type(n) is int and n >= 0 for n in score):
        return score
    return None


def fetch(code: str, start_year: int) -> list[dict]:
    season = f"{start_year}-{(start_year + 1) % 100:02d}"
    response = requests.get(URL.format(season=season, code=code), timeout=30)
    response.raise_for_status()
    matches = response.json()["matches"]
    if len(matches) != 380:
        raise ValueError(f"Expected 380 fixtures in openfootball {code} {season}; found {len(matches)}")
    return matches


def _days_apart(a: str, b: str) -> int:
    return abs((date.fromisoformat(a) - date.fromisoformat(b)).days)


def name_map(openfootball: list[dict], played: pd.DataFrame) -> dict[str, str]:
    """openfootball club name -> football-data.co.uk club name."""
    votes: dict[str, Counter] = defaultdict(Counter)
    for raw in openfootball:
        score = final_score(raw)
        if score is None:
            continue
        candidates = played[(played.home_goals == score[0]) & (played.away_goals == score[1])]
        candidates = candidates[[_days_apart(d, raw["date"]) <= 2 for d in candidates.date]]
        for match in candidates.itertuples(index=False):
            votes[raw["team1"]][match.home] += 1
            votes[raw["team2"]][match.away] += 1
    clubs = sorted({raw["team1"] for raw in openfootball} | {raw["team2"] for raw in openfootball})
    targets = sorted(set(played.home) | set(played.away))
    mapping = {club: votes[club].most_common(1)[0][0] for club in clubs if votes[club]}
    unmatched = [t for t in targets if t not in mapping.values()]
    for club in clubs:
        if club not in mapping and unmatched:
            guess = difflib.get_close_matches(club, unmatched, n=1, cutoff=0.0)[0]
            mapping[club] = guess
            unmatched.remove(guess)
    if len(set(mapping.values())) != len(clubs):
        raise ValueError(f"Could not align club names between sources: {mapping}")
    return mapping


def season_fixtures(openfootball: list[dict], played: pd.DataFrame) -> pd.DataFrame:
    """All 380 fixtures with football-data names; results from football-data where played."""
    mapping = name_map(openfootball, played)
    results = {(m.home, m.away): m for m in played.itertuples(index=False)}
    rows = []
    for raw in openfootball:
        home, away = mapping[raw["team1"]], mapping[raw["team2"]]
        result = results.get((home, away))
        rows.append({"round": raw.get("round", ""), "date": result.date if result else raw.get("date", ""),
                     "home": home, "away": away,
                     "home_goals": int(result.home_goals) if result else None,
                     "away_goals": int(result.away_goals) if result else None,
                     "status": "final" if result else "scheduled"})
        source_score = final_score(raw)
        if result and source_score and source_score != [result.home_goals, result.away_goals]:
            raise ValueError(f"Sources disagree on {home} v {away}: {source_score} vs "
                             f"{[result.home_goals, result.away_goals]}")
    fixtures = pd.DataFrame(rows)
    if fixtures.duplicated(["home", "away"]).any():
        raise ValueError("Duplicate home/away pairing in fixture list")
    return fixtures.sort_values(["date", "home"]).reset_index(drop=True)
