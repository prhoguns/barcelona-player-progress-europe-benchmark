"""Barcelona 2015/16 player progress | public-data demo dashboard."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).parent
DATA = ROOT / "data" / "derived"
NAVY, BLUE, MAROON, GOLD, MINT = "#100b23", "#1558bb", "#a11f51", "#f7c950", "#6fe0d4"
METRICS = {
    "xg": "Expected goals", "xa": "Expected assists", "goals": "Goals", "assists": "Assists",
    "progressive_passes": "Progressive passes", "final_third_entries": "Final-third entries",
    "pressures": "Pressures", "recoveries": "Ball recoveries", "interceptions": "Interceptions",
    "tackles": "Tackles", "progressive_carries": "Progressive carries",
}

st.set_page_config(page_title="Barça | Player Lab", page_icon="⚽", layout="wide")
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');
html,body,[class*=css],.stApp{font-family:'DM Sans',sans-serif;color:#f6f3ff}
.stApp{background:radial-gradient(circle at 75% 0%,#192a69 0%,#100b23 40%,#0c0a1a 100%)}
[data-testid="stHeader"]{background:#100b23}
[data-testid="stSidebar"]{background:#12102a;border-right:1px solid #343053}
[data-testid="stSidebar"] p,[data-testid="stSidebar"] label,[data-testid="stSidebar"] span{color:#e8e0fa!important}
label,[data-testid="stWidgetLabel"] p{color:#d6d0e9!important}
h1,h2,h3{font-family:'Space Grotesk',sans-serif;letter-spacing:-.04em}
h1{font-size:3.05rem!important;color:#fff!important}
h2{color:#fff!important;padding-top:.35rem}
.stAlert{border-radius:14px}
div[data-testid="metric-container"]{background:#1b1737;border:1px solid #373052;border-radius:16px;padding:16px}
div[data-testid="metric-container"] label{color:#bdb7d3!important}
div[data-testid="stMetric"] [data-testid="stMetricValue"]{color:#fff!important}
div[data-testid="stTabs"] button{font-weight:700;color:#c7c1dd}
.stTabs [data-baseweb="tab"]{color:#c7c1dd!important}
.hero{background:linear-gradient(110deg,#9c1948 0%,#572064 48%,#134890 100%);border:1px solid #8c4d87;border-radius:22px;padding:28px 34px;margin:0 0 20px;box-shadow:0 22px 60px #0005}
.eyebrow{color:#f7c950;text-transform:uppercase;letter-spacing:.22em;font-size:.74rem;font-weight:700}
.deck{color:#e6dfee;font-size:1.05rem;max-width:700px;line-height:1.55}
.badge{display:inline-block;border:1px solid #ffffff58;border-radius:999px;padding:5px 12px;font-size:.76rem;color:#f9eacf;margin:8px 8px 0 0}
.note{background:#18152f;border-left:4px solid #f7c950;border-radius:8px;padding:12px 16px;color:#d8d2e8;margin:10px 0 18px}
</style>""", unsafe_allow_html=True)

@st.cache_data
def load():
    a = pd.read_csv(DATA / "appearances.csv", parse_dates=["date"])
    s = pd.read_csv(DATA / "game_states.csv", parse_dates=["date"])
    p = pd.read_csv(DATA / "pass_zones.csv", parse_dates=["date"])
    t = pd.read_csv(DATA / "tracking_sample.csv")
    m = json.loads((DATA / "manifest.json").read_text())
    tm = json.loads((DATA / "tracking_manifest.json").read_text())
    return a, s, p, t, m, tm

if not (DATA / "appearances.csv").exists():
    st.error("Demo outputs are missing. Run `python scripts/build_data.py` and `python scripts/build_tracking_sample.py` first.")
    st.stop()

