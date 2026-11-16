"""Consumption patterns: the ways a data product is used once it is built.

A dashboard is one way to consume data, not the only one. A run chooses its consumption patterns and
the Analytics and AI Engineer generates the artifacts for each, in the syntax of the stack's own tool:

    bi            dashboards and reports on the governed semantic model
    sql           governed SQL access through masked views
    ai-assistant  questions in plain language, grounded in a semantic model and verified queries
    data-api      an API for applications (OpenAPI or GraphQL) over named, parameterised queries
    data-sharing  live sharing with other accounts or organisations
    reverse-etl   syncing curated data back into business applications
    ml-features   features for machine learning, one row per business key
    ai-retrieval  a searchable index of what the product contains, for AI applications
    file-extract  scheduled file exports with a control total

Two rules hold for every pattern. First, every pattern reads the masked consumer views, never the
base tables, so Restricted attributes cannot leave through a side door. Second, the SQL each pattern
relies on is executed against the sandbox copy of the model before the gate, and the results are
reported: a pattern is evidence, not a promise. Tool-specific syntax lives only here.
"""
from __future__ import annotations

import json
import re

from ..catalog import stacks
from ..modeling import physical as ph
from ..util import dump_yaml
from .sandbox import tname

PATTERNS: dict[str, dict] = {
    "bi": {"label": "Dashboards and reports", "slot": "bi", "who": "Business users and analysts",
           "what": "A semantic model for the BI tool, with the governed metrics."},
    "sql": {"label": "Governed SQL access", "slot": None, "who": "Analysts and data scientists",
            "what": "Masked consumer views and the access model for direct queries."},
    "ai-assistant": {"label": "Ask in plain language", "slot": "ai_consumption", "who": "Business users",
                     "what": "A semantic model and verified queries that ground a natural-language assistant."},
    "data-api": {"label": "Data API for applications", "slot": "data_api", "who": "Application teams",
                 "what": "An API specification over named, parameterised queries."},
    "data-sharing": {"label": "Share with other organisations", "slot": "data_sharing", "who": "Partners and other business units",
                     "what": "A live share of the masked views, with no copies."},
    "reverse-etl": {"label": "Sync back to business applications", "slot": "reverse_etl", "who": "Sales, service and marketing teams",
                    "what": "Sync definitions that push curated attributes into operational tools."},
    "ml-features": {"label": "Features for machine learning", "slot": "feature_store", "who": "Data scientists and ML engineers",
                    "what": "A feature set with one row per business key, and its registration."},
    "ai-retrieval": {"label": "Search index for AI applications", "slot": "vector_store", "who": "AI application teams",
                     "what": "Documents that describe the product, and a vector index over them."},
    "file-extract": {"label": "Scheduled file exports", "slot": None, "who": "Downstream systems and regulators",
                     "what": "Export statements with a manifest and a control total."},
}
DEFAULT = ["bi", "sql"]


def _bound(profile: dict, slot: str | None) -> str | None:
    if slot is None:
        return "built in"
    t = stacks.tool(profile, slot)
    return None if t in ("none", "") else t


def options(profile: dict) -> list[dict]:
    """Every pattern, whether this stack can deliver it, and with which tool."""
    out = []
    for pid, p in PATTERNS.items():
        t = _bound(profile, p["slot"])
        out.append({"id": pid, "label": p["label"], "who": p["who"], "what": p["what"], "tool": t, "available": bool(t),
                    "default": pid in DEFAULT,
                    "reason": "" if t else f"Bind the `{p['slot']}` slot of the technology stack to use this pattern."})
    return out


def resolve(profile: dict, wanted: list[str] | None) -> list[str]:
    """The patterns a run will deliver: what was asked for (validated), or the default pair."""
    avail = {o["id"]: o for o in options(profile)}
    if wanted is None:
        return [p for p in DEFAULT if avail[p]["available"]]
    unknown = [w for w in wanted if w not in avail]
    if unknown:
        raise ValueError(f"Unknown consumption pattern: {', '.join(unknown)}")
    missing = [avail[w]["label"] for w in wanted if not avail[w]["available"]]
    if missing:
        raise ValueError(f"This technology stack has no tool bound for: {', '.join(missing)}")
    return [p for p in PATTERNS if p in wanted]


