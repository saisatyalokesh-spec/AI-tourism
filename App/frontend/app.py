"""
app.py — Streamlit frontend. Run from the frontend/ folder, with the backend
already running (see backend/main.py):

    streamlit run app.py

Talks to the FastAPI backend over HTTP at BACKEND_URL below.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import folium
import plotly.graph_objects as go
import requests
import streamlit as st
from streamlit_folium import st_folium

BACKEND_URL = "BACKEND_URL = "BACKEND_URL = "https://ai-tourism-ehym.onrender.com/docs"
# Nominatim (OpenStreetMap's free geocoder) and OSRM's public demo routing
# server — both free, no API key required. Nominatim's usage policy requires
# a real identifying User-Agent on every request (unlabeled traffic gets
# blocked), and asks for no more than ~1 request/second, which a single
# person clicking through a trip planner comfortably stays under.
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_HEADERS = {"User-Agent": "SmartTourismTelangana/1.0 (student capstone project)"}
OSRM_ROUTE_URL = "https://router.project-osrm.org/route/v1/driving"

st.set_page_config(page_title="Telangana_Tourism_Trails", page_icon="🗺️", layout="wide")

# ---------------------------------------------------------------------------
# Styling — a warm, heritage-inspired look instead of the earlier dark
# analytics-dashboard theme: parchment/sandstone background, a deep
# terracotta primary accent and turmeric-gold secondary accent (drawn from
# Charminar's stone and Telangana's festival colors), serif display
# headings paired with clean sans-serif body text, pill-shaped chips and
# buttons, and cards marked by a colored top edge instead of a full border.
# The sidebar stays dark for contrast, but everything else flips to light.
# ---------------------------------------------------------------------------
ACCENT = "#8B5FD1"        # primary — bright royal purple (lifted for dark-bg contrast)
ACCENT_SOFT = "#D4AF37"   # secondary — champagne gold (royal + gold = premium pairing)
GRADIENT_END = "#E0459B"  # pink/magenta endpoint used only for hero gradient text/buttons on Plan Your Trip
HEAT = "#E0604C"          # warm/hot indicator, brightened for dark background
GOOD = "#4CAF6D"
WARN = "#E0B23D"
BAD = "#E05C5C"
BG = "#160B22"            # near-black aubergine page background
PANEL = "#231433"         # card surface — dark purple-slate, lighter than the page
BORDER = "#3D2A52"        # muted violet border, visible against dark panels
TEXT_MUTED = "#B3A3C4"    # muted lavender-gray for secondary text
TEXT_MAIN = "#F0E9FA"     # near-white lavender — primary text
SIDEBAR_BG = "#0F0718"    # near-black sidebar, darker than the main panels for depth
SIDEBAR_TEXT = "#F0E9FA"

st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=Work+Sans:wght@400;500;600;700&display=swap');

    html, body, [data-testid="stAppViewContainer"] {{
        background: {BG};
        color: {TEXT_MAIN};
        font-family: "Work Sans", "Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif;
    }}
    .bg-gradient {{
        position: fixed; inset: 0; z-index: -1; pointer-events: none;
        background-image:
            radial-gradient(1000px 500px at 10% -10%, {ACCENT_SOFT}22 0%, transparent 60%),
            radial-gradient(800px 420px at 105% 5%, {ACCENT}18 0%, transparent 55%);
    }}
    [data-testid="stHeader"] {{ background: rgba(0,0,0,0); }}
    [data-testid="stSidebar"] {{ background: {SIDEBAR_BG}; border-right: 1px solid #2A1740; }}
    [data-testid="stSidebar"] * {{ color: {SIDEBAR_TEXT} !important; }}
    [data-testid="stSidebar"] hr {{ border-color: #4A2E63 !important; }}
    .block-container {{ padding-top: 1.6rem; padding-bottom: 2.5rem; max-width: 1240px; }}

    h1, h2, h3, h4 {{
        font-family: "Playfair Display", Georgia, serif; font-weight: 700; letter-spacing: 0;
        color: {TEXT_MAIN};
    }}
    p, span, div, label {{ letter-spacing: 0; }}

    .hero-stat::before {{ content: ""; position: absolute; top: 0; left: 0; right: 0; height: 4px;
                           background: linear-gradient(90deg, {ACCENT}, {ACCENT_SOFT}); }}
    .hero-stat .icon {{ font-size: 1.6rem; margin-bottom: 0.3rem; }}
    .hero-stat .label {{ font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.09em;
                          color: {TEXT_MUTED}; margin-bottom: 0.4rem; font-weight: 600; }}
    .hero-stat .value {{ font-family: "Playfair Display", Georgia, serif; font-size: 2.2rem;
                          font-weight: 700; line-height: 1; color: {TEXT_MAIN}; }}
    .hero-stat .sub {{ font-size: 0.78rem; color: {TEXT_MUTED}; margin-top: 0.45rem; }}

    .cost-row {{ display:flex; justify-content:space-between; align-items:flex-start;
                 padding:0.7rem 0.2rem; border-bottom:1px dashed {BORDER}; }}
    .cost-row .name {{ font-weight:600; color: {TEXT_MAIN}; }}
    .cost-row .desc {{ font-size:0.8rem; color:{TEXT_MUTED}; margin-top:0.15rem; max-width:400px; }}
    .cost-row .amount {{ white-space:nowrap; padding-left:1rem; font-variant-numeric: tabular-nums;
                          font-weight: 700; color: {TEXT_MAIN}; }}

    .chip {{ display:inline-block; padding:0.32rem 0.85rem; border-radius:999px; font-size:0.78rem;
             margin:0.15rem 0.3rem 0.15rem 0; border:1px solid {BORDER}; background:{BG}; color: {TEXT_MAIN}; }}
    .chip-suggested {{ background:{ACCENT}; border-color:{ACCENT}; color:#FFF8EE; font-weight: 650; }}

    .stTabs [data-baseweb="tab-list"] {{ gap: 6px; border-bottom: 2px solid {BORDER}; }}
    .stTabs [data-baseweb="tab"] {{ background: transparent; border-radius: 999px 999px 0 0;
                                     padding: 0.6rem 1.2rem; color: {TEXT_MUTED}; font-weight: 600; }}
    .stTabs [aria-selected="true"] {{ color: {ACCENT} !important; background: {PANEL} !important;
                                        border-bottom: 2px solid {ACCENT}; }}

    .stButton>button {{
        background: {ACCENT}; color: #FFF8EE; border: none; border-radius: 999px; font-weight: 650;
        padding: 0.55rem 1.3rem; transition: filter 0.15s ease, transform 0.1s ease;
    }}
    .stButton>button:hover {{ filter: brightness(1.1); transform: translateY(-1px); }}

    /* Interactive sidebar navigation */
    .sidebar-nav-title {{
        font-family: "Playfair Display", Georgia, serif;
        font-weight: 700;
        font-size: 1.12rem;
        color: {SIDEBAR_TEXT};
        margin-bottom: 0.35rem;
    }}
    .sidebar-nav-subtitle {{
        color: {TEXT_MUTED};
        font-size: 0.78rem;
        margin-bottom: 0.8rem;
    }}
    [data-testid="stSidebar"] .stButton {{
        margin: 0.28rem 0;
    }}
    [data-testid="stSidebar"] .stButton > button {{
        width: 100%;
        min-height: 3.15rem;
        border-radius: 14px !important;
        padding: 0.72rem 0.9rem !important;
        text-align: left !important;
        font-weight: 800 !important;
        font-size: 0.94rem !important;
        letter-spacing: 0.01em;
        transition: all 0.18s ease;
        box-shadow: 0 3px 12px rgba(0,0,0,0.18);
    }}
    [data-testid="stSidebar"] .stButton > button[kind="secondary"] {{
        background: {PANEL} !important;
        color: {SIDEBAR_TEXT} !important;
        border: 1.5px solid #4A2E63 !important;
    }}
    [data-testid="stSidebar"] .stButton > button[kind="secondary"]:hover {{
        background: #32194A !important;
        color: #FFFFFF !important;
        border-color: {ACCENT_SOFT} !important;
        transform: translateX(3px);
        box-shadow: 0 5px 16px {ACCENT}33;
    }}
    [data-testid="stSidebar"] .stButton > button[kind="primary"] {{
        background: linear-gradient(135deg, {ACCENT_SOFT}, #C89B2C) !important;
        color: #0F0718 !important;
        border: 2px solid {ACCENT_SOFT} !important;
        font-weight: 900 !important;
        box-shadow: 0 6px 18px {ACCENT_SOFT}35;
    }}
    [data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {{
        filter: brightness(1.08);
        transform: translateX(3px);
    }}

    [data-testid="stMetricValue"] {{ color: {TEXT_MAIN}; }}
    hr {{ border-color: {BORDER} !important; }}

    /* -----------------------------------------------------------------
       Form widgets — previously untouched by theme CSS, so every select,
       date picker, number stepper, and text input kept Streamlit's
       default chrome regardless of which palette was applied above. This
       is the actual reason earlier theme swaps didn't feel different:
       only backgrounds/accents changed, not the inputs people interact
       with most. Restyled here to match the active palette.
       ----------------------------------------------------------------- */
    div[data-baseweb="select"] > div, div[data-baseweb="input"],
    [data-testid="stNumberInput"] input, [data-testid="stDateInput"] input,
    [data-testid="stTextInput"] input {{
        background: {PANEL} !important; border: 1.5px solid {BORDER} !important;
        border-radius: 12px !important; color: {TEXT_MAIN} !important;
        min-height: 3rem !important; font-size: 1rem !important;
    }}
    div[data-baseweb="select"] > div:focus-within, div[data-baseweb="input"]:focus-within {{
        border-color: {ACCENT} !important; box-shadow: 0 0 0 3px {ACCENT}33 !important;
    }}
    [data-testid="stNumberInput"] button {{
        background: {PANEL} !important; border-color: {BORDER} !important; color: {ACCENT} !important;
    }}
    [data-testid="stNumberInput"] button:hover {{ background: {ACCENT}22 !important; }}
    div[data-baseweb="select"] svg, [data-testid="stDateInput"] svg {{ fill: {ACCENT_SOFT} !important; }}
    [data-baseweb="popover"] li, [data-baseweb="menu"] {{
        background: {PANEL} !important; color: {TEXT_MAIN} !important;
    }}
    [data-baseweb="popover"] li:hover {{ background: {ACCENT}22 !important; }}
    /* Multiselect selected-tag pills — default to BaseWeb's stock red/orange,
       which clashes with every custom palette above unless overridden. */
    div[data-baseweb="tag"] {{
        background: {ACCENT} !important; border-radius: 999px !important; border: none !important;
    }}
    div[data-baseweb="tag"] span {{ color: #FFF8EE !important; }}
    .stSelectbox label, .stMultiSelect label, .stNumberInput label,
    .stDateInput label, .stTextInput label {{
        color: {TEXT_MAIN} !important; font-weight: 600; font-size: 0.98rem !important;
        margin-bottom: 0.35rem !important;
    }}
    /* Breathing room between stacked form widgets — the default Streamlit
       spacing reads noticeably tighter than the reference design. */
    [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] {{
        margin-bottom: 0.3rem;
    }}

    /* Section headers (####) — a colored left rule + generous indent
       instead of a plain bold line, so every card heading in the app
       (not just the top banner) carries the accent identity. */
    h4 {{
        border-left: 4px solid {ACCENT}; padding-left: 0.7rem; margin: 0.3rem 0 0.8rem 0 !important;
    }}
    h5, h6 {{
        border-left: 3px solid {ACCENT_SOFT}; padding-left: 0.6rem;
    }}

    /* Cards — glow-edged instead of a flat top bar: a soft radial tint
       plus a colored outer glow shadow, larger radius throughout. */
    .card {{
        background: linear-gradient(160deg, {PANEL} 0%, {PANEL} 70%, {ACCENT}14 100%);
        border: 1px solid {BORDER}; border-radius: 22px; padding: 1.7rem 1.9rem;
        box-shadow: 0 8px 28px {ACCENT}1F, 0 2px 6px rgba(0,0,0,0.25);
    }}
    [data-testid="stVerticalBlockBorderWrapper"] > div > [data-testid="stVerticalBlock"] {{
        background: linear-gradient(160deg, {PANEL} 0%, {PANEL} 70%, {ACCENT_SOFT}14 100%);
        border: 1px solid {BORDER}; border-radius: 22px; padding: 1.6rem 1.8rem;
        box-shadow: 0 8px 28px {ACCENT}1F, 0 2px 6px rgba(0,0,0,0.25);
    }}
    .hero-stat {{
        background: linear-gradient(160deg, {PANEL} 0%, {PANEL} 75%, {ACCENT_SOFT}12 100%);
        border: 1px solid {BORDER}; border-radius: 18px; box-shadow: 0 6px 20px {ACCENT}1A;
        padding: 1.5rem 1.2rem; text-align: center; height: 100%; position: relative; overflow: hidden;
    }}

    /* Chips — filled, glowing pills instead of flat outlined boxes. */
    .chip {{
        background: {ACCENT}14; border-color: {ACCENT}40; box-shadow: 0 1px 4px {ACCENT}22;
    }}

    /* Gradient text + gradient CTA — used only on the Plan Your Trip hero
       and its primary button, kept separate from the rest of the (single-
       accent) palette so it reads as a deliberate highlight, not a re-skin. */
    .gradient-text {{
        background: linear-gradient(90deg, {ACCENT}, {GRADIENT_END});
        -webkit-background-clip: text; background-clip: text; color: transparent;
    }}
    .gradient-btn>button {{
        background: linear-gradient(90deg, {ACCENT}, {GRADIENT_END}) !important;
    }}
    .st-key-generate_trip_btn_wrap .stButton>button {{
        background: linear-gradient(90deg, {ACCENT}, {GRADIENT_END}) !important;
        color: #FFF !important; font-size: 1.02rem; padding: 0.75rem 1.3rem;
    }}
    /* Ghost/outline button — used for secondary CTAs like "View Spot Details"
       so the page has one filled gradient button (the primary action) and
       everything else stays visually secondary. */
    .st-key-view_spot_details_wrap .stButton>button {{
        background: transparent !important; border: 1.5px solid {ACCENT} !important;
        color: {ACCENT} !important;
    }}
    .st-key-view_spot_details_wrap .stButton>button:hover {{ background: {ACCENT}18 !important; }}

    /* Icon-in-circle section badges. */
    .icon-badge {{
        display: inline-flex; align-items: center; justify-content: center;
        width: 2.3rem; height: 2.3rem; border-radius: 50%; font-size: 1.1rem;
        background: linear-gradient(160deg, {ACCENT}55, {ACCENT_SOFT}33);
        border: 1px solid {ACCENT}55; margin-right: 0.6rem; vertical-align: middle;
    }}

    /* Static (non-interactive) transport-mode pills — informational only,
       matching the "Suggested transport" display in the reference design;
       the value itself is fully automatic, not user-editable. */
    .transport-pill {{
        display: inline-block; padding: 0.65rem 1.35rem; border-radius: 999px; font-weight: 600;
        font-size: 0.95rem; margin: 0.25rem 0.4rem 0.25rem 0; border: 1.5px solid {BORDER};
        color: {TEXT_MUTED}; background: {PANEL};
    }}
    .transport-pill.active {{
        background: {ACCENT}; border-color: {ACCENT}; color: #FFF;
    }}

    /* ---- Capability cards (Project Overview) — a professional
       capability-statement grid instead of a database-style table. ---- */
    .cap-card {{
        background: linear-gradient(160deg, {PANEL} 0%, {PANEL} 80%, {ACCENT}12 100%);
        border: 1px solid {BORDER}; border-radius: 18px; padding: 1.5rem 1.6rem;
        height: 100%; box-shadow: 0 8px 22px rgba(0,0,0,0.30);
    }}
    .cap-card .cap-head {{ display: flex; align-items: center; gap: 0.7rem; margin-bottom: 0.75rem; }}
    .cap-card .cap-icon {{
        width: 2.5rem; height: 2.5rem; border-radius: 12px; display: flex; align-items: center;
        justify-content: center; font-size: 1.2rem; flex-shrink: 0;
    }}
    .cap-card .cap-title {{ font-family: "Playfair Display", Georgia, serif; font-weight: 700;
        font-size: 1.05rem; color: {TEXT_MAIN}; }}
    .cap-card .cap-body {{ font-size: 0.87rem; line-height: 1.55; color: {TEXT_MUTED}; margin-bottom: 0.85rem; }}
    .cap-card .cap-why {{
        border-top: 1px dashed {BORDER}; padding-top: 0.7rem; font-size: 0.82rem; line-height: 1.5;
    }}
    .cap-card .cap-why-label {{
        font-size: 0.66rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.09em;
        display: block; margin-bottom: 0.3rem;
    }}

    /* ---- Model spec sheets (Predictions & Modules) — official technical
       datasheet layout: header, meta strip, input/output flow, rationale. ---- */
    .spec-card {{
        background: linear-gradient(160deg, {PANEL} 0%, {PANEL} 85%, {GRADIENT_END}0A 100%);
        border: 1px solid {BORDER}; border-radius: 20px; padding: 1.7rem 1.9rem; margin-bottom: 1.1rem;
        box-shadow: 0 10px 28px rgba(0,0,0,0.32);
    }}
    .spec-card .spec-head {{ display: flex; align-items: center; gap: 0.9rem; flex-wrap: wrap; margin-bottom: 1rem; }}
    .spec-card .spec-icon {{
        width: 3rem; height: 3rem; border-radius: 14px; display: flex; align-items: center;
        justify-content: center; font-size: 1.4rem; flex-shrink: 0;
    }}
    .spec-card .spec-name {{ font-family: "Playfair Display", Georgia, serif; font-weight: 700;
        font-size: 1.2rem; color: {TEXT_MAIN}; }}
    .spec-card .spec-badge {{
        display: inline-block; padding: 0.28rem 0.75rem; border-radius: 999px; font-size: 0.72rem;
        font-weight: 700; letter-spacing: 0.02em; margin-top: 0.25rem;
    }}
    .spec-card .spec-meta-strip {{
        display: flex; gap: 1.6rem; flex-wrap: wrap; padding: 0.75rem 0; margin-bottom: 0.9rem;
        border-top: 1px solid {BORDER}; border-bottom: 1px solid {BORDER};
    }}
    .spec-card .spec-meta-item .k {{
        font-size: 0.66rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: {TEXT_MUTED};
        display: block; margin-bottom: 0.2rem;
    }}
    .spec-card .spec-meta-item .v {{ font-size: 0.86rem; color: {TEXT_MAIN}; font-weight: 500; }}
    .spec-card .spec-flow {{
        font-size: 0.87rem; line-height: 1.6; color: {TEXT_MAIN}; background: {BG};
        border: 1px solid {BORDER}; border-radius: 12px; padding: 0.75rem 1rem; margin-bottom: 0.9rem;
    }}
    .spec-card .spec-flow .arrow {{ font-weight: 700; margin: 0 0.4rem; }}
    .spec-card .spec-why {{
        font-size: 0.86rem; line-height: 1.6; color: {TEXT_MUTED}; border-left: 3px solid; padding-left: 0.9rem;
    }}
    .spec-card .spec-why-label {{
        font-size: 0.66rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.09em;
        display: block; margin-bottom: 0.35rem; color: {TEXT_MAIN};
    }}

    /* ---- Supporting-module list — a clean labeled list, appendix-style. ---- */
    .module-item {{ display: flex; gap: 0.9rem; padding: 0.9rem 0; border-bottom: 1px solid {BORDER}; align-items: flex-start; }}
    .module-item:last-child {{ border-bottom: none; }}
    .module-item .m-icon {{
        width: 2.2rem; height: 2.2rem; border-radius: 10px; display: flex; align-items: center;
        justify-content: center; font-size: 1.02rem; flex-shrink: 0; margin-top: 0.1rem;
    }}
    .module-item .m-name {{ font-weight: 700; font-size: 0.92rem; color: {TEXT_MAIN}; font-family: "Playfair Display", Georgia, serif; }}
    .module-item .m-role {{ font-size: 0.84rem; color: {TEXT_MUTED}; line-height: 1.5; margin-top: 0.15rem; }}

    /* ---- Small section eyebrow label (used above each card grid) ---- */
    .section-eyebrow {{ display:flex; align-items:center; gap:0.6rem; margin-bottom:0.9rem; }}
    .section-eyebrow .bar {{ width:3px; height:1.4rem; background: linear-gradient(180deg, {ACCENT}, {GRADIENT_END}); border-radius:2px; }}
    .section-eyebrow .label {{ font-family:"Playfair Display",Georgia,serif; font-weight:700; font-size:0.95rem;
        letter-spacing:0.02em; color:{TEXT_MUTED}; text-transform:uppercase; }}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(f'<div class="bg-gradient"></div>', unsafe_allow_html=True)

st.markdown(
    f"""
    <div style='padding: 0.4rem 0 1rem 0; border-bottom: 3px solid {ACCENT}; margin-bottom: 1.2rem;'>
        <h1 style='margin:0; font-size:2.3rem;'>🗺️ Telangana_Tourism_Trails</h1>
        <p style='margin:0.35rem 0 0 0; color:{TEXT_MUTED}; font-size:0.98rem; font-family:"Work Sans",sans-serif;'>
            Discover Telangana. Plan Smarter. Travel Better.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Backend helpers
