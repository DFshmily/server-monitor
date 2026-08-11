"""Server metrics collector using psutil + docker."""
import os
import json
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
    interfaces = {}
    for name, counters in io.items():
        if name == 'lo':
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
            "month": state.get("month", time.strftime("%Y-%m")),
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

    # ── 月度流量累计（跨月自动重置，跨重启保留）──
    month = time.strftime("%Y-%m")
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
            "recv_bytes": month_recv,
            "sent_bytes": month_sent,
            "total_bytes": month_recv + month_sent,
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
    """Docker container stats (if Docker is available)."""
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
        return {"containers": containers, "total": len(containers)}
    except Exception:
        return {"containers": [], "total": 0, "error": "docker_unavailable"}


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


def collect_all() -> dict:
    """Collect all metrics and return as a single dict."""
    net = get_network_metrics()
    return {
        "timestamp": int(time.time()),
        "hostname": socket.gethostname(),
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
    }


if __name__ == "__main__":
    import json
    data = collect_all()
    print(json.dumps(data, indent=2))
