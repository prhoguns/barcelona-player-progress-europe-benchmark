"""Goal scorers from English Wikipedia club season pages (CC BY-SA 4.0).

Each "<season> <club> season" article lists matches in football box templates
with scorers and minutes. A league match is accepted only when its score agrees
with football-data.co.uk and the listed scorers (plus own goals) add up to the
club's goals, so incomplete pages are detected instead of silently undercounting.
"""
from __future__ import annotations

import re
import time

import pandas as pd
import requests

API = "https://en.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": "BarcaPlayerLab/1.0 (https://github.com/prhoguns/barcelona-player-progress-europe-benchmark)"}
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                       "september", "october", "november", "december"], 1)}
LINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]+))?\]\]")
GOAL = re.compile(r"\{\{\s*goal\s*\|([^{}]*)\}\}", re.I)


def page_title(start_year: int, article: str) -> str:
    return f"{start_year}–{(start_year + 1) % 100:02d} {article} season"


def fetch_pages(titles: list[str], batch: int = 10, pause: float = 1.0) -> dict[str, str | None]:
    """Raw wikitext for each title (None when the page does not exist), following redirects."""
    pages: dict[str, str | None] = {}
    for start in range(0, len(titles), batch):
        chunk = titles[start:start + batch]
        params = {"action": "query", "titles": "|".join(chunk), "prop": "revisions", "rvprop": "content",
                  "rvslots": "main", "format": "json", "formatversion": 2, "redirects": 1, "maxlag": 5}
        while True:
            response = requests.get(API, params=params, headers=HEADERS, timeout=60)
            response.raise_for_status()
            payload = response.json()
            aliases = {r["to"]: r["from"] for r in payload["query"].get("redirects", [])}
            aliases.update({n["to"]: n["from"] for n in payload["query"].get("normalized", [])})
            for page in payload["query"]["pages"]:
                title = aliases.get(page["title"], page["title"])
                if page.get("missing"):
                    pages[title] = None
                elif "revisions" in page:
                    pages[title] = page["revisions"][0]["slots"]["main"]["content"]
            if "continue" not in payload:
                break
            params.update(payload["continue"])
        time.sleep(pause)
    return pages


def _template_end(text: str, start: int) -> int:
    depth, i = 0, start
    while i < len(text) - 1:
        pair = text[i:i + 2]
        if pair == "{{":
            depth, i = depth + 1, i + 2
        elif pair == "}}":
            depth, i = depth - 1, i + 2
            if depth == 0:
                return i
        else:
            i += 1
    return len(text)


