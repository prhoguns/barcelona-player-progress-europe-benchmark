"""Build compact CC0 La Liga team-score summaries for the team forecast."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "current" / "team_forecast.json"
BASE = "https://raw.githubusercontent.com/openfootball/football.json/master"


def summarize(matches: list[dict], cutoff: date) -> dict:
    teams = defaultdict(lambda: {"games": 0, "gf": 0, "ga": 0})
    totals = {"matches": 0, "home_goals": 0, "away_goals": 0}
    for match in matches:
        raw = match.get("score")
        score = raw.get("ft") if isinstance(raw, dict) else None
        if not (isinstance(score, list) and len(score) == 2
                and all(type(goal) is int and goal >= 0 for goal in score)):
            continue
        if date.fromisoformat(match["date"]) > cutoff:
            continue
        home, away = match["team1"], match["team2"]
        hg, ag = score
        teams[home]["games"] += 1; teams[home]["gf"] += hg; teams[home]["ga"] += ag
        teams[away]["games"] += 1; teams[away]["gf"] += ag; teams[away]["ga"] += hg
        totals["matches"] += 1; totals["home_goals"] += hg; totals["away_goals"] += ag
    return {"totals": totals, "teams": dict(sorted(teams.items()))}


def main() -> None:
    seasons = {}
    for season in ("2025-26", "2026-27"):
        url = f"{BASE}/{season}/es.1.json"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        rows = response.json()["matches"]
        if len(rows) != 380:
            raise ValueError(f"Expected 380 {season} La Liga fixtures; found {len(rows)}")
        seasons[season] = summarize(rows, date.today())
        seasons[season]["source_url"] = url
    if seasons["2025-26"]["totals"]["matches"] < 300:
        raise ValueError("Prior season has too few results for a baseline")
    payload = {
        "source": "openfootball/football.json", "license": "CC0-1.0",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": "aggregated completed La Liga scores; missing 2025/26 results excluded",
        "seasons": seasons,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print({s: value["totals"]["matches"] for s, value in seasons.items()})


if __name__ == "__main__":
    main()