# ----------------------------------------------------------------------------- shared building blocks
class Ctx:
    """What every pattern needs: names in the target platform, names in the sandbox, and safe column lists."""

    def __init__(self, model: dict, profile: dict, run_id: str, sandbox):
        self.model, self.p, self.run_id, self.sb = model, profile, run_id, sandbox
        self.schema = ph.schema_name(profile)
        self.dialect = ph.dialect_for(profile)
        self.engine = stacks.tool(profile, "compute_engine")
        self.product = re.sub(r"\W+", "_", model["name"]).strip("_").lower()
        self.entities = {e["name"]: e for e in model["entities"]}
        self.files: dict[str, str] = {}
        self.checks: list[list] = []
        self.gaps: list[str] = []
        for e in model["entities"]:                        # the masked views every pattern reads
            sandbox.masking(e, self.restricted(e))

    def restricted(self, e: dict) -> list[str]:
        return [a["name"] for a in e["attributes"] if a["classification"] == "restricted"]

    def open_attrs(self, e: dict) -> list[dict]:
        """Attributes a consumer may see unmasked."""
        return [a for a in e["attributes"] if a["classification"] != "restricted"]

    def view(self, e: dict) -> str:
        return f"{self.schema}.v_{ph.table_name(e, self.p).lower()}"

    def target(self, sql: str) -> str:
        return re.sub(r"@@(\w+)@@", lambda m: self.view(self.entities[m.group(1)]), sql)

    def local(self, sql: str) -> str:
        return re.sub(r"@@(\w+)@@", lambda m: f"v_consumer_{tname(self.entities[m.group(1)])}", sql)

    def run(self, sql: str, params: dict | None = None) -> list[tuple]:
        return self.sb.db.execute(self.local(sql), params or {}).fetchall()

    def check(self, pattern: str, what: str, ok: bool, detail: str) -> None:
        self.checks.append([PATTERNS[pattern]["label"], what, "pass" if ok else "FAIL", detail])

    def metric_sql(self, m: dict) -> str:
        """The governed metric as portable SQL over the masked view."""
        e = self.entities[m["entity"]]
        return self.sb.metric_sql(m).replace(f"FROM {tname(e)}", f"FROM @@{e['name']}@@")

    def subject(self) -> tuple[dict, dict, str] | None:
        """The main fact, the dimension it is most often analysed by, and the fact's key to it."""
        for f in (e for e in self.model["entities"] if e["kind"] == "fact"):
            for a in f["attributes"]:
                if a.get("fk") and a["fk"]["entity"] in self.entities and a["classification"] != "restricted":
                    return f, self.entities[a["fk"]["entity"]], a["name"]
        return None

    def measures(self, f: dict) -> list[dict]:
        return [a for a in self.open_attrs(f) if not a["pk"] and not a.get("fk")
                and ph.parse_type(a["type"])[0] in ("decimal", "integer", "bigint")][:4]

    def feature_sql(self) -> tuple[str, str, list[str]] | None:
        """One row per business key with counts and aggregates of the main fact."""
        s = self.subject()
        if not s:
            return None
        f, d, key = s
        feats = [("row_count", "COUNT(*)")]
        for a in self.measures(f):
            feats += [(f"{a['name']}_sum", f"SUM({a['name']})"), (f"{a['name']}_avg", f"AVG({a['name']})")]
        body = ",\n       ".join(f"{expr} AS {name}" for name, expr in feats)
        return f"SELECT {key},\n       {body}\nFROM @@{f['name']}@@\nGROUP BY {key}", key, [n for n, _ in feats]


# ----------------------------------------------------------------------------- data API
def _data_api(c: Ctx) -> None:
    tool = stacks.tool(c.p, "data_api")
    queries, paths, types = [], {}, []
    js = {"decimal": "number", "integer": "integer", "bigint": "integer", "boolean": "boolean"}
    for e in c.model["entities"]:
        attrs = c.open_attrs(e)
        cols = ", ".join(a["name"] for a in attrs)
        filters = [a for a in attrs if (a["pk"] or a.get("fk") or ph.parse_type(a["type"])[0] == "string")][:4]
        where = " AND ".join(f"(:{a['name']} IS NULL OR {a['name']} = :{a['name']})" for a in filters) or "1 = 1"
        order = next((a["name"] for a in attrs if a["pk"]), attrs[0]["name"])
        name = f"list_{e['name']}"
        sql = f"SELECT {cols}\nFROM @@{e['name']}@@\nWHERE {where}\nORDER BY {order}\nLIMIT :limit OFFSET :offset"
        queries.append((name, sql, filters))
        props = {a["name"]: {"type": js.get(ph.parse_type(a["type"])[0], "string"), "description": a.get("description", "")}
                 for a in attrs}
        paths[f"/{e['name'].replace('_', '-')}"] = {"get": {
            "operationId": name, "summary": f"List {e.get('label') or e['name']} ({e.get('grain', '')})", "x-query": name,
            "parameters": [{"name": a["name"], "in": "query", "required": False, "schema": {"type": "string"}} for a in filters] + [
                {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 100, "maximum": 1000}},
                {"name": "offset", "in": "query", "schema": {"type": "integer", "default": 0}}],
            "responses": {"200": {"description": "Rows", "content": {"application/json": {"schema": {
                "type": "array", "items": {"type": "object", "properties": props}}}}},
                "401": {"description": "Not signed in"}, "403": {"description": "Caller lacks the consumer role"}}}}
        types.append("type " + "".join(w.title() for w in e["name"].split("_")) + " {\n" + "".join(
            f"  {a['name']}: {({'number': 'Float', 'integer': 'Int', 'boolean': 'Boolean'}).get(js.get(ph.parse_type(a['type'])[0], ''), 'String')}\n"
            for a in attrs) + "}\n")
    for m in c.model.get("metrics", []):
        name = f"metric_{m['name']}"
        queries.append((name, c.metric_sql(m).replace("SELECT ", "SELECT ", 1) + "", []))
        paths[f"/metrics/{m['name'].replace('_', '-')}"] = {"get": {
            "operationId": name, "summary": f"{m['label']}: {m['definition']}", "x-query": name,
            "responses": {"200": {"description": "The governed value", "content": {"application/json": {"schema": {
                "type": "object", "properties": {"value": {"type": "number"}, "unit": {"type": "string"}}}}}}}}}
    c.files["api/queries.sql"] = (
        f"-- Named queries behind the data API of {c.model['name']} (run {c.run_id}).\n"
        "-- The API runs only these statements, with bound parameters: it never builds SQL from a request.\n"
        "-- Every query reads a masked consumer view, so Restricted attributes cannot be returned.\n\n"
        + "\n\n".join(f"-- name: {n}\n{c.target(q)};" for n, q, _ in queries) + "\n")
    c.files["api/openapi.yaml"] = dump_yaml({
        "openapi": "3.0.3", "info": {"title": f"{c.model['name']} data API", "version": str(c.model.get("version", "1.0.0")),
                                     "description": "Read-only access to the governed data product. Each operation runs one "
                                                    "named, parameterised query from queries.sql against the masked views."},
        "servers": [{"url": "https://${API_HOST}/data/v1"}],
        "security": [{"oauth2": ["data.read"]}],
        "components": {"securitySchemes": {"oauth2": {"type": "oauth2", "flows": {"clientCredentials": {
            "tokenUrl": "https://${IDENTITY_PROVIDER}/oauth2/token", "scopes": {"data.read": "Read the data product"}}}}}},
        "paths": paths})
    if tool == "graphql":
        c.files["api/schema.graphql"] = (
            "# Read-only GraphQL schema over the masked consumer views. Resolvers run the named queries in queries.sql.\n\n"
            + "\n".join(types) + "\ntype Query {\n" + "".join(
                f"  {e['name']}(limit: Int = 100, offset: Int = 0): [{''.join(w.title() for w in e['name'].split('_'))}!]!\n"
                for e in c.model["entities"]) + "}\n")
    ran, leaked = 0, 0
    for n, q, filters in queries:
        params = {a["name"]: None for a in filters}
        if ":limit" in q:
            params.update(limit=5, offset=0)
        rows = c.run(q, params)
        ran += 1
        leaked += sum(1 for r in rows for v in r if v == "***")
    c.check("data-api", f"{ran} named queries execute with bound parameters", ran == len(queries), f"{ran} of {len(queries)} ran")
    c.check("data-api", "No Restricted attribute is selected by any query", leaked == 0, f"{leaked} masked values returned")


