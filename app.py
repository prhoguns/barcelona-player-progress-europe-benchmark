"""Season Forecast Lab: current-season club forecasts, plus the 2015/16 Barcelona event-data demo."""
from __future__ import annotations

import runpy
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).parent
st.set_page_config(page_title="Season Forecast Lab", page_icon="⚽", layout="wide")
view = st.sidebar.radio("View", ["2026/27 · current season", "2015/16 · Barcelona historical demo"])

if view.startswith("2026/27"):
    runpy.run_path(str(ROOT / "current_dashboard.py"))
else:
    runpy.run_path(str(ROOT / "historical.py"))