appearances, states, zones, tracking, manifest, track_manifest = load()
numeric = ["minutes", "goals", "assists", "xg", "xa", "shots", "passes", "completed_passes",
           "progressive_passes", "final_third_entries", "pressures", "recoveries", "interceptions",
           "tackles", "carries", "progressive_carries", "risk_passes", "reward_passes"]
for col in numeric:
    appearances[col] = pd.to_numeric(appearances[col], errors="coerce").fillna(0)
appearance_sum = appearances.groupby(["club", "competition", "player_id", "player"], as_index=False)[numeric].sum()
dominant_role = (appearances.groupby(["club", "player_id", "role"],as_index=False).minutes.sum()
                 .sort_values("minutes",ascending=False).drop_duplicates(["club", "player_id"]))
appearance_sum = appearance_sum.merge(dominant_role[["club", "player_id", "role"]],on=["club", "player_id"],how="left")
appearance_sum = appearance_sum.merge(appearances.groupby(["club", "player_id"]).size().rename("matches").reset_index(), on=["club", "player_id"], how="left")

def plot_style(fig, height=350):
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(color="#e9e3f5", family="DM Sans"), margin=dict(l=8,r=8,t=35,b=8),
                      height=height, legend=dict(orientation="h", y=1.13), colorway=[GOLD,MINT,MAROON,BLUE])
    fig.update_xaxes(gridcolor="#39334f", zerolinecolor="#39334f")
    fig.update_yaxes(gridcolor="#39334f", zerolinecolor="#39334f")
    return fig

def pitch(fig):
    fig.add_shape(type="rect", x0=0,y0=0,x1=120,y1=80,line=dict(color="#b6d7cb",width=2))
    fig.add_shape(type="line", x0=60,y0=0,x1=60,y1=80,line=dict(color="#b6d7cb",width=1))
    fig.add_shape(type="circle", x0=50,y0=30,x1=70,y1=50,line=dict(color="#b6d7cb",width=1))
    for x0,x1 in [(0,18),(102,120)]:
        fig.add_shape(type="rect",x0=x0,y0=18,x1=x1,y1=62,line=dict(color="#b6d7cb",width=1))
    fig.update_xaxes(range=[-2,122],visible=False,scaleanchor="y",scaleratio=1)
    fig.update_yaxes(range=[-2,82],visible=False)
    return fig

def metric_note():
    st.caption("Per 90 = event count × 90 ÷ estimated minutes played. xG is StatsBomb shot xG; xA assigns an assisted shot’s xG to its linked pass. Progressive pass: completed, ≥12 StatsBomb x units forward, ending at x≥60. These are descriptive proxies, not causal player value estimates.")

with st.sidebar:
    st.markdown("### ◈ BARÇA PLAYER LAB")
    st.caption("Historical demo · Men · 2015/16")
    barca = appearance_sum[appearance_sum.club == "Barcelona"].sort_values("minutes", ascending=False)
    role_filter = st.selectbox("Role", ["All", "FWD", "MID", "DEF", "GK"])
    roster = barca if role_filter == "All" else barca[barca.role == role_filter]
    selected_name = st.selectbox("Barcelona player", roster.player.tolist())
    selected = barca[barca.player == selected_name].iloc[0]
    match_names = appearances[appearances.player_id == selected.player_id].sort_values("date")
    match_options = ["Full season"] + [f"{r.date:%d %b %Y} · {r.opponent}" for r in match_names.itertuples()]
    match_choice = st.selectbox("Match focus", match_options)
    st.markdown("---")
    st.caption("Coverage: Barcelona 38 · Arsenal 38 · Juventus 38 · PSG 37 · Leverkusen 34 matches. One club per league; PSG has a published-fixture gap.")
    st.caption("StatsBomb event data and SkillCorner tracking samples are separate sources and matches.")

