"""Application configuration."""
import os

# Server
HOST = os.environ.get("MONITOR_HOST", "0.0.0.0")
PORT = int(os.environ.get("MONITOR_PORT", "8000"))

# Database
DB_PATH = os.environ.get("MONITOR_DB", "/var/lib/server-monitor/data.db")

# Auth
API_KEY = os.environ.get("MONITOR_API_KEY", "default-key")

# JWT (fallback: derive from API_KEY so it stays stable across restarts)
JWT_SECRET = os.environ.get("MONITOR_JWT_SECRET", f"jwt-{API_KEY}-salt-2026")
JWT_EXPIRE_SECONDS = int(os.environ.get("MONITOR_JWT_EXPIRE", "86400"))  # 24h default

# Alerts: Telegram push (optional; alerts work silently without it)
TELEGRAM_TOKEN = os.environ.get("MONITOR_TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("MONITOR_TELEGRAM_CHAT_ID", "")

# Alerts: Bark push (iOS). Key = the 30-char device key from the Bark app
# (https://api.day.app/XXXX...). Optional; when set, alerts also go to Bark.
BARK_KEY = os.environ.get("MONITOR_BARK_KEY", "")
BARK_GROUP = os.environ.get("MONITOR_BARK_GROUP", "")      # optional push group
BARK_DEVICE = os.environ.get("MONITOR_BARK_DEVICE", "")    # optional device token (rarely needed)

# Alerts: Server酱 (WeChat push via sctapi.ftqq.com). Optional.
SERVERCHAN_KEY = os.environ.get("MONITOR_SERVERCHAN_KEY", "")

# Alerts: 企业微信 / 钉钉 group-bot webhooks. Optional.
WECOM_WEBHOOK = os.environ.get("MONITOR_WECOM_WEBHOOK", "")
DINGTALK_WEBHOOK = os.environ.get("MONITOR_DINGTALK_WEBHOOK", "")

# Monthly traffic quota for traffic_used_percent alerts (GiB per server).
# Oracle free tier e.g. 10 TiB outbound = 10240 GiB. 0 = disable quota check.
TRAFFIC_QUOTA_GB = float(os.environ.get("MONITOR_TRAFFIC_QUOTA_GB", "0"))

# SMTP for email verification codes
SMTP_HOST = os.environ.get("MONITOR_SMTP_HOST", "smtp.qq.com")
SMTP_PORT = int(os.environ.get("MONITOR_SMTP_PORT", "465"))
SMTP_USER = os.environ.get("MONITOR_SMTP_USER", "")       # sender email, e.g. xxx@qq.com
SMTP_PASS = os.environ.get("MONITOR_SMTP_PASS", "")       # SMTP authorization code
SMTP_FROM = os.environ.get("MONITOR_SMTP_FROM", SMTP_USER)  # From header (defaults to user)

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
