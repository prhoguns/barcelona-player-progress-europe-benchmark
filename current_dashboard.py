"""Current season: club forecasts, player goal projections, match stats and model accuracy."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.current_season import OPTIONAL, load_player_csv
from src.forecast import ForecastModel
from src.leagues import LEAGUES

ROOT = Path(__file__).parent
DATA = ROOT / "data" / "current"
# Categorical slots from the validated dark palette; MUTED marks "every other club".
BLUE, ORANGE, AQUA, MUTED = "#3987e5", "#d95926", "#199e70", "#5d5a73"
INK, INK_2, GRID = "#f6f3ff", "#c3c2b7", "#2c2843"

st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');
html,body,.stApp{font-family:'DM Sans',sans-serif;color:#f6f3ff}
.stApp{background:radial-gradient(circle at 75% 0%,#1c2c64 0%,#100b23 42%,#0c0a1a 100%)}
[data-testid="stHeader"]{background:#100b23}
[data-testid="stSidebar"]{background:#12102a;border-right:1px solid #343053}
[data-testid="stSidebar"] p,[data-testid="stSidebar"] label{color:#e8e0fa!important}
label,[data-testid="stWidgetLabel"] p{color:#d6d0e9!important}
.stTabs [data-baseweb="tab"]{color:#c7c1dd!important}
h1,h2,h3{font-family:'Space Grotesk',sans-serif;letter-spacing:-.04em;color:#fff!important}
div[data-testid="stMetric"] [data-testid="stMetricValue"]{color:#fff!important}
.hero{background:linear-gradient(110deg,#9c1948 0%,#572064 48%,#134890 100%);border:1px solid #8c4d87;border-radius:22px;padding:26px 32px;margin:0 0 18px;box-shadow:0 22px 60px #0005}
.eyebrow{color:#f7c950;text-transform:uppercase;letter-spacing:.22em;font-size:.74rem;font-weight:700}
.deck{color:#e6dfee;font-size:1.02rem;max-width:780px;line-height:1.55}
.badge{display:inline-block;border:1px solid #ffffff58;border-radius:999px;padding:5px 12px;font-size:.76rem;color:#f9eacf;margin:8px 8px 0 0}
.note{background:#18152f;border-left:4px solid #f7c950;border-radius:8px;padding:12px 16px;color:#d8d2e8;margin:10px 0 18px}
</style>""", unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def read_json(path: str, stamp: float) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


@st.cache_data(show_spinner=False)
def read_csv(path: str, stamp: float) -> pd.DataFrame:
    return pd.read_csv(path)


def load_json(path: Path) -> dict:
    return read_json(str(path), path.stat().st_mtime)


def load_csv(path: Path) -> pd.DataFrame:
    return read_csv(str(path), path.stat().st_mtime)


def style(fig: go.Figure, height: int = 340, **layout) -> go.Figure:
    layout.setdefault("hovermode", "x unified")
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(color=INK, family="DM Sans"), height=height, margin=dict(l=8, r=8, t=30, b=8),
                      legend=dict(orientation="h", y=1.12, font=dict(color=INK_2)), **layout)
    fig.update_xaxes(gridcolor=GRID, zeroline=False)
    fig.update_yaxes(gridcolor=GRID, zeroline=False)
    return fig


def pct(value: float) -> str:
    return f"{100 * value:.0f}%"


# ---------------------------------------------------------------- selection

league_names = {config["name"]: key for key, config in LEAGUES.items()}
with st.sidebar:
    st.markdown("### ◈ SEASON FORECAST LAB")
    league_name = st.radio("League", list(league_names), horizontal=True)
    league_key = league_names[league_name]
    folder = DATA / league_key
    if not (folder / "clubs.json").exists():
        st.error("No forecasts built yet. Run `python scripts/build_forecasts.py`.")
        st.stop()
    clubs_data = load_json(folder / "clubs.json")
    club_names = sorted(clubs_data["clubs"])
    default = LEAGUES[league_key]["default_club"]
    club = st.selectbox("Club", club_names, index=club_names.index(default) if default in club_names else 0)
    if st.button("Refresh results and forecasts", width="stretch"):
        with st.spinner("Downloading new results and re-running the forecast (about a minute)..."):
            run = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_forecasts.py"), "--quick",
                                  "--league", league_key], capture_output=True, text=True, cwd=ROOT)
        if run.returncode == 0:
            st.cache_data.clear()
            st.rerun()
        st.error(f"Refresh failed: {run.stderr[-600:]}")
    st.caption(f"Results through {clubs_data['results_through']} · built {clubs_data['as_of']}. "
               "Updated automatically every day.")

