"""汇总导入全部 ORM 模型：Alembic autogenerate 与开发建表的唯一入口。"""
from app.modules.audit.models import Event  # noqa: F401
from app.modules.brandkit.models import BrandAsset  # noqa: F401
from app.modules.campaign.models import Campaign  # noqa: F401
from app.modules.contact.models import Contact, EmailCandidate  # noqa: F401
from app.modules.discovery.models import Company, Lead, ResearchFact, SourceRun  # noqa: F401
from app.modules.identity.models import Membership, Tenant, User  # noqa: F401
from app.modules.mailbox.models import Mailbox, Message, Thread  # noqa: F401
from app.modules.quota.models import UsageCounter  # noqa: F401
from app.modules.sequence.models import SendJob, SequenceState  # noqa: F401
from app.modules.triage.models import SuppressionEntry  # noqa: F401
