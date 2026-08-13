"""
predict.py — loads the trained models and turns request data into predictions.

Data & model locations (relative to the App/ folder):
    App/pickles/best_trip_cost_model.pkl        cost model (MultiOutput XGBoost)
    App/pickles/best_model.pkl                    crowd model (XGBoost)
    App/pickles/best_climate_lstm_model.pt          climate model weights (PyTorch LSTM)
    App/pickles/best_climate_metadata.pkl            climate model metadata (seq_len, target_cols)
    App/data/smart_tourism.db                          SQLite database — replaces the old CSVs. Tables used:
                                                           trip_budget_prediction  (cost model's training data)
                                                           spot_visitors           (crowd model's training data
                                                                                     + spot/district list)
                                                           climate_dataset         (climate readings — Tourist_Spots,
                                                                                     District, Date, Temperature_Max_C/
                                                                                     Min_C, Rainfall_mm, ...)
                                                           amenities               (spot_name, district, amenity_name,
                                                                                     amenity_type, lat, lon)
                                                         Also present but not yet wired into an endpoint:
                                                           accommodations, other_spots (with review text + embeddings).

Amenities now come from the database's dedicated `amenities` table (spot_name,
amenity_name, amenity_type) instead of a comma-separated CSV column — see
get_amenities() below.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from dotenv import load_dotenv
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler
from sqlalchemy import create_engine, text

APP_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = APP_ROOT.parent
PICKLES_DIR = APP_ROOT / "pickles"
DATA_DIR = APP_ROOT / "data"
DB_PATH = DATA_DIR / "smart_tourism.db"

# Load the same .env used by migrate_to_supabase.py (Tourism Project/.env),
# regardless of the working directory the server is started from.
load_dotenv(PROJECT_ROOT / ".env")
SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")

# If SUPABASE_DB_URL is set, every query in this module goes to Supabase
# Postgres instead of the local smart_tourism.db file. Falls back to the
# local SQLite file automatically if the variable isn't set, so the app
# still works with zero setup.
_engine = create_engine(SUPABASE_DB_URL, pool_pre_ping=True) if SUPABASE_DB_URL else None

BUDGET_MODEL_PATH = PICKLES_DIR / "best_trip_cost_model.pkl"
CROWD_MODEL_PATH = PICKLES_DIR / "best_model.pkl"
CLIMATE_MODEL_PATH = PICKLES_DIR / "best_climate_lstm_model.pt"
CLIMATE_METADATA_PATH = PICKLES_DIR / "best_climate_metadata.pkl"

BUDGET_NUMERIC_COLS = ["duration_days", "num_travelers", "route_distance_km"]
BUDGET_ORDINAL_COLS = ["accommodation_tier"]
BUDGET_NOMINAL_COLS = ["transport_mode", "season"]

RAIN_THRESHOLD_MM = 1.0  # matches Climate_Forecast_EDA.ipynb's rain-day definition

# ---------------------------------------------------------------------------
# Spot-to-spot distance assumptions.
#
# The other_spots table carries a distinct Latitude/Longitude per individual
# tourist spot (271 spots, 271 unique coordinate pairs — no two spots share
# a point), so real point-to-point distance is computed with the Haversine
# formula for every pair, including spots in the same district. The
# climate_dataset table is kept as a fallback for any spot that's only
# present there (its coordinates are recorded per *district*, so it's only
# meaningful for comparing spots across different districts).
# Roads are never a straight line, so a fixed detour factor is applied on
# top of the great-circle distance to get a more realistic
# "distance you'd actually drive" figure.
# ---------------------------------------------------------------------------

EARTH_RADIUS_KM = 6371.0
ROAD_DISTANCE_FACTOR = 1.3  # typical straight-line-to-road-distance multiplier


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1_r, lon1_r, lat2_r, lon2_r = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1_r) * np.cos(lat2_r) * np.sin(dlon / 2) ** 2
    return float(2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a)))


@lru_cache(maxsize=1)
def _other_spots_coordinates() -> Dict[str, Tuple[float, float]]:
    """One (lat, lon) per tourist spot, read from the other_spots table —
    real per-spot coordinates, not the one-per-district figures in
    climate_dataset."""
    with get_db_connection() as conn:
        df = pd.read_sql_query("SELECT name, lat, lon FROM other_spots", conn)
    df = df.dropna(subset=["lat", "lon"]).drop_duplicates(subset=["name"])
    return {row.name: (float(row.lat), float(row.lon)) for row in df.itertuples(index=False)}


@lru_cache(maxsize=1)
def get_spot_coordinates() -> Dict[str, Tuple[float, float]]:
    """One (lat, lon) per tourist spot. other_spots (real per-spot
    coordinates) takes priority; climate_dataset fills in any spot only
    present there (coordinates recorded per *district* in that table, so
    only meaningful for cross-district comparisons)."""
    _, _, climate_df = load_project_data()
    coords = dict(_other_spots_coordinates())
    climate_coords = (
        climate_df.dropna(subset=["Latitude", "Longitude"])
        .drop_duplicates(subset=["Tourist Spots"])
        .set_index("Tourist Spots")[["Latitude", "Longitude"]]
    )
    for spot, row in climate_coords.iterrows():
        coords.setdefault(spot, (float(row.Latitude), float(row.Longitude)))
    return coords


def get_spot_coordinate(spot_name: str) -> Tuple[float, float] | None:
    return get_spot_coordinates().get(spot_name)


@lru_cache(maxsize=1)
def get_spot_district_map() -> Dict[str, str]:
    """spot name -> district, combining the spot_visitors table (primary) and
    the climate_dataset table (fallback for spots only present there)."""
    budget_df, visitors_df, climate_df = load_project_data()
    mapping = dict(zip(visitors_df["Spot_Name"], visitors_df["District"]))
    for spot, district in zip(climate_df["Tourist Spots"], climate_df["District"]):
        mapping.setdefault(spot, district)
    return mapping


def get_spot_district(spot_name: str) -> str | None:
    return get_spot_district_map().get(spot_name)


# Fallback only: used when a spot has no coordinate in either other_spots or
# climate_dataset, so a real point-to-point distance can't be computed at
# all. This flat figure stands in for "a short local hop within the same
# district" instead of reporting a false 0 km.
SAME_DISTRICT_ASSUMED_KM = 25.0


def compute_distance_km(spot_a: str, spot_b: str) -> Dict[str, object]:
    """Distance between two spots. Returns a dict with:
      - distance_km: float, or None if nothing could be determined
      - method: "haversine" (real Haversine x road-factor calculation, using
                per-spot coordinates from other_spots — works for same- and
                cross-district pairs alike), "same_district_assumed" (flat
                local-hop fallback, only used when coordinates are missing
                for a same-district pair), or "unavailable" (coordinates
                unknown for a spot and districts differ or are unknown)
    """
    if spot_a == spot_b:
        return {"distance_km": 0.0, "method": "same_spot"}

    coord_a = get_spot_coordinate(spot_a)
    coord_b = get_spot_coordinate(spot_b)
    if coord_a is not None and coord_b is not None:
        straight_line_km = _haversine_km(coord_a[0], coord_a[1], coord_b[0], coord_b[1])
        return {"distance_km": round(straight_line_km * ROAD_DISTANCE_FACTOR, 1), "method": "haversine"}

    district_a = get_spot_district(spot_a)
    district_b = get_spot_district(spot_b)
    if district_a is not None and district_a == district_b:
        return {"distance_km": SAME_DISTRICT_ASSUMED_KM, "method": "same_district_assumed"}

    return {"distance_km": None, "method": "unavailable"}


def compute_chain_distances(spot_names: List[str]) -> Dict[str, object]:
    """Leg-by-leg distance for an ordered list of spots (a simple itinerary
    visiting each in turn), plus the total. Legs with no usable data are
    flagged (method="unavailable") rather than silently dropped."""
    legs = []
    total_km = 0.0
    all_available = True
    for spot_a, spot_b in zip(spot_names, spot_names[1:]):
        leg = compute_distance_km(spot_a, spot_b)
        available = leg["distance_km"] is not None
        if not available:
            all_available = False
        legs.append({
            "from_spot": spot_a, "to_spot": spot_b,
            "distance_km": leg["distance_km"], "available": available, "method": leg["method"],
        })
        total_km += leg["distance_km"] or 0.0
    return {"legs": legs, "total_km": round(total_km, 1), "all_available": all_available}

# Known category lists the crowd model was trained on (Crowd_predication.ipynb).
# Hardcoded rather than inferred from the database so a table missing a rare
# value never silently produces the wrong number of columns.
CROWD_CATEGORY_VALUES = ["heritage", "leisure", "nature", "other", "religious"]
CROWD_FESTIVAL_VALUES = [
    "Bathukamma, Dussehra", "Bhogi, Sankranti", "Bonalu", "Buddha Purnima", "Christmas",
    "Diwali", "Holi", "Independence Day, Krishna Janmashtami", "Maha Shivaratri", "None",
    "Ugadi, Sri Rama Navami", "Vinayaka Chavithi",
]
CROWD_MONTH_VALUES = [
    "April", "August", "December", "February", "January", "July", "June",
    "March", "May", "November", "October", "September",
]
CROWD_SEASON_VALUES = ["Monsoon", "Post-Monsoon", "Summer", "Winter"]

# Rough transport-capacity guidance for the "suggest transport by group size" ask.
# Not a hard rule — the frontend uses this to highlight sensible options, the
# user can still pick anything.
TRANSPORT_CAPACITY = {
    "bike": (1, 2),
    "auto": (1, 3),
    "car": (1, 5),
    "bus": (4, 50),
    "train": (1, 50),
}

# ---------------------------------------------------------------------------
# Realistic travel cost assumptions.
#
# The trained cost model's travel_cost_est is replaced with a plain
# fuel/fare-based formula — it's easier to trust and explain than a learned
# number, and easy to tune as real-world prices drift. All figures are rough
# India-wide, present-day assumptions; adjust freely for your context.
# ---------------------------------------------------------------------------

PETROL_PRICE_PER_LITRE = 105.0  # ₹/litre, roughly representative nationwide

# Realistic on-road mileage (km per litre) for two-wheelers/cars. A bike
# typically does 30-40 km/l, so 35 is used as the middle of that range.
MODE_FUEL_EFFICIENCY_KMPL = {
    "bike": 35.0,
    "auto": 22.0,   # auto-rickshaws vary (CNG/petrol); treated as petrol-equivalent
    "car": 15.0,
}

# How many travelers a single vehicle of that type comfortably seats —
# used to work out how many vehicles the group actually needs.
VEHICLE_SEATS = {
    "bike": 2,
    "auto": 3,
    "car": 4,
}

# Public transport is priced per traveler per km rather than by fuel burned.
BUS_FARE_PER_KM_PER_TRAVELER = 1.5   # ₹/km/traveler, typical state-run bus fare
TRAIN_FARE_PER_KM_PER_TRAVELER = 1.0  # ₹/km/traveler, typical general/sleeper fare


def estimate_realistic_travel_cost(transport_mode: str, route_distance_km: float, num_travelers: int) -> float:
    """Round-trip travel cost using plain petrol-price/mileage or per-km fare
    math instead of the trained model's learned estimate."""
    mode = str(transport_mode).strip().lower()
    round_trip_km = max(0.0, float(route_distance_km)) * 2
    travelers = max(1, int(num_travelers))

    if mode in MODE_FUEL_EFFICIENCY_KMPL:
        seats = VEHICLE_SEATS[mode]
        vehicles_needed = -(-travelers // seats)  # ceil division
        litres_needed = (round_trip_km / MODE_FUEL_EFFICIENCY_KMPL[mode]) * vehicles_needed
        return round(litres_needed * PETROL_PRICE_PER_LITRE, 2)
    if mode == "bus":
        return round(round_trip_km * BUS_FARE_PER_KM_PER_TRAVELER * travelers, 2)
    if mode == "train":
        return round(round_trip_km * TRAIN_FARE_PER_KM_PER_TRAVELER * travelers, 2)

    # Unknown mode — fall back to the car-equivalent formula for a sane number.
    litres_needed = round_trip_km / MODE_FUEL_EFFICIENCY_KMPL["car"]
    return round(litres_needed * PETROL_PRICE_PER_LITRE, 2)


class ClimateLSTM(nn.Module):
    """Architecture reconstructed from the trained state_dict's weight shapes
    (input_size=3: Temperature_Max_C, Temperature_Min_C, Rainfall_Percent)."""

    def __init__(self, input_size=3, hidden_size=24, num_layers=1, output_size=3, dropout=0.2):
        super().__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True)
        self.dropout = nn.Dropout(dropout)
        self.fc = nn.Linear(hidden_size, output_size)

    def forward(self, x):
        out, _ = self.lstm(x)
        out = self.dropout(out[:, -1, :])
        return self.fc(out)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def get_db_connection():
    """Connection to the project database.

    Returns a SQLAlchemy connection to Supabase Postgres when SUPABASE_DB_URL
    is set (see Tourism Project/.env) AND that connection actually works;
    otherwise falls back to a read-only connection to the local
    App/data/smart_tourism.db SQLite file. Both support the same
    `with get_db_connection() as conn:` / pd.read_sql_query usage used
    throughout this module.

    A broken or unreachable SUPABASE_DB_URL (wrong host, paused project,
    bad password, no network egress to Supabase from wherever this is
    deployed, etc.) no longer takes the whole app down — it falls back to
    SQLite the same as if SUPABASE_DB_URL had never been set, and prints
    one line explaining why so it's still visible in the logs.
    """
    if _engine is not None and _supabase_reachable():
        return _engine.connect()
    uri = f"file:{DB_PATH.as_posix()}?mode=ro"
    return sqlite3.connect(uri, uri=True, check_same_thread=False)


