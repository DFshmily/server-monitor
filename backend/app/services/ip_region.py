"""IP 归属地查询（ip2region 离线 xdb 库，无外部 API 依赖）。

xdb 文件: /var/lib/server-monitor/ip2region.xdb（约 300KB，来自 ip2region 官方仓库）
"""
import io
import logging
import os
import threading

from app.services.ip2region import util as ip2_util
from app.services.ip2region import searcher as ip2_searcher

logger = logging.getLogger(__name__)

XDB_PATH = os.environ.get("MONITOR_IP2REGION_DB", "/var/lib/server-monitor/ip2region.xdb")

_searcher = None
_lock = threading.Lock()


def _get_searcher():
    global _searcher
    if _searcher is None:
        with _lock:
            if _searcher is None:
                try:
                    if not os.path.exists(XDB_PATH):
                        logger.warning("ip2region.xdb 不存在: %s", XDB_PATH)
                        _searcher = False
                        return None
                    with io.open(XDB_PATH, "rb") as handle:
                        header = ip2_util.load_header(handle)
                        version = ip2_util.version_from_header(header)
                        c_buffer = ip2_util.load_content(handle)
                    if version is None:
                        raise ValueError("无法识别 xdb 版本")
                    _searcher = ip2_searcher.new_with_buffer(version, c_buffer)
                except Exception as e:
                    logger.warning("ip2region 初始化失败: %s", e)
                    _searcher = False
    return _searcher or None


def lookup(ip: str) -> str:
    """返回 IP 归属地（如 '日本|大阪' / '中国|广东省|深圳市'），本机或未知返回空。"""
    if not ip or ip in ("127.0.0.1", "::1", "localhost", "unknown"):
        return ""
    s = _get_searcher()
    if not s:
        return ""
    try:
        region = s.search(ip) or ""
        parts = [p.strip() for p in region.split("|") if p.strip() and p.strip() != "0"]
        if not parts:
            return ""
        # 去掉运营商段（电信/联通/移动/铁通/教育网 等）
        if parts[-1] in ("电信", "联通", "移动", "铁通", "教育网", "长城宽带"):
            parts = parts[:-1]
        # 国家可能为 "中国" 或 "日本" 等；省/市可能缺失
        return "|".join(parts[:4])
    except Exception:
        return ""
