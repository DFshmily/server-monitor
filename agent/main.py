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

# HTTP 客户端: 优先 curl_cffi(Chrome TLS 指纹) 规避 Cloudflare 机器人检测对
# Python 请求的拦截/延迟; 未安装时回退到 requests.
# 注意: impersonate 会强制 HTTP/2, 直连 uvicorn(http://) 时会吞掉请求体,
# 所以只有走 https(经 Cloudflare/Nginx) 时才启用 impersonate。
try:
    from curl_cffi import requests as http_client
    HAS_CURL_CFFI = True
except ImportError:
    import requests as http_client
    HAS_CURL_CFFI = False

from collector import collect_all, set_custom_config

# Configuration from environment or defaults
BACKEND_URL = os.environ.get("MONITOR_BACKEND_URL", "http://localhost:8000")
PUSH_INTERVAL = int(os.environ.get("MONITOR_INTERVAL", "2"))  # seconds
SERVER_NAME = os.environ.get("MONITOR_SERVER_NAME", "")
API_KEY = os.environ.get("MONITOR_API_KEY", "default-key")
MAX_RETRIES = 3
RETRY_DELAY = 5
PUSH_TIMEOUT = int(os.environ.get("MONITOR_PUSH_TIMEOUT", "20"))  # 秒; 经 Cloudflare 推送偶发 >10s

# ── 直连源站(绕过 Cloudflare)可选 ──
# 国内→Cloudflare 推送大 payload 偶发 3-30s 卡顿/超时, 直连源站稳定在 ~0.5s。
# MONITOR_ORIGIN_URL 指向源站地址(如 https://<源站IP>), 同时配:
#   MONITOR_PUSH_HOST   = 源站域名(用于 Nginx Host 路由, 如 dashboard.dfshmily.icu)
#   MONITOR_PUSH_VERIFY = 0 关闭 TLS 校验(源站证书为 Cloudflare 源证书, 不在公共信任链)
# 注意: 源站 IP 属敏感配置, 用 systemd drop-in 覆盖, 不要写进公开仓库。
ORIGIN_URL = os.environ.get("MONITOR_ORIGIN_URL", "").rstrip("/")
PUSH_HOST = os.environ.get("MONITOR_PUSH_HOST", "")
PUSH_VERIFY = os.environ.get("MONITOR_PUSH_VERIFY", "1") != "0"

# 仅 https(经 Cloudflare 或直连源站) 时启用 Chrome 指纹伪装
HTTP_KW: dict = {"impersonate": "chrome"} if HAS_CURL_CFFI and (BACKEND_URL.startswith("https") or ORIGIN_URL.startswith("https")) else {}

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
    """POST metrics to backend API (via Cloudflare 域名 或 直连源站)."""
    base = ORIGIN_URL or BACKEND_URL
    url = f"{base}/api/agent/metrics"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    kw = dict(HTTP_KW)
    if ORIGIN_URL:
        # 直连源站: Nginx 按 Host 路由, 源站证书不在公共信任链需关校验
        headers["Host"] = PUSH_HOST or "dashboard.dfshmily.icu"
        kw["verify"] = PUSH_VERIFY
    payload = {
        "server_name": SERVER_NAME or data.get("hostname", "unknown"),
        "metrics": data,
    }

    for attempt in range(MAX_RETRIES):
        try:
            # 注意: curl_cffi 某些构建下 json= 参数会发空 body, 统一用 data= 显式序列化
            resp = http_client.post(url, data=json.dumps(payload).encode(), headers=headers, timeout=PUSH_TIMEOUT, **kw)  # type: ignore[arg-type]
            if resp.status_code == 200:
                return True
            elif resp.status_code == 401:
                logger.error("Authentication failed. Check MONITOR_API_KEY.")
                return False
            else:
                logger.warning(f"Push failed ({resp.status_code}): {resp.text}")
        except http_client.exceptions.ConnectionError:
            logger.warning(f"Connection failed (attempt {attempt + 1}/{MAX_RETRIES})")
        except http_client.exceptions.Timeout:
            logger.warning(f"Timeout (attempt {attempt + 1}/{MAX_RETRIES})")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")

        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_DELAY)

    return False


# 自定义监控命令配置：定期从后端拉取（管理页配置），失败静默保留旧配置
CUSTOM_CONFIG_REFRESH = 60  # 秒
_last_custom_fetch = 0.0


def fetch_custom_config() -> None:
    """拉取本服务器在管理页配置的自定义监控命令，注入 collector。"""
    global _last_custom_fetch
    if time.time() - _last_custom_fetch < CUSTOM_CONFIG_REFRESH:
        return
    _last_custom_fetch = time.time()
    try:
        base = ORIGIN_URL or BACKEND_URL
        url = f"{base}/api/agent/custom-config?server_name={SERVER_NAME or 'unknown'}"
        headers = {"Authorization": f"Bearer {API_KEY}"}
        kw = dict(HTTP_KW)
        if ORIGIN_URL:
            headers["Host"] = PUSH_HOST or "dashboard.dfshmily.icu"
            kw["verify"] = PUSH_VERIFY
        resp = http_client.get(url, headers=headers, timeout=10, **kw)
        if resp.status_code == 200:
            items = resp.json()  # [{name, cmd, interval, unit, timeout}]
            cfg = {}
            for it in items:
                cfg[it.get("name")] = {
                    "cmd": it.get("cmd", ""),
                    "interval": it.get("interval", 60),
                    "unit": it.get("unit", ""),
                    "timeout": it.get("timeout", 5),
                }
            set_custom_config(cfg)
        else:
            logger.warning(f"custom-config fetch failed ({resp.status_code})")
    except Exception as e:
        logger.warning(f"custom-config fetch error: {e}")


def main():
    logger.info(f"Agent starting...")
    logger.info(f"  Backend: {BACKEND_URL}{' (直连源站: ' + ORIGIN_URL + ')' if ORIGIN_URL else ''}")
    logger.info(f"  Server:  {SERVER_NAME or '(auto-detect)'}")
    logger.info(f"  Interval: {PUSH_INTERVAL}s")
    logger.info(f"  HTTP 客户端: {'curl_cffi' + (' (Chrome 指纹)' if HTTP_KW else ' (无伪装)') if HAS_CURL_CFFI else 'requests'}")

    # Initial CPU measurement (first read is always 0)
    collect_all()
    time.sleep(1)

    consecutive_failures = 0
    while running:
        start = time.time()

        try:
            fetch_custom_config()  # 内部节流 60s
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
