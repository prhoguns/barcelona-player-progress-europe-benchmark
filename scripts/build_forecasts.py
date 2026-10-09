"""Build every forecast, backtest and stats file the dashboard reads.

Usage:
    python scripts/build_forecasts.py                     # full rebuild: tune, train, evaluate, forecast
    python scripts/build_forecasts.py --league la-liga    # one league only
    python scripts/build_forecasts.py --quick             # reuse saved hyperparameters (dashboard refresh)
    python scripts/build_forecasts.py --refresh-wikipedia-history

Outputs go to data/current/<league>/ plus a shared forecast archive.
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import match_model as mm  # noqa: E402
from src import player_model as pm  # noqa: E402
from src import schedule  # noqa: E402
from src import season_forecast as sf  # noqa: E402
from src import wiki_season as ws  # noqa: E402
from src.football_data import load_history  # noqa: E402
from src.leagues import CURRENT_SEASON, LEAGUES, WIKIPEDIA, season_label  # noqa: E402

OUT = ROOT / "data" / "current"
WIKI = ROOT / "data" / "derived" / "wikipedia"
ARCHIVE = OUT / "forecast_archive.csv"
TRAIN_FROM = 2011            # 2010/11 only warms up the ratings
VALIDATION = [2012, 2013, 2014]
TEST = list(range(2015, CURRENT_SEASON))
BACKTEST = list(range(2013, CURRENT_SEASON))
PLAYER_TRAIN = list(range(2013, 2019))
ALPHAS, CARRIES = (0.01, 0.015, 0.02, 0.03, 0.05, 0.08), (0.7, 0.85, 0.95)
STAT_COLUMNS = ["shots", "sot", "corners", "fouls", "yellow", "red", "xg", "ht"]


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def clean(value):
    """JSON-safe conversion for numpy and pandas values."""
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if np.isnan(value) else round(float(value), 4)
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean(payload), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- match model

def tune(history: pd.DataFrame) -> tuple[dict, list[dict]]:
    """Pick rating decay, summer carry-over and learner on validation seasons only."""
    trials = []
    for alpha, carry in itertools.product(ALPHAS, CARRIES):
        features = mm.pre_match_features(history, alpha, carry)
        score = mm.score_predictions(mm.walk_forward(features, VALIDATION, TRAIN_FROM))
        trials.append({"alpha": alpha, "carry": carry, "learner": "poisson_glm", **score})
    best = min(trials, key=lambda t: t["log_loss"])
    features = mm.pre_match_features(history, best["alpha"], best["carry"])
    boosted = mm.score_predictions(mm.walk_forward(features, VALIDATION, TRAIN_FROM, learner="gradient_boosting"))
    trials.append({"alpha": best["alpha"], "carry": best["carry"], "learner": "gradient_boosting", **boosted})
    winner = min(trials, key=lambda t: t["log_loss"])
    return {"alpha": winner["alpha"], "carry": winner["carry"], "learner": winner["learner"],
            "train_from": TRAIN_FROM}, trials


def evaluate_matches(history: pd.DataFrame, features: pd.DataFrame, params: dict) -> dict:
    """Out-of-sample comparison on test seasons never used for tuning."""
    test = history[history.season.isin(TEST)]
    outcome = mm.outcome_index(test.home_goals.to_numpy(), test.away_goals.to_numpy())
    candidates = {
        "Trained model (goals + shots on target)": mm.walk_forward(features, TEST, TRAIN_FROM, mm.FULL, params["learner"]),
        "Goals-only model": mm.walk_forward(features, TEST, TRAIN_FROM, mm.GOALS_ONLY, params["learner"]),
        "Gradient boosting (same features)": mm.walk_forward(features, TEST, TRAIN_FROM, mm.FULL, "gradient_boosting"),
    }
    if params["learner"] == "gradient_boosting":
        candidates["Poisson GLM (same features)"] = mm.walk_forward(features, TEST, TRAIN_FROM, mm.FULL, "poisson_glm")
    rows, per_season = [], []
    for name, predictions in candidates.items():
        rows.append({"model": name, **mm.score_predictions(predictions)})
        for season, group in predictions.groupby("season"):
            per_season.append({"model": name, "season": season, **mm.score_predictions(group)})
    base = []
    for season in TEST:
        prior = history[(history.season >= TRAIN_FROM) & (history.season < season)]
        freq = np.bincount(mm.outcome_index(prior.home_goals.to_numpy(), prior.away_goals.to_numpy()), minlength=3)
        base.append(np.tile(freq / freq.sum(), (int((history.season == season).sum()), 1)))
    rows.append({"model": "Base rates (home/draw/away frequencies)", **mm.scores(np.vstack(base), outcome)})
    market = mm.market_probabilities(test)
    rows.append({"model": "Bookmakers (closing odds)", **mm.scores(market, outcome)})
    for season in TEST:
        mask = (test.season == season).to_numpy()
        per_season.append({"model": "Bookmakers (closing odds)", "season": season, **mm.scores(market[mask], outcome[mask])})
    predictions = candidates["Trained model (goals + shots on target)"]
    bins = pd.cut(predictions.p_home, np.linspace(0, 1, 11))
    calibration = predictions.assign(won=predictions.home_goals > predictions.away_goals).groupby(bins, observed=True).agg(
        predicted=("p_home", "mean"), observed=("won", "mean"), matches=("won", "size")).reset_index(drop=True)
    return {"overall": rows, "per_season": per_season, "calibration": calibration.to_dict("records")}


# ---------------------------------------------------------------- wikipedia

def wikipedia_data(league_key: str, history: pd.DataFrame, refresh_history: bool) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validated scorer events and match coverage for every mapped club season."""
    goals_path, coverage_path = WIKI / f"{league_key}_goals.csv", WIKI / f"{league_key}_coverage.csv"
    cached_goals = pd.read_csv(goals_path, keep_default_na=False) if goals_path.exists() and not refresh_history else None
    cached_cov = pd.read_csv(coverage_path) if coverage_path.exists() and not refresh_history else None
    seasons = BACKTEST + [CURRENT_SEASON] if cached_goals is None else [CURRENT_SEASON]
    wanted = {}
    for season in seasons:
        league = history[history.season == season]
        for club in sorted(set(league.home) | set(league.away)):
            if club in WIKIPEDIA:
                wanted[ws.page_title(season, WIKIPEDIA[club])] = (season, club)
    log(f"  fetching {len(wanted)} Wikipedia season pages")
    pages = ws.fetch_pages(list(wanted))
    events, coverage = [], []
    for title, (season, club) in wanted.items():
        text = pages.get(title)
        if not text:
            continue
        found, covered = ws.club_season(text, club, sf.club_matches(history, season, club))
        tag = {"league": league_key, "season": season, "club": club}
        events.append(found.assign(**tag))
        coverage.append(covered.assign(**tag))
    events = pd.concat(events, ignore_index=True) if events else pd.DataFrame()
    coverage = pd.concat(coverage, ignore_index=True) if coverage else pd.DataFrame()
    if cached_goals is not None:
        events = pd.concat([cached_goals[cached_goals.season != CURRENT_SEASON], events], ignore_index=True)
        coverage = pd.concat([cached_cov[cached_cov.season != CURRENT_SEASON], coverage], ignore_index=True)
    # Flags arrive as text from the CSV cache or as objects after concatenation; restore real booleans.
    for column in ("penalty", "own_goal", "validated"):
        events[column] = events[column].astype(str).eq("True")
    for column in ("found", "complete"):
        coverage[column] = coverage[column].astype(str).eq("True")
    events["player_id"] = events.player_id.fillna("").astype(str)
    WIKI.mkdir(parents=True, exist_ok=True)
    events.to_csv(goals_path, index=False)
    coverage.to_csv(coverage_path, index=False)
    return events, coverage


