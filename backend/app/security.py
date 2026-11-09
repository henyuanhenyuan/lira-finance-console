"""JWT 鉴权与口令散列。"""

from __future__ import annotations

import datetime as dt
from typing import Any

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request

from .config import get_settings


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        return False


def issue_token(user: dict[str, Any]) -> str:
    s = get_settings()
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": str(user["id"]),
        "email": user["email"],
        "name": user["display_name"],
        "role": user["role"],
        "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(minutes=s.jwt_ttl_minutes)).timestamp()),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> dict[str, Any]:
    s = get_settings()
    try:
        return jwt.decode(token, s.jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(401, "登录已过期") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(401, "无效凭证") from exc


async def current_user(request: Request) -> dict[str, Any]:
    from . import db

    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(401, "缺少访问令牌")
    payload = decode_token(auth[7:].strip())
    row = await db.fetchrow(
        "SELECT id,email,display_name,role,status FROM ops.users WHERE id=$1",
        int(payload["sub"]),
    )
    if row is None or row["status"] != "active":
        raise HTTPException(401, "账号已停用或不存在")
    return {
        "id": row["id"], "email": row["email"],
        "name": row["display_name"], "display_name": row["display_name"],
        "role": row["role"], "status": row["status"],
    }


CurrentUser = Depends(current_user)
