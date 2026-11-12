import csv
import io
import json

from fastapi.testclient import TestClient

from adef.api.app import app
from adef.config import DEMO_DATA_DIR
from adef.connectors import jira_export
from adef.demo_data import build_pack, generate
from adef.engine.scenarios import SCENARIOS
from adef.modeling import importers
from conftest import drive

c = TestClient(app)


def test_generator_is_deterministic_and_complete(tmp_path):
    m1 = generate(tmp_path / "a")
    m2 = generate(tmp_path / "b")
    assert m1 == m2
    for pack in SCENARIOS:
        folders = {k.split("/")[1] for k in m1 if k.startswith(pack + "/") and k.count("/") >= 2}
        assert folders - {"client-demo-kit"} == {"jira", "source-metadata", "source-data", "model", "catalog", "lineage"}


def test_committed_demo_data_is_current():
    from adef.demo_kit import KITS, build_kit
    from adef.util import sha256_text
    manifest = json.loads((DEMO_DATA_DIR / "manifest.json").read_text())
    expected = {f"{p}/{r}": c for p in SCENARIOS for r, c in build_pack(p).items()}
    expected.update({f"{p}/client-demo-kit/{r}": c for p in KITS for r, c in build_kit(p).items()})
    for key, content in expected.items():
        assert manifest[key]["sha256"] == sha256_text(content), f"regenerate demo-data: {key}"
        assert (DEMO_DATA_DIR / key).read_bytes() == content.encode(), f"regenerate demo-data: {key}"


def test_jira_exports_round_trip():
    for pack, proj in (("utilities", "UTIL"), ("retail", "RET")):
        files = build_pack(pack)
        from_csv = jira_export.parse("x.csv", files[f"jira/{proj}-jira-export.csv"])
        from_json = jira_export.parse("x.json", files[f"jira/{proj}-jira-export.json"])
        assert [i["key"] for i in from_csv] == [i["key"] for i in from_json]
        stories = [i for i in from_csv if i["type"] == "Story" and "nfr" not in i["labels"] and i["acceptance_criteria"]]
        assert len(stories) == len(SCENARIOS[pack]["requirements"])
        assert all(a for i in from_json if i["type"] == "Story" for a in i["acceptance_criteria"])
        assert any(i["untrusted_findings"]["injection"] for i in from_csv)


def test_source_data_keys_join():
    files = build_pack("utilities")

    def rows(name):
        return list(csv.DictReader(io.StringIO(files[f"source-data/{name}.csv"])))
    accounts = {r["account_id"] for r in rows("cis__account")}
    orphans = [b for b in rows("cis__bill") if b["account_id"] not in accounts]
    assert len(orphans) == 1  # the planted DQ-003 anomaly
    meters = {r["meter_id"] for r in rows("mdm__meter")}
    assert all(r["meter_id"] in meters for r in rows("mdm__daily_read"))
    assert all("@example.com" in r["email"] for r in csv.DictReader(io.StringIO(build_pack("retail")["source-data/crm__customer.csv"])))


def test_model_exports_reimport():
    files = build_pack("telco")
    for name in ("model/telco-churn.model.dbml", "model/telco-churn.ddl.snowflake.sql", "model/telco-churn.data-dictionary.csv"):
        assert importers.detect_and_parse(name, files[name])["stats"]["tables"] == 3


def test_api_demo_files_and_jira_import():
    files = c.get("/api/demo-files").json()
    assert any(f["path"].endswith("UTIL-jira-export.csv") for f in files)
    assert c.get("/api/demo-files/file", params={"path": "../README.md"}).status_code == 404
    text = c.get("/api/demo-files/file", params={"path": "telco/jira/TEL-jira-export.json"}).text
    issues = c.post("/api/jira/import", files={"file": ("TEL.json", text, "application/json")}).json()
    assert issues[0]["key"] == "TEL-1"


def test_run_from_demo_files_with_multi_vendor_fallback(engine):
    r = c.post("/api/settings/agents/preset", json={"preset": "multi-vendor"})
    assert r.status_code == 200
    providers = {a["provider_id"] for a in r.json()["agents"].values()}
    assert len(providers) >= 6
    files = build_pack("utilities")
    issues = jira_export.parse("u.csv", files["jira/UTIL-jira-export.csv"])
    meta = importers.detect_and_parse("utilities-source-catalog.csv", files["source-metadata/utilities-source-catalog.csv"])
    rid = engine.create_run({"client_code": "DEMO", "domain_pack": "utilities", "jira_issues": issues, "source_metadata": meta})["run_id"]
    st = drive(engine, rid)
    assert "has no API key configured" in st["usage"]["adef-intent-requirements"]["fallback"]
    mp = engine.ws(rid).read_json("02-mapping/mapping.json")
    assert not [m for m in mp["mappings"] if m["confidence"] == "low"]
    c.post("/api/settings/agents/preset", json={"preset": "simulator"})
