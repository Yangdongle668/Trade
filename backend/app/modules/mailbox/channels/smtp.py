"""通用 SMTP 通道：企业邮箱（阿里/腾讯/Zoho/自建）商用刚需（ADR-8 修订）。"""
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate

from app.core.security import decrypt_secret
from app.modules.mailbox.channels.base import (ChannelError, HardBounceError, MailChannel,
                                               OutgoingMail)
from app.modules.mailbox.models import Mailbox

# 常见企业邮箱预设（接入向导用，架构 §7）
SMTP_PRESETS = {
    "aliyun": {"host": "smtp.qiye.aliyun.com", "port": 465, "ssl": True},
    "tencent": {"host": "smtp.exmail.qq.com", "port": 465, "ssl": True},
    "zoho": {"host": "smtp.zoho.com", "port": 465, "ssl": True},
    "netease": {"host": "smtphz.qiye.163.com", "port": 465, "ssl": True},
    "gmail_app_password": {"host": "smtp.gmail.com", "port": 587, "ssl": False},
    "outlook_app_password": {"host": "smtp.office365.com", "port": 587, "ssl": False},
}


def build_message(mailbox_email: str, mail: OutgoingMail) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = mailbox_email
    msg["To"] = mail.to_email
    msg["Subject"] = mail.subject
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = mail.rfc_message_id
    if mail.in_reply_to:
        msg["In-Reply-To"] = mail.in_reply_to
        msg["References"] = mail.in_reply_to
    if mail.unsubscribe_url:
        msg["List-Unsubscribe"] = f"<{mail.unsubscribe_url}>"
    body = mail.body_text
    if mail.footer or mail.unsubscribe_url:
        body += "\n\n--\n" + mail.footer
        if mail.unsubscribe_url:
            body += f"\nUnsubscribe: {mail.unsubscribe_url}"
    msg.set_content(body)
    return msg


class SmtpChannel(MailChannel):
    name = "smtp_imap"

    def send(self, mailbox: Mailbox, mail: OutgoingMail) -> None:
        cfg = mailbox.smtp_imap_config or {}
        host, port = cfg.get("smtp_host"), int(cfg.get("smtp_port", 465))
        use_ssl = bool(cfg.get("smtp_ssl", True))
        if not host:
            raise ChannelError("SMTP 未配置主机")
        password = decrypt_secret(mailbox.credentials_enc)
        msg = build_message(mailbox.email, mail)
        try:
            if use_ssl:
                server = smtplib.SMTP_SSL(host, port, timeout=30,
                                          context=ssl.create_default_context())
            else:
                server = smtplib.SMTP(host, port, timeout=30)
                server.starttls(context=ssl.create_default_context())
            with server:
                server.login(mailbox.email, password)
                server.send_message(msg)
        except smtplib.SMTPRecipientsRefused as e:
            raise HardBounceError(f"收件人被拒: {e}") from e
        except (smtplib.SMTPException, OSError) as e:
            raise ChannelError(f"SMTP 发送失败: {e}") from e
