"""Medallion pipeline code for the target cloud: source database -> bronze -> silver -> gold -> analytics.

    pipelines/01_ingest   source DB  -> bronze   (open table format on S3 / ADLS / GCS / OneLake)
    pipelines/02_curate   bronze     -> silver   -> gold (same format, MERGE-based, idempotent)
    pipelines/03_publish  gold       -> analytics engine (zero-copy where the engine reads the format)

Tool-specific syntax lives only here and in codegen.py (the adapter layer). Nothing here runs in
this environment against a cloud: the Local lakehouse runner executes the equivalent logic on the
same model, mapping and generated gold SQL to prove it before promotion.
"""
from __future__ import annotations

import json
import re

from ..catalog.stacks import PATTERN_LABELS, ZERO_COPY_FORMATS, source_pattern, tool
from ..modeling import physical as ph
from ..util import dump_yaml
from . import ingest_patterns

JDBC = {
    "oracle": ("oracle.jdbc.OracleDriver", "jdbc:oracle:thin:@//${SOURCE_HOST}:1521/${SOURCE_SERVICE}",
               "com.oracle.database.jdbc:ojdbc11:23.5.0.24.07"),
    "db2": ("com.ibm.db2.jcc.DB2Driver", "jdbc:db2://${SOURCE_HOST}:50000/${SOURCE_DATABASE}", "com.ibm.db2:jcc:11.5.9.0"),
    "sqlserver": ("com.microsoft.sqlserver.jdbc.SQLServerDriver",
                  "jdbc:sqlserver://${SOURCE_HOST}:1433;databaseName=${SOURCE_DATABASE}", "com.microsoft.sqlserver:mssql-jdbc:12.8.1.jre11"),
    "postgres": ("org.postgresql.Driver", "jdbc:postgresql://${SOURCE_HOST}:5432/${SOURCE_DATABASE}", "org.postgresql:postgresql:42.7.4"),
    "mysql": ("com.mysql.cj.jdbc.Driver", "jdbc:mysql://${SOURCE_HOST}:3306/${SOURCE_DATABASE}", "com.mysql:mysql-connector-j:9.1.0"),
    "teradata": ("com.teradata.jdbc.TeraDriver", "jdbc:teradata://${SOURCE_HOST}/DATABASE=${SOURCE_DATABASE}", "com.teradata.jdbc:terajdbc:20.00.00.34"),
    "sap-hana": ("com.sap.db.jdbc.Driver", "jdbc:sap://${SOURCE_HOST}:30015/?databaseName=${SOURCE_DATABASE}", "com.sap.cloud.db.jdbc:ngdbc:2.22.12"),
    "netezza": ("org.netezza.Driver", "jdbc:netezza://${SOURCE_HOST}:5480/${SOURCE_DATABASE}", "client-supplied nzjdbc.jar (not on Maven Central)"),
    "mainframe-db2-zos": ("com.ibm.db2.jcc.DB2Driver", "jdbc:db2://${SOURCE_HOST}:446/${SOURCE_LOCATION}", "com.ibm.db2:jcc:11.5.9.0 (needs the Db2 Connect licence)"),
}
# Sources read through a Spark connector instead of JDBC: (format, options that locate one collection or table)
CONNECTOR = {
    "mongodb": ("mongodb", {"connection.uri": "${SOURCE_URI}", "database": "${SOURCE_DATABASE}", "collection": "<table>"}),
    "dynamodb": ("dynamodb", {"tableName": "<table>", "region": "${AWS_REGION}"}),
    "cosmosdb": ("cosmos.oltp", {"spark.cosmos.accountEndpoint": "${SOURCE_ENDPOINT}", "spark.cosmos.database": "${SOURCE_DATABASE}",
                                 "spark.cosmos.container": "<table>"}),
}
WATERMARK = "last_updated_ts"


def lake_name(table: str) -> str:
    return table.lower().replace(".", "__")


