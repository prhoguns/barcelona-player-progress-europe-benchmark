"""Barça Player Lab: current-season home, historical event-data demo."""
from __future__ import annotations

import runpy
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).parent
st.set_page_config(page_title="Barça | Player Lab", page_icon="⚽", layout="wide")
view = st.sidebar.radio("Season view", ["2026/27 · current", "2015/16 · historical demo"])

if view.startswith("2026/27"):
    runpy.run_path(str(ROOT / "current_dashboard.py"))
else:
    runpy.run_path(str(ROOT / "historical.py"))
