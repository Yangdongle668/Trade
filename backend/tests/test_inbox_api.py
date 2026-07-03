"""收件箱/回信/漏斗 API。"""
import uuid
from datetime import datetime, timezone
from unittest.mock import patch


def _seed_thread_with_reply(db, client, auth_headers, classification="interested",
                            lead_status="hot"):
    from app.modules.campaign.models import Campaign
    from app.modules.contact.models import Contact, EmailCandidate
    from app.modules.discovery.models import Company, Lead
    from app.modules.mailbox.models import Mailbox, Message, Thread
    from app.core.security import encrypt_secret

    me = client.get("/api/auth/me", headers=auth_headers).json()
    tid, uid = uuid.UUID(me["tenant_id"]), uuid.UUID(me["user_id"])
    campaign = Campaign(tenant_id=tid, owner_user_id=uid, name="c", status="active", icp={})
    company = Company(tenant_id=tid, domain="brightline.co.uk", name="Brightline", country="GB")
    db.add_all([campaign, company])
    db.flush()
    lead = Lead(tenant_id=tid, company_id=company.id, campaign_id=campaign.id,
                owner_user_id=uid, status=lead_status)
    contact = Contact(tenant_id=tid, company_id=company.id, full_name="James")
    db.add_all([lead, contact])
    db.flush()
    db.add(EmailCandidate(tenant_id=tid, contact_id=contact.id,
                          email="james@brightline.co.uk", confidence="high"))
    mailbox = Mailbox(tenant_id=tid, user_id=uid, email="wei@x.com", channel="smtp_imap",
                      credentials_enc=encrypt_secret("pw"),
                      smtp_imap_config={"smtp_host": "x"}, health="healthy")
    thread = Thread(tenant_id=tid, lead_id=lead.id, contact_id=contact.id, subject="Track")
    db.add_all([mailbox, thread])
    db.flush()
    db.add_all([
        Message(tenant_id=tid, thread_id=thread.id, mailbox_id=mailbox.id, direction="out",
                rfc_message_id="<o@x>", subject="Track", body_text="hello",
                sent_or_received_at=datetime.now(timezone.utc)),
        Message(tenant_id=tid, thread_id=thread.id, mailbox_id=mailbox.id, direction="in",
                rfc_message_id="<r@x>", subject="Re: Track",
                body_text="Please send catalog", classification=classification,
                classification_confidence=95,
                sent_or_received_at=datetime.now(timezone.utc)),
    ])
    db.commit()
    return thread, lead


def test_inbox_list_and_detail(client, auth_headers, db):
    thread, _ = _seed_thread_with_reply(db, client, auth_headers)
    lst = client.get("/api/inbox", headers=auth_headers).json()
    assert len(lst) == 1
    assert lst[0]["classification"] == "interested"
    assert lst[0]["lead_status"] == "hot"

    detail = client.get(f"/api/inbox/{thread.id}", headers=auth_headers).json()
    assert [m["direction"] for m in detail["messages"]] == ["out", "in"]


def test_inbox_filter(client, auth_headers, db):
    _seed_thread_with_reply(db, client, auth_headers, classification="rejected",
                            lead_status="rejected")
    assert client.get("/api/inbox?classification=interested", headers=auth_headers).json() == []
    assert len(client.get("/api/inbox?classification=rejected", headers=auth_headers).json()) == 1


def test_draft_and_send_reply_hands_off(client, auth_headers, db):
    thread, lead = _seed_thread_with_reply(db, client, auth_headers)
    with patch("app.modules.triage.inbox_router.invoke_json",
               return_value={"body": "Hi James, catalog attached."}):
        r = client.post(f"/api/inbox/{thread.id}/draft-reply", headers=auth_headers)
    assert r.status_code == 200 and "catalog" in r.json()["body"]

    with patch("app.modules.triage.inbox_router.get_channel") as mock_ch:
        r2 = client.post(f"/api/inbox/{thread.id}/send-reply", headers=auth_headers,
                         json={"body": "Hi James, here is the catalog."})
    assert r2.status_code == 204
    sent_mail = mock_ch.return_value.send.call_args[0][1]
    assert sent_mail.in_reply_to == "<r@x>"        # 线程化
    db.refresh(lead)
    assert lead.status == "handed_off"              # 热线索交接完成


def test_funnel_report(client, auth_headers, db):
    _seed_thread_with_reply(db, client, auth_headers)
    f = client.get("/api/reports/funnel", headers=auth_headers).json()
    assert f["leads_total"] == 1 and f["hot"] == 1 and f["replied"] == 1