# ----------------------------------------------------------------------------- data sharing
def _data_sharing(c: Ctx) -> None:
    tool, share = stacks.tool(c.p, "data_sharing"), f"{c.product}_share"
    views = [(e, c.view(e)) for e in c.model["entities"]]
    head = (f"-- Share {c.model['name']} with another account or organisation ({tool}), run {c.run_id}.\n"
            "-- Only the masked consumer views are shared: no base table, no Restricted value.\n"
            "-- Adding a recipient is outward-facing (action class A3): it is done by the Platform Owner after G8,\n"
            "-- with the recipient named in the approval. The recipient lines below are therefore commented out.\n\n")
    if tool == "snowflake-secure-share":
        db = c.schema.split(".")[0] if "." in c.schema else "${DATABASE}"
        body = [f"CREATE SHARE IF NOT EXISTS {share} COMMENT = 'DataCrew run {c.run_id}';",
                f"GRANT USAGE ON DATABASE {db} TO SHARE {share};", f"GRANT USAGE ON SCHEMA {db}.{c.schema.split('.')[-1]} TO SHARE {share};"]
        for e, v in views:
            cols = ", ".join(f"'***' AS {a['name']}" if a["classification"] == "restricted" else a["name"] for a in e["attributes"])
            body += [f"-- a shared view must be SECURE so the recipient cannot see its definition or pushed-down rows",
                     f"CREATE OR REPLACE SECURE VIEW {v}_shared AS SELECT {cols} FROM {v};",
                     f"GRANT SELECT ON VIEW {v}_shared TO SHARE {share};"]
        body.append(f"-- ALTER SHARE {share} ADD ACCOUNTS = <consumer_org>.<consumer_account>;")
        c.files["sharing/share.sql"] = head + "\n".join(body) + "\n"
    elif tool == "delta-sharing":
        body = [f"CREATE SHARE IF NOT EXISTS {share} COMMENT 'DataCrew run {c.run_id}';"]
        body += [f"ALTER SHARE {share} ADD VIEW {v};" for _, v in views]
        body += [f"-- CREATE RECIPIENT IF NOT EXISTS <recipient_name> USING ID '<recipient sharing identifier>';",
                 f"-- GRANT SELECT ON SHARE {share} TO RECIPIENT <recipient_name>;"]
        c.files["sharing/share.sql"] = head + "\n".join(body) + "\n"
    elif tool == "redshift-datashare":
        body = [f"CREATE DATASHARE {share};", f"ALTER DATASHARE {share} ADD SCHEMA {c.schema};"]
        body += [f"ALTER DATASHARE {share} ADD TABLE {v};" for _, v in views]
        body.append(f"-- GRANT USAGE ON DATASHARE {share} TO NAMESPACE '<consumer namespace id>';")
        c.files["sharing/share.sql"] = head + "\n".join(body) + "\n"
    elif tool == "analytics-hub":
        body = [f"CREATE SCHEMA IF NOT EXISTS {share} OPTIONS (description = 'Shared views of {c.model['name']}');"]
        for e, v in views:
            cols = ", ".join(a["name"] for a in c.open_attrs(e))
            body.append(f"CREATE OR REPLACE VIEW {share}.{v.split('.')[-1]} AS SELECT {cols} FROM {v};")
        c.files["sharing/share.sql"] = head + "\n".join(body) + "\n"
        c.files["sharing/listing.json"] = json.dumps({
            "displayName": c.model["name"], "description": c.model.get("description", ""),
            "bigqueryDataset": {"dataset": f"projects/${{PROJECT}}/datasets/{share}"},
            "restrictedExportConfig": {"enabled": True, "restrictQueryResult": True},
            "note": "Create with: bq / Analytics Hub API, in the exchange named in the G8 approval. Subscribers are added by "
                    "the Platform Owner."}, indent=2)
    elif tool == "onelake-shortcut":
        c.files["sharing/shortcuts.json"] = json.dumps({"shortcuts": [
            {"name": v.split(".")[-1], "path": "Tables", "target": {"oneLake": {
                "workspaceId": "${SOURCE_WORKSPACE_ID}", "itemId": "${SOURCE_LAKEHOUSE_ID}", "path": f"Tables/{v.split('.')[-1]}"}}}
            for _, v in views], "note": "Created in the consuming workspace by its owner after G8. Shortcuts point at the "
                                         "masked views' tables, never at the gold tables."}, indent=2)
    else:
        c.gaps.append(f"data_sharing `{tool}` has no template")
        return
    text = "\n".join(v for k, v in c.files.items() if k.startswith("sharing/"))
    base = [ph.table_name(e, c.p) for e in c.model["entities"] if re.search(rf"\b{c.schema}\.{ph.table_name(e, c.p)}\b", text)]
    c.check("data-sharing", "Only masked views are shared, never a base table", not base, f"{len(views)} views; base tables shared: {base or 'none'}")
    live = [ln for ln in text.splitlines() if re.search(r"ADD ACCOUNTS|TO RECIPIENT|TO NAMESPACE", ln) and not ln.lstrip().startswith("--")]
    c.check("data-sharing", "No recipient is added before approval", not live, "recipient statements are commented out" if not live else live[0])


