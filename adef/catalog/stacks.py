"""Capability slots, tool options per slot, preset Stack Profiles, and validation.

Mirrors skills/adef-stack-binding/references/capability-slots.md. The Stack Profile is
the only source of truth for tool choice in a run.
"""
from __future__ import annotations

import copy
from pathlib import Path

from ..config import ADAPTERS_DIR

SLOTS: list[dict] = [
    # --- hop 0: where the data lives today
    {"slot": "source_database", "required": True, "job": "Operational source database (system of record)",
     "options": ["oracle", "db2", "sqlserver", "postgres", "mysql", "teradata", "sap-hana", "sqlite-local"]},
    # --- hop 1: land in the cloud as an open table format (bronze)
    {"slot": "cloud", "required": True, "job": "Hyperscaler hosting the lake, identity, networking",
     "options": ["aws", "azure", "gcp", "local"]},
    {"slot": "object_storage", "required": True, "job": "Lake storage for bronze, silver and gold",
     "options": ["s3", "adls", "gcs", "onelake", "local-filesystem"]},
    {"slot": "table_format", "required": True, "job": "Open table format for every lake layer",
     "options": ["iceberg", "delta", "hudi"]},
    {"slot": "lake_catalog", "required": True, "job": "Table catalog for the open table format",
     "options": ["aws-glue-catalog", "unity-catalog", "polaris", "biglake-metastore", "hive-metastore", "onelake",
                 "sqlite-catalog"]},
    {"slot": "ingestion", "required": True, "job": "Pipeline 1: extract from the source database into bronze",
     "options": ["spark-jdbc", "aws-dms", "azure-data-factory", "gcp-datastream", "debezium-kafka", "fivetran",
                 "airbyte", "informatica", "adef-local-extract"]},
    # --- hop 2: curate bronze -> silver -> gold in the lake
    {"slot": "lakehouse_compute", "required": True, "job": "Pipeline 2: engine that curates silver and gold",
     "options": ["aws-glue", "emr-spark", "databricks", "dataproc", "synapse-spark", "fabric-spark", "duckdb-local"]},
    {"slot": "transformation", "required": True, "job": "How silver and gold transformations are written",
     "options": ["spark-sql", "spark-sql-pipelines", "dbt-core", "dbt-cloud", "dataform", "duckdb-sql", "native-sql",
                 "matillion", "informatica"]},
    # --- hop 3: serve from the analytics layer
    {"slot": "compute_engine", "required": True, "job": "Pipeline 3: analytics engine that serves gold",
     "options": ["snowflake", "databricks", "bigquery", "redshift", "synapse", "fabric", "postgres", "duckdb-local"]},
    {"slot": "orchestration", "required": True, "job": "Schedules and chains the three pipelines",
     "options": ["airflow", "platform-workflows", "azure-data-factory", "snowflake-tasks", "dagster", "control-m",
                 "adef-runner"]},
    {"slot": "data_quality", "required": True, "job": "Rule execution and scoring",
     "options": ["great-expectations", "dbt-tests", "soda", "pipeline-expectations", "dataform-assertions",
                 "native-metrics"]},
    {"slot": "catalog_governance", "required": True, "job": "Glossary, ownership, classification, policies",
     "options": ["collibra", "purview", "unity-catalog", "alation", "datahub", "atlan", "dataplex", "snowflake-horizon",
                 "adef-local-catalog"]},
    {"slot": "lineage", "required": False, "job": "Technical and business lineage",
     "options": ["catalog-native", "openlineage", "none"]},
    {"slot": "virtualization", "required": False, "job": "Federated access layer",
     "options": ["none", "denodo", "trino", "starburst"]},
    {"slot": "semantic_layer", "required": False, "job": "Governed metrics",
     "options": ["platform-native", "dbt-semantic-layer", "atscale", "cube", "none"]},
    {"slot": "bi", "required": True, "job": "Reports and dashboards",
     "options": ["power-bi", "tableau", "looker", "qlik", "cognos", "adef-console"]},
    {"slot": "ai_consumption", "required": False, "job": "Natural-language access to governed data",
     "options": ["platform-native", "none"]},
    {"slot": "version_control", "required": True, "job": "Source control and review",
     "options": ["github", "gitlab", "azure-repos", "bitbucket"]},
    {"slot": "cicd", "required": True, "job": "Build, test, deploy automation",
     "options": ["github-actions", "gitlab-ci", "azure-pipelines", "jenkins"]},
    {"slot": "iac", "required": False, "job": "Infrastructure as code",
     "options": ["terraform", "bicep", "cloudformation", "none"]},
    {"slot": "secrets", "required": True, "job": "Credential storage by reference",
     "options": ["aws-secrets-manager", "azure-key-vault", "gcp-secret-manager", "hashicorp-vault", "adef-vault"]},
    {"slot": "observability", "required": True, "job": "Pipeline, data and cost telemetry",
     "options": ["platform-native", "datadog", "monte-carlo", "grafana", "adef-console"]},
    {"slot": "itsm", "required": False, "job": "Tickets, incidents, change records",
     "options": ["jira", "servicenow", "none"]},
    {"slot": "approval_channel", "required": True, "job": "Where humans grant approvals",
     "options": ["adef-console", "pull-request-and-ticket", "chat-workflow"]},
]
SLOT_NAMES = [s["slot"] for s in SLOTS]
PIPELINE_SLOTS = ["source_database", "cloud", "object_storage", "table_format", "lake_catalog", "ingestion",
                  "lakehouse_compute", "transformation", "compute_engine"]


