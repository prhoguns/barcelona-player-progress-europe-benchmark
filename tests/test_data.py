import pandas as pd

from src.analytics import goal_team, per90, progressive_pass, role


def test_normalization_rules():
    assert role("Right Center Back") == "DEF"
    assert role("Center Forward") == "FWD"
    assert per90(5, 450) == 1
    assert progressive_pass([40, 30], [65, 30])
    assert not progressive_pass([40, 30], [45, 30])
    assert goal_team({"type": {"name": "Shot"}, "team": {"name": "Barcelona"},
                      "shot": {"outcome": {"name": "Goal"}}}) == "Barcelona"


def test_derived_coverage_and_ranges():
    a = pd.read_csv("data/derived/appearances.csv")
    z = pd.read_csv("data/derived/pass_zones.csv")
    t = pd.read_csv("data/derived/tracking_sample.csv")
    assert a.match_id.nunique() == 185
    assert a.groupby("club").match_id.nunique().to_dict() == {
        "Barcelona": 38, "Arsenal": 38, "Juventus": 38,
        "Paris Saint-Germain": 37, "Bayer Leverkusen": 34,
    }
    assert a.minutes.between(0, 110).all()
    assert (a[["goals", "assists", "xg", "xa", "passes", "pressures"]] >= 0).all().all()
    assert z.x_bin.between(0, 5).all() and z.y_bin.between(0, 3).all()
    assert z.completed.le(z.passes).all()
    assert set(t.sample_player) == {f"Sample player {i}" for i in range(1, 7)}
    assert t.second.between(0, 600).all()