model_info = load_json(folder / "model.json")
players_data = load_json(folder / "players.json")["clubs"]
matches = load_csv(folder / "matches.csv")
backtest = load_csv(folder / "team_backtest.csv")
info = clubs_data["clubs"][club]
record, projection = info["record"], info["projection"]

st.markdown(f"""<div class="hero"><div class="eyebrow">{league_name} · {clubs_data['season']}</div>
<h1>{club}</h1><div class="deck">Season forecasts from a match model trained on {model_info['data']['matches']:,}
{league_name} matches since {model_info['data']['seasons'].split('–')[0]}, tested on seasons it never saw.
Player projections use scorer data checked against official results.</div>
<span class="badge">{record['played']} OF 38 PLAYED</span><span class="badge">POINTS {projection['points']:.0f} PROJECTED</span>
<span class="badge">UPDATED DAILY</span></div>""", unsafe_allow_html=True)

tabs = st.tabs(["Overview", "Season forecast", "Players", "Match stats", "Model accuracy", "Sources & method"])

# ---------------------------------------------------------------- overview

with tabs[0]:
    c = st.columns(4)
    c[0].metric("Won · drawn · lost", f"{record['wins']}–{record['draws']}–{record['losses']}")
    c[1].metric("Points", record["points"])
    c[2].metric("Projected points", f"{projection['points']:.0f}", help=f"80% range {projection['points_low']}–{projection['points_high']}")
    c[3].metric("Projected goals", f"{projection['goals_for']:.0f}", help=f"80% range {projection['goals_for_low']}–{projection['goals_for_high']}")
    played = pd.DataFrame(info["played"])
    fixtures = pd.DataFrame(info["fixtures"])
    fig = go.Figure()
    if not played.empty:
        played["points"] = played.result.map({"W": 3, "D": 1, "L": 0})
        fig.add_trace(go.Scatter(x=list(range(0, len(played) + 1)), y=[0] + played.points.cumsum().tolist(),
                                 mode="lines+markers", name="Points won", line=dict(color=BLUE, width=2), marker=dict(size=8)))
    if not fixtures.empty:
        path = record["points"] + (3 * fixtures.win + fixtures.draw).cumsum()
        fig.add_trace(go.Scatter(x=list(range(record["played"], 39)), y=[record["points"]] + path.tolist(),
                                 mode="lines", name="Expected from here", line=dict(color=BLUE, width=2, dash="dot")))
    style(fig, xaxis_title="League matches played", yaxis_title="Cumulative points")
    st.plotly_chart(fig, width="stretch")
    left, right = st.columns(2)
    with left:
        st.markdown("**Results**")
        if played.empty:
            st.caption("No league matches played yet.")
        else:
            shown = played.assign(score=played.goals_for.astype(str) + "–" + played.goals_against.astype(str))
            st.dataframe(shown[["date", "opponent", "venue", "score", "result"]].iloc[::-1], hide_index=True, width="stretch")
    with right:
        st.markdown("**Next fixtures**")
        if fixtures.empty:
            st.caption("Season complete.")
        else:
            nxt = fixtures.head(6).assign(Win=lambda f: f.win.map(pct), Draw=lambda f: f.draw.map(pct), Loss=lambda f: f.loss.map(pct))
            st.dataframe(nxt[["date", "opponent", "venue", "Win", "Draw", "Loss"]], hide_index=True, width="stretch")

# ---------------------------------------------------------------- season forecast