def _profile(pid, label, desc, slots, limits=None, standards=None, secrets_prefix="secrets/adef", executable=False):
    return {
        "profile_id": pid, "label": label, "description": desc, "profile_version": "2.0.0",
        "portability_required": False, "executable_locally": executable,
        "variables": {"org_prefix": "acme", "domain": "customer",
                      "lake_root": {"aws": "s3://acme-lake", "azure": "abfss://lake@acmelake.dfs.core.windows.net",
                                    "gcp": "gs://acme-lake", "local": "lake"}.get(slots.get("cloud"), "lake")},
        "environments": {
            "dev": {"purpose": "sandbox", "agent_max_class": "A1", "secrets_ref": f"{secrets_prefix}/dev"},
            "test": {"purpose": "shared", "agent_max_class": "A2", "secrets_ref": f"{secrets_prefix}/test"},
            "prod": {"purpose": "production", "agent_max_class": "A0", "secrets_ref": f"{secrets_prefix}/prod"},
        },
        "slots": {k: ({"tool": v, "version": "current"} if v != "none" else {"tool": "none", "reason": "not required for v1"})
                  for k, v in slots.items()},
        "limits": limits or {"max_compute_size": "S", "auto_suspend_seconds": 60, "query_timeout_seconds": 120,
                             "profiling_row_cap": 10000, "monthly_cost_cap": 500},
        "standards": standards or dict(MEDALLION),
    }


MEDALLION = {"layers": ["bronze", "silver", "gold", "serving"], "naming_case": "lower_snake",
             "history_default": "type-2", "timezone": "UTC", "branch_strategy": "trunk-with-feature-branches",
             "protected_branches": ["main"]}
COMMON = {"lineage": "openlineage", "virtualization": "none", "ai_consumption": "none", "itsm": "jira",
          "approval_channel": "adef-console"}

