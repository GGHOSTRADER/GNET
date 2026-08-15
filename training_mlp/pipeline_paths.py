"""
pipeline_paths.py
-----------------
Single source of truth for all folder and file paths used across the pipeline.

Priority: explicit env var override > derived from STRATEGY_NAME.

Import this at the top of every pipeline script:
    from pipeline_paths import INPUTS_DIR, PROCESSED_DIR, MODEL_DIR, REPORTS_DIR, ...
"""

from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv(Path(__file__).parent / ".env")

STRATEGY_NAME = os.getenv("STRATEGY_NAME", "MA2CrossLE")
MODEL_NAME    = os.getenv("MODEL_NAME",    "mlp_baseline")

_STRATEGY_DIR = Path("strategies") / STRATEGY_NAME

def _resolve(env_key: str, default: Path) -> Path:
    val = os.getenv(env_key, "").strip()
    return Path(val) if val else default

INPUTS_DIR    = _resolve("INPUTS_DIR",    _STRATEGY_DIR / "inputs")
PROCESSED_DIR = _resolve("PROCESSED_DIR", _STRATEGY_DIR / "processed")
MODEL_DIR     = _resolve("MODEL_DIR",     _STRATEGY_DIR / "model" / MODEL_NAME)
REPORTS_DIR   = _resolve("REPORTS_DIR",   _STRATEGY_DIR / "reports")

# ── Derived file paths ────────────────────────────────────────────────────────
TRADES_FILE   = INPUTS_DIR    / os.getenv("TRADES_FILE", "trades_30.csv")
BARS_FILE     = INPUTS_DIR    / os.getenv("BARS_FILE",   "data_30.txt")
FEATURES_FILE = PROCESSED_DIR / "df_features_labeled.csv"
ENRICHED_FILE = PROCESSED_DIR / "df_enriched.csv"