with tabs[1]:
    st.subheader("Where the season is heading")
    c = st.columns(3)
    c[0].metric("Final points", f"{projection['points']:.1f}", help="Mean of the forecast")
    c[0].caption(f"80% range {projection['points_low']}–{projection['points_high']}")
    c[1].metric("Goals scored", f"{projection['goals_for']:.0f}")
    c[1].caption(f"80% range {projection['goals_for_low']}–{projection['goals_for_high']} · {record['goals_for']} so far")
    c[2].metric("Goals conceded", f"{projection['goals_against']:.0f}")
    c[2].caption(f"80% range {projection['goals_against_low']}–{projection['goals_against_high']} · {record['goals_against']} so far")

    st.markdown("**How the forecast has changed**")
    prog = pd.DataFrame(info["progression"])
    measure = st.radio("Show", ["Points", "Goals scored", "Goals conceded"], horizontal=True, key="prog")
    col = {"Points": "points", "Goals scored": "goals_for", "Goals conceded": "goals_against"}[measure]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=prog.matches_played, y=prog[f"{col}_high"], mode="lines", line=dict(width=0),
                             showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=prog.matches_played, y=prog[f"{col}_low"], mode="lines", line=dict(width=0),
                             fill="tonexty", fillcolor="rgba(57,135,229,.22)", name="80% range"))
    fig.add_trace(go.Scatter(x=prog.matches_played, y=prog[col], mode="lines+markers", name=f"Projected {measure.lower()}",
                             line=dict(color=BLUE, width=2), marker=dict(size=8)))
    style(fig, xaxis_title="League matches played when the forecast was made", yaxis_title=f"Projected final {measure.lower()}")
    st.plotly_chart(fig, width="stretch")
    st.caption("Each point re-runs today's trained model with only the results known at that moment. "
               "0 is the preseason forecast.")

    st.markdown("**Remaining fixtures**")
    if not fixtures.empty:
        table = fixtures.assign(Win=fixtures.win.map(pct), Draw=fixtures.draw.map(pct), Loss=fixtures.loss.map(pct),
                                **{"Expected goals for": fixtures.xg_for.round(2), "Expected goals against": fixtures.xg_against.round(2)})
        st.dataframe(table[["round", "date", "opponent", "venue", "Win", "Draw", "Loss", "Expected goals for",
                            "Expected goals against"]], hide_index=True, width="stretch")

    st.markdown(f"**Projected {league_name} table**")
    league_table = pd.DataFrame(clubs_data["table"])
    fig = go.Figure()
    for highlight in (False, True):
        part = league_table[league_table.club.eq(club) == highlight]
        fig.add_trace(go.Scatter(
            x=part.projected_points, y=part.club, mode="markers", name=club if highlight else "Other clubs",
            marker=dict(size=10, color=BLUE if highlight else MUTED, line=dict(color="#100b23", width=2)),
            error_x=dict(type="data", symmetric=False, array=part.points_high - part.projected_points,
                         arrayminus=part.projected_points - part.points_low, color=BLUE if highlight else MUTED, thickness=2),
            hovertemplate="%{y}: %{x:.1f} points<extra></extra>"))
    style(fig, height=560, xaxis_title="Projected final points (dot) with 80% range", hovermode="closest")
    fig.update_yaxes(categoryorder="array", categoryarray=league_table.club.tolist()[::-1])
    st.plotly_chart(fig, width="stretch")
    shown = league_table.assign(position=range(1, len(league_table) + 1))
    st.dataframe(shown[["position", "club", "played", "points", "goal_difference", "projected_points", "points_low",
                        "points_high", "projected_goals_for", "projected_goals_against"]].round(1),
                 hide_index=True, width="stretch")

# ---------------------------------------------------------------- players