match_focus = None if match_choice == "Full season" else match_names.iloc[match_options.index(match_choice)-1]
st.markdown("""<div class="hero"><div class="eyebrow">Historical performance studio · 2015/16</div>
<h1>Barcelona Player Progress</h1><div class="deck">Season arcs, role peers across Europe, and the contributions that rarely make a scoreline. Built from public event data, with a separate open tracking prototype.</div>
<span class="badge">DEMO DATA</span><span class="badge">MEN’S CLUB FOOTBALL</span><span class="badge">FIVE-LEAGUE CLUB PANEL</span></div>""", unsafe_allow_html=True)
st.warning("Live Barcelona tracking feed pending licensed SkillCorner access.", icon="📡")
st.markdown("<div class='note'>Sources and seasons: StatsBomb Open Data, men’s 2015/16 league events for the five selected clubs. SkillCorner open sample: 2024/25 A-League, a different match and source. This dashboard is a historical demo, not a live scouting feed.</div>", unsafe_allow_html=True)

tabs = st.tabs(["Season progress", "Quiet contribution", "Game state", "Workload & rotation", "Form tracker", "Risk–reward passing", "Off-ball sample", "Methods & sources"])

with tabs[0]:
    st.subheader(f"{selected_name} · season progress")
    peer = appearance_sum[(appearance_sum.role == selected.role) & (appearance_sum.club != "Barcelona") & (appearance_sum.minutes >= 900)]
    metric = st.selectbox("Compare a metric", list(METRICS), format_func=lambda k: METRICS[k])
    value = 90*selected[metric]/selected.minutes
    peer_values = 90*peer[metric]/peer.minutes
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Minutes", f"{selected.minutes:,.0f}")
    c2.metric(f"{METRICS[metric]} /90", f"{value:.2f}")
    c3.metric("Peer median /90", f"{peer_values.median():.2f}" if len(peer) else "—")
    c4.metric("Role peers", len(peer))
    cum = match_names.sort_values("date").copy()
    cum["cum_minutes"] = cum.minutes.cumsum()
    cum["cum_metric"] = 90*cum[metric].cumsum()/cum.cum_minutes
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=cum.date,y=cum.cum_metric,mode="lines+markers",name=selected_name,line=dict(color=GOLD,width=3),marker=dict(size=5)))
    if len(peer):
        fig.add_hline(y=peer_values.median(),line_dash="dash",line_color=MINT,annotation_text="Europe panel role median")
    st.plotly_chart(plot_style(fig),width="stretch")
    st.caption("Cumulative per-90 rate by Barcelona match date. Europe benchmark = median of same-role players with ≥900 minutes from Arsenal, Juventus, Paris Saint-Germain and Bayer Leverkusen; selected-club panel, not a league-wide percentile.")
    with st.expander("See peer comparison table"):
        display = peer.assign(per90=peer_values).sort_values("per90",ascending=False)[["player","club","role","minutes","per90"]]
        st.dataframe(display.rename(columns={"per90":f"{METRICS[metric]} /90"}),width="stretch",hide_index=True)
    metric_note()

with tabs[1]:
    st.subheader("Quiet Contribution Finder")
    st.caption("Ranks Barcelona outfield players with ≥450 minutes by low-visibility actions per 90: recoveries + interceptions + 0.5 × pressures + progressive passes + progressive carries. Goals and assists are shown for context, not subtracted from the score.")
    quiet = barca[(barca.role != "GK") & (barca.minutes >= 450)].copy()
    quiet["quiet_per90"] = 90*(quiet.recoveries+quiet.interceptions+.5*quiet.pressures+quiet.progressive_passes+quiet.progressive_carries)/quiet.minutes
    quiet["goal_involvements"] = quiet.goals+quiet.assists
    quiet = quiet.sort_values("quiet_per90",ascending=False)
    fig = px.bar(quiet.head(12).sort_values("quiet_per90"),x="quiet_per90",y="player",orientation="h",color="goal_involvements",color_continuous_scale=[[0,MAROON],[1,GOLD]],labels={"quiet_per90":"Quiet actions /90","player":"","goal_involvements":"G+A"})
    st.plotly_chart(plot_style(fig,460),width="stretch")
    st.dataframe(quiet[["player","role","minutes","quiet_per90","goal_involvements"]].round(2),hide_index=True,width="stretch")

