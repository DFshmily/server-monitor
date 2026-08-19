"""Server metrics collector using psutil + docker."""
import os
import json
import re
import subprocess
import time
import socket
import ssl
import psutil

# Network rate tracking state
_prev_net_io = None
_prev_net_time = 0.0

# Persistent lifetime traffic state file (survives reboots)
TRAFFIC_STATE_FILE = os.environ.get(
    "MONITOR_TRAFFIC_STATE", "/var/lib/server-monitor/traffic_state.json"
)

# TLS cert check cache: don't handshake on every 2s collection
CERT_REFRESH_SECONDS = 6 * 3600  # refresh every 6h
_cert_cache: dict = {}

# Docker stats cache: docker stats API 慢(1-2s), 30s 刷新一次即可
DOCKER_REFRESH_SECONDS = 30
_docker_cache: dict = {"at": 0.0, "data": None}

# Monthly traffic quota (GiB) for THIS server; 0/absent = 不监控额度百分比.
# 每台服务器独立配置(环境变量), 规则阈值可在面板按服务器定制.
TRAFFIC_QUOTA_GB = float(os.environ.get("MONITOR_TRAFFIC_QUOTA_GB", "0"))

# 月度结算时区, 按厂商账单口径独立配置:
#   MONITOR_TRAFFIC_TZ=utc       -> UTC 月结 (对齐 Oracle 云账单)
#   MONITOR_TRAFFIC_TZ=shanghai  -> 北京时间月结 (对齐腾讯云/国内厂商, 默认)
TRAFFIC_TZ = os.environ.get("MONITOR_TRAFFIC_TZ", "").strip().lower()

# 虚拟网卡不计入流量统计: docker 桥接/veth/隧道会把同一份流量重复计数,
# 云厂商计费只认物理网卡。前缀匹配, lo 恒排除。
VIRTUAL_IFACE_PREFIXES = ("docker", "veth", "br-", "virbr", "tun", "tap", "wg", "tailscale", "kube")


def _month_key() -> str:
    """自然月标识, 按本机配置的结算时区计算, 跨月自动重置."""
    import datetime
    if TRAFFIC_TZ == "utc":
        tz = datetime.timezone.utc
    else:
        tz = datetime.timezone(datetime.timedelta(hours=8))  # 默认北京时间
    return datetime.datetime.now(tz).strftime("%Y-%m")


def _load_traffic_state() -> dict:
    """Load persisted traffic totals; return empty state if missing/corrupt."""
    try:
        with open(TRAFFIC_STATE_FILE, "r") as f:
            state = json.load(f)
        if isinstance(state, dict):
            return state
    except Exception:
        pass
    return {}


def _save_traffic_state(state: dict) -> None:
    """Persist traffic totals so they survive reboots."""
    try:
        os.makedirs(os.path.dirname(TRAFFIC_STATE_FILE), exist_ok=True)
        tmp = TRAFFIC_STATE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f)
        os.replace(tmp, TRAFFIC_STATE_FILE)
    except Exception:
        pass


def get_cpu_metrics() -> dict:
    """CPU metrics: overall + per-core + iowait + steal."""
    cpu_percent = psutil.cpu_percent(interval=0)
    per_cpu = psutil.cpu_percent(interval=0, percpu=True)
    cpu_times = psutil.cpu_times_percent(interval=0)
    cpu_freq = psutil.cpu_freq()

    return {
        "percent": round(cpu_percent, 2),
        "per_cpu": [round(c, 2) for c in per_cpu],
        "iowait": round(getattr(cpu_times, 'iowait', 0), 2),
        "steal": round(getattr(cpu_times, 'steal', 0), 2),
        "user": round(getattr(cpu_times, 'user', 0), 2),
        "system": round(getattr(cpu_times, 'system', 0), 2),
        "idle": round(getattr(cpu_times, 'idle', 0), 2),
        "cores": psutil.cpu_count(logical=True),
        "physical_cores": psutil.cpu_count(logical=False),
        "freq_current": round(cpu_freq.current, 0) if cpu_freq else 0,
        "freq_max": round(cpu_freq.max, 0) if cpu_freq else 0,
    }