class MedallionGen:
    def __init__(self, model: dict, mapping: dict, profile: dict, run_id: str, gold_sql: dict[str, str],
                 curate_style: str = "sql"):
        self.model, self.mapping, self.p, self.run_id = model, mapping, profile, run_id
        self.curate_style = curate_style              # "sql": Spark SQL scripts; "pyspark": PySpark jobs
        self.gold_sql = gold_sql                      # entity table -> SELECT (silver refs) from codegen
        self.fmt = tool(profile, "table_format")
        self.src = tool(profile, "source_database")
        self.ing = tool(profile, "ingestion")
        self.lake = tool(profile, "lakehouse_compute")
        self.cat = tool(profile, "lake_catalog")
        self.engine = tool(profile, "compute_engine")
        self.orch = tool(profile, "orchestration")
        self.cloud = tool(profile, "cloud")
        self.pattern = source_pattern(profile)
        self.ingest_entry = ingest_patterns.entry_point(profile)
        self.root = (profile.get("variables") or {}).get("lake_root", "s3://acme-lake")
        self.catalog = {"unity-catalog": "main", "aws-glue-catalog": "glue_catalog", "biglake-metastore": "biglake",
                        "onelake": "onelake", "polaris": "polaris", "hive-metastore": "spark_catalog"}.get(self.cat, "lake")
        self.files: dict[str, str] = {}
        self.gaps: list[str] = []

    # ---------------------------------------------------------------- shared
    def source_tables(self) -> list[dict]:
        meta = {s["table"]: s for s in self.mapping.get("sources", [])}
        used = set()
        for m in self.mapping["mappings"]:
            parts = (m.get("source") or "").split(".")
            if len(parts) >= 3:
                used.add(".".join(parts[:2]))
            used |= set(re.findall(r"\{\{stg:([\w.]+)\}\}", m.get("expression") or ""))
        out = []
        for t in sorted(used):
            s = meta.get(t, {"table": t, "columns": []})
            pks = [c["name"] for c in s.get("columns", []) if c.get("pk")]
            out.append({"source": t.upper(), "bronze": f"{self.catalog}.bronze.{lake_name(t)}",
                        "silver": f"{self.catalog}.silver.{lake_name(t)}", "primary_key": pks,
                        "watermark": WATERMARK, "columns": s.get("columns", [])})
        return out

    def using(self) -> str:
        return {"iceberg": "iceberg", "delta": "delta", "hudi": "hudi"}.get(self.fmt, "iceberg")

    def generate(self) -> dict:
        self.ingest()
        self.curate()
        self.publish()
        self.orchestrate()
        self.files["pipelines/README.md"] = self.readme()
        return {"files": self.files, "gaps": self.gaps}

    # ---------------------------------------------------------------- pipeline 1: ingest
    def ingest(self):
        tables = self.source_tables()
        if self.ing == "adef-local-extract":
            self.files["pipelines/01_ingest/ingest_config.yaml"] = dump_yaml({
                "run_id": self.run_id, "executor": "adef local lakehouse runner (adef/lakehouse/runner.py)",
                "source": {"type": self.src, "watermark": WATERMARK}, "target": {"format": self.fmt, "layer": "bronze"},
                "tables": [{k: t[k] for k in ("source", "bronze", "primary_key", "watermark")} for t in tables]})
            return
        if self.pattern in ("files", "event-stream", "saas-api") or (
                self.pattern == "database-cdc" and self.ing in ("debezium-kafka", "fivetran", "airbyte", "qlik-replicate")):
            ingest_patterns.generate(self, tables)
            return
        if self.src in CONNECTOR:
            self._ingest_connector(tables)
            return
        drv = JDBC.get(self.src)
        if not drv:
            self.gaps.append(f"source_database `{self.src}` has no JDBC template; extraction is a binding gap")
            drv = ("<driver>", "<jdbc-url>", "<maven-coordinates>")
        cfg = {"run_id": self.run_id, "source": {"type": self.src, "jdbc_url": drv[1], "driver": drv[0],
                                                 "driver_package": drv[2],
                                                 "credentials": "${SOURCE_SECRET_REF} (resolved by the job role, never in code)"},
               "target": {"format": self.fmt, "catalog": self.catalog, "lake_root": self.root, "layer": "bronze"},
               "fetch_size": 10000, "partitions": 4,
               "tables": [{k: t[k] for k in ("source", "bronze", "primary_key", "watermark")} for t in tables]}
        self.files["pipelines/01_ingest/ingest_config.yaml"] = dump_yaml(cfg)
        write = ({"iceberg": 'df.writeTo(t["bronze"]).overwritePartitions()',
                  "delta": 'df.write.format("delta").mode("overwrite").option("replaceWhere", f"_batch_id = \'{batch_id}\'")'
                           '.option("mergeSchema", "true").saveAsTable(t["bronze"])',
                  "hudi": 'df.write.format("hudi").option("hoodie.table.name", t["bronze"].split(".")[-1]).mode("append")'
                          '.saveAsTable(t["bronze"])'}[self.using()])
        create = {"iceberg": "CREATE TABLE IF NOT EXISTS {t} USING iceberg PARTITIONED BY (_batch_id) AS SELECT * FROM _new WHERE 1=0",
                  "delta": "CREATE TABLE IF NOT EXISTS {t} USING delta PARTITIONED BY (_batch_id) AS SELECT * FROM _new WHERE 1=0",
                  "hudi": "CREATE TABLE IF NOT EXISTS {t} USING hudi AS SELECT * FROM _new WHERE 1=0"}[self.using()]
        self.files["pipelines/01_ingest/ingest_jdbc.py"] = f'''"""Pipeline 1 - extract {self.src} tables into bronze ({self.fmt}) - run {self.run_id}.

Runs on {self.lake}. Incremental on the {WATERMARK} watermark (pushed down to the source), one
partition per batch, idempotent: re-running a batch replaces only that batch's partition.
Credentials come from the secrets manager through the job role; nothing secret is in this file.
"""
import argparse
import json
from datetime import datetime, timezone

import yaml
from pyspark.sql import SparkSession, functions as F


def watermark(spark, table):
    try:
        return spark.sql(f"SELECT MAX({WATERMARK}) AS w FROM {{table}}").first()["w"]
    except Exception:  # first run: table does not exist yet
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="ingest_config.yaml")
    ap.add_argument("--batch-id", default=datetime.now(timezone.utc).strftime("B%Y%m%dT%H%M%S"))
    ap.add_argument("--user", required=True)
    ap.add_argument("--password-secret", required=True, help="secret name; resolved here, never logged")
    args = ap.parse_args()
    cfg = yaml.safe_load(open(args.config))
    spark = SparkSession.builder.appName("adef-ingest-{self.run_id}").getOrCreate()
    password = get_secret(args.password_secret)
    batch_id = args.batch_id
    report = []
    for t in cfg["tables"]:
        wm = watermark(spark, t["bronze"])
        query = f"SELECT * FROM {{t['source']}}" + (f" WHERE {WATERMARK.upper()} > TIMESTAMP '{{wm}}'" if wm else "")
        df = (spark.read.format("jdbc")
              .option("url", cfg["source"]["jdbc_url"]).option("driver", cfg["source"]["driver"])
              .option("query", query).option("user", args.user).option("password", password)
              .option("fetchsize", cfg["fetch_size"]).load())
        df = df.toDF(*[c.lower() for c in df.columns])
        df = (df.withColumn("_ingested_at", F.current_timestamp())
                .withColumn("_batch_id", F.lit(batch_id))
                .withColumn("_source_system", F.lit(cfg["source"]["type"])))
        df.createOrReplaceTempView("_new")
        spark.sql("{create}".format(t=t["bronze"]))
        {write}
        report.append({{"table": t["source"], "rows": df.count(), "watermark_from": str(wm) if wm else None}})
    print(json.dumps({{"batch_id": batch_id, "tables": report}}))


def get_secret(name):
    """Resolve the source password from the platform secret store (adapter: secrets slot)."""
{self._secret_snippet()}


if __name__ == "__main__":
    main()
'''
        if self.pattern == "database-cdc":
            self.files["pipelines/01_ingest/fold_landing.py"] = ingest_patterns._fill(
                ingest_patterns.FOLD, what="change events", tool=self.ing, run=self.run_id, fmt=self.fmt, lake=self.lake,
                catalog=self.catalog, using=self.using())
            landed = {"aws-dms": ("parquet", "op", "landing/dms"), "gcp-datastream": ("avro", "source_metadata.change_type",
                                                                                      "landing/datastream")}.get(
                self.ing, ("parquet", "op", f"landing/{self.src}"))
            cfg["landing"] = {"format": landed[0], "operation_column": landed[1], "written_by": self.ing}
            for t in cfg["tables"]:
                t["landing"] = f"{self.root}/{landed[2]}/{lake_name(t['source'])}/"
            self.files["pipelines/01_ingest/ingest_config.yaml"] = dump_yaml(cfg)
        if self.ing == "aws-dms":
            self.files["pipelines/01_ingest/dms/table-mappings.json"] = json.dumps({"rules": [
                {"rule-type": "selection", "rule-id": str(i + 1), "rule-name": f"include-{lake_name(t['source'])}",
                 "object-locator": {"schema-name": t["source"].split(".")[0], "table-name": t["source"].split(".")[1]},
                 "rule-action": "include"} for i, t in enumerate(tables)] + [
                {"rule-type": "transformation", "rule-id": "900", "rule-name": "lowercase-columns", "rule-target": "column",
                 "object-locator": {"schema-name": "%", "table-name": "%", "column-name": "%"}, "rule-action": "convert-lowercase"}]},
                indent=2)
            self.files["pipelines/01_ingest/dms/s3-target-endpoint.json"] = json.dumps({
                "EndpointType": "target", "EngineName": "s3",
                "S3Settings": {"BucketName": "${LANDING_BUCKET}", "BucketFolder": "landing/dms", "DataFormat": "parquet",
                               "ParquetVersion": "parquet-2-0", "TimestampColumnName": "_dms_ts", "IncludeOpForFullLoad": True,
                               "CdcInsertsAndUpdates": True, "ServiceAccessRoleArn": "${DMS_S3_ROLE_ARN}"}}, indent=2)
            self.files["pipelines/01_ingest/dms/README.md"] = (
                "AWS DMS full load + CDC from the source into Parquet under `landing/dms/`. `ingest_jdbc.py` is the "
                "fallback/full-reload path; `fold_landing.py` (same pattern, `spark.read.parquet`) merges each DMS batch "
                f"into the bronze {self.fmt} tables. Endpoint credentials live in Secrets Manager.\n")
        elif self.ing == "azure-data-factory":
            self.files["pipelines/01_ingest/adf/pl_ingest_bronze.json"] = json.dumps({
                "name": f"pl_ingest_bronze_{self.run_id.lower().replace('-', '_')}",
                "properties": {"parameters": {"batch_id": {"type": "string"}}, "activities": [
                    {"name": f"copy_{lake_name(t['source'])}", "type": "Copy", "typeProperties": {
                        "source": {"type": {"db2": "Db2Source", "oracle": "OracleSource", "sqlserver": "SqlServerSource",
                                            "postgres": "PostgreSqlV2Source", "mysql": "MySqlSource", "teradata": "TeradataSource",
                                            "sap-hana": "SapHanaSource", "netezza": "NetezzaSource"}.get(self.src, "RelationalSource"),
                                   "query": f"SELECT * FROM {t['source']} WHERE {WATERMARK.upper()} > '@{{pipeline().parameters.batch_id}}'"},
                        "sink": {"type": "ParquetSink", "storeSettings": {"type": "AzureBlobFSWriteSettings"}}},
                     "inputs": [{"referenceName": f"ds_{self.src}_source", "type": "DatasetReference"}],
                     "outputs": [{"referenceName": "ds_adls_landing", "type": "DatasetReference",
                                  "parameters": {"folder": f"landing/{lake_name(t['source'])}"}}]} for t in tables] + [
                    {"name": "fold_into_bronze", "type": "DatabricksNotebook" if self.lake == "databricks" else "SynapseNotebook",
                     "dependsOn": [{"activity": f"copy_{lake_name(t['source'])}", "dependencyConditions": ["Succeeded"]} for t in tables],
                     "typeProperties": {"notebookPath": "/pipelines/01_ingest/ingest_jdbc", "baseParameters": {"mode": "landing"}}}]}}, indent=2)
        elif self.ing == "gcp-datastream":
            self.files["pipelines/01_ingest/datastream/stream.yaml"] = dump_yaml({
                "displayName": f"adef-{self.run_id.lower()}-ingest",
                "sourceConfig": {"sourceConnectionProfile": f"projects/${{PROJECT}}/locations/${{REGION}}/connectionProfiles/{self.src}-source",
                                 f"{self.src}SourceConfig": {"includeObjects": {f"{self.src}Schemas": [
                                     {"schema": s, "tables": [{"table": t["source"].split(".")[1]} for t in tables if t["source"].startswith(s + ".")]}
                                     for s in sorted({t["source"].split(".")[0] for t in tables})]}}},
                "destinationConfig": {"destinationConnectionProfile": "projects/${PROJECT}/locations/${REGION}/connectionProfiles/gcs-landing",
                                      "gcsDestinationConfig": {"path": "/landing/datastream", "avroFileFormat": {}}},
                "backfillAll": {}})
        elif self.ing not in ("spark-jdbc", "adef-local-extract"):
            self.gaps.append(f"ingestion `{self.ing}` has no template; the Spark JDBC job is generated as the fallback")

    def _ingest_connector(self, tables: list[dict]) -> None:
        """A document or key-value database read through its Spark connector: nested fields are kept as JSON text."""
        fmt, options = CONNECTOR[self.src]
        self.files["pipelines/01_ingest/ingest_config.yaml"] = dump_yaml({
            "run_id": self.run_id, "source": {"type": self.src, "pattern": self.pattern, "format": fmt, "options": options,
                                              "credentials": "${SOURCE_SECRET_REF} (resolved by the job role, never in code)"},
            "target": {"format": self.fmt, "catalog": self.catalog, "lake_root": self.root, "layer": "bronze"},
            "tables": [{k: t[k] for k in ("source", "bronze", "primary_key", "watermark")} for t in tables]})
        self.files["pipelines/01_ingest/ingest_jdbc.py"] = ingest_patterns._fill(
            CONNECTOR_JOB, src=self.src, fmt=self.fmt, run=self.run_id, lake=self.lake, using=self.using(),
            watermark=WATERMARK)

    def _secret_snippet(self) -> str:
        s = tool(self.p, "secrets")
        if s == "aws-secrets-manager":
            return '    import boto3\n    return boto3.client("secretsmanager").get_secret_value(SecretId=name)["SecretString"]'
        if s == "azure-key-vault":
            return ('    from azure.identity import DefaultAzureCredential\n    from azure.keyvault.secrets import SecretClient\n'
                    '    import os\n    return SecretClient(os.environ["KEY_VAULT_URL"], DefaultAzureCredential()).get_secret(name).value')
        if s == "gcp-secret-manager":
            return ('    from google.cloud import secretmanager\n    c = secretmanager.SecretManagerServiceClient()\n'
                    '    return c.access_secret_version(name=f"{name}/versions/latest").payload.data.decode()')
        return '    import os\n    return os.environ[name]'

    # ---------------------------------------------------------------- pipeline 2: curate
    def curate(self):
        u = self.using()
        out = [f"-- Pipeline 2a - bronze -> silver ({u}), run {self.run_id}. Typed, trimmed, de-duplicated on the key,",
               "-- latest change wins. MERGE makes every run idempotent.", ""]
        cdc = self.pattern == "database-cdc"
        for t in self.source_tables():
            cols = t["columns"] or [{"name": "*", "type": "string"}]
            if cols[0]["name"] == "*":
                self.gaps.append(f"{t['source']}: no column metadata, silver keeps bronze columns as-is")
            sel = ", ".join(self._spark_cast(c["name"], c["type"]) for c in cols if c["name"] != "*") or "*"
            keys = t["primary_key"] or [cols[0]["name"]]
            on = " AND ".join(f"s.{k} = n.{k}" for k in keys)
            out += [f"CREATE TABLE IF NOT EXISTS {t['silver']} USING {u} AS",
                    f"SELECT {sel}, CAST(NULL AS TIMESTAMP) AS _ingested_at FROM {t['bronze']} WHERE 1 = 0;",
                    f"MERGE INTO {t['silver']} s USING (",
                    f"  SELECT * FROM (SELECT {sel}, _ingested_at{', _op' if cdc else ''}, ROW_NUMBER() OVER (PARTITION BY {', '.join(keys)} "
                    f"ORDER BY {WATERMARK} DESC, _ingested_at DESC) AS _rn FROM {t['bronze']}) WHERE _rn = 1",
                    f") n ON {on}"]
            if cdc:   # the latest change wins; a delete at the source removes the row from silver
                out += ["WHEN MATCHED AND n._op = 'D' THEN DELETE",
                        "WHEN MATCHED AND n._ingested_at > s._ingested_at THEN UPDATE SET *",
                        "WHEN NOT MATCHED AND n._op <> 'D' THEN INSERT *;", ""]
            else:
                out += ["WHEN MATCHED AND n._ingested_at > s._ingested_at THEN UPDATE SET *",
                        "WHEN NOT MATCHED THEN INSERT *;", ""]
        silver_sql = "\n".join(out)
        gold = [f"-- Pipeline 2b - silver -> gold ({u}): the approved dimensional model, run {self.run_id}.",
                "-- The SELECT bodies are generated from the approved mapping (MAP/BR IDs inline) and were executed",
                "-- by the local lakehouse rehearsal against the synthetic source before this code was proposed.", ""]
        for e in self.model["entities"]:
            t = ph.table_name(e, None)
            body = self.gold_sql.get(t)
            if not body:
                continue
            body = re.sub(r"\bsilver_([a-z0-9_]+)", lambda m: f"{self.catalog}.silver.{m.group(1)}", body)
            pk = next(a["name"] for a in e["attributes"] if a["pk"])
            target = f"{self.catalog}.gold.{t}"
            gold += [f"-- {e['label']} | grain: {e.get('grain')} | history: {e.get('history')}",
                     f"CREATE TABLE IF NOT EXISTS {target} USING {u} AS SELECT * FROM (\n{body}\n) WHERE 1 = 0;"]
            if e.get("history") == "type2":
                gold += ["-- SCD type 2 (ADR-001): close changed current versions, then insert new versions",
                         f"MERGE INTO {target} g USING (\n{body}\n) n ON g.{pk} = n.{pk} AND g.is_current = TRUE",
                         "WHEN MATCHED AND (" + " OR ".join(f"NOT (g.{a['name']} <=> n.{a['name']})" for a in e["attributes"] if not a["pk"])
                         + ") THEN UPDATE SET g.is_current = FALSE, g.valid_to = current_timestamp();",
                         f"INSERT INTO {target} SELECT n.* FROM (\n{body}\n) n LEFT JOIN {target} g ON g.{pk} = n.{pk} AND g.is_current = TRUE "
                         f"WHERE g.{pk} IS NULL;", ""]
            else:
                gold += [f"MERGE INTO {target} g USING (\n{body}\n) n ON g.{pk} = n.{pk}",
                         "WHEN MATCHED THEN UPDATE SET *", "WHEN NOT MATCHED THEN INSERT *;", ""]
        gold_sql = "\n".join(gold)
        if self.curate_style == "pyspark":
            self.files["pipelines/02_curate/bronze_to_silver.py"] = self._pyspark_job(
                "Pipeline 2a - bronze to silver", "bronze_to_silver", silver_sql)
            self.files["pipelines/02_curate/silver_to_gold.py"] = self._pyspark_job(
                "Pipeline 2b - silver to gold", "silver_to_gold", gold_sql)
            self.files["pipelines/02_curate/__init__.py"] = ""
            self.files["pipelines/02_curate/run_curate.py"] = (
                f'"""Runs pipeline 2 (curate) for {self.model["name"]}: bronze to silver, then silver to gold."""\n'
                "import importlib.util\nimport pathlib\nimport sys\n\nfrom pyspark.sql import SparkSession\n\n\n"
                "def _load(name):\n    path = pathlib.Path(__file__).with_name(f\"{name}.py\")\n"
                "    spec = importlib.util.spec_from_file_location(name, path)\n    module = importlib.util.module_from_spec(spec)\n"
                "    spec.loader.exec_module(module)\n    return module\n\n\n"
                "def main(only=None):\n"
                f"    spark = SparkSession.builder.appName(\"{self.run_id}-curate\").getOrCreate()\n"
                "    for step in (\"bronze_to_silver\", \"silver_to_gold\"):\n"
                "        _load(step).run(spark, only)\n\n\n"
                "if __name__ == \"__main__\":\n    main(sys.argv[1:] or None)\n")
        else:
            self.files["pipelines/02_curate/01_bronze_to_silver.sql"] = silver_sql
            self.files["pipelines/02_curate/02_silver_to_gold.sql"] = gold_sql

    def _pyspark_job(self, title: str, name: str, sql: str) -> str:
        """One PySpark module: every statement of the pipeline as a named step, run in order and safe to re-run."""
        steps: list[tuple[str, str]] = []
        for chunk in re.split(r";[ \t]*(?:\n|$)", sql):
            body = "\n".join(line for line in chunk.strip().splitlines())
            code = [line for line in body.splitlines() if line.strip() and not line.strip().startswith("--")]
            if not code:
                continue
            m = re.search(r"(?:CREATE TABLE IF NOT EXISTS|MERGE INTO|INSERT INTO)\s+([\w.]+)", body)
            verb = "create" if "CREATE TABLE" in code[0] else "merge" if "MERGE INTO" in code[0] else "insert"
            steps.append((f"{verb}:{m.group(1) if m else len(steps)}", body))
        items = ",\n".join(f'    ("{n}", """\n{s}\n""")' for n, s in steps)
        return (f'"""{title} ({self.using()}), run {self.run_id}.\n\n'
                "Generated from the approved mapping. Every statement is idempotent (CREATE IF NOT EXISTS, MERGE on the\n"
                'business key), so a failed run can be re-run safely. Run on the lakehouse Spark runtime.\n"""\n'
                "import sys\n\nfrom pyspark.sql import SparkSession\n\n"
                f"STEPS = [\n{items},\n]\n\n\n"
                "def run(spark, only=None):\n"
                '    """Run every step, or only those whose name contains one of the given table names."""\n'
                "    for name, statement in STEPS:\n"
                "        if only and not any(o in name for o in only):\n            continue\n"
                "        print(f\"[{__name__}] {name}\")\n        spark.sql(statement)\n\n\n"
                "if __name__ == \"__main__\":\n"
                f"    run(SparkSession.builder.appName(\"{self.run_id}-{name}\").getOrCreate(), sys.argv[1:] or None)\n")

    def _publish_runner(self) -> None:
        """A runner for pipeline 3 that uses the analytics engine's own command-line client. No credentials in the file."""
        cli = {"snowflake": ("SnowSQL", 'snowsql --connection "${SNOWSQL_CONNECTION:?set the named SnowSQL connection}" '
                             '-o exit_on_error=true -o friendly=false -f "$f"'),
               "bigquery": ("bq", 'bq query --use_legacy_sql=false --project_id "${BQ_PROJECT:?set the project}" < "$f"'),
               "redshift": ("psql", 'psql "${REDSHIFT_DSN:?set a DSN that uses IAM or pgpass, never a password}" -v ON_ERROR_STOP=1 -f "$f"'),
               "databricks": ("Databricks SQL CLI", 'dbsqlcli -e "$f"'),
               "athena": ("the AWS CLI", 'grep -v "^--" "$f" | while IFS= read -r statement; do\n'
                          '    [ -z "$statement" ] && continue\n'
                          '    aws athena start-query-execution --work-group "${ATHENA_WORKGROUP:?set the workgroup}" '
                          '--query-execution-context Database=serving --query-string "$statement"\n  done'),
               "trino": ("the Trino CLI", 'trino --server "${TRINO_SERVER:?set the coordinator URL}" --file "$f"'),
               "starburst": ("the Trino CLI", 'trino --server "${TRINO_SERVER:?set the coordinator URL}" --file "$f"'),
               "postgres": ("psql", 'psql "${POSTGRES_DSN:?set a DSN that uses pgpass or IAM, never a password}" -v ON_ERROR_STOP=1 -f "$f"'),
               "fabric": ("sqlcmd", 'sqlcmd -S "${SQL_ENDPOINT:?set the SQL endpoint}" -d "${SQL_DATABASE:?set the database}" -G -b -i "$f"'),
               "synapse": ("sqlcmd", 'sqlcmd -S "${SQL_ENDPOINT:?set the SQL endpoint}" -d "${SQL_DATABASE:?set the database}" -G -b -i "$f"'),
               }.get(self.engine)
        if not cli:
            return
        self.files["pipelines/03_publish/run_publish.sh"] = (
            "#!/usr/bin/env bash\n"
            f"# Pipeline 3 - publish gold to {self.engine} with {cli[0]}, run {self.run_id}.\n"
            "# Authentication comes from the client's own configuration (named connection, IAM or SSO).\n"
            "# This script holds no credentials. It is run by the release pipeline identity, not by a person.\n"
            "set -euo pipefail\n"
            'cd "$(dirname "$0")"\n'
            'for f in publish.sql; do\n  echo "running $f"\n  ' + cli[1] + "\ndone\n")

    def _spark_cast(self, col: str, ltype: str) -> str:
        base = ph.parse_type(ltype)[0]
        if base in ("json", "array"):      # kept as validated JSON text in silver; gold or serving parses it natively
            return f"CASE WHEN {col} IS NOT NULL AND get_json_object({col}, '$') IS NULL THEN NULL ELSE {col} END AS {col}"
        if base in ("uuid", "geography", "time"):
            return f"NULLIF(TRIM({col}), '') AS {col}"
        phys = ph.phys_type(ltype, "databricks")
        if phys == "STRING":
            return f"NULLIF(TRIM({col}), '') AS {col}"
        return f"TRY_CAST({col} AS {phys}) AS {col}" if phys not in ("BOOLEAN",) else f"CAST({col} AS BOOLEAN) AS {col}"

    # ---------------------------------------------------------------- pipeline 3: publish
    def publish(self):
        zero = self.fmt in ZERO_COPY_FORMATS.get(self.engine, set())
        ents = [(e, ph.table_name(e, None)) for e in self.model["entities"]]
        serving = ph.case("serving", self.p)
        masked = {t: [a["name"] for a in e["attributes"] if a["classification"] == "restricted"] for e, t in ents}

        def view(t, src):
            cols = ", ".join(f"'***' AS {a['name']}" if a["name"] in masked[t] else a["name"]
                             for e, tt in ents if tt == t for a in e["attributes"])
            if any(e.get("history") == "type2" for e, tt in ents if tt == t):
                cols += ", valid_from, valid_to, is_current"      # so consumers can ask for current rows
            return f"CREATE OR REPLACE VIEW {serving}.v_{t} AS SELECT {cols} FROM {src};"
        out = [f"-- Pipeline 3 - publish gold to {self.engine} ({'zero-copy' if zero else 'copy'}), run {self.run_id}.",
               "-- Consumers get the v_ views, which mask Restricted attributes (ADR-003).", ""]
        if self.engine == "snowflake":
            out += ["CREATE SCHEMA IF NOT EXISTS SERVING;",
                    "-- one-time platform setup (A3, Platform Owner): external volume and catalog integration",
                    "-- CREATE EXTERNAL VOLUME lake_volume STORAGE_LOCATIONS = ((NAME='lake' " + {
                        "aws": "STORAGE_PROVIDER='S3' STORAGE_BASE_URL='${LAKE_ROOT}/' STORAGE_AWS_ROLE_ARN='${SNOWFLAKE_LAKE_ROLE_ARN}'",
                        "azure": "STORAGE_PROVIDER='AZURE' STORAGE_BASE_URL='azure://${STORAGE_ACCOUNT}.blob.core.windows.net/lake/' "
                                 "AZURE_TENANT_ID='${AZURE_TENANT_ID}'",
                        "gcp": "STORAGE_PROVIDER='GCS' STORAGE_BASE_URL='gcs://${LAKE_BUCKET}/'"}.get(self.cloud, "") + "));",
                    ("-- CREATE CATALOG INTEGRATION lake_catalog CATALOG_SOURCE=GLUE CATALOG_NAMESPACE='gold' "
                     "TABLE_FORMAT=ICEBERG GLUE_AWS_ROLE_ARN='${SNOWFLAKE_GLUE_ROLE_ARN}' GLUE_CATALOG_ID='${AWS_ACCOUNT_ID}' ENABLED=TRUE;"
                     if self.cat == "aws-glue-catalog" else
                     "-- CREATE CATALOG INTEGRATION lake_catalog CATALOG_SOURCE=ICEBERG_REST TABLE_FORMAT=ICEBERG "
                     "CATALOG_NAMESPACE='gold' REST_CONFIG=(CATALOG_URI='${ICEBERG_REST_URI}' CATALOG_NAME='${ICEBERG_CATALOG}') "
                     "REST_AUTHENTICATION=(TYPE=OAUTH OAUTH_CLIENT_ID='${CATALOG_CLIENT_ID}' "
                     "OAUTH_CLIENT_SECRET='<set by the Platform Owner, never committed>' OAUTH_ALLOWED_SCOPES=('PRINCIPAL_ROLE:ALL')) "
                     "ENABLED=TRUE;"), ""]
            for e, t in ents:
                if zero:
                    out.append(f"CREATE OR REPLACE ICEBERG TABLE SERVING.{t.upper()} EXTERNAL_VOLUME = 'lake_volume' "
                               f"CATALOG = 'lake_catalog' CATALOG_TABLE_NAME = '{t}';")
                else:
                    out.append(f"COPY INTO SERVING.{t.upper()} FROM @lake_stage/gold/{t}/ FILE_FORMAT = (TYPE = PARQUET) "
                               "MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;")
                out.append(view(t, f"SERVING.{t.upper()}").replace(f"{serving}.v_", "SERVING.V_"))
            if zero:
                out += [f"ALTER ICEBERG TABLE SERVING.{t.upper()} REFRESH;" for e, t in ents]
        elif self.engine == "databricks":
            out += [f"CREATE SCHEMA IF NOT EXISTS {self.catalog}.serving;"]
            for e, t in ents:
                out.append(view(t, f"{self.catalog}.gold.{t}").replace(f"{serving}.v_", f"{self.catalog}.serving.v_"))
                out.append(f"GRANT SELECT ON VIEW {self.catalog}.serving.v_{t} TO `analysts`;")
        elif self.engine == "bigquery":
            out += ["CREATE SCHEMA IF NOT EXISTS serving;"]
            for e, t in ents:
                out.append(f"CREATE OR REPLACE EXTERNAL TABLE serving.{t} WITH CONNECTION `${{REGION}}.lake_connection` "
                           f"OPTIONS (format = '{'ICEBERG' if self.fmt == 'iceberg' else 'DELTA_LAKE'}', "
                           f"uris = ['{self.root}/gold/{t}{'/metadata/latest.metadata.json' if self.fmt == 'iceberg' else ''}']);")
                out.append(view(t, f"serving.{t}"))
        elif self.engine == "redshift":
            out += ["CREATE EXTERNAL SCHEMA IF NOT EXISTS gold_ext FROM DATA CATALOG DATABASE 'gold' "
                    "IAM_ROLE '${REDSHIFT_SPECTRUM_ROLE_ARN}';", "CREATE SCHEMA IF NOT EXISTS serving;"]
            for e, t in ents:
                out.append(f"CREATE MATERIALIZED VIEW serving.{t} AUTO REFRESH NO AS SELECT * FROM gold_ext.{t};")
                out.append(view(t, f"serving.{t}"))
        elif self.engine in ("fabric", "synapse"):
            out += ["-- Gold Delta tables in the lakehouse are exposed through its SQL analytics endpoint.",
                    "IF SCHEMA_ID('serving') IS NULL EXEC('CREATE SCHEMA serving');"]
            for e, t in ents:
                src = (f"[gold_lakehouse].[dbo].[{t}]" if self.engine == "fabric" else
                       f"OPENROWSET(BULK '{self.root}/gold/{t}/', FORMAT = 'DELTA') AS r")
                out.append(f"CREATE OR ALTER VIEW serving.{t} AS SELECT * FROM {src};")
                out.append(view(t, f"serving.{t}").replace("CREATE OR REPLACE VIEW", "CREATE OR ALTER VIEW"))
        elif self.engine == "athena":
            out += ["-- Athena reads the gold tables in place through the Glue Data Catalog: there is nothing to copy.",
                    "-- Each statement is submitted on its own (Athena runs one statement per request); run_publish.sh does that."]
            for e, t in ents:
                out.append(view(t, f"gold.{t}"))
        elif self.engine in ("trino", "starburst"):
            cat = {"iceberg": "iceberg", "delta": "delta", "hudi": "hudi"}[self.using()]
            out += [f"-- {self.engine} reads the gold tables in place through its `{cat}` catalog (connector to {self.cat}).",
                    f"CREATE SCHEMA IF NOT EXISTS {cat}.serving;"]
            for e, t in ents:
                out.append(view(t, f"{cat}.gold.{t}").replace(f"{serving}.v_", f"{cat}.serving.v_"))
        elif self.engine == "postgres":
            out += ["-- PostgreSQL does not read lake tables in place: gold is copied in. The load is a full replace inside",
                    "-- one transaction, so readers see either the previous version or the new one, never a partial load.",
                    "CREATE SCHEMA IF NOT EXISTS serving;", "BEGIN;"]
            for e, t in ents:
                cols = ", ".join(f"{a['name']} {ph.phys_type(a['type'], 'postgres')}" for a in e["attributes"])
                out += [f"CREATE TABLE IF NOT EXISTS serving.{t} ({cols});", f"TRUNCATE serving.{t};",
                        f"\\copy serving.{t} FROM PROGRAM 'cat ${{GOLD_EXPORT_DIR}}/{t}/*.csv' WITH (FORMAT csv, HEADER true)",
                        view(t, f"serving.{t}")]
            out.append("COMMIT;")
        elif self.engine == "duckdb-local":
            out.append("-- Executed by the ADEF local lakehouse runner (adef/lakehouse/runner.py, publish step).")
        else:
            self.gaps.append(f"compute_engine `{self.engine}` has no publish template")
        self.files["pipelines/03_publish/publish.sql"] = "\n".join(out) + "\n"
        self._publish_runner()

    # ---------------------------------------------------------------- orchestration of the three pipelines
    def orchestrate(self):
        dag = re.sub(r"\W+", "_", self.model["name"]).strip("_")
        py = self.curate_style == "pyspark"
        silver_file = "pipelines/02_curate/bronze_to_silver.py" if py else "pipelines/02_curate/01_bronze_to_silver.sql"
        gold_file = "pipelines/02_curate/silver_to_gold.py" if py else "pipelines/02_curate/02_silver_to_gold.sql"
        if self.orch == "airflow":
            submit = {"aws-glue": "GlueJobOperator", "emr-spark": "EmrServerlessStartJobOperator",
                      "dataproc": "DataprocSubmitJobOperator"}.get(self.lake, "SparkSubmitOperator")
            self.files[f"orchestration/dags/{dag}_medallion.py"] = f'''"""Medallion pipelines for {self.model["name"]} ({self.run_id}): ingest -> curate -> publish."""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.empty import EmptyOperator

# Operators per stack (adapter): ingest/curate run on {self.lake} via {submit}; publish runs SQL on {self.engine}.
with DAG(
    dag_id="{dag}_medallion",
    schedule="0 2 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args={{"retries": 2, "retry_delay": timedelta(minutes=10)}},
    tags=["adef", "{self.run_id}", "medallion"],
) as dag:
    ingest = EmptyOperator(task_id="p1_ingest_bronze")      # replace with {submit}({self.ingest_entry})
    silver = EmptyOperator(task_id="p2a_bronze_to_silver")  # replace with {submit}({silver_file})
    gold = EmptyOperator(task_id="p2b_silver_to_gold")      # replace with {submit}({gold_file})
    quality = EmptyOperator(task_id="quality_gate")         # quality/ rules; a critical failure stops publish
    publish = EmptyOperator(task_id="p3_publish_{self.engine.replace('-', '_')}")
    ingest >> silver >> gold >> quality >> publish
'''
        elif self.orch == "platform-workflows":
            self.files["resources/medallion_job.yml"] = dump_yaml({"resources": {"jobs": {f"{dag}_medallion": {
                "name": f"{dag}_medallion", "max_concurrent_runs": 1,
                "schedule": {"quartz_cron_expression": "0 0 2 * * ?", "timezone_id": "UTC"},
                "tasks": [{"task_key": "p1_ingest_bronze", "spark_python_task": {"python_file": self.ingest_entry}},
                          {"task_key": "p2_curate", "depends_on": [{"task_key": "p1_ingest_bronze"}],
                           **({"spark_python_task": {"python_file": silver_file}} if py else {"sql_task": {"file": {"path": silver_file}}})},
                          {"task_key": "p2_gold", "depends_on": [{"task_key": "p2_curate"}],
                           **({"spark_python_task": {"python_file": gold_file}} if py else {"sql_task": {"file": {"path": gold_file}}})},
                          {"task_key": "p3_publish", "depends_on": [{"task_key": "p2_gold"}],
                           "sql_task": {"file": {"path": "pipelines/03_publish/publish.sql"}}}]}}}})
        elif self.orch == "azure-data-factory":
            self.files["orchestration/adf/pl_medallion.json"] = json.dumps({"name": f"pl_{dag}_medallion", "properties": {
                "activities": [{"name": "p1_ingest", "type": "ExecutePipeline", "typeProperties": {
                    "pipeline": {"referenceName": f"pl_ingest_bronze_{self.run_id.lower().replace('-', '_')}", "type": "PipelineReference"}}},
                    {"name": "p2_curate", "type": "SynapseNotebook", "dependsOn": [{"activity": "p1_ingest", "dependencyConditions": ["Succeeded"]}],
                     "typeProperties": {"notebook": {"referenceName": "nb_curate", "type": "NotebookReference"}}},
                    {"name": "p3_publish", "type": "Script", "dependsOn": [{"activity": "p2_curate", "dependencyConditions": ["Succeeded"]}],
                     "typeProperties": {"scripts": [{"type": "NonQuery", "text": "-- pipelines/03_publish/publish.sql"}]}}]}}, indent=2)
        elif self.orch == "adef-runner":
            self.files["orchestration/run_local.sh"] = (
                "#!/usr/bin/env bash\n# Runs the three pipelines locally (ADEF local lakehouse runner).\nset -euo pipefail\n"
                f"python -m adef lakehouse run --run {self.run_id} --env \"${{1:-test}}\"\n")

    def readme(self) -> str:
        return (f"# Medallion pipelines - {self.model['name']}\n\n"
                f"| # | Pipeline | From | To | Runs on |\n|---|---|---|---|---|\n"
                f"| 1 | Ingest | `{self.src}` ({PATTERN_LABELS[self.pattern]}) | bronze `{self.fmt}` in `{self.catalog}` (`{self.root}`) | {self.ing} / {self.lake} |\n"
                f"| 2 | Curate | bronze | silver, gold (`{self.fmt}`) | "
                f"{'PySpark jobs' if self.curate_style == 'pyspark' else tool(self.p, 'transformation')} on {self.lake} |\n"
                f"| 3 | Publish | gold | `{self.engine}` serving layer | {'zero-copy' if self.fmt in ZERO_COPY_FORMATS.get(self.engine, set()) else 'copy'} |\n\n"
                + {"database-batch": "Incremental extraction uses the source `LAST_UPDATED_TS` watermark. ",
                   "database-cdc": "Change events are folded into bronze with their operation; deletes reach silver. ",
                   "files": "Each file is loaded exactly once; rows that do not fit the schema are quarantined. ",
                   "saas-api": "Application objects are landed by the connector and folded into bronze once. ",
                   "event-stream": "Topics are read with a checkpoint, so every message reaches bronze exactly once. "}[self.pattern]
                + "Every step is idempotent (MERGE on business keys), so a failed run can be re-run safely.\n")


