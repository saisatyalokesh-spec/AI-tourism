## 1. Project Overview

*A Multi-Fusion AI-Powered Smart Tourism Platform — combining tourist
demand forecasting, real-time crowd analytics, climate assessment, and
personalized recommendations into one budget-aware trip planner for
Telangana.*
             USER
               │
               ▼
       🖥️ STREAMLIT
          frontend/app.py
               │
               │ HTTP
               ▼
       ⚡ FASTAPI BACKEND
          backend/main.py
               │
        ┌──────┴──────┐
        ▼             ▼
   🤖 ML MODELS    🗄️ SUPABASE
   .pkl / .pt      PostgreSQL
        │             │
        │       ┌─────┼──────────┐
        │       ▼     ▼          ▼
        │    Crowd Climate     Cost
        │    Spots  Weather    Budget
        │
        ▼
   🎯 Predictions

### What it does

You fill in one form — district, tourist spot(s), travel dates, group
size, transport, accommodation tier — and the app runs three trained
models against it, then shows the results as one dashboard: **Predictions**.

### Platform capabilities

| Capability | What it does | Why it's there |
|---|---|---|
| **Trip Setup** | Collects district, spot(s), dates, group size, transport, accommodation tier — one form. | Every prediction below needs these as inputs. |
| **Cost Estimation** | Itemized cost breakdown (stay, food, travel, entry fees, tolls) plus per-person/per-day figures. | Lets you compare trips of different lengths and group sizes fairly. |
| **Crowd Forecasting** | Predicted visitor count for the chosen spot and date, labeled Quiet/Moderate/Busy/Very Crowded. | The main lever for avoiding overcrowded visits. |
| **Climate Forecast** | Predicted max/min temperature and rain chance for your travel dates — a real forward LSTM forecast, not a historical lookup. | Informs both comfort and safety planning. |
| **Packing Tips** | Auto-generated from the climate forecast (umbrella, sun protection, jacket, etc.). | Turns raw weather numbers into something actionable. |
| **Good Time to Visit** | One badge (Great/Good/Fair/Not Ideal) merging the crowd and climate outlook. | One glance instead of cross-referencing two panels. |
| **Amenities** | Nearby restaurants, ATMs, hospitals for the selected spot. | Practical, on-the-ground usefulness. |
| **Spot Rating & Popularity** | Popularity tier (Emerging/Popular/Very Popular) and rating shown on the destination card. | Helps judge a spot before committing a trip to it. |
| **Upcoming Festivals** | Festivals near the travel date, matched to their typical (or verified) calendar date. | A heads-up on likely busier or more vibrant periods. |
| **Suggested Visiting Order** | For multi-spot trips, the shortest route through the selected spots — not the order they were clicked in. | Real route optimization, not a placeholder feature. |
| **Transport Suggestions** | A recommended mode based on group size, editable by the traveler. | Rough capacity guidance, never forced. |

---

## 2. Predictions & Modules

### The three trained models

| Prediction | Model | Trained on | Inputs → Output |
|---|---|---|---|
| **💸 Cost** | `MultiOutputRegressor` wrapping 5 XGBoost regressors (`pickles/best_trip_cost_model.pkl`) | `trip_budget_prediction` table | Duration, travelers, distance, transport mode, accommodation tier, season → stay / food / entry-fee / tolls estimates. Travel cost specifically comes from a real fuel-price/fare formula (`estimate_realistic_travel_cost()`), not the model's own guess — easier to trust and to keep current as fuel prices actually change. |
| **👥 Crowd** | XGBoost regressor (`pickles/best_model.pkl`) | `spot_visitors` table | Spot, district, category, year, month, season, festival → predicted visitor count. The **Busy**/**Very Crowded** labels are only ever shown when the travel date genuinely falls inside a real festival window (checked against a verified festival calendar) — on an ordinary day, the label tops out at Moderate, so a model that leans heavily on historical spot popularity can't present a routine day as festival-level crowds. |
| **🌦️ Climate** | 1-layer PyTorch LSTM (`pickles/best_climate_lstm_model.pt` + `best_climate_metadata.pkl`) | `climate_dataset` table | The model was trained on the *day-to-day change* in temperature/rainfall, not raw values. To forecast your travel date, the backend replays the last known days through the LSTM autoregressively (each prediction feeds the next step), sums the predicted daily changes up to your date, and adds that to the district's last known reading — a genuine forward forecast, not a historical lookup. Past a 14-day horizon, it's blended toward that month's historical seasonal average so it doesn't just drift in whatever direction the data happened to end. |

### Supporting infrastructure

| Module | Role |
|---|---|
| **FastAPI backend** (`backend/main.py`) | Serves every prediction and lookup endpoint (`/predict/*`, `/spot-info`, `/amenities`, `/distance/*`, `/festival-date/*`) over HTTP. |
| **SQLite database** | `predict.get_db_connection()` reads from the local `data/smart_tourism.db` — spots, visitors, and climate history all live there. |
| **scikit-learn preprocessing** | Ordinal/one-hot encoding pipelines that turn raw form inputs into the exact feature format each trained model expects. |
| **Route optimization** | Haversine point-to-point distances between real spot coordinates, with an exact (brute-force) shortest-route search for small trips and a nearest-neighbor heuristic beyond that (`suggest_visit_order()`). |
| **Festival calendar** | Verified exact dates where known, falling back to a festival's typical month otherwise — powers both the "upcoming festivals" list and the crowd model's festival-window check. |
| **Packing-tip rules engine** | Rule-based, not ML — turns forecasted temperature/rain thresholds into plain-language packing suggestions. |
| **Streamlit frontend** (`frontend/app.py`) | The UI itself, plus the climate history/forecast and cost-breakdown charts. |

---

## 3. Setup

### Model & data files

Copy your 4 model files into `App/pickles/` and `smart_tourism.db` into
`App/data/`, matching the filenames above.

### Install dependencies

```bash
cd App/backend && pip install -r requirements.txt
cd ../frontend && pip install -r requirements.txt
```

### Run it — two terminals

**Terminal 1 — backend:**
```bash
cd App/backend
uvicorn main:app --reload
```
Runs at `http://127.0.0.1:8000`. Visit `http://127.0.0.1:8000/docs` to try
every endpoint directly.

**Terminal 2 — frontend:**
```bash
cd App/frontend
streamlit run app.py
```
Runs at `http://127.0.0.1:6501`. The backend must already be running — the
frontend shows a clear error with the exact command to run if it isn't.

---

## 4. Known data notes

- **Upcoming festivals:** festival dates vary year to year (many follow
  the lunar calendar). Verified exact dates are used where known
  (`FESTIVAL_DATES`); otherwise a festival is matched to its *typical*
  calendar month (`FESTIVAL_TYPICAL_MONTH`) — see `backend/predict.py`.
- **Crowd labels:** Busy/Very Crowded are only shown when the travel date
  is inside a real festival window (see `_festival_is_active()` in
  `backend/predict.py`) — this is a deliberate design choice, not a bug,
  since the underlying model leans more on *which spot* than *which
  month*.
- **Suggested visiting order:** exact (brute-force) for up to
  `EXACT_ROUTE_MAX_SPOTS` spots, nearest-neighbor heuristic beyond that;
  the first spot picked is always kept as the starting point.
- **Not yet used by any endpoint:** the `accommodations` table (name,
  tier, cost, district, lat/lon) — potential material for a "suggest a
  hotel" feature. `other_spots`'s `reviews`/`text_vec` columns
  (precomputed review-text embeddings) are also unused — potential
  material for a "similar spots" feature.

See `PREDICTIONS.md` for the full technical detail behind each model.