# ----------------------------------------------------------------------------- reverse ETL
def _reverse_etl(c: Ctx) -> None:
    tool, fs = stacks.tool(c.p, "reverse_etl"), c.feature_sql()
    if not fs:
        c.gaps.append("reverse-etl: the model has no fact with a key to a dimension, so there is nothing to sync")
        return
    feat_sql, key, feats = fs
    f, d, _ = c.subject()
    pk = next(a["name"] for a in d["attributes"] if a["pk"])
    attrs = [a["name"] for a in c.open_attrs(d) if not a["pk"]][:6]
    current = "\nWHERE d.is_current = TRUE" if d.get("history") == "type2" else ""
    sql = (f"SELECT d.{pk}" + "".join(f",\n       d.{a}" for a in attrs) + "".join(f",\n       f.{n}" for n in feats)
           + f"\nFROM @@{d['name']}@@ d\nLEFT JOIN (\n{feat_sql}\n) f ON f.{key} = d.{pk}")
    model_name = f"{d['name']}_360"
    c.files[f"reverse-etl/models/{model_name}.sql"] = (
        f"-- Reverse ETL model: one row per {d['name']} with its curated attributes and activity (run {c.run_id}).\n"
        "-- Reads masked views only: a Restricted attribute is never synced into a business application.\n"
        + c.target(sql) + current + "\n")
    mappings = [{"from": pk, "to": "External_Id__c", "type": "identifier"}] + [
        {"from": n, "to": "".join(w.title() for w in n.split("_")) + "__c"} for n in attrs + feats]
    if tool == "hightouch":
        cfg = {"model": model_name, "destination": "${CRM_DESTINATION}", "object": "Account", "mode": "upsert",
               "schedule": {"type": "interval", "interval": {"unit": "hour", "quantity": 6}}, "paused": True,
               "configuration": {"externalIdMapping": mappings[0], "mappings": mappings[1:]}}
    else:
        cfg = {"label": f"{model_name} to CRM", "operation": "upsert", "paused": True,
               "source_attributes": {"object": {"type": "model", "name": model_name}},
               "destination_attributes": {"connection": "${CRM_DESTINATION}", "object": "account"},
               "schedule": {"frequency": "hourly", "hour_interval": 6},
               "mappings": [{"from": {"type": "column", "data": m["from"]}, "to": m["to"],
                             "is_primary_identifier": m.get("type") == "identifier"} for m in mappings]}
    c.files["reverse-etl/sync.yaml"] = (
        f"# {tool} sync for {c.model['name']}. It is created paused: writing into a business application is an\n"
        "# outward-facing action (A3) and starts only after G8, by the application's owner. Destination field\n"
        "# names are proposals: confirm them with the application owner.\n" + dump_yaml(cfg))
    rows = c.run(sql + current.replace("= TRUE", "= 1"))
    keys = [r[0] for r in rows]
    c.check("reverse-etl", "The sync model returns one row per business key", len(keys) == len(set(keys)) and bool(keys),
            f"{len(keys)} rows, {len(set(keys))} distinct keys")
    c.check("reverse-etl", "No Restricted attribute is synced", not any(v == "***" for r in rows for v in r),
            f"{len(attrs) + len(feats) + 1} columns, none Restricted")


