# 🧠 What This App Predicts, and How

## 1. 💸 Cost Estimation

**Model:** 5 XGBoost models working together (`pickles/best_trip_cost_model.pkl`), trained in `eda_trip_budget_prediction.ipynb`.

**In simple terms:** Give it your trip length, group size, distance,
transport mode, and hotel tier — it estimates what you'll spend, split
into 5 parts: stay, food, travel, entry tickets, and tolls/parking.

**Trained on:** real past trip data — the `trip_budget_prediction` table.

**Good to know:** Travel cost isn't a guess from the model — it's worked
out with a real fuel-price/fare formula instead, so it stays accurate even
as prices change.

**Output:** 5 cost components, added up into one total estimated cost.

**🔀 Flow:**
```
📝 Days · Travelers · Distance · Transport · Hotel Tier
        │
        ▼
🤖 5 XGBoost models predict together
        │
        ▼
🏨 Stay  🍽️ Food  🎫 Tickets  🅿️ Tolls    ⛽ Travel
   (from the models)                 (from a real fuel-price formula)
        │
        ▼
💸 Total Estimated Cost
```

---

## 2. 👥 Crowd Prediction

**Model:** XGBoost (`pickles/best_model.pkl`), trained in `Crowd_predication.ipynb`.

**In simple terms:** Give it a spot, district, category, and date — it
predicts roughly how many people will visit, then labels it 🟢 Quiet,
🟡 Moderate, 🟠 Busy, or 🔴 Very Crowded.

**Trained on:** real historical visitor counts — the `spot_visitors` table.

**Good to know:** The model is much better at telling *which spot* is
popular than *which month* is busy (confirmed in the training notebook's
own analysis). So one extra rule sits on top: 🟠 **Busy** and 🔴 **Very
Crowded** only ever appear when your travel date genuinely falls inside a
real festival window. Otherwise it stays at Moderate — even for a very
popular spot — so an ordinary Tuesday can't get mislabeled as
festival-level crowds. See `_festival_is_active()` in `backend/predict.py`.

**🔀 Flow:**
```
📝 Spot · District · Category · Date
        │
        ▼
🤖 XGBoost predicts a visitor count
        │
        ▼
🎉 Does the date fall inside a real festival?
   ├── ✅ Yes → 🟠 Busy or 🔴 Very Crowded allowed
   └── ❌ No  → capped at 🟡 Moderate
        │
        ▼
🟢🟡🟠🔴 Final Crowd Level
```

---

## 3. 🌦️ Weather Forecast

**Model:** an LSTM — a model built for predicting sequences (`pickles/best_climate_lstm_model.pt`), trained in `Climate_Forecast_EDA.ipynb`.

**In simple terms:** It learned how weather *changes* day to day, not just
what's typical. To forecast your travel date, it looks at the last several
days of real weather, predicts tomorrow, then feeds that guess back in to
predict the day after — walking forward one day at a time until it
reaches your travel date.

That makes it a genuine forward forecast — it works for any future date,
not just a lookup of "what usually happens this time of year."

**🔀 Flow:**
```
📈 Last several days of real weather
        │
        ▼
🔁 LSTM predicts Day 1's change  ──┐
        │                          │ (feeds back in)
        ▼                          │
🔁 LSTM predicts Day 2's change  ◄─┘
        │
       ... repeats until your travel date ...
        │
        ▼
➕ Add up every predicted daily change
        │
        ▼
🌡️ Final forecast for your travel date

        More than 14 days away?
        │
        ▼
🔀 Blend in that month's usual weather pattern too
```

**One smart adjustment:** walking forward day-by-day alone can drift off
track for dates far in the future (e.g. it might just keep trending
"rainy" if the data happens to end during monsoon). So for trips more than
`CLIMATE_BLEND_HORIZON_DAYS` (14) days away, the forecast blends in that
month's usual historical weather pattern too — nearer-term forecasts still
trust the day-by-day walk on its own.

**Output:** predicted high temp, predicted low temp, chance of rain.

---

## 4. 🔔 Amenities

**Not an AI model** — a simple, honest lookup. Every spot has its nearby
restaurants, ATMs, and hospitals stored directly in the `amenities` table
(see `get_amenities()` in `backend/predict.py`). If a spot doesn't have
this info yet, the app says "not available" instead of guessing.

---

## 📝 Where predictions get saved

Every time you hit "Generate Predictions," the app saves your full
request and the full result — cost, crowd, and climate — with a timestamp
to `App/predictions_log.txt`. Automatic, no setup needed.