# ---------------------------------------------------------------------------
def api_get(path: str, params: dict | None = None):
    r = requests.get(f"{BACKEND_URL}{path}", params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def api_post(path: str, payload: dict):
    r = requests.post(f"{BACKEND_URL}{path}", json=payload, timeout=120)
    if not r.ok:
        detail = r.json().get("detail", r.text) if r.headers.get("content-type", "").startswith("application/json") else r.text
        raise RuntimeError(detail)
    return r.json()


# ---------------------------------------------------------------------------
# Navigator Map — Nominatim (geocoding) + OSRM (routing) + Folium (rendering).
# All three are free, no API key needed, which is why this combo (rather
# than Google Maps) is used here.
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False, ttl=3600)
def geocode_location(query: str) -> dict | None:
    """Turns free-text like 'Hyderabad Railway Station' into a (lat, lon) via
    Nominatim. Returns None if nothing matched. Results are cached for an
    hour since the same place name always geocodes the same way and this
    keeps repeat lookups from re-hitting the public server."""
    if not query or not query.strip():
        return None
    try:
        r = requests.get(
            NOMINATIM_URL,
            params={"q": f"{query}, Telangana, India", "format": "json", "limit": 1},
            headers=NOMINATIM_HEADERS, timeout=15,
        )
        r.raise_for_status()
        results = r.json()
        if not results:
            return None
        return {
            "lat": float(results[0]["lat"]), "lon": float(results[0]["lon"]),
            "display_name": results[0].get("display_name", query),
        }
    except Exception:
        return None


