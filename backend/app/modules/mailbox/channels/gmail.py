"""Gmail API 通道（OAuth）：refresh_token 换 access_token → messages.send（raw MIME）。"""
import base64

import httpx

from app.core.config import get_settings
from app.core.security import decrypt_secret
from app.modules.mailbox.channels.base import (ChannelError, HardBounceError, MailChannel,
                                               OutgoingMail)
from app.modules.mailbox.channels.smtp import build_message
from app.modules.mailbox.models import Mailbox


def _access_token(refresh_token: str) -> str:
    s = get_settings()
    resp = httpx.post("https://oauth2.googleapis.com/token", data={
        "client_id": s.google_client_id, "client_secret": s.google_client_secret,
        "refresh_token": refresh_token, "grant_type": "refresh_token",
    }, timeout=30)
    if resp.status_code != 200:
        raise ChannelError(f"Gmail token 刷新失败: {resp.text[:200]}")
    return resp.json()["access_token"]


class GmailChannel(MailChannel):
    name = "gmail"

    def send(self, mailbox: Mailbox, mail: OutgoingMail) -> None:
        token = _access_token(decrypt_secret(mailbox.credentials_enc))
        raw = base64.urlsafe_b64encode(
            build_message(mailbox.email, mail).as_bytes()).decode()
        resp = httpx.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            headers={"Authorization": f"Bearer {token}"},
            json={"raw": raw}, timeout=60,
        )
        if resp.status_code == 400 and "invalid" in resp.text.lower():
            raise HardBounceError(resp.text[:200])
        if resp.status_code != 200:
            raise ChannelError(f"Gmail 发送失败 {resp.status_code}: {resp.text[:200]}")