@lru_cache(maxsize=1)
def _supabase_reachable() -> bool:
    """Tests the Supabase connection exactly once per process and caches
    the result — so a broken SUPABASE_DB_URL doesn't re-attempt (and
    re-wait on) a slow DNS/connect failure on every single query; every
    call after the first failure falls back to SQLite immediately. Only
    reached when _engine is not None (SUPABASE_DB_URL was set)."""
    try:
        with _engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        print(f"[predict] Supabase unreachable, falling back to local SQLite for this session: {e}")
        return False


def log_interaction(spot_name: str, action_type: str) -> None:
    """Records one row in Supabase's user_interactions table (spot_name,
    action_type, timestamp). Only active when SUPABASE_DB_URL is set AND
    reachable — a no-op against the local SQLite fallback, since that
    table only exists in Supabase (created by migrate_to_supabase.py).
    Never raises: a logging failure should never break the request that
    triggered it."""
    if _engine is None or not _supabase_reachable():
        return
    try:
        with _engine.begin() as conn:
            conn.execute(
                text("INSERT INTO user_interactions (spot_name, action_type) VALUES (:spot_name, :action_type)"),
                {"spot_name": spot_name, "action_type": action_type},
            )
    except Exception as e:  # pragma: no cover
        print(f"[predict] Could not log interaction to Supabase: {e}")


