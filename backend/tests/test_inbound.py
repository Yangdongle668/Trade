"""入向处理：归属/去重/分类→状态流转/退订/自动回复不停序列。"""
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from unittest.mock import patch

import pytest

from app.core.security import encrypt_secret
from app.modules.campaign.models import Campaign
from app.modules.contact.models import Contact, EmailCandidate
from app.modules.discovery.models import Company, Lead
from app.modules.mailbox.inbound import InboundMail, parse_mime
from app.modules.mailbox.models import Mailbox, Message, Thread
from app.modules.sequence.models import SendJob, SequenceState
from app.modules.triage.processor import process_inbound
from app.modules.triage.service import is_suppressed

TENANT = uuid.uuid4()
OWNER = uuid.uuid4()
OUT_MSG_ID = "<out123@reachout.com>"


def test_parse_mime_plain():
    m = EmailMessage()
    m["From"] = "James Holloway <james@brightline.co.uk>"
    m["Subject"] = "Re: Track lighting"
    m["Message-ID"] = "<abc@mail.brightline.co.uk>"
    m["In-Reply-To"] = OUT_MSG_ID
    m.set_content("Please send your catalog and price list.")
    parsed = parse_mime(m.as_bytes())
    assert parsed.from_email == "james@brightline.co.uk"
    assert parsed.in_reply_to == OUT_MSG_ID
    assert "catalog" in parsed.body_text


@pytest.fixture()
def world(db):
    campaign = Campaign(tenant_id=TENANT, owner_user_id=OWNER, name="t", status="active", icp={})
    company = Company(tenant_id=TENANT, domain="brightline.co.uk", name="Brightline",
                      country="GB")
    db.add_all([campaign, company])
    db.flush()
    lead = Lead(tenant_id=TENANT, company_id=company.id, campaign_id=campaign.id,
                owner_user_id=OWNER, status="in_sequence")
    contact = Contact(tenant_id=TENANT, company_id=company.id, full_name="James Holloway")
    db.add_all([lead, contact])
    db.flush()
    db.add(EmailCandidate(tenant_id=TENANT, contact_id=contact.id,
                          email="james@brightline.co.uk", confidence="high"))
    mailbox = Mailbox(tenant_id=TENANT, user_id=OWNER, email="wei@reachout.com",
                      channel="smtp_imap", credentials_enc=encrypt_secret("pw"),
                      health="healthy")
    thread = Thread(tenant_id=TENANT, lead_id=lead.id, contact_id=contact.id, subject="Track")
    db.add_all([mailbox, thread])
    db.flush()
    # 已发出的第 1 步 + 在途的第 2 步（用于验证回复取消在途）
    state = SequenceState(tenant_id=TENANT, contact_id=contact.id, campaign_id=campaign.id,
                          lead_id=lead.id, status="active", current_step=1)
    db.add(state)
    db.flush()
    db.add_all([
        Message(tenant_id=TENANT, thread_id=thread.id, mailbox_id=mailbox.id,
                direction="out", rfc_message_id=OUT_MSG_ID, subject="Track",
                body_text="…", sent_or_received_at=datetime.now(timezone.utc)),
        SendJob(tenant_id=TENANT, sequence_state_id=state.id, step_no=1,
                idempotency_key=f"{state.id}:1", mailbox_id=mailbox.id,
                scheduled_at=datetime.now(timezone.utc), status="approved",
                subject="s", body_text="b"),
    ])
    db.commit()
    return {"db": db, "lead": lead, "mailbox": mailbox, "state": state, "thread": thread}


def _mail(body: str, msg_id: str = "<r1@brightline.co.uk>") -> InboundMail:
    return InboundMail(from_email="james@brightline.co.uk", subject="Re: Track",
                       body_text=body, rfc_message_id=msg_id, in_reply_to=OUT_MSG_ID)


def _classified(category: str, confidence: int = 95):
    return patch("app.modules.triage.processor.invoke_json",
                 return_value={"category": category, "confidence": confidence,
                               "summary_zh": "摘要"})


def test_interested_reply_makes_hot_and_stops_sequence(world):
    db = world["db"]
    with _classified("interested"):
        assert process_inbound(db, world["mailbox"], _mail("Send catalog please")) == "interested"
    db.refresh(world["lead"]); db.refresh(world["state"])
    assert world["lead"].status == "hot"
    assert world["state"].status == "stopped_replied"          # 不变量 1
    assert db.query(SendJob).filter_by(status="canceled").count() == 1


def test_dedup_by_message_id(world):
    db = world["db"]
    with _classified("interested"):
        process_inbound(db, world["mailbox"], _mail("hi", "<same@x>"))
        assert process_inbound(db, world["mailbox"], _mail("hi", "<same@x>")) == "dup"


def test_auto_reply_does_not_stop_sequence(world):
    db = world["db"]
    with _classified("auto_reply"):
        process_inbound(db, world["mailbox"], _mail("Out of office until July 14"))
    db.refresh(world["state"]); db.refresh(world["lead"])
    assert world["state"].status == "active"                    # 序列继续
    assert world["lead"].status == "in_sequence"


def test_unsubscribe_keyword_suppresses(world):
    db = world["db"]
    with _classified("rejected"):  # 即便分类器没识别为 unsubscribe，关键词兜底
        process_inbound(db, world["mailbox"], _mail("Please remove me from your list"))
    assert is_suppressed(db, TENANT, "james@brightline.co.uk")
    db.refresh(world["lead"])
    assert world["lead"].status == "rejected"


def test_later_reply_marks_nurturing(world):
    db = world["db"]
    with _classified("later"):
        process_inbound(db, world["mailbox"], _mail("Try us again in Q4"))
    db.refresh(world["lead"])
    assert world["lead"].status == "nurturing"


def test_low_confidence_goes_unclassified(world):
    db = world["db"]
    with _classified("interested", confidence=40):
        assert process_inbound(db, world["mailbox"], _mail("hmm")) == "unclassified"
    db.refresh(world["lead"])
    assert world["lead"].status == "replied"  # 保守：转人工分拣


def test_unmatched_sender_ignored(world):
    db = world["db"]
    mail = InboundMail(from_email="stranger@nowhere.com", subject="spam",
                       body_text="buy now", rfc_message_id="<z@x>")
    assert process_inbound(db, world["mailbox"], mail) == "unmatched"
