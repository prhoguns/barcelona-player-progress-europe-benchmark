"""Trained league match model: rolling team ratings feeding a goal-rate regression.

Each club carries exponentially weighted averages of goals and shots on target,
for and against. Before every match those ratings become features; a regression
with a Poisson loss predicts each side's goals, and a Dixon-Coles adjustment
corrects the independent-Poisson draw rate. Two learners are compared on
validation seasons: a Poisson GLM and gradient-boosted trees. All features use
only matches played earlier.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.stats import nbinom, poisson
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import PoissonRegressor

STATS = ("gf", "ga", "sotf", "sota")
DEFAULT = {"gf": 1.3, "ga": 1.3, "sotf": 4.3, "sota": 4.3}
FULL = ("attack_goals", "opp_defence_goals", "attack_sot", "opp_defence_sot", "home")
GOALS_ONLY = ("attack_goals", "opp_defence_goals", "home")
MAX_GOALS = 10


@dataclass
class Ratings:
    """Sequential team ratings; `alpha` weights the newest match, `carry` keeps form across summers."""
    alpha: float
    carry: float
    teams: dict = field(default_factory=dict)
    active: set = field(default_factory=set)
    season: int | None = None

    def start_season(self, season: int, clubs: set[str]) -> None:
        if self.season == season:
            return
        if not self.active:
            self.teams = {club: dict(DEFAULT) for club in clubs}
        else:
            mean = {s: np.mean([self.teams[t][s] for t in self.active]) for s in STATS}
            relegated = self.active - clubs
            promoted_base = ({s: np.mean([self.teams[t][s] for t in relegated]) for s in STATS}
                             if relegated else dict(DEFAULT))
            for club in clubs:
                if club in self.active:
                    self.teams[club] = {s: self.carry * self.teams[club][s] + (1 - self.carry) * mean[s]
                                        for s in STATS}
                else:
                    self.teams[club] = dict(promoted_base)
        self.active, self.season = set(clubs), season

    def update(self, row) -> None:
        home, away = self.teams[row.home], self.teams[row.away]
        observed = {
            "home": {"gf": row.home_goals, "ga": row.away_goals, "sotf": row.home_sot, "sota": row.away_sot},
            "away": {"gf": row.away_goals, "ga": row.home_goals, "sotf": row.away_sot, "sota": row.home_sot},
        }
        for side, team in (("home", home), ("away", away)):
            for stat, value in observed[side].items():
                if pd.notna(value):
                    team[stat] += self.alpha * (float(value) - team[stat])

    def features(self, home: str, away: str) -> tuple[dict, dict]:
        h, a = self.teams[home], self.teams[away]
        log = lambda v: float(np.log(max(v, 0.05)))
        home_row = {"attack_goals": log(h["gf"]), "opp_defence_goals": log(a["ga"]),
                    "attack_sot": log(h["sotf"]), "opp_defence_sot": log(a["sota"]), "home": 1.0}
        away_row = {"attack_goals": log(a["gf"]), "opp_defence_goals": log(h["ga"]),
                    "attack_sot": log(a["sotf"]), "opp_defence_sot": log(h["sota"]), "home": 0.0}
        return home_row, away_row

    def table(self) -> pd.DataFrame:
        return pd.DataFrame(self.teams).T.loc[sorted(self.active)]


def season_clubs(matches: pd.DataFrame) -> dict[int, set[str]]:
    return {season: set(group.home) | set(group.away) for season, group in matches.groupby("season")}


def pre_match_features(matches: pd.DataFrame, alpha: float, carry: float) -> pd.DataFrame:
    """One row per team per match with ratings known before kick-off."""
    clubs = season_clubs(matches)
    ratings = Ratings(alpha, carry)
    rows = []
    for row in matches.sort_values(["date", "home"]).itertuples(index=False):
        ratings.start_season(row.season, clubs[row.season])
        home_x, away_x = ratings.features(row.home, row.away)
        key = {"season": row.season, "date": row.date, "home": row.home, "away": row.away}
        rows.append({**key, "side": "home", "team": row.home, **home_x, "goals": row.home_goals})
        rows.append({**key, "side": "away", "team": row.away, **away_x, "goals": row.away_goals})
        ratings.update(row)
    return pd.DataFrame(rows)


def ratings_snapshots(matches: pd.DataFrame, alpha: float, carry: float,
                      requests: set[tuple[int, str]], extra_clubs: dict[int, set[str]] | None = None
                      ) -> dict[tuple[int, str], Ratings]:
    """Ratings positioned in `season` after every match dated on or before `cutoff`.

    One pass over the history serves every (season, cutoff) request.
    """
    clubs = season_clubs(matches)
    for season, extra in (extra_clubs or {}).items():
        clubs[season] = clubs.get(season, set()) | extra
    pending = sorted(requests, key=lambda r: (r[1], r[0]))
    ratings, out, i = Ratings(alpha, carry), {}, 0

    def take(request):
        snapshot = copy.deepcopy(ratings)
        snapshot.start_season(request[0], clubs[request[0]])
        out[request] = snapshot

    for row in matches.sort_values(["date", "home"]).itertuples(index=False):
        while i < len(pending) and pending[i][1] < row.date:
            take(pending[i]); i += 1
        ratings.start_season(row.season, clubs[row.season])
        ratings.update(row)
    for request in pending[i:]:
        take(request)
    return out


def _tau(home_goals, away_goals, lam, mu, rho):
    tau = np.ones_like(np.asarray(lam, dtype=float))
    tau = np.where((home_goals == 0) & (away_goals == 0), 1 - lam * mu * rho, tau)
    tau = np.where((home_goals == 0) & (away_goals == 1), 1 + lam * rho, tau)
    tau = np.where((home_goals == 1) & (away_goals == 0), 1 + mu * rho, tau)
    tau = np.where((home_goals == 1) & (away_goals == 1), 1 - rho, tau)
    return tau


def outcome_probabilities(lam: np.ndarray, mu: np.ndarray, rho: float) -> np.ndarray:
    """Rows of [home win, draw, away win] from Dixon-Coles adjusted Poisson score grids."""
    lam, mu = np.asarray(lam, dtype=float), np.asarray(mu, dtype=float)
    goals = np.arange(MAX_GOALS + 1)
    grid = poisson.pmf(goals[None, :, None], lam[:, None, None]) * poisson.pmf(goals[None, None, :], mu[:, None, None])
    for h, a in ((0, 0), (0, 1), (1, 0), (1, 1)):
        grid[:, h, a] *= _tau(np.array(h), np.array(a), lam, mu, rho)
    grid /= grid.sum(axis=(1, 2), keepdims=True)
    lower = np.tril(np.ones((MAX_GOALS + 1, MAX_GOALS + 1)), -1)
    return np.stack([(grid * lower).sum(axis=(1, 2)), np.trace(grid, axis1=1, axis2=2),
                     (grid * lower.T).sum(axis=(1, 2))], axis=1)


LEARNERS = {
    "poisson_glm": lambda: PoissonRegressor(alpha=1e-4, max_iter=1000),
    "gradient_boosting": lambda: HistGradientBoostingRegressor(
        loss="poisson", max_iter=200, learning_rate=0.05, max_leaf_nodes=15,
        min_samples_leaf=80, l2_regularization=1.0, random_state=0),
}


@dataclass
class MatchModel:
    learner: str
    features: tuple[str, ...]
    estimator: object
    rho: float
    goal_dispersion: float = 0.0

    def predict_goals(self, rows: pd.DataFrame) -> np.ndarray:
        return self.estimator.predict(rows[list(self.features)])

    def goal_rates(self, home_rows: pd.DataFrame, away_rows: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        return self.predict_goals(home_rows), self.predict_goals(away_rows)

    def goal_quantile(self, q: float, mean: float) -> int:
        """Quantile of a remaining-goals total, widened for season-level strength uncertainty."""
        if mean <= 0:
            return 0
        if self.goal_dispersion <= 0:
            return int(poisson.ppf(q, mean))
        size = 1 / self.goal_dispersion
        return int(nbinom.ppf(q, size, size / (size + mean)))

    def describe(self) -> dict:
        info = {"learner": self.learner, "features": list(self.features),
                "dixon_coles_rho": self.rho, "goal_dispersion": self.goal_dispersion}
        if self.learner == "poisson_glm":
            info["coefficients"] = {"intercept": float(self.estimator.intercept_),
                                    **{n: float(c) for n, c in zip(self.features, self.estimator.coef_)}}
        return info


def paired(rows: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    home = rows[rows.side == "home"].reset_index(drop=True)
    away = rows[rows.side == "away"].reset_index(drop=True)
    return home, away


def fit(rows: pd.DataFrame, features: tuple[str, ...] = FULL, learner: str = "poisson_glm") -> MatchModel:
    estimator = LEARNERS[learner]().fit(rows[list(features)], rows["goals"])
    home, away = paired(rows)
    lam, mu = estimator.predict(home[list(features)]), estimator.predict(away[list(features)])
    hg, ag = home.goals.to_numpy(), away.goals.to_numpy()
    grid = np.linspace(-0.25, 0.15, 81)
    rho = float(grid[np.argmax([np.log(np.clip(_tau(hg, ag, lam, mu, r), 1e-9, None)).sum() for r in grid])])
    return MatchModel(learner, features, estimator, rho)


def outcome_index(home_goals: np.ndarray, away_goals: np.ndarray) -> np.ndarray:
    return np.where(home_goals > away_goals, 0, np.where(home_goals == away_goals, 1, 2))


def scores(probabilities: np.ndarray, outcome: np.ndarray) -> dict:
    """Log loss, Brier score and ranked probability score for home/draw/away forecasts."""
    probabilities = np.clip(probabilities, 1e-12, 1)
    onehot = np.eye(3)[outcome]
    cumulative = np.cumsum(probabilities, axis=1)[:, :2] - np.cumsum(onehot, axis=1)[:, :2]
    return {"log_loss": float(-np.log(probabilities[np.arange(len(outcome)), outcome]).mean()),
            "brier": float(((probabilities - onehot) ** 2).sum(axis=1).mean()),
            "rps": float((cumulative ** 2).sum(axis=1).mean() / 2),
            "accuracy": float((probabilities.argmax(axis=1) == outcome).mean()),
            "matches": int(len(outcome))}


def market_probabilities(matches: pd.DataFrame) -> np.ndarray:
    implied = 1 / matches[["odds_h", "odds_d", "odds_a"]].to_numpy(dtype=float)
    return implied / implied.sum(axis=1, keepdims=True)


def walk_forward(features: pd.DataFrame, seasons: list[int], train_from: int,
                 feature_set: tuple[str, ...] = FULL, learner: str = "poisson_glm") -> pd.DataFrame:
    """Predict each season with a model trained only on earlier seasons."""
    out = []
    for season in seasons:
        model = fit(features[(features.season >= train_from) & (features.season < season)], feature_set, learner)
        home, away = paired(features[features.season == season])
        lam, mu = model.goal_rates(home, away)
        probs = outcome_probabilities(lam, mu, model.rho)
        out.append(pd.DataFrame({"season": season, "date": home.date, "home": home.team, "away": away.team,
                                 "home_goals": home.goals, "away_goals": away.goals, "xg_home": lam, "xg_away": mu,
                                 "p_home": probs[:, 0], "p_draw": probs[:, 1], "p_away": probs[:, 2]}))
    return pd.concat(out, ignore_index=True)


def score_predictions(predictions: pd.DataFrame) -> dict:
    outcome = outcome_index(predictions.home_goals.to_numpy(), predictions.away_goals.to_numpy())
    return scores(predictions[["p_home", "p_draw", "p_away"]].to_numpy(), outcome)