def _normalize_columns(df: pd.DataFrame, canonical_names: List[str]) -> pd.DataFrame:
    """Renames df's columns to match canonical_names, case/spacing-insensitively.

    Needed because migrate_to_supabase.py lowercases every column name
    before uploading to Postgres (df.columns = [c.lower()...]), while this
    module (and the local SQLite database) uses the original mixed-case
    names, e.g. "Spot_Name" rather than "spot_name". Works unchanged
    whether the data came from Supabase (lowercase) or local SQLite
    (original case)."""
    def _key(name: str) -> str:
        return name.strip().lower().replace(" ", "_").replace("-", "_")

    lookup = {_key(c): c for c in df.columns}
    rename_map = {}
    for canonical in canonical_names:
        actual = lookup.get(_key(canonical))
        if actual is not None and actual != canonical:
            rename_map[actual] = canonical
    return df.rename(columns=rename_map)


@lru_cache(maxsize=1)
def load_project_data() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Loads the three core tables from smart_tourism.db (replaces the old
    trip_budget_prediction_dataset.csv / spot_visitors.csv /
    Climate_Dataset_Final.csv reads)."""
    with get_db_connection() as conn:
        budget_df = pd.read_sql_query("SELECT * FROM trip_budget_prediction", conn)
        visitors_df = pd.read_sql_query("SELECT * FROM spot_visitors", conn)
        climate_df = pd.read_sql_query("SELECT * FROM climate_dataset", conn)

    visitors_df = _normalize_columns(
        visitors_df, ["Spot_Name", "District", "Category", "Month", "Season", "Festival", "Year"]
    )
    climate_df = _normalize_columns(
        climate_df,
        [
            "Tourist_Spots", "District", "Date", "Latitude", "Longitude",
            "Temperature_Max_C", "Temperature_Min_C", "Rainfall_mm",
        ],
    )

    # The DB column is Tourist_Spots (underscore); the rest of this module
    # was written against the CSV's "Tourist Spots" (space) name, so it's
    # renamed once here rather than touching every call site below.
    climate_df = climate_df.rename(columns={"Tourist_Spots": "Tourist Spots"})

    budget_df["season"] = budget_df["season"].astype(str)
    budget_df["transport_mode"] = budget_df["transport_mode"].astype(str)
    budget_df["accommodation_tier"] = budget_df["accommodation_tier"].astype(str)

    visitors_df["Spot_Name"] = visitors_df["Spot_Name"].astype(str)
    visitors_df["District"] = visitors_df["District"].astype(str)
    visitors_df["Category"] = visitors_df["Category"].astype(str)
    visitors_df["Month"] = visitors_df["Month"].astype(str)
    visitors_df["Season"] = visitors_df["Season"].astype(str)
    visitors_df["Festival"] = visitors_df["Festival"].fillna("None").astype(str)

    climate_df["Tourist Spots"] = climate_df["Tourist Spots"].astype(str)
    climate_df["District"] = climate_df["District"].astype(str)
    climate_df["Date"] = pd.to_datetime(climate_df["Date"])

    return budget_df, visitors_df, climate_df


@lru_cache(maxsize=1)
def get_district_spot_map() -> Tuple[List[str], Dict[str, List[str]]]:
    _, visitors_df, _ = load_project_data()
    districts = sorted(visitors_df["District"].dropna().unique().tolist())
    spot_map = {}
    for district in districts:
        spots = sorted(visitors_df.loc[visitors_df["District"] == district, "Spot_Name"].dropna().unique().tolist())
        spot_map[district] = spots
    return districts, spot_map


def get_districts() -> List[str]:
    districts, _ = get_district_spot_map()
    return districts


def get_spots_by_district(district: str, category: str | None = None) -> List[str]:
    _, spot_map = get_district_spot_map()
    spots = spot_map.get(district, [])
    if category:
        _, visitors_df, _ = load_project_data()
        in_category = set(
            visitors_df.loc[visitors_df["Category"] == category, "Spot_Name"].dropna().unique().tolist()
        )
        spots = [s for s in spots if s in in_category]
    return spots


def get_all_spots() -> List[str]:
    _, visitors_df, _ = load_project_data()
    return sorted(visitors_df["Spot_Name"].dropna().unique().tolist())


def get_cost_input_options() -> Dict[str, List[str]]:
    budget_df, visitors_df, _ = load_project_data()
    return {
        "transport_modes": sorted(budget_df["transport_mode"].dropna().unique().tolist()),
        "accommodation_tiers": ["Budget", "Mid", "Premium"],
        "seasons": sorted(budget_df["season"].dropna().unique().tolist()),
        "categories": sorted(visitors_df["Category"].dropna().unique().tolist()),
        "months": sorted(visitors_df["Month"].dropna().unique().tolist()),
        "festivals": sorted(visitors_df["Festival"].dropna().fillna("None").unique().tolist()),
        "years": sorted(visitors_df["Year"].dropna().unique().tolist()),
    }


def suggest_transport_modes(num_travelers: int) -> List[str]:
    """Transport modes ordered by how well they fit the group size — the
    frontend defaults to the first entry but the user can still tap any mode:

    - exactly 2 travelers: a bike is the ideal, most economical fit
    - up to 3 travelers:   an auto comfortably seats the group
    - up to 5 travelers:   a car comfortably seats the group
    - more than 5:         too many for a car/auto/bike — bus and train
                            are the practical choices (bus first, then train)
    """
    if num_travelers > 5:
        priority = ["bus", "train", "car", "auto", "bike"]
    elif num_travelers == 2:
        priority = ["bike", "auto", "car", "bus", "train"]
    elif num_travelers <= 3:
        priority = ["auto", "car", "bike", "bus", "train"]
    else:  # 4 or 5
        priority = ["car", "auto", "bus", "train", "bike"]
    known = list(TRANSPORT_CAPACITY.keys())
    # Keep the ordering even if a mode isn't in TRANSPORT_CAPACITY (future-proof).
    return [m for m in priority if m in known] + [m for m in known if m not in priority]


# ---------------------------------------------------------------------------
# Cost prediction
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_budget_preprocessor() -> ColumnTransformer:
    budget_df, _, _ = load_project_data()

    numeric_pipe = Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
    ])
    ordinal_pipe = Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("ordinal", OrdinalEncoder(categories=[["Budget", "Mid", "Premium"]],
                                    handle_unknown="use_encoded_value", unknown_value=-1)),
    ])
    nominal_pipe = Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
    ])

    preprocessor = ColumnTransformer(transformers=[
        ("num", numeric_pipe, BUDGET_NUMERIC_COLS),
        ("ord", ordinal_pipe, BUDGET_ORDINAL_COLS),
        ("cat", nominal_pipe, BUDGET_NOMINAL_COLS),
    ])
    X = budget_df[BUDGET_NUMERIC_COLS + BUDGET_ORDINAL_COLS + BUDGET_NOMINAL_COLS]
    preprocessor.fit(X)
    return preprocessor


@lru_cache(maxsize=1)
def get_budget_model():
    return joblib.load(BUDGET_MODEL_PATH)


def predict_budget_cost(form_data: Dict[str, object]) -> Dict[str, float]:
    model = get_budget_model()
    preprocessor = get_budget_preprocessor()

    row = pd.DataFrame([{
        "duration_days": float(form_data["duration_days"]),
        "num_travelers": float(form_data["num_travelers"]),
        "route_distance_km": float(form_data["route_distance_km"]),
        "transport_mode": str(form_data["transport_mode"]),
        "accommodation_tier": str(form_data["accommodation_tier"]),
        "season": str(form_data["season"]),
    }])

    transformed = preprocessor.transform(row)
    pred = model.predict(transformed)
    result = {
        # travel_cost_est comes from the realistic petrol/fare formula below,
        # not the trained model's output — see estimate_realistic_travel_cost().
        "travel_cost_est": estimate_realistic_travel_cost(
            transport_mode=form_data["transport_mode"],
            route_distance_km=form_data["route_distance_km"],
            num_travelers=form_data["num_travelers"],
        ),
        "stay_cost_est": float(pred[0][1]),
        "food_cost_est": float(pred[0][2]),
        "entry_fees_est": float(pred[0][3]),
        "tolls_and_parking_est": float(pred[0][4]),
    }
    result["total_estimated_cost"] = float(sum(result.values()))
    return result


# ---------------------------------------------------------------------------
# Crowd prediction
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_crowd_preprocessor() -> ColumnTransformer:
    _, visitors_df, _ = load_project_data()

    onehot_cols = ["Category", "Festival", "Month", "Season"]
    ordinal_cols = ["Spot_Name", "District"]
    passthrough_cols = ["Year"]

    onehot_pipe = Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(
            categories=[CROWD_CATEGORY_VALUES, CROWD_FESTIVAL_VALUES, CROWD_MONTH_VALUES, CROWD_SEASON_VALUES],
            handle_unknown="ignore", sparse_output=False,
        )),
    ])
    ordinal_pipe = Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("ordinal", OrdinalEncoder(
            categories=[
                sorted(visitors_df["Spot_Name"].dropna().unique().tolist()),
                sorted(visitors_df["District"].dropna().unique().tolist()),
            ],
            handle_unknown="use_encoded_value", unknown_value=-1,
        )),
    ])

    preprocessor = ColumnTransformer(
        transformers=[("onehot", onehot_pipe, onehot_cols), ("ordinal", ordinal_pipe, ordinal_cols)],
        remainder="passthrough",
    )
    X = visitors_df[onehot_cols + ordinal_cols + passthrough_cols]
    preprocessor.fit(X)
    return preprocessor


@lru_cache(maxsize=1)
def get_crowd_model():
    return joblib.load(CROWD_MODEL_PATH)


def _festival_is_active(festival: object, target_date: object) -> bool:
    """Return True only when the travel date is actually inside a festival window.

    The crowd UI intentionally reserves the Busy / Very Crowded labels for
    festival periods. On normal days, the highest displayed level is Moderate.
    Verified 2026 dates are used when available; for future years we fall back
    to the festival's typical month rather than inventing an exact date.
    """
    festival_name = str(festival or "None")
    if festival_name == "None":
        return False
    if not isinstance(target_date, date):
        try:
            target_date = date.fromisoformat(str(target_date))
        except Exception:
            return False

    known_dates = FESTIVAL_DATES.get(target_date.year, {}).get(festival_name, ())
    if known_dates:
        return target_date in known_dates

    month_name = FESTIVAL_TYPICAL_MONTH.get(festival_name)
    return bool(month_name and MONTH_NUMBER.get(month_name) == target_date.month)


def crowd_level_label(visitors: float, festival_active: bool = False) -> str:
    """Translate visitor count into a user-facing crowd level.

    Busy and Very Crowded are intentionally festival-only labels. This keeps
    ordinary travel dates from being presented as festival-level crowds even
    when the regression model returns a relatively high historical estimate.
    """
    if not festival_active:
        if visitors < 1000:
            return "Quiet"
        return "Moderate"
    if visitors < 1000:
        return "Quiet"
    if visitors < 5000:
        return "Moderate"
    if visitors < 20000:
        return "Busy"
    return "Very Crowded"


def predict_crowd_count(form_data: Dict[str, object]) -> float:
    model = get_crowd_model()
    preprocessor = get_crowd_preprocessor()

    row = pd.DataFrame([{
        "Spot_Name": str(form_data["spot_name"]),
        "District": str(form_data["district"]),
        "Category": str(form_data["category"]),
        "Year": int(form_data["year"]),
        "Month": str(form_data["month"]),
        "Season": str(form_data["season"]),
        "Festival": str(form_data["festival"]),
    }])
    transformed = preprocessor.transform(row[["Category", "Festival", "Month", "Season", "Spot_Name", "District", "Year"]])
    pred = model.predict(transformed)[0]
    return float(max(pred, 0.0))


# ---------------------------------------------------------------------------
# Climate forecasting — real LSTM prediction, not a historical lookup.
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_climate_model():
    meta = joblib.load(CLIMATE_METADATA_PATH)
    state_dict = torch.load(CLIMATE_MODEL_PATH, map_location="cpu", weights_only=True)
    model = ClimateLSTM()
    model.load_state_dict(state_dict)
    model.eval()
    return model, meta


@lru_cache(maxsize=1)
def _climate_statewide_series() -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Rebuilds the day-to-day statewide series the LSTM was trained on:
    Temperature_Max_C, Temperature_Min_C, and a derived Rainfall_Percent
    (rolling 7-day % of rain-days per district), averaged across all spots."""
    _, _, climate_df = load_project_data()
    df = climate_df.copy()
    df["Is_Rain_Day"] = (df["Rainfall_mm"] >= RAIN_THRESHOLD_MM).astype(int)
    df["Rainfall_Percent"] = (
        df.groupby("District")["Is_Rain_Day"]
          .transform(lambda s: s.rolling(7, min_periods=1).mean() * 100)
    )
    statewide = df.groupby("Date")[["Temperature_Max_C", "Temperature_Min_C", "Rainfall_Percent"]].mean()
    statewide = statewide.asfreq("D").ffill()
    return df, statewide