PRESETS: list[dict] = [
    _profile("example-a", "Oracle → AWS S3 Iceberg → Snowflake",
             "Oracle to S3 with AWS DMS, Iceberg tables in the Glue catalog curated with Glue Spark, "
             "served zero-copy from Snowflake.",
             {**COMMON, "source_database": "oracle", "cloud": "aws", "object_storage": "s3", "table_format": "iceberg",
              "lake_catalog": "aws-glue-catalog", "ingestion": "aws-dms", "lakehouse_compute": "aws-glue",
              "transformation": "spark-sql", "compute_engine": "snowflake", "orchestration": "airflow",
              "data_quality": "great-expectations", "catalog_governance": "collibra", "semantic_layer": "platform-native",
              "bi": "power-bi", "version_control": "github", "cicd": "github-actions", "iac": "terraform",
              "secrets": "aws-secrets-manager", "observability": "platform-native", "itsm": "servicenow"},
             standards=dict(MEDALLION, naming_case="upper_snake")),
    _profile("example-b", "DB2 → Azure ADLS Delta → Databricks",
             "IBM Db2 to ADLS with Azure Data Factory, Delta tables in Unity Catalog curated with Lakeflow "
             "declarative pipelines, served from Databricks SQL.",
             {**COMMON, "source_database": "db2", "cloud": "azure", "object_storage": "adls", "table_format": "delta",
              "lake_catalog": "unity-catalog", "ingestion": "azure-data-factory", "lakehouse_compute": "databricks",
              "transformation": "spark-sql-pipelines", "compute_engine": "databricks", "orchestration": "platform-workflows",
              "data_quality": "pipeline-expectations", "catalog_governance": "unity-catalog", "semantic_layer": "none",
              "bi": "power-bi", "version_control": "azure-repos", "cicd": "azure-pipelines", "iac": "terraform",
              "secrets": "azure-key-vault", "observability": "platform-native"}, secrets_prefix="kv/adef"),
    _profile("gcp-bigquery", "Oracle → GCS Iceberg → BigQuery",
             "Oracle to GCS with Datastream, Iceberg tables in the BigLake metastore curated on Dataproc, served "
             "from BigQuery as BigLake Iceberg tables.",
             {**COMMON, "source_database": "oracle", "cloud": "gcp", "object_storage": "gcs", "table_format": "iceberg",
              "lake_catalog": "biglake-metastore", "ingestion": "gcp-datastream", "lakehouse_compute": "dataproc",
              "transformation": "spark-sql", "compute_engine": "bigquery", "orchestration": "airflow",
              "data_quality": "great-expectations", "catalog_governance": "dataplex", "semantic_layer": "platform-native",
              "bi": "looker", "version_control": "github", "cicd": "github-actions", "iac": "terraform",
              "secrets": "gcp-secret-manager", "observability": "platform-native"}, secrets_prefix="projects/adef/secrets"),
    _profile("azure-fabric", "DB2 → OneLake Delta → Microsoft Fabric",
             "IBM Db2 to OneLake with Data Factory, Delta tables curated with Fabric Spark, served from the Fabric "
             "Warehouse with Purview governance.",
             {**COMMON, "source_database": "db2", "cloud": "azure", "object_storage": "onelake", "table_format": "delta",
              "lake_catalog": "onelake", "ingestion": "azure-data-factory", "lakehouse_compute": "fabric-spark",
              "transformation": "spark-sql", "compute_engine": "fabric", "orchestration": "azure-data-factory",
              "data_quality": "great-expectations", "catalog_governance": "purview", "semantic_layer": "platform-native",
              "bi": "power-bi", "version_control": "azure-repos", "cicd": "azure-pipelines", "iac": "bicep",
              "secrets": "azure-key-vault", "observability": "platform-native", "itsm": "servicenow"},
             secrets_prefix="kv/adef"),
    _profile("aws-redshift", "DB2 → AWS S3 Iceberg → Redshift",
             "IBM Db2 to S3 with Spark JDBC on EMR, Iceberg tables in the Glue catalog, served from Redshift "
             "through Spectrum external schemas.",
             {**COMMON, "source_database": "db2", "cloud": "aws", "object_storage": "s3", "table_format": "iceberg",
              "lake_catalog": "aws-glue-catalog", "ingestion": "spark-jdbc", "lakehouse_compute": "emr-spark",
              "transformation": "spark-sql", "compute_engine": "redshift", "orchestration": "airflow",
              "data_quality": "great-expectations", "catalog_governance": "datahub", "semantic_layer": "dbt-semantic-layer",
              "bi": "tableau", "version_control": "gitlab", "cicd": "gitlab-ci", "iac": "terraform",
              "secrets": "aws-secrets-manager", "observability": "datadog"}),
    _profile("local-lakehouse", "Local lakehouse (runs on this machine)",
             "Synthetic source database (SQLite, or a real Oracle/Db2 container) to Delta tables on local disk, "
             "curated with DuckDB and served from a DuckDB analytics database. Every pipeline really executes.",
             {**COMMON, "source_database": "sqlite-local", "cloud": "local", "object_storage": "local-filesystem",
              "table_format": "delta", "lake_catalog": "sqlite-catalog", "ingestion": "adef-local-extract",
              "lakehouse_compute": "duckdb-local", "transformation": "duckdb-sql", "compute_engine": "duckdb-local",
              "orchestration": "adef-runner", "data_quality": "native-metrics", "catalog_governance": "adef-local-catalog",
              "semantic_layer": "none", "bi": "adef-console", "version_control": "github", "cicd": "github-actions",
              "iac": "none", "secrets": "adef-vault", "observability": "adef-console", "itsm": "none"},
             secrets_prefix="adef-vault", executable=True),
]

# analytics engine -> SQL dialect used by the DDL exporter and serving-layer code
DIALECT_FOR_ENGINE = {"snowflake": "snowflake", "databricks": "databricks", "bigquery": "bigquery",
                      "redshift": "redshift", "synapse": "tsql", "fabric": "tsql", "postgres": "postgres",
                      "duckdb-local": "duckdb"}

