from __future__ import annotations

from datetime import date
from typing import List, Optional

from pydantic import BaseModel


class CostRequest(BaseModel):
    duration_days: int
    num_travelers: int
    route_distance_km: float
    transport_mode: str
    accommodation_tier: str
    season: str
    user_budget: Optional[float] = None


class CostResponse(BaseModel):
    travel_cost_est: float
    stay_cost_est: float
    food_cost_est: float
    entry_fees_est: float
    tolls_and_parking_est: float
    total_estimated_cost: float


class CrowdRequest(BaseModel):
    spot_name: str
    district: str
    category: str
    year: int
    month: str
    season: str
    festival: str = "None"


class CrowdResponse(BaseModel):
    predicted_visitors: float
    crowd_level: str


class ClimateRequest(BaseModel):
    district: str
    target_date: date


class ClimateResponse(BaseModel):
    predicted_max_temp: float
    predicted_min_temp: float
    rain_chance_percent: float
    forecast_date: str
    last_known_date: str
    days_ahead: int
    recommendation: str


class ClimateForecastRequest(BaseModel):
    district: str
    start_date: date
    end_date: date


class ClimateForecastDay(BaseModel):
    date: str
    days_ahead: int
    predicted_max_temp: float
    predicted_max_temp_low: float
    predicted_max_temp_high: float
    predicted_min_temp: float
    rain_chance_percent: float
    rain_chance_percent_low: float
    rain_chance_percent_high: float
    recommendation: str


class ClimateHistoryDay(BaseModel):
    date: str
    actual_max_temp: float
    actual_min_temp: float
    actual_rain_chance_percent: float


class ClimateForecastResponse(BaseModel):
    district: str
    days: List[ClimateForecastDay]
    history: List[ClimateHistoryDay]


class AmenitiesResponse(BaseModel):
    spot_name: str
    amenities: List[str]
    available: bool


class SpotDistanceResponse(BaseModel):
    spot_a: str
    spot_b: str
    distance_km: Optional[float]
    available: bool
    method: str  # "haversine" | "same_district_assumed" | "same_spot" | "unavailable"


class SpotCoordinateResponse(BaseModel):
    spot_name: str
    available: bool
    lat: Optional[float] = None
    lon: Optional[float] = None


class SpotCoordinatesRequest(BaseModel):
    spots: List[str]


class SpotCoordinatesResponse(BaseModel):
    coordinates: List[SpotCoordinateResponse]


class ChainDistanceRequest(BaseModel):
    spots: List[str]


class DistanceLeg(BaseModel):
    from_spot: str
    to_spot: str
    distance_km: Optional[float]
    available: bool
    method: str


class ChainDistanceResponse(BaseModel):
    legs: List[DistanceLeg]
    total_km: float
    all_available: bool


class SpotInfoResponse(BaseModel):
    spot_name: str
    available: bool
    popularity: Optional[int] = None
    popularity_label: Optional[str] = None
    category: Optional[str] = None
    entry_fee: Optional[float] = None


class VisitOrderRequest(BaseModel):
    spots: List[str]


class VisitOrderResponse(BaseModel):
    order: List[str]
    total_km: float
    all_available: bool
    original_order: List[str]
    original_total_km: float
    original_all_available: bool
    improved: bool
    savings_km: Optional[float] = None


class UpcomingFestival(BaseModel):
    festival: str
    month: str
    forecast_date: str
    days_until: int
    date_is_estimate: bool = False


class VisitRating(BaseModel):
    badge: str
    level: str
    reasons: List[str]


class TripPredictRequest(BaseModel):
    """One combined request the frontend uses for the 'Generate Predictions' button."""
    district: str
    spot_name: str
    category: str
    target_date: date
    end_date: Optional[date] = None  # trip end date, for the climate forecast chart; defaults to target_date only
    duration_days: int
    num_travelers: int
    route_distance_km: float
    transport_mode: str
    accommodation_tier: str
    season: str
    festival: str = "None"
    user_budget: Optional[float] = None