def _parse_date(value: str) -> str | None:
    match = re.search(r"start date\s*\|\s*(\d{4})\s*\|\s*(\d{1,2})\s*\|\s*(\d{1,2})", value, re.I)
    if match:
        y, m, d = map(int, match.groups())
        return f"{y:04d}-{m:02d}-{d:02d}"
    match = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", value)
    if match and match.group(2).lower() in MONTHS:
        return f"{int(match.group(3)):04d}-{MONTHS[match.group(2).lower()]:02d}-{int(match.group(1)):02d}"
    match = re.search(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", value)
    if match and match.group(1).lower() in MONTHS:
        return f"{int(match.group(3)):04d}-{MONTHS[match.group(1).lower()]:02d}-{int(match.group(2)):02d}"
    return None


def match_boxes(text: str) -> list[dict]:
    """Every football box on the page with date, score, both scorer fields and section heading."""
    text = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", text, flags=re.S)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    headings = [(m.start(), m.group(2).strip()) for m in re.finditer(r"^(={2,3})\s*([^=].*?)\s*\1\s*$", text, re.M)]
    boxes = []
    for found in re.finditer(r"\{\{\s*(?:#invoke:\s*)?football\s*box", text, re.I):
        body = text[found.start():_template_end(text, found.start())]
        params = {m.group(1).lower(): m.group(2).strip()
                  for m in re.finditer(r"^\s*\|\s*(\w+)\s*=(.*?)(?=^\s*\|\s*\w+\s*=|\}\}\s*\Z)", body, re.M | re.S)}
        score = re.search(r"(\d+)\s*[–\-−]\s*(\d+)", re.sub(LINK, lambda m: m.group(2) or m.group(1), params.get("score", "")))
        section = [h for pos, h in headings if pos < found.start()]
        boxes.append({"date": _parse_date(params.get("date", "")), "team1": params.get("team1", ""),
                      "team2": params.get("team2", ""), "goals1": params.get("goals1", ""),
                      "goals2": params.get("goals2", ""),
                      "score": (int(score.group(1)), int(score.group(2))) if score else None,
                      "section": section[-1] if section else ""})
    return boxes


def _player(entry: str) -> tuple[str, str] | None:
    before = entry.split("{{")[0] if not entry.lstrip("*: ").startswith("{{") else entry
    for target, label in LINK.findall(before):
        if not target.lower().startswith(("file:", "image:")):
            name = re.sub(r"\s*\(.*?\)\s*$", "", target)
            return target.strip(), name.strip()
    plain = re.sub(r"\{\{.*?\}\}|'''?|[*:]", "", before).strip()
    return (plain, plain) if plain else None


def goal_events(field: str) -> list[dict]:
    """Scorers in one box field; own goals are flagged rather than credited to a player."""
    events = []
    for entry in re.split(r"<br\s*/?>|\n", field):
        goals = GOAL.findall(entry)
        if not goals:
            continue
        player = _player(entry)
        for params in goals:
            # Minutes are normally followed by a (possibly empty) modifier, but editors
            # often drop the empty one, so read tokens in order instead of in pairs.
            for token in (p.strip() for p in params.split("|")):
                if re.match(r"^\d+(\+\d+)?$", token):
                    events.append({"player_id": player[0] if player else "",
                                   "player": player[1] if player else "",
                                   "minute": token, "penalty": False, "own_goal": False})
                elif token and events and "=" not in token:
                    events[-1]["penalty"] |= "pen" in token.lower()
                    events[-1]["own_goal"] |= "o.g" in token.lower()
    return events


def _plain_side(team1: str, team2: str) -> int | None:
    """The page's own club is usually the unlinked team in its boxes."""
    linked1, linked2 = bool(LINK.search(team1)), bool(LINK.search(team2))
    if linked1 != linked2:
        return 2 if linked1 else 1
    return None


def club_season(text: str, club: str, league_matches: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validated league scorers plus reported scorers in other competitions for one club season.

    `league_matches` holds the club's football-data.co.uk league matches for that season.
    Returns (goal events, league match coverage).
    """
    boxes = [b for b in match_boxes(text) if b["date"] and b["score"]]
    used, events, coverage = set(), [], []
    for match in league_matches.itertuples(index=False):
        home = match.home == club
        found = None
        for i, box in enumerate(boxes):
            if i in used or box["score"] != (match.home_goals, match.away_goals):
                continue
            if abs(pd.Timestamp(box["date"]) - pd.Timestamp(match.date)).days <= 1:
                found = i
                break
        club_goals = match.home_goals if home else match.away_goals
        record = {"date": match.date, "opponent": match.away if home else match.home,
                  "venue": "Home" if home else "Away", "goals": int(club_goals), "found": found is not None,
                  "complete": False}
        if found is not None:
            used.add(found)
            side = goal_events(boxes[found]["goals1" if home else "goals2"])
            record["complete"] = len(side) == club_goals and all(e["player"] or e["own_goal"] for e in side)
            for event in side:
                events.append({**event, "date": match.date, "opponent": record["opponent"],
                               "competition": "league", "validated": record["complete"]})
        coverage.append(record)
    for i, box in enumerate(boxes):
        side = _plain_side(box["team1"], box["team2"])
        if i in used or side is None:
            continue
        opponent = LINK.sub(lambda m: m.group(2) or m.group(1), box[f"team{3 - side}"]).strip()
        for event in goal_events(box[f"goals{side}"]):
            events.append({**event, "date": box["date"], "opponent": opponent,
                           "competition": box["section"] or "other", "validated": False})
    columns = ["date", "opponent", "competition", "player_id", "player", "minute", "penalty", "own_goal", "validated"]
    return pd.DataFrame(events, columns=columns), pd.DataFrame(coverage)
