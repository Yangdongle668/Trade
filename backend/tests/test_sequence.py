"""序列引擎不变量测试：幂等、回复即停、频控、压制、日限、推进。"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.core.security import encrypt_secret
from app.modules.campaign.models import Campaign
from app.modules.contact.models import Contact, EmailCandidate
from app.modules.discovery.models import Company, Lead
from app.modules.mailbox.channels.base import HardBounceError, MailChannel
from app.modules.mailbox.models import Mailbox
from app.modules.sequence import service
from app.modules.sequence.generator import DraftResult
from app.modules.sequence.models import SendJob, SequenceState
from app.modules.sequence.service import EnrollError, enroll_lead, execute_send
from app.modules.triage.models import SuppressionEntry
from app.modules.triage.service import add_suppression

TENANT = uuid.uuid4()
OWNER = uuid.uuid4()


class FakeChannel(MailChannel):
    name = "smtp_imap"
    sent: list = []
    fail_hard = False

    def send(self, mailbox, mail):
        if FakeChannel.fail_hard:
            raise HardBounceError("user unknown")
        FakeChannel.sent.append(mail)


@pytest.fixture()
def world(db):
    """租户 + Campaign + 公司 + ready 线索 + 联系人(高置信邮箱) + healthy 邮箱。"""
    FakeChannel.sent, FakeChannel.fail_hard = [], False
    campaign = Campaign(tenant_id=TENANT, owner_user_id=OWNER, name="t", status="active",
                        automation_level="full_auto",
                        icp={"countries": ["US"], "industry_keywords": ["led"]})
    company = Company(tenant_id=TENANT, domain="harborhale.com", name="Harbor & Hale",
                      country="US")
    db.add_all([campaign, company])
    db.flush()
    lead = Lead(tenant_id=TENANT, company_id=company.id, campaign_id=campaign.id,
                owner_user_id=OWNER, status="ready", score=91)
    contact = Contact(tenant_id=TENANT, company_id=company.id, full_name="Megan Cho",
                      role_title="Co-founder")
    db.add_all([lead, contact])
    db.flush()
    db.add(EmailCandidate(tenant_id=TENANT, contact_id=contact.id,
                          email="megan.cho@harborhale.com", confidence="high",
                          verify_status="valid"))
    mailbox = Mailbox(tenant_id=TENANT, user_id=OWNER, email="wei@reachout.com",
                      channel="smtp_imap", credentials_enc=encrypt_secret("pw"),
                      smtp_imap_config={"smtp_host": "x"}, health="healthy",
                      warmup_day=21, daily_limit=20)
    db.add(mailbox)
    db.commit()
    return {"db": db, "campaign": campaign, "lead": lead, "contact": contact,
            "mailbox": mailbox, "company": company}


GOOD_DRAFT = DraftResult(ok=True, subject="Track lighting for your showroom",
                         body="Hi Megan, congrats on the new showroom. Worth a line sheet?")


def _tick(db, now=None):
    with patch("app.modules.sequence.service.generate_email", return_value=GOOD_DRAFT), \
         patch("app.modules.sequence.tasks.execute_send_job"):
        return service.tick(db, now=now or datetime.now(timezone.utc))


def test_enroll_and_tick_idempotent(world):
    db = world["db"]
    state = enroll_lead(db, world["lead"], world["mailbox"])
    db.commit()
    assert world["lead"].status == "in_sequence"

    stats1 = _tick(db)
    assert stats1["jobs_created"] == 1
    stats2 = _tick(db)  # 再 tick：幂等键 + next_action_at=None，不产生重复 job
    assert stats2["jobs_created"] == 0
    assert db.query(SendJob).count() == 1
    job = db.query(SendJob).one()
    assert job.status == "approved"  # full_auto
    assert job.idempotency_key == f"{state.id}:0"


def test_global_frequency_blocks_second_sequence(world):
    db = world["db"]
    enroll_lead(db, world["lead"], world["mailbox"])
    db.commit()
    # 同联系人在另一 Campaign 30 天内再入队 → 拒绝
    c2 = Campaign(tenant_id=TENANT, owner_user_id=OWNER, name="t2", status="active",
                  icp={})
    db.add(c2)
    db.flush()
    lead2 = Lead(tenant_id=TENANT, company_id=world["company"].id, campaign_id=c2.id,
                 owner_user_id=OWNER, status="ready")
    db.add(lead2)
    db.commit()
    with pytest.raises(EnrollError, match="30 天内"):
        enroll_lead(db, lead2, world["mailbox"])


def test_suppressed_contact_cannot_enroll(world):
    db = world["db"]
    add_suppression(db, TENANT, "megan.cho@harborhale.com", "unsubscribe")
    db.commit()
    with pytest.raises(EnrollError, match="压制"):
        enroll_lead(db, world["lead"], world["mailbox"])


@patch("app.modules.sequence.service.get_channel", return_value=FakeChannel())
def test_execute_sends_and_advances(mock_ch, world):
    db = world["db"]
    state = enroll_lead(db, world["lead"], world["mailbox"])
    db.commit()
    _tick(db)
    job = db.query(SendJob).one()
    job.status = "queued"
    db.commit()

    assert execute_send(db, job.id) == "sent"
    assert len(FakeChannel.sent) == 1
    mail = FakeChannel.sent[0]
    assert mail.to_email == "megan.cho@harborhale.com"
    assert "/api/u/" in mail.unsubscribe_url  # 退订链接注入
    db.refresh(state)
    assert state.current_step == 1            # 推进到第 2 步
    assert state.next_action_at is not None   # 3 天后


@patch("app.modules.sequence.service.get_channel", return_value=FakeChannel())
def test_execute_cancels_if_suppressed_between(mock_ch, world):
    """三重校验 ①：排队后、发送前被退订 → 取消而非发送。"""
    db = world["db"]
    enroll_lead(db, world["lead"], world["mailbox"])
    db.commit()
    _tick(db)
    job = db.query(SendJob).one()
    job.status = "queued"
    db.add(SuppressionEntry(tenant_id=TENANT, value="megan.cho@harborhale.com",
                            kind="email", reason="unsubscribe"))
    db.commit()
    assert execute_send(db, job.id) == "canceled:suppressed"
    assert FakeChannel.sent == []


@patch("app.modules.sequence.service.get_channel", return_value=FakeChannel())
def test_execute_defers_when_daily_limit_hit(mock_ch, world):
    """三重校验 ③：日限用尽 → 顺延不发送。"""
    db = world["db"]
    enroll_lead(db, world["lead"], world["mailbox"])
    db.commit()
    _tick(db)
    job = db.query(SendJob).one()
    job.status = "queued"
    db.commit()
    from app.modules.mailbox.service import record_send
    for _ in range(20):
        record_send(db, world["mailbox"])
    db.commit()
    assert execute_send(db, job.id).startswith("deferred")
    assert FakeChannel.sent == []


@patch("app.modules.sequence.service.get_channel", return_value=FakeChannel())
def test_hard_bounce_suppresses_and_fails_job(mock_ch, world):
    db = world["db"]
    enroll_lead(db, world["lead"], world["mailbox"])
    db.commit()
    _tick(db)
    job = db.query(SendJob).one()
    job.status = "queued"
    db.commit()
    FakeChannel.fail_hard = True
    assert execute_send(db, job.id) == "failed:hard_bounce"
    from app.modules.triage.service import is_suppressed
    assert is_suppressed(db, TENANT, "megan.cho@harborhale.com")


def test_reply_stops_all_pending(world):
    """不变量 1：回复 → 序列停 + 在途 job 全取消。"""
    db = world["db"]
    state = enroll_lead(db, world["lead"], world["mailbox"])
    db.commit()
    _tick(db)
    stopped = service.stop_sequences_for_contacts(db, TENANT, [world["contact"].id], "replied")
    db.commit()
    assert stopped == 1
    db.refresh(state)
    assert state.status == "stopped_replied"
    assert db.query(SendJob).filter_by(status="canceled").count() == 1
