from fastapi.testclient import TestClient

from adpe.api.app import app

c = TestClient(app)


def test_catalog_and_health():
    assert c.get("/api/health").json()["ok"]
    cat = c.get("/api/catalog").json()
    assert len(cat["agents"]) == 9 and len(cat["presets"]) == 5 and len(cat["exporters"]) >= 15
    assert {p["pack_id"] for p in cat["domain_packs"]} >= {"utilities", "telco", "financial-services", "retail"}


def test_secrets_are_write_only():
    r = c.post("/api/secrets", json={"name": "k1", "value": "sk-ant-" + "api03-SECRETSECRETSECRET9999"})
    assert r.status_code == 200 and "SECRET" not in r.text
    assert "SECRETSECRET" not in c.get("/api/secrets").text
    bad = c.put("/api/settings/providers", json=[{"id": "demo", "type": "simulator", "label": "s"},
                                                 {"id": "x", "type": "anthropic", "label": "x", "api_key_ref": "sk-ant-literal"}])
    assert bad.status_code == 400


def test_agent_binding_validation():
    r = c.put("/api/settings/agents", json={"adpe-solution-design": {"provider_id": "nope", "model": "m"}})
    assert r.status_code == 400
    r = c.put("/api/settings/agents", json={"adpe-solution-design": {"provider_id": "demo", "model": "adpe-simulator-1", "effort": "high"}})
    assert r.status_code == 200 and r.json()["adpe-solution-design"]["effort"] == "high"


def test_jira_demo_and_metadata_import():
    issues = c.post("/api/jira/search", json={"jql": "project = RET"}).json()
    assert issues and all(i["key"].startswith("RET-") for i in issues)
    csv = "table_name,column_name,data_type,is_nullable,primary_key\norders,order_id,varchar(20),N,Y\norders,amount,decimal(12,2),Y,\n"
    meta = c.post("/api/metadata/import", files={"file": ("dict.csv", csv, "text/csv")}).json()
    assert meta["stats"] == {"tables": 1, "columns": 2}
    model = meta["logical_model"]
    r = c.post("/api/models/export", json={"model": model, "format": "ddl", "dialect": "snowflake"})
    assert r.status_code == 200 and "CREATE TABLE" in r.text


def test_create_run_rejects_secret():
    r = c.post("/api/runs", json={"request": "use token " + "gh" + "p_abcdefghijklmnopqrstuvwxyz0123456789"})
    assert r.status_code == 422 and "Rotate" in r.json()["detail"]