with tabs[2]:
    entry = players_data.get(club, {})
    st.subheader("League goal projections")
    if entry.get("status") != "ok":
        st.info(entry.get("status", "No player data for this club."))
    elif not entry.get("forecasts"):
        st.info("No league goals recorded yet this season.")
    else:
        fc = pd.DataFrame(entry["forecasts"]).sort_values("projected")
        fig = go.Figure()
        fig.add_trace(go.Bar(x=fc.goals, y=fc.player, orientation="h", name="Scored so far",
                             marker=dict(color=BLUE, cornerradius=4), hovertemplate="%{y}: %{x} so far<extra></extra>"))
        fig.add_trace(go.Bar(x=fc.projected - fc.goals, y=fc.player, orientation="h", name="Projected still to come",
                             marker=dict(color="rgba(57,135,229,.35)", cornerradius=4),
                             error_x=dict(type="data", symmetric=False, array=fc.high - fc.projected,
                                          arrayminus=fc.projected - fc.low, color=INK_2, thickness=1.5),
                             customdata=fc[["projected", "low", "high"]],
                             hovertemplate="%{y}: %{customdata[0]:.1f} projected (80% range %{customdata[1]:.0f}–%{customdata[2]:.0f})<extra></extra>"))
        style(fig, height=max(260, 38 * len(fc) + 80), barmode="stack", bargap=0.35, hovermode="closest",
              xaxis_title="League goals this season")
        st.plotly_chart(fig, width="stretch")
        st.dataframe(fc.iloc[::-1].assign(**{"Last season's share of club goals": fc.previous_share.iloc[::-1].map(
                         lambda v: "—" if pd.isna(v) else pct(v))})[["player", "goals", "projected", "low", "high",
                                                                      "Last season's share of club goals"]].round(1),
                     hide_index=True, width="stretch")
        st.caption(f"About {entry['unassigned_remaining']:.0f} more {club} league goals are expected from players who "
                   "have not scored yet, own goals, or new signings. Ranges are 80% intervals; the model shares the "
                   "club's expected remaining goals out by each scorer's record, shrunk toward last season.")
    if entry.get("all_competitions"):
        st.markdown("**Goals in all competitions (as reported on Wikipedia)**")
        rows = []
        for r in entry["all_competitions"]:
            rows.append({"player": r["player"], "total": r["goals"], "penalties": r["penalties"],
                         **{("League" if k == "league" else k): v for k, v in r["by_competition"].items()}})
        table = pd.DataFrame(rows).fillna(0)
        first = [c for c in ("player", "total", "League") if c in table.columns]
        st.dataframe(table[first + [c for c in table.columns if c not in first]], hide_index=True, width="stretch")
        st.caption("League goals are checked against official results; cup and European goals are taken as reported. "
                   "Pre-season friendlies are excluded.")
    if entry.get("league_goal_minutes"):
        minutes = pd.Series(entry["league_goal_minutes"]).clip(upper=90)
        bins = pd.cut(minutes, [0, 15, 30, 45, 60, 75, 90], include_lowest=True,
                      labels=["0–15", "16–30", "31–45+", "46–60", "61–75", "76–90+"]).value_counts().sort_index()
        fig = go.Figure(go.Bar(x=bins.index.astype(str), y=bins.values, marker=dict(color=BLUE, cornerradius=4),
                               hovertemplate="%{x} min: %{y} goals<extra></extra>"))
        style(fig, height=260, xaxis_title="Minute of league goal", yaxis_title="Goals", hovermode="closest")
        st.markdown("**When the goals come**")
        st.plotly_chart(fig, width="stretch")

    with st.expander("Upload your own match-level player data (optional)"):
        st.caption("A CSV with one row per player per match (matchday, date, player, minutes, plus optional metrics) "
                   "unlocks per-90 progress and an experimental ridge-regression forecast trained on historical "
                   "StatsBomb data. Uploads stay in your browser session.")
        st.download_button("Download CSV template", (ROOT / "examples" / "current_player_match_template.csv").read_bytes(),
                           file_name="player_match_template.csv", mime="text/csv")
        uploaded = st.file_uploader("Player match CSV", type=["csv"])
        final_rounds = {int(str(r["round"]).rsplit(" ", 1)[-1]) for r in info["played"] if str(r.get("round", "")).strip()}
        if uploaded is not None:
            try:
                rows = load_player_csv(uploaded.getvalue(), final_rounds)
            except (ValueError, TypeError) as exc:
                st.error(str(exc))
            else:
                name = st.selectbox("Player", sorted(rows.player.unique()))
                metrics = [m for m in OPTIONAL if m in rows.columns] + ["minutes"]
                metric = st.selectbox("Metric", metrics, format_func=lambda m: m.replace("_", " ").title())
                rounds = sorted(final_rounds)
                if len(rounds) < 5:
                    st.info("At least five completed matches are needed for this model.")
                else:
                    history = pd.concat([pd.read_csv(ROOT / "data" / "derived" / "appearances.csv"),
                                         pd.read_csv(ROOT / "data" / "training" / "leverkusen_2023_24_appearances.csv")])
                    try:
                        result = ForecastModel(history, (metric,)).predict(rows[rows.player == name], metric, rounds, len(rounds))
                    except ValueError as exc:
                        st.info(str(exc))
                    else:
                        a, b, c = st.columns(3)
                        a.metric("Observed", f"{result['observed']:.1f}")
                        b.metric("Projected final", f"{result['projected']:.1f}")
                        c.metric("Historical 80% band", f"{result['lower']:.1f}–{result['upper']:.1f}")

# ---------------------------------------------------------------- match stats

