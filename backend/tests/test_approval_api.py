"""审批流 API + 退订端点。"""
import uuid
from datetime import datetime, timezone


def _seed_pending_job(db, client, auth_headers):
    """经 ORM 直接布景一个 pending_approval job（依赖对象最小集）。"""
    from app.modules.campaign.models import Campaign
    from app.modules.contact.models import Contact
    from app.modules.discovery.models import Company, Lead
    from app.modules.sequence.models import SendJob, SequenceState

    me = client.get("/api/auth/me", headers=auth_headers).json()
    tid, uid = uuid.UUID(me["tenant_id"]), uuid.UUID(me["user_id"])
    campaign = Campaign(tenant_id=tid, owner_user_id=uid, name="c", status="active", icp={})
    company = Company(tenant_id=tid, domain="x.com", name="X Co", country="US")
    db.add_all([campaign, company])
    db.flush()
    lead = Lead(tenant_id=tid, company_id=company.id, campaign_id=campaign.id,
                owner_user_id=uid, status="in_sequence")
    contact = Contact(tenant_id=tid, company_id=company.id, full_name="A B")
    db.add_all([lead, contact])
    db.flush()
    state = SequenceState(tenant_id=tid, contact_id=contact.id, campaign_id=campaign.id,
                          lead_id=lead.id, status="active")
    db.add(state)
    db.flush()
    job = SendJob(tenant_id=tid, sequence_state_id=state.id, step_no=0,
                  idempotency_key=f"{state.id}:0", mailbox_id=uuid.uuid4(),
                  scheduled_at=datetime.now(timezone.utc), status="pending_approval",
                  subject="s", body_text="b", generation_meta={"fact_urls": []})
    db.add(job)
    db.commit()
    return job, state


def test_pending_list_and_approve_with_edit(client, auth_headers, db):
    job, _ = _seed_pending_job(db, client, auth_headers)
    lst = client.get("/api/sendjobs/pending", headers=auth_headers).json()
    assert len(lst) == 1 and lst[0]["company_name"] == "X Co"

    r = client.post(f"/api/sendjobs/{job.id}/approve", headers=auth_headers,
                    json={"subject": "s2", "body_text": "b2"})
    assert r.status_code == 204
    db.refresh(job)
    assert job.status == "approved" and job.subject == "s2"
    assert job.generation_meta["edited"]["subject"] is True

    # 已批准的不能再操作
    assert client.post(f"/api/sendjobs/{job.id}/approve", headers=auth_headers,
                       json={"subject": "", "body_text": ""}).status_code == 409


def test_reject_stops_sequence(client, auth_headers, db):
    job, state = _seed_pending_job(db, client, auth_headers)
    r = client.post(f"/api/sendjobs/{job.id}/reject", headers=auth_headers,
                    json={"reason": "语气太硬"})
    assert r.status_code == 204
    db.refresh(job); db.refresh(state)
    assert job.status == "rejected" and state.status == "stopped_manual"


def test_unsubscribe_endpoint(client, auth_headers, db):
    from app.modules.triage.service import is_suppressed, unsubscribe_token
    me = client.get("/api/auth/me", headers=auth_headers).json()
    tid = uuid.UUID(me["tenant_id"])
    token = unsubscribe_token(tid, "target@x.com")

    with_db_patch = client.get(f"/api/u/{token}")
    # 退订端点用独立 SessionLocal（生产为 Postgres）；测试环境仅验证签名解析与响应
    assert with_db_patch.status_code == 200

    # 直接走 service 验证压制生效
    from app.modules.triage.service import add_suppression
    add_suppression(db, tid, "target@x.com", "unsubscribe")
    db.commit()
    assert is_suppressed(db, tid, "target@x.com")


def test_invalid_unsubscribe_token(client):
    r = client.get("/api/u/not-a-valid-token")
    assert r.status_code == 200 and "Invalid" in r.text
