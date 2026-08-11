"""Auth endpoints: register, login, me, invites, user management."""
import secrets
import time

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, EmailStr, Field

from app.core.database import get_db
from app.core.auth import (
    hash_password, verify_password, create_token, decode_token,
    generate_invite_code, make_invite_expiry,
)
from app.core.mailer import send_verification_code
from app.core.config import SMTP_USER
from app.core.database import audit_log

router = APIRouter(prefix="/api/auth", tags=["auth"])

ADMIN_EMAIL = "admin@dfshmily.icu"
INVITE_TTL_DAYS = 7
CODE_TTL_SECONDS = 600  # 10 min
CODE_RESEND_SECONDS = 60  # min interval between sends


# ── Schemas ───────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    invite_code: str
    code: str  # email verification code


class SendCodeRequest(BaseModel):
    email: EmailStr
    invite_code: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    remember: bool = False


class InviteBatchRequest(BaseModel):
    count: int = Field(default=10, ge=1, le=100)
    days: int = Field(default=7, ge=1, le=365)


class InviteManualRequest(BaseModel):
    code: str = Field(min_length=4, max_length=32)
    days: int = Field(default=7, ge=1, le=365)


class RoleRequest(BaseModel):
    email: EmailStr
    role: str  # 'admin' | 'user'


class DisableRequest(BaseModel):
    email: EmailStr
    disabled: bool


class PasswordRequest(BaseModel):
    old_password: str = ""
    new_password: str = Field(min_length=8, max_length=128)


# ── Dependencies ──────────────────────────────────────────────────
async def get_current_user(authorization: str = Header(None)):
    """Return user row dict or raise 401."""
    if not authorization:
        raise HTTPException(status_code=401, detail="未登录")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="未登录")
    payload = decode_token(parts[1])
    if not payload:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM users WHERE email = ?", (payload["sub"],)
    )
    row = await cursor.fetchone()
    if not row or row["disabled"]:
        raise HTTPException(status_code=401, detail="账号不存在或已被禁用")
    return dict(row)


async def require_admin(user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


async def require_root_admin(user: dict = Depends(get_current_user)):
    """Only the root account (admin@dfshmily.icu) may grant/revoke admin roles."""
    if user["email"] != ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="需要超级管理员权限")
    return user


# ── Public: send code / register / login ──────────────────────────
@router.post("/send-code")
async def send_code(req: SendCodeRequest):
    """Validate invite code, then email a 6-digit verification code."""
    db = await get_db()
    email = req.email.lower()

    # 1. Email not already registered
    cur = await db.execute("SELECT id FROM users WHERE email = ?", (email,))
    if await cur.fetchone():
        raise HTTPException(status_code=400, detail="该邮箱已注册")

    # 2. Invite code valid & unused & not expired
    cur = await db.execute(
        "SELECT * FROM invites WHERE code = ?", (req.invite_code.strip().upper(),)
    )
    inv = await cur.fetchone()
    if not inv:
        raise HTTPException(status_code=400, detail="邀请码无效")
    if inv["used_by"]:
        raise HTTPException(status_code=400, detail="邀请码已被使用")
    if inv["expires_at"] < int(time.time()):
        raise HTTPException(status_code=400, detail="邀请码已过期")

    # 3. Rate limit: at most one code per 60s per email
    now = int(time.time())
    cur = await db.execute(
        "SELECT created_at FROM email_codes WHERE email = ? ORDER BY id DESC LIMIT 1",
        (email,),
    )
    last = await cur.fetchone()
    if last and now - last["created_at"] < CODE_RESEND_SECONDS:
        wait = CODE_RESEND_SECONDS - (now - last["created_at"])
        raise HTTPException(status_code=429, detail=f"发送太频繁，请 {wait} 秒后再试")

    # 4. Generate + store + send
    code = f"{secrets.randbelow(1000000):06d}"
    await db.execute(
        "INSERT INTO email_codes (email, code, expires_at, created_at) VALUES (?, ?, ?, ?)",
        (email, code, now + CODE_TTL_SECONDS, now),
    )
    await db.commit()

    if not SMTP_USER:
        # Dev mode: return the code in the response so setup is testable
        # without a configured SMTP account. Remove for production.
        return {"ok": True, "dev_code": code, "message": "SMTP 未配置，验证码(仅开发模式): " + code}

    ok = send_verification_code(email, code)
    if not ok:
        raise HTTPException(status_code=500, detail="邮件发送失败，请稍后重试")
    return {"ok": True, "message": "验证码已发送到你的邮箱"}