def get_memory_metrics() -> dict:
    """Memory + swap metrics."""
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()

    return {
        "total": mem.total,
        "used": mem.used,
        "available": mem.available,
        "cached": getattr(mem, 'cached', 0),
        "buffers": getattr(mem, 'buffers', 0),
        "shared": getattr(mem, 'shared', 0),
        "percent": round(mem.percent, 2),
        "swap_total": swap.total,
        "swap_used": swap.used,
        "swap_percent": round(swap.percent, 2),
    }


def get_disk_metrics() -> dict:
    """Disk usage per partition + I/O stats."""
    partitions = []
    for p in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(p.mountpoint)
            partitions.append({
                "device": p.device,
                "mountpoint": p.mountpoint,
                "fstype": p.fstype,
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
                "percent": round(usage.percent, 2),
            })
        except (PermissionError, OSError):
            continue

    io = psutil.disk_io_counters()
    io_stats = {}
    if io:
        per_disk = psutil.disk_io_counters(perdisk=True)
        for name, counters in per_disk.items():
            io_stats[name] = {
                "read_bytes": counters.read_bytes,
                "write_bytes": counters.write_bytes,
                "read_count": counters.read_count,
                "write_count": counters.write_count,
                "read_time": counters.read_time,
                "write_time": counters.write_time,
            }

    return {
        "partitions": partitions,
        "io": {
            "read_bytes": io.read_bytes if io else 0,
            "write_bytes": io.write_bytes if io else 0,
            "read_count": io.read_count if io else 0,
            "write_count": io.write_count if io else 0,
        },
        "io_per_disk": io_stats,
    }


