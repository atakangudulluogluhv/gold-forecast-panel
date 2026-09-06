# 🥇 Gold Price Forecast Panel (TRY / gram)

*Türkçe sürüm: [README.tr.md](README.tr.md)*

A Streamlit panel that forecasts the Turkish lira price of gram gold from historical
data, measures how reliable that forecast actually is through backtesting, and uses
Claude for a short written interpretation.

What makes the panel unusual is not that it produces a forecast, but that it
**measures the limit of that forecast and shows it on screen**. If the directional
prediction has no skill, the panel prints a red warning; if trading on the signal
lags buy-and-hold, it says so with numbers. See *Measured finding* below.

> **This is not an investment tool.** It does not produce buy or sell advice, and the
> reason it does not is itself a measured result, not a design preference.

## Running

**Windows — one step:** double-click `baslat.bat`.

The script does everything itself: creates the virtual environment, installs packages,
prepares the `.env` file and opens the panel. The first run takes a few minutes for
package installation; later launches take seconds.

**Manual:**

```bash
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env          # Linux/macOS: cp .env.example .env
streamlit run app.py
```

Stop the panel with `Ctrl+C` in the terminal.

## API key

Needed for the AI commentary and news scoring. **The panel works fully without a key** —
only those two features are disabled.

1. https://console.anthropic.com → **Settings → API keys → Create Key**
2. The key is shown only once, at creation; use the copy button (a key copied from the
   list is masked and therefore invalid)
3. Add credit under **Billing** — the API is prepaid
4. Open `.env` and paste it:

```
ANTHROPIC_API_KEY=sk-ant-api03-...
```

No quotes, no spaces. Save and restart the panel.

⚠️ If the project folder sits inside OneDrive or Dropbox, `.env` is synced to the cloud.
Move the project to a folder that is not synced if you do not want that.

## First launch

Data is downloaded and the model is trained; this takes roughly 45 seconds per horizon.
Results are written to `cache/`, so later launches are instant. Use **Refresh data** /
**Retrain model** in the sidebar to recompute.

## Architecture — who does what

**The language model does not make the forecast.** The price forecast comes from a
regression model (scikit-learn) running on your own machine and costs no tokens. Claude
is used for two narrow jobs only: scoring the day's news headlines, and writing a short
comment from an already-computed numeric summary.

The reason is measurability. Handing a raw price series to a language model and asking
it to "predict" produces a number that changes on every query and cannot be backtested.
A regression has a measurable track record — every accuracy figure in the panel comes
from that measurement.

```
Yahoo Finance ─┐
truncgil ──────┼─→ gram gold TRY series ─→ features ─→ regression ─→ forecast
EPU / GDELT ───┘                                            │
                                                            ↓
                                                   Claude → short comment
```

### Data sources (all free, no API key required)

| Source | What it provides |
|---|---|
| Yahoo Finance | Gold (`GC=F`), USD/TRY (`TRY=X`), dollar index, US 10y yield, VIX, oil, S&P 500 |
| truncgil | Live gram gold / ounce / dollar price |
| policyuncertainty.com | Newspaper-based daily uncertainty index (EPU), since 1985 |
| GDELT | Daily sentiment tone of world news about gold, since 2018 |
| Google News + Investing RSS | Current headlines (for Claude scoring) |

### Three layers of news data

The distinction is not "news or not news" but **"does it have history"** — you cannot
claim a feature improves the model without a history to test it against.

| Layer | Enters the model? | Why |
|---|---|---|
| Market indicators (dollar index, yields, VIX…) | Yes | 10 years of daily history → testable |
| News indices (EPU, GDELT) | Yes | Daily history → testable |
| Today's headlines (Claude score) | No | No history → not measurable |

The third layer is shown as a separate signal in the panel and accumulated in
`cache/sentiment_history.csv`; after a few months it becomes measurable.

## Measured finding: there is no exploitable edge

