"""租户上下文：JWT → 当前用户/租户，注入依赖 + 会话级 RLS 变量。

数据隔离双保险（架构 §9）：
1. 应用层：所有查询经 CurrentUser.tenant_id 过滤；
2. 数据库层：RLS 策略读取 `app.tenant_id` 会话变量（backend/sql/rls.sql），
   漏写 WHERE 也不会跨租户泄漏。
"""
import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import decode_access_token


@dataclass
class CurrentUser:
    user_id: uuid.UUID
    tenant_id: uuid.UUID


def get_current_user(request: Request) -> CurrentUser:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="缺少访问令牌")
    try:
        payload = decode_access_token(auth.removeprefix("Bearer "))
    except Exception:
        raise HTTPException(status_code=401, detail="令牌无效或已过期")
    return CurrentUser(user_id=uuid.UUID(payload["sub"]), tenant_id=uuid.UUID(payload["tid"]))


def get_tenant_db(
    user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> Session:
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT set_config('app.tenant_id', :tid, false)"), {"tid": str(user.tenant_id)})
    return db
