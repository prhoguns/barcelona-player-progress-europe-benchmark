# Season Forecast Lab

A machine-learning project that forecasts the 2026/27 season for **every club in La Liga and the Premier League**: final points, goals scored and conceded, every remaining match, and each scorer's league goal total. It updates itself every day from public data, and every model is tested on past seasons it never saw.

It started as a Barcelona player dashboard; the 2015/16 Barcelona event-data analysis is still included as a separate historical demo.

## What it predicts

| Question | How |
| --- | --- |
| Who wins each remaining match? | Trained match model: expected goals for both sides, then home/draw/away probabilities |
| How many points will a club finish on? | Every remaining fixture combined, with 80% ranges from 4,000 simulated seasons |
| How many goals will it score and concede? | Sum of the match model's expected goals, with the same simulated ranges |
| How many league goals will each scorer finish with? | Each player's share of club goals (shrunk toward last season) × the goals the club is still expected to score |
| How has the forecast moved? | The forecast re-run after every matchday using only results known at the time |

The dashboard also has match stats (goals vs expected goals, shots, splits by half and venue, every club compared on 10 measures), the projected league table, and a model-accuracy page.

## How good is it?

Everything below is **out of sample**. Settings were chosen on 2012/13–2014/15; each test season (2015/16–2025/26) was predicted by a model trained only on earlier seasons.

**Match outcomes** (4,180 matches per league; lower log loss is better):

| Model | La Liga log loss | La Liga accuracy | Premier League log loss | Premier League accuracy |
| --- | ---: | ---: | ---: | ---: |
| **Trained model (goals + shots on target)** | **0.978** | **53.0%** | **0.978** | **53.1%** |
| Same model, goals only | 0.979 | 52.8% | 0.978 | 53.1% |
| Gradient-boosted trees, same features | 0.993 | 51.0% | 0.995 | 51.8% |
| Base rates (no team information) | 1.066 | 45.7% | 1.067 | 44.3% |
| Bookmakers' closing odds | 0.960 | 54.4% | 0.956 | 54.7% |

The model is clearly better than knowing nothing and close to, but not better than, closing bookmaker odds, which pool the information of the whole betting market and are the standard benchmark in football forecasting. Its probabilities are well calibrated: matches given a 60% home-win chance were won at home about 60% of the time.

**Season points** (every club in every test season, 220 forecasts per checkpoint):

| Forecast made after | La Liga avg error (model / keep pace) | Inside 80% range | Premier League avg error (model / keep pace) | Inside 80% range |
| --- | ---: | ---: | ---: | ---: |
| Preseason | 7.5 / 8.1 pts | 77% | 9.2 / 10.4 pts | 73% |
| 7 matches | **5.8 / 11.1 pts** | 83% | **7.8 / 12.9 pts** | 74% |
| 19 matches | 4.5 / 6.0 pts | 81% | 5.0 / 6.1 pts | 80% |
| 28 matches | 3.3 / 3.6 pts | 81% | 3.6 / 3.9 pts | 80% |

Before a ball is kicked, "keep pace" means repeating last season's total. The Premier League's early-season ranges are a little too narrow (74% instead of 80%): clubs there change more during a season than the model expects.

**Player league goals** (players who had scored by that point; fitted on 2013/14–2018/19, tested on 2019/20–2025/26):

| Club matches played | La Liga avg error (model / keep pace) | Premier League avg error (model / keep pace) |
| --- | ---: | ---: |
| 7 | **2.5 / 4.7 goals** | **2.6 / 4.9 goals** |
| 19 | 1.3 / 1.6 goals | 1.4 / 1.7 goals |
| 28 | 0.8 / 0.9 goals | 0.9 / 1.0 goals |

## The models

**1. Team ratings (feature engineering).** Every club carries four exponentially weighted averages: goals scored, goals conceded, shots on target for and against. After each match a rating moves a small step (α = 0.02 in La Liga, 0.015 in the Premier League) toward what just happened. Over the summer, ratings keep 95% of their value and regress 5% toward the league average; promoted clubs start at the average of the clubs they replaced. Every feature is computed only from matches played before the one being predicted.

