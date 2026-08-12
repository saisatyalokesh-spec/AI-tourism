"""
main.py — FastAPI app. Run from the backend/ folder:

    uvicorn main:app --reload

Endpoints:
    GET  /districts                     list of districts
    GET  /spots?district=...&category=...   spots in a district, optionally filtered by category (or all spots if district omitted)
    GET  /options                          dropdown choices for the cost/crowd forms
    GET  /transport-suggestions?num_travelers=N   suggested transport modes for group size
    GET  /amenities/{spot_name}             amenities for a spot (if available)
    GET  /spot-info/{spot_name}               popularity tier, category, entry fee for a spot
    GET  /festival-date/{festival}              next occurrence date of a named festival
    GET  /spot-coordinates/{spot_name}          lat/lon for one spot (for the Navigator Map tab)
    POST /spot-coordinates                       lat/lon for several spots in one call
    POST /distance/optimize                     suggested visiting order for a multi-spot trip (shortest route)
    POST /predict/cost                       cost estimate
    POST /predict/crowd                       crowd/footfall estimate
    POST /predict/climate                      climate forecast (max/min temp, rain chance) for a single date
    POST /predict/climate-forecast                  day-by-day climate forecast for a date range (for a chart)
    POST /predict/trip                            all three predictions together, logged to the DB/text log

Every call to /spot-info/{spot_name} and /predict/trip also logs a row to
Supabase's user_interactions table (spot_name, action_type, timestamp) via
predict.log_interaction() — a no-op if SUPABASE_DB_URL isn't set.
"""

from __future__ import annotations

import sys
from pathlib import Path

# uvicorn's --reload runs the actual server in a separate subprocess. On
# Windows, that subprocess is a fresh interpreter (multiprocessing's
# "spawn" method) that does NOT inherit this process's sys.path — so
# without this, the imports below can fail with "ModuleNotFoundError" even
# though the exact same command works fine without --reload.
#
# Two directories need to be on the path, not just one: `predict` and
# `schemas` are siblings of this file (App/backend/), but `database` lives
# at the project root, two levels up — confirmed against this repo's git
# history, `database/` has never been nested inside App/backend/.
_BACKEND_DIR = Path(__file__).resolve().parent          # .../App/backend
_PROJECT_ROOT = _BACKEND_DIR.parent.parent               # .../Tourism Project
sys.path.insert(0, str(_BACKEND_DIR))
sys.path.insert(0, str(_PROJECT_ROOT))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import predict
from database.database import log_prediction
from schemas import (
    AmenitiesResponse, ChainDistanceRequest, ChainDistanceResponse, ClimateForecastRequest,
    ClimateForecastResponse, ClimateRequest, ClimateResponse, CostRequest, CostResponse, CrowdRequest,
    CrowdResponse, SpotCoordinateResponse, SpotCoordinatesRequest, SpotCoordinatesResponse, SpotDistanceResponse,
    SpotInfoResponse, TripPredictRequest, VisitOrderRequest, VisitOrderResponse,
)

app = FastAPI(title="Smart Tourism API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/districts")
def districts():
    return predict.get_districts()


@app.get("/spots")
def spots(district: str | None = None, category: str | None = None):
    if district:
        return predict.get_spots_by_district(district, category)
    return predict.get_all_spots()


@app.get("/options")
def options():
    return predict.get_cost_input_options()


@app.get("/transport-suggestions")
def transport_suggestions(num_travelers: int):
    return predict.suggest_transport_modes(num_travelers)


@app.get("/amenities/{spot_name}", response_model=AmenitiesResponse)
def amenities(spot_name: str):
    items = predict.get_amenities(spot_name)
    return AmenitiesResponse(spot_name=spot_name, amenities=items, available=len(items) > 0)


@app.get("/spot-info/{spot_name}", response_model=SpotInfoResponse)
def spot_info(spot_name: str):
    predict.log_interaction(spot_name, "view_spot_info")
    return predict.get_spot_rating_popularity(spot_name)


@app.get("/festival-date/{festival}")
def festival_date(festival: str, from_date: str | None = None):
    """Next occurrence of `festival` on/after `from_date` (defaults to today) —
    used to jump the trip date picker to that festival when it's selected."""
    from datetime import date as _date

    ref_date = _date.fromisoformat(from_date) if from_date else _date.today()
    try:
        result = predict.get_next_festival_date(festival, ref_date)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown festival: {festival}")
    return {
        "festival": result["festival"],
        "date": result["date"].isoformat(),
        "date_is_estimate": result["date_is_estimate"],
    }


@app.get("/distance", response_model=SpotDistanceResponse)
def spot_distance(spot_a: str, spot_b: str):
    result = predict.compute_distance_km(spot_a, spot_b)
    return SpotDistanceResponse(
        spot_a=spot_a, spot_b=spot_b,
        distance_km=result["distance_km"], available=result["distance_km"] is not None, method=result["method"],
    )


@app.get("/spot-coordinates/{spot_name}", response_model=SpotCoordinateResponse)
def spot_coordinate(spot_name: str):
    coord = predict.get_spot_coordinate(spot_name)
    if coord is None:
        return SpotCoordinateResponse(spot_name=spot_name, available=False)
    return SpotCoordinateResponse(spot_name=spot_name, available=True, lat=coord[0], lon=coord[1])


