"""Validation for optional, user-authorized current-season player match data."""
from __future__ import annotations

import io
from datetime import date

import pandas as pd

REQUIRED = ("matchday", "date", "player", "minutes")
OPTIONAL = ("goals", "assists", "xg", "xa", "passes", "progressive_passes",
            "pressures", "recoveries", "interceptions", "tackles")


def load_player_csv(content: bytes, final_rounds: set[int], today: date | None = None) -> pd.DataFrame:
    """Accept only La Liga player-match rows; leave absent metrics absent."""
    if len(content) > 2_000_000:
        raise ValueError("Upload must be 2 MB or smaller")
    frame = pd.read_csv(io.BytesIO(content))
    missing = set(REQUIRED) - set(frame.columns)
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")
    if frame.empty:
        raise ValueError("CSV has no player-match rows")
    frame["matchday"] = pd.to_numeric(frame.matchday, errors="raise").astype(int)
    if not set(frame.matchday).issubset(final_rounds):
        raise ValueError("Every matchday must be a completed Barcelona La Liga fixture")
    frame["date"] = pd.to_datetime(frame.date, errors="raise").dt.date
    as_of = today or date.today()
    if any(d < date(2026, 7, 1) or d > as_of for d in frame.date):
        raise ValueError("Dates must fall in the 2026/27 season through today")
    frame["player"] = frame.player.astype(str).str.strip()
    if frame.player.eq("").any() or frame.duplicated(["matchday", "player"]).any():
        raise ValueError("Each player needs one nonblank row per matchday")
    frame["minutes"] = pd.to_numeric(frame.minutes, errors="raise")
    if not frame.minutes.between(0, 120).all():
        raise ValueError("Minutes must be between 0 and 120")
    for metric in OPTIONAL:
        if metric in frame.columns:
            frame[metric] = pd.to_numeric(frame[metric], errors="raise")
            if frame[metric].isna().any() or (frame[metric] < 0).any():
                raise ValueError(f"{metric} must be complete and nonnegative when supplied")
    return frame.sort_values(["matchday", "player"]).reset_index(drop=True)