CONNECTOR_JOB = '''"""Pipeline 1 - read __SRC__ collections into bronze (__FMT__) - run __RUN__.

__SRC__ is read through its Spark connector. Documents can be nested: every nested field is written to
bronze as JSON text, so no attribute is lost and the shape can change at the source without breaking
the load. Silver validates the JSON; the mapping says which paths become columns.
Incremental on the __WATERMARK__ watermark where the collection has it. Runs on __LAKE__.
"""
import argparse
import json
from datetime import datetime, timezone

import yaml
from pyspark.sql import SparkSession, functions as F
from pyspark.sql.types import ArrayType, MapType, StructType


def flatten_to_json(df):
    nested = [f.name for f in df.schema.fields if isinstance(f.dataType, (StructType, ArrayType, MapType))]
    for name in nested:
        df = df.withColumn(name, F.to_json(F.col(name)))
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="ingest_config.yaml")
    ap.add_argument("--batch-id", default=datetime.now(timezone.utc).strftime("B%Y%m%dT%H%M%S"))
    args = ap.parse_args()
    cfg = yaml.safe_load(open(args.config))
    spark = SparkSession.builder.appName("adef-ingest-__RUN__").getOrCreate()
    report = []
    for t in cfg["tables"]:
        reader = spark.read.format(cfg["source"]["format"])
        for key, value in cfg["source"]["options"].items():
            reader = reader.option(key, value.replace("<table>", t["source"].split(".")[-1]))
        df = flatten_to_json(reader.load())
        df = df.toDF(*[c.lower() for c in df.columns])
        try:
            last = spark.sql(f"SELECT MAX(__WATERMARK__) AS w FROM {t['bronze']}").first()["w"]
        except Exception:  # first run: the bronze table does not exist yet
            last = None
        if last is not None and "__WATERMARK__" in df.columns:
            df = df.filter(F.col("__WATERMARK__") > F.lit(last))
        df = (df.withColumn("_ingested_at", F.current_timestamp())
                .withColumn("_batch_id", F.lit(args.batch_id))
                .withColumn("_source_system", F.lit(cfg["source"]["type"])))
        df.write.format("__USING__").mode("append").option("mergeSchema", "true").saveAsTable(t["bronze"])
        report.append({"table": t["source"], "rows": df.count(), "watermark_from": str(last) if last else None})
    print(json.dumps({"batch_id": args.batch_id, "tables": report}))


if __name__ == "__main__":
    main()
'''