with tabs[2]:
    st.subheader("Game State Contribution")
    person_states = states[(states.club=="Barcelona") & (states.player_id==selected.player_id)].copy()
    cols = ["passes","progressive_passes","shots","xg","pressures","recoveries"]
    for col in cols: person_states[col]=pd.to_numeric(person_states[col],errors="coerce").fillna(0)
    if match_focus is not None: person_states = person_states[person_states.match_id==match_focus.match_id]
    by_state = person_states.groupby("state",as_index=False)[cols].sum()
    measure = st.selectbox("Contribution",cols,format_func=lambda x:METRICS.get(x,x.replace("_"," ").title()))
    fig = px.bar(by_state,x="state",y=measure,color="state",color_discrete_map={"Leading":MINT,"Level":GOLD,"Trailing":MAROON},text_auto=".1f")
    st.plotly_chart(plot_style(fig),width="stretch")
    st.caption("State uses the score immediately before each event. Totals are event volumes; state-specific minutes are unavailable in this compact demo, so state rates are deliberately omitted. Match focus follows the sidebar selector.")

with tabs[3]:
    st.subheader("Player Workload & Rotation")
    work = match_names.sort_values("date").copy()
    work["last_5_minutes"] = work.minutes.rolling(5,min_periods=1).sum()
    work["rest_days"] = work.date.diff().dt.days
    c1,c2,c3 = st.columns(3)
    c1.metric("Starts",int(work.started.sum()))
    c2.metric("Last 5 appearances",f"{work.tail(5).minutes.sum():.0f} min")
    c3.metric("Median rest",f"{work.rest_days.median():.0f} days" if len(work)>1 else "—")
    fig = go.Figure()
    fig.add_trace(go.Bar(x=work.date,y=work.minutes,name="Minutes",marker_color=BLUE,hovertext=work.opponent))
    fig.add_trace(go.Scatter(x=work.date,y=work.last_5_minutes/5,name="5-game mean",line=dict(color=GOLD,width=3)))
    st.plotly_chart(plot_style(fig),width="stretch")
    st.caption("Match minutes are estimated from Starting XI, substitution and dismissal events, including observed stoppage time. Rest days count selected club appearances only; this is not a medical load or injury-risk measure.")

with tabs[4]:
    st.subheader("Player Form Tracker")
    form = match_names.sort_values("date").copy()
    form["involvement"] = form.xg+form.xa
    form["form_5"] = 90*form.involvement.rolling(5,min_periods=1).sum()/form.minutes.rolling(5,min_periods=1).sum()
    form["progression_5"] = 90*form.progressive_passes.rolling(5,min_periods=1).sum()/form.minutes.rolling(5,min_periods=1).sum()
    choice = st.radio("Form view",["xG + xA /90","Progressive passes /90"],horizontal=True)
    series = "form_5" if choice.startswith("xG") else "progression_5"
    fig = go.Figure(go.Scatter(x=form.date,y=form[series],mode="lines+markers",line=dict(color=MINT,width=3),fill="tozeroy",fillcolor="rgba(111,224,212,.15)",hovertext=form.opponent))
    st.plotly_chart(plot_style(fig),width="stretch")
    st.caption("Rolling five appearances, weighted by minutes. Early points use fewer than five appearances; xG + xA describes chance involvement rather than realized goals.")