# ----------------------------------------------------------------------------- machine learning features
def _ml_features(c: Ctx) -> None:
    store, fs = stacks.tool(c.p, "feature_store"), c.feature_sql()
    if not fs:
        c.gaps.append("ml-features: the model has no fact with a key to a dimension, so no feature set was derived")
        return
    sql, key, feats = fs
    f, d, _ = c.subject()
    name = f"{d['name']}_features"
    table = f"{c.schema}.fs_{name}"
    c.files["features/feature_set.sql"] = (
        f"-- Feature set `{name}`: one row per {key}, from the masked view of {f['name']} (run {c.run_id}).\n"
        "-- Aggregates only: no Restricted attribute and no free text can enter a model by this path.\n"
        f"CREATE OR REPLACE TABLE {table} AS\n{c.target(sql)};\n".replace(
            "CREATE OR REPLACE TABLE", "CREATE OR ALTER VIEW" if c.dialect == "tsql" else "CREATE OR REPLACE TABLE"))
    c.files["features/feature_spec.yaml"] = dump_yaml({
        "feature_set": name, "entity": {"name": d["name"], "join_key": key}, "source": c.view(f), "table": table,
        "refresh": "daily, after the publish pipeline", "owner": "Data Steward", "store": store,
        "features": [{"name": n, "type": "bigint" if n == "row_count" else "double",
                      "description": f"{n.rsplit('_', 1)[-1]} of {n.rsplit('_', 1)[0]} per {key}" if n != "row_count"
                      else f"number of {f['name']} rows per {key}"} for n in feats],
        "leakage_note": "Aggregates cover all history. For training, filter the source to rows before the label date."})
    reg = {
        "databricks-feature-store": (
            "from databricks.feature_engineering import FeatureEngineeringClient\n\n"
            "fe = FeatureEngineeringClient()\n"
            f"fe.create_table(name=\"{table}\", primary_keys=[\"{key}\"], df=spark.table(\"{table}\"),\n"
            f"                description=\"{name} from DataCrew run {c.run_id}\")\n"),
        "snowflake-feature-store": (
            "from snowflake.ml.feature_store import CreationMode, Entity, FeatureStore, FeatureView\n\n"
            "fs = FeatureStore(session=session, database=session.get_current_database(), name=\"FEATURE_STORE\",\n"
            "                  default_warehouse=session.get_current_warehouse(), creation_mode=CreationMode.CREATE_IF_NOT_EXIST)\n"
            f"entity = Entity(name=\"{d['name'].upper()}\", join_keys=[\"{key.upper()}\"])\n"
            "fs.register_entity(entity)\n"
            f"view = FeatureView(name=\"{name.upper()}\", entities=[entity], feature_df=session.table(\"{table}\"),\n"
            "                   refresh_freq=\"1 day\")\n"
            "fs.register_feature_view(feature_view=view, version=\"1\")\n"),
        "sagemaker-feature-store": (
            "import boto3\n\n"
            "sm = boto3.client(\"sagemaker\")\n"
            f"sm.create_feature_group(\n    FeatureGroupName=\"{name.replace('_', '-')}\",\n"
            f"    RecordIdentifierFeatureName=\"{key}\",\n    EventTimeFeatureName=\"event_time\",\n"
            "    FeatureDefinitions=[\n"
            f"        {{\"FeatureName\": \"{key}\", \"FeatureType\": \"String\"}},\n"
            "        {\"FeatureName\": \"event_time\", \"FeatureType\": \"String\"},\n"
            + "".join(f"        {{\"FeatureName\": \"{n}\", \"FeatureType\": \"{'Integral' if n == 'row_count' else 'Fractional'}\"}},\n" for n in feats)
            + "    ],\n    OfflineStoreConfig={\"S3StorageConfig\": {\"S3Uri\": \"${FEATURE_STORE_S3_URI}\"}},\n"
              "    RoleArn=\"${SAGEMAKER_FEATURE_ROLE_ARN}\",\n)\n"),
        "feast": (
            "from datetime import timedelta\n\nfrom feast import Entity, FeatureView, Field\n"
            "from feast.infra.offline_stores.file_source import FileSource\nfrom feast.types import Float64, Int64\n\n"
            f"entity = Entity(name=\"{d['name']}\", join_keys=[\"{key}\"])\n"
            f"source = FileSource(path=\"${{FEATURE_EXPORT_PATH}}/{name}.parquet\", timestamp_field=\"event_time\")\n"
            f"view = FeatureView(name=\"{name}\", entities=[entity], ttl=timedelta(days=2), source=source, schema=[\n"
            + "".join(f"    Field(name=\"{n}\", dtype={'Int64' if n == 'row_count' else 'Float64'}),\n" for n in feats) + "])\n"),
    }.get(store)
    if reg:
        c.files["features/register.py"] = (
            f'"""Register the feature set `{name}` in {store} (run {c.run_id}).\n\n'
            "Run by the ML platform identity after G8. It registers features that already exist as a governed table;\n"
            'it creates no new data and holds no credentials.\n"""\n' + reg)
    else:
        c.files["features/REGISTER.md"] = (
            f"# Registering `{name}` in {store}\n\nNo registration script is generated for {store}. Register the table "
            f"`{table}` from `feature_spec.yaml`: the entity, join key, feature names and types are all there.\n")
        c.gaps.append(f"feature_store `{store}`: registration is described in features/REGISTER.md, not scripted")
    rows = c.run(sql)
    keys = [r[0] for r in rows]
    c.check("ml-features", "The feature set has one row per business key", len(keys) == len(set(keys)) and bool(keys),
            f"{len(keys)} rows, {len(feats)} features")
    c.check("ml-features", "No key is missing", all(k is not None for k in keys), f"{sum(k is None for k in keys)} null keys")