# How many days past the dataset's last known date the LSTM's day-to-day diff
# walk is trusted on its own. Beyond this, its output is blended toward the
# historical per-district average for the target's calendar month, since the
# diff walk has no seasonal awareness and otherwise just drifts near-linearly
# from whatever the last known date happened to look like.
CLIMATE_BLEND_HORIZON_DAYS = 14

# Hard ceiling on how far ahead the day-by-day LSTM walk will run. Each day
# ahead is one full model pass in a plain Python loop with no early exit —
# a date picked with no upper bound (e.g. years out) would mean thousands
# of sequential forward passes on a single page load, which is slow enough
# to look like — and on a resource-limited host, potentially cause — a
# hung/crashed process rather than a clean error. The frontend's date
# picker already limits this to a year out; this is the backend's own
# floor under that, independent of any particular UI enforcing it.
CLIMATE_FORECAST_MAX_DAYS_AHEAD = 400

# A plain point forecast doesn't show its own uncertainty, so a confidence
# band is added that widens with how far out the day is — a rough but
# honest way to signal "less sure the further ahead this is", the same
# shape as a typical forecasting chart's shaded interval.
TEMP_BAND_BASE_C = 1.0
TEMP_BAND_PER_DAY_C = 0.35
TEMP_BAND_MAX_C = 6.0
RAIN_BAND_BASE_PCT = 6.0
RAIN_BAND_PER_DAY_PCT = 2.0
RAIN_BAND_MAX_PCT = 35.0

