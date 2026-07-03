def test_register_login_me(client):
    r = client.post("/api/auth/register", json={
        "email": "a@b.com", "password": "password1", "company_name": "T1"})
    assert r.status_code == 200
    token = r.json()["access_token"]

    r2 = client.post("/api/auth/login", json={"email": "a@b.com", "password": "password1"})
    assert r2.status_code == 200

    r3 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r3.status_code == 200
    assert r3.json()["email"] == "a@b.com"
    assert r3.json()["role"] == "admin"


def test_duplicate_email_rejected(client):
    body = {"email": "a@b.com", "password": "password1", "company_name": "T1"}
    assert client.post("/api/auth/register", json=body).status_code == 200
    assert client.post("/api/auth/register", json=body).status_code == 409


def test_wrong_password(client):
    client.post("/api/auth/register", json={
        "email": "a@b.com", "password": "password1", "company_name": "T1"})
    r = client.post("/api/auth/login", json={"email": "a@b.com", "password": "wrong"})
    assert r.status_code == 401


def test_me_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401
