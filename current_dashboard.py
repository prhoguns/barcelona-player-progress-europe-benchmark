"""Current Barcelona season with licensed-data boundaries made explicit."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from scripts.build_current_fixtures import main as refresh_fixtures
from src.current_season import OPTIONAL, load_player_csv

ROOT = Path(__file__).parent
SNAPSHOT = ROOT / "data" / "current" / "fixtures.json"
NAVY, GOLD, MINT, MAROON, BLUE = "#100b23", "#f7c950", "#6fe0d4", "#a11f51", "#1558bb"

st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');
html,body,.stApp{font-family:'DM Sans',sans-serif;color:#f6f3ff}
.stApp{background:radial-gradient(circle at 75% 0%,#1c2c64 0%,#100b23 42%,#0c0a1a 100%)}
[data-testid="stHeader"]{background:#100b23}
[data-testid="stSidebar"]{background:#12102a;border-right:1px solid #343053}
[data-testid="stSidebar"] p,[data-testid="stSidebar"] label{color:#e8e0fa!important}
[data-testid="stSidebar"] button p{color:#211634!important}
label,[data-testid="stWidgetLabel"] p{color:#d6d0e9!important}
.stTabs [data-baseweb="tab"]{color:#c7c1dd!important}
h1,h2,h3{font-family:'Space Grotesk',sans-serif;letter-spacing:-.04em;color:#fff!important}
div[data-testid="stMetric"] [data-testid="stMetricValue"]{color:#fff!important}
.hero{background:linear-gradient(110deg,#9c1948 0%,#572064 48%,#134890 100%);border:1px solid #8c4d87;border-radius:22px;padding:28px 34px;margin:0 0 20px;box-shadow:0 22px 60px #0005}
.eyebrow{color:#f7c950;text-transform:uppercase;letter-spacing:.22em;font-size:.74rem;font-weight:700}
.deck{color:#e6dfee;font-size:1.05rem;max-width:760px;line-height:1.55}
.badge{display:inline-block;border:1px solid #ffffff58;border-radius:999px;padding:5px 12px;font-size:.76rem;color:#f9eacf;margin:8px 8px 0 0}
.note{background:#18152f;border-left:4px solid #f7c950;border-radius:8px;padding:12px 16px;color:#d8d2e8;margin:10px 0 18px}
</style>""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### ◈ BARÇA PLAYER LAB")
    st.caption("Men’s La Liga · 2026/27")
    if st.button("Refresh current fixtures", width="stretch"):
        try:
            refresh_fixtures()
            st.success("Fixture snapshot refreshed")
        except Exception as exc:
            st.error(f"Refresh failed; the saved snapshot remains available. {exc}")
    st.caption("Results use a public-domain fixture feed. Player event and tracking feeds are not connected.")

snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
fixtures = pd.DataFrame(snapshot["matches"])
finals = fixtures[fixtures.status == "final"].sort_values("date").copy()
home = finals.home.eq("FC Barcelona")
finals["for"] = finals.home_goals.where(home, finals.away_goals).astype(int)
finals["against"] = finals.away_goals.where(home, finals.home_goals).astype(int)
finals["result"] = finals.apply(lambda r: "W" if r["for"] > r["against"] else "D" if r["for"] == r["against"] else "L", axis=1)
finals["points"] = finals.result.map({"W": 3, "D": 1, "L": 0})
finals["cumulative_points"] = finals.points.cumsum()
finals["goal_difference"] = (finals["for"] - finals["against"]).cumsum()
final_rounds = {int(r.rsplit(" ", 1)[-1]) for r in finals["round"]}

st.markdown("""<div class="hero"><div class="eyebrow">Current season · men’s La Liga</div>
<h1>Barcelona 2026/27</h1><div class="deck">A current-season match pulse. Player-level analysis becomes available when an authorized match data feed is connected; the 2015/16 event-data work remains in the separate historical demo view.</div>
<span class="badge">CURRENT SEASON</span><span class="badge">FIXTURES + RESULTS</span><span class="badge">PLAYER FEED PENDING</span></div>""", unsafe_allow_html=True)
st.warning("Live Barcelona tracking feed pending licensed SkillCorner access.", icon="📡")
st.markdown(f"<div class='note'>Fixture source: openfootball/football.json (CC0). Snapshot retrieved {snapshot['retrieved_at_utc'][:16].replace('T', ' ')} UTC. {len(finals)} of 38 league fixtures have final scores in this snapshot. This is not a live player-stat feed.</div>", unsafe_allow_html=True)

tabs = st.tabs(["Season pulse", "Player progress", "Module coverage", "Sources & method"])
with tabs[0]:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("League matches", f"{len(finals)}/38")
    c2.metric("Record", f"{(finals.result == 'W').sum()}W · {(finals.result == 'D').sum()}D · {(finals.result == 'L').sum()}L")
    c3.metric("Points", int(finals.points.sum()))
    c4.metric("Goals", f"{int(finals['for'].sum())}–{int(finals['against'].sum())}")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=finals.date, y=finals.cumulative_points, mode="lines+markers", name="Points", line=dict(color=GOLD,width=3)))
    fig.add_trace(go.Scatter(x=finals.date, y=finals.goal_difference, mode="lines+markers", name="Goal difference", line=dict(color=MINT,width=3),yaxis="y2"))
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(color="#e9e3f5"), height=350, margin=dict(l=8,r=8,t=35,b=8),
                      legend=dict(orientation="h",y=1.12,font=dict(color="#e9e3f5")), yaxis=dict(title="Points",gridcolor="#39334f"),
                      yaxis2=dict(title="Goal difference",overlaying="y",side="right",showgrid=False))
    st.plotly_chart(fig,width="stretch")
    st.caption("Progression is ordered by actual match date; postponed matches can make matchday numbers appear out of order.")
    table = fixtures.copy()
    table["opponent"] = table.away.where(table.home.eq("FC Barcelona"),table.home)
    table["venue"] = table.home.eq("FC Barcelona").map({True:"Home",False:"Away"})
    table["score"] = table.apply(lambda r: f"{int(r.home_goals)}–{int(r.away_goals)}" if r.status == "final" else "—",axis=1)
    st.dataframe(table[["round","date","opponent","venue","score","status"]],hide_index=True,width="stretch")

with tabs[1]:
    st.subheader("Current-season player progress")
    st.info("No current Barcelona player-match feed is bundled. Upload data you are authorized to use; it stays in this browser session and is not written to the repository.")
    st.download_button("Download CSV template", (ROOT / "examples" / "current_player_match_template.csv").read_bytes(),
                       file_name="barcelona_2026_27_player_match_template.csv",mime="text/csv")
    uploaded = st.file_uploader("Player match CSV · La Liga 2026/27", type=["csv"])
    if uploaded is not None:
        try:
            player_rows = load_player_csv(uploaded.getvalue(),final_rounds)
        except (ValueError, TypeError) as exc:
            st.error(str(exc))
        else:
            st.success(f"Loaded {len(player_rows)} authorized player-match rows for {player_rows.player.nunique()} players")
            player_name = st.selectbox("Player",sorted(player_rows.player.unique()))
            person = player_rows[player_rows.player == player_name].sort_values("matchday").copy()
            available = [m for m in OPTIONAL if m in person.columns]
            p1,p2,p3 = st.columns(3)
            p1.metric("Appearances in file",len(person))
            p2.metric("Minutes in file",f"{person.minutes.sum():.0f}")
            p3.metric("Last five rows",f"{person.tail(5).minutes.sum():.0f} min")
            if available:
                chosen = st.selectbox("Recorded metric",available,format_func=lambda m:m.replace("_"," ").title())
                person["cumulative"] = person[chosen].cumsum()
                person["per90"] = 90*person["cumulative"]/person.minutes.cumsum().replace(0,float("nan"))
                fig = go.Figure(go.Scatter(x=person.matchday,y=person.per90,mode="lines+markers",line=dict(color=GOLD,width=3)))
                fig.update_layout(template="plotly_dark",paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",height=320,
                                  xaxis_title="Matchday",yaxis_title=f"Cumulative {chosen.replace('_',' ')} per 90")
                st.plotly_chart(fig,width="stretch")
            st.caption("Values are from the uploaded file only. Missing metrics remain unavailable; no historical 2015/16 player values are substituted.")

with tabs[2]:
    st.subheader("Current-season module coverage")
    modules = [
        ("Barcelona player season progress", "Available for metrics in an authorized player-match CSV; role peer benchmarks need a licensed comparable feed."),
        ("Quiet Contribution Finder", "Pending defensive-action player data; uploads with pressures, recoveries and interceptions can support it."),
        ("Game State Contribution", "Pending current-season event timeline and score-state data."),
        ("Player Workload and Rotation", "Available from an authorized player-match CSV with minutes."),
        ("Player Form Tracker", "Available from an authorized player-match CSV for supplied metrics."),
        ("Risk–Reward Pass Profile", "Pending current-season pass event locations and outcomes."),
        ("Off-ball movement", "Pending licensed Barcelona tracking. The SkillCorner open sample is unrelated to Barcelona."),
        ("Matchday season forecast", "Pending authorized current player-match observations and a validated training set; no 2015/16 values are presented as current predictions."),
    ]
    for title, detail in modules:
        with st.container(border=True):
            st.markdown(f"**{title}**")
            st.caption(detail)

with tabs[3]:
    st.subheader("Sources and boundaries")
    st.markdown("The 2026/27 results come from [openfootball/football.json](https://github.com/openfootball/football.json), a [CC0 public-domain](https://github.com/openfootball/football.json/blob/master/LICENSE.md) fixture dataset. Its own README says upstream updates are not guaranteed daily, so the snapshot timestamp and a manual refresh control are shown. The feed contains fixtures and scores, not player-level event or tracking data.")
    st.markdown("[FC Barcelona official results](https://www.fcbarcelona.com/en/futbol/primer-equipo/resultados) and [La Liga player statistics](https://www.laliga.com/en-US/stats/laliga-easports/scorers/team/fc-barcelona) can be viewed at their sources. Their site content is not copied into this public repository. The [2015/16 StatsBomb](https://github.com/hudl/open-data) analysis remains available through the season selector as a labelled historical method demo.")
    st.caption("Data status: current-season match results snapshot, optional user-provided player CSV, historical event-data demo, no live player feed, no licensed Barcelona tracking.")