def get_network_metrics() -> dict:
    """Network I/O per interface + connections + rates + persistent totals."""
    global _prev_net_io, _prev_net_time
    io = psutil.net_io_counters(pernic=True)

    def is_counted(name: str) -> bool:
        if name == 'lo':
            return False
        return not name.startswith(VIRTUAL_IFACE_PREFIXES)

    interfaces = {}
    for name, counters in io.items():
        if not is_counted(name):
            continue
        interfaces[name] = {
            "bytes_sent": counters.bytes_sent,
            "bytes_recv": counters.bytes_recv,
            "packets_sent": counters.packets_sent,
            "packets_recv": counters.packets_recv,
            "errin": counters.errin,
            "errout": counters.errout,
            "dropin": counters.dropin,
            "dropout": counters.dropout,
        }

    # Calculate rates between samples
    now = time.time()
    rates = {}
    total_recv_rate = 0
    total_sent_rate = 0
    if _prev_net_io:
        dt = now - _prev_net_time
        if dt > 0:
            for name, cur in interfaces.items():
                prev = _prev_net_io.get(name)
                if prev:
                    recv_rate = max(0, (cur["bytes_recv"] - prev["bytes_recv"]) / dt)
                    sent_rate = max(0, (cur["bytes_sent"] - prev["bytes_sent"]) / dt)
                    rates[name] = {
                        "recv_rate": round(recv_rate, 2),
                        "sent_rate": round(sent_rate, 2),
                    }
                    total_recv_rate += recv_rate
                    total_sent_rate += sent_rate
    _prev_net_io = interfaces
    _prev_net_time = now

    # --- Persistent lifetime traffic totals (survive reboots) ---
    # System counters reset on reboot, so we accumulate deltas into a
    # persistent file.  total_lifetime_recv/sent keep counting forever.
    boot_time = psutil.boot_time()
    current_recv = sum(v["bytes_recv"] for v in interfaces.values())
    current_sent = sum(v["bytes_sent"] for v in interfaces.values())

    state = _load_traffic_state()
    if state.get("boot_time") != boot_time:
        # 首次运行或系统重启：lifetime 以当前计数器为起点（保证 >= 本机流量），
        # 重启时保留旧 lifetime 值；月度流量同样跨重启保留
        state = {
            "boot_time": boot_time,
            "base_recv": current_recv,
            "base_sent": current_sent,
            "lifetime_recv": max(state.get("lifetime_recv", 0), current_recv),
            "lifetime_sent": max(state.get("lifetime_sent", 0), current_sent),
            "month": state.get("month", _month_key()),
            "month_recv": state.get("month_recv", 0),
            "month_sent": state.get("month_sent", 0),
            "month_base_recv": state.get("month_base_recv", current_recv),
            "month_base_sent": state.get("month_base_sent", current_sent),
        }
        delta_recv = 0
        delta_sent = 0
    else:
        # 同一次启动内：delta = 当前计数器 - 上次采样计数器
        delta_recv = max(0, current_recv - state.get("base_recv", current_recv))
        delta_sent = max(0, current_sent - state.get("base_sent", current_sent))

    lifetime_recv = state.get("lifetime_recv", 0) + delta_recv
    lifetime_sent = state.get("lifetime_sent", 0) + delta_sent

    # ── 月度流量累计（北京时间自然月，跨月自动重置，跨重启保留）──
    month = _month_key()
    if state.get("month") != month:
        state["month"] = month
        state["month_recv"] = 0
        state["month_sent"] = 0
        state["month_base_recv"] = current_recv
        state["month_base_sent"] = current_sent
    month_delta_recv = max(0, current_recv - state.get("month_base_recv", current_recv))
    month_delta_sent = max(0, current_sent - state.get("month_base_sent", current_sent))
    month_recv = state.get("month_recv", 0) + month_delta_recv
    month_sent = state.get("month_sent", 0) + month_delta_sent

    # Rebase so the next delta is measured from the current counter
    state["base_recv"] = current_recv
    state["base_sent"] = current_sent
    state["lifetime_recv"] = lifetime_recv
    state["lifetime_sent"] = lifetime_sent
    state["month_base_recv"] = current_recv
    state["month_base_sent"] = current_sent
    state["month_recv"] = month_recv
    state["month_sent"] = month_sent
    _save_traffic_state(state)

    # Current boot session totals (raw system counters, reset on reboot)
    total_bytes_recv = current_recv
    total_bytes_sent = current_sent

    connections = psutil.net_connections(kind='inet')
    tcp_states = {}
    for conn in connections:
        if conn.type == socket.SOCK_STREAM:
            st = conn.status
            tcp_states[st] = tcp_states.get(st, 0) + 1

    return {
        "interfaces": interfaces,
        "rates": rates,
        "total_recv_rate": round(total_recv_rate, 2),
        "total_sent_rate": round(total_sent_rate, 2),
        "total_bytes_recv": total_bytes_recv,
        "total_bytes_sent": total_bytes_sent,
        "lifetime_bytes_recv": lifetime_recv,
        "lifetime_bytes_sent": lifetime_sent,
        "tcp_states": tcp_states,
        "total_connections": len(connections),
        "traffic_month": {
            "month": month,
            "tz": "UTC" if TRAFFIC_TZ == "utc" else "Asia/Shanghai",
            "recv_bytes": month_recv,
            "sent_bytes": month_sent,
            "total_bytes": month_recv + month_sent,
            "quota_gb": TRAFFIC_QUOTA_GB,
            "used_percent": round((month_recv + month_sent) / (1024 ** 3) / TRAFFIC_QUOTA_GB * 100, 2) if TRAFFIC_QUOTA_GB > 0 else None,
        },
    }


def _check_cert(domain: str) -> dict | None:
    """TLS handshake against domain:443, return cert expiry info (or None on error)."""
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((domain, 443), timeout=5) as sock:
            with ctx.wrap_socket(sock, server_hostname=domain) as tls:
                raw_cert = tls.getpeercert()
        cert: dict = raw_cert if isinstance(raw_cert, dict) else {}
        not_after = ssl.cert_time_to_seconds(cert["notAfter"])
        issuer = dict(x[0] for x in cert.get("issuer", [])).get("organizationName", "")
        subject = dict(x[0] for x in cert.get("subject", [])).get("commonName", domain)
        return {
            "days_left": int((not_after - time.time()) / 86400),
            "expires_at": int(not_after),
            "issuer": issuer,
            "subject": subject,
        }
    except Exception as e:
        return {"days_left": None, "error": str(e)[:100]}


