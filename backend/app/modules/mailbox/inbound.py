"""入向邮件解析与三通道收件轮询（架构 §7：统一 3 分钟增量拉取）。

游标：IMAP = {uidvalidity, uidnext}；Gmail = {history_id}；Graph = {delta_link}。
"""
import email
import email.policy
import imaplib
from dataclasses import dataclass, field
from datetime import datetime, timezone

import structlog

from app.core.security import decrypt_secret
from app.modules.mailbox.models import Mailbox

log = structlog.get_logger()


@dataclass
class InboundMail:
    from_email: str
    subject: str
    body_text: str
    rfc_message_id: str
    in_reply_to: str = ""
    references: list[str] = field(default_factory=list)
    received_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def parse_mime(raw: bytes) -> InboundMail | None:
    try:
        msg = email.message_from_bytes(raw, policy=email.policy.default)
    except Exception:
        return None
    from_header = msg.get("From", "")
    addr = email.utils.parseaddr(from_header)[1].lower()
    if not addr:
        return None
    body = ""
    plain = msg.get_body(preferencelist=("plain",))
    if plain is not None:
        body = plain.get_content()
    else:
        html = msg.get_body(preferencelist=("html",))
        if html is not None:
            import re
            body = re.sub(r"<[^>]+>", " ", html.get_content())
    refs = (msg.get("References") or "").split()
    return InboundMail(
        from_email=addr,
        subject=msg.get("Subject", "")[:500],
        body_text=body.strip()[:8000],
        rfc_message_id=(msg.get("Message-ID") or "").strip(),
        in_reply_to=(msg.get("In-Reply-To") or "").strip(),
        references=refs,
    )


def poll_imap(mailbox: Mailbox) -> tuple[list[InboundMail], dict]:
    """IMAP UID 游标增量拉取；返回 (新邮件, 新游标)。"""
    cfg = mailbox.smtp_imap_config or {}
    host = cfg.get("imap_host") or cfg.get("smtp_host", "").replace("smtp", "imap", 1)
    port = int(cfg.get("imap_port", 993))
    if not host:
        return [], mailbox.poll_cursor
    cursor = dict(mailbox.poll_cursor or {})
    out: list[InboundMail] = []
    try:
        conn = imaplib.IMAP4_SSL(host, port, timeout=30)
        conn.login(mailbox.email, decrypt_secret(mailbox.credentials_enc))
        _, data = conn.select("INBOX", readonly=True)
        _, uv_data = conn.status("INBOX", "(UIDVALIDITY UIDNEXT)")
        status = uv_data[0].decode()
        uidvalidity = int(status.split("UIDVALIDITY")[1].split()[0].strip("() "))
        uidnext = int(status.split("UIDNEXT")[1].split()[0].strip("() "))

        if cursor.get("uidvalidity") != uidvalidity:
            # 信箱重置：从当前 UIDNEXT 起步，不回灌历史（避免把旧邮件当新回复）
            cursor = {"uidvalidity": uidvalidity, "uidnext": uidnext}
        elif uidnext > int(cursor.get("uidnext", uidnext)):
            since = int(cursor["uidnext"])
            _, found = conn.uid("search", None, f"UID {since}:*")
            for uid in (found[0] or b"").split():
                if int(uid) < since:
                    continue
                _, fetched = conn.uid("fetch", uid, "(RFC822)")
                if fetched and fetched[0] and isinstance(fetched[0], tuple):
                    parsed = parse_mime(fetched[0][1])
                    if parsed:
                        out.append(parsed)
            cursor["uidnext"] = uidnext
        conn.logout()
    except (imaplib.IMAP4.error, OSError) as e:
        log.warning("imap.poll_error", mailbox=mailbox.email, error=str(e))
    return out, cursor


def poll_mailbox(mailbox: Mailbox) -> tuple[list[InboundMail], dict]:
    """按通道分发；Gmail/Graph 轮询在 OAuth 向导接入后启用（同一返回契约）。"""
    if mailbox.channel == "smtp_imap":
        return poll_imap(mailbox)
    # gmail: history.list(startHistoryId) / graph: delta —— OAuth 接入后实现
    return [], mailbox.poll_cursor or {}