# How many days of real historical readings to show leading into the
# forecast on the climate chart.
CLIMATE_HISTORY_DAYS = 14


def get_recent_climate_history(district: str, days: int = CLIMATE_HISTORY_DAYS) -> List[Dict[str, object]]:
    """Actual historical daily readings for a district, the `days` before
    (and including) the dataset's last known date — the real 'so far' line
    the forecast continues from on the chart."""
    aug_df, statewide = _climate_statewide_series()
    last_known_date = statewide.index[-1]
    district_daily = aug_df.groupby(["District", "Date"])[
        ["Temperature_Max_C", "Temperature_Min_C", "Rainfall_Percent"]
    ].mean()
    known_districts = {d for d, _ in district_daily.index}
    if district not in known_districts:
        return []
    series = district_daily.xs(district, level="District").sort_index()
    series = series.loc[series.index <= last_known_date].tail(days)
    return [
        {
            "date": ts.date().isoformat(),
            "actual_max_temp": round(float(row["Temperature_Max_C"]), 1),
            "actual_min_temp": round(float(row["Temperature_Min_C"]), 1),
            "actual_rain_chance_percent": round(float(np.clip(row["Rainfall_Percent"], 0, 100)), 0),
        }
        for ts, row in series.iterrows()
    ]


@lru_cache(maxsize=1)
def _district_monthly_climatology() -> pd.DataFrame:
    """Historical average Temperature_Max_C, Temperature_Min_C, and
    Rainfall_Percent per (District, calendar month), used to correct the
    LSTM's forecast toward the real seasonal pattern for longer horizons."""
    aug_df, _ = _climate_statewide_series()
    df = aug_df.copy()
    df["Month"] = df["Date"].dt.month
    return df.groupby(["District", "Month"])[["Temperature_Max_C", "Temperature_Min_C", "Rainfall_Percent"]].mean()


