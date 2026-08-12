"""
config.py — loads Supabase credentials from a .env file if present.

Supabase logging is entirely optional. If SUPABASE_URL / SUPABASE_KEY aren't
set, database.py falls back to writing predictions to a local CSV
(App/predictions_log.csv) instead — the app works either way.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Resolved relative to this file, not the current working directory — a
# bare load_dotenv() only checks the CWD (and its parents), so whether
# these credentials were found depended entirely on which folder the
# backend happened to be launched from. This project's .env lives at
# Tourism Project/.env, i.e. one level up from this file
# (database/config.py -> Tourism Project/) — same root predict.py already
# loads SUPABASE_DB_URL from, so both credential sets now come from the
# one place regardless of launch directory.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")
# Back-compat: also pick up database/.env if someone created one alongside
# this file directly instead of at the project root.
load_dotenv(Path(__file__).resolve().parent / ".env", override=False)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")