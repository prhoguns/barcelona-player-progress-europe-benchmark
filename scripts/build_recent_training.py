"""Build compact 2023/24 Leverkusen player-match training rows from StatsBomb.

Source event JSON is read in memory and never saved. This is a historical
training panel, not Barcelona 2026/27 observations.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
from pathlib import Path

from build_data import BASE, FIELDS, fetch_json, process, write_csv

ROOT = Path(__file__).resolve().parents[1]
COMPETITION_ID, SEASON_ID = 9, 281
CLUB = "Bayer Leverkusen"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    if not 1 <= args.workers <= 12:
        parser.error("--workers must be between 1 and 12")
    matches = fetch_json(f"{BASE}/matches/{COMPETITION_ID}/{SEASON_ID}.json")
    selected = [m for m in matches if CLUB in (
        m["home_team"]["home_team_name"], m["away_team"]["away_team_name"])]
    if len(selected) != 34 or len({m["match_id"] for m in selected}) != 34:
        raise ValueError(f"Expected 34 distinct Leverkusen league matches; found {len(selected)}")
    appearances = []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for index, (rows, _, _) in enumerate(pool.map(process, ((m, "Bundesliga", CLUB) for m in selected)), 1):
            appearances.extend(rows)
            if index % 10 == 0 or index == len(selected):
                print(f"Processed {index}/34 matches", flush=True)
    out = ROOT / "data" / "training"
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "leverkusen_2023_24_appearances.csv", FIELDS,
              sorted(appearances, key=lambda r: (r["date"], r["player_id"])))
    manifest = {
        "source": "StatsBomb Open Data", "source_url": "https://github.com/hudl/open-data",
        "competition": "Men's Bundesliga", "season": "2023/2024", "club": CLUB,
        "competition_id": COMPETITION_ID, "season_id": SEASON_ID,
        "matches": len(selected), "appearance_rows": len(appearances),
        "use": "historical forecast training only", "current_barcelona_data": False,
        "raw_events_redistributed": False,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