def _climate_forecast_series(district: str, last_date: date) -> List[Dict[str, object]]:
    """Day-by-day LSTM forecast for `district`, for every date from the day
    after the dataset's last known reading through `last_date` (inclusive).
    One walk covers the whole window, so a multi-day chart doesn't cost one
    model pass per day."""
    model, meta = get_climate_model()
    seq_len = meta.get("seq_len", 7)

    aug_df, statewide = _climate_statewide_series()
    diffs = statewide.diff().dropna()
    last_known_date = statewide.index[-1]

    target_ts = pd.Timestamp(last_date)
    days_ahead = (target_ts.normalize() - last_known_date.normalize()).days
    if days_ahead < 1:
        raise ValueError(f"Pick a travel date after {last_known_date.date()} — that's the latest date in the dataset.")
    if days_ahead > CLIMATE_FORECAST_MAX_DAYS_AHEAD:
        raise ValueError(
            f"That date is {days_ahead} days ahead — this forecast walks forward one day at a time "
            f"from the dataset's last known reading, so dates more than "
            f"{CLIMATE_FORECAST_MAX_DAYS_AHEAD} days out aren't supported. Pick a nearer date."
        )

    current_seq = torch.tensor(diffs.values[-seq_len:], dtype=torch.float32).unsqueeze(0)
    future_diffs = []
    with torch.no_grad():
        for _ in range(days_ahead):
            next_diff = model(current_seq)
            future_diffs.append(next_diff.squeeze(0).numpy())
            current_seq = torch.cat([current_seq[:, 1:, :], next_diff.unsqueeze(1)], dim=1)
    cumulative_diffs = np.cumsum(future_diffs, axis=0)  # one row per day-ahead, running total

    district_daily = aug_df.groupby(["District", "Date"])[
        ["Temperature_Max_C", "Temperature_Min_C", "Rainfall_Percent"]
    ].mean()
    known_districts = {d for d, _ in district_daily.index}
    if district not in known_districts:
        raise ValueError(f"No climate data found for district '{district}'.")

    baseline = district_daily.xs(last_known_date, level="Date")
    baseline_series = baseline.loc[district] if district in baseline.index \
        else district_daily.xs(district, level="District").iloc[-1]

    climatology = _district_monthly_climatology()

    series: List[Dict[str, object]] = []
    for i, cumulative_diff in enumerate(cumulative_diffs, start=1):
        forecast = baseline_series.values + cumulative_diff
        predicted_max = float(forecast[0])
        predicted_min = float(forecast[1])
        rain_chance = float(np.clip(forecast[2], 0, 100))

        day_ts = last_known_date + pd.Timedelta(days=i)
        month = day_ts.month
        if (district, month) in climatology.index:
            hist = climatology.loc[(district, month)]
        else:
            hist = climatology.xs(month, level="Month").mean()

        lstm_weight = max(0.0, min(1.0, 1.0 - i / CLIMATE_BLEND_HORIZON_DAYS))
        predicted_max = lstm_weight * predicted_max + (1 - lstm_weight) * float(hist["Temperature_Max_C"])
        predicted_min = lstm_weight * predicted_min + (1 - lstm_weight) * float(hist["Temperature_Min_C"])
        rain_chance = lstm_weight * rain_chance + (1 - lstm_weight) * float(hist["Rainfall_Percent"])
        rain_chance = float(np.clip(rain_chance, 0, 100))

        temp_band = min(TEMP_BAND_MAX_C, TEMP_BAND_BASE_C + TEMP_BAND_PER_DAY_C * i)
        rain_band = min(RAIN_BAND_MAX_PCT, RAIN_BAND_BASE_PCT + RAIN_BAND_PER_DAY_PCT * i)

        series.append({
            "date": day_ts.date().isoformat(),
            "days_ahead": i,
            "predicted_max_temp": round(predicted_max, 1),
            "predicted_max_temp_low": round(predicted_max - temp_band, 1),
            "predicted_max_temp_high": round(predicted_max + temp_band, 1),
            "predicted_min_temp": round(predicted_min, 1),
            "rain_chance_percent": round(rain_chance, 0),
            "rain_chance_percent_low": round(max(0.0, rain_chance - rain_band), 0),
            "rain_chance_percent_high": round(min(100.0, rain_chance + rain_band), 0),
        })

    return series


def _climate_recommendation(predicted_max: float, rain_chance: float) -> str:
    if rain_chance >= 60:
        return "High chance of rain — pack rain gear and keep indoor options in mind."
    if predicted_max >= 38:
        return "Very hot — start early, stay hydrated, and avoid the midday sun."
    if rain_chance < 20 and predicted_max < 34:
        return "Good weather for sightseeing and outdoor plans."
    return "Fairly mild conditions — a light jacket for the evening should be enough."


def predict_climate(district: str, target_date: date) -> Dict[str, object]:
    """Predicted max/min temperature and rain chance for a district on a future
    date, using the trained LSTM (not a historical lookup)."""
    _, statewide = _climate_statewide_series()
    last_known_date = statewide.index[-1]
    series = _climate_forecast_series(district, target_date)
    day = series[-1]
    return {
        "predicted_max_temp": day["predicted_max_temp"],
        "predicted_min_temp": day["predicted_min_temp"],
        "rain_chance_percent": day["rain_chance_percent"],
        "forecast_date": day["date"],
        "last_known_date": last_known_date.date().isoformat(),
        "days_ahead": day["days_ahead"],
        "recommendation": _climate_recommendation(day["predicted_max_temp"], day["rain_chance_percent"]),
    }


def predict_climate_forecast(district: str, start_date: date, end_date: date) -> Dict[str, object]:
    """Daily forecast for every date from start_date to end_date (inclusive)
    — the multi-day series a chart needs, instead of just one day. Reuses a
    single LSTM walk out to end_date, so it costs no more than a single
    predict_climate() call for the furthest date. Also includes the recent
    actual history leading up to the forecast, for a chart that shows both."""
    if end_date < start_date:
        raise ValueError("end_date must be on or after start_date.")
    full_series = _climate_forecast_series(district, end_date)
    start_ts = pd.Timestamp(start_date).normalize()
    days = [d for d in full_series if pd.Timestamp(d["date"]) >= start_ts]
    for d in days:
        d["recommendation"] = _climate_recommendation(d["predicted_max_temp"], d["rain_chance_percent"])
    history = get_recent_climate_history(district)
    return {"district": district, "days": days, "history": history}


# ---------------------------------------------------------------------------
# Amenities
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _amenities_by_spot() -> Dict[str, List[str]]:
    """spot name -> list of "amenity_name (amenity_type)" strings, read from
    the database's `amenities` table (spot_name, district, amenity_name,
    amenity_type, lat, lon)."""
    with get_db_connection() as conn:
        amenities_df = pd.read_sql_query(
            "SELECT spot_name, amenity_name, amenity_type FROM amenities", conn
        )
    mapping: Dict[str, List[str]] = {}
    for spot_name, amenity_name, amenity_type in amenities_df.itertuples(index=False):
        label = f"{amenity_name} ({amenity_type})" if amenity_type else str(amenity_name)
        mapping.setdefault(str(spot_name), []).append(label)
    return mapping


def get_amenities(spot_name: str) -> List[str]:
    """Amenities near a spot, from the database's `amenities` table. Returns
    an empty list if the spot has none — the frontend shows a friendly "not
    available" message in that case."""
    return _amenities_by_spot().get(spot_name, [])


# ---------------------------------------------------------------------------
# Spot popularity (destination card)
# ---------------------------------------------------------------------------

