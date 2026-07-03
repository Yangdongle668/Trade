"""应用层租户隔离：租户 A 的数据对租户 B 不可见/不可改。"""


def _register(client, email, company):
    r = client.post("/api/auth/register", json={
        "email": email, "password": "password1", "company_name": company})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_brandkit_isolated_between_tenants(client):
    h1 = _register(client, "t1@x.com", "T1")
    h2 = _register(client, "t2@x.com", "T2")

    r = client.post("/api/brandkit", headers=h1, json={
        "kind": "product", "title": "LED Track Light 20W",
        "content": {"moq": "200 units", "cert": "ETL"}})
    assert r.status_code == 201
    asset_id = r.json()["id"]

    assert len(client.get("/api/brandkit", headers=h1).json()) == 1
    assert client.get("/api/brandkit", headers=h2).json() == []

    # 跨租户改/删 → 404
    r = client.put(f"/api/brandkit/{asset_id}", headers=h2, json={
        "kind": "product", "title": "hijack", "content": {}})
    assert r.status_code == 404
    assert client.delete(f"/api/brandkit/{asset_id}", headers=h2).status_code == 404


def test_campaigns_isolated(client):
    h1 = _register(client, "t1@x.com", "T1")
    h2 = _register(client, "t2@x.com", "T2")
    client.post("/api/campaigns", headers=h1, json={
        "name": "北美 LED 分销商", "icp": {"countries": ["US"], "industry_keywords": ["led lighting"]}})
    assert len(client.get("/api/campaigns", headers=h1).json()) == 1
    assert client.get("/api/campaigns", headers=h2).json() == []