@st.cache_data(show_spinner=False, ttl=3600)
def get_osrm_route(waypoints: tuple[tuple[float, float], ...]) -> dict | None:
    """Actual road route through an ordered list of (lat, lon) waypoints, via
    OSRM's public demo routing server. Returns the route geometry (as a list
    of [lat, lon] points, ready for folium.PolyLine) plus total distance/
    duration, or None if OSRM couldn't route between them (e.g. a point in
    the ocean, or the demo server being temporarily unavailable)."""
    if len(waypoints) < 2:
        return None
    coord_str = ";".join(f"{lon},{lat}" for lat, lon in waypoints)
    try:
        r = requests.get(
            f"{OSRM_ROUTE_URL}/{coord_str}",
            params={"overview": "full", "geometries": "geojson"},
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("code") != "Ok" or not data.get("routes"):
            return None
        route = data["routes"][0]
        # GeoJSON geometry is [lon, lat] pairs — flip to [lat, lon] for folium.
        line = [[lat, lon] for lon, lat in route["geometry"]["coordinates"]]
        return {
            "line": line,
            "distance_km": route["distance"] / 1000,
            "duration_min": route["duration"] / 60,
        }
    except Exception:
        return None


def render_navigator_map(markers: list[dict], route: dict | None) -> None:
    """markers: list of {"name", "lat", "lon", "kind"} where kind is
    'start', 'primary', or 'stop' (controls marker color/icon). Draws all
    markers plus the OSRM route line (if available) on a Folium map, auto-
    fit to bounds so every point is visible without manual zooming."""
    center_lat = sum(m["lat"] for m in markers) / len(markers)
    center_lon = sum(m["lon"] for m in markers) / len(markers)
    fmap = folium.Map(location=[center_lat, center_lon], zoom_start=8, tiles="OpenStreetMap")

    marker_style = {
        "start": ("home", "green"),
        "primary": ("flag", "blue"),
        "stop": ("map-marker", "orange"),
    }
    for m in markers:
        icon_name, color = marker_style.get(m["kind"], ("map-pin", "gray"))
        folium.Marker(
            location=[m["lat"], m["lon"]], tooltip=m["name"],
            popup=m["name"], icon=folium.Icon(color=color, icon=icon_name, prefix="fa"),
        ).add_to(fmap)

    if route and route.get("line"):
        folium.PolyLine(route["line"], color=ACCENT, weight=5, opacity=0.85).add_to(fmap)

    bounds = [[m["lat"], m["lon"]] for m in markers]
    fmap.fit_bounds(bounds, padding=(30, 30))
    st_folium(fmap, use_container_width=True, height=480, returned_objects=[])


def _bridge(hist_dates: list, hist_values: list, fc_dates: list, fc_values: list):
    """Prepend the last historical point onto the forecast series so the two
    lines/bars visually connect at the handoff instead of leaving a gap."""
    if hist_dates and hist_values:
        return [hist_dates[-1]] + fc_dates, [hist_values[-1]] + fc_values
    return list(fc_dates), list(fc_values)


def build_temp_chart(history: list, forecast_days: list) -> go.Figure:
    """One chart, two lines (max/min temp), each drawn solid for the actual
    readings and dashed for the forecast — the same color both times, so
    the only thing that changes is 'known' vs 'predicted'. A single
    vertical line marks where the forecast starts. No confidence band, no
    trend line — just the two things a person actually wants to read."""
    hist_dates = [d["date"] for d in history]
    fc_dates = [d["date"] for d in forecast_days]
    boundary = hist_dates[-1] if hist_dates else (fc_dates[0] if fc_dates else None)

    fig = go.Figure()
    for label, hist_key, fc_key, color in [
        ("Max temp", "actual_max_temp", "predicted_max_temp", HEAT),
        ("Min temp", "actual_min_temp", "predicted_min_temp", ACCENT_SOFT),
    ]:
        hv = [d[hist_key] for d in history]
        fv = [d[fc_key] for d in forecast_days]
        fc_dates_plot, fc_values_plot = _bridge(hist_dates, hv, fc_dates, fv)

        if hist_dates:
            fig.add_trace(go.Scatter(
                x=hist_dates, y=hv, mode="lines+markers", name=label, legendgroup=label,
                line=dict(color=color, width=3), marker=dict(size=6),
                hovertemplate=f"%{{x}}<br>%{{y:.0f}}°C<extra>{label}</extra>",
            ))
        if fc_dates_plot:
            fig.add_trace(go.Scatter(
                x=fc_dates_plot, y=fc_values_plot, mode="lines+markers", name=label, legendgroup=label,
                showlegend=not hist_dates, line=dict(color=color, width=3, dash="dash"),
                marker=dict(size=6, symbol="circle-open"),
                hovertemplate=f"%{{x}}<br>%{{y:.0f}}°C (forecast)<extra>{label}</extra>",
            ))

    if boundary:
        fig.add_vline(x=boundary, line_dash="dot", line_color=TEXT_MUTED, opacity=0.6)
        fig.add_annotation(x=boundary, y=1, yref="paper", yanchor="bottom", showarrow=False,
                            text="Today", font=dict(color=TEXT_MUTED, size=11))

    fig.update_layout(
        template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=TEXT_MAIN, size=13), margin=dict(l=10, r=10, t=30, b=10), height=320,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, bgcolor="rgba(0,0,0,0)"),
        xaxis=dict(showgrid=False, type="category"), yaxis=dict(title="°C", gridcolor=BORDER, zerolinecolor=BORDER),
        hovermode="x unified",
    )
    return fig


def build_rain_chart(history: list, forecast_days: list) -> go.Figure:
    """Rain chance as plain bars — easier to read at a glance than a line
    with a shaded range. Forecast bars get a diagonal hatch pattern (the
    same 'known vs predicted' idea as the dashed line above, just adapted
    for bars) instead of a second color, so the two charts read the same way."""
    hist_dates = [d["date"] for d in history]
    hist_vals = [d["actual_rain_chance_percent"] for d in history]
    fc_dates = [d["date"] for d in forecast_days]
    fc_vals = [d["rain_chance_percent"] for d in forecast_days]
    boundary = hist_dates[-1] if hist_dates else (fc_dates[0] if fc_dates else None)

    fig = go.Figure()
    if hist_dates:
        fig.add_trace(go.Bar(
            x=hist_dates, y=hist_vals, name="So far", marker_color=ACCENT,
            hovertemplate="%{x}<br>%{y:.0f}% chance<extra>So far</extra>",
        ))
    if fc_dates:
        fig.add_trace(go.Bar(
            x=fc_dates, y=fc_vals, name="Forecast",
            marker=dict(color=ACCENT, pattern=dict(shape="/", size=7, solidity=0.35)),
            hovertemplate="%{x}<br>%{y:.0f}% chance<extra>Forecast</extra>",
        ))

    if boundary:
        fig.add_vline(x=boundary, line_dash="dot", line_color=TEXT_MUTED, opacity=0.6)
        fig.add_annotation(x=boundary, y=1, yref="paper", yanchor="bottom", showarrow=False,
                            text="Today", font=dict(color=TEXT_MUTED, size=11))

    fig.update_layout(
        template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=TEXT_MAIN, size=13), margin=dict(l=10, r=10, t=30, b=10), height=320,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, bgcolor="rgba(0,0,0,0)"),
        xaxis=dict(showgrid=False, type="category"), yaxis=dict(title="%", gridcolor=BORDER, range=[0, 100]),
        bargap=0.25,
    )
    return fig


def build_cost_chart(cost: dict) -> go.Figure:
    """Horizontal bar chart of the same itemized cost breakdown shown in the
    table above — a quick visual read of which line item dominates the
    total, colored consistently with the rest of the dashboard's palette."""
    items = [
        ("🏨 Stay", cost["stay_cost_est"], ACCENT),
        ("🍽️ Food", cost["food_cost_est"], ACCENT_SOFT),
        ("🚌 Travel", cost["travel_cost_est"], HEAT),
        ("🎫 Entry fees", cost["entry_fees_est"], WARN),
        ("🅿️ Tolls & misc", cost["tolls_and_parking_est"], TEXT_MUTED),
    ]
    items.sort(key=lambda t: t[1])
    labels = [i[0] for i in items]
    values = [i[1] for i in items]
    colors = [i[2] for i in items]

    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h", marker_color=colors,
        text=[f"₹{v:,.0f}" for v in values], textposition="outside",
        hovertemplate="%{y}<br>₹%{x:,.0f}<extra></extra>",
    ))
    fig.update_layout(
        template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=TEXT_MAIN, size=13), margin=dict(l=10, r=40, t=10, b=10), height=260,
        xaxis=dict(showgrid=True, gridcolor=BORDER, zeroline=False, title="₹"),
        yaxis=dict(showgrid=False),
        showlegend=False,
    )
    return fig


# Telangana's tourism-season calendar, mapped from the trip's start month to
# the season labels the cost model was trained on (Festival_Peak covers the
# Dussehra/Diwali stretch, Winter_Picnic the cool Dec-Feb months).
SEASON_BY_MONTH = {
    1: "Winter_Picnic", 2: "Winter_Picnic", 3: "Summer", 4: "Summer", 5: "Summer",
    6: "Monsoon", 7: "Monsoon", 8: "Monsoon", 9: "Monsoon",
    10: "Festival_Peak", 11: "Festival_Peak", 12: "Winter_Picnic",
}

# The "Route distance (km)" input has been removed from the UI. A fixed
# one-way distance is assumed instead so the cost model still has a value to
# work with — the Travel line item's actual ₹ figure comes from a realistic
# petrol-price/mileage formula in the backend (see
# predict.estimate_realistic_travel_cost), not this assumption.
ASSUMED_ROUTE_DISTANCE_KM = 40

# Mirrors predict.SAME_DISTRICT_ASSUMED_KM on the backend — display-text
# fallback only, used when coordinates are missing for a spot; the actual
# distance is computed and returned by the /distance/chain endpoint.
SAME_DISTRICT_ASSUMED_KM_LABEL = 25