@router.post("/register")
async def register(req: RegisterRequest):
    db = await get_db()
    email = req.email.lower()

    # 1. Check email not taken
    cur = await db.execute("SELECT id FROM users WHERE email = ?", (email,))
    if await cur.fetchone():
        raise HTTPException(status_code=400, detail="该邮箱已注册")

    # 2. Validate invite code (unused & not expired)
    cur = await db.execute(
        "SELECT * FROM invites WHERE code = ?", (req.invite_code.strip().upper(),)
    )
    inv = await cur.fetchone()
    if not inv:
        raise HTTPException(status_code=400, detail="邀请码无效")
    if inv["used_by"]:
        raise HTTPException(status_code=400, detail="邀请码已被使用")
    if inv["expires_at"] < int(time.time()):
        raise HTTPException(status_code=400, detail="邀请码已过期")

    # 3. Validate email verification code (latest unused, unexpired)
    cur = await db.execute(
        "SELECT * FROM email_codes WHERE email = ? AND used = 0 ORDER BY id DESC LIMIT 1",
        (email,),
    )
    code_row = await cur.fetchone()
    if not code_row:
        raise HTTPException(status_code=400, detail="请先获取邮箱验证码")
    if code_row["code"] != req.code.strip():
        raise HTTPException(status_code=400, detail="验证码错误")
    if code_row["expires_at"] < int(time.time()):
        raise HTTPException(status_code=400, detail="验证码已过期，请重新获取")

    # 4. Create user + mark invite & code used
    now = int(time.time())
    await db.execute(
        "INSERT INTO users (email, password_hash, role, created_at) VALUES (?, ?, 'user', ?)",
        (email, hash_password(req.password), now),
    )
    await db.execute(
        "UPDATE invites SET used_by = ?, used_at = ? WHERE id = ?",
        (email, now, inv["id"]),
    )
    await db.execute(
        "UPDATE email_codes SET used = 1 WHERE id = ?", (code_row["id"],)
    )
    await db.commit()
    return {"ok": True, "message": "注册成功"}


@router.post("/login")
async def login(req: LoginRequest):
    db = await get_db()
    email = req.email.lower()
    now = int(time.time())

    # ── Brute-force protection: 5 failed attempts => 15 min lockout ──
    cur = await db.execute(
        "SELECT COUNT(*) as n, MAX(created_at) as last FROM login_attempts WHERE email = ? AND success = 0 AND created_at > ?",
        (email, now - 900),
    )
    row = await cur.fetchone()
    if row and row["n"] >= 5:
        wait = 900 - (now - row["last"])
        raise HTTPException(status_code=429, detail=f"尝试次数过多，请 {max(wait, 1)} 秒后再试")

    cur = await db.execute("SELECT * FROM users WHERE email = ?", (email,))
    row = await cur.fetchone()
    ok = bool(row and verify_password(req.password, row["password_hash"]))
    await db.execute(
        "INSERT INTO login_attempts (email, success, created_at) VALUES (?, ?, ?)",
        (email, int(ok), now),
    )
    await db.commit()

    if not row or not ok:
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    if row["disabled"]:
        raise HTTPException(status_code=403, detail="账号已被禁用")
    token = create_token(email, row["role"], remember=req.remember)
    return {"token": token, "email": email, "role": row["role"]}


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return {"email": user["email"], "role": user["role"]}


@router.post("/change-password")
async def change_password(req: PasswordRequest, user: dict = Depends(get_current_user)):
    # Admin may change password without old one (first-login flow); regular users must verify.
    if user["role"] != "admin" and not verify_password(req.old_password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="原密码错误")
    db = await get_db()
    await db.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (hash_password(req.new_password), user["id"]),
    )
    await db.commit()
    return {"ok": True}


# ── Admin: invites ────────────────────────────────────────────────
@router.post("/invites", dependencies=[Depends(require_admin)])
async def create_invites(req: InviteBatchRequest, admin: dict = Depends(require_admin)):
    db = await get_db()
    codes = generate_invite_code(req.count)
    now = int(time.time())
    exp = now + req.days * 86400
    for c in codes:
        await db.execute(
            "INSERT INTO invites (code, created_at, expires_at) VALUES (?, ?, ?)",
            (c, now, exp),
        )
    await db.commit()
    await audit_log(admin["email"], "create_invites", f"生成 {len(codes)} 个邀请码，有效期 {req.days} 天")
    return {"codes": codes, "expires_in_days": req.days}


