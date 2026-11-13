"""Medallion architecture: stack model, synthetic sources, local pipeline execution, cloud codegen, hosting."""
import ast
import json
import sqlite3
from argparse import Namespace

import pytest
import yaml
from fastapi.testclient import TestClient

from adef import sources
from adef.api.app import app
from adef.catalog import stacks
from adef.engine.agents_front import _model_from_mapping
from adef.engine.codegen import CodeGen
from adef.engine.scenarios import SCENARIOS, scenario_mapping
from adef.lakehouse.runner import LocalLakehouse, _one, query_serving
from conftest import drive

c = TestClient(app)


def model_and_mapping(pack):
    mp = scenario_mapping(pack)
    return _model_from_mapping(mp, pack, pack, SCENARIOS[pack]["metrics"]), mp


# ------------------------------------------------------------------ stack model
def test_presets_cover_three_hyperscalers_and_local():
    clouds = {stacks.tool(p, "cloud") for p in stacks.PRESETS}
    assert clouds == {"aws", "azure", "gcp", "local"}
    assert {stacks.tool(p, "source_database") for p in stacks.PRESETS} >= {"oracle", "db2"}
    assert {stacks.tool(p, "table_format") for p in stacks.PRESETS} == {"iceberg", "delta"}
    for p in stacks.PRESETS:
        v = stacks.validate(p)
        assert v["ok"], (p["profile_id"], v["blocking"])
        assert len(stacks.pipeline_summary(p)) == 3
    assert [p["profile_id"] for p in stacks.PRESETS if stacks.is_local(p)] == ["local-lakehouse"]


def test_cloud_mismatch_is_blocking():
    p = stacks.preset("example-a")
    p["slots"]["object_storage"] = {"tool": "adls"}          # Azure storage on an AWS stack
    v = stacks.validate(p)
    assert not v["ok"] and any("runs on azure" in b for b in v["blocking"])


# ------------------------------------------------------------------ synthetic sources
def test_seed_scripts_for_oracle_and_db2():
    ora, db2 = sources.ddl("telco", "oracle"), sources.ddl("telco", "db2")
    assert "NO AUTHENTICATION" in ora and "VARCHAR2" in ora and "IDENTIFIED BY" not in ora
    assert "CREATE SCHEMA CRM;" in db2 and "VARCHAR2" not in db2
    stmts = sources._statements(sources.inserts("telco", "oracle"))
    assert len(stmts) == sum(len(r) for r in sources.source_rows("telco").values())
    assert all(not s.endswith(";") for s in stmts[:5])


def test_sqlite_source_is_schema_qualified_and_has_watermark():
    con = sources.connect({"type": "sqlite-local", "pack": "telco"})
    assert "CRM.SUBSCRIBER" in con.tables()
    cols, rows = con.query("SELECT * FROM CRM.SUBSCRIBER LIMIT 1")
    assert sources.WATERMARK in cols and "email_address" in cols
    con.close()


# ------------------------------------------------------------------ local execution of the three pipelines
@pytest.mark.parametrize("pack,fmt", [("telco", "delta"), ("retail", "iceberg")])
def test_three_pipelines_execute(tmp_path, pack, fmt):
    model, mp = model_and_mapping(pack)
    rep = LocalLakehouse(tmp_path, "test", model, mp, {"type": "sqlite-local", "pack": pack}, fmt,
                         stacks.preset("local-lakehouse")).run_all("B1")
    assert rep["status"] == "passed"
    assert len(rep["layers"]["gold"]) == len(model["entities"])
    assert all(m["status"] == "pass" for m in rep["metrics"])
    restricted = [x for x in rep["layers"]["serving"] if x["masked_columns"]]
    q = query_serving(tmp_path / "analytics" / "test.duckdb", restricted[0]["table"].split(".")[1], 3)
    col = q["columns"].index(restricted[0]["masked_columns"][0])
    assert {r[col] for r in q["rows"]} == {"***"}


def test_planted_source_anomaly_is_a_dq_finding(tmp_path):
    model, mp = model_and_mapping("utilities")
    rep = LocalLakehouse(tmp_path, "test", model, mp, {"type": "sqlite-local", "pack": "utilities"}, "delta").run_all()
    assert rep["status"] == "passed-with-dq-findings"
    assert [(d["id"], d["failures"]) for d in rep["dq"] if d["status"] == "fail"] == [("DQ-003", 1)]