# ----------------------------------------------------------------------------- natural-language assistant
def _ai_assistant(c: Ctx, consumers: list[dict]) -> None:
    tool = stacks.tool(c.p, "ai_consumption")
    if tool == "platform-native":
        tool = {"snowflake": "snowflake-cortex-analyst", "databricks": "databricks-genie", "fabric": "fabric-copilot",
                "bigquery": "bigquery-conversational-analytics"}.get(c.engine, "platform-native")
    metrics = c.model.get("metrics", [])
    verified = [{"name": m["name"], "question": f"What is the {m['label'].lower()}?", "sql": c.metric_sql(m), "metric": m}
                for m in metrics]
    for i, cons in enumerate(consumers[: len(metrics)]):       # the questions consumers actually asked, where a metric answers
        verified.append({"name": f"consumer_question_{i + 1}", "question": cons["question"], "sql": c.metric_sql(metrics[i % len(metrics)]),
                         "metric": metrics[i % len(metrics)], "asked_by": cons["name"]})
    tables = []
    for e in c.model["entities"]:
        dims, times, facts = [], [], []
        for a in c.open_attrs(e):
            base = ph.parse_type(a["type"])[0]
            item = {"name": a["name"], "expr": a["name"], "data_type": ph.phys_type(a["type"], c.dialect),
                    "description": a.get("description") or a["name"]}
            if base in ("date", "timestamp", "timestamp_tz"):
                times.append(item)
            elif base in ("decimal", "integer", "bigint") and not a["pk"] and not a.get("fk"):
                facts.append(item)
            else:
                dims.append(item)
        tables.append({"name": e["name"], "description": f"{e.get('description') or e['name']}. Grain: {e.get('grain', '')}.",
                       "base_table": {"schema": c.schema, "table": c.view(e).split(".")[-1]},
                       "dimensions": dims, "time_dimensions": times, "facts": facts})
    rels = [{"name": f"{e['name']}_to_{a['fk']['entity']}", "left_table": e["name"], "right_table": a["fk"]["entity"],
             "relationship_columns": [{"left_column": a["name"], "right_column": a["fk"]["attribute"]}],
             "join_type": "left_outer", "relationship_type": "many_to_one"}
            for e in c.model["entities"] for a in c.open_attrs(e) if a.get("fk") and a["fk"]["entity"] in c.entities]
    rules = ["Answer only from the tables listed here. If a question needs data that is not here, say so.",
             "Use the governed metric definitions exactly; do not invent a different formula.",
             "Restricted attributes are not available. Do not try to reconstruct them.",
             "Say which table and metric an answer came from."]
    semantic = {"name": c.product, "description": c.model.get("description") or c.model["name"], "tables": tables,
                "relationships": rels,
                "metrics": [{"name": m["name"], "description": m["definition"], "expr": c.target(c.metric_sql(m)).split("SELECT ", 1)[1].split(" FROM ")[0]}
                            for m in metrics],
                "verified_queries": [{"name": v["name"], "question": v["question"], "sql": c.target(v["sql"]),
                                      "verified_by": "DataCrew sandbox execution", **({"asked_by": v["asked_by"]} if v.get("asked_by") else {})}
                                     for v in verified],
                "custom_instructions": " ".join(rules)}
    if tool == "snowflake-cortex-analyst":
        c.files["assistant/semantic_model.yaml"] = (
            "# Cortex Analyst semantic model. Upload to a stage and reference it from the Cortex Analyst API or an agent.\n"
            + dump_yaml(semantic))
    elif tool == "databricks-genie":
        c.files["assistant/genie_space.md"] = (
            f"# Genie space: {c.model['name']}\n\n## Tables to add\n\n" + "\n".join(f"- `{c.view(e)}`: {e.get('description') or e['name']}"
                                                                                      for e in c.model["entities"])
            + "\n\n## General instructions\n\n" + "\n".join(f"- {r}" for r in rules)
            + "\n\n## Metric definitions\n\n" + "\n".join(f"- **{m['label']}**: {m['definition']}" for m in metrics)
            + "\n\n## Example SQL (add as trusted examples)\n\n"
            + "\n\n".join(f"**{v['question']}**\n\n```sql\n{c.target(v['sql'])}\n```" for v in verified) + "\n")
        c.files["assistant/semantic_context.yaml"] = dump_yaml(semantic)
    else:
        c.files["assistant/semantic_context.yaml"] = (
            f"# Semantic context for {tool}: tables, joins, governed metrics and verified question-and-SQL pairs.\n"
            + dump_yaml(semantic))
    c.files["assistant/evaluation.yaml"] = dump_yaml({
        "purpose": "Questions with a known answer. Ask each one in the assistant after it is configured and compare.",
        "pass_rule": "The assistant's number equals `expected` and it names the metric it used.",
        "questions": [{"question": v["question"], "metric": v["metric"]["name"],
                       "expected": (lambda r: round(r, 4) if isinstance(r, (int, float)) else r)(c.run(v["sql"])[0][0])}
                      for v in verified]})
    ok = 0
    for v in verified:
        got = c.run(v["sql"])[0][0]
        direct = c.sb.db.execute(c.sb.metric_sql(v["metric"])).fetchone()[0]
        ok += got == direct
    c.check("ai-assistant", "Every verified query returns the governed metric value", ok == len(verified), f"{ok} of {len(verified)} equal")
    exposed = [a for t in tables for a in t["dimensions"] + t["facts"] + t["time_dimensions"]
               if any(a["name"] in c.restricted(e) for e in c.model["entities"] if e["name"] == t["name"])]
    c.check("ai-assistant", "The semantic model exposes no Restricted attribute", not exposed, f"{sum(len(t['dimensions']) + len(t['facts']) + len(t['time_dimensions']) for t in tables)} columns described")


