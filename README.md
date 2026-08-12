# 🧭 Smart Tourism Telangana — FastAPI + Streamlit

An AI-powered trip planner for Telangana. Tell it where you want to go and
when — it predicts your trip cost 💸, how crowded it'll be 👥, and the
weather 🌦️, all in one place. Built with FastAPI (backend + trained
models) and Streamlit (frontend), reading from a local SQLite database.

This README follows the same structure as the app itself: **Project
Overview** first, then **Predictions & Modules**, then how to set it up
and run it.

---

## 1. 📋 Project Overview

*A Multi-Fusion AI-Powered Smart Tourism Platform — combining tourist
demand forecasting, real-time crowd analytics, climate assessment, and
personalized recommendations into one budget-aware trip planner for
Telangana.*

### 🧩 What it does

Fill in one simple form — district, spot(s), dates, group size, transport,
hotel tier — and three AI models do the thinking for you. You get one
clean results page with everything you need to decide.

### 🔀 How it flows, end to end

```
📝 You fill the trip form
        │
        ▼
🖥️  STREAMLIT frontend sends it to the backend
        │
        ▼
⚡ FASTAPI backend receives your request
        │
        ▼
🤖 3 AI models run at once
   ├── 💸 Cost model
   ├── 👥 Crowd model
   └── 🌦️ Climate model
        │
        ▼
📊 One results page — cost, crowd, weather,
   packing tips, festivals, best route
```

### ✨ What you can do with it

| Feature | In plain terms | Why it matters |
|---|---|---|
| 🧭 **Trip Setup** | One form for district, spot(s), dates, group size, transport, and hotel tier. | Everything else in the app runs off this one form. |
| 💸 **Cost Estimate** | See what your trip will cost, split into stay, food, travel, tickets, and extras. | Compare trips of different lengths and group sizes fairly. |
| 👥 **Crowd Forecast** | See if a spot will be quiet or packed on your dates. | Helps you avoid the rush — or dodge it on purpose. |
| 🌦️ **Weather Forecast** | See the expected temperature and rain chance for your travel dates. | Real forward forecasting, not just "here's what usually happens." |
| 🎒 **Packing Tips** | Simple packing suggestions based on the weather forecast. | Turns raw numbers into "bring an umbrella" advice. |
| 🌟 **Good Time to Visit** | One badge — Great / Good / Fair / Not Ideal — combining crowd + weather. | One glance instead of checking two separate things. |
| 🔔 **Nearby Amenities** | Restaurants, ATMs, and hospitals near your spot. | Practical, useful info while you're actually there. |
| ⭐ **Spot Rating & Popularity** | See how popular a spot is before you commit to visiting. | Helps you pick between similar options. |
| 🎉 **Festival Calendar** | See which festivals fall during your trip. | A heads-up on busier — or more fun — days. |
| 🗺️ **Best Route** | For multi-spot trips, get the shortest order to visit them in. | Saves real travel time, not just a random order. |
| 🚗 **Transport Suggestions** | A recommended way to travel, based on group size — you can always change it. | Quick guidance, never forced on you. |

---

## 2. 🧠 Predictions & Modules

### 🤖 The three AI models

| Prediction | Model | Simple explanation |
|---|---|---|
| 💸 **Cost** | XGBoost (trained on real trip data) | Looks at your trip's length, group size, distance, transport, and hotel tier, and estimates what you'll spend — split into stay, food, tickets, and extras. Travel cost uses a real fuel-price formula instead of a guess, so it stays accurate as prices change. |
| 👥 **Crowd** | XGBoost (trained on real visitor counts) | Looks at how busy that exact spot has been in the past, by month and by festival, and predicts how crowded your dates will be. It only shows **Busy** or **Very Crowded** when your date genuinely falls during a real festival — so an ordinary day won't be mislabeled as festival-level crowds. |
| 🌦️ **Climate** | LSTM (a weather-trend model) | Looks at the last few days of real weather and predicts how it'll change from there — like guessing tomorrow's weather from today's trend, stretched out to your travel dates. For trips more than 2 weeks away, it also blends in that month's usual weather pattern. |

### ⚙️ Supporting infrastructure

| Module | What it does |
|---|---|
| ⚡ **FastAPI backend** | Handles every prediction and lookup request from the app. |
| 🗄️ **SQLite database** | Stores every spot, visitor record, and weather reading the models use. |
| 🧮 **scikit-learn preprocessing** | Turns your form answers into the exact format each model expects. |
| 🗺️ **Route optimization** | Works out real distances between spots and finds the shortest order to visit them. |
| 🎉 **Festival calendar** | Uses real festival dates where known, and a typical month otherwise. |
| 🎒 **Packing-tip engine** | Simple rules (not AI) that turn weather numbers into packing advice. |
| 🖥️ **Streamlit frontend** | The app you actually see and click through, plus all its charts. |

---

## 3. ⚙️ Setup

### 📦 Model & data files

Copy your 4 model files into `App/pickles/` and `smart_tourism.db` into
`App/data/`.

### 📥 Install dependencies

```bash
cd App/backend && pip install -r requirements.txt
cd ../frontend && pip install -r requirements.txt
```

### ▶️ Run it — two terminals

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
Runs at `http://127.0.0.1:8501`. Start the backend first — the frontend
shows a clear error with the exact command if it isn't running yet.

---

## 4. 📝 Good to know

- 🎉 **Festivals:** dates shift year to year (many follow the lunar
  calendar), so real confirmed dates are used where known, and a typical
  month otherwise.
- 👥 **Crowd labels:** Busy/Very Crowded only ever show up when your date
  is genuinely inside a real festival window — this is on purpose, not a
  bug, since a popular spot could otherwise look "Busy" every single day.
- 🗺️ **Best route:** exact for smaller trips, a quick smart-guess for
  bigger ones — your first spot always stays the starting point.
- 💤 **Not used yet:** the app has hotel data and spot-review data on hand
  that nothing currently uses — good material for a future "suggest a
  hotel" or "similar spots" feature.

See `PREDICTIONS.md` for the deeper technical detail behind each model.