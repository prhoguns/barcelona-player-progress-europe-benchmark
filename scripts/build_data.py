"""Fetch public source files into memory and publish only compact derived CSVs.

Usage: python scripts/build_data.py [--workers 8]
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import io
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.analytics import event_clock, goal_team, progressive_pass, role, safe_float

BASE = "https://raw.githubusercontent.com/hudl/open-data/master/data"
CLUBS = {11: ("La Liga", "Barcelona"), 2: ("Premier League", "Arsenal"),
         12: ("Serie A", "Juventus"), 7: ("Ligue 1", "Paris Saint-Germain"),
         9: ("Bundesliga", "Bayer Leverkusen")}
FIELDS = ["match_id", "date", "competition", "club", "opponent", "player_id", "player",
          "role", "position", "minutes", "started", "result", "goals", "assists",
          "xg", "xa", "shots", "passes", "completed_passes", "progressive_passes",
          "final_third_entries", "pressures", "recoveries", "interceptions", "tackles",
          "carries", "progressive_carries", "risk_passes", "reward_passes"]
STATE_FIELDS = ["match_id", "date", "club", "player_id", "player", "role", "state",
                "passes", "progressive_passes", "shots", "xg", "pressures", "recoveries"]
PASS_FIELDS = ["match_id", "date", "club", "player_id", "player", "role", "x_bin", "y_bin", "passes", "completed", "progressive", "risk", "reward", "xa"]

def fetch_json(url: str):
    for attempt in range(4):
        try:
            r = requests.get(url, timeout=45)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError):
            if attempt == 3:
                raise
            time.sleep(1.5 * (attempt + 1))

def fixtures():
    all_matches = []
    for cid, (league, club) in CLUBS.items():
        matches = fetch_json(f"{BASE}/matches/{cid}/27.json")
        selected = [m for m in matches if club in (m["home_team"]["home_team_name"],
                                                m["away_team"]["away_team_name"])]
        print(f"{league}: {len(selected)} {club} fixtures", flush=True)
        for m in selected:
            all_matches.append((m, league, club))
    return all_matches

def process(item):
    match, league, club = item
    events = fetch_json(f"{BASE}/events/{match['match_id']}.json")
    events.sort(key=lambda e: e.get("index", 0))
    match_id = match["match_id"]
    date = match["match_date"]
    home = match["home_team"]["home_team_name"]
    away = match["away_team"]["away_team_name"]
    opponent = away if club == home else home
    club_score = match["home_score"] if club == home else match["away_score"]
    opponent_score = match["away_score"] if club == home else match["home_score"]
    result = "W" if club_score > opponent_score else "D" if club_score == opponent_score else "L"
    end_minute = max((event_clock(e) for e in events if e.get("period") == 2), default=90)
    end_minute = max(90, min(110, end_minute))

    players = {}
    for e in events:
        if e.get("team", {}).get("name") != club or e.get("type", {}).get("name") != "Starting XI":
            continue
        for p in e.get("tactics", {}).get("lineup", []):
            obj = p.get("player", {})
            pos = p.get("position", {}).get("name", "Unknown")
            players[obj["id"]] = {"name": obj["name"], "position": pos, "start": 0.0,
                                   "end": end_minute, "started": 1}

    for e in events:
        if e.get("team", {}).get("name") != club or e.get("type", {}).get("name") != "Substitution":
            continue
        minute = event_clock(e)
        outgoing = e.get("player", {})
        incoming = e.get("substitution", {}).get("replacement", {})
        if outgoing.get("id") in players:
            players[outgoing["id"]]["end"] = minute
        if incoming.get("id"):
            pos = e.get("position", {}).get("name", "Unknown")
            players[incoming["id"]] = {"name": incoming.get("name", "Unknown"),
                                        "position": pos, "start": minute,
                                        "end": end_minute, "started": 0}

    for e in events:
        if e.get("team", {}).get("name") == club and e.get("type", {}).get("name") in ("Bad Behaviour", "Foul Committed"):
            if e.get("bad_behaviour", {}).get("card", {}).get("name") == "Red Card" or e.get("foul_committed", {}).get("card", {}).get("name") in ("Red Card", "Second Yellow"):
                pid = e.get("player", {}).get("id")
                if pid in players:
                    players[pid]["end"] = min(players[pid]["end"], event_clock(e))

    totals = defaultdict(Counter)
    states = defaultdict(Counter)
    passes = []
    score = Counter()
    for e in events:
        team = e.get("team", {}).get("name")
        pid = e.get("player", {}).get("id")
        typ = e.get("type", {}).get("name")
        if team == club and pid in players:
            state = "Leading" if score[club] > score[opponent] else "Trailing" if score[club] < score[opponent] else "Level"
            t, s = totals[pid], states[(pid, state)]
            if typ == "Pass":
                p = e.get("pass", {})
                complete = not p.get("outcome")
                prog = complete and progressive_pass(e.get("location"), p.get("end_location"))
                start, end = e.get("location") or [None, None], p.get("end_location") or [None, None]
                x, y, ex, ey = (start + [None, None])[:2] + (end + [None, None])[:2]
                risk = bool(x is not None and ex is not None and x >= 60 and ex >= 80 and (p.get("through_ball") or ex - x >= 15))
                reward = complete and bool(prog or safe_float(p.get("assisted_shot_id") is not None))
                t["passes"] += 1; s["passes"] += 1
                t["completed_passes"] += int(complete)
                t["progressive_passes"] += int(prog); s["progressive_passes"] += int(prog)
                t["final_third_entries"] += int(complete and x is not None and ex is not None and x < 80 <= ex)
                t["risk_passes"] += int(risk); t["reward_passes"] += int(reward)
                t["assists"] += int(bool(p.get("goal_assist")))
                xa = safe_float(p.get("shot_statsbomb_xg"))
                # StatsBomb xA is attached to the assisted shot, resolved below by id.
                passes.append({"match_id": match_id, "date": date, "club": club, "player_id": pid,
                               "player": players[pid]["name"], "role": role(players[pid]["position"]),
                               "x": x, "y": y, "end_x": ex, "end_y": ey,
                               "completed": int(complete), "progressive": int(prog),
                               "risk": int(risk), "reward": int(reward), "xa": xa,
                               "_event_id": e.get("id"), "_shot_id": p.get("assisted_shot_id")})
            elif typ == "Shot":
                xg = safe_float(e.get("shot", {}).get("statsbomb_xg"))
                t["shots"] += 1; s["shots"] += 1
                t["xg"] += xg; s["xg"] += xg
                t["goals"] += int(e.get("shot", {}).get("outcome", {}).get("name") == "Goal")
            elif typ == "Pressure":
                t["pressures"] += 1; s["pressures"] += 1
            elif typ == "Ball Recovery":
                t["recoveries"] += 1; s["recoveries"] += 1
            elif typ == "Interception":
                t["interceptions"] += 1
            elif typ == "Duel" and e.get("duel", {}).get("type", {}).get("name") == "Tackle":
                t["tackles"] += 1
            elif typ == "Carry":
                t["carries"] += 1
                t["progressive_carries"] += int(progressive_pass(e.get("location"), e.get("carry", {}).get("end_location")))
        scoring_team = goal_team(e)
        if scoring_team == "__opponent__":
            score[opponent if team == club else club] += 1
        elif scoring_team:
            score[scoring_team] += 1

    # The pass's assisted_shot_id points to a Shot event with an xG value.
    shot_xg = {e.get("id"): safe_float(e.get("shot", {}).get("statsbomb_xg"))
               for e in events if e.get("type", {}).get("name") == "Shot"}
    for p in passes:
        if p["_shot_id"] in shot_xg:
            p["xa"] = shot_xg[p["_shot_id"]]
            totals[p["player_id"]]["xa"] += p["xa"]
        del p["_event_id"], p["_shot_id"]

    appearances = []
    for pid, info in players.items():
        minutes = max(0, min(end_minute, info["end"]) - info["start"])
        if minutes < 1:
            continue
        row = {"match_id": match_id, "date": date, "competition": league, "club": club,
               "opponent": opponent, "player_id": pid, "player": info["name"],
               "role": role(info["position"]), "position": info["position"],
               "minutes": round(minutes, 2), "started": info["started"], "result": result}
        row.update({k: round(float(totals[pid][k]), 4) for k in FIELDS if k in totals[pid]})
        appearances.append(row)
    state_rows = []
    for (pid, state), counter in states.items():
        if pid not in players:
            continue
        row = {"match_id": match_id, "date": date, "club": club, "player_id": pid,
               "player": players[pid]["name"], "role": role(players[pid]["position"]), "state": state}
        row.update(counter)
        state_rows.append(row)
    return appearances, state_rows, passes

def write_csv(path, fields, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, 0) for k in fields})

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    out = ROOT / "data" / "derived"
    out.mkdir(parents=True, exist_ok=True)
    selected = fixtures()
    appearances, states, passes = [], [], []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(process, item): item for item in selected}
        for index, future in enumerate(cf.as_completed(futures), 1):
            a, s, p = future.result()
            appearances.extend(a); states.extend(s); passes.extend(p)
            if index % 20 == 0 or index == len(selected):
                print(f"Processed {index}/{len(selected)} matches", flush=True)
    write_csv(out / "appearances.csv", FIELDS, sorted(appearances, key=lambda r:(r['date'],r['club'],r['player_id'])))
    write_csv(out / "game_states.csv", STATE_FIELDS, sorted(states, key=lambda r:(r['date'],r['club'],r['player_id'])))
    # Aggregate spatial cells to avoid redistributing event-level source records.
    zones = {}
    for p in passes:
        if p["x"] is None or p["y"] is None:
            continue
        x_bin = min(5, max(0, int(float(p["x"]) // 20)))
        y_bin = min(3, max(0, int(float(p["y"]) // 20)))
        key = (p["match_id"], p["player_id"], x_bin, y_bin)
        if key not in zones:
            zones[key] = {k: p[k] for k in ("match_id", "date", "club", "player_id", "player", "role")}
            zones[key].update({"x_bin": x_bin, "y_bin": y_bin, "passes": 0,
                               "completed": 0, "progressive": 0, "risk": 0, "reward": 0, "xa": 0.0})
        z = zones[key]
        z["passes"] += 1
        for k in ("completed", "progressive", "risk", "reward", "xa"):
            z[k] += p[k]
    write_csv(out / "pass_zones.csv", PASS_FIELDS, zones.values())
    manifest = {"source": "StatsBomb Open Data", "season": "2015/2016", "season_id": 27,
                "clubs": CLUBS, "match_count": len(selected), "appearance_rows": len(appearances),
                "pass_events_processed": len(passes), "pass_zone_rows": len(zones), "coverage": "All published fixtures for each selected club; Bundesliga contains only Bayer Leverkusen's 34 matches in source catalog.",
                "source_url": "https://github.com/hudl/open-data", "demo": True}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))

if __name__ == "__main__":
    main()