# ----------------------------------------------------------------------------- retrieval index
def _ai_retrieval(c: Ctx) -> None:
    store = stacks.tool(c.p, "vector_store")
    docs = []
    for e in c.model["entities"]:
        docs.append({"id": f"table:{e['name']}", "kind": "table", "title": e.get("label") or e["name"],
                     "text": f"{e.get('label') or e['name']}: {e.get('description') or ''}. Grain: {e.get('grain', '')}. "
                             f"Query it as {c.view(e)}.", "object": c.view(e)})
        for a in e["attributes"]:
            masked = a["classification"] == "restricted"
            docs.append({"id": f"column:{e['name']}.{a['name']}", "kind": "column", "title": f"{e['name']}.{a['name']}",
                         "text": f"Column {a['name']} of {e['name']}: {a.get('description') or a['name']}. "
                                 + ("It is Restricted and masked for consumers." if masked else f"Type {a['type']}."),
                         "object": c.view(e)})
    for m in c.model.get("metrics", []):
        docs.append({"id": f"metric:{m['name']}", "kind": "metric", "title": m["label"],
                     "text": f"Metric {m['label']}: {m['definition']} Unit: {m.get('unit', '')}. Grain: {m.get('grain', '')}.",
                     "object": c.view(c.entities[m["entity"]])})
    c.files["retrieval/documents.jsonl"] = "".join(json.dumps(d) + "\n" for d in docs)
    table = f"{c.schema}.product_documents"
    head = (f"-- Search index over what {c.model['name']} contains (run {c.run_id}).\n"
            "-- The documents describe tables, columns and metrics. They hold no row of business data,\n"
            "-- so an AI application can find the right table without seeing anyone's data.\n")
    if store == "snowflake-cortex-search":
        c.files["retrieval/index.sql"] = head + (
            f"CREATE OR REPLACE CORTEX SEARCH SERVICE {c.schema}.{c.product}_search\n  ON text\n  ATTRIBUTES kind, object\n"
            f"  WAREHOUSE = ${{WAREHOUSE}}\n  TARGET_LAG = '1 day'\n  AS (SELECT id, kind, title, text, object FROM {table});\n")
    elif store == "bigquery-vector-search":
        c.files["retrieval/index.sql"] = head + (
            f"CREATE OR REPLACE TABLE {table}_embedded AS\nSELECT * FROM ML.GENERATE_EMBEDDING(\n  MODEL `${{EMBEDDING_MODEL}}`,\n"
            f"  (SELECT id, kind, title, text AS content, object FROM {table}));\n"
            f"CREATE VECTOR INDEX IF NOT EXISTS {c.product}_idx ON {table}_embedded(ml_generate_embedding_result)\n"
            "  OPTIONS (index_type = 'IVF', distance_type = 'COSINE');\n")
    elif store == "pgvector":
        c.files["retrieval/index.sql"] = head + (
            "CREATE EXTENSION IF NOT EXISTS vector;\n"
            "CREATE TABLE IF NOT EXISTS product_documents (id TEXT PRIMARY KEY, kind TEXT, title TEXT, text TEXT, object TEXT,\n"
            "  embedding vector(${EMBEDDING_DIMENSIONS}));\n"
            "CREATE INDEX IF NOT EXISTS product_documents_embedding ON product_documents USING hnsw (embedding vector_cosine_ops);\n")
    elif store == "databricks-vector-search":
        c.files["retrieval/create_index.py"] = (
            f'"""Create the vector index over the product documents of {c.model["name"]} (run {c.run_id}).\n\n'
            'The documents describe tables, columns and metrics; they hold no row of business data.\n"""\n'
            "from databricks.vector_search.client import VectorSearchClient\n\n"
            "client = VectorSearchClient()\n"
            "client.create_delta_sync_index(\n    endpoint_name=\"${VECTOR_SEARCH_ENDPOINT}\",\n"
            f"    index_name=\"{table}_index\",\n    source_table_name=\"{table}\",\n    pipeline_type=\"TRIGGERED\",\n"
            "    primary_key=\"id\",\n    embedding_source_column=\"text\",\n"
            "    embedding_model_endpoint_name=\"${EMBEDDING_ENDPOINT}\",\n)\n")
    elif store == "opensearch":
        c.files["retrieval/index.json"] = json.dumps({"settings": {"index": {"knn": True}}, "mappings": {"properties": {
            "id": {"type": "keyword"}, "kind": {"type": "keyword"}, "title": {"type": "text"}, "text": {"type": "text"},
            "object": {"type": "keyword"},
            "embedding": {"type": "knn_vector", "dimension": 1024, "method": {"name": "hnsw", "engine": "faiss", "space_type": "cosinesimil"}}}}},
            indent=2)
    elif store == "azure-ai-search":
        c.files["retrieval/index.json"] = json.dumps({"name": f"{c.product.replace('_', '-')}-documents", "fields": [
            {"name": "id", "type": "Edm.String", "key": True, "filterable": True},
            {"name": "kind", "type": "Edm.String", "filterable": True, "facetable": True},
            {"name": "title", "type": "Edm.String", "searchable": True}, {"name": "text", "type": "Edm.String", "searchable": True},
            {"name": "object", "type": "Edm.String", "filterable": True},
            {"name": "embedding", "type": "Collection(Edm.Single)", "searchable": True, "dimensions": 1536,
             "vectorSearchProfile": "default"}],
            "vectorSearch": {"algorithms": [{"name": "hnsw", "kind": "hnsw"}],
                             "profiles": [{"name": "default", "algorithm": "hnsw"}]}}, indent=2)
    else:
        c.gaps.append(f"vector_store `{store}` has no template")
    if store in ("opensearch", "azure-ai-search"):
        c.gaps.append(f"vector_store `{store}`: set the embedding dimension in retrieval/index.json to match the chosen embedding model")
    ids = [d["id"] for d in docs]
    c.check("ai-retrieval", "Every table, column and metric has one document", len(ids) == len(set(ids)),
            f"{len(docs)} documents")
    leak = [d["id"] for d in docs if "***" in d["text"]]
    c.check("ai-retrieval", "Documents describe the product and contain no business data", not leak,
            "metadata only: names, descriptions, grains, definitions")


