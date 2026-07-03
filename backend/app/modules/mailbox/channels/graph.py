"""Microsoft Graph 通道（OAuth）：refresh_token → sendMail。"""
import httpx

from app.core.config import get_settings
from app.core.security import decrypt_secret
from app.modules.mailbox.channels.base import ChannelError, MailChannel, OutgoingMail
from app.modules.mailbox.models import Mailbox


def _access_token(refresh_token: str) -> str:
    s = get_settings()
    resp = httpx.post(
        "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        data={"client_id": s.ms_client_id, "client_secret": s.ms_client_secret,
              "refresh_token": refresh_token, "grant_type": "refresh_token",
              "scope": "https://graph.microsoft.com/Mail.Send offline_access"},
        timeout=30)
    if resp.status_code != 200:
        raise ChannelError(f"Graph token 刷新失败: {resp.text[:200]}")
    return resp.json()["access_token"]


class GraphChannel(MailChannel):
    name = "ms_graph"

    def send(self, mailbox: Mailbox, mail: OutgoingMail) -> None:
        token = _access_token(decrypt_secret(mailbox.credentials_enc))
        body = mail.body_text
        if mail.footer or mail.unsubscribe_url:
            body += "\n\n--\n" + mail.footer
            if mail.unsubscribe_url:
                body += f"\nUnsubscribe: {mail.unsubscribe_url}"
        payload = {
            "message": {
                "subject": mail.subject,
                "body": {"contentType": "Text", "content": body},
                "toRecipients": [{"emailAddress": {"address": mail.to_email}}],
                "internetMessageHeaders": [
                    {"name": "X-Outreach-Message-ID", "value": mail.rfc_message_id},
                ] + ([{"name": "List-Unsubscribe", "value": f"<{mail.unsubscribe_url}>"}]
                     if mail.unsubscribe_url else []),
            },
            "saveToSentItems": True,
        }
        resp = httpx.post("https://graph.microsoft.com/v1.0/me/sendMail",
                          headers={"Authorization": f"Bearer {token}"},
                          json=payload, timeout=60)
        if resp.status_code != 202:
            raise ChannelError(f"Graph 发送失败 {resp.status_code}: {resp.text[:200]}")
