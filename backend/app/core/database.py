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
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_login_attempts_email ON login_attempts(email, created_at);

        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            action TEXT NOT NULL,
            detail TEXT,
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_audit_logs_ts ON audit_logs(created_at);
    """)
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