# ----------------------------------------------------------------------------- file extracts
def _file_extract(c: Ctx) -> None:
    out, manifest = [f"-- Scheduled exports of {c.model['name']} from {c.engine} (run {c.run_id}).",
                     "-- Each export reads a masked view and writes Parquet. The row count of each export is written to the",
                     "-- manifest as a control total, so the receiver can prove it got every row.", ""], []
    for e in c.model["entities"]:
        name = ph.table_name(e, c.p).lower()
        sel = f"SELECT {', '.join(a['name'] for a in c.open_attrs(e))} FROM @@{e['name']}@@"
        loc = f"${{EXPORT_ROOT}}/{c.product}/{name}"
        t = c.target(sel)
        stmt = {
            "snowflake": f"COPY INTO @export_stage/{c.product}/{name}/ FROM ({t})\n  FILE_FORMAT = (TYPE = PARQUET) HEADER = TRUE OVERWRITE = TRUE;",
            "redshift": f"UNLOAD ('{t}')\n  TO '{loc}/' IAM_ROLE '${{REDSHIFT_UNLOAD_ROLE_ARN}}' FORMAT AS PARQUET ALLOWOVERWRITE;",
            "bigquery": f"EXPORT DATA OPTIONS (uri = '{loc}/*.parquet', format = 'PARQUET', overwrite = true) AS\n{t};",
            "databricks": f"INSERT OVERWRITE DIRECTORY '{loc}' USING PARQUET\n{t};",
            "trino": f"UNLOAD ({t})\n  TO '{loc}/' WITH (format = 'PARQUET');" if c.engine == "athena" else
                     f"-- Trino writes exports through a Hive catalog table on the export location\n"
                     f"CREATE TABLE hive.exports.{name} WITH (format = 'PARQUET', external_location = '{loc}/') AS\n{t};",
            "tsql": f"CREATE EXTERNAL TABLE exports.{name}\n  WITH (LOCATION = '{c.product}/{name}/', DATA_SOURCE = export_lake, FILE_FORMAT = parquet_format)\n  AS {t};",
            "postgres": f"\\copy ({t}) TO PROGRAM 'cat > ${{EXPORT_DIR}}/{name}.csv' WITH (FORMAT csv, HEADER true)",
            "duckdb": f"COPY ({t}) TO '{name}.parquet' (FORMAT PARQUET);",
        }.get(c.dialect)
        if not stmt:
            c.gaps.append(f"file-extract: no export statement for dialect `{c.dialect}`")
            return
        out += [f"-- {e.get('label') or e['name']}", stmt, ""]
        rows = c.run(f"SELECT COUNT(*) FROM ({sel})")[0][0]
        manifest.append({"export": name, "source": c.view(e), "format": "csv" if c.dialect == "postgres" else "parquet",
                         "location": f"{loc}/", "columns": [a["name"] for a in c.open_attrs(e)],
                         "excluded_restricted_columns": c.restricted(e), "control_total_rows_in_rehearsal": rows})
    c.files["extracts/export.sql"] = "\n".join(out)
    c.files["extracts/manifest.yaml"] = dump_yaml({
        "product": c.model["name"], "schedule": "daily, after the publish pipeline", "delivery": "pull from the export location",
        "receiver_check": "compare the received row count with the control total written by each run",
        "exports": manifest})
    c.check("file-extract", "Every export statement reads a masked view and selects no Restricted column",
            all(not set(m["columns"]) & set(m["excluded_restricted_columns"]) for m in manifest), f"{len(manifest)} exports")
    c.check("file-extract", "Every export returned rows in the rehearsal", all(m["control_total_rows_in_rehearsal"] > 0 for m in manifest),
            ", ".join(f"{m['export']}={m['control_total_rows_in_rehearsal']}" for m in manifest))


GENERATORS = {"data-api": _data_api, "data-sharing": _data_sharing, "reverse-etl": _reverse_etl, "ml-features": _ml_features,
              "ai-retrieval": _ai_retrieval, "file-extract": _file_extract}


def generate(patterns: list[str], model: dict, profile: dict, run_id: str, sandbox, consumers: list[dict] | None = None) -> dict:
    """Artifacts and executed checks for the chosen patterns. `bi` and `sql` are produced by the stage itself."""
    c = Ctx(model, profile, run_id, sandbox)
    for p in patterns:
        if p == "ai-assistant":
            _ai_assistant(c, consumers or [])
        elif p in GENERATORS:
            GENERATORS[p](c)
    return {"files": c.files, "checks": c.checks, "gaps": c.gaps}