def season_for_date(travel_date: date, valid_seasons: list[str]) -> str:
    season = SEASON_BY_MONTH[travel_date.month]
    return season if season in valid_seasons else valid_seasons[0]


# Rough average road speed by mode — enough for a ballpark "Est. Travel Time"
# tile, not a routing engine. Bike/auto assume mixed town+highway riding;
# car/bus assume state highway; train is an average including stops.
AVG_SPEED_KMPH = {"bike": 35, "auto": 30, "car": 50, "bus": 40, "train": 55}


def estimate_travel_time(distance_km: float, mode: str) -> str:
    speed = AVG_SPEED_KMPH.get(mode, 40)
    hours = distance_km / speed if speed else 0
    h = int(hours)
    m = int(round((hours - h) * 60))
    if m == 60:
        h, m = h + 1, 0
    if h == 0:
        return f"{m}m"
    return f"{h}h {m}m"


# ---------------------------------------------------------------------------
# Onboarding: Project Overview → Predictions & Modules → Plan Your Trip.
# Three session_state-driven "views"; each of the first two calls st.stop()
# so the main app below never runs until the person clicks through to it —
# same pattern the file already uses for the "backend unreachable" error.
# ---------------------------------------------------------------------------
if "app_view" not in st.session_state:
    st.session_state.app_view = "overview"


def render_table(headers: list[str], rows: list[list[str]]) -> None:
    ths = "".join(
        f"<th style='text-align:left; padding:0.7rem 1rem; color:{TEXT_MUTED}; font-size:0.72rem; "
        f"text-transform:uppercase; letter-spacing:0.08em; font-weight:700; "
        f"border-bottom:1px solid {BORDER};'>{h}</th>"
        for h in headers
    )
    trs = ""
    for row in rows:
        # Spot popularity is retained in the destination view, but is not
        # part of the Project Overview table.
        if row[0] == "⭐ <b>Spot Popularity</b>":
            continue
        tds = "".join(
            f"<td style='padding:0.85rem 1rem; border-bottom:1px solid {BORDER}; "
            f"vertical-align:top; font-size:0.88rem; line-height:1.45;'>{c}</td>"
            for c in row
        )
        trs += f"<tr>{tds}</tr>"
    st.markdown(
        f"""<div class="card" style="padding:0; overflow-x:auto;">
        <table style="width:100%; border-collapse:collapse;">
        <thead><tr>{ths}</tr></thead><tbody>{trs}</tbody>
        </table></div>""",
        unsafe_allow_html=True,
    )


def render_capability_grid(items: list[dict], columns: int = 2) -> None:
    """Project Overview — a capability-statement grid (icon, title, what it
    does, why it's used) instead of a table, matching how a professional
    product one-pager presents its modules."""
    cols = st.columns(columns)
    for i, item in enumerate(items):
        color = item.get("color", ACCENT)
        with cols[i % columns]:
            st.markdown(
                f"""<div class="cap-card">
                <div class="cap-head">
                    <div class="cap-icon" style="background:{color}22; color:{color};">{item['icon']}</div>
                    <div class="cap-title">{item['title']}</div>
                </div>
                <div class="cap-body">{item['what']}</div>
                <div class="cap-why" style="border-top-color:{color}44;">
                    <span class="cap-why-label" style="color:{color};">Why it's used</span>
                    {item['why']}
                </div>
                </div>""",
                unsafe_allow_html=True,
            )
            st.write("")


def render_model_specs(items: list[dict]) -> None:
    """Predictions & Modules — each trained model as an official-looking
    technical spec sheet (header, meta strip, input→output flow, rationale)
    instead of a wide table row."""
    for item in items:
        color = item.get("color", ACCENT)
        st.markdown(
            f"""<div class="spec-card">
            <div class="spec-head">
                <div class="spec-icon" style="background:{color}22; color:{color};">{item['icon']}</div>
                <div>
                    <div class="spec-name">{item['name']}</div>
                    <span class="spec-badge" style="background:{color}22; color:{color};">{item['model']}</span>
                </div>
            </div>
            <div class="spec-meta-strip">
                <div class="spec-meta-item"><span class="k">Trained On</span><span class="v">{item['trained_on']}</span></div>
            </div>
            <div class="spec-flow">{item['inputs']} <span class="arrow" style="color:{color};">→</span> {item['output']}</div>
            <div class="spec-why" style="border-left-color:{color};">
                <span class="spec-why-label">Why this model</span>{item['why']}
            </div>
            </div>""",
            unsafe_allow_html=True,
        )


def render_module_list(items: list[dict]) -> None:
    """Supporting modules — a clean labeled appendix list instead of a
    two-column table."""
    rows = "".join(
        f"""<div class="module-item">
        <div class="m-icon" style="background:{item.get('color', ACCENT)}22; color:{item.get('color', ACCENT)};">{item['icon']}</div>
        <div><div class="m-name">{item['name']}</div><div class="m-role">{item['role']}</div></div>
        </div>"""
        for item in items
    )
    st.markdown(f'<div class="card" style="padding:0.3rem 1.6rem;">{rows}</div>', unsafe_allow_html=True)


def render_section_eyebrow(label: str) -> None:
    st.markdown(
        f"""<div class="section-eyebrow"><div class="bar"></div><span class="label">{label}</span></div>""",
        unsafe_allow_html=True,
    )


NAV_STEPS = [
    ("overview", "1", "Project Overview"),
    ("modules", "2", "Predictions & Modules"),
    ("app", "3", "Plan Your Trip"),
    ("results", "4", "Predictions"),
]


def render_sidebar_nav() -> None:
    """Interactive boxed sidebar navigation with bold step labels."""
    active_view = st.session_state.app_view

    st.markdown(
        f"""<div class="sidebar-nav-title">🗺️ Telangana_Tourism_Trails</div>
        <div class="sidebar-nav-subtitle">Your Smart Travel Companion</div>""",
        unsafe_allow_html=True,
    )

    step_icons = {
        "overview": "📋",
        "modules": "🧠",
        "app": "🧭",
        "results": "📊",
    }

    for view_key, num, label in NAV_STEPS:
        is_active = view_key == active_view
        icon = step_icons.get(view_key, "•")
        button_label = f"{icon}  {num}. {label}"
        if st.button(
            button_label,
            key=f"nav_{view_key}",
            use_container_width=True,
            type="primary" if is_active else "secondary",
        ):
            st.session_state.app_view = view_key
            st.rerun()

with st.sidebar:
    render_sidebar_nav()
    st.markdown(
        f"""<div style="margin-top:2rem; border-radius:16px; padding:1.1rem 1.1rem;
        background: linear-gradient(160deg, {ACCENT}55 0%, {GRADIENT_END}33 100%);
        border: 1px solid {ACCENT}66;">
        <div style="font-size:1.6rem;">🌴</div>
        <div style="font-family:'Playfair Display',Georgia,serif; font-weight:700; font-size:1.05rem;
        margin-top:0.3rem;">Explore Telangana</div>
        <div style="font-size:0.82rem; opacity:0.85; margin-top:0.3rem; line-height:1.4;">
        Uncover hidden gems and create unforgettable memories.</div>
        </div>""",
        unsafe_allow_html=True,
    )

if st.session_state.app_view == "overview":
    hero_path = Path(__file__).parent / "images" / "hero_telangana.jpg"
    if hero_path.exists():
        st.image(str(hero_path), use_container_width=True)
    st.write("")
    st.markdown("## 📋 Project Overview")
    st.markdown(
        f"""<p style="font-family:'Playfair Display',Georgia,serif; font-style:italic;
        font-weight:600; font-size:1.15rem; line-height:1.5; color:{TEXT_MUTED};
        margin:0.3rem 0 0.6rem 0;">
        A Multi-Fusion AI-Powered Smart Tourism Platform — combining tourist demand forecasting,
        real-time crowd analytics, climate assessment, and personalized recommendations into one
        budget-aware trip planner for Telangana.</p>""",
        unsafe_allow_html=True,
    )
    st.write("")
    render_section_eyebrow("Platform Capabilities")
    render_capability_grid(
        [
            {"icon": "🧭", "title": "Trip Setup", "color": ACCENT,
             "what": "Collects district, spot(s), travel dates, group size, transport, and accommodation tier.",
             "why": "Every downstream prediction (cost, crowd, climate) needs these as inputs — this is the "
                    "single form that feeds all three models at once."},
            {"icon": "💸", "title": "Cost Estimation", "color": GRADIENT_END,
             "what": "Predicts an itemized trip cost breakdown (travel, stay, food, activities) plus "
                     "per-person/per-day figures.",
             "why": "Directly answers the problem statement's \"budget-aware tourism planning\" goal — lets "
                    "travelers compare trips of different lengths and group sizes fairly."},
            {"icon": "👥", "title": "Crowd Forecasting", "color": GOOD,
             "what": "Predicts expected visitor count at a spot for the chosen date, labeled "
                     "Quiet / Moderate / Busy / Very Crowded.",
             "why": "Core to \"real-time crowd analytics\" — the platform's main lever for mitigating "
                    "overcrowding."},
            {"icon": "🌦️", "title": "Climate Assessment", "color": ACCENT_SOFT,
             "what": "Forecasts max/min temperature and rain chance for each day of the trip.",
             "why": "Covers the \"climate impact analytics\" goal — informs both comfort and safety planning."},
            {"icon": "🎒", "title": "Packing Tips", "color": HEAT,
             "what": "Auto-generates packing suggestions (umbrella, sun protection, jacket) from the "
                     "climate forecast.",
             "why": "Turns raw climate numbers into an actionable, traveler-safety-oriented recommendation."},
            {"icon": "🔔", "title": "Amenities", "color": WARN,
             "what": "Lists nearby restaurants, ATMs, hospitals, etc. for the selected spot.",
             "why": "Supports traveler safety and convenience — knowing what's actually around a destination."},
            {"icon": "⭐", "title": "Spot Popularity", "color": ACCENT,
             "what": "Shows a spot's popularity tier (Emerging / Popular / Very Popular).",
             "why": "A lightweight personalization signal — helps travelers judge a destination before "
                    "committing a whole trip to it."},
            {"icon": "🎉", "title": "Upcoming Festivals", "color": GRADIENT_END,
             "what": "Flags festivals near the travel date, matched to their typical month.",
             "why": "Gives travelers a heads-up on likely-busier periods without needing a separate "
                    "festival calendar."},
            {"icon": "🧭", "title": "Suggested Visiting Order", "color": GOOD,
             "what": "For multi-spot trips, computes the shortest route through the selected spots.",
             "why": "Addresses \"inefficient resource utilization\" — an optimized itinerary instead of "
                    "visiting spots in click order."},
        ],
        columns=2,
    )
    st.write("")
    _, nav_col = st.columns([3, 1])
    with nav_col:
        if st.button("Continue → Predictions & Modules", use_container_width=True):
            st.session_state.app_view = "modules"
            st.rerun()
    st.stop()

