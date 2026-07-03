"""Campaign 创建 → 预跑启动的 API 流程（发现任务入队 mock 掉）。"""
from unittest.mock import patch


def test_create_and_start_dry_run(client, auth_headers):
    r = client.post("/api/campaigns", headers=auth_headers, json={
        "name": "北美 LED 轨道灯分销商",
        "icp": {"countries": ["US"], "industry_keywords": ["led track lighting"],
                "company_types": ["distributor"], "freeform": "要有实体门店"},
        "automation_level": "per_email",
    })
    assert r.status_code == 201
    cid = r.json()["id"]
    assert r.json()["status"] == "draft"

    with patch("app.modules.discovery.tasks.run_campaign.delay") as mock_delay:
        r2 = client.post(f"/api/campaigns/{cid}/start-dry-run", headers=auth_headers)
    assert r2.status_code == 200
    assert r2.json()["status"] == "dry_run"
    mock_delay.assert_called_once_with(cid)

    # 重复启动 → 409
    r3 = client.post(f"/api/campaigns/{cid}/start-dry-run", headers=auth_headers)
    assert r3.status_code == 409


def test_dry_run_requires_icp_keywords(client, auth_headers):
    r = client.post("/api/campaigns", headers=auth_headers,
                    json={"name": "空 ICP", "icp": {}})
    cid = r.json()["id"]
    assert client.post(f"/api/campaigns/{cid}/start-dry-run",
                       headers=auth_headers).status_code == 422


def test_invalid_automation_level(client, auth_headers):
    r = client.post("/api/campaigns", headers=auth_headers,
                    json={"name": "x", "automation_level": "yolo"})
    assert r.status_code == 422
