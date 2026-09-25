"""Small, auditable transformations for the event-data demo."""
from __future__ import annotations

import math

ROLE_MAP = {
    "Goalkeeper": "GK", "Right Back": "DEF", "Left Back": "DEF",
    "Right Center Back": "DEF", "Left Center Back": "DEF", "Center Back": "DEF",
    "Right Wing Back": "DEF", "Left Wing Back": "DEF",
    "Center Defensive Midfield": "MID", "Left Defensive Midfield": "MID",
    "Right Defensive Midfield": "MID", "Center Midfield": "MID",
    "Left Center Midfield": "MID", "Right Center Midfield": "MID",
    "Left Midfield": "MID", "Right Midfield": "MID",
    "Center Attacking Midfield": "MID", "Left Attacking Midfield": "MID",
    "Right Attacking Midfield": "MID", "Left Wing": "FWD",
    "Right Wing": "FWD", "Center Forward": "FWD", "Secondary Striker": "FWD",
}

def role(position: str | None) -> str:
    return ROLE_MAP.get(position or "", "MID")

def per90(value: float, minutes: float) -> float:
    return 90 * value / minutes if minutes > 0 else 0.0

def progressive_pass(start: list | None, end: list | None) -> bool:
    """Simple 120x80 pitch proxy: completed pass advances >=10m-equivalent x."""
    return bool(start and end and len(start) >= 2 and len(end) >= 2
                and end[0] - start[0] >= 12 and end[0] >= 60)

def event_clock(event: dict) -> float:
    return float(event.get("minute", 0)) + float(event.get("second", 0)) / 60

def goal_team(event: dict) -> str | None:
    typ = event.get("type", {}).get("name")
    if typ == "Shot" and event.get("shot", {}).get("outcome", {}).get("name") == "Goal":
        return event.get("team", {}).get("name")
    if typ == "Own Goal Against":
        return "__opponent__"
    return None

def safe_float(value) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else 0.0
    except (TypeError, ValueError):
        return 0.0