def get_certificates_metrics() -> dict:
    """TLS certificate expiry for MONITOR_CERT_DOMAINS (comma-separated).

    Refreshed at most every CERT_REFRESH_SECONDS to avoid handshaking on
    every 2s collection; failures keep the previous cached result.
    """
    raw = os.environ.get("MONITOR_CERT_DOMAINS", "")
    domains = [d.strip().lower() for d in raw.split(",") if d.strip()]
    if not domains:
        return {}
    now = time.time()
    out = {}
    for domain in domains:
        cache = _cert_cache.get(domain)
        if cache and now - cache[0] < CERT_REFRESH_SECONDS:
            if cache[1] is not None:
                out[domain] = cache[1]
            continue
        result = _check_cert(domain)
        _cert_cache[domain] = (now, result)
        if result is not None:
            out[domain] = result
    return out


def get_load_metrics() -> dict:
    """System load averages."""
    load1, load5, load15 = psutil.getloadavg()
    return {
        "load1": round(load1, 2),
        "load5": round(load5, 2),
        "load15": round(load15, 2),
    }


def get_process_metrics(top_n: int = 10) -> dict:
    """Top processes by CPU/memory + totals."""
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status']):
        try:
            info = proc.info
            processes.append({
                "pid": info['pid'],
                "name": info['name'],
                "cpu_percent": round(info['cpu_percent'] or 0, 2),
                "memory_percent": round(info['memory_percent'] or 0, 2),
                "status": info['status'],
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    by_cpu = sorted(processes, key=lambda p: p['cpu_percent'], reverse=True)[:top_n]
    by_mem = sorted(processes, key=lambda p: p['memory_percent'], reverse=True)[:top_n]

    return {
        "total": len(processes),
        "running": sum(1 for p in processes if p['status'] == 'running'),
        "sleeping": sum(1 for p in processes if p['status'] == 'sleeping'),
        "top_cpu": by_cpu,
        "top_memory": by_mem,
    }


def get_system_metrics() -> dict:
    """System-level metrics: uptime, context switches, interrupts, etc."""
    uptime = time.time() - psutil.boot_time()
    ctx = psutil.cpu_stats()

    return {
        "uptime_seconds": int(uptime),
        "boot_time": int(psutil.boot_time()),
        "hostname": socket.gethostname(),
        "context_switches": ctx.ctx_switches,
        "interrupts": ctx.interrupts,
        "soft_interrupts": ctx.soft_interrupts,
        "syscalls": getattr(ctx, 'syscalls', 0),
    }


def get_docker_metrics() -> dict:
    """Docker container stats (if Docker is available).

    docker stats API 较慢(1-2s), 加 30s 缓存避免拖慢每次采集。
    """
    now = time.time()
    if now - _docker_cache["at"] < DOCKER_REFRESH_SECONDS and _docker_cache["data"] is not None:
        return _docker_cache["data"]
    try:
        import docker
        client = docker.from_env()
        containers = []
        for c in client.containers.list(all=True):
            stats = {}
            if c.status == 'running':
                try:
                    raw = c.stats(stream=False)
                    # CPU
                    cpu_delta = raw['cpu_stats']['cpu_usage']['total_usage'] - \
                                raw['precpu_stats']['cpu_usage']['total_usage']
                    system_delta = raw['cpu_stats']['system_cpu_usage'] - \
                                   raw['precpu_stats']['system_cpu_usage']
                    num_cpus = raw['cpu_stats']['online_cpus']
                    cpu_percent = (cpu_delta / system_delta * num_cpus * 100) if system_delta > 0 else 0

                    # Memory
                    mem_usage = raw['memory_stats'].get('usage', 0)
                    mem_limit = raw['memory_stats'].get('limit', 0)
                    mem_percent = (mem_usage / mem_limit * 100) if mem_limit > 0 else 0

                    # Network
                    net = raw.get('networks', {})
                    net_rx = sum(v.get('rx_bytes', 0) for v in net.values())
                    net_tx = sum(v.get('tx_bytes', 0) for v in net.values())

                    stats = {
                        "cpu_percent": round(cpu_percent, 2),
                        "memory_usage": mem_usage,
                        "memory_limit": mem_limit,
                        "memory_percent": round(mem_percent, 2),
                        "net_rx": net_rx,
                        "net_tx": net_tx,
                    }
                except Exception:
                    pass

            containers.append({
                "id": c.short_id,
                "name": c.name,
                "image": str(c.image.tags[0]) if c.image.tags else str(c.image.short_id),
                "status": c.status,
                "created": int(c.attrs['Created'].timestamp()) if hasattr(c.attrs.get('Created', ''), 'timestamp') else 0,
                **stats,
            })
        result = {"containers": containers, "total": len(containers)}
        _docker_cache.update(at=now, data=result)
        return result
    except Exception:
        result = {"containers": [], "total": 0, "error": "docker_unavailable"}
        _docker_cache.update(at=now, data=result)
        return result


def get_services_metrics() -> dict:
    """Systemd service status."""
    try:
        import subprocess
        result = subprocess.run(
            ['systemctl', 'list-units', '--type=service', '--no-pager', '--no-legend', '--plain'],
            capture_output=True, text=True, timeout=10
        )
        services = []
        failed = 0
        for line in result.stdout.strip().split('\n'):
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 4:
                name = parts[0]
                load = parts[1]
                active = parts[2]
                sub = parts[3]
                if active == 'failed':
                    failed += 1
                services.append({
                    "name": name,
                    "load": load,
                    "active": active,
                    "sub": sub,
                })
        return {
            "total": len(services),
            "failed": failed,
            "running": sum(1 for s in services if s['active'] == 'active'),
            "services": services,
        }
    except Exception:
        return {"total": 0, "failed": 0, "running": 0, "services": []}


AGENT_VERSION = "1.7.0"  # bump when agent behavior changes (shown in Admin health panel)


# ── 自定义监控项（哪吒风格：agent 定期执行命令上报数值）────────────
# 配置文件: /etc/server-monitor/custom-commands.json
# 格式: { "名称": {"cmd": "命令", "interval": 秒, "unit": "单位(可选)", "timeout": 秒(可选)} }
# 例: { "公网IP": {"cmd": "curl -s --max-time 5 ifconfig.me", "interval": 300} }
CUSTOM_CONFIG_FILE = os.environ.get(
    "MONITOR_CUSTOM_CONFIG", "/etc/server-monitor/custom-commands.json"
)
_custom_state = {"config_mtime": 0, "config": {}, "last_run": {}, "results": {}}


def set_custom_config(config: dict) -> None:
    """由 main.py 定期从后端拉取配置后注入（管理页配置 → 数据库 → agent）。"""
    if not isinstance(config, dict):
        config = {}
    _custom_state["config"] = config
    _custom_state["last_run"] = {}
    _custom_state["results"] = {}


def _load_custom_config() -> dict:
    """后备配置源：本地文件（后端不可达时兜底）。"""
    try:
        mtime = os.path.getmtime(CUSTOM_CONFIG_FILE)
        if mtime == _custom_state["config_mtime"]:
            return _custom_state["config"]
        with open(CUSTOM_CONFIG_FILE, encoding="utf-8") as f:
            cfg = json.load(f)
        _custom_state["config"] = cfg if isinstance(cfg, dict) else {}
        _custom_state["config_mtime"] = mtime
        _custom_state["last_run"] = {}
        _custom_state["results"] = {}
    except FileNotFoundError:
        _custom_state["config"] = {}
        _custom_state["config_mtime"] = 0
    except Exception:
        _custom_state["config"] = {}
    return _custom_state["config"]


def _run_custom_command(name: str, item: dict) -> dict:
    """执行一条自定义命令，解析 stdout 首行为数值。"""
    cmd = item.get("cmd", "")
    unit = item.get("unit", "")
    timeout = float(item.get("timeout", 5))
    if not cmd:
        return {"ok": False, "error": "未配置命令"}
    try:
        proc = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        if proc.returncode != 0:
            return {"ok": False, "error": (proc.stderr or f"exit {proc.returncode}").strip()[:120]}
        out = (proc.stdout or "").strip()
        if not out:
            return {"ok": False, "error": "无输出"}
        line = out.splitlines()[0]
        # 1) 整个输出就是数值 → 直接取
        try:
            return {"ok": True, "value": float(line), "unit": unit, "raw": line[:80]}
        except ValueError:
            pass
        # 2) 行首带数值（如 "12.3 MB"、"45°C"）→ 提取数值
        # 注意 [\d.]+ 会贪婪吞掉整个 IP（141.147.147.92），float 失败要兜底
        m = re.match(r"^\s*(-?[\d.]+)", line)
        if m:
            try:
                return {"ok": True, "value": float(m.group(1)), "unit": unit, "raw": line[:80]}
            except ValueError:
                pass
        # 3) 非数值字符串（如公网 IP）→ value=None, 前端显示 raw 原文
        return {"ok": True, "value": None, "unit": unit, "raw": line[:80]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "执行超时"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}


def get_custom_metrics() -> dict:
    """按各自间隔执行自定义命令，返回 {名称: {ok, value, unit, raw?, error?}}。"""
    # 优先用后端注入的配置（管理页配置），空时兜底本地文件
    cfg = _custom_state["config"]
    if not cfg:
        cfg = _load_custom_config()
    if not cfg:
        return {}
    now = time.time()
    out = {}
    for name, item in cfg.items():
        interval = float(item.get("interval", 60))
        last = _custom_state["last_run"].get(name, 0.0)
        if now - last < interval:
            if name in _custom_state["results"]:
                out[name] = _custom_state["results"][name]
            continue
        _custom_state["last_run"][name] = now
        result = _run_custom_command(name, item)
        _custom_state["results"][name] = result
        out[name] = result
    return out


# ── apt 可升级包数量（安全更新提醒）───────────────────────────────
_apt_cache: dict = {"ts": 0, "count": 0, "ok": False, "packages": []}
APT_REFRESH_SECONDS = 3600  # 每小时查一次（apt list 有点慢）


def parse_apt_upgradable(output: str) -> list:
    """解析 `apt list --upgradable` 输出,返回 [{name, version, old_version}] 列表。
    行格式: 包名/发行版 新版本 架构 [upgradable from: 旧版本]
    """
    pkgs = []
    for line in output.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("listing"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        name = parts[0].split("/")[0]
        version = parts[1]
        old_version = None
        # 找 "[upgradable from: xxx]"
        up_idx = line.find("[upgradable from:")
        if up_idx >= 0:
            rest = line[up_idx + len("[upgradable from:"):]
            old_version = rest.split("]")[0].strip()
        pkgs.append({"name": name, "version": version, "old_version": old_version})
    return pkgs


def get_apt_updates() -> dict:
    """统计 apt 可升级包及其列表（Debian/Ubuntu；非 apt 系统返回 0）。"""
    now = time.time()
    if now - _apt_cache["ts"] < APT_REFRESH_SECONDS:
        return dict(_apt_cache)
    try:
        proc = subprocess.run(
            "apt list --upgradable 2>/dev/null",
            shell=True, capture_output=True, text=True, timeout=20,
        )
        raw = proc.stdout or ""
        count = len([l for l in raw.splitlines() if l.strip() and not l.lower().startswith("listing")])
        # 采集具体包列表(供管理面板展示哪些软件待更新)
        packages = parse_apt_upgradable(raw)
        # 适度截断:最多记录 200 个,避免 payload 过大
        if len(packages) > 200:
            packages = packages[:200]
        _apt_cache.update(ts=now, count=count, ok=True, packages=packages)
    except Exception:
        _apt_cache.update(ts=now, count=0, ok=False, packages=[])
    return dict(_apt_cache)


def collect_all() -> dict:
    """Collect all metrics and return as a single dict."""
    net = get_network_metrics()
    return {
        "timestamp": int(time.time()),
        "hostname": socket.gethostname(),
        "agent_version": AGENT_VERSION,
        "cpu": get_cpu_metrics(),
        "memory": get_memory_metrics(),
        "disk": get_disk_metrics(),
        "network": net,
        "traffic_month": net.get("traffic_month", {}),
        "load": get_load_metrics(),
        "processes": get_process_metrics(top_n=10),
        "system": get_system_metrics(),
        "docker": get_docker_metrics(),
        "services": get_services_metrics(),
        "certificates": get_certificates_metrics(),
        "custom": get_custom_metrics(),
        "apt_updates": get_apt_updates(),
    }


if __name__ == "__main__":
    import json
    data = collect_all()
    print(json.dumps(data, indent=2))
