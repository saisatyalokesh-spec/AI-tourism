# What This App Predicts, and How

## 1. Cost Estimation
**Model:** `pickles/best_trip_cost_model.pkl` — a `MultiOutputRegressor` wrapping
5 XGBoost regressors, trained in `eda_trip_budget_prediction.ipynb`.

**Inputs:** duration (days), number of travelers, route distance (km),
transport mode, accommodation tier, season.

**Data it was trained on:** `data/trip_budget_prediction_dataset.csv`.

**Output:** five cost components — travel, stay, food, entry fees, tolls &
parking — summed into a total estimated cost.

## 2. Crowd / Footfall Prediction
**Model:** `pickles/best_model.pkl` — an XGBoost regressor, trained in
`Crowd_predication.ipynb`.

**Inputs:** spot name, district, category, year, month, season, festival.

**Data it was trained on:** `data/spot_visitors.csv`.

**Output:** predicted visitor count for that spot in that month, bucketed
into a Quiet / Moderate / Busy / Very Crowded label.

**Note:** the trained model leans much more on *which spot* than *which
month* — confirmed in the notebook's own correlation analysis — so
predictions for the same spot across different months may look similar.

## 3. Climate Forecast
**Model:** `pickles/best_climate_lstm_model.pt` + `best_climate_metadata.pkl`
— a 1-layer PyTorch LSTM, trained in `Climate_Forecast_EDA.ipynb`.

**How it actually works (this matters):** the model was trained on the
*day-to-day change* (`.diff()`) in the statewide daily average of
`Temperature_Max_C`, `Temperature_Min_C`, and a derived `Rainfall_Percent`
(a rolling 7-day % of rain-days per district, rain day = ≥1mm rainfall). To
forecast a future date, the backend:

1. Rebuilds that statewide daily series from `data/Climate_Dataset_Final.csv`.
2. Takes the last 7 days of it and feeds them through the LSTM, one day at a
   time, feeding each prediction back in as the next input (autoregressive).
3. Adds up all the predicted daily changes between the dataset's last known
   date and your travel date.
4. Adds that cumulative change to the chosen district's last known actual
   reading, to get the final forecast.

This is a genuine forward prediction, not a lookup of the closest historical
row — it works for any future date, not just ones near existing data.

**Seasonal blend:** the day-to-day diff walk above has no notion of season —
left alone, it just drifts roughly linearly away from whatever the dataset's
last known date looked like (e.g. always trending "rainy" if the dataset
happens to end during monsoon). Past `CLIMATE_BLEND_HORIZON_DAYS` (14 days,
see `backend/predict.py`), the forecast is blended toward that district's
historical average for the target date's calendar month, computed from every
year in `data/Climate_Dataset_Final.csv`. Nearer-term forecasts (within 14
days of the dataset's last date) still trust the LSTM's own walk.

**Output:** predicted max temp, predicted min temp, rain chance (%).

## 4. Amenities
**Not a trained model** — a direct lookup. Looks for an `Amenities` column
on `data/spot_visitors.csv` (comma-separated values per spot). If that
column doesn't exist yet, the app shows "not available" rather than
guessing — add the column to enable this.

## Where each prediction gets logged

Every time you hit "Generate Predictions," the backend logs the full
request (district, spot, trip details) and the full result (cost, crowd,
climate) with a timestamp to `predictions_log.txt` in the project root —
always, with zero setup. If you've configured Supabase (see
`backend/database/.env.example`), the same record is also inserted into a
`trip_predictions` table there.
