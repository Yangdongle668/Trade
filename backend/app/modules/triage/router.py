"""退订端点：无需登录（邮件收件人点击），命中签名即永久压制。"""
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modules.triage.service import add_suppression, parse_unsubscribe_token

router = APIRouter(tags=["public"])

_PAGE = """<!doctype html><meta charset="utf-8">
<body style="font-family:sans-serif;max-width:480px;margin:80px auto;text-align:center">
<h2>{title}</h2><p style="color:#666">{note}</p></body>"""


@router.get("/api/u/{token}", response_class=HTMLResponse)
def unsubscribe(token: str, db: Session = Depends(get_db)) -> str:
    parsed = parse_unsubscribe_token(token)
    if parsed is None:
        return _PAGE.format(title="Invalid link", note="This unsubscribe link is not valid.")
    tenant_id, email = parsed
    add_suppression(db, tenant_id, email, "unsubscribe", "收件人点击退订链接")
    db.commit()
    return _PAGE.format(title="You're unsubscribed",
                        note=f"{email} will not receive any further emails from this sender.")