with tabs[3]:
    home = matches.home.eq(club)
    mine = matches[home | matches.away.eq(club)].copy()
    if mine.empty:
        st.info("No league matches played yet.")
    else:
        is_home = mine.home.eq(club)
        side = lambda stat, own=True: mine[f"home_{stat}"].where(is_home == own, mine[f"away_{stat}"])
        stats = pd.DataFrame({
            "date": mine.date, "opponent": mine.away.where(is_home, mine.home), "venue": is_home.map({True: "Home", False: "Away"}),
            "goals_for": side("goals"), "goals_against": side("goals", False), "ht_for": side("ht"), "ht_against": side("ht", False),
            "xg_for": side("xg"), "xg_against": side("xg", False), "shots": side("shots"), "shots_against": side("shots", False),
            "on_target": side("sot"), "on_target_against": side("sot", False), "corners": side("corners"),
            "fouls": side("fouls"), "yellow": side("yellow"), "red": side("red")}).sort_values("date").reset_index(drop=True)
        n = len(stats)
        c = st.columns(4)
        c[0].metric("Goals vs expected goals", f"{stats.goals_for.sum():.0f} vs {stats.xg_for.sum():.1f}")
        c[1].metric("Conceded vs expected", f"{stats.goals_against.sum():.0f} vs {stats.xg_against.sum():.1f}")
        c[2].metric("Shots on target per game", f"{stats.on_target.mean():.1f}", help=f"Opponents: {stats.on_target_against.mean():.1f}")
        accuracy = stats.on_target.sum() / max(stats.shots.sum(), 1)
        c[3].metric("Shot accuracy", pct(accuracy), help="Share of shots that hit the target")

        left, right = st.columns(2)
        x = list(range(1, n + 1))
        for column, title, actual, expected in ((left, "Attack: goals vs expected goals", "goals_for", "xg_for"),
                                                (right, "Defence: conceded vs expected", "goals_against", "xg_against")):
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=x, y=stats[actual].cumsum(), mode="lines+markers", name="Actual",
                                     line=dict(color=BLUE, width=2), marker=dict(size=8)))
            fig.add_trace(go.Scatter(x=x, y=stats[expected].cumsum(), mode="lines+markers", name="Expected (xG)",
                                     line=dict(color=ORANGE, width=2, dash="dot"), marker=dict(size=8)))
            style(fig, height=300, xaxis_title="League match", yaxis_title="Cumulative goals")
            with column:
                st.markdown(f"**{title}**")
                st.plotly_chart(fig, width="stretch")
        st.caption("Expected goals (xG) estimate how many goals the chances created were worth. "
                   "Scoring well above xG usually means finishing that is hard to sustain.")

        st.markdown("**Splits**")
        halves = pd.DataFrame({"": ["First half", "Second half"],
                               "Scored": [stats.ht_for.sum(), stats.goals_for.sum() - stats.ht_for.sum()],
                               "Conceded": [stats.ht_against.sum(), stats.goals_against.sum() - stats.ht_against.sum()]})
        points = stats.apply(lambda r: 3 if r.goals_for > r.goals_against else 1 if r.goals_for == r.goals_against else 0, axis=1)
        venues = stats.assign(points=points).groupby("venue").agg(
            played=("points", "size"), points_per_game=("points", "mean"), scored=("goals_for", "sum"),
            conceded=("goals_against", "sum"), xg_per_game=("xg_for", "mean")).round(2).reset_index()
        a, b = st.columns(2)
        a.dataframe(halves, hide_index=True, width="stretch")
        b.dataframe(venues, hide_index=True, width="stretch")

        st.markdown(f"**{club} against the rest of the {league_name}**")
        options = {"Expected goals per game": ("xg", True), "Expected goals against per game": ("xg", False),
                   "Goals per game": ("goals", True), "Goals conceded per game": ("goals", False),
                   "Shots on target per game": ("sot", True), "Shots on target faced per game": ("sot", False),
                   "Shots per game": ("shots", True), "Corners per game": ("corners", True),
                   "Fouls per game": ("fouls", True), "Yellow cards per game": ("yellow", True)}
        choice = st.selectbox("Compare", list(options))
        stat, own = options[choice]
        per_club = []
        for team in sorted(set(matches.home) | set(matches.away)):
            h, a_ = matches[matches.home == team], matches[matches.away == team]
            values = pd.concat([h[f"home_{stat}" if own else f"away_{stat}"], a_[f"away_{stat}" if own else f"home_{stat}"]])
            per_club.append({"club": team, "value": values.mean()})
        per_club = pd.DataFrame(per_club).sort_values("value")
        fig = go.Figure(go.Bar(x=per_club.value, y=per_club.club, orientation="h",
                               marker=dict(color=[BLUE if t == club else MUTED for t in per_club.club], cornerradius=4),
                               hovertemplate="%{y}: %{x:.2f}<extra></extra>"))
        style(fig, height=560, xaxis_title=choice, hovermode="closest")
        st.plotly_chart(fig, width="stretch")

        st.markdown("**Match by match**")
        table = stats.assign(score=stats.goals_for.astype(str) + "–" + stats.goals_against.astype(str),
                             half_time=stats.ht_for.astype("Int64").astype(str) + "–" + stats.ht_against.astype("Int64").astype(str))
        st.dataframe(table[["date", "opponent", "venue", "score", "half_time", "xg_for", "xg_against", "shots",
                            "on_target", "shots_against", "on_target_against", "corners", "fouls", "yellow", "red"]],
                     hide_index=True, width="stretch")