@app.post("/spot-coordinates", response_model=SpotCoordinatesResponse)
def spot_coordinates_batch(req: SpotCoordinatesRequest):
    """Coordinates for several spots in one call — used by the Navigator Map
    tab to place a marker for every selected spot without one request per
    spot."""
    results = []
    for spot_name in req.spots:
        coord = predict.get_spot_coordinate(spot_name)
        if coord is None:
            results.append(SpotCoordinateResponse(spot_name=spot_name, available=False))
        else:
            results.append(SpotCoordinateResponse(spot_name=spot_name, available=True, lat=coord[0], lon=coord[1]))
    return SpotCoordinatesResponse(coordinates=results)


@app.post("/distance/chain", response_model=ChainDistanceResponse)
def spot_distance_chain(req: ChainDistanceRequest):
    if len(req.spots) < 2:
        raise HTTPException(status_code=400, detail="Provide at least two spots to compute distances between them.")
    return predict.compute_chain_distances(req.spots)


@app.post("/distance/optimize", response_model=VisitOrderResponse)
def spot_visit_order(req: VisitOrderRequest):
    if len(req.spots) < 2:
        raise HTTPException(status_code=400, detail="Provide at least two spots to suggest a visiting order.")
    return predict.suggest_visit_order(req.spots)


@app.post("/predict/cost", response_model=CostResponse)
def predict_cost(req: CostRequest):
    try:
        result = predict.predict_budget_cost(req.model_dump())
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/predict/crowd", response_model=CrowdResponse)
def predict_crowd(req: CrowdRequest):
    try:
        data = req.model_dump()
        visitors = predict.predict_crowd_count(data)
        # The request schema sends year/month rather than the full date. The
        # frontend derives Festival from the real travel date, so the selected
        # festival itself is the authoritative signal for this endpoint.
        festival_active = str(data.get("festival", "None")) != "None"
        return CrowdResponse(predicted_visitors=visitors, crowd_level=predict.crowd_level_label(visitors, festival_active))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/predict/climate", response_model=ClimateResponse)
def predict_climate_route(req: ClimateRequest):
    try:
        result = predict.predict_climate(req.district, req.target_date)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/predict/climate-forecast", response_model=ClimateForecastResponse)
def predict_climate_forecast_route(req: ClimateForecastRequest):
    try:
        result = predict.predict_climate_forecast(req.district, req.start_date, req.end_date)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/predict/trip")
def predict_trip(req: TripPredictRequest):
    """Runs cost + crowd + climate together for the 'Generate Predictions'
    button, and logs the whole thing (inputs + all three results)."""
    cost = predict.predict_budget_cost({
        "duration_days": req.duration_days, "num_travelers": req.num_travelers,
        "route_distance_km": req.route_distance_km, "transport_mode": req.transport_mode,
        "accommodation_tier": req.accommodation_tier, "season": req.season,
    })

    crowd_input = {
        "spot_name": req.spot_name, "district": req.district, "category": req.category,
        "year": req.target_date.year, "month": req.target_date.strftime("%B"),
        "season": req.season, "festival": req.festival,
    }
    crowd_visitors = predict.predict_crowd_count(crowd_input)
    festival_active = predict._festival_is_active(req.festival, req.target_date)
    crowd = {
        "predicted_visitors": crowd_visitors,
        "crowd_level": predict.crowd_level_label(crowd_visitors, festival_active),
    }

    climate_error = None
    climate = None
    climate_forecast_error = None
    climate_forecast = None
    try:
        climate = predict.predict_climate(req.district, req.target_date)
    except Exception as e:
        climate_error = str(e)
    try:
        climate_forecast = predict.predict_climate_forecast(
            req.district, req.target_date, req.end_date or req.target_date
        )
    except Exception as e:
        climate_forecast_error = str(e)

    # Combined "good time to visit" badge — needs both crowd and climate, so
    # only computed when climate succeeded.
    visit_rating = None
    if climate is not None:
        visit_rating = predict.combined_visit_rating(
            crowd["crowd_level"], climate["rain_chance_percent"], climate["predicted_max_temp"]
        )

    # Packing tips from the whole trip window's forecast (falls back to the
    # single-day climate result if the multi-day forecast wasn't available).
    packing_tips = []
    if climate_forecast and climate_forecast.get("days"):
        packing_tips = predict.generate_trip_packing_tips(climate_forecast["days"])
    elif climate is not None:
        packing_tips = predict.generate_packing_tips(
            climate["rain_chance_percent"], climate["predicted_max_temp"], climate["predicted_min_temp"]
        )

    spot_info = predict.get_spot_rating_popularity(req.spot_name)
    upcoming_festivals = predict.get_upcoming_festivals(
        req.spot_name, req.district, req.category, req.target_date
    )

    result = {
        "cost": cost, "crowd": crowd,
        "climate": climate, "climate_error": climate_error,
        "climate_forecast": climate_forecast, "climate_forecast_error": climate_forecast_error,
        "spot_info": spot_info,
        "visit_rating": visit_rating,
        "packing_tips": packing_tips,
        "upcoming_festivals": upcoming_festivals,
    }
    log_prediction("trip", req.district, req.spot_name, req.model_dump(), result)
    predict.log_interaction(req.spot_name, "predict_trip")
    return result