# Which tools the built-in generators know how to target.
SUPPORTED_BY_GENERATOR = {
    "source_database": {"oracle", "db2", "sqlserver", "postgres", "mysql", "sqlite-local"},
    "ingestion": {"spark-jdbc", "aws-dms", "azure-data-factory", "gcp-datastream", "adef-local-extract"},
    "table_format": {"iceberg", "delta"},
    "lake_catalog": {"aws-glue-catalog", "unity-catalog", "biglake-metastore", "onelake", "hive-metastore",
                     "polaris", "sqlite-catalog"},
    "lakehouse_compute": {"aws-glue", "emr-spark", "databricks", "dataproc", "synapse-spark", "fabric-spark",
                          "duckdb-local"},
    "transformation": {"spark-sql", "spark-sql-pipelines", "dbt-core", "dbt-cloud", "dataform", "duckdb-sql",
                       "native-sql"},
    "orchestration": {"airflow", "platform-workflows", "azure-data-factory", "snowflake-tasks", "dagster", "adef-runner"},
    "cicd": {"github-actions", "gitlab-ci", "azure-pipelines", "jenkins"},
    "compute_engine": set(DIALECT_FOR_ENGINE),
}

# Executable locally by the ADEF runner (the rest is generated code for the target cloud).
LOCAL_EXECUTION = {"lakehouse_compute": {"duckdb-local"}, "source_database": {"sqlite-local", "oracle", "db2", "postgres"},
                   "table_format": {"delta", "iceberg"}}

CLOUD_OF = {"s3": "aws", "adls": "azure", "onelake": "azure", "gcs": "gcp", "local-filesystem": "local",
            "aws-glue-catalog": "aws", "biglake-metastore": "gcp", "onelake-catalog": "azure", "sqlite-catalog": "local",
            "aws-dms": "aws", "azure-data-factory": "azure", "gcp-datastream": "gcp", "adef-local-extract": "local",
            "aws-glue": "aws", "emr-spark": "aws", "dataproc": "gcp", "synapse-spark": "azure", "fabric-spark": "azure",
            "duckdb-local": "local"}

# analytics engine -> table formats it reads in place (zero-copy); otherwise gold is copied in
ZERO_COPY_FORMATS = {"snowflake": {"iceberg"}, "databricks": {"delta", "iceberg"}, "bigquery": {"iceberg", "delta"},
                     "redshift": {"iceberg", "hudi", "delta"}, "synapse": {"delta"}, "fabric": {"delta", "iceberg"},
                     "postgres": set(), "duckdb-local": set()}

COMPAT_RULES = [
    ("transformation", "spark-sql-pipelines", "lakehouse_compute", {"databricks"},
     "Lakeflow declarative (Spark SQL) pipelines run on Databricks"),
    ("transformation", "dataform", "compute_engine", {"bigquery"}, "Dataform runs in BigQuery"),
    ("transformation", "duckdb-sql", "lakehouse_compute", {"duckdb-local"}, "DuckDB SQL runs on the local DuckDB engine"),
    ("orchestration", "snowflake-tasks", "compute_engine", {"snowflake"}, "Snowflake tasks need Snowflake"),
    ("orchestration", "platform-workflows", "lakehouse_compute", {"databricks"}, "Platform workflows are Databricks Jobs"),
    ("orchestration", "adef-runner", "lakehouse_compute", {"duckdb-local"}, "The DataCrew runner executes the local lakehouse"),
    ("data_quality", "pipeline-expectations", "transformation", {"spark-sql-pipelines"},
     "Pipeline expectations need Lakeflow declarative pipelines"),
    ("data_quality", "dbt-tests", "transformation", {"dbt-core", "dbt-cloud"}, "dbt tests need dbt"),
    ("data_quality", "dataform-assertions", "transformation", {"dataform"}, "Dataform assertions need Dataform"),
    ("catalog_governance", "unity-catalog", "lakehouse_compute", {"databricks"}, "Unity Catalog governs Databricks"),
    ("lake_catalog", "unity-catalog", "lakehouse_compute", {"databricks"}, "Unity Catalog is Databricks' lake catalog"),
    ("catalog_governance", "snowflake-horizon", "compute_engine", {"snowflake"}, "Horizon governs Snowflake"),
    ("lakehouse_compute", "duckdb-local", "object_storage", {"local-filesystem"}, "The local engine reads local disk"),
    ("table_format", "hudi", "lakehouse_compute", {"emr-spark", "aws-glue", "dataproc"}, "Hudi needs a Spark engine with Hudi"),
]


def preset(profile_id: str) -> dict | None:
    p = next((p for p in PRESETS if p["profile_id"] == profile_id), None)
    return copy.deepcopy(p) if p else None


