#!/usr/bin/env python3
"""
Server Monitor Agent
Lightweight agent that collects system metrics and pushes to the dashboard backend.
"""
import os
import sys
import time
import json
import logging
import signal
import requests
from collector import collect_all

# Configuration from environment or defaults
BACKEND_URL = os.environ.get("MONITOR_BACKEND_URL", "http://localhost:8000")
PUSH_INTERVAL = int(os.environ.get("MONITOR_INTERVAL", "2"))  # seconds
SERVER_NAME = os.environ.get("MONITOR_SERVER_NAME", "")
API_KEY = os.environ.get("MONITOR_API_KEY", "default-key")
MAX_RETRIES = 3
RETRY_DELAY = 5

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("monitor-agent")

running = True


def signal_handler(sig, frame):
    global running
    logger.info("Shutting down agent...")
    running = False


signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


def push_metrics(data: dict) -> bool:
    """POST metrics to backend API."""
    url = f"{BACKEND_URL}/api/agent/metrics"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "server_name": SERVER_NAME or data.get("hostname", "unknown"),
        "metrics": data,
    }

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
            if resp.status_code == 200:
                return True
            elif resp.status_code == 401:
                logger.error("Authentication failed. Check MONITOR_API_KEY.")
                return False
            else:
                logger.warning(f"Push failed ({resp.status_code}): {resp.text}")
        except requests.exceptions.ConnectionError:
            logger.warning(f"Connection failed (attempt {attempt + 1}/{MAX_RETRIES})")
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout (attempt {attempt + 1}/{MAX_RETRIES})")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")

        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_DELAY)

    return False


def main():
    logger.info(f"Agent starting...")
    logger.info(f"  Backend: {BACKEND_URL}")
    logger.info(f"  Server:  {SERVER_NAME or '(auto-detect)'}")
    logger.info(f"  Interval: {PUSH_INTERVAL}s")

    # Initial CPU measurement (first read is always 0)
    collect_all()
    time.sleep(1)

    consecutive_failures = 0
    while running:
        start = time.time()

        try:
            data = collect_all()
            success = push_metrics(data)

            if success:
                if consecutive_failures > 0:
                    logger.info(f"Reconnected after {consecutive_failures} failures")
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                if consecutive_failures >= 10:
                    logger.error(f"Failed {consecutive_failures} consecutive times, backing off...")
                    time.sleep(30)
                    continue

        except Exception as e:
            logger.error(f"Collection error: {e}")
            consecutive_failures += 1

        # Maintain consistent interval
        elapsed = time.time() - start
        sleep_time = max(0, PUSH_INTERVAL - elapsed)
        if sleep_time > 0:
            time.sleep(sleep_time)

    logger.info("Agent stopped.")


if __name__ == "__main__":
    main()
