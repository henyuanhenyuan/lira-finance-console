from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import db, security

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=4, max_length=128)


class PasswordIn(BaseModel):
    old_password: str = Field(min_length=4, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


@router.post("/login")
async def login(body: LoginIn):
    row = await db.fetchrow(
        "SELECT id,email,password_hash,display_name,role,status FROM ops.users WHERE lower(email)=lower($1)",
        body.email,
    )
    if not row or not security.verify_password(body.password, row["password_hash"]):
        raise HTTPException(401, "邮箱或密码不正确")
    if row["status"] != "active":
        raise HTTPException(403, "该账号已被停用，请联系管理员")

    user = {"id": row["id"], "email": row["email"],
            "display_name": row["display_name"], "role": row["role"]}
    await db.execute(
        "UPDATE ops.users SET last_login_at=now() WHERE id=$1", row["id"])
    await db.execute(
        "INSERT INTO ops.audit_log(actor,action,target) VALUES($1,'login',$2)",
        row["email"], row["email"])
    return {"token": security.issue_token(user), "user": user}


@router.get("/me")
async def me(user=Depends(security.current_user)):
    return user


@router.post("/password")
async def change_password(body: PasswordIn, user=Depends(security.current_user)):
    row = await db.fetchrow("SELECT password_hash FROM ops.users WHERE id=$1", user["id"])
    if not row or not security.verify_password(body.old_password, row["password_hash"]):
        raise HTTPException(400, "原密码不正确")
    await db.execute(
        "UPDATE ops.users SET password_hash=$2 WHERE id=$1",
        user["id"], security.hash_password(body.new_password))
    await db.execute(
        "INSERT INTO ops.audit_log(actor,action,target) VALUES($1,'change_password',$2)",
        user["email"], user["email"])
    return {"ok": True}
