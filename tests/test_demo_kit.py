"""The Telco client demo kit: every file uploads where the README says, and a run built from it completes."""
import io
import zipfile

from fastapi.testclient import TestClient

from adef.api.app import app
from adef.config import DEMO_DATA_DIR
from conftest import drive

c = TestClient(app)
KIT = DEMO_DATA_DIR / "telco" / "client-demo-kit"


def upload(endpoint, name):
    return c.post(endpoint, files={"file": (name, (KIT / name).read_bytes(), "text/plain")})


def test_kit_files_upload_where_the_readme_says():
    readme = (KIT / "00-README.md").read_text()
    names = sorted(p.name for p in KIT.iterdir())
    assert names[0] == "00-README.md" and len(names) == 8
    assert all(n in readme for n in names[1:])
    for name in ("02-jira-export-TEL.csv", "03-jira-export-TEL.json"):
        issues = upload("/api/jira/import", name).json()
        assert len(issues) == 13 and [i["key"] for i in issues if i["untrusted_findings"]["injection"]] == ["TEL-7"]
    for name in ("04-catalog-export-source-systems.csv", "05-source-model-erwin.sql", "06-source-model.dbml"):
        meta = upload("/api/metadata/import", name).json()
        assert meta["stats"] == {"tables": 5, "columns": 32}
    legacy = upload("/api/metadata/import", "07-legacy-warehouse-model.sql").json()["logical_model"]
    r = c.post("/api/models/export", json={"model": legacy, "format": "ddl", "dialect": "databricks"})
    assert r.status_code == 200 and "USING DELTA" in r.text


def test_kit_downloads_as_zip():
    r = c.get("/api/demo-files/zip", params={"folder": "telco/client-demo-kit"})
    assert r.status_code == 200
    assert len(zipfile.ZipFile(io.BytesIO(r.content)).namelist()) == 8
    assert c.get("/api/demo-files/zip", params={"folder": "../.."}).status_code == 404


def test_run_from_the_kit_as_a_presenter_would(engine):
    issues = upload("/api/jira/import", "02-jira-export-TEL.csv").json()
    meta = upload("/api/metadata/import", "04-catalog-export-source-systems.csv").json()
    meta.pop("logical_model")
    r = c.post("/api/runs", json={"client_code": "NIMBUS-MOBILE", "domain_pack": "telco", "stack_profile": "example-b",
                                  "request": (KIT / "01-business-request.md").read_text(), "jira_issues": issues,
                                  "source_metadata": meta})
    rid = r.json()["run_id"]
    drive(engine, rid)
    ws = engine.ws(rid)
    assert "TEL-7" in ws.read("00-intake/intake-brief.md").split("Untrusted content findings")[1]
    open_items = ws.read("01-requirements/open-items.md")
    assert "ARPU by region and sales channel" in open_items and "Churn propensity score" in open_items
    mp = ws.read_json("02-mapping/mapping.json")
    assert {m["confidence"] for m in mp["mappings"] if m["source"] != "derived"} == {"high"}
    assert ws.read("final/traceability-matrix.csv").count(",pass") == 5
