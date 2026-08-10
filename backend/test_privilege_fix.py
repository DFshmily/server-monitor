"""End-to-end verification of the super-admin (root) privilege fix, live server.

Seeds a throwaway promoted-admin + plain user directly in the DB, then drives
the running backend over HTTP with stdlib urllib (no extra deps).
"""
import asyncio
import json
import os
import time
import urllib.error
import urllib.request

# Must match the systemd unit: JWT_SECRET derives from MONITOR_API_KEY.
os.environ.setdefault("MONITOR_API_KEY", "monitor-secret-key-2026")

from app.core.database import get_db
from app.core.auth import hash_password, create_token

BASE = "http://127.0.0.1:8000"
ROOT = "admin@dfshmily.icu"
TEST_ADMIN = "privilege-test-admin@dfshmily.icu"
TEST_USER = "privilege-test-user@dfshmily.icu"

results = []


def check(name, cond):
    results.append((name, cond))
    print(("✅" if cond else "❌"), name)


def call(method, path, token=None, body=None):
    req = urllib.request.Request(BASE + path, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=data, timeout=10) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}


async def seed():
    db = await get_db()
    now = int(time.time())
    await db.execute(
        "INSERT OR REPLACE INTO users (email, password_hash, role, created_at) VALUES (?, ?, 'admin', ?)",
        (TEST_ADMIN, hash_password("testpass123"), now),
    )
    await db.execute(
        "INSERT OR REPLACE INTO users (email, password_hash, role, created_at) VALUES (?, ?, 'user', ?)",
        (TEST_USER, hash_password("testpass123"), now),
    )
    await db.commit()


async def cleanup():
    db = await get_db()
    await db.execute("DELETE FROM users WHERE email IN (?, ?)", (TEST_ADMIN, TEST_USER))
    await db.commit()
    await db.close()  # shut down aiosqlite worker thread so the process can exit


def main():
    asyncio.run(seed())
    try:
        t_admin = create_token(TEST_ADMIN, "admin", remember=False)
        t_root = create_token(ROOT, "admin", remember=False)

        # 1. Promoted admin tries to demote ROOT -> 403
        s, _ = call("POST", "/api/auth/users/role", t_admin, {"email": ROOT, "role": "user"})
        check("被提拔的管理员不能降级 root (403)", s == 403)

        # 2. Promoted admin tries to disable ROOT -> 403
        s, _ = call("POST", "/api/auth/users/disable", t_admin, {"email": ROOT, "disabled": True})
        check("被提拔的管理员不能禁用 root (403)", s == 403)

        # 3. Promoted admin cannot change ANY role (even promote a plain user) -> 403
        s, _ = call("POST", "/api/auth/users/role", t_admin, {"email": TEST_USER, "role": "admin"})
        check("被提拔的管理员不能给任何人改角色 (403)", s == 403)

        # 4. Promoted admin CAN still disable a plain user
        s, _ = call("POST", "/api/auth/users/disable", t_admin, {"email": TEST_USER, "disabled": True})
        check("普通管理员仍可禁用普通用户 (200)", s == 200)

        # 5. Root CAN revoke the promoted admin
        s, _ = call("POST", "/api/auth/users/role", t_root, {"email": TEST_ADMIN, "role": "user"})
        check("root 可收回管理员权限 (200)", s == 200)

        # 6. Demoted user cannot reach user management at all
        s, _ = call("GET", "/api/auth/users", t_admin)
        check("降级后无法访问用户管理 (403)", s == 403)

        # 7. Root cannot demote self
        s, _ = call("POST", "/api/auth/users/role", t_root, {"email": ROOT, "role": "user"})
        check("root 不能修改自己的角色 (400)", s == 400)

        # 8. Nonexistent target -> 404
        s, _ = call("POST", "/api/auth/users/role", t_root, {"email": "nobody@nowhere.icu", "role": "user"})
        check("目标不存在返回 404", s == 404)

        # 9. Root keeps ultimate control (re-enable the plain user)
        s, _ = call("POST", "/api/auth/users/disable", t_root, {"email": TEST_USER, "disabled": False})
        check("root 可启停任意账号 (200)", s == 200)
    finally:
        asyncio.run(cleanup())

    failed = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    if failed:
        print("FAILED:", failed)
        raise SystemExit(1)
    print("ALL PASS ✅")


if __name__ == "__main__":
    main()
