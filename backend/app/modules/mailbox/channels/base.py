"""三通道统一契约（ADR-8）：序列引擎对通道差异无感知。"""
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.modules.mailbox.models import Mailbox


class ChannelError(Exception):
    """发送失败（可重试）。"""


class HardBounceError(ChannelError):
    """确定性投递失败（地址不存在等）：不重试，计入退信并压制。"""


@dataclass
class OutgoingMail:
    to_email: str
    subject: str
    body_text: str
    rfc_message_id: str          # 由调用方预生成，保证线程化与幂等追踪
    in_reply_to: str = ""
    unsubscribe_url: str = ""    # 注入 List-Unsubscribe 头 + 文末链接（合规）
    footer: str = ""             # 公司落款（CAN-SPAM 物理地址）


class MailChannel(ABC):
    name: str = "base"

    @abstractmethod
    def send(self, mailbox: Mailbox, mail: OutgoingMail) -> None:
        """成功返回 None；失败抛 ChannelError / HardBounceError。"""


def new_rfc_message_id(domain_hint: str) -> str:
    return f"<{uuid.uuid4().hex}@{domain_hint or 'outreach.local'}>"
