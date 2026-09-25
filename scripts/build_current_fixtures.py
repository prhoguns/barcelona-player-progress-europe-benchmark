"""Refresh the public-domain 2026/27 Barcelona La Liga fixture snapshot."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import requests

SOURCE = "https://raw.githubusercontent.com/openfootball/football.json/master/2026-27/es.1.json"
OUT = Path(__file__).resolve().parents[1] / "data" / "current" / "fixtures.json"
CLUB = "FC Barcelona"


def normalize_matches(payload: dict) -> list[dict]:
    matches = []
    for raw in payload.get("matches", []):
        home, away = raw.get("team1"), raw.get("team2")
        if CLUB not in (home, away):
            continue
        score = raw.get("score", {}).get("ft")
        final = isinstance(score, list) and len(score) == 2 and all(isinstance(n, int) for n in score)
        matches.append({
            "round": raw.get("round", ""), "date": raw.get("date", ""),
            "time": raw.get("time", ""), "home": home, "away": away,
            "home_goals": score[0] if final else None,
            "away_goals": score[1] if final else None,
            "status": "final" if final else "scheduled",
        })
    matches.sort(key=lambda m: (m["date"], m["time"], m["round"]))
    if len(matches) != 38 or len({m["round"] for m in matches}) != 38:
        raise ValueError("Expected 38 distinct Barcelona La Liga matchdays; source coverage changed")
    return matches


def main() -> None:
    response = requests.get(SOURCE, timeout=30)
    response.raise_for_status()
    matches = normalize_matches(response.json())
    result = {
        "season": "2026/27", "competition": "La Liga", "club": CLUB,
        "status": "current-season fixture and result snapshot; not live player event data",
        "source": "openfootball/football.json", "source_url": SOURCE,
        "license": "CC0-1.0", "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "matches": matches,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(matches)} fixtures; {sum(m['status'] == 'final' for m in matches)} finals")


if __name__ == "__main__":
    main()