if st.session_state.app_view == "modules":
    st.markdown("## 🧠 Predictions & Modules Used")
    st.caption("The three trained models behind the app's predictions, and the supporting modules around them.")
    st.write("")
    render_section_eyebrow("Predictions — Model Specifications")
    render_model_specs(
        [
            {
                "icon": "💸", "name": "Cost Estimation", "color": GRADIENT_END,
                "model": "Multi-output XGBoost Regressor",
                "trained_on": "trip_budget_prediction table",
                "inputs": "Duration · Travelers · Distance · Transport Mode · Accommodation Tier · Season",
                "output": "Itemized cost breakdown",
                "why": "Cost depends on nonlinear interactions between inputs (e.g. accommodation tier "
                       "matters far more on a 7-day trip than a 1-day one) — gradient-boosted trees capture "
                       "that without manual feature engineering. The multi-output wrapper predicts all 5 "
                       "cost components (stay, food, travel, entry, misc) in a single pass so they stay "
                       "consistent with each other and sum cleanly to the total.",
            },
            {
                "icon": "👥", "name": "Crowd Forecasting", "color": GOOD,
                "model": "XGBoost Regressor",
                "trained_on": "spot_visitors table",
                "inputs": "Spot · District · Category · Year · Month · Season · Festival",
                "output": "Predicted visitor count",
                "why": "Visitor counts spike around specific festival/month/spot combinations rather than "
                       "increasing smoothly — a tree-based model handles that kind of \"it depends which "
                       "spot AND which month\" interaction well, trains fast on tabular data, and needs no "
                       "scaling of the categorical spot/district/category features.",
            },
            {
                "icon": "🌦️", "name": "Climate Assessment", "color": ACCENT_SOFT,
                "model": "PyTorch LSTM (Sequence Model)",
                "trained_on": "climate_dataset table",
                "inputs": "Recent daily max/min temperature &amp; rainfall sequence",
                "output": "Next-day(s) max/min temp and rain chance",
                "why": "Tomorrow's weather depends on the recent trend, not the calendar date alone — "
                       "climate is fundamentally sequential. An LSTM's recurrent memory is built exactly "
                       "for that kind of day-to-day dependency, which a plain regressor treating each day "
                       "independently would miss; a rolling seasonal-average blend then corrects its drift "
                       "for forecasts further out.",
            },
        ],
    )

    # -----------------------------------------------------------------
    # (Climate-forecast walkthrough removed here per request.)
    # -----------------------------------------------------------------

    st.write("")
    render_section_eyebrow("Supporting Infrastructure")
    render_module_list(
        [
            {"icon": "⚙️", "color": ACCENT, "name": "FastAPI Backend",
             "role": "Serves every prediction and lookup endpoint (/predict/*, /spot-info, "
                     "/amenities, /distance/*) over HTTP."},
            {"icon": "🗄️", "color": ACCENT_SOFT, "name": "SQLite Database",
             "role": "smart_tourism.db — holds spot/crowd/climate/cost history plus amenities and "
                     "popularity, replacing the project's original CSV files."},
            {"icon": "🧮", "color": GOOD, "name": "scikit-learn Preprocessing",
             "role": "Ordinal/one-hot encoding and imputation pipelines that turn raw form inputs into the "
                     "exact feature format each trained model expects."},
            {"icon": "🧭", "color": HEAT, "name": "Route Optimization (Haversine + Heuristic)",
             "role": "Computes real spot-to-spot distances and the shortest visiting order — exact for "
                     "small trips, nearest-neighbor for larger ones."},
            {"icon": "🎉", "color": GRADIENT_END, "name": "Festival Calendar Mapping",
             "role": "Maps each known festival to its typical month, so upcoming festivals can be matched "
                     "to the travel date."},
            {"icon": "🎒", "color": WARN, "name": "Packing-Tip Rules Engine",
             "role": "Rule-based (not ML) — turns forecasted temperature/rain thresholds into "
                     "plain-language packing suggestions."},
            {"icon": "📊", "color": ACCENT, "name": "Streamlit Frontend + Plotly",
             "role": "This UI, and the climate history/forecast charts on the Climate Info tab."},
        ],
    )
    st.write("")
    back_col, _, next_col = st.columns([1, 2, 1])
    with back_col:
        if st.button("← Back", use_container_width=True):
            st.session_state.app_view = "overview"
            st.rerun()
    with next_col:
        if st.button("Continue → Plan Your Trip", use_container_width=True):
            st.session_state.app_view = "app"
            st.rerun()
    st.stop()