def tool(profile: dict, slot: str) -> str:
    return (profile.get("slots", {}).get(slot) or {}).get("tool", "none")


def dialect(profile: dict) -> str:
    return DIALECT_FOR_ENGINE.get(tool(profile, "compute_engine"), "ansi")


def adapter_path(slot: str, toolname: str) -> Path | None:
    d = ADAPTERS_DIR / slot
    if not d.exists():
        return None
    for f in sorted(d.glob(f"{toolname}-*.md")):
        if not f.name.endswith(".conformance.md"):
            return f
    return None


def validate(profile: dict) -> dict:
    """Task T1 of adef-stack-binding. Returns rows plus blocking gaps and warnings."""
    rows, blocking, warnings = [], [], []
    slots = profile.get("slots", {})
    for s in SLOTS:
        b = slots.get(s["slot"])
        t = (b or {}).get("tool")
        status, note = "bound", ""
        if not b or not t:
            status = "missing"
            if s["required"]:
                blocking.append(f"Required slot `{s['slot']}` is not bound")
        elif t == "none":
            status = "none"
            if s["required"]:
                blocking.append(f"Required slot `{s['slot']}` cannot be `none`")
            elif not b.get("reason"):
                warnings.append(f"Slot `{s['slot']}` bound to none without a reason")
        else:
            ap = adapter_path(s["slot"], t)
            if ap:
                note = f"adapter {ap.relative_to(ADAPTERS_DIR.parent)}"
            elif t in SUPPORTED_BY_GENERATOR.get(s["slot"], set()):
                note = "built-in generator template (adapter not yet reviewed)"
                warnings.append(f"`{s['slot']}:{t}` uses a built-in template; write and review an adapter before client use (E3-2)")
            else:
                note = "no adapter: design-time binding only"
                warnings.append(f"`{s['slot']}:{t}` has no adapter; agents will not improvise tool syntax for it")
        rows.append({"slot": s["slot"], "required": s["required"], "tool": t or "", "status": status, "note": note})
    for a_slot, a_tool, b_slot, allowed, why in COMPAT_RULES:
        if tool(profile, a_slot) == a_tool and tool(profile, b_slot) not in allowed:
            blocking.append(f"Incompatible: {a_slot}={a_tool} with {b_slot}={tool(profile, b_slot)} ({why})")
    cloud = tool(profile, "cloud")
    for sl in ("object_storage", "lake_catalog", "ingestion", "lakehouse_compute"):
        need = CLOUD_OF.get(tool(profile, sl))
        if need and cloud not in ("none", need):
            blocking.append(f"Incompatible: {sl}={tool(profile, sl)} runs on {need}, but cloud={cloud}")
    fmt, eng = tool(profile, "table_format"), tool(profile, "compute_engine")
    if eng in ZERO_COPY_FORMATS and fmt not in ZERO_COPY_FORMATS[eng]:
        warnings.append(f"{eng} does not read {fmt} tables in place; Pipeline 3 will copy gold into {eng} instead of "
                        "serving it zero-copy")
    for env, cfg in (profile.get("environments") or {}).items():
        ref = str(cfg.get("secrets_ref", ""))
        if not ref:
            blocking.append(f"Environment `{env}` has no secrets_ref")
        from ..guardrails.scanners import scan_secrets
        if scan_secrets(ref):
            blocking.append(f"Environment `{env}` secrets_ref looks like a literal credential")
    return {"rows": rows, "blocking": blocking, "warnings": warnings, "ok": not blocking,
            "executable_locally": is_local(profile)}


def is_local(profile: dict) -> bool:
    return all(tool(profile, s) in allowed for s, allowed in LOCAL_EXECUTION.items())


def pipeline_summary(profile: dict) -> list[dict]:
    """The three hops as tools, for docs and the console."""
    t = lambda s: tool(profile, s)  # noqa: E731
    zero = t("table_format") in ZERO_COPY_FORMATS.get(t("compute_engine"), set())
    return [
        {"pipeline": 1, "name": "Ingest", "from": f"{t('source_database')} source database",
         "to": f"bronze ({t('table_format')} on {t('object_storage')}, {t('lake_catalog')})", "tool": t("ingestion")},
        {"pipeline": 2, "name": "Curate", "from": "bronze", "to": f"silver and gold ({t('table_format')})",
         "tool": f"{t('transformation')} on {t('lakehouse_compute')}"},
        {"pipeline": 3, "name": "Publish", "from": "gold", "to": f"{t('compute_engine')} analytics layer",
         "tool": "zero-copy external tables" if zero else "copy into the analytics engine"},
    ]