# ---------------------------------------------------------------- model accuracy

with tabs[4]:
    data_info = model_info["data"]
    st.subheader("Is the model any good?")
    st.markdown(f"Every number here comes from seasons the model never saw while it was being built: settings were chosen on "
                f"{data_info['validation_seasons']}, and each test season ({data_info['test_seasons']}) is predicted by a "
                "model trained only on the seasons before it.")
    st.markdown("**Match predictions** (home win / draw / away win)")
    overall = pd.DataFrame(model_info["evaluation"]["overall"])
    st.dataframe(overall.rename(columns={"log_loss": "Log loss", "rps": "Ranked prob. score", "brier": "Brier score",
                                         "accuracy": "Accuracy", "matches": "Matches"}).round(4),
                 hide_index=True, width="stretch")
    st.caption("Lower log loss, Brier and ranked probability scores are better. Closing bookmaker odds are the "
               "toughest benchmark in football forecasting; base rates show what knowing nothing about the teams scores.")
    seasons = pd.DataFrame(model_info["evaluation"]["per_season"])
    fig = go.Figure()
    for name, color in (("Trained model (goals + shots on target)", BLUE), ("Bookmakers (closing odds)", ORANGE),
                        ("Goals-only model", AQUA)):
        part = seasons[seasons.model == name]
        fig.add_trace(go.Scatter(x=part.season.map(lambda s: f"{s}/{(s + 1) % 100:02d}"), y=part.log_loss,
                                 mode="lines+markers", name=name, line=dict(color=color, width=2), marker=dict(size=8)))
    style(fig, height=320, yaxis_title="Log loss (lower is better)")
    st.plotly_chart(fig, width="stretch")

    calibration = pd.DataFrame(model_info["evaluation"]["calibration"])
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines", name="Perfect calibration", line=dict(color=MUTED, dash="dot")))
    fig.add_trace(go.Scatter(x=calibration.predicted, y=calibration.observed, mode="lines+markers", name="Model",
                             line=dict(color=BLUE, width=2), marker=dict(size=8), customdata=calibration.matches,
                             hovertemplate="Predicted %{x:.0%}, happened %{y:.0%} (%{customdata} matches)<extra></extra>"))
    style(fig, height=320, xaxis_title="Predicted home-win probability", yaxis_title="Share of those matches won at home",
          hovermode="closest")
    fig.update_xaxes(tickformat=".0%"); fig.update_yaxes(tickformat=".0%")
    st.markdown("**Calibration:** when the model says 60%, does it happen about 60% of the time?")
    st.plotly_chart(fig, width="stretch")

    st.markdown("**Season totals** (every club, every test season)")
    team = pd.DataFrame(model_info["team_backtest"])
    team = team.rename(columns={"matches_played": "Matches played", "points_mae": "Points error (model)",
                                "naive_points_mae": "Points error (naive)", "goals_mae": "Goals error (model)",
                                "naive_goals_mae": "Goals error (naive)", "points_coverage": "Points inside 80% range",
                                "goals_coverage": "Goals inside 80% range", "forecasts": "Forecasts"})
    for column in ("Points inside 80% range", "Goals inside 80% range"):
        team[column] = team[column].map(pct)
    st.dataframe(team.round(2), hide_index=True, width="stretch")
    st.caption("Errors are average absolute differences from the final total. Naive = keep the current pace "
               "(or repeat last season's total before a ball is kicked).")

    first_test = int(data_info["test_seasons"][:4])
    mine = backtest[(backtest.club == club) & (backtest.matches_played == 7) & (backtest.season >= first_test)]
    if not mine.empty:
        st.markdown(f"**{club}: forecast after 7 matches vs what happened**")
        labels = mine.season.map(lambda s: f"{s}/{(s + 1) % 100:02d}")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=labels, y=mine.forecast_points, mode="markers", name="Forecast after 7 matches",
                                 marker=dict(size=10, color=BLUE),
                                 error_y=dict(type="data", symmetric=False, array=mine.forecast_points_high - mine.forecast_points,
                                              arrayminus=mine.forecast_points - mine.forecast_points_low, color=BLUE, thickness=2)))
        fig.add_trace(go.Scatter(x=labels, y=mine.actual_points, mode="markers", name="Actual final points",
                                 marker=dict(size=10, color=ORANGE, symbol="diamond", line=dict(color="#100b23", width=2))))
        style(fig, height=320, yaxis_title="Final points")
        st.plotly_chart(fig, width="stretch")

    st.markdown("**Player goal projections**")
    player_eval = model_info["player_model"]["evaluation"]
    pe = pd.DataFrame(player_eval["test"]).rename(columns={
        "matches_played": "Club matches played", "model_mae": "Error (model)", "pace_mae": "Error (keep pace)",
        "no_more_goals_mae": "Error (no more goals)", "coverage": "Inside 80% range", "players": "Player forecasts"})
    pe["Inside 80% range"] = pe["Inside 80% range"].map(pct)
    st.dataframe(pe.round(2), hide_index=True, width="stretch")
    st.caption(f"Fitted on {', '.join(player_eval['train_seasons'])}; tested on {', '.join(player_eval['test_seasons'])} "
               f"({player_eval['club_seasons_used']} club seasons with complete scorer data). "
               "Errors are average absolute differences in final league goals for players who had scored by that point.")

    with st.expander("Model details"):
        details = model_info["model"]
        params = model_info["params"]
        st.markdown(f"- Learner chosen on validation seasons: **{details['learner'].replace('_', ' ')}**\n"
                    f"- Rating update weight α = {params['alpha']} (newest match), summer carry-over = {params['carry']}\n"
                    f"- Dixon–Coles low-score correction ρ = {details['dixon_coles_rho']:.3f}\n"
                    f"- Season-strength dispersion = {details['goal_dispersion']:.4f}\n"
                    f"- Player model: prior strength {model_info['player_model']['params']['strength']} club goals, "
                    f"last-season weight {model_info['player_model']['params']['weight']}, baseline share "
                    f"{model_info['player_model']['params']['baseline']}")
        if "coefficients" in details:
            st.dataframe(pd.DataFrame(details["coefficients"].items(), columns=["term", "coefficient"]).round(4),
                         hide_index=True)
        st.dataframe(pd.DataFrame(model_info["tuning"]).round(4), hide_index=True, width="stretch")