def player_training_rows(events, coverage, team_backtest, league_key) -> pd.DataFrame:
    valid = pm.valid_club_seasons(coverage)
    priors = pm.previous_shares(events, coverage, valid)
    rows = []
    for row in team_backtest[team_backtest.matches_played.isin(pm.CHECKPOINTS)].itertuples(index=False):
        key = (league_key, row.season, row.club)
        if key not in valid:
            continue
        cov = coverage[(coverage.league == key[0]) & (coverage.season == key[1]) & (coverage.club == key[2])]
        if len(cov) != 38:
            continue
        ev = events[(events.league == key[0]) & (events.season == key[1]) & (events.club == key[2])]
        remaining = row.forecast_goals_for - row.observed_goals_for
        rows.append(pm.checkpoint_rows(ev, cov, key, row.matches_played, priors.get(key, {}), remaining, final=True))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


# ---------------------------------------------------------------- league build

def build_league(league_key: str, quick: bool, refresh_wikipedia_history: bool) -> pd.DataFrame:
    config = LEAGUES[league_key]
    out = OUT / league_key
    out.mkdir(parents=True, exist_ok=True)
    log(f"{config['name']}: loading results")
    history = load_history(config["football_data"], CURRENT_SEASON)
    played = history[history.season == CURRENT_SEASON]
    fixtures = schedule.season_fixtures(schedule.fetch(config["openfootball"], CURRENT_SEASON), played)
    clubs = sorted(set(fixtures.home))

    saved = out / "model.json"
    if quick and saved.exists():
        previous = json.loads(saved.read_text())
        params, trials = previous["params"], previous["tuning"]
    else:
        log("  tuning on validation seasons")
        params, trials = tune(history)
    log(f"  params {params}")
    features = mm.pre_match_features(history, params["alpha"], params["carry"])

    today = date.today().isoformat()
    dispersion_reqs = sf.dispersion_requests(history, [s for s in range(TRAIN_FROM + 1, CURRENT_SEASON)])
    club_cutoffs = {club: [sf.checkpoint_cutoff(sf.club_matches(history, CURRENT_SEASON, club), k)
                           if k else sf.day_before(fixtures.date.min())
                           for k in range(len(sf.club_matches(history, CURRENT_SEASON, club)) + 1)]
                    for club in clubs}
    requests = set(dispersion_reqs) | {(CURRENT_SEASON, today)}
    requests |= {(CURRENT_SEASON, c) for cuts in club_cutoffs.values() for c in cuts}
    if not quick:
        requests |= sf.backtest_requests(history, BACKTEST)
    log(f"  rating snapshots for {len(requests)} checkpoints")
    snapshots = mm.ratings_snapshots(history, params["alpha"], params["carry"], requests,
                                     extra_clubs={CURRENT_SEASON: set(clubs)})
    frozen = sf.frozen_remaining(snapshots, dispersion_reqs)
    model = sf.fit_for_season(features, frozen, params, CURRENT_SEASON)

    if quick and saved.exists():
        evaluation, team_summary = previous["evaluation"], previous["team_backtest"]
        team_backtest = pd.read_csv(out / "team_backtest.csv")
        player_params, player_eval = previous["player_model"]["params"], previous["player_model"]["evaluation"]
    else:
        log("  out-of-sample evaluation")
        evaluation = evaluate_matches(history, features, params)
        log("  season backtest for every club")
        models = {season: sf.fit_for_season(features, frozen, params, season) for season in BACKTEST}
        team_backtest = sf.backtest(history, models, snapshots, BACKTEST)
        team_summary = sf.summarize_backtest(team_backtest[team_backtest.season.isin(TEST)]).to_dict("records")

    log("  current-season forecasts")
    now = snapshots[(CURRENT_SEASON, today)]
    club_payload, archive_rows = {}, []
    for club in clubs:
        mine = fixtures[(fixtures.home == club) | (fixtures.away == club)].reset_index(drop=True)
        done = sf.club_matches(history, CURRENT_SEASON, club)
        upcoming = mine[mine.status == "scheduled"]
        future = sf.fixture_forecasts(now, model, upcoming[["round", "date", "home", "away"]], club)
        record = sf.club_record(done, club)
        projection = sf.totals(record, future, model)
        progression = []
        for k, cutoff in enumerate(club_cutoffs[club]):
            rest = pd.concat([done.iloc[k:][["home", "away"]], upcoming[["home", "away"]]], ignore_index=True)
            step = sf.totals(sf.club_record(done.iloc[:k], club),
                             sf.fixture_forecasts(snapshots[(CURRENT_SEASON, cutoff)], model, rest, club), model)
            progression.append({"matches_played": k, "as_of": cutoff, **step})
        archive_rows.append({"run_date": today, "league": league_key, "club": club, "matches_played": record["played"],
                             **{k: projection[k] for k in ("points", "points_low", "points_high", "goals_for",
                                                           "goals_against")}})
        played_rows = []
        rounds = {(r.home, r.away): r.round for r in mine.itertuples(index=False)}
        for match in done.itertuples(index=False):
            home = match.home == club
            gf, ga = (match.home_goals, match.away_goals) if home else (match.away_goals, match.home_goals)
            played_rows.append({"round": rounds.get((match.home, match.away), ""), "date": match.date,
                                "opponent": match.away if home else match.home,
                                "venue": "Home" if home else "Away", "goals_for": gf, "goals_against": ga,
                                "result": "W" if gf > ga else "D" if gf == ga else "L"})
        club_payload[club] = {
            "record": record, "projection": projection, "progression": progression, "played": played_rows,
            "fixtures": [{"round": r["round"], "date": r["date"],
                          "opponent": r["away"] if r["home"] == club else r["home"],
                          "venue": "Home" if r["home"] == club else "Away",
                          "win": r["win"], "draw": r["draw"], "loss": r["loss"],
                          "xg_for": r["xg_for"], "xg_against": r["xg_against"]} for r in future.to_dict("records")],
            "rating": now.teams[club],
        }
    table = sorted(({"club": c, "played": v["record"]["played"], "points": v["record"]["points"],
                     "goal_difference": v["record"]["goals_for"] - v["record"]["goals_against"],
                     "projected_points": v["projection"]["points"], "points_low": v["projection"]["points_low"],
                     "points_high": v["projection"]["points_high"],
                     "projected_goals_for": v["projection"]["goals_for"],
                     "projected_goals_against": v["projection"]["goals_against"]} for c, v in club_payload.items()),
                   key=lambda r: -r["projected_points"])

    log("  player data from Wikipedia")
    events, coverage = wikipedia_data(league_key, history, refresh_wikipedia_history)
    if not (quick and saved.exists()):
        rows = player_training_rows(events, coverage, team_backtest, league_key)
        train, test = rows[rows.season.isin(PLAYER_TRAIN)], rows[~rows.season.isin(PLAYER_TRAIN)]
        test_params = pm.fit(train)
        player_eval = {"train_seasons": [season_label(s) for s in PLAYER_TRAIN],
                       "test_seasons": sorted({season_label(s) for s in test.season}),
                       "test": pm.evaluate(test, test_params).to_dict("records"),
                       "club_seasons_used": int(rows.groupby(["season", "club"]).ngroups)}
        player_params = pm.fit(rows)
    players_payload = player_forecasts(events, coverage, club_payload, player_params, league_key)

    played.drop(columns=[c for c in played.columns if c.startswith("odds_")]).to_csv(out / "matches.csv", index=False)
    team_backtest.to_csv(out / "team_backtest.csv", index=False)
    write_json(out / "clubs.json", {"league": config["name"], "season": season_label(CURRENT_SEASON),
                                    "as_of": today, "clubs": club_payload, "table": table,
                                    "results_through": played.date.max() if len(played) else None})
    write_json(out / "players.json", players_payload)
    write_json(saved, {
        "league": config["name"], "built_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "params": params, "tuning": trials, "model": model.describe(), "evaluation": evaluation,
        "team_backtest": team_summary,
        "player_model": {"params": player_params, "evaluation": player_eval},
        "data": {"seasons": f"{season_label(int(history.season.min()))}–{season_label(CURRENT_SEASON)}",
                 "matches": int(len(history)), "current_matches": int(len(played)),
                 "test_seasons": f"{season_label(TEST[0])}–{season_label(TEST[-1])}",
                 "validation_seasons": f"{season_label(VALIDATION[0])}–{season_label(VALIDATION[-1])}"},
    })
    return pd.DataFrame(archive_rows)


