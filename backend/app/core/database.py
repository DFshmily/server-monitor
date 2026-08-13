"""SQLite database layer using aiosqlite."""
import aiosqlite
from app.core.config import DB_PATH

_db: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        _db = await aiosqlite.connect(DB_PATH)
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA journal_mode=WAL")
        await _db.execute("PRAGMA busy_timeout=5000")
    return _db


async def init_db() -> None:
    db = await get_db()
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS metrics_raw (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_name TEXT NOT NULL,
            timestamp INTEGER NOT NULL,
            data TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_raw_server_ts ON metrics_raw(server_name, timestamp);

        CREATE TABLE IF NOT EXISTS metrics_agg (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_name TEXT NOT NULL,
            timestamp INTEGER NOT NULL,
            interval TEXT NOT NULL,
            data TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_agg_server_ts ON metrics_agg(server_name, timestamp, interval);

        CREATE TABLE IF NOT EXISTS server_meta (
            server_name TEXT PRIMARY KEY,
            alias TEXT
        );

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',      -- 'admin' | 'user'
            disabled INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS invites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            used_by TEXT,
            used_at INTEGER
        );

        CREATE TABLE IF NOT EXISTS email_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            code TEXT NOT NULL,
            expires_at INTEGER NOT NULL,
            used INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_email_codes_email ON email_codes(email);

        CREATE TABLE IF NOT EXISTS alert_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_name TEXT NOT NULL,          -- '*' = all servers
            metric TEXT NOT NULL,               -- cpu, memory, disk, load1, net_in, net_out
            operator TEXT NOT NULL DEFAULT '>', -- > | >= | < | <=
            threshold REAL NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS alert_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_id INTEGER,
            server_name TEXT NOT NULL,
            metric TEXT NOT NULL,
            value REAL,
            message TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'threshold',  -- threshold | offline | recovered
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_alert_events_ts ON alert_events(created_at);

        CREATE TABLE IF NOT EXISTS login_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            success INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL,
            ip TEXT,
            user_agent TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_login_attempts_email ON login_attempts(email, created_at);
        CREATE INDEX IF NOT EXISTS idx_login_attempts_ts ON login_attempts(created_at);

        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            action TEXT NOT NULL,
            detail TEXT,
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_audit_logs_ts ON audit_logs(created_at);

        CREATE TABLE IF NOT EXISTS probe_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL,              -- http | tcp | ping | dns
            target TEXT NOT NULL,            -- URL / host:port / host / domain
            expected TEXT DEFAULT '',        -- http 关键词匹配(可选)
            interval INTEGER NOT NULL DEFAULT 60,
            timeout INTEGER NOT NULL DEFAULT 10,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS probe_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_id INTEGER NOT NULL,
            ok INTEGER NOT NULL DEFAULT 0,
            latency_ms REAL,
            status_code INTEGER,
            message TEXT,
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_probe_results_rule ON probe_results(rule_id, id);

        CREATE TABLE IF NOT EXISTS maintenance_windows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_name TEXT NOT NULL DEFAULT '*',
            start_at INTEGER NOT NULL,
            end_at INTEGER NOT NULL,
            note TEXT DEFAULT '',
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_maint_time ON maintenance_windows(start_at, end_at);

        CREATE TABLE IF NOT EXISTS custom_commands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_name TEXT NOT NULL,
            name TEXT NOT NULL,
            cmd TEXT NOT NULL,
            interval INTEGER NOT NULL DEFAULT 60,
            unit TEXT DEFAULT '',
            timeout INTEGER NOT NULL DEFAULT 5,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_custom_server ON custom_commands(server_name);

        CREATE TABLE IF NOT EXISTS heartbeat_checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,             -- 心跳 URL 标识（URL 即密钥）
            interval INTEGER NOT NULL DEFAULT 86400,  -- 预期间隔(秒)
            grace INTEGER NOT NULL DEFAULT 3600,      -- 宽限(秒)
            last_ping INTEGER DEFAULT 0,
            last_ping_success INTEGER DEFAULT 1,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_heartbeat_slug ON heartbeat_checks(slug);
    """)
    # ── Migrations (idempotent ALTERs for schema evolution) ──
    cols = [r["name"] for r in await (await db.execute("PRAGMA table_info(login_attempts)")).fetchall()]
    if "ip" not in cols:
        await db.execute("ALTER TABLE login_attempts ADD COLUMN ip TEXT")
    if "user_agent" not in cols:
        await db.execute("ALTER TABLE login_attempts ADD COLUMN user_agent TEXT")
    await db.commit()


async def close_db() -> None:
    global _db
    if _db:
        await _db.close()
        _db = None


async def audit_log(email: str, action: str, detail: str | None = None) -> None:
    """Write an audit log entry (called from admin endpoints)."""
    db = await get_db()
    import time
    await db.execute(
        "INSERT INTO audit_logs (email, action, detail, created_at) VALUES (?, ?, ?, ?)",
        (email, action, detail, int(time.time())),
    )
    await db.commit()