def test_incremental_extraction_picks_only_changed_rows(tmp_path):
    model, mp = model_and_mapping("telco")
    mk = lambda: LocalLakehouse(tmp_path, "rehearsal", model, mp, {"type": "sqlite-local", "pack": "telco"}, "delta")  # noqa: E731
    mk().run_all("B1")
    rerun = mk()
    rerun.ingest("B2")
    assert sum(x["rows_extracted"] for x in rerun.report["layers"]["bronze"]) == 0
    db = sources.sqlite_dir("telco") / "CRM.sqlite"
    con = sqlite3.connect(db)
    con.execute("UPDATE SUBSCRIBER SET STATUS = 'SUSPENDED', LAST_UPDATED_TS = '2026-12-31 00:00:00' WHERE SUBSCRIBER_ID = 'SUB000003'")
    con.commit()
    con.close()
    try:
        lh = mk()
        rep = lh.run_all("B3")
        extracted = {x["table"]: x["rows_extracted"] for x in rep["layers"]["bronze"]}
        assert extracted["crm.subscriber"] == 1 and sum(extracted.values()) == 1
        import duckdb
        an = duckdb.connect(str(tmp_path / "analytics" / "rehearsal.duckdb"), read_only=True)
        assert _one(an, "SELECT status FROM serving.dim_subscriber WHERE subscriber_id = 'SUB000003'") == "SUSPENDED"
        an.close()
    finally:
        sources.build_sqlite("telco", force=True)


# ------------------------------------------------------------------ cloud code generation
@pytest.mark.parametrize("pid", [p["profile_id"] for p in stacks.PRESETS])
def test_medallion_code_for_every_stack(pid):
    model, mp = model_and_mapping("telco")
    out = CodeGen(model, mp["mappings"], mp["dq_rules"], stacks.preset(pid), "RUN-T", mp["entity_filters"],
                  sources=mp["sources"]).generate()
    files = out["files"]
    for f in ("pipelines/01_ingest/ingest_config.yaml", "pipelines/02_curate/01_bronze_to_silver.sql",
              "pipelines/02_curate/02_silver_to_gold.sql", "pipelines/03_publish/publish.sql"):
        assert f in files, (pid, f)
    assert out["gaps"] == []
    for f, content in files.items():
        if f.endswith(".py"):
            ast.parse(content)
        elif f.endswith((".yml", ".yaml")):
            yaml.safe_load(content)
        elif f.endswith(".json"):
            json.loads(content)
    assert "MERGE INTO" in files["pipelines/02_curate/02_silver_to_gold.sql"]


# ------------------------------------------------------------------ full lifecycle on the local stack + API
def test_local_stack_releases_really_run(engine):
    rid = engine.create_run({"client_code": "LOCAL", "domain_pack": "telco", "stack_profile": "local-lakehouse"})["run_id"]
    drive(engine, rid)
    lk = c.get(f"/api/runs/{rid}/lakehouse").json()
    assert lk["executable_locally"] and set(lk["reports"]) == {"rehearsal", "test", "prod"}
    assert all(r["status"] == "passed" for r in lk["reports"].values())
    assert "real execution" in engine.ws(rid).read("06-release/REL-001-verification-prod.md")
    q = c.get(f"/api/runs/{rid}/lakehouse/query", params={"env": "prod", "table": "dim_subscriber", "limit": 2}).json()
    assert q["total_rows"] == 60 and "***" in q["rows"][0]
    assert c.get(f"/api/runs/{rid}/lakehouse/query", params={"env": "prod", "table": "x; drop"}).status_code == 400
    assert c.post(f"/api/runs/{rid}/lakehouse/rehearse").json()["status"] == "passed"


def test_cloud_stack_is_rehearsed_and_simulated(engine):
    rid = engine.create_run({"client_code": "CLOUD", "domain_pack": "retail", "stack_profile": "example-a"})["run_id"]
    drive(engine, rid)
    ws = engine.ws(rid)
    assert ws.has("05-test/rehearsal/lakehouse-report.json") and not ws.has("06-release/lakehouse-prod.json")
    assert "simulated" in ws.read("06-release/REL-001-verification-prod.md")
    assert "pipelines/03_publish/publish.sql" in c.get(f"/api/runs/{rid}/repo").json()["files"]


# ------------------------------------------------------------------ hosting
def test_env_keys_pick_team_and_are_not_persisted(tmp_path, monkeypatch):
    from adef.settings_store import SettingsStore
    for v in ("OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "ADEF_TEAM_PRESET"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-value-not-a-real-key")
    st = SettingsStore(tmp_path)
    data = st.load()
    assert data["runtime"]["team_preset"] == "all-claude"
    assert next(p for p in data["providers"] if p["id"] == "anthropic")["api_key_ref"] == "env:ANTHROPIC_API_KEY"
    st.save(data)
    assert "ANTHROPIC_API_KEY" not in (tmp_path / "settings.json").read_text()
    assert "test-value" not in (tmp_path / "settings.json").read_text()


def test_public_bind_requires_token(monkeypatch):
    from adef.cli import serve
    monkeypatch.delenv("ADEF_API_TOKEN", raising=False)
    monkeypatch.delenv("ADPE_API_TOKEN", raising=False)
    assert serve(Namespace(host="0.0.0.0", port=8999, allow_insecure=False)) == 2