**2. Match model: Poisson regression (GLM) with a Dixon–Coles correction.** Goals are counts, so a Poisson regression predicts each side's expected goals from the log of its attack ratings, the opponent's defence ratings, and home advantage. Scores are turned into home/draw/away probabilities, with the Dixon–Coles adjustment fixing the plain Poisson model's undercount of 0–0 and 1–1 draws. Chosen because it is the standard, well-understood model for football scores, its coefficients are interpretable (home advantage is worth about +36% expected goals in La Liga), and it beat gradient-boosted trees on the validation seasons; with only five inputs, the trees overfit.

**3. Season simulation.** Remaining fixtures are simulated 4,000 times. In each simulated season the club's attack and defence are scaled by random factors whose spread was measured on past seasons (how far teams drifted from their ratings after a forecast was made). Without that, the ranges were too narrow.

**4. Player model: empirical-Bayes shrinkage.** A player's share of his club's goals is estimated as `(his goals + k × prior) / (club goals + k)`, where the prior is half his share last season (zero for players new to the club's scoring list). The fitted k (24 in La Liga, 32 in the Premier League) means a hot start of 7 matches is trusted only partly. The expected share is applied to the goals the match model still expects the club to score; a negative binomial gives the 80% range. k, the prior weight and the baseline were chosen by grid search on past seasons.

## Data and how it stays current

| Source | What it provides | Licence and handling |
| --- | --- | --- |
| [football-data.co.uk](https://www.football-data.co.uk/) | Results, half-time scores, shots, shots on target, corners, fouls, cards, closing odds, and (from 2026/27) expected goals, for 2010/11 onwards | No stated licence. Raw files are downloaded at build time into a git-ignored cache; only derived numbers are stored |
| [openfootball/football.json](https://github.com/openfootball/football.json) | The full fixture list, including unplayed matches | CC0 public domain |
| English Wikipedia club season pages | Goal scorers, minutes, penalties, own goals, cup goals | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/); derived scorer tables in `data/derived/wikipedia/` carry the same licence |

Quality checks are built in: club names are matched between sources automatically from games both have scored, both sources' scores are cross-checked, and a Wikipedia league match only counts if its listed scorers add up to the official score. Clubs whose pages don't pass (for example Manchester United and Valencia at the time of writing) still get team forecasts; the dashboard explains why player forecasts are missing.

A GitHub Actions workflow (`.github/workflows/refresh-data.yml`) rebuilds everything at 06:17 UTC each day, runs the tests, and commits only when results or scorer data changed. A forecast archive (`data/current/forecast_archive.csv`) records each live forecast so it can be graded at season's end.

## Rebuild it yourself

Use Python 3.11 or later:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/build_forecasts.py   # about 6 minutes: download, tune, train, backtest, forecast
pytest -q
streamlit run app.py
```

`python scripts/build_forecasts.py --quick` reuses the saved settings and evaluations and just refreshes results and forecasts (about a minute; the dashboard's refresh button runs this). `--league la-liga` builds one league; `--refresh-wikipedia-history` refetches past seasons' scorer pages.

| File | Role |
| --- | --- |
| `src/football_data.py` | Download and parse results and match stats |
| `src/schedule.py` | Fixture list and automatic club-name matching |
| `src/match_model.py` | Team ratings, Poisson GLM / gradient boosting, Dixon–Coles, scoring rules |
| `src/season_forecast.py` | Season simulation, uncertainty calibration, backtests |
| `src/wiki_season.py` | Wikipedia scorer parsing and validation |
| `src/player_model.py` | Player share model, fitting and evaluation |
| `scripts/build_forecasts.py` | Runs the whole pipeline and writes `data/current/<league>/` |
| `current_dashboard.py` | The dashboard |

To add a league, add its football-data.co.uk and openfootball codes to `src/leagues.py` (and Wikipedia article names for player data).

## Deploy for free

[Streamlit Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy) hosts public GitHub repositories for free. Sign in at [share.streamlit.io](https://share.streamlit.io/) with GitHub, choose **Create app**, select this repository, branch `main` and entry point `app.py`. It installs `requirements.txt`, uses `.streamlit/config.toml` for the theme, and redeploys whenever the daily workflow pushes new data.

## Limits

No injuries, suspensions, transfers or minutes played; no player-level xG (no source with clear reuse rights); cup and European fixtures are not part of the season forecast. Bookmakers remain more accurate match by match. Wikipedia pages are edited by volunteers and occasionally lag a day or two.

## Optional: upload your own player data

The Players page still accepts an authorized match-by-match player CSV (required columns `matchday,date,player,minutes`, optional `role` and metrics `goals,assists,xg,xa,passes,progressive_passes,pressures,recoveries,interceptions,tackles`; template in [`examples/current_player_match_template.csv`](examples/current_player_match_template.csv)). Uploads stay in the browser session. They feed an experimental per-metric ridge regression:

For each metric, a ridge regression learns the rate of production **in the remaining club matches** from the four historical 2015/16 comparison clubs **and all 34 Bayer Leverkusen Bundesliga matches from 2023/24**. The latter is the most recent complete men's club league season in the StatsBomb Open Data catalog that I found. Each training row is a player at a match checkpoint: inputs are cumulative and last-five observed per-90 rates, minutes exposure, fraction of the club season completed and broad role. Only matches at or before that checkpoint enter the inputs. The target is the player's subsequent output per remaining club match. Negative future rates are floored at zero and extreme rates are capped at the historical training set’s 99.5th percentile. The displayed final total equals the authorized 2026/27 observed total plus predicted future output over the remaining 38-match schedule; it cannot fall below the observed total.

Historical 2015/16 Barcelona is held out of model fitting and used to estimate mean absolute error and a 10th–90th percentile residual band at the selected horizon. The app shows the training and holdout snapshot counts. These are **retrospective error checks, not calibrated 2026/27 probabilities**; snapshots from one player are correlated. Adding 2023/24 data does not by itself establish lower error for current Barcelona players. Changes in players, tactics and data coverage make the model unsuitable for scouting or betting decisions. The current-season prediction is unavailable until an authorized CSV supplies at least 90 observed minutes for the selected player; no forecast is generated from team scores alone.

On the 2015/16 Barcelona holdout, adding 2023/24 Leverkusen to the 2015/16 peer training panel changed pooled snapshot mean absolute final-total error as follows. These are retrospective diagnostics, with no current-season validation:

| Metric | 2015/16 training only | Training with 2023/24 added |
| --- | ---: | ---: |
| Goals | 1.77 | 1.80 |
| Assists | 1.29 | 1.30 |
| Estimated minutes | 292 | 298 |
| xG | 1.32 | 1.33 |
| Passes | 232 | 228 |
| Pressures | 39.7 | 40.4 |

The newer panel improves the pass diagnostic but worsens the others slightly on this older holdout. The model uses equal checkpoint weights and no claim of improved 2026/27 forecast accuracy. A current, licensed Barcelona player-match feed and current-season holdout are needed to assess or recalibrate it.


## Historical 2015/16 Barcelona demo

| Source | Competition and season | Dashboard use | Published club fixtures in this build |
| --- | --- | --- | ---: |
| StatsBomb Open Data | Men’s La Liga 2015/16 | Barcelona player analysis | Barcelona 38 |
| StatsBomb Open Data | Men’s Premier League 2015/16 | Same-role peer panel | Arsenal 38 |
| StatsBomb Open Data | Men’s Serie A 2015/16 | Same-role peer panel | Juventus 38 |
| StatsBomb Open Data | Men’s Ligue 1 2015/16 | Same-role peer panel | Paris Saint-Germain 37 |
| StatsBomb Open Data | Men’s Bundesliga 2015/16 | Same-role peer panel | Bayer Leverkusen 34 |
| StatsBomb Open Data | Men’s Bundesliga 2023/24 | Historical forecast training only | Bayer Leverkusen 34 |
| SkillCorner Open Data | 2024/25 A-League, Auckland FC vs Newcastle United Jets FC, 30 November 2024 | Separate 10-minute tracking prototype | One excerpt |

The historical panel contains **185 selected-club matches**, 2,552 player-match appearances, and 114,744 pass events processed into compact spatial aggregates. It is a **curated five-club comparison**, not a full European-league distribution. The published StatsBomb Ligue 1 catalog has 37 PSG fixtures here, leaving one fixture gap; the Bundesliga catalog provides Leverkusen’s 34 fixtures, not the entire league. Source coverage can change when the upstream repository changes. The SkillCorner match is unrelated to every StatsBomb fixture and is never joined to Barcelona data. Sample players are shown with anonymized display labels.


Rebuild the historical demo with `python scripts/build_data.py --workers 8`, `python scripts/build_recent_training.py --workers 6` and `python scripts/build_tracking_sample.py`. These stream source JSON in memory and write only aggregated outputs to `data/derived/`.

## Historical analytics methodology

- **Playing time:** Starting XI players begin at minute zero; substitutes start or exit at their substitution time; dismissals end their minutes. Match end is the final second-period event, floored at 90 minutes and capped at 110. Minutes are estimates and include observed stoppage time.
- **Broad role:** dominant minutes played as goalkeeper, defender, midfielder or forward. The same-role peer median includes non-Barcelona players with at least 900 minutes in the four selected comparison clubs. This controls only broad role and exposure, not team style, match strength or possession.
- **Per 90:** `90 × event count ÷ estimated minutes`. Cumulative season progress and five-appearance form use total events over total minutes, rather than an unweighted average of match rates.
- **xG and xA:** xG is StatsBomb’s provided shot value. xA is the xG of a shot linked by StatsBomb’s `assisted_shot_id` to a pass; unlinked chances do not receive xA here.
- **Progressive pass/carry proxy:** completed pass or carry with at least 12 StatsBomb pitch x-units forward and an endpoint at x≥60 on a 120×80 pitch. Final-third entry is a completed pass crossing from x<80 to x≥80. This simple definition is displayed in the app.
- **Quiet Contribution Finder:** `(recoveries + interceptions + 0.5×pressures + progressive passes + progressive carries) × 90 ÷ minutes`, restricted to Barcelona outfield players with at least 450 minutes. The components overlap in football meaning and should not be interpreted as player value.
- **Game state:** each event is labelled Leading, Level or Trailing using the score immediately before it. Own goals are assigned to the opponent. State charts show event volumes because this compact export does not calculate state-specific on-pitch minutes.
- **Risk–reward passing:** the risk proxy counts a pass from x≥60 to x≥80 with a through-ball flag or at least 15 x-units of advance. Reward counts a completed progressive or shot-assist pass. These are descriptive and can overlap; neither is an expected-value model. The pitch uses 20×20 pass-origin counts, not raw event records.
- **Off-ball sample:** SkillCorner positions are sampled every two seconds over the first ten minutes of period one. Only detected points are used. Movement steps implying more than 10 m/s are filtered; the distance is an illustrative partial path, not an official physical output. Display coordinates are projected from the sample’s 105×68m pitch to the 120×80 graphic.

## Findings in the historical sample

- Luis Suárez accumulated roughly **27.6 xG** and **10.7 linked-pass xA** in 3,243 estimated league minutes. His xG pace was about **0.77 per 90**, versus **0.40 per 90** for the selected-club forward peer median.
- Andrés Iniesta led eligible Barcelona outfield players on the defined quiet-action index at **31.15 per 90**. Javier Mascherano recorded **27.37 per 90** with no goals or assists, illustrating why the index surfaces players whose work a scoreline misses.
- These findings describe the supplied 2015/16 open-data panel. They do not indicate current form, future performance, or scouting-grade ranking.

## Credits, terms and limits

**Event data source: StatsBomb.** The dashboard displays the StatsBomb logo from the [StatsBomb Open Data repository](https://github.com/hudl/open-data/tree/master/img). StatsBomb’s [open-data terms](https://github.com/hudl/open-data#terms--conditions) require source attribution and logo use for published analysis; the source [media pack](https://statsbomb.com/media-pack/) is linked as well. The repo includes only compact derived aggregates, not StatsBomb’s raw match/event JSON.

**Current-season sources:** results and match stats from [football-data.co.uk](https://www.football-data.co.uk/) (derived numbers only), fixtures from [openfootball/football.json](https://github.com/openfootball/football.json) ([CC0](https://github.com/openfootball/football.json/blob/master/LICENSE.md)), and scorers from English Wikipedia ([CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)). See *Data and how it stays current* above.

**Tracking sample source: SkillCorner Open Data.** The source [repository](https://github.com/SkillCorner/opendata) is [MIT licensed](https://github.com/SkillCorner/opendata/blob/master/LICENSE). This project retains the source credit, only publishes a small derived, anonymized display excerpt, and keeps it separate from Barcelona analysis. Tracking has detection and identity limitations noted in SkillCorner’s README.

This is an independent analytical project and is not affiliated with any club, league, data provider, StatsBomb or SkillCorner. Future live Barcelona off-ball features require an appropriately licensed tracking feed and are **pending**.
