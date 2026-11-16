"""Any enterprise stack: composed stacks, ingestion patterns, data types, consumption patterns, more integrations."""
import ast
import json

import pytest
import yaml
from fastapi.testclient import TestClient

from adef.api.app import app
from adef.catalog import stacks
from adef.connectors import context_sources as cs
from adef.engine import consume
from adef.engine.codegen import CodeGen
from adef.engine.sandbox import Sandbox
from adef.engine.scenarios import SCENARIOS
from adef.modeling import physical as ph
from adef.modeling.logical import LOGICAL_TYPES, parse_type
from conftest import drive
from test_lakehouse import model_and_mapping

c = TestClient(app)


def _parse_all(files: dict) -> None:
    for f, content in files.items():
        if f.endswith(".py"):
            ast.parse(content)
        elif f.endswith((".yml", ".yaml")):
            yaml.safe_load(content)
        elif f.endswith(".json"):
            json.loads(content)
        elif f.endswith(".jsonl"):
            [json.loads(line) for line in content.splitlines()]


def _code(profile, pack="telco"):
    model, mp = model_and_mapping(pack)
    return CodeGen(model, mp["mappings"], mp["dq_rules"], profile, "RUN-T", mp["entity_filters"], sources=mp["sources"]).generate()


# ------------------------------------------------------------------ stack catalog and composer
def test_presets_cover_the_main_enterprise_platforms():
    engines = {stacks.tool(p, "compute_engine") for p in stacks.PRESETS}
    assert engines >= {"snowflake", "databricks", "bigquery", "redshift", "athena", "synapse", "fabric"}
    assert {stacks.source_pattern(p) for p in stacks.PRESETS} == set(stacks.PATTERN_LABELS)
    by_cloud = {}
    for p in stacks.PRESETS:
        by_cloud.setdefault(stacks.tool(p, "cloud"), set()).add(stacks.tool(p, "compute_engine"))
    assert {"snowflake", "databricks"} <= by_cloud["aws"] and {"snowflake", "databricks"} <= by_cloud["azure"]
    assert "databricks" in by_cloud["gcp"]


def test_every_composed_stack_is_valid_and_generates_code_without_gaps():
    o = stacks.compose_options()
    seen = 0
    for cloud in o["clouds"]:
        for engine in o["engines"][cloud]:
            for source, patterns in o["sources"].items():
                for pattern in patterns:
                    prof = stacks.compose(cloud, engine, source, pattern)
                    v = stacks.validate(prof)
                    assert v["ok"], (prof["profile_id"], pattern, v["blocking"])
                    seen += 1
    assert seen > 500
    # one stack per (cloud, engine, pattern) is enough to prove the generators: 620 would only repeat them
    for cloud in o["clouds"]:
        for engine in o["engines"][cloud]:
            for source, pattern in (("oracle", "database-batch"), ("postgres", "database-cdc"), ("files", "files"),
                                    ("salesforce", "saas-api"), ("kafka-topics", "event-stream"), ("mongodb", "database-batch")):
                out = _code(stacks.compose(cloud, engine, source, pattern))
                assert out["gaps"] == [], (cloud, engine, source, out["gaps"])
                _parse_all(out["files"])


def test_composer_refuses_what_does_not_exist():
    with pytest.raises(ValueError, match="runs on aws"):
        stacks.compose("azure", "redshift", "oracle")
    with pytest.raises(ValueError, match="arrives as"):
        stacks.compose("aws", "snowflake", "salesforce", "database-cdc")
    assert c.post("/api/stacks/compose", json={"cloud": "gcp", "engine": "fabric", "source": "oracle"}).status_code == 400
    r = c.post("/api/stacks/compose", json={"cloud": "gcp", "engine": "snowflake", "source": "sap-s4hana"}).json()
    assert r["validation"]["ok"] and r["profile"]["slots"]["lake_catalog"]["tool"] == "polaris"
    assert r["profile"]["label"].startswith("SAP S/4HANA → Google Cloud GCS Iceberg → Snowflake")
    assert "fabric" not in c.get("/api/stacks/compose").json()["engines"]["aws"]


