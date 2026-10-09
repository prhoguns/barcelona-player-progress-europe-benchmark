"""League match results and team match stats from football-data.co.uk.

The site publishes one CSV per season (results, shots, cards, corners, closing
odds and, from 2026/27, expected goals). It has no stated reuse licence, so the
raw files are downloaded at build time into a git-ignored cache and only
derived summaries are written to the repository.
"""
from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "cache" / "football_data"
URL = "https://www.football-data.co.uk/mmz4281/{code}/{league}.csv"
FIRST_SEASON = 2010  # 2010/11; earliest seasons only warm up team ratings

COLUMNS = {
    "HomeTeam": "home", "AwayTeam": "away", "FTHG": "home_goals", "FTAG": "away_goals",
    "HTHG": "home_ht", "HTAG": "away_ht", "HS": "home_shots", "AS": "away_shots",
    "HST": "home_sot", "AST": "away_sot", "HC": "home_corners", "AC": "away_corners",
    "HF": "home_fouls", "AF": "away_fouls", "HY": "home_yellow", "AY": "away_yellow",
    "HR": "home_red", "AR": "away_red", "HxG": "home_xg", "AxG": "away_xg",
}


def season_code(start_year: int) -> str:
    return f"{start_year % 100:02d}{(start_year + 1) % 100:02d}"


def _closing_odds(raw: pd.DataFrame) -> pd.DataFrame:
    """Pinnacle closing odds where published, else the market-average closing price."""
    odds = pd.DataFrame(index=raw.index)
    for side in "HDA":
        value = pd.Series(float("nan"), index=raw.index)
        for column in (f"PSC{side}", f"AvgC{side}", f"PS{side}", f"Avg{side}"):
            if column in raw:
                value = value.fillna(pd.to_numeric(raw[column], errors="coerce"))
        odds[f"odds_{side.lower()}"] = value
    return odds


def parse_season(text: str, start_year: int) -> pd.DataFrame:
    raw = pd.read_csv(io.StringIO(text.lstrip("﻿")))
    raw = raw.dropna(subset=["HomeTeam", "AwayTeam", "FTHG", "FTAG"])
    frame = raw[[c for c in COLUMNS if c in raw]].rename(columns=COLUMNS)
    frame["date"] = pd.to_datetime(raw["Date"], dayfirst=True, format="mixed").dt.date.astype(str)
    frame = pd.concat([frame, _closing_odds(raw)], axis=1)
    frame.insert(0, "season", start_year)
    for column in frame.columns:
        if column not in ("home", "away", "date", "season"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame[["home_goals", "away_goals"]] = frame[["home_goals", "away_goals"]].astype(int)
    return frame.sort_values(["date", "home"]).reset_index(drop=True)


def load_season(league: str, start_year: int, refresh: bool = False) -> pd.DataFrame:
    """Return one season, downloading it when missing or when refresh is requested."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{league}_{season_code(start_year)}.csv"
    if refresh or not path.exists():
        response = requests.get(URL.format(code=season_code(start_year), league=league), timeout=30)
        response.raise_for_status()
        path.write_bytes(response.content)
    return parse_season(path.read_bytes().decode("utf-8-sig", errors="replace"), start_year)


def load_history(league: str, current_start: int, refresh_current: bool = True) -> pd.DataFrame:
    """All seasons from FIRST_SEASON through the current one, oldest first."""
    seasons = [load_season(league, year, refresh=refresh_current and year == current_start)
               for year in range(FIRST_SEASON, current_start + 1)]
    history = pd.concat(seasons, ignore_index=True)
    for year, frame in zip(range(FIRST_SEASON, current_start), seasons):
        if len(frame) != 380:
            raise ValueError(f"Expected 380 {league} matches in {year}/{(year + 1) % 100:02d}; found {len(frame)}")
    return history
