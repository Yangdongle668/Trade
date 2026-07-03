from app.modules.mailbox.channels.base import ChannelError, MailChannel

_REGISTRY: dict[str, MailChannel] = {}


def get_channel(name: str) -> MailChannel:
    if not _REGISTRY:
        from app.modules.mailbox.channels.gmail import GmailChannel
        from app.modules.mailbox.channels.graph import GraphChannel
        from app.modules.mailbox.channels.smtp import SmtpChannel
        _REGISTRY.update({c.name: c for c in (SmtpChannel(), GmailChannel(), GraphChannel())})
    channel = _REGISTRY.get(name)
    if channel is None:
        raise ChannelError(f"未知通道 {name}")
    return channel
