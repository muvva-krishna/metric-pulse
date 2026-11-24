"""Central configuration for MetricPulse."""

from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DBT_PROJECT_DIR = ROOT_DIR / "dbt_project"
DB_PATH = ROOT_DIR / "metricpulse.duckdb"
MANIFEST_PATH = DBT_PROJECT_DIR / "target" / "manifest.json"

# Deterministic reference "now" matching the seeded dataset's latest timestamp
REF_NOW = datetime(2026, 11, 24, 18, 0, 0)

# Triage thresholds
DEFAULT_FRESHNESS_SLA_HOURS = 4.0
ROW_VOLUME_Z_THRESHOLD = -2.5
NULL_RATE_SPIKE_THRESHOLD = 0.15
NULL_RATE_ABS_THRESHOLD = 0.20

# EXPLAIN cost guard threshold (estimated cardinality)
MAX_ESTIMATED_ROWS = 5_000_000
