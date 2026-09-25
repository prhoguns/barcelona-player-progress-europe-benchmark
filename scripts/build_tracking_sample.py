"""Stream a short, separate SkillCorner sample; never retain raw tracking files."""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
MATCH_ID = 1886347
BASE = f"https://raw.githubusercontent.com/SkillCorner/opendata/master/data/matches/{MATCH_ID}"
TRACK = f"https://media.githubusercontent.com/media/SkillCorner/opendata/master/data/matches/{MATCH_ID}/{MATCH_ID}_tracking_extrapolated.jsonl"

def main():
    meta = requests.get(f"{BASE}/{MATCH_ID}_match.json", timeout=30).json()
    home_id = meta["home_team"]["id"]
    players = [p for p in meta["players"] if p.get("team_id") == home_id
               and p.get("player_role", {}).get("position_group") != "Goalkeeper"][:6]
    ids = {p["id"]: f"Sample player {i + 1}" for i, p in enumerate(players)}
    rows, last = [], {}
    with requests.get(TRACK, stream=True, timeout=60) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line:
                continue
            frame = json.loads(line)
            if frame["frame"] > 6010:
                break
            if frame["frame"] % 20 != 10 or frame.get("period") != 1:
                continue
            second = (frame["frame"] - 10) / 10
            for point in frame.get("player_data", []):
                pid = point.get("player_id")
                if pid not in ids or not point.get("is_detected"):
                    continue
                x, y = point.get("x"), point.get("y")
                if x is None or y is None:
                    continue
                previous = last.get(pid)
                step = 0.0
                if previous and second > previous[0]:
                    speed = math.dist((x, y), previous[1:]) / (second - previous[0])
                    if speed <= 10:
                        step = math.dist((x, y), previous[1:])
                last[pid] = (second, x, y)
                rows.append({"sample_player": ids[pid], "second": second, "x_m": round(x, 2),
                             "y_m": round(y, 2), "distance_step_m": round(step, 2)})
    out = ROOT / "data" / "derived"
    out.mkdir(parents=True, exist_ok=True)
    with (out / "tracking_sample.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["sample_player", "second", "x_m", "y_m", "distance_step_m"])
        writer.writeheader(); writer.writerows(rows)
    (out / "tracking_manifest.json").write_text(json.dumps({
        "source": "SkillCorner Open Data", "match_id": MATCH_ID,
        "match": f"{meta['home_team']['name']} vs {meta['away_team']['name']}",
        "date": meta["date_time"][:10], "competition": meta["competition_edition"]["competition"]["name"],
        "sample_seconds": 600, "sample_players": list(ids.values()), "rows": len(rows),
        "notice": "Separate tracking demonstration; not Barcelona or the 2015/16 StatsBomb fixtures.",
        "source_url": "https://github.com/SkillCorner/opendata", "demo": True
    }, indent=2) + "\n")
    print(f"Wrote {len(rows)} derived tracking points")

if __name__ == "__main__":
    main()