def player_forecasts(events, coverage, club_payload, params, league_key) -> dict:
    current_events = events[events.season == CURRENT_SEASON]
    current_cov = coverage[coverage.season == CURRENT_SEASON]
    valid = pm.valid_club_seasons(coverage)
    priors = pm.previous_shares(events, coverage, valid)
    payload = {}
    for club, info in club_payload.items():
        cov = current_cov[current_cov.club == club]
        ev = current_events[current_events.club == club]
        key = (league_key, CURRENT_SEASON, club)
        friendly = ev.competition.str.contains("friendl|pre-season|preseason|tour", case=False, regex=True)
        reported = ev[~ev.own_goal & (ev.player_id != "") & ~friendly]
        all_comps = reported.groupby("player_id").agg(player=("player", "first"), goals=("minute", "size"),
                                                      penalties=("penalty", "sum")).reset_index()
        by_comp = reported.groupby(["player_id", "competition"]).size().unstack(fill_value=0)
        minutes = [int(str(m).split("+")[0]) for m in reported[reported.competition == "league"].minute]
        entry = {"page": ws.page_title(CURRENT_SEASON, WIKIPEDIA[club]) if club in WIKIPEDIA else None,
                 "matches_checked": int(len(cov)), "matches_complete": int(cov.complete.sum()) if len(cov) else 0,
                 "all_competitions": [{**r, "by_competition": by_comp.loc[r["player_id"]].to_dict()}
                                      for r in all_comps.sort_values("goals", ascending=False).to_dict("records")],
                 "league_goal_minutes": minutes}
        played = info["record"]["played"]
        if club not in WIKIPEDIA or cov.empty:
            entry["status"] = "No Wikipedia season page with match details was found for this club."
        elif key not in valid or len(cov) != played:
            entry["status"] = (f"Wikipedia scorers add up for {entry['matches_complete']} of {played} league matches, "
                               "so player forecasts are withheld until the page is complete.")
        else:
            entry["status"] = "ok"
            remaining = info["projection"]["goals_for"] - info["record"]["goals_for"]
            rows = pm.checkpoint_rows(ev, cov, key, played, priors.get(key, {}), remaining, final=False)
            if not rows.empty:
                result = pm.forecast(rows, params).sort_values("projected", ascending=False)
                entry["forecasts"] = result[["player_id", "player", "goals", "previous_share", "projected",
                                             "low", "high"]].to_dict("records")
                entry["unassigned_remaining"] = remaining - float((result.projected - result.goals).sum())
        payload[club] = entry
    return {"source": "English Wikipedia club season pages (CC BY-SA 4.0)", "clubs": payload}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--league", choices=sorted(LEAGUES), action="append")
    parser.add_argument("--quick", action="store_true", help="reuse saved hyperparameters and evaluations")
    parser.add_argument("--refresh-wikipedia-history", action="store_true")
    args = parser.parse_args()
    archive = [build_league(key, args.quick, args.refresh_wikipedia_history) for key in (args.league or LEAGUES)]
    archive = pd.concat(archive, ignore_index=True)
    if ARCHIVE.exists():
        previous = pd.read_csv(ARCHIVE)
        known = set(zip(previous.league, previous.club, previous.matches_played))
        archive = archive[[k not in known for k in zip(archive.league, archive.club, archive.matches_played)]]
        archive = pd.concat([previous, archive], ignore_index=True)
    archive.round(3).to_csv(ARCHIVE, index=False)
    log("done")


if __name__ == "__main__":
    main()