with tabs[5]:
    st.subheader("Risk–Reward Pass Profile")
    p = zones[(zones.club=="Barcelona") & (zones.player_id==selected.player_id)].copy()
    if match_focus is not None: p=p[p.match_id==match_focus.match_id]
    p["passes"] = pd.to_numeric(p.passes,errors="coerce").fillna(0)
    for k in ("completed","progressive","risk","reward","xa"): p[k]=pd.to_numeric(p[k],errors="coerce").fillna(0)
    total = p.passes.sum()
    a,b,c,d=st.columns(4)
    a.metric("Passes",f"{total:,.0f}")
    b.metric("Completion",f"{p.completed.sum()/total:.0%}" if total else "—")
    c.metric("Progressive",f"{p.progressive.sum():,.0f}")
    d.metric("xA",f"{p.xa.sum():.2f}")
    grid = p.groupby(["x_bin","y_bin"],as_index=False)["passes"].sum()
    fig = go.Figure()
    for row in grid.itertuples():
        fig.add_shape(type="rect",x0=row.x_bin*20,y0=row.y_bin*20,x1=(row.x_bin+1)*20,y1=(row.y_bin+1)*20,
                      fillcolor=f"rgba(247,201,80,{min(.85,.12+.73*row.passes/max(1,grid.passes.max())):.2f})",line=dict(width=0))
    pitch(fig)
    st.plotly_chart(plot_style(fig,410),width="stretch")
    st.caption("Pitch cells show pass origins; darker gold means more passes. Risk proxy = pass from x≥60 to x≥80 with a through-ball flag or ≥15 x-unit advance. Reward proxy = completed progressive pass or shot-assist pass. These definitions overlap and are descriptive, not expected-value modeling.")

with tabs[6]:
    st.subheader("Off-ball movement prototype · separate SkillCorner sample")
    st.info(f"SkillCorner Open Data: {track_manifest['match']} · {track_manifest['competition']} · {track_manifest['date']}. First 10 minutes of period 1. Anonymized display labels. This is neither Barcelona data nor a linked StatsBomb fixture.")
    track_player=st.selectbox("Sample tracked player",sorted(tracking.sample_player.unique()))
    path=tracking[tracking.sample_player==track_player].sort_values("second")
    fig=go.Figure(go.Scatter(x=60+path.x_m*120/105,y=40+path.y_m*80/68,mode="lines+markers",line=dict(color=MINT,width=2),marker=dict(size=4,color=path.second,colorscale="Sunset"),name=track_player))
    pitch(fig)
    st.plotly_chart(plot_style(fig,420),width="stretch")
    st.caption(f"Detected-position path sampled every 2 seconds. Filtered distance sum: {path.distance_step_m.sum():.0f} m over this excerpt. Tracking coordinates are projected to a 120×80 display pitch; gaps and detection errors remain. Distance is illustrative, not an official physical metric.")

with tabs[7]:
    st.subheader("Coverage, methods & acknowledgements")
    st.markdown("**StatsBomb Open Data** supplies 2015/16 men’s league events for one selected club in each of La Liga, Premier League, Serie A, Ligue 1 and Bundesliga. The benchmark is a curated club panel, with players classified into broad roles. Club fixture counts: Barcelona 38, Arsenal 38, Juventus 38, Paris Saint-Germain 37 and Bayer Leverkusen 34. PSG’s missing published fixture is a coverage gap.\n\n**SkillCorner Open Data** supplies an independent 2024/25 A-League tracking sample. The app uses anonymized labels and a 10-minute derived excerpt. No source match joining is attempted.\n\n**Data status:** historical public-data demo. No live tracking, licensed Barcelona footage, medical workload data, or current-season feeds.")
    st.image(str(ROOT / "assets" / "statsbomb-logo.png"),caption="StatsBomb — event data source",width=180)
    st.markdown("[StatsBomb Open Data and terms](https://github.com/hudl/open-data) · [StatsBomb media pack](https://statsbomb.com/media-pack/) · [SkillCorner Open Data and MIT license](https://github.com/SkillCorner/opendata) · [Methods and reproduction in README](https://github.com/prhoguns/barcelona-player-progress-europe-benchmark#readme)")
