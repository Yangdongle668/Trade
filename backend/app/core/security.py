import base64
import os
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(user_id: uuid.UUID, tenant_id: uuid.UUID) -> str:
    s = get_settings()
    payload = {
        "sub": str(user_id),
        "tid": str(tenant_id),
        "exp": datetime.now(timezone.utc) + timedelta(hours=s.access_token_ttl_hours),
    }
    return jwt.encode(payload, s.secret_key, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])


# ---- 凭据加密（OAuth refresh_token / BYOK / SMTP 授权码）----

def _aes() -> AESGCM:
    key_b64 = get_settings().encryption_key
    key = base64.b64decode(key_b64) if key_b64 else b"\x00" * 32  # 开发缺省，生产必配
    return AESGCM(key)


def encrypt_secret(plain: str) -> str:
    nonce = os.urandom(12)
    ct = _aes().encrypt(nonce, plain.encode(), None)
    return base64.b64encode(nonce + ct).decode()


def decrypt_secret(token: str) -> str:
    raw = base64.b64decode(token)
    return _aes().decrypt(raw[:12], raw[12:], None).decode()
