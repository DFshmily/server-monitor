"""Application configuration."""
import os

# Server
HOST = os.environ.get("MONITOR_HOST", "0.0.0.0")
PORT = int(os.environ.get("MONITOR_PORT", "8000"))

# Database
DB_PATH = os.environ.get("MONITOR_DB", "/var/lib/server-monitor/data.db")

# Auth
API_KEY = os.environ.get("MONITOR_API_KEY", "default-key")

# Data retention (days)
RETENTION_REALTIME = 1      # 2s data: keep 1 day
RETENTION_1MIN = 7          # 1min averages: keep 7 days
RETENTION_5MIN = 30         # 5min averages: keep 30 days
RETENTION_1H = 180          # 1h averages: keep 180 days
RETENTION_1D = 730          # 1d averages: keep 2 years

# Aggregation intervals (seconds)
INTERVALS = {
    "realtime": 2,
    "1min": 60,
    "5min": 300,
    "1h": 3600,
    "1d": 86400,
}