The panel's most important output is not the forecast but the limit of the forecast.
Three independent measurements point the same way.

**1. Directional accuracy is a trend artefact.** Gold in TRY rose in 72% of historical
30-day windows. The model's 71.8% directional accuracy is below that — no better than a
constant "it always goes up" prediction. At 7 days the difference is +0.6 points, which
is noise.

| Horizon | Model direction | "Always up" | Real edge |
|---|---|---|---|
| 7 days | 63.4% | 62.9% | +0.6 pts |
| 30 days | 71.8% | 72.4% | −0.6 pts |

**2. Trading the signal lags buy-and-hold.** The strategy "hold gold when the model says
up, otherwise stay in TRY" loses **even at zero transaction cost**:

| Cost | Strategy | Buy-and-hold | Difference |
|---|---|---|---|
| 0% | 327% | 350% | −23 pts |
| 0.5% (bank) | 250% | 350% | −100 pts |
| 2% (jeweller spread) | 19% | 350% | −331 pts |

**3. Probabilities are not informed beyond the base rate.** The Brier skill score for the
2–3 day upward probability is below zero — the model does no more than repeat the
historical rate of increase.

The MAPE difference is statistically significant (naive 2.62% → model 2.52%), but that is
a small improvement in *magnitude*; trading is done on *direction*, and there is no skill
in direction.

The panel displays all three measurements and prints a red warning when they come out
negative. **That is why it is not a decision or investment tool** — a measured result,
not a missing feature.

## Honesty notes

- Every forecast is compared against the **naive** assumption that the price does not
  change at all. When the model cannot beat it, the panel says so plainly and shows
  today's price as the forecast. At a 1-day horizon it usually cannot — gold is very
  close to a random walk on a daily scale.
- The **ablation table** shows whether adding features actually helps. In this project
  the market and news features make some horizons *worse*: with roughly 2,200 days of
  data, 45 features overfit. In that case the panel uses the narrower feature set.
- Backtesting trains on data up to each day only and leaves a gap (embargo) as long as
  the target horizon — otherwise the model has seen the answer.
- Both the feature set and the model were selected on the same test, so the reported
  error may be somewhat optimistic.

## Token cost

Claude calls use `claude-haiku-4-5` and are cached to disk. Measured on real calls:

| Job | Frequency | Tokens (in + out) | Cost |
|---|---|---|---|
| News scoring | At most once a day | 1,091 + 125 | ~0.08 TRY |
| Commentary | On button press, cached for the same numbers | 451 + 412 | ~0.12 TRY |

Roughly **6–13 TRY per month** depending on use. The raw price series is never sent; the
only line that goes out for commentary looks like this:

```
gram_altin_fiyati=6180.41 TL | vade=7 gun | tahmin=6229.01 TL |
tahmin_araligi=6009.34-6483.31 TL | model_ortalama_hatasi=%2.52 |
naive_ortalama_hatasi=%2.62 | naiveyi_geciyor=evet | rsi=55.21 | vix=17.27 | ...
```

Sending the same series raw would be ~50,000 tokens. Tokens used and cost are shown in
the interface after each call; cached responses are marked as free.

> Abbreviations were deliberately avoided: an early version wrote `ufuk=7g` and the model
> once read it as "7 grams". Saving a few tokens is not worth a wrong output.

## File layout

```
baslat.bat          One-click launcher (venv + install + run)
app.py              Streamlit interface
gold/config.py      symbols, horizons, file paths
gold/data.py        data fetching, calibration, caching
gold/features.py    feature generation (3 groups: price / market / news)
gold/model.py       backtest, ablation, trend baseline, trade simulation, forecast
gold/proba.py       2–3 day upward probability + calibration scorecard
gold/news.py        RSS headlines
gold/ai.py          Claude calls (token discipline lives here)
gold/ui.py          number formatting, theme colours, charts
```

---

**This is not investment advice.** Price forecasting is uncertain by nature and the
results here are for educational and research purposes.
