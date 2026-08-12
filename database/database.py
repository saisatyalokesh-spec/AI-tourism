"""
database.py — logs every prediction (inputs + outputs + timestamp).

If SUPABASE_URL/SUPABASE_KEY are configured (see config.py / .env.example),
each prediction is inserted into a Supabase table called "trip_predictions".
Create that table in your Supabase project with columns matching the keys
passed to log_prediction() below (timestamp, district, spot_name,
prediction_type, inputs, result) — "inputs" and "result" can be plain text
(JSON-encoded) columns.

Whether or not Supabase is configured, every prediction is ALSO appended to
a local text log at App/predictions_log.txt, so there's always a record of
what was predicted and how — this is the "text file for which predictions
are made" — even with zero setup.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from database.config import SUPABASE_KEY, SUPABASE_URL

LOG_PATH = Path(__file__).resolve().parent.parent / "App" / "predictions_log.txt"

_supabase_client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        from supabase import create_client
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:  # pragma: no cover - optional dependency
        print(f"[database] Supabase not available, logging to file only: {e}")
        _supabase_client = None


def log_prediction(prediction_type: str, district: str, spot_name: str,
                    inputs: Dict[str, Any], result: Dict[str, Any]) -> None:
    """Records one prediction. Never raises — a logging failure should never
    break a prediction request."""
    timestamp = datetime.now(timezone.utc).isoformat()

    # Always write to the local text log.
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(
                f"[{timestamp}] {prediction_type} | district={district} | spot={spot_name}\n"
                f"    inputs: {json.dumps(inputs, default=str)}\n"
                f"    result: {json.dumps(result, default=str)}\n\n"
            )
    except Exception as e:  # pragma: no cover
        print(f"[database] Could not write local log: {e}")

    # Optionally also push to Supabase.
    if _supabase_client is not None:
        try:
            _supabase_client.table("trip_predictions").insert({
                "timestamp": timestamp,
                "prediction_type": prediction_type,
                "district": district,
                "spot_name": spot_name,
                "inputs": json.dumps(inputs, default=str),
                "result": json.dumps(result, default=str),
            }).execute()
        except Exception as e:  # pragma: no cover
            print(f"[database] Supabase insert failed, local log still has it: {e}")