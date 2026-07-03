from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.core.tenancy import CurrentUser, get_current_user
from app.modules.identity.models import Membership, Tenant, User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    company_name: str
    display_name: str = ""


class TokenOut(BaseModel):
    access_token: str
    tenant_id: str
    user_id: str


@router.post("/register", response_model=TokenOut)
def register(body: RegisterIn, db: Session = Depends(get_db)) -> TokenOut:
    if db.execute(select(User).where(User.email == body.email.lower())).scalar_one_or_none():
        raise HTTPException(409, "该邮箱已注册")
    if len(body.password) < 8:
        raise HTTPException(422, "密码至少 8 位")
    tenant = Tenant(name=body.company_name)
    user = User(email=body.email.lower(), password_hash=hash_password(body.password),
                display_name=body.display_name or body.email.split("@")[0])
    db.add_all([tenant, user])
    db.flush()
    db.add(Membership(user_id=user.id, tenant_id=tenant.id, role="admin"))
    db.commit()
    return TokenOut(access_token=create_access_token(user.id, tenant.id),
                    tenant_id=str(tenant.id), user_id=str(user.id))


class LoginIn(BaseModel):
    email: EmailStr
    password: str


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)) -> TokenOut:
    user = db.execute(select(User).where(User.email == body.email.lower())).scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "邮箱或密码错误")
    membership = db.execute(
        select(Membership).where(Membership.user_id == user.id)
    ).scalars().first()
    if membership is None:
        raise HTTPException(403, "账号未关联任何团队")
    return TokenOut(access_token=create_access_token(user.id, membership.tenant_id),
                    tenant_id=str(membership.tenant_id), user_id=str(user.id))


class MeOut(BaseModel):
    user_id: str
    tenant_id: str
    email: str
    display_name: str
    role: str


@router.get("/me", response_model=MeOut)
def me(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)) -> MeOut:
    user = db.get(User, current.user_id)
    membership = db.execute(
        select(Membership).where(Membership.user_id == current.user_id,
                                 Membership.tenant_id == current.tenant_id)
    ).scalar_one_or_none()
    if user is None or membership is None:
        raise HTTPException(401, "会话无效")
    return MeOut(user_id=str(user.id), tenant_id=str(current.tenant_id),
                 email=user.email, display_name=user.display_name, role=membership.role)