# ===========================================================================
# Step 4 — Predictions. A dedicated page, reached only via "Generate
# Predictions" on the Plan Your Trip step below — same session_state-driven
# pattern as the Overview/Modules steps, so predictions are never squeezed
# into a narrow column alongside the input form.
# ===========================================================================
if st.session_state.app_view == "results":
    ctx = st.session_state.get("trip_context")
    if not ctx:
        st.markdown(
            f"""<div class="card"><h4 style='color:{TEXT_MAIN}; margin:0; font-weight:600;'>
            No trip configured yet — head back to Plan Your Trip to set one up.
            </h4></div>""",
            unsafe_allow_html=True,
        )
        if st.button("← Plan Your Trip", use_container_width=True):
            st.session_state.app_view = "app"
            st.rerun()
        st.stop()

    payload = ctx["payload"]
    disp = ctx["display"]
    selected_spot = disp["selected_spot"]
    selected_district = disp["selected_district"]
    start_date = disp["start_date"]
    end_date = disp["end_date"]
    duration_days = disp["duration_days"]
    num_travelers = disp["num_travelers"]
    transport_mode = disp["transport_mode"]
    accommodation_tier = disp["accommodation_tier"]
    user_budget = disp["user_budget"]
    # Falls back to [selected_spot] for trip_context saved before this key
    # existed (e.g. a session mid-flight when this feature shipped).
    selected_spots_for_map = disp.get("selected_spots") or [selected_spot]

    top_col1, top_col2 = st.columns([3, 1])
    with top_col1:
        st.markdown(f"## 📊 Predictions for {selected_spot}")
        st.caption(f"{selected_district} · {start_date} to {end_date} ({duration_days} day(s))")
    with top_col2:
        st.write("")
        if st.button("← Edit Trip Details", key="edit_trip_top", use_container_width=True):
            st.session_state.app_view = "app"
            st.rerun()

    # Cache the result against the exact payload — a fresh generation from
    # Plan Your Trip always recomputes, but incidental reruns on this page
    # (like a tab switch) won't needlessly re-call the API.
    cache_key = json.dumps(payload, sort_keys=True, default=str)
    if st.session_state.get("trip_result_cache_key") != cache_key:
        with st.spinner("Running AI predictions..."):
            try:
                result = api_post("/predict/trip", payload)
            except Exception as e:
                st.error(f"Prediction failed: {e}")
                st.stop()
        st.session_state["trip_result"] = result
        st.session_state["trip_result_cache_key"] = cache_key
    else:
        result = st.session_state["trip_result"]

    cost = result["cost"]
    crowd = result["crowd"]
    climate = result["climate"]
    climate_error = result["climate_error"]
    climate_forecast = result.get("climate_forecast") or {}
    packing_tips = result.get("packing_tips") or []
    upcoming_festivals = result.get("upcoming_festivals") or []
    num_spots = disp.get("num_spots", 1)

    st.write("")
    st.markdown(
        f"""<div style="background:{WARN}15; border:1px solid {WARN}55; border-radius:10px;
        padding:0.9rem 1.1rem; margin-bottom:1rem; font-size:0.88rem; line-height:1.5;">
        <b style="color:{WARN};">⚠️ DISCLAIMER:</b> Predictions shown here are generated by machine learning
        models trained on historical data and are estimates only — actual costs, crowd levels, and weather
        may vary. This tool is meant to assist trip planning, not replace official sources.
        </div>""",
        unsafe_allow_html=True,
    )

    # ---- Stat preview row — visible above the tabs regardless of which one
    # is open, mirroring the reference layout's always-visible tile row. ----
    budget_balance = user_budget - cost["total_estimated_cost"] if user_budget > 0 else None
    travel_time_label = estimate_travel_time(payload["route_distance_km"], transport_mode)
    transport_icon = {"bike": "🏍️", "auto": "🛺", "car": "🚗", "bus": "🚌", "train": "🚆"}.get(transport_mode, "🚗")

    tile_specs = [
        (transport_icon, "TRANSPORT MODE", transport_mode.upper(), "As configured", ACCENT),
        ("🏨", "STAY TIER", accommodation_tier.upper(), f"Tier: {accommodation_tier}", ACCENT_SOFT),
        ("📍", "TOTAL DISTANCE", f"{payload['route_distance_km']:,.1f} km", "Route span", ACCENT_SOFT),
        ("🕒", "EST. TRAVEL TIME", travel_time_label, "One-way, road estimate", ACCENT_SOFT),
        ("💰", "PREDICTED COST", f"₹{cost['total_estimated_cost']:,.0f}", "Total expenses", ACCENT),
        (
            "💳", "BUDGET BALANCE",
            (f"₹{abs(budget_balance):,.0f}" if budget_balance is not None else "—"),
            (("Surplus" if budget_balance >= 0 else "Deficit") if budget_balance is not None else "No budget set"),
            (GOOD if (budget_balance is not None and budget_balance >= 0) else
             (BAD if budget_balance is not None else TEXT_MUTED)),
        ),
    ]
    tile_cols = st.columns(6)
    for col, (icon, label, value, sub, color) in zip(tile_cols, tile_specs):
        with col:
            st.markdown(
                f"""<div class="hero-stat" style="padding:0.9rem 0.6rem;">
                <div class="icon" style="font-size:1.2rem;">{icon}</div>
                <div class="label" style="font-size:0.62rem;">{label}</div>
                <div class="value" style="font-size:1.15rem; color:{color};">{value}</div>
                <div class="sub" style="font-size:0.68rem;">{sub}</div></div>""",
                unsafe_allow_html=True,
            )

    st.write("")

    # ---- Destination Snapshot — category, popularity, entry fee, and
    # amenities for the primary spot, in one glance-able strip so this page
    # is fully self-contained (no need to flip back to Plan Your Trip). ----
    try:
        snap_info = api_get(f"/spot-info/{selected_spot}")
    except Exception:
        snap_info = {"available": False}
    try:
        snap_amenities = api_get(f"/amenities/{selected_spot}")
    except Exception:
        snap_amenities = {"available": False, "amenities": []}

    with st.container(border=True):
        snap_col1, snap_col2 = st.columns([1, 2])
        with snap_col1:
            st.markdown(f"#### 📍 {selected_spot}")
            if snap_info.get("available"):
                POPULARITY_COLOR2 = {"Emerging": TEXT_MUTED, "Popular": ACCENT_SOFT, "Very Popular": ACCENT}
                pop_color2 = POPULARITY_COLOR2.get(snap_info["popularity_label"], TEXT_MUTED)
                chip_parts = [
                    f'<span class="chip" style="border-color:{pop_color2}66; color:{pop_color2}; '
                    f'font-weight:600;">⭐ {snap_info["popularity_label"]} ({snap_info["popularity"]})</span>'
                ]
                if snap_info.get("category"):
                    chip_parts.append(f'<span class="chip">🏷️ {snap_info["category"]}</span>')
                if snap_info.get("entry_fee"):
                    chip_parts.append(f'<span class="chip">🎫 ₹{snap_info["entry_fee"]:,.0f} entry</span>')
                chip_parts.append(f'<span class="chip">🗺️ {selected_district}</span>')
                st.markdown("".join(chip_parts), unsafe_allow_html=True)
            else:
                st.caption("No popularity/category data on record for this spot.")
        with snap_col2:
            st.markdown("###### 🛎️ Amenities Nearby")
            if snap_amenities.get("available"):
                st.markdown(
                    "".join(f'<span class="chip">{a}</span>' for a in snap_amenities["amenities"]),
                    unsafe_allow_html=True,
                )
            else:
                st.caption("Amenities data isn't available for this spot yet.")

    st.write("")
    cost_tab, climate_tab, crowd_tab, map_tab = st.tabs(
        ["💸 Cost Estimation", "🌦️ Climate Info", "👥 Crowd Data", "🗺️ Navigator Map"]
    )

    with cost_tab:
        st.markdown(
            f"""<div class="hero-stat" style="padding:1.8rem;">
            <div class="label">Total Estimated Cost</div>
            <div class="value" style="color:{ACCENT}; font-size:3rem;">₹{cost['total_estimated_cost']:,.0f}</div>
            <div class="sub">for {num_travelers} traveler(s) over {duration_days} day(s), travelling by {transport_mode}
            with {accommodation_tier.lower()}-tier stay</div></div>""",
            unsafe_allow_html=True,
        )
        st.write("")

        per_person = cost["total_estimated_cost"] / max(1, num_travelers)
        per_day = cost["total_estimated_cost"] / max(1, duration_days)
        per_person_per_day = per_person / max(1, duration_days)
        pp_col1, pp_col2, pp_col3 = st.columns(3)
        with pp_col1:
            st.markdown(f"""<div class="hero-stat"><div class="label">Per Person</div>
            <div class="value" style="font-size:1.6rem; color:{ACCENT_SOFT};">₹{per_person:,.0f}</div>
            <div class="sub">total for the whole trip</div></div>""", unsafe_allow_html=True)
        with pp_col2:
            st.markdown(f"""<div class="hero-stat"><div class="label">Per Day</div>
            <div class="value" style="font-size:1.6rem; color:{ACCENT_SOFT};">₹{per_day:,.0f}</div>
            <div class="sub">for the whole group</div></div>""", unsafe_allow_html=True)
        with pp_col3:
            st.markdown(f"""<div class="hero-stat"><div class="label">Per Person / Day</div>
            <div class="value" style="font-size:1.6rem; color:{ACCENT_SOFT};">₹{per_person_per_day:,.0f}</div>
            <div class="sub">the easiest number to compare trips by</div></div>""", unsafe_allow_html=True)
        st.write("")

        st.write("")
        st.markdown("#### 📋 Detailed Itemized Cost Breakdown")
        fare_varies = transport_mode in ("bus", "train")
        travel_details = f"{transport_mode.upper()} mode · {payload['route_distance_km']:,.1f} km route span"
        render_table(
            ["Expense Category", "Details & Basis", "Predicted Cost"],
            [
                ["🏨 <b>Accommodation (Stay)</b>",
                 f"{duration_days} night(s) · {accommodation_tier} tier",
                 f"₹{cost['stay_cost_est']:,.0f}"],
                ["🍽️ <b>Food & Dining</b>",
                 f"{duration_days} day(s) × {num_travelers} traveler(s)",
                 f"₹{cost['food_cost_est']:,.0f}"],
                ["🚌 <b>Travel & Transport</b>", travel_details, f"₹{cost['travel_cost_est']:,.0f}"],
                ["🎫 <b>Sightseeing & Entry Fees</b>",
                 f"{num_spots} spot(s) entry fees total",
                 f"₹{cost['entry_fees_est']:,.0f}"],
                ["🅿️ <b>Tolls & Parking / Misc</b>",
                 "Route tolls, parking & local levies",
                 f"₹{cost['tolls_and_parking_est']:,.0f}"],
                ["💰 <b>Total Predicted Trip Budget</b>",
                 "All-inclusive estimated expenditure",
                 f"<b style='color:{GOOD};'>₹{cost['total_estimated_cost']:,.0f}</b>"],
            ],
        )
        if fare_varies:
            st.caption(
                f"🎫 **Ticket cost may differ** — {transport_mode} fares vary by operator, class, and "
                "how early you book. The figure above uses an average fare for this distance; check "
                "current fares before booking to confirm the actual travel cost."
            )

        st.write("")
        st.markdown("##### 📊 Where the money goes")
        st.plotly_chart(build_cost_chart(cost), use_container_width=True, config={"displayModeBar": False})

        if user_budget > 0:
            budget_difference = user_budget - cost["total_estimated_cost"]
            budget_status = (
                f"You are **₹{budget_difference:,.0f} within** your estimated budget."
                if budget_difference >= 0
                else f"The estimated trip cost is **₹{abs(budget_difference):,.0f} over** your budget."
            )
            st.write("")
            st.info(f"""**Your estimated budget:** ₹{user_budget:,.0f}  
{budget_status}""")

    with climate_tab:
        if climate:
            rain = climate["rain_chance_percent"]
            tmax = climate["predicted_max_temp"]
            rain_color = GOOD if rain < 30 else (WARN if rain < 60 else BAD)
            heat_color = GOOD if tmax < 32 else (WARN if tmax < 38 else BAD)

            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown(f"""<div class="hero-stat"><div class="icon">🌡️</div>
                <div class="label">Predicted Max Temp</div>
                <div class="value" style="color:{heat_color};">{tmax:.0f}°C</div>
                <div class="sub">daytime peak</div></div>""", unsafe_allow_html=True)
            with col2:
                st.markdown(f"""<div class="hero-stat"><div class="icon">🌙</div>
                <div class="label">Predicted Min Temp</div>
                <div class="value" style="color:{ACCENT_SOFT};">{climate['predicted_min_temp']:.0f}°C</div>
                <div class="sub">overnight low</div></div>""", unsafe_allow_html=True)
            with col3:
                st.markdown(f"""<div class="hero-stat"><div class="icon">🌧️</div>
                <div class="label">Possible Rainfall</div>
                <div class="value" style="color:{rain_color};">{rain:.0f}%</div>
                <div class="sub">chance of rain</div></div>""", unsafe_allow_html=True)

            st.write("")
            if rain >= 60 or tmax >= 38:
                st.warning(climate["recommendation"])
            elif rain < 20 and tmax < 34:
                st.success(climate["recommendation"])
            else:
                st.info(climate["recommendation"])
            st.caption(
                f"Forecast for **{selected_district}** on **{climate['forecast_date']}** "
                f"({climate['days_ahead']} day(s) ahead of the dataset's latest reading, {climate['last_known_date']})."
            )

            forecast_days = climate_forecast.get("days") or []
            forecast_history = climate_forecast.get("history") or []
            if forecast_days:
                st.write("")
                st.markdown("#### Climate forecast for your trip")
                st.caption(
                    f"Prediction window: **{start_date:%b %d, %Y} to {end_date:%b %d, %Y}**. "
                    "Solid lines/bars are recorded weather; dashed lines and hatched bars are the "
                    "model's prediction for these selected travel dates."
                )
                # Full-width page now, so these run side by side instead of stacked.
                chart_col1, chart_col2 = st.columns(2)
                with chart_col1:
                    st.markdown("**Temperature (°C)**")
                    st.plotly_chart(
                        build_temp_chart(forecast_history, forecast_days), use_container_width=True,
                        config={"displayModeBar": False},
                    )
                with chart_col2:
                    st.markdown("**Chance of rain (%)**")
                    st.plotly_chart(
                        build_rain_chart(forecast_history, forecast_days), use_container_width=True,
                        config={"displayModeBar": False},
                    )

            if packing_tips:
                st.write("")
                st.markdown("#### 🎒 Packing Tips")
                st.caption("Auto-generated from the trip window's climate forecast.")
                for tip in packing_tips:
                    st.markdown(f"- {tip}")
        else:
            st.error(f"Couldn't generate a climate forecast: {climate_error}")

    with crowd_tab:
        v = crowd["predicted_visitors"]
        # Thresholds match the backend's recalibrated crowd_level_label
        # cutoffs (4,000 / 8,500 / 15,000 — the dataset's real quartiles),
        # not the old fixed 8,000/15,000 split, which disagreed with the
        # backend's own labels and made "Busy" show up almost regardless
        # of date.
        crowd_emoji = "🟢" if v < 4000 else ("🟡" if v < 8500 else ("🟠" if v < 15000 else "🔴"))
        crowd_col1, crowd_col2 = st.columns(2)
        with crowd_col1:
            st.markdown(f"""<div class="hero-stat"><div class="icon">👥</div>
            <div class="label">Predicted Visitors</div>
            <div class="value" style="color:{ACCENT};">{v:,.0f}</div>
            <div class="sub">on your travel date</div></div>""", unsafe_allow_html=True)
        with crowd_col2:
            level_color = GOOD if v < 4000 else (ACCENT_SOFT if v < 8500 else (WARN if v < 15000 else BAD))
            st.markdown(f"""<div class="hero-stat"><div class="icon">{crowd_emoji}</div>
            <div class="label">Crowd Level</div>
            <div class="value" style="color:{level_color}; font-size:1.6rem;">{crowd['crowd_level']}</div>
            <div class="sub">Quiet 🟢 · Moderate 🟡 · Busy 🟠 · V.Crowded 🔴</div></div>""", unsafe_allow_html=True)

        st.write("")
        advice_col, festival_col = st.columns(2)
        with advice_col:
            st.markdown("##### 🧭 Suggested planning advice")
            if v >= 15000:
                st.warning("🚧 Very crowded forecast. Recommend booking early and visiting in off-peak hours.")
            elif v >= 8500:
                st.info("⚖️ Busy day expected. Good for planning around peak hours.")
            elif v >= 4000:
                st.info("🙂 Moderate crowd expected. Good for planning a balanced sightseeing day.")
            else:
                st.success("✅ Low crowd is expected. Ideal for relaxed travel and flexible itineraries.")

        with festival_col:
            if upcoming_festivals:
                st.markdown("##### 🎉 Upcoming Festivals")
                st.caption(
                    "No separate visitor number per festival — the single **Predicted visitors** "
                    "figure above already is the number to go by."
                )
                for f in upcoming_festivals[:5]:
                    f_date = date.fromisoformat(f["forecast_date"])
                    date_label = f_date.strftime("%B %d, %Y")
                    exactness = "estimated month" if f.get("date_is_estimate") else "festival date"
                    when = "today" if f["days_until"] == 0 else f"in {f['days_until']} day(s)"
                    st.markdown(
                        f"""<div class="cost-row"><div><div class="name">🎊 {f['festival']}</div>
                        <div class="desc">📅 {date_label} · ⏳ {when} · {exactness}</div></div></div>""",
                        unsafe_allow_html=True,
                    )
            else:
                st.markdown("##### 🎉 Upcoming Festivals")
                st.caption("No festivals matched to this spot/date window.")

    with map_tab:
        st.markdown("##### 🗺️ Route to Your Destination(s)")
        st.caption(
            "Enter any starting point — your home, a hotel, a landmark — and this draws the actual "
            "road route to your selected spot(s). Powered by Nominatim (geocoding) + OSRM (routing) + "
            "Folium (the map itself) — all free, open-source, no API key."
        )
        start_query = st.text_input(
            "📍 Your starting location", placeholder="e.g. Secunderabad Railway Station, Hyderabad",
            key="nav_map_start_location",
        )

        with st.spinner("Loading spot coordinates..."):
            try:
                coord_resp = api_post("/spot-coordinates", {"spots": selected_spots_for_map})
                spot_coords = {c["spot_name"]: c for c in coord_resp["coordinates"] if c["available"]}
            except Exception as e:
                spot_coords = {}
                st.caption(f"Couldn't load spot coordinates: {e}")

        missing_coords = [s for s in selected_spots_for_map if s not in spot_coords]
        if missing_coords:
            st.caption(f"⚠️ No coordinates on record for: {', '.join(missing_coords)} — skipped on the map.")

        markers = []
        route_waypoints = []
        start_geo = None
        if start_query.strip():
            with st.spinner("Locating your starting point..."):
                start_geo = geocode_location(start_query)
            if start_geo is None:
                st.warning(
                    "🔍 Couldn't find that location — try adding a city/district "
                    "(e.g. 'Karimnagar Bus Stand, Karimnagar')."
                )
            else:
                st.caption(f"📌 Matched to: {start_geo['display_name']}")
                markers.append({"name": f"Start: {start_query}", "lat": start_geo["lat"],
                                 "lon": start_geo["lon"], "kind": "start"})
                route_waypoints.append((start_geo["lat"], start_geo["lon"]))

        for i, spot in enumerate(selected_spots_for_map):
            c = spot_coords.get(spot)
            if c is None:
                continue
            markers.append({"name": spot, "lat": c["lat"], "lon": c["lon"],
                             "kind": "primary" if i == 0 else "stop"})
            route_waypoints.append((c["lat"], c["lon"]))

        if not markers:
            st.info(
                "Nothing to show yet — enter a starting location above, or make sure your selected "
                "spot(s) have coordinates on record."
            )
        else:
            route = None
            if len(route_waypoints) >= 2:
                with st.spinner("Calculating road route..."):
                    route = get_osrm_route(tuple(route_waypoints))
                if route is None and start_geo is not None:
                    st.caption("⚠️ Couldn't compute a road route right now — showing markers only.")

            render_navigator_map(markers, route)

            if route:
                r1, r2 = st.columns(2)
                with r1:
                    st.markdown(f"""<div class="hero-stat"><div class="icon">🛣️</div>
                    <div class="label">Road Distance</div>
                    <div class="value" style="color:{ACCENT};">{route['distance_km']:,.1f} km</div>
                    <div class="sub">actual route, not straight-line</div></div>""", unsafe_allow_html=True)
                with r2:
                    hrs = int(route["duration_min"] // 60)
                    mins = int(route["duration_min"] % 60)
                    time_label = f"{hrs}h {mins}m" if hrs else f"{mins}m"
                    st.markdown(f"""<div class="hero-stat"><div class="icon">⏱️</div>
                    <div class="label">Estimated Drive Time</div>
                    <div class="value" style="color:{ACCENT};">{time_label}</div>
                    <div class="sub">OSRM driving estimate, no traffic</div></div>""", unsafe_allow_html=True)
    st.stop()

# ===========================================================================
# Step 3 — Plan Your Trip: selecting a destination and configuring the trip.
# Predictions live on their own step (above) — this page is inputs only.
# ===========================================================================
try:
    districts = api_get("/districts")
except Exception:
    st.error(
        f"Can't reach the backend at **{BACKEND_URL}**. Start it first:\n\n"
        f"```\ncd backend\nuvicorn main:app --reload\n```"
    )
    st.stop()

options = api_get("/options")

st.markdown(
    f"""<div style='padding: 0.2rem 0 0.4rem 0;'>
    <h1 style='margin:0; font-size:2.4rem;'>Plan Your <span class="gradient-text">Trip</span> ✈️</h1>
    <p style='margin:0.4rem 0 0 0; color:{TEXT_MUTED}; font-size:1rem;'>
        Configure your trip preferences and get AI-powered recommendations with cost, climate,
        and crowd insights.
    </p></div>""",
    unsafe_allow_html=True,
)
st.write("")

# ---------------------------------------------------------------------------
# Jump the Start Date to match a picked festival — runs as the festival
# pills' on_change callback, so it fires (and updates trip_start_date in
# session_state) before the date_input widget below re-renders, even
# though the pills sit further down the form.
# ---------------------------------------------------------------------------
def _apply_festival_date():
    picked = st.session_state.get("festival_filter")
    if not picked:
        return
    try:
        resp = api_get(f"/festival-date/{picked}", {"from_date": date.today().isoformat()})
        new_date = date.fromisoformat(resp["date"])
        st.session_state["trip_start_date"] = max(new_date, date.today())
        st.session_state["_festival_date_is_estimate"] = resp.get("date_is_estimate", False)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Trip Configuration — every prediction input, gathered first so the
# Selected Destination panel and Smart Insights strip below can use the
# values live. (The interactive route map lives on the Predictions page's
# Navigator Map tab — this page stays a fast, focused input form.)
# ---------------------------------------------------------------------------
with st.container(border=True):
    st.markdown(
        '<span class="icon-badge">⚙️</span>'
        '<span style="font-family:\'Playfair Display\',Georgia,serif; font-weight:700; '
        'font-size:1.25rem; vertical-align:middle;">Trip Configuration</span>',
        unsafe_allow_html=True,
    )
    st.caption("Customize your travel preferences")

    # Row 1 — where: district on the left, tourist spot(s) on the right.
    # Full page width (instead of a single narrow column) so both fields
    # get real room instead of stacking one under the other.
    row1_c1, row1_c2 = st.columns([0.4, 0.6])
    with row1_c1:
        selected_district = st.selectbox("📍 Destination Hub / Area", districts)

        # Interactive filter: narrow the spot list by category before picking,
        # instead of a disconnected "spot category" field further down the form.
        category_options = options["categories"]
        category_filter = st.pills(
            "🏷️ Filter spots by category", category_options, selection_mode="single",
            key="spot_category_filter",
            help="Tap a category to narrow the spot list on the right — tap again to clear it.",
        )
    with row1_c2:
        spot_params = {"district": selected_district}
        if category_filter:
            spot_params["category"] = category_filter
        filtered_spot_options = api_get("/spots", spot_params)
        default_spots = filtered_spot_options[:1] if filtered_spot_options else []
        selected_spots = st.multiselect(
            "🚩 Tourist Spot(s)", filtered_spot_options,
            default=default_spots,
            help="Pick one spot for a single-destination trip, or several to plan a multi-stop route. "
                 "Predictions (cost, crowd, climate) are shown for the first spot in the list.",
        )
        if not selected_spots:
            st.warning("No tourist spot records match this filter." if not filtered_spot_options
                       else "Select at least one tourist spot to continue.")
            st.stop()
    # Predictions (cost/crowd/climate/amenities) are single-spot by design,
    # so the first spot picked is treated as the trip's primary destination.
    selected_spot = selected_spots[0]

    try:
        spot_info = api_get(f"/spot-info/{selected_spot}")
    except Exception:
        spot_info = {"available": False}

    # This field no longer needs to be shown to the user — it's pre-filled
    # from the selected spot's recorded category (falling back to any active
    # category filter, then the first option) and used directly as a
    # prediction input.
    default_category = (
        spot_info.get("category") if spot_info.get("available") and spot_info.get("category") in category_options
        else (category_filter if category_filter else (category_options[0] if category_options else None))
    )
    category = default_category

    st.markdown("---")

    # Row 2 — when & who: date, duration, travelers side by side.
    row2_c1, row2_c2, row2_c3 = st.columns(3)
    with row2_c1:
        start_date = st.date_input("📅 Start Date", value=date.today(), min_value=date.today(),
                                    key="trip_start_date")
    with row2_c2:
        duration_days = st.number_input("🗓️ Duration (Days)", min_value=1, max_value=30, value=3,
                                         key="trip_duration_days")
    with row2_c3:
        num_travelers = st.number_input("👥 Travelers", min_value=1, max_value=20, value=2)
    end_date = start_date + timedelta(days=duration_days)
    st.caption(f"**Travel window:** {start_date} to {end_date}")

    suggested = api_get("/transport-suggestions", {"num_travelers": num_travelers})
    transport_modes = options["transport_modes"]
    default_transport = suggested[0] if suggested else transport_modes[0]

    # Transport mode is user-editable — pills default to the auto-suggested
    # mode for this group size, but any mode can be tapped to override it.
    # For groups over 5 (too many for a car/auto/bike), both bus and train
    # are called out as suggestions since neither is a clearly better fit.
    if num_travelers > 5:
        suggestion_note = "Bus or Train recommended for this group size — tap to pick either"
    elif num_travelers == 2:
        suggestion_note = "Bike recommended — tap to change"
    elif num_travelers <= 3:
        suggestion_note = "Auto recommended — tap to change"
    else:
        suggestion_note = "Car recommended — tap to change"
    st.markdown(f"**Suggested transport for {num_travelers} traveler(s):** ({suggestion_note})")
    transport_pick = st.pills(
        "Transport mode", transport_modes, selection_mode="single",
        default=default_transport, key="transport_mode_pick", label_visibility="collapsed",
    )
    transport_mode = transport_pick if transport_pick else default_transport

    st.markdown("---")

    # Row 3 — money & timing: accommodation, budget, and an interactive
    # festival filter side by side (replaces the old boxed "spot category /
    # nearby festival" section — festival is now a tappable pill row).
    row3_c1, row3_c2, row3_c3 = st.columns(3)
    with row3_c1:
        accommodation_tier = st.selectbox("🏨 Accommodation Tier", options["accommodation_tiers"], index=1)
    with row3_c2:
        user_budget = st.number_input(
            "💰 Estimated Budget (₹)",
            min_value=0, value=0, step=500,
            help="Enter the total amount you plan to spend for this trip. Leave it at ₹0 if you do not have "
                 "a budget yet.",
        )
    with row3_c3:
        season = season_for_date(start_date, options["seasons"])
        st.caption(f"**Season:** {season} · auto-detected")

    festival_options = [f for f in options["festivals"] if f != "None"]
    st.markdown("🎉 **Nearby festival** (optional — tap one to jump your Start Date to it)")
    festival_pick = st.pills(
        "Nearby festival", festival_options, selection_mode="single",
        key="festival_filter", label_visibility="collapsed", on_change=_apply_festival_date,
    )
    if festival_pick:
        is_estimate = st.session_state.get("_festival_date_is_estimate", False)
        note = "estimated month — exact date not yet in the calendar" if is_estimate else "confirmed date"
        st.caption(f"📅 Start Date jumped to **{start_date}** for {festival_pick} ({note}).")

    # The crowd model's Festival input is always derived from the actual
    # Start Date, not from whichever pill was last tapped — a "busy" crowd
    # prediction can only be attributed to a festival when the travel date
    # genuinely falls in that festival's window. Tapping a pill above is
    # just a shortcut to jump the date there; it's this date-driven lookup,
    # not the pill selection itself, that reaches the crowd model. This
    # also means a mismatch is impossible: e.g. picking "Diwali" and then
    # changing Duration/Start Date away from Nov 8 can no longer leave a
    # stale "Diwali" festival flag feeding the model for an ordinary day.
    try:
        festival_match = api_get("/festival-for-date", {"target_date": start_date.isoformat()})
        festival = festival_match["festival"]
    except Exception:
        festival = "None"
        festival_match = {"festival": "None", "is_month_level_estimate": False}
    if festival != "None":
        est_note = " — estimated month, not a confirmed date" if festival_match.get("is_month_level_estimate") else ""
        st.caption(f"🎊 Your travel date falls during **{festival}**{est_note} — crowd prediction accounts for this.")
    else:
        st.caption("📆 No festival falls on your travel date — crowd prediction reflects a regular day, "
                    "not festival-level crowds.")

    st.write("")
    with st.container(key="generate_trip_btn_wrap"):
        generate_predictions = st.button(
            "Generate My Trip Plan ✨", type="primary", use_container_width=True,
            key="generate_trip_plan_btn",
        )

# ---------------------------------------------------------------------------
# Distance between selected spots — computed here (before the map/insights
# columns render) since both need it: the map draws the route, and the
# Smart Insights strip needs a route distance for its live cost preview.
# ---------------------------------------------------------------------------
effective_route_distance_km = ASSUMED_ROUTE_DISTANCE_KM
chain_distance = None
visit_order = None

if len(selected_spots) >= 2:
    try:
        chain_distance = api_post("/distance/chain", {"spots": selected_spots})
        if chain_distance["all_available"]:
            effective_route_distance_km = chain_distance["total_km"]
    except Exception:
        chain_distance = None
    try:
        visit_order = api_post("/distance/optimize", {"spots": selected_spots})
    except Exception:
        visit_order = None

# Quick live preview of cost/crowd/climate using the current form values —
# same models the full "Generate My Trip Plan" flow uses, just called
# eagerly here so the map stats and Smart Insights strip update as the
# person adjusts inputs, without waiting for the full multi-page flow.
preview_cost = None
try:
    preview_cost = api_post("/predict/cost", {
        "duration_days": duration_days, "num_travelers": num_travelers,
        "route_distance_km": effective_route_distance_km, "transport_mode": transport_mode,
        "accommodation_tier": accommodation_tier, "season": season,
        # Real recorded entry fees for these spot(s) replace the model's
        # blind entry-fee guess when available — see predict.predict_budget_cost().
        "spot_names": selected_spots,
    })
except Exception:
    preview_cost = None

preview_crowd = None
try:
    preview_crowd = api_post("/predict/crowd", {
        "spot_name": selected_spot, "district": selected_district, "category": category,
        "year": start_date.year, "month": start_date.strftime("%B"), "season": season, "festival": festival,
    })
except Exception:
    preview_crowd = None

preview_climate = None
try:
    preview_climate = api_post("/predict/climate", {"district": selected_district, "target_date": start_date.isoformat()})
except Exception:
    preview_climate = None

# ---------------------------------------------------------------------------
# Selected Destination — popularity/category/entry fee + amenities.
# (The interactive route map — Nominatim/OSRM/Folium — lives on the
# Predictions page's Navigator Map tab once a trip is generated, not here;
# keeping this page to a fast, focused input form.)
# ---------------------------------------------------------------------------
st.write("")
with st.container(border=True):
        st.markdown(
            '<span class="icon-badge">📍</span>'
            '<span style="font-family:\'Playfair Display\',Georgia,serif; font-weight:700; '
            'font-size:1.25rem; vertical-align:middle;">Selected Destination</span>'
            f'<span style="float:right; color:{TEXT_MUTED}; font-size:0.85rem; margin-top:0.4rem;">'
            f'updates live as you change the form above</span>',
            unsafe_allow_html=True,
        )
        spots_line = selected_spot if len(selected_spots) == 1 else (
            f"{selected_spot} <span style='color:{TEXT_MUTED};'>(primary)</span> + "
            f"{len(selected_spots) - 1} more"
        )

        POPULARITY_COLOR = {"Emerging": TEXT_MUTED, "Popular": ACCENT_SOFT, "Very Popular": ACCENT}
        if spot_info.get("available"):
            pop_label = spot_info["popularity_label"]
            pop_color = POPULARITY_COLOR.get(pop_label, TEXT_MUTED)
            pop_chip_parts = [
                f'<span class="chip" style="border-color:{pop_color}66; color:{pop_color}; '
                f'font-weight:600;">⭐ {pop_label} ({spot_info["popularity"]})</span>'
            ]
            if spot_info.get("category"):
                pop_chip_parts.append(f'<span class="chip">🏷️ {spot_info["category"]}</span>')
            if spot_info.get("entry_fee"):
                pop_chip_parts.append(f'<span class="chip">🎫 ₹{spot_info["entry_fee"]:,.0f} entry</span>')
            popularity_line = f'<div style="margin-top:0.5rem;">{"".join(pop_chip_parts)}</div>'
        else:
            popularity_line = (
                f'<div style="margin-top:0.5rem; color:{TEXT_MUTED}; font-size:0.85rem;">'
                f'Popularity not on record for this spot.</div>'
            )

        # Wide card spans the full page, with destination details and amenities side by side.
        detail_col, amenity_col = st.columns([0.6, 0.4])
        with detail_col:
            st.markdown(
                f'<div><b>District:</b> {selected_district}<br>'
                f'<b>Spot(s):</b> {spots_line}<br>'
                f'<b>Travel window:</b> {start_date} to {end_date} ({duration_days} day(s))'
                f'{popularity_line}</div>',
                unsafe_allow_html=True,
            )
            if visit_order and visit_order.get("improved"):
                order_str = " → ".join(visit_order["order"])
                st.caption(f"🧭 Shorter visiting order available: **{order_str}** "
                           f"(saves {visit_order['savings_km']:,.1f} km)")
        with amenity_col:
            st.markdown(
                '<span class="icon-badge" style="width:1.9rem; height:1.9rem; font-size:0.95rem;">🔔</span>'
                '<span style="font-weight:700; vertical-align:middle;">Amenities</span>',
                unsafe_allow_html=True,
            )
            am = api_get(f"/amenities/{selected_spot}")
            if am["available"]:
                st.markdown("".join(f'<span class="chip">{a}</span>' for a in am["amenities"]), unsafe_allow_html=True)
            else:
                st.caption("Amenities data isn't available for this spot yet.")

st.write("")

# ---------------------------------------------------------------------------
# Smart Insights — a live preview strip using the same models the full
# "Generate My Trip Plan" flow calls, so the person gets a feel for the
# trip's shape before committing to the full multi-page flow.
# ---------------------------------------------------------------------------
with st.container(border=True):
    st.markdown("#### ✨ Smart Insights")
    st.caption(f"AI-powered recommendations for **{selected_spot}**, {selected_district} · "
               f"updates the moment you change the destination above")
    i1, i2, i3, i4 = st.columns(4)
    with i1:
        st.markdown(f"""<div class="hero-stat"><div class="icon">🕒</div>
        <div class="label">Best Time to Visit</div>
        <div class="value" style="font-size:1.15rem; color:{ACCENT};">Oct – Feb</div>
        <div class="sub">Winter &amp; festival season — coolest, most events</div></div>""",
                    unsafe_allow_html=True)
    with i2:
        if preview_crowd:
            st.markdown(f"""<div class="hero-stat"><div class="icon">👥</div>
            <div class="label">Crowd Prediction</div>
            <div class="value" style="font-size:1.15rem; color:{GOOD};">{preview_crowd['crowd_level']}</div>
            <div class="sub">{preview_crowd['predicted_visitors']:,.0f} expected visitors</div></div>""",
                        unsafe_allow_html=True)
        else:
            st.markdown("""<div class="hero-stat"><div class="icon">👥</div>
            <div class="label">Crowd Prediction</div><div class="sub">Unavailable right now</div></div>""",
                        unsafe_allow_html=True)
    with i3:
        if preview_climate:
            st.markdown(f"""<div class="hero-stat"><div class="icon">🌦️</div>
            <div class="label">Weather Outlook</div>
            <div class="value" style="font-size:1.15rem; color:{ACCENT_SOFT};">
            {preview_climate['predicted_min_temp']:.0f}°C – {preview_climate['predicted_max_temp']:.0f}°C</div>
            <div class="sub">{preview_climate['rain_chance_percent']:.0f}% chance of rain</div></div>""",
                        unsafe_allow_html=True)
        else:
            st.markdown("""<div class="hero-stat"><div class="icon">🌦️</div>
            <div class="label">Weather Outlook</div><div class="sub">Unavailable right now</div></div>""",
                        unsafe_allow_html=True)
    with i4:
        if preview_cost:
            st.markdown(f"""<div class="hero-stat"><div class="icon">💰</div>
            <div class="label">Budget Estimate</div>
            <div class="value" style="font-size:1.15rem; color:{GOOD};">
            ₹{preview_cost['total_estimated_cost']:,.0f}</div>
            <div class="sub">for {num_travelers} traveler(s)</div></div>""", unsafe_allow_html=True)
        else:
            st.markdown("""<div class="hero-stat"><div class="icon">💰</div>
            <div class="label">Budget Estimate</div><div class="sub">Unavailable right now</div></div>""",
                        unsafe_allow_html=True)

generate_predictions = generate_predictions or st.session_state.pop("_generate_for_selected_dates", False)

if generate_predictions:
    payload = {
        "district": selected_district, "spot_name": selected_spot, "category": category,
        "target_date": start_date.isoformat(), "end_date": end_date.isoformat(), "duration_days": duration_days,
        "num_travelers": num_travelers, "route_distance_km": effective_route_distance_km,
        "transport_mode": transport_mode, "accommodation_tier": accommodation_tier,
        "season": season, "festival": festival, "user_budget": user_budget,
        "spot_names": selected_spots,
    }
    st.session_state["trip_context"] = {
        "payload": payload,
        "display": {
            "selected_spot": selected_spot, "selected_district": selected_district,
            "start_date": start_date, "end_date": end_date, "duration_days": duration_days,
            "num_travelers": num_travelers, "transport_mode": transport_mode,
            "accommodation_tier": accommodation_tier, "user_budget": user_budget,
            "num_spots": len(selected_spots), "selected_spots": selected_spots,
        },
    }
    st.session_state.pop("trip_result_cache_key", None)
    st.session_state.app_view = "results"
    st.rerun()