def test_tools_that_do_not_fit_are_blocking():
    p = stacks.preset("aws-redshift")
    p["slots"]["cloud"] = {"tool": "azure"}
    assert any("compute_engine=redshift runs on aws" in b for b in stacks.validate(p)["blocking"])
    p = stacks.preset("files-athena")
    p["slots"]["ingestion"] = {"tool": "spark-jdbc"}
    assert any("does not handle the source pattern `files`" in b for b in stacks.validate(p)["blocking"])
    p = stacks.preset("azure-synapse")
    p["slots"]["data_sharing"] = {"tool": "snowflake-secure-share"}
    assert any("Secure shares are a Snowflake feature" in b for b in stacks.validate(p)["blocking"])
    p = stacks.preset("gcp-databricks-streaming")
    p["slots"]["streaming"] = {"tool": "none", "reason": "x"}
    assert any("needs the `streaming` slot" in b for b in stacks.validate(p)["blocking"])


# ------------------------------------------------------------------ ingestion patterns
def test_each_source_pattern_generates_its_own_ingest():
    files = _code(stacks.preset("files-athena"))["files"]
    job = files["pipelines/01_ingest/ingest_files.py"]
    assert "_corrupt_record" in job and "_quarantine" in job and "_file_manifest" in job       # bad rows kept, files loaded once
    feed = yaml.safe_load(files["pipelines/01_ingest/ingest_config.yaml"])["tables"][0]
    assert feed["format"] == "csv" and "string" in feed["schema"] and feed["landing"].endswith("/")
    assert "ingest_jdbc.py" not in "".join(files)

    files = _code(stacks.preset("gcp-databricks-streaming"))["files"]
    job = files["pipelines/01_ingest/ingest_stream.py"]
    assert "readStream" in job and "checkpointLocation" in job and "from_json" in job and "_quarantine" in job
    assert "python_file: pipelines/01_ingest/ingest_stream.py" in files["resources/medallion_job.yml"]

    files = _code(stacks.preset("saas-snowflake"))["files"]
    conn = json.loads(files["pipelines/01_ingest/fivetran/connector.json"])
    assert conn["service"] == "salesforce" and conn["paused"] is True and "fold_landing.py" in "".join(files)

    files = _code(stacks.preset("aws-databricks"))["files"]             # change data capture: deletes reach silver
    assert "_op" in files["pipelines/01_ingest/fold_landing.py"]
    silver = next(v for k, v in files.items() if "bronze_to_silver" in k or k.endswith("silver.sql"))
    assert "n._op = 'D' THEN DELETE" in silver

    kinesis = stacks.compose("aws", "redshift", "kafka-topics")
    kinesis["slots"]["streaming"] = {"tool": "kinesis"}
    job = _code(kinesis)["files"]["pipelines/01_ingest/ingest_stream.py"]
    assert 'F.col("data").alias("value")' in job and "shardId" in job
    mongo = _code(stacks.compose("azure", "synapse", "mongodb"))["files"]["pipelines/01_ingest/ingest_jdbc.py"]
    assert "flatten_to_json" in mongo and "jdbc" not in mongo.split('"""')[2]


def test_no_generated_ingest_code_holds_a_credential():
    from adef.guardrails.scanners import scan_secrets
    for pid in ("files-athena", "gcp-databricks-streaming", "saas-snowflake", "aws-databricks", "azure-snowflake"):
        for f, content in _code(stacks.preset(pid))["files"].items():
            assert not scan_secrets(content), (pid, f)


@pytest.mark.parametrize("engine,needle", [("athena", "FROM gold."), ("trino", "CREATE SCHEMA IF NOT EXISTS iceberg.serving"),
                                           ("postgres", "TRUNCATE serving.")])
def test_publish_for_more_engines(engine, needle):
    cloud = "aws"
    files = _code(stacks.compose(cloud, engine, "oracle"))["files"]
    assert needle in files["pipelines/03_publish/publish.sql"] and "pipelines/03_publish/run_publish.sh" in files