# Popularity in other_spots is a raw score (observed range ~128-999 across
# the 271 spots, mean ~537). Bucketed into three plain-language tiers rather
# than shown as a bare number — the thresholds sit close to the 33rd/66th
# percentiles of the observed distribution.
POPULARITY_EMERGING_MAX = 400
POPULARITY_POPULAR_MAX = 650


def popularity_label(popularity: float) -> str:
    if popularity < POPULARITY_EMERGING_MAX:
        return "Emerging"
    if popularity < POPULARITY_POPULAR_MAX:
        return "Popular"
    return "Very Popular"


@lru_cache(maxsize=1)
def _other_spots_info() -> Dict[str, Dict[str, object]]:
    """spot name -> {category, popularity, entry_fee}, read from the
    database's `other_spots` table."""
    with get_db_connection() as conn:
        df = pd.read_sql_query(
            "SELECT name, category, popularity, entry_fee FROM other_spots", conn
        )
    df = df.drop_duplicates(subset=["name"])
    info: Dict[str, Dict[str, object]] = {}
    for row in df.itertuples(index=False):
        info[str(row.name)] = {
            "category": None if pd.isna(row.category) else str(row.category),
            "popularity": None if pd.isna(row.popularity) else int(row.popularity),
            "entry_fee": None if pd.isna(row.entry_fee) else float(row.entry_fee),
        }
    return info


def get_spot_rating_popularity(spot_name: str) -> Dict[str, object]:
    """Popularity score + tier, category, and entry fee for a spot, from the
    `other_spots` table. `available=False` if the spot has no row there
    (e.g. it only appears in spot_visitors/climate_dataset)."""
    info = _other_spots_info().get(spot_name)
    if info is None:
        return {
            "spot_name": spot_name, "available": False,
            "popularity": None, "popularity_label": None, "category": None, "entry_fee": None,
        }
    popularity = info["popularity"]
    return {
        "spot_name": spot_name,
        "available": True,
        "popularity": popularity,
        "popularity_label": popularity_label(popularity) if popularity is not None else None,
        "category": info["category"],
        "entry_fee": info["entry_fee"],
    }


# ---------------------------------------------------------------------------
# Upcoming festivals at a destination
#
# Festival dates vary year to year (many follow the lunar calendar).  The
# application therefore keeps an actual date calendar for years for which it
# has been verified, with the old month mapping only as a clearly-labelled
# fallback for a year that has not yet been added.
# ---------------------------------------------------------------------------

FESTIVAL_TYPICAL_MONTH = {
    "Bhogi, Sankranti": "January",
    "Maha Shivaratri": "February",
    "Holi": "March",
    "Ugadi, Sri Rama Navami": "April",
    "Buddha Purnima": "May",
    "Bonalu": "July",
    "Independence Day, Krishna Janmashtami": "August",
    "Vinayaka Chavithi": "September",
    "Bathukamma, Dussehra": "October",
    "Diwali": "November",
    "Christmas": "December",
}

# Telangana Government's 2026 calendar.  A category can contain more than one
# festival because that is how the crowd model was trained; use the first
# upcoming date in that category when presenting a jump target.
FESTIVAL_DATES = {
    2026: {
        "Bhogi, Sankranti": (date(2026, 1, 13), date(2026, 1, 14)),
        "Maha Shivaratri": (date(2026, 2, 15),),
        "Holi": (date(2026, 3, 3),),
        "Ugadi, Sri Rama Navami": (date(2026, 3, 19), date(2026, 3, 27)),
        "Buddha Purnima": (date(2026, 5, 1),),
        "Bonalu": (date(2026, 8, 10),),
        "Independence Day, Krishna Janmashtami": (date(2026, 8, 15), date(2026, 9, 4)),
        "Vinayaka Chavithi": (date(2026, 9, 14),),
        "Bathukamma, Dussehra": (date(2026, 10, 11), date(2026, 10, 20)),
        "Diwali": (date(2026, 11, 8),),
        "Christmas": (date(2026, 12, 25),),
    },
}

MONTH_NUMBER = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12,
}

# How far ahead of the travel date to look for a festival worth flagging.
FESTIVAL_LOOKAHEAD_DAYS = 150


def get_upcoming_festivals(
    spot_name: str, district: str, category: str, target_date: date,
    lookahead_days: int = FESTIVAL_LOOKAHEAD_DAYS,
) -> List[Dict[str, object]]:
    """Return a jump target for each upcoming crowd-model festival category.

    Verified calendar dates are preferred.  If the selected year is not in
    the calendar, retain the month-level estimate so the feature remains
    useful instead of inventing a precise date.
    """
    results: List[Dict[str, object]] = []

    for festival, month_name in FESTIVAL_TYPICAL_MONTH.items():
        known_dates = FESTIVAL_DATES.get(target_date.year, {}).get(festival, ())
        future_known_dates = [d for d in known_dates if d >= target_date]
        if future_known_dates:
            candidate = min(future_known_dates)
            days_until = (candidate - target_date).days
            date_is_estimate = False
        else:
            # If a verified date has already passed, fall through to the next
            # year's month estimate until that year's official calendar is
            # recorded.
            date_is_estimate = True
            month_num = MONTH_NUMBER[month_name]
            candidate_year = target_date.year if month_num >= target_date.month else target_date.year + 1
            candidate = date(candidate_year, month_num, 1)
            is_current_month = (candidate.year, candidate.month) == (target_date.year, target_date.month)
            if is_current_month:
                candidate = target_date
                days_until = 0
            else:
                days_until = (candidate - target_date).days
        if days_until > lookahead_days:
            continue

        results.append({
            "festival": festival,
            "month": month_name,
            "forecast_date": candidate.isoformat(),
            "days_until": days_until,
            "date_is_estimate": date_is_estimate,
        })

    results.sort(key=lambda r: r["days_until"])
    return results


def get_next_festival_date(festival: str, from_date: date) -> Dict[str, object]:
    """Next occurrence of a single named festival on/after from_date.

    Shares the "verified calendar first, month-estimate fallback" logic
    used by get_upcoming_festivals, but for one festival with no lookahead
    cap — used to jump the trip date picker straight to that festival.
    """
    month_name = FESTIVAL_TYPICAL_MONTH.get(festival)
    if month_name is None:
        raise KeyError(f"Unknown festival: {festival!r}")

    known_dates = FESTIVAL_DATES.get(from_date.year, {}).get(festival, ())
    future_known_dates = [d for d in known_dates if d >= from_date]
    if future_known_dates:
        return {"festival": festival, "date": min(future_known_dates), "date_is_estimate": False}

    month_num = MONTH_NUMBER[month_name]
    candidate_year = from_date.year if month_num >= from_date.month else from_date.year + 1
    candidate = date(candidate_year, month_num, 1)
    if (candidate.year, candidate.month) == (from_date.year, from_date.month):
        candidate = from_date
    return {"festival": festival, "date": candidate, "date_is_estimate": True}