@router.post("/invites/manual", dependencies=[Depends(require_admin)])
async def create_invite_manual(req: InviteManualRequest, admin: dict = Depends(require_admin)):
    """Manually add a custom invite code with a chosen validity period."""
    db = await get_db()
    code = req.code.strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail="邀请码不能为空")

    # 检查是否已存在
    cur = await db.execute("SELECT id FROM invites WHERE code = ?", (code,))
    if await cur.fetchone():
        raise HTTPException(status_code=400, detail="该邀请码已存在")

    now = int(time.time())
    await db.execute(
        "INSERT INTO invites (code, created_at, expires_at) VALUES (?, ?, ?)",
        (code, now, now + req.days * 86400),
    )
    await db.commit()
    await audit_log(admin["email"], "create_invite_manual", f"手动添加邀请码 {code}，{req.days} 天")
    return {"ok": True, "code": code, "expires_in_days": req.days}


class InviteDeleteRequest(BaseModel):
    code: str = Field(min_length=1, max_length=32)


@router.post("/invites/delete", dependencies=[Depends(require_admin)])
async def delete_invite(req: InviteDeleteRequest, admin: dict = Depends(require_admin)):
    """Delete/cancel an invite code (only if unused)."""
    db = await get_db()
    code = req.code.strip().upper()
    cur = await db.execute("SELECT * FROM invites WHERE code = ?", (code,))
    inv = await cur.fetchone()
    if not inv:
        raise HTTPException(status_code=404, detail="邀请码不存在")
    if inv["used_by"]:
        raise HTTPException(status_code=400, detail="该邀请码已被使用，不能删除")
    await db.execute("DELETE FROM invites WHERE id = ?", (inv["id"],))
    await db.commit()
    await audit_log(admin["email"], "delete_invite", f"取消邀请码 {code}")
    return {"ok": True, "code": code}


@router.get("/invites", dependencies=[Depends(require_admin)])
async def list_invites():
    db = await get_db()
    cur = await db.execute(
        "SELECT code, created_at, expires_at, used_by, used_at FROM invites ORDER BY id DESC LIMIT 100"
    )
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


# ── Admin: users ──────────────────────────────────────────────────
@router.get("/users", dependencies=[Depends(require_admin)])
async def list_users():
    db = await get_db()
    cur = await db.execute(
        "SELECT id, email, role, disabled, created_at FROM users ORDER BY id"
    )
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.post("/users/role", dependencies=[Depends(require_root_admin)])
async def set_role(req: RoleRequest, admin: dict = Depends(require_root_admin)):
    email = req.email.lower()
    if email == admin["email"]:
        raise HTTPException(status_code=400, detail="不能修改自己的角色")
    if req.role not in ("admin", "user"):
        raise HTTPException(status_code=400, detail="角色必须是 admin 或 user")
    db = await get_db()
    cur = await db.execute("SELECT id FROM users WHERE email = ?", (email,))
    if not await cur.fetchone():
        raise HTTPException(status_code=404, detail="用户不存在")
    await db.execute("UPDATE users SET role = ? WHERE email = ?", (req.role, email))
    await db.commit()
    await audit_log(admin["email"], "set_role", f"{email} → {req.role}")
    return {"ok": True}


@router.post("/users/disable", dependencies=[Depends(require_admin)])
async def set_disabled(req: DisableRequest, admin: dict = Depends(require_admin)):
    email = req.email.lower()
    if email == admin["email"]:
        raise HTTPException(status_code=400, detail="不能禁用自己的账号")
    db = await get_db()
    cur = await db.execute("SELECT role FROM users WHERE email = ?", (email,))
    target = await cur.fetchone()
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    # 只有超级管理员能禁用/启用其他管理员
    if target["role"] == "admin" and admin["email"] != ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="不能操作其他管理员")
    await db.execute("UPDATE users SET disabled = ? WHERE email = ?", (int(req.disabled), email))
    await db.commit()
    await audit_log(admin["email"], "set_disabled", f"{email} → {'禁用' if req.disabled else '启用'}")
    return {"ok": True}