# ---------------------------------------------------------------- sources

with tabs[5]:
    st.subheader("Sources and method")
    st.markdown(f"""
**Results and match stats:** [football-data.co.uk](https://www.football-data.co.uk/) season files
({model_info['data']['seasons']}): scores, half-time scores, shots, shots on target, corners, fouls, cards, closing
odds and, from 2026/27, expected goals. The site states no reuse licence, so raw files are downloaded at build time and
only derived numbers are stored here.

**Fixture schedule:** [openfootball/football.json](https://github.com/openfootball/football.json) (CC0 public domain),
used for matches not yet played. Club names are matched to football-data.co.uk automatically, and both sources'
scores are cross-checked.

**Scorers:** English Wikipedia club season pages, [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
A league match only counts when its listed scorers add up to the official score, so incomplete pages are caught.

**Match model:** each club has slowly updating ratings for goals and shots on target, scored and conceded. A Poisson
regression turns the two teams' ratings and home advantage into expected goals, with a Dixon–Coles correction for
low-scoring draws. Gradient-boosted trees were tested too and did worse on validation seasons.

**Season totals:** every remaining fixture is forecast, and thousands of simulated seasons, in which each club's
strength can drift by an amount measured on past seasons, give the 80% ranges.

**Players:** a scorer's share of club goals is estimated by shrinking his current share toward last season's share and
a league baseline, then applied to the goals the club is still expected to score.

**Not included:** injuries, transfers, minutes played and player-level xG (no source with clear reuse rights),
and cup or European fixtures in the season forecast.
""")