# ---------------------------------------------------------------------------
# Combined "good time to visit" badge — merges crowd level + climate outlook
# into a single call instead of making the person weigh two separate panels.
# ---------------------------------------------------------------------------

CROWD_LEVEL_HEAVY = {"Busy", "Very Crowded"}
CROWD_LEVEL_LIGHT = {"Quiet", "Moderate"}


def combined_visit_rating(crowd_level: str, rain_chance_percent: float, predicted_max_temp: float) -> Dict[str, object]:
    crowd_heavy = crowd_level in CROWD_LEVEL_HEAVY
    weather_poor = rain_chance_percent >= 60 or predicted_max_temp >= 38
    weather_great = rain_chance_percent < 20 and predicted_max_temp < 34
    crowd_light = crowd_level in CROWD_LEVEL_LIGHT

    reasons: List[str] = []
    if crowd_level == "Very Crowded":
        reasons.append("Very large crowds expected")
    elif crowd_level == "Busy":
        reasons.append("Busy crowds expected")
    elif crowd_level == "Quiet":
        reasons.append("Crowds should be light")
    else:
        reasons.append("Crowds should be moderate")

    if rain_chance_percent >= 60:
        reasons.append("High chance of rain")
    elif predicted_max_temp >= 38:
        reasons.append("Very hot conditions expected")
    elif weather_great:
        reasons.append("Pleasant weather expected")
    else:
        reasons.append("Fairly mild weather expected")

    if crowd_heavy and weather_poor:
        badge, level = "Not Ideal", "poor"
    elif crowd_heavy or weather_poor:
        badge, level = "Fair — Some Trade-offs", "fair"
    elif crowd_light and weather_great:
        badge, level = "Great Time to Visit", "great"
    else:
        badge, level = "Good Time to Visit", "good"

    return {"badge": badge, "level": level, "reasons": reasons}


# ---------------------------------------------------------------------------
# Packing tips, auto-generated from the climate forecast
# ---------------------------------------------------------------------------

def generate_packing_tips(max_rain_chance_percent: float, max_temp: float, min_temp: float) -> List[str]:
    """Packing suggestions from the worst-case rain chance and the
    hottest/coldest points of the trip's forecast window."""
    tips: List[str] = []

    if max_rain_chance_percent >= 50:
        tips.append("☔ Umbrella or raincoat — high chance of rain during the trip")
    elif max_rain_chance_percent >= 25:
        tips.append("☔ Pack a compact umbrella just in case")

    if max_temp >= 36:
        tips.append("🧴 Sunscreen, sunglasses, and a hat — very hot conditions expected")
        tips.append("💧 Carry extra water and stay hydrated")
    elif max_temp >= 30:
        tips.append("🧴 Light sun protection (sunscreen, cap) recommended")

    if min_temp <= 15:
        tips.append("🧥 A warm jacket for chilly mornings and evenings")
    elif min_temp <= 20:
        tips.append("🧥 A light jacket or sweater for cooler evenings")

    if max_temp >= 30 and max_rain_chance_percent < 30:
        tips.append("👕 Light, breathable clothing")

    if max_rain_chance_percent >= 50:
        tips.append("👟 Waterproof or quick-dry footwear")

    if not tips:
        tips.append("🙂 Mild conditions expected — no special packing needed beyond the essentials")

    return tips


def generate_trip_packing_tips(forecast_days: List[Dict[str, object]]) -> List[str]:
    """Packing tips from a whole trip's forecast (predict_climate_forecast's
    `days` list) rather than just a single day — uses the hottest day, the
    coldest night, and the rainiest day across the whole window."""
    if not forecast_days:
        return []
    max_rain = max(d["rain_chance_percent"] for d in forecast_days)
    max_temp = max(d["predicted_max_temp"] for d in forecast_days)
    min_temp = min(d["predicted_min_temp"] for d in forecast_days)
    return generate_packing_tips(max_rain, max_temp, min_temp)


# ---------------------------------------------------------------------------
# Suggested visiting order for multi-spot trips — shortest route, not the
# order spots happened to be clicked in.
# ---------------------------------------------------------------------------

# Brute-forcing every ordering is exact but O((n-1)!), so it's only used up
# to this many spots; beyond that a nearest-neighbor heuristic is used
# instead (fast, usually close to optimal, not guaranteed exact).
EXACT_ROUTE_MAX_SPOTS = 7


def _nearest_neighbor_order(spot_names: List[str]) -> List[str]:
    route = [spot_names[0]]
    remaining = list(spot_names[1:])
    while remaining:
        last = route[-1]
        best_spot, best_km = None, float("inf")
        for candidate in remaining:
            leg = compute_distance_km(last, candidate)
            km = leg["distance_km"] if leg["distance_km"] is not None else float("inf")
            if km < best_km:
                best_km, best_spot = km, candidate
        route.append(best_spot)
        remaining.remove(best_spot)
    return route


def suggest_visit_order(spot_names: List[str]) -> Dict[str, object]:
    """Reorders spots (keeping the first as the trip's starting point) to
    minimize total travel distance. Returns both the suggested order and the
    original click order so the frontend can show the difference."""
    import itertools

    original_chain = compute_chain_distances(spot_names)

    if len(spot_names) <= 2:
        best_order = list(spot_names)
    elif len(spot_names) <= EXACT_ROUTE_MAX_SPOTS:
        best_order = list(spot_names)
        best_km = original_chain["total_km"] if original_chain["all_available"] else float("inf")
        for perm in itertools.permutations(spot_names[1:]):
            candidate = [spot_names[0]] + list(perm)
            chain = compute_chain_distances(candidate)
            if not chain["all_available"]:
                continue
            if chain["total_km"] < best_km:
                best_km, best_order = chain["total_km"], candidate
    else:
        best_order = _nearest_neighbor_order(spot_names)

    best_chain = compute_chain_distances(best_order)
    savings_km = None
    if original_chain["all_available"] and best_chain["all_available"]:
        savings_km = round(original_chain["total_km"] - best_chain["total_km"], 1)

    return {
        "order": best_order,
        "total_km": best_chain["total_km"],
        "all_available": best_chain["all_available"],
        "original_order": list(spot_names),
        "original_total_km": original_chain["total_km"],
        "original_all_available": original_chain["all_available"],
        "improved": bool(savings_km and savings_km > 0.05),
        "savings_km": savings_km,
    }