def test_snowflake_publish_follows_the_cloud():
    azure = _code(stacks.preset("azure-snowflake"))["files"]["pipelines/03_publish/publish.sql"]
    assert "STORAGE_PROVIDER='AZURE'" in azure and "ICEBERG_REST" in azure and "GLUE" not in azure
    aws = _code(stacks.preset("example-a"))["files"]["pipelines/03_publish/publish.sql"]
    assert "STORAGE_PROVIDER='S3'" in aws and "CATALOG_SOURCE=GLUE" in aws and "SERVING.* REFRESH" not in aws


# ------------------------------------------------------------------ data types
def test_extended_types_map_on_every_dialect():
    assert parse_type("VARCHAR2(30)") == ("string", [30]) and parse_type("timestamp with time zone")[0] == "timestamp_tz"
    assert parse_type("VARIANT")[0] == "json" and parse_type("uniqueidentifier")[0] == "uuid"
    assert parse_type("something unknown")[0] == "string"
    for dialect in ph.TYPE_MAP:
        for t in LOGICAL_TYPES:
            assert ph.phys_type(t, dialect), (dialect, t)
    assert ph.phys_type("json", "snowflake") == "VARIANT" and ph.phys_type("json", "redshift") == "SUPER"
    assert ph.phys_type("json", "bigquery") == "JSON" and ph.phys_type("geography", "bigquery") == "GEOGRAPHY"
    assert ph.phys_type("timestamp_tz", "tsql") == "DATETIMEOFFSET(6)" and ph.phys_type("uuid", "postgres") == "UUID"
    assert "json" in ph.KEPT_AS_TEXT["tsql"] and ph.KEPT_AS_TEXT["snowflake"] == []


def test_a_model_with_semi_structured_columns_builds_end_to_end():
    model, mp = model_and_mapping("retail")
    fact = next(e for e in model["entities"] if e["kind"] == "fact")
    fact["attributes"].append({"name": "basket_json", "label": "Basket", "type": "json", "pk": False, "fk": None,
                               "classification": "internal", "description": "Basket as sent by the till", "nullable": True})
    fact["attributes"].append({"name": "sold_at", "label": "Sold at", "type": "timestamp_tz", "pk": False, "fk": None,
                               "classification": "internal", "description": "Sale time with zone", "nullable": True})
    sb = Sandbox(model, mp["dq_rules"])
    sb.build()
    assert sb.db.execute(f"SELECT COUNT(basket_json) FROM fct_{fact['name']}").fetchone()[0] > 0
    from adef.modeling import exports
    ddl = exports.render("ddl", model, {"profile": stacks.preset("example-a"), "dialect": "snowflake"})[1]
    assert "VARIANT" in ddl.upper() and "TIMESTAMP_TZ" in ddl.upper()
    import copy
    mp2 = copy.deepcopy(mp)                                   # the scenario is shared: never change it in place
    mp2["sources"][0]["columns"].append({"name": "payload", "type": "json", "classification": "internal", "pk": False})
    out = CodeGen(model, mp2["mappings"], mp2["dq_rules"], stacks.preset("aws-redshift"), "RUN-T", mp2["entity_filters"],
                  sources=mp2["sources"]).generate()
    assert out["gaps"] == []
    silver = out["files"]["pipelines/02_curate/01_bronze_to_silver.sql"]
    assert "get_json_object(payload, '$')" in silver          # JSON is validated in silver, not cast away


# ------------------------------------------------------------------ consumption patterns
@pytest.mark.parametrize("pid", [p["profile_id"] for p in stacks.PRESETS])
def test_every_available_pattern_is_generated_and_checked_by_execution(pid):
    prof = stacks.preset(pid)
    for pack in ("telco", "financial-services"):
        model, mp = model_and_mapping(pack)
        sb = Sandbox(model, mp["dq_rules"])
        sb.build()
        patterns = [o["id"] for o in consume.options(prof) if o["available"]]
        out = consume.generate(patterns, model, prof, "RUN-T", sb, [{"name": a, "question": b} for a, b in SCENARIOS[pack]["consumers"]])
        _parse_all(out["files"])
        assert out["checks"] and all(k[2] == "pass" for k in out["checks"]), [k for k in out["checks"] if k[2] != "pass"]
        ran = {k[0] for k in out["checks"]}
        assert ran == {consume.PATTERNS[p]["label"] for p in patterns if p not in ("bi", "sql")}
        restricted = {a["name"] for e in model["entities"] for a in e["attributes"] if a["classification"] == "restricted"}
        for f in ("api/openapi.yaml", "features/feature_spec.yaml", "extracts/manifest.yaml"):
            if f in out["files"] and f != "extracts/manifest.yaml":
                assert not [r for r in restricted if f"{r}:" in out["files"][f] or f"- {r}\n" in out["files"][f]], (pid, f)


def test_pattern_syntax_follows_the_stack():
    def gen(pid, pattern, pack="retail"):
        model, mp = model_and_mapping(pack)
        sb = Sandbox(model, mp["dq_rules"])
        sb.build()
        return consume.generate([pattern], model, stacks.preset(pid), "RUN-T", sb, [])["files"]
    assert "SECURE VIEW" in gen("example-a", "data-sharing")["sharing/share.sql"]
    assert "ALTER SHARE" in gen("example-b", "data-sharing")["sharing/share.sql"]
    assert "CREATE DATASHARE" in gen("aws-redshift", "data-sharing")["sharing/share.sql"]
    assert "restrictedExportConfig" in gen("gcp-bigquery", "data-sharing")["sharing/listing.json"]
    for pid in ("example-a", "example-b", "aws-redshift"):         # nobody is added to a share before approval
        live = [ln for ln in gen(pid, "data-sharing")["sharing/share.sql"].splitlines()
                if ("ADD ACCOUNTS" in ln or "TO RECIPIENT" in ln or "TO NAMESPACE" in ln) and not ln.startswith("--")]
        assert live == []
    assert "COPY INTO @export_stage" in gen("example-a", "file-extract")["extracts/export.sql"]
    assert "UNLOAD ('" in gen("aws-redshift", "file-extract")["extracts/export.sql"]
    assert "EXPORT DATA OPTIONS" in gen("gcp-bigquery", "file-extract")["extracts/export.sql"]
    assert "WITH (format = 'PARQUET')" in gen("files-athena", "file-extract")["extracts/export.sql"]
    assert "CORTEX SEARCH SERVICE" in gen("example-a", "ai-retrieval")["retrieval/index.sql"]
    assert "create_delta_sync_index" in gen("example-b", "ai-retrieval")["retrieval/create_index.py"]
    assert "verified_queries" in gen("example-a", "ai-assistant")["assistant/semantic_model.yaml"]
    assert "General instructions" in gen("example-b", "ai-assistant")["assistant/genie_space.md"]
    assert "type Query" in gen("azure-fabric", "data-api")["api/schema.graphql"]
    sync = yaml.safe_load(gen("example-a", "reverse-etl")["reverse-etl/sync.yaml"])
    assert sync["paused"] is True and sync["mode"] == "upsert"                 # created paused: writing out needs approval
    ev = yaml.safe_load(gen("example-a", "ai-assistant")["assistant/evaluation.yaml"])
    assert ev["questions"] and all(q["expected"] is not None for q in ev["questions"])


def test_a_run_delivers_the_patterns_it_chose(engine):
    opts = c.post("/api/consumption-options", json={"stack_profile": "azure-snowflake"}).json()
    assert {o["id"] for o in opts if o["available"]} == set(consume.PATTERNS)
    synapse = {o["id"]: o for o in c.post("/api/consumption-options", json={"stack_profile": "azure-synapse"}).json()}
    assert not synapse["data-sharing"]["available"] and "data_sharing" in synapse["data-sharing"]["reason"]
    bad = c.post("/api/runs", json={"client_code": "ACME", "domain_pack": "retail", "stack_profile": "azure-synapse",
                                    "consumption_patterns": ["data-sharing"]})
    assert bad.status_code == 422 and "no tool bound" in bad.text
    assert c.post("/api/runs", json={"client_code": "ACME", "domain_pack": "retail", "consumption_patterns": ["telepathy"]}).status_code == 422

    wanted = ["bi", "sql", "data-api", "data-sharing", "ml-features", "ai-assistant", "file-extract"]
    rid = engine.create_run({"client_code": "ACME", "domain_pack": "retail", "stack_profile": "azure-snowflake",
                             "consumption_patterns": wanted})["run_id"]
    st = drive(engine, rid, timeout=240)
    assert [o["id"] for o in st["consumption"]] == [p for p in consume.PATTERNS if p in wanted]
    ws = engine.ws(rid)
    arts = st["gates_detail"]["G8"]["request"]["artifacts"]
    for f in ("api/openapi.yaml", "sharing/share.sql", "features/feature_set.sql", "assistant/semantic_model.yaml",
              "extracts/export.sql"):
        assert f"08-consumption/patterns/{f}" in arts and ws.has(f"08-consumption/patterns/{f}")       # approved by hash at G8
    assert not ws.has("08-consumption/patterns/reverse-etl/sync.yaml")                                # not asked for
    val = ws.read("08-consumption/validation.md")
    assert "Consumption patterns, checked by execution" in val and "FAIL" not in val
    assert "Share with other organisations" in ws.read("08-consumption/consumer-map.md")
    assert st["consistency"]["counts"]["fail"] == 0

    default = engine.create_run({"client_code": "ACME", "domain_pack": "retail"}, start=False)["run_id"]
    assert [o["id"] for o in engine.status(default)["consumption"]] == ["bi", "sql"]


def test_a_composed_stack_runs_the_whole_lifecycle(engine):
    prof = stacks.compose("azure", "databricks", "sap-s4hana")
    rid = engine.create_run({"client_code": "ACME", "domain_pack": "utilities", "stack_profile": prof,
                             "consumption_patterns": ["bi", "sql", "ai-assistant", "ai-retrieval"]})["run_id"]
    st = drive(engine, rid, timeout=240)
    assert st["status"] == "completed" and st["consistency"]["counts"]["fail"] == 0


