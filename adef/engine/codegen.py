"""Pipeline code generation bound to the Stack Profile (stack-binding T3 + pipeline-build).

Generates readable, idempotent code for one work package, with MAP/BR/DQ IDs in comments
and in the manifest. Tool-specific syntax lives only here (the adapter layer); a tool the
generator does not know produces an explicit binding gap, never improvised syntax.
"""
from __future__ import annotations

import re
from collections import Counter

from ..catalog.stacks import tool
from ..modeling import physical as ph
from ..modeling.exports import export_dbt_schema
from ..modeling.logical import parse_type
from ..util import dump_yaml


def _src_table(source: str) -> str | None:
    parts = (source or "").split(".")
    return ".".join(parts[:2]) if len(parts) >= 3 else None


def _src_col(source: str) -> str:
    return (source or "").split(".")[-1]


def stg_name(table: str) -> str:
    return "stg_" + table.replace(".", "__")


class CodeGen:
    def __init__(self, model: dict, mapping: list[dict], dq: list[dict], profile: dict, run_id: str,
                 entity_filters: dict | None = None, package: str = "WP-001", sources: list[dict] | None = None):
        self.sources = sources or []
        self.model, self.mapping, self.dq, self.p = model, mapping, dq, profile
        self.run_id, self.pkg = run_id, package
        self.filters = entity_filters or {}
        self.dialect = ph.dialect_for(profile)
        self.trans = tool(profile, "transformation")
        self.orch = tool(profile, "orchestration")
        self.cicd = tool(profile, "cicd")
        self.iac = tool(profile, "iac")
        self.engine = tool(profile, "compute_engine")
        self.schema = ph.schema_name(profile)
        self.raw_schema = ph.schema_name(profile, 0)
        self.stg_schema = ph.schema_name(profile, 1)
        self.gaps: list[str] = []
        self.files: dict[str, str] = {}
        self.implemented: set[str] = set()

    # ------------------------------------------------------------ helpers
    def rows_for(self, entity: str) -> list[dict]:
        return [m for m in self.mapping if m["target_entity"] == entity]

    def main_table(self, entity: str) -> str | None:
        c = Counter(_src_table(m["source"]) for m in self.rows_for(entity) if _src_table(m["source"]))
        return c.most_common(1)[0][0] if c else None

    def source_tables(self) -> list[str]:
        out = set()
        for m in self.mapping:
            t = _src_table(m.get("source", ""))
            if t:
                out.add(t)
            for ref in re.findall(r"\{\{stg:([\w.]+)\}\}", m.get("expression") or ""):
                out.add(ref)
        return sorted(out)

    def ref(self, table: str) -> str:
        if self.trans in ("dbt-core", "dbt-cloud"):
            return "{{ ref('" + stg_name(table) + "') }}"
        if self.trans == "dataform":
            return "${ref('" + stg_name(table) + "')}"
        return f"{self.stg_schema}.{stg_name(table)}"

    def render_expr(self, expr: str) -> str:
        return re.sub(r"\{\{stg:([\w.]+)\}\}", lambda m: self.ref(m.group(1)), expr)

    @staticmethod
    def _lines(items: list[tuple[str, str]], indent: str) -> str:
        out = []
        for i, (expr, tag) in enumerate(items):
            comma = "," if i < len(items) - 1 else ""
            out.append(f"{indent}{expr}{comma}  {tag}".rstrip())
        return "\n".join(out)

    def entity_select(self, e: dict) -> str:
        main = self.main_table(e["name"])
        rows = {m["target_attribute"]: m for m in self.rows_for(e["name"])}
        inner: list[tuple[str, str]] = []
        outer: list[tuple[str, str]] = []
        for a in e["attributes"]:
            m = rows.get(a["name"])
            tag = f"-- {m['id']}" if m else "-- unmapped"
            if m and m.get("business_rule"):
                tag += f" {m['business_rule']}"
            if m:
                self.implemented.add(m["id"])
                if m.get("business_rule"):
                    self.implemented.add(m["business_rule"])
            # A derived value computed from source columns (src.x, {{stg:..}}) belongs in the inner select, so
            # other derived values can reference it by name; only expressions over target attributes go outside.
            if m and m.get("source") == "derived" and not re.search(r"\bsrc\.|\{\{stg:", m.get("expression") or ""):
                expr = m.get("expression")
                if not expr:
                    self.gaps.append(f"{m['id']}: derived `{a['name']}` has no expression in the approved mapping")
                    expr = f"CAST(NULL AS {ph.phys_type(a['type'], self.dialect)})"
                    tag += " GAP"
                outer.append((f"{self.render_expr(expr)} AS {a['name']}", tag))
                continue
            if m and m.get("expression"):
                inner.append((f"{self.render_expr(m['expression'])} AS {a['name']}", tag))
            elif m and _src_table(m["source"]) == main:
                inner.append((f"src.{_src_col(m['source'])} AS {a['name']}", tag))
            else:
                why = f"source {m['source']} is outside the main relation" if m else "no mapping row"
                self.gaps.append(f"{e['name']}.{a['name']}: {why}; join pattern needs a design decision")
                inner.append((f"CAST(NULL AS {ph.phys_type(a['type'], self.dialect)}) AS {a['name']}", tag + " GAP"))
            outer.append((f"base.{a['name']}", ""))
        frm = self.ref(main) if main else "(SELECT 1) /* no source relation mapped */"
        sql = "WITH base AS (\n    SELECT\n" + self._lines(inner, "        ") + f"\n    FROM {frm} src"
        where = self.filters.get(e["name"])
        if where:
            sql += f"\n    WHERE {where}  -- entity filter (business rule)"
        # keep the target attribute order in the outer select
        order = {a["name"]: i for i, a in enumerate(e["attributes"])}
        outer.sort(key=lambda x: order.get(x[0].split(" AS ")[-1].replace("base.", ""), 0))
        return sql + "\n)\nSELECT\n" + self._lines(outer, "    ") + "\nFROM base\n"

    def pk(self, e):
        return next(a["name"] for a in e["attributes"] if a["pk"])

    def dq_sql(self, r: dict) -> str | None:
        e = next((x for x in self.model["entities"] if x["name"] == r["entity"]), None)
        if not e:
            return None
        t = f"{self.schema}.{ph.table_name(e, self.p)}"
        c, p = r.get("attribute"), r.get("params") or {}
        typ = r["type"]
        where = f" AND {p['where']}" if p.get("where") else ""
        if typ == "not_null":
            return f"SELECT * FROM {t} WHERE {c} IS NULL"
        if typ == "unique":
            return f"SELECT {c}, COUNT(*) AS n FROM {t} WHERE 1=1{where} GROUP BY {c} HAVING COUNT(*) > 1"
        if typ == "accepted_values":
            vals = ", ".join(f"'{v}'" for v in p.get("values", []))
            return f"SELECT * FROM {t} WHERE {c} NOT IN ({vals})"
        if typ == "range":
            return f"SELECT * FROM {t} WHERE {c} < {p.get('min')} OR {c} > {p.get('max')}"
        if typ == "referential":
            pe = next(x for x in self.model["entities"] if x["name"] == p["to_entity"])
            return (f"SELECT s.* FROM {t} s LEFT JOIN {self.schema}.{ph.table_name(pe, self.p)} r "
                    f"ON s.{c} = r.{p['to_attribute']} WHERE s.{c} IS NOT NULL AND r.{p['to_attribute']} IS NULL")
        if typ == "row_count_min":
            return f"SELECT 1 AS failed FROM (SELECT COUNT(*) AS n FROM {t}) x WHERE n < {p.get('min', 1)}"
        return None

    # ------------------------------------------------------------ generators
    def generate(self) -> dict:
        self.common()
        if self.trans in ("dbt-core", "dbt-cloud"):
            self.gen_dbt()
        elif self.trans == "spark-sql-pipelines":
            self.gen_spark()
        elif self.trans == "dataform":
            self.gen_dataform()
        elif self.trans == "native-sql":
            self.gen_native()
        elif self.trans in ("spark-sql", "duckdb-sql"):
            pass  # silver and gold are the medallion SQL below
        else:
            self.gaps.append(f"transformation tool `{self.trans}` has no reviewed adapter; generated portable SQL only")
            self.gen_native()
        self.gen_orchestration()
        self.gen_ci()
        self.gen_iac()
        self.gen_dq_files()
        self.gen_medallion()
        return {"files": self.files, "gaps": self.gaps, "implemented": sorted(self.implemented),
                "objects": [f"{self.schema}.{ph.table_name(e, self.p)}" for e in self.model["entities"]]}

    def common(self):
        self.files[".gitignore"] = "target/\ndbt_packages/\nlogs/\n.venv/\n__pycache__/\n*.env\n"
        self.files["README.md"] = (
            f"# {self.model['name']}\n\nGenerated by `adef-pipeline-build` for run `{self.run_id}`, work package "
            f"`{self.pkg}`.\n\n- Compute engine: `{self.engine}` (dialect `{self.dialect}`)\n- Transformation: "
            f"`{self.trans}`\n- Orchestration: `{self.orch}`\n- CI/CD: `{self.cicd}`\n\nTarget schema: "
            f"`{self.schema}`. Environment-specific values come from variables and the secrets manager by "
            "reference; no credentials are stored in this repository.\n\nDeployment happens only through the "
            "CI/CD pipeline identity after release gates G6a/G6b. Agents never push to `main`.\n")

    def gen_dbt(self):
        proj = self.model["name"].replace("-", "_")
        self.files["dbt_project.yml"] = dump_yaml({
            "name": proj, "version": "1.0.0", "config-version": 2, "profile": proj,
            "model-paths": ["models"], "snapshot-paths": ["snapshots"], "test-paths": ["tests"],
            "vars": {"org_prefix": (self.p.get("variables") or {}).get("org_prefix", "acme")},
            "models": {proj: {"staging": {"+materialized": "view", "+schema": self.stg_schema},
                              "marts": {"+materialized": "table", "+schema": self.schema}}}})
        self.files["profiles.example.yml"] = (
            f"# Copy to ~/.dbt/profiles.yml. Credentials are read from the environment, never committed.\n{proj}:\n"
            f"  target: dev\n  outputs:\n    dev:\n      type: {self.engine}\n"
            "      # account/host and credentials: env_var('...') populated from the secrets manager\n")
        srcs: dict[str, list] = {}
        for t in self.source_tables():
            sysname, tbl = t.split(".")
            srcs.setdefault(sysname, []).append(tbl)
        self.files["models/staging/_sources.yml"] = dump_yaml({"version": 2, "sources": [
            {"name": s, "schema": f"{self.raw_schema}_{s}".lower(), "tables": [{"name": t} for t in sorted(ts)]}
            for s, ts in srcs.items()]})
        for t in self.source_tables():
            sysname, tbl = t.split(".")
            self.files[f"models/staging/{stg_name(t)}.sql"] = (
                f"-- Staging: light typing and renaming only (layer {self.stg_schema})\n"
                f"SELECT *\nFROM {{{{ source('{sysname}', '{tbl}') }}}}\n")
        for e in self.model["entities"]:
            name = ph.table_name(e, None)
            body = self.entity_select(e)
            if e.get("history") == "type2":
                self.files[f"snapshots/{e['name']}_snapshot.sql"] = (
                    f"{{% snapshot {e['name']}_snapshot %}}\n{{{{ config(unique_key='{self.pk(e)}', strategy='check', "
                    f"check_cols='all', target_schema='{self.schema}') }}}}\n{body}{{% endsnapshot %}}\n")
                self.files[f"models/marts/{name}.sql"] = (
                    f"-- {e['label']}: type 2 history from snapshot\nSELECT\n    {{{{ dbt_utils.generate_surrogate_key"
                    f"(['{self.pk(e)}', 'dbt_valid_from']) }}}} AS {e['name']}_sk,\n    dbt_valid_from AS valid_from,\n"
                    f"    dbt_valid_to AS valid_to,\n    dbt_valid_to IS NULL AS is_current,\n    "
                    + ",\n    ".join(a["name"] for a in e["attributes"]) + f"\nFROM {{{{ ref('{e['name']}_snapshot') }}}}\n")
            elif e["kind"] == "fact":
                self.files[f"models/marts/{name}.sql"] = (
                    f"{{{{ config(materialized='incremental', unique_key='{self.pk(e)}', incremental_strategy='merge', "
                    f"on_schema_change='fail') }}}}\n-- {e['label']} | grain: {e.get('grain')}\n{body}")
            else:
                self.files[f"models/marts/{name}.sql"] = f"-- {e['label']} | grain: {e.get('grain')}\n{body}"
        self.files["models/marts/schema.yml"] = export_dbt_schema(self.model, {"profile": None, "dq_rules": self.dq})
        self.files["packages.yml"] = dump_yaml({"packages": [{"package": "dbt-labs/dbt_utils", "version": "1.3.0"}]})

    def gen_spark(self):
        for t in self.source_tables():
            self.files[f"pipelines/staging/{stg_name(t)}.sql"] = (
                f"-- Staging view over the raw landing table\nCREATE OR REFRESH MATERIALIZED VIEW {self.stg_schema}.{stg_name(t)}\n"
                f"AS SELECT * FROM {self.raw_schema}.{t.replace('.', '_')};\n")
        for e in self.model["entities"]:
            name = ph.table_name(e, self.p)
            cons = []
            for r in self.dq:
                if r["entity"] != e["name"] or not r.get("attribute"):
                    continue
                c, p = r["attribute"], r.get("params") or {}
                cond = {"not_null": f"{c} IS NOT NULL",
                        "accepted_values": f"{c} IN ({', '.join(repr(v) for v in p.get('values', []))})",
                        "range": f"{c} BETWEEN {p.get('min')} AND {p.get('max')}"}.get(r["type"])
                if cond:
                    act = "FAIL UPDATE" if r.get("severity") in ("critical", "high") else "DROP ROW"
                    cons.append(f"  CONSTRAINT {r['id'].lower().replace('-', '_')} EXPECT ({cond}) ON VIOLATION {act}")
            if e.get("history") == "type2":
                self.files[f"pipelines/marts/{name}.sql"] = (
                    f"-- {e['label']}: type 2 history via CDC apply\nCREATE OR REFRESH STREAMING TABLE {self.schema}.{name}"
                    + (" (\n" + ",\n".join(cons) + "\n)" if cons else "") + ";\n\n"
                    f"CREATE TEMPORARY VIEW {e['name']}_changes AS\n{self.entity_select(e)};\n\n"
                    f"APPLY CHANGES INTO {self.schema}.{name}\nFROM STREAM({e['name']}_changes)\nKEYS ({self.pk(e)})\n"
                    f"SEQUENCE BY current_timestamp()  -- use the source change timestamp column (ADR-001)\nSTORED AS SCD TYPE 2;\n")
            else:
                self.files[f"pipelines/marts/{name}.sql"] = (
                    f"-- {e['label']} | grain: {e.get('grain')}\nCREATE OR REFRESH MATERIALIZED VIEW {self.schema}.{name}"
                    + (" (\n" + ",\n".join(cons) + "\n)" if cons else "") + f"\nAS\n{self.entity_select(e)};\n")

    def gen_dataform(self):
        for t in self.source_tables():
            sysname, tbl = t.split(".")
            self.files[f"definitions/sources/{stg_name(t)}.sqlx"] = (
                f'config {{ type: "view", schema: "{self.stg_schema}" }}\nSELECT * FROM ${{ref("{self.raw_schema}_{sysname}", "{tbl}")}}\n')
        for e in self.model["entities"]:
            name = ph.table_name(e, None)
            nn = [r["attribute"] for r in self.dq if r["entity"] == e["name"] and r["type"] == "not_null"]
            cfg = {"type": "incremental" if e["kind"] == "fact" else "table", "schema": self.schema,
                   "uniqueKey": [self.pk(e)], "assertions": {"uniqueKey": [self.pk(e)], "nonNull": nn or [self.pk(e)]}}
            import json as _j
            self.files[f"definitions/marts/{name}.sqlx"] = f"config {_j.dumps(cfg, indent=2)}\n-- {e['label']}\n{self.entity_select(e)}"

    def gen_native(self):
        for t in self.source_tables():
            self.files[f"sql/00_staging/{stg_name(t)}.sql"] = (
                f"CREATE OR REPLACE VIEW {self.stg_schema}.{stg_name(t)} AS\nSELECT * FROM {self.raw_schema}.{t.replace('.', '_')};\n")
        for i, e in enumerate(self.model["entities"], start=1):
            name = ph.table_name(e, self.p)
            cols = [a["name"] for a in e["attributes"]]
            key = self.pk(e)
            hist = ""
            if e.get("history") == "type2":
                hist = ("-- Type 2: close current versions whose attributes changed, then insert new versions.\n"
                        "-- valid_from/valid_to/is_current maintained per adapter pattern `history-type2`.\n")
            self.files[f"sql/10_marts/{i:02d}_{name.lower()}.sql"] = (
                f"-- {e['label']} | grain: {e.get('grain')} | idempotent MERGE on {key}\n{hist}"
                f"MERGE INTO {self.schema}.{name} AS tgt\nUSING (\n{self.entity_select(e)}) AS s\nON tgt.{key} = s.{key}\n"
                f"WHEN MATCHED THEN UPDATE SET {', '.join(f'{c} = s.{c}' for c in cols if c != key)}\n"
                f"WHEN NOT MATCHED THEN INSERT ({', '.join(cols)}) VALUES ({', '.join('s.' + c for c in cols)});\n")
        if self.engine == "snowflake" and self.orch == "snowflake-tasks":
            pass

    def lake_gold_sql(self) -> dict[str, str]:
        """Gold SELECTs reading silver tables (shared with the local lakehouse runner)."""
        lake = CodeGen(self.model, self.mapping, self.dq, self.p, self.run_id, self.filters, self.pkg, self.sources)
        lake.ref = lambda table: "silver_" + table.lower().replace(".", "__")  # type: ignore[method-assign]
        return {ph.table_name(e, None): lake.entity_select(e) for e in self.model["entities"]}

    def gen_medallion(self):
        from .medallion import MedallionGen
        mg = MedallionGen(self.model, {"mappings": self.mapping, "sources": self.sources}, self.p, self.run_id,
                          self.lake_gold_sql()).generate()
        self.files.update(mg["files"])
        self.gaps += mg["gaps"]

    def gen_dq_files(self):
        for r in self.dq:
            sql = self.dq_sql(r)
            if not sql:
                continue
            self.implemented.add(r["id"])
            path = f"tests/dq/{r['id'].lower()}.sql" if self.trans.startswith("dbt") else f"quality/{r['id'].lower()}.sql"
            if self.trans.startswith("dbt"):
                sql = re.sub(rf"{re.escape(self.schema)}\.(\w+)", lambda m: "{{ ref('" + m.group(1).lower() + "') }}", sql)
            self.files[path] = (f"-- {r['id']} ({r['type']}, severity {r.get('severity')}, threshold {r.get('threshold')})"
                                f" traces {r.get('requirement')}\n-- Returns failing rows; zero rows = pass.\n{sql}\n")

    def gen_orchestration(self):
        dag = self.model["name"].replace("-", "_")
        if self.orch == "airflow":
            cmd = "dbt build --target {{ var.value.adef_env }}" if self.trans.startswith("dbt") else "run_sql_folder sql/"
            self.files[f"orchestration/dags/{dag}.py"] = f'''"""Airflow DAG for {self.model["name"]} ({self.run_id}). Retries are safe: every load is idempotent."""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

default_args = {{"owner": "data-platform", "retries": 2, "retry_delay": timedelta(minutes=10)}}

with DAG(
    dag_id="{dag}",
    schedule="0 3 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["adef", "{self.run_id}"],
) as dag:
    transform = BashOperator(task_id="transform_and_test", bash_command="{cmd}")
    freshness = BashOperator(task_id="source_freshness", bash_command="dbt source freshness || true")
    freshness >> transform
'''
        elif self.orch == "platform-workflows":
            self.files["resources/job.yml"] = dump_yaml({"resources": {
                "pipelines": {dag: {"name": dag, "catalog": "${var.catalog}", "target": self.schema,
                                    "libraries": [{"glob": {"include": "pipelines/**"}}]}},
                "jobs": {f"{dag}_daily": {"name": f"{dag}_daily", "max_concurrent_runs": 1,
                                          "schedule": {"quartz_cron_expression": "0 0 3 * * ?", "timezone_id": "UTC"},
                                          "tasks": [{"task_key": "refresh", "pipeline_task": {"pipeline_id": f"${{resources.pipelines.{dag}.id}}"}}]}}}})
            self.files["databricks.yml"] = dump_yaml({"bundle": {"name": dag}, "include": ["resources/*.yml"],
                                                      "variables": {"catalog": {"default": "main"}},
                                                      "targets": {"dev": {"mode": "development", "default": True},
                                                                  "test": {"mode": "production"}, "prod": {"mode": "production"}}})
        elif self.orch == "azure-data-factory":
            import json as _j
            self.files[f"orchestration/adf/pipeline_{dag}.json"] = _j.dumps({"name": f"pl_{dag}", "properties": {
                "activities": [{"name": "transform", "type": "Custom", "typeProperties": {"command": "dbt build"},
                                "policy": {"retry": 2, "timeout": "0.01:00:00"}}],
                "annotations": ["adef", self.run_id]}}, indent=2)
        elif self.orch == "snowflake-tasks":
            self.files["orchestration/tasks.sql"] = (
                f"CREATE OR REPLACE TASK {self.schema}.T_{dag.upper()}\n  WAREHOUSE = ${{WAREHOUSE}}\n"
                "  SCHEDULE = 'USING CRON 0 3 * * * UTC'\nAS\n  EXECUTE IMMEDIATE FROM @${STAGE}/sql/10_marts/;\n"
                "-- Tasks are created suspended; resuming is part of the G6 release, not the build.\n")
        elif self.orch == "dagster":
            self.files["orchestration/definitions.py"] = (
                f'from dagster import Definitions, ScheduleDefinition, define_asset_job\n\njob = define_asset_job("{dag}")\n'
                f'defs = Definitions(jobs=[job], schedules=[ScheduleDefinition(job=job, cron_schedule="0 3 * * *")])\n')
        elif self.orch != "adef-runner":
            self.gaps.append(f"orchestration tool `{self.orch}` has no generator; schedule documented in build plan only")

    def gen_ci(self):
        steps = ["pip install -r requirements-ci.txt", "gitleaks detect --no-banner", "sqlfluff lint --dialect "
                 + {"tsql": "tsql", "databricks": "sparksql"}.get(self.dialect, self.dialect if self.dialect != "ansi" else "ansi")]
        if self.trans.startswith("dbt"):
            steps += ["dbt deps", "dbt compile --target ci", "dbt build --target ci --select state:modified+"]
        else:
            steps += ["python -m adef_ci dry_run", "python -m adef_ci unit_tests"]
        self.files["requirements-ci.txt"] = "sqlfluff==3.2.5\n" + ("dbt-core==1.9.0\n" if self.trans.startswith("dbt") else "")
        if self.cicd == "github-actions":
            self.files[".github/workflows/ci.yml"] = dump_yaml({
                "name": "ci", "on": {"pull_request": {"branches": ["main"]}},
                "permissions": {"contents": "read"},
                "jobs": {"verify": {"runs-on": "ubuntu-latest", "steps": [{"uses": "actions/checkout@v4"},
                         {"uses": "actions/setup-python@v5", "with": {"python-version": "3.12"}}]
                         + [{"run": s} for s in steps]}}})
            self.files[".github/workflows/deploy.yml"] = dump_yaml({
                "name": "deploy", "on": {"workflow_dispatch": {"inputs": {"environment": {"required": True},
                                                                         "commit": {"required": True}}}},
                "jobs": {"deploy": {"runs-on": "ubuntu-latest", "environment": "${{ inputs.environment }}",
                                    "steps": [{"uses": "actions/checkout@v4", "with": {"ref": "${{ inputs.commit }}"}},
                                              {"name": "Verify tested commit equals deployed commit (G5 record)",
                                               "run": "python scripts/verify_release_hash.py ${{ inputs.commit }}"},
                                              {"run": "echo deploy via pipeline identity only"}]}}})
        elif self.cicd == "gitlab-ci":
            self.files[".gitlab-ci.yml"] = dump_yaml({"stages": ["verify"], "verify": {
                "stage": "verify", "image": "python:3.12", "script": steps,
                "rules": [{"if": "$CI_PIPELINE_SOURCE == 'merge_request_event'"}]}})
        elif self.cicd == "azure-pipelines":
            self.files["azure-pipelines.yml"] = dump_yaml({"trigger": "none", "pr": {"branches": {"include": ["main"]}},
                                                           "pool": {"vmImage": "ubuntu-latest"},
                                                           "steps": [{"script": s} for s in steps]})
        elif self.cicd == "jenkins":
            self.files["Jenkinsfile"] = ("pipeline {\n  agent any\n  stages {\n    stage('verify') {\n      steps {\n"
                                         + "".join(f"        sh '{s}'\n" for s in steps) + "      }\n    }\n  }\n}\n")

    def gen_iac(self):
        if self.iac != "terraform":
            return
        res = {"snowflake": f'resource "snowflake_schema" "data_product" {{\n  database = var.database\n  name     = "{self.schema}"\n}}\n',
               "databricks": f'resource "databricks_schema" "data_product" {{\n  catalog_name = var.catalog\n  name         = "{self.schema}"\n}}\n',
               "bigquery": f'resource "google_bigquery_dataset" "data_product" {{\n  dataset_id = "{self.schema}"\n  location   = var.location\n}}\n'}
        body = res.get(self.engine, f'# No reviewed terraform adapter for {self.engine}; schema created by migration.\n')
        self.files["infra/main.tf"] = (f"# Schema for {self.model['name']}. Applied only by the release pipeline (G6).\n"
                                       "variable \"database\" { default = \"\" }\nvariable \"catalog\" { default = \"main\" }\n"
                                       "variable \"location\" { default = \"US\" }\n\n" + body)


def manifest_types(model: dict, dialect: str) -> dict:
    return {e["name"]: {a["name"]: ph.phys_type(a["type"], dialect) for a in e["attributes"]} for e in model["entities"]}


_ = parse_type
