"""Retrospective ridge forecast trained on 2015/16 peer clubs.

Training inputs use only events observed by the checkpoint. The target is the
subsequent per-club-match output. Barcelona is excluded from fitting and used
only for retrospective error bands. This does not calibrate a 2026/27 feed.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

METRICS = ("minutes", "goals", "assists", "xg", "xa", "passes",
           "progressive_passes", "pressures", "recoveries", "interceptions", "tackles")
ROLES = ("FWD", "MID", "DEF", "GK")
MIN_OBSERVED_MINUTES = 90
RIDGE_PENALTY = 12.0


def features(observed: float, recent: float, minutes: float, recent_minutes: float,
             played: int, role: str) -> np.ndarray:
    """Use cumulative and last-five *observed* rates, exposure and role."""
    rate = min(50.0, 90 * observed / minutes) if minutes > 0 else 0.0
    recent_rate = min(50.0, 90 * recent / recent_minutes) if recent_minutes > 0 else 0.0
    return np.array([1.0, np.log1p(rate), np.log1p(recent_rate),
                     min(1.3, minutes / (90 * played)),
                     min(1.3, recent_minutes / (90 * min(played, 5))),
                     played / 38, *(1.0 if role == r else 0.0 for r in ROLES)], dtype=float)


def ridge_fit(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    penalty = np.eye(x.shape[1]) * RIDGE_PENALTY
    penalty[0, 0] = 0.0
    return np.linalg.solve(x.T @ x + penalty, x.T @ y)


@dataclass
class TrainingRows:
    x: np.ndarray
    future_rate: np.ndarray
    club: np.ndarray
    checkpoint: np.ndarray
    observed: np.ndarray
    final: np.ndarray
    remaining: np.ndarray


def make_training_rows(appearances: pd.DataFrame, metric: str) -> TrainingRows:
    if metric not in METRICS:
        raise ValueError(f"Unsupported metric: {metric}")
    records = []
    for club, club_rows in appearances.groupby("club"):
        games = (club_rows[["match_id", "date"]].drop_duplicates()
                 .sort_values(["date", "match_id"]).reset_index(drop=True))
        order = {mid: i + 1 for i, mid in enumerate(games.match_id)}
        total_games = len(games)
        for _, player_rows in club_rows.groupby("player_id"):
            player_rows = player_rows.copy()
            player_rows["game_index"] = player_rows.match_id.map(order)
            minutes_by_game = np.zeros(total_games + 1)
            values_by_game = np.zeros(total_games + 1)
            for row in player_rows.itertuples():
                minutes_by_game[row.game_index] += float(row.minutes)
                values_by_game[row.game_index] += float(getattr(row, metric))
            cumulative_minutes = np.cumsum(minutes_by_game)
            cumulative_values = np.cumsum(values_by_game)
            for checkpoint in range(5, total_games):
                observed_minutes = cumulative_minutes[checkpoint]
                if observed_minutes < MIN_OBSERVED_MINUTES:
                    continue
                start = max(0, checkpoint - 5)
                recent_minutes = observed_minutes - cumulative_minutes[start]
                recent = cumulative_values[checkpoint] - cumulative_values[start]
                role_minutes = (player_rows[player_rows.game_index <= checkpoint]
                                .groupby("role").minutes.sum())
                role = role_minutes.idxmax() if len(role_minutes) else "UNKNOWN"
                observed = cumulative_values[checkpoint]
                final = cumulative_values[-1]
                remaining = total_games - checkpoint
                x = features(observed, recent, observed_minutes, recent_minutes, checkpoint, role)
                records.append((x, max(0.0, final - observed) / remaining, club,
                                checkpoint, observed, final, remaining))
    if not records:
        raise ValueError("Historical training data has no valid checkpoints")
    return TrainingRows(np.stack([r[0] for r in records]),
                        np.array([r[1] for r in records]),
                        np.array([r[2] for r in records]),
                        np.array([r[3] for r in records]),
                        np.array([r[4] for r in records]),
                        np.array([r[5] for r in records]),
                        np.array([r[6] for r in records]))


class ForecastModel:
    def __init__(self, appearances: pd.DataFrame, metrics: tuple[str, ...] = METRICS):
        self.coefficients = {}
        self.holdout = {}
        self.training_sizes = {}
        self.max_future_rates = {}
        for metric in metrics:
            rows = make_training_rows(appearances, metric)
            train = rows.club != "Barcelona"
            check = rows.club == "Barcelona"
            if train.sum() < 100 or check.sum() < 20:
                raise ValueError("Historical panel is too small for a forecast")
            coefficients = ridge_fit(rows.x[train], rows.future_rate[train])
            self.max_future_rates[metric] = float(np.quantile(rows.future_rate[train], 0.995))
            predicted_future_rate = np.minimum(self.max_future_rates[metric],
                                               np.maximum(0.0, rows.x[check] @ coefficients))
            predicted_final = rows.observed[check] + rows.remaining[check] * predicted_future_rate
            self.coefficients[metric] = coefficients
            self.training_sizes[metric] = int(train.sum())
            self.holdout[metric] = pd.DataFrame({
                "checkpoint": rows.checkpoint[check],
                "error": rows.final[check] - predicted_final,
            })

    def predict(self, player_rows: pd.DataFrame, metric: str, played_rounds: list[int],
                cutoff: int) -> dict:
        if metric not in self.coefficients:
            raise ValueError(f"Unsupported metric: {metric}")
        if not 1 <= cutoff <= len(played_rounds) <= 38:
            raise ValueError("Cutoff must be within the completed fixture window")
        prior_rounds = played_rounds[:cutoff]
        observed_rows = player_rows[player_rows.matchday.isin(prior_rounds)]
        observed_minutes = float(observed_rows.minutes.sum())
        if observed_minutes < MIN_OBSERVED_MINUTES:
            raise ValueError("At least 90 observed player minutes are needed")
        if metric not in observed_rows.columns:
            raise ValueError(f"{metric} is absent from the authorized upload")
        observed = float(observed_rows[metric].sum())
        recent_rows = observed_rows[observed_rows.matchday.isin(prior_rounds[-5:])]
        recent = float(recent_rows[metric].sum())
        recent_minutes = float(recent_rows.minutes.sum())
        role = "UNKNOWN"
        if "role" in observed_rows.columns:
            role_minutes = observed_rows.groupby("role").minutes.sum()
            if len(role_minutes):
                role = str(role_minutes.idxmax())
        x = features(observed, recent, observed_minutes, recent_minutes, cutoff, role)
        remaining = 38 - cutoff
        future_rate = min(self.max_future_rates[metric], max(0.0, float(x @ self.coefficients[metric])))
        point = observed + remaining * future_rate

        if remaining == 0:
            return {"metric": metric, "observed": observed, "projected": observed,
                    "lower": observed, "upper": observed, "remaining_matches": 0,
                    "future_per_match": 0.0, "holdout_mae": 0.0, "holdout_samples": 0,
                    "training_checkpoints": self.training_sizes[metric],
                    "role": role, "cutoff": cutoff}

        errors = self.holdout[metric]
        same_horizon = errors[errors.checkpoint == min(cutoff, 37)].error
        if len(same_horizon) < 10:
            same_horizon = errors[errors.checkpoint.between(max(5, cutoff - 2), min(37, cutoff + 2))].error
        if same_horizon.empty:
            same_horizon = errors.error
        low_error, high_error = np.quantile(same_horizon, [0.10, 0.90])
        lower = max(observed, min(point, point + float(low_error)))
        upper = max(point, point + float(high_error))
        return {"metric": metric, "observed": observed, "projected": point,
                "lower": lower, "upper": upper, "remaining_matches": remaining,
                "future_per_match": future_rate, "holdout_mae": float(np.mean(np.abs(same_horizon))),
                "holdout_samples": int(len(same_horizon)),
                "training_checkpoints": self.training_sizes[metric],
                "role": role, "cutoff": cutoff}