# ------------------------------------------------------------------ integrations
def test_new_live_integrations_parse_what_the_systems_return(monkeypatch):
    class R:
        def __init__(self, payload, text=""):
            self.status_code, self._p, self.text = 200, payload, text

        def json(self):
            return self._p

    posted = []

    def fake_get(url, **kw):
        if "/_apis/wit/workitems/7" in url:
            return R({"fields": {"System.WorkItemType": "User Story", "System.Title": "Churn by segment", "System.State": "Active",
                                 "System.Description": "<p>As a manager</p>", "System.Rev": 3,
                                 "Microsoft.VSTS.Common.AcceptanceCriteria": "<ul><li>rate matches</li></ul>"}})
        if url.endswith("/_apis/wit/workitems"):
            return R({"value": [{"id": 7, "fields": {"System.Title": "Churn by segment", "System.WorkItemType": "User Story",
                                                     "System.State": "Active"}}]})
        if url.endswith("/repository/tree"):
            return R([{"type": "blob", "path": "docs/style.md"}, {"type": "tree", "path": "docs"}, {"type": "blob", "path": "a.png"}])
        if "/repository/files/" in url:
            return R({}, text="# Style\nUse MERGE.")
        if url.endswith("/rest/2.0/assets"):
            return R({"results": [{"id": "ab12cd34-0000", "displayName": "Churn rate", "type": {"name": "Business Term"},
                                   "domain": {"name": "Glossary"}, "status": {"name": "Accepted"}}]})
        if "/rest/2.0/assets/" in url:
            return R({"displayName": "Churn rate", "type": {"name": "Business Term"}, "domain": {"name": "Glossary"},
                      "status": {"name": "Accepted"}, "lastModifiedOn": 5})
        if url.endswith("/rest/2.0/attributes"):
            return R({"results": [{"type": {"name": "Definition"}, "value": "<p>Churned / active</p>"}]})
        if "/drive/root/search" in url:
            return R({"value": [{"id": "01ABC", "name": "glossary.md", "size": 20, "webUrl": "https://x/glossary.md", "file": {}},
                                {"id": "01DEF", "name": "deck.pptx", "size": 9, "file": {}}]})
        if "/drive/items/" in url:
            return R({"name": "glossary.md", "webUrl": "https://x/glossary.md", "eTag": "e1",
                      "@microsoft.graph.downloadUrl": "https://download.example/glossary"})
        if url.startswith("https://download.example/"):
            assert "headers" not in kw                                    # the bearer token is not sent to the download host
            return R({}, text="Churn rate: churned / active")
        return R({"id": "site-1", "displayName": "Data"})

    def fake_post(url, **kw):
        posted.append((url, kw.get("json") or kw.get("data")))
        return R({"access_token": "t"} if "oauth2" in url else {"workItems": [{"id": 7}]})

    monkeypatch.setattr(cs.httpx, "get", fake_get)
    monkeypatch.setattr(cs.httpx, "post", fake_post)
    monkeypatch.setenv("T_TOKEN", "x")
    ado = cs.AzureDevOpsSource({"mode": "live", "base_url": "https://dev.azure.com/acme", "project": "Data Platform", "token_ref": "env:T_TOKEN"})
    assert ado.search("churn' OR 1=1 --", "telco")[0]["ref"] == "7"
    assert "'churn  OR 1=1 --'" in posted[0][1]["query"]                 # the quote cannot close the WIQL string
    item = ado.fetch("7", "telco")
    assert "As a manager" in item["content"] and "- rate matches" in item["content"]
    with pytest.raises(cs.ContextSourceError):
        ado.fetch("7; DROP", "telco")
    gl = cs.GitLabSource({"mode": "live", "base_url": "https://gitlab.com", "repo": "acme/data/platform", "branch": "main", "token_ref": "env:T_TOKEN"})
    assert [f["ref"] for f in gl.search("docs", "telco")] == ["docs/style.md"] and "MERGE" in gl.fetch("docs/style.md", "telco")["content"]
    with pytest.raises(cs.ContextSourceError):
        gl.fetch("../secrets", "telco")
    col = cs.CollibraSource({"mode": "live", "base_url": "https://acme.collibra.com", "user": "svc", "token_ref": "env:T_TOKEN"})
    assert col.search("churn", "telco")[0]["kind"] == "business term"
    assert "Definition: Churned / active" in col.fetch("ab12cd34-0000", "telco")["content"]
    sp = cs.SharePointSource({"mode": "live", "tenant": "acme.onmicrosoft.com", "client_id": "11111111-2222", "site": "acme.sharepoint.com:/sites/data",
                              "token_ref": "env:T_TOKEN"})
    hits = sp.search("glossary", "telco")
    assert [h["title"] for h in hits] == ["glossary.md"] and hits[0]["ref"] == "site-1|01ABC"
    assert sp.fetch(hits[0]["ref"], "telco")["content"].startswith("Churn rate")
    with pytest.raises(cs.ContextSourceError):
        cs.SharePointSource({"mode": "live", "tenant": "x", "client_id": "y", "site": "bad", "token_ref": "env:T_TOKEN"}).search("a", "telco")


def test_catalog_context_reaches_the_mapping_stage(engine):
    d = c.get("/api/context/sources").json()
    assert d["stages"]["mapping"]["needs"][0]["sources"][0] == "collibra"
    assert "azure-devops" in d["stages"]["requirements"]["needs"][0]["sources"] or any(
        "azure-devops" in n["sources"] for n in d["stages"]["requirements"]["needs"])
    rid = engine.create_run({"client_code": "ACME", "domain_pack": "telco", "autopilot": False}, start=False)["run_id"]
    table = next(r for r in c.post("/api/integrations/collibra/search", json={"query": "", "domain": "telco"}).json()["results"]
                 if r["kind"] == "table")
    r = c.post(f"/api/runs/{rid}/context", json={"stage": "mapping", "source": "collibra", "ref": table["ref"],
                                                 "need": "catalog", "added_by": "Demo Presenter"})
    assert r.status_code == 200, r.text
    from adef import context_hub
    block = context_hub.prompt_block(engine.ws(rid), "mapping")[0]
    assert "classification:" in block and "Collibra" in block
