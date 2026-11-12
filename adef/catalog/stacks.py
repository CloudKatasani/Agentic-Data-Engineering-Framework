"""Capability slots, tool options per slot, preset Stack Profiles, and validation.

Mirrors skills/adef-stack-binding/references/capability-slots.md. The Stack Profile is
the only source of truth for tool choice in a run.
"""
from __future__ import annotations

import copy
from pathlib import Path

from ..config import ADAPTERS_DIR

SLOTS: list[dict] = [
    {"slot": "cloud", "required": True, "job": "Hosting, identity, networking",
     "options": ["aws", "azure", "gcp", "on-premises"]},
    {"slot": "object_storage", "required": True, "job": "Landing and raw file storage",
     "options": ["s3", "adls", "gcs", "minio"]},
    {"slot": "table_format", "required": False, "job": "Open table format",
     "options": ["iceberg", "delta", "hudi", "none"]},
    {"slot": "compute_engine", "required": True, "job": "Warehouse or lakehouse engine",
     "options": ["snowflake", "databricks", "bigquery", "redshift", "synapse", "fabric", "postgres"]},
    {"slot": "ingestion", "required": True, "job": "Batch, CDC and streaming extraction",
     "options": ["native-loader", "fivetran", "informatica", "azure-data-factory", "aws-glue", "kafka-connect", "airbyte"]},
    {"slot": "transformation", "required": True, "job": "Modelled transformations",
     "options": ["dbt-core", "dbt-cloud", "spark-sql-pipelines", "dataform", "native-sql", "matillion", "informatica"]},
    {"slot": "orchestration", "required": True, "job": "Scheduling and dependencies",
     "options": ["airflow", "platform-workflows", "azure-data-factory", "snowflake-tasks", "dagster", "control-m"]},
    {"slot": "data_quality", "required": True, "job": "Rule execution and scoring",
     "options": ["dbt-tests", "great-expectations", "soda", "pipeline-expectations", "dataform-assertions", "native-metrics"]},
    {"slot": "catalog_governance", "required": True, "job": "Glossary, ownership, classification, policies",
     "options": ["collibra", "purview", "unity-catalog", "alation", "datahub", "atlan", "dataplex", "snowflake-horizon"]},
    {"slot": "lineage", "required": False, "job": "Technical and business lineage",
     "options": ["catalog-native", "openlineage", "none"]},
    {"slot": "virtualization", "required": False, "job": "Federated access layer",
     "options": ["none", "denodo", "trino", "starburst"]},
    {"slot": "semantic_layer", "required": False, "job": "Governed metrics",
     "options": ["platform-native", "dbt-semantic-layer", "atscale", "cube", "none"]},
    {"slot": "bi", "required": True, "job": "Reports and dashboards",
     "options": ["power-bi", "tableau", "looker", "qlik", "cognos"]},
    {"slot": "ai_consumption", "required": False, "job": "Natural-language access to governed data",
     "options": ["platform-native", "none"]},
    {"slot": "version_control", "required": True, "job": "Source control and review",
     "options": ["github", "gitlab", "azure-repos", "bitbucket"]},
    {"slot": "cicd", "required": True, "job": "Build, test, deploy automation",
     "options": ["github-actions", "gitlab-ci", "azure-pipelines", "jenkins"]},
    {"slot": "iac", "required": False, "job": "Infrastructure as code",
     "options": ["terraform", "bicep", "cloudformation", "none"]},
    {"slot": "secrets", "required": True, "job": "Credential storage by reference",
     "options": ["aws-secrets-manager", "azure-key-vault", "gcp-secret-manager", "hashicorp-vault"]},
    {"slot": "observability", "required": True, "job": "Pipeline, data and cost telemetry",
     "options": ["platform-native", "datadog", "monte-carlo", "grafana"]},
    {"slot": "itsm", "required": False, "job": "Tickets, incidents, change records",
     "options": ["jira", "servicenow", "none"]},
    {"slot": "approval_channel", "required": True, "job": "Where humans grant approvals",
     "options": ["adef-console", "pull-request-and-ticket", "chat-workflow"]},
]
SLOT_NAMES = [s["slot"] for s in SLOTS]


def _profile(pid, label, desc, slots, limits=None, standards=None, secrets_prefix="secrets/adef"):
    return {
        "profile_id": pid, "label": label, "description": desc, "profile_version": "1.0.0",
        "portability_required": False,
        "variables": {"org_prefix": "acme", "domain": "customer"},
        "environments": {
            "dev": {"purpose": "sandbox", "agent_max_class": "A1", "secrets_ref": f"{secrets_prefix}/dev"},
            "test": {"purpose": "shared", "agent_max_class": "A2", "secrets_ref": f"{secrets_prefix}/test"},
            "prod": {"purpose": "production", "agent_max_class": "A0", "secrets_ref": f"{secrets_prefix}/prod"},
        },
        "slots": {k: ({"tool": v, "version": "current"} if v != "none" else {"tool": "none", "reason": "not required for v1"})
                  for k, v in slots.items()},
        "limits": limits or {"max_compute_size": "S", "auto_suspend_seconds": 60, "query_timeout_seconds": 120,
                             "profiling_row_cap": 10000, "monthly_cost_cap": 500},
        "standards": standards or {"layers": ["raw", "conformed", "curated", "data_product"],
                                   "naming_case": "upper_snake", "history_default": "type-2", "timezone": "UTC",
                                   "branch_strategy": "trunk-with-feature-branches", "protected_branches": ["main"]},
    }


LAKE = {"layers": ["bronze", "silver", "gold", "data_product"], "naming_case": "lower_snake",
        "history_default": "type-2", "timezone": "UTC", "branch_strategy": "trunk-with-feature-branches",
        "protected_branches": ["main"]}

PRESETS: list[dict] = [
    _profile("example-a", "AWS + Snowflake + dbt + Airflow",
             "Cloud data platform, SQL-first transformation (spec Example Profile A).",
             {"cloud": "aws", "object_storage": "s3", "table_format": "iceberg", "compute_engine": "snowflake",
              "ingestion": "native-loader", "transformation": "dbt-core", "orchestration": "airflow",
              "data_quality": "dbt-tests", "catalog_governance": "collibra", "lineage": "catalog-native",
              "virtualization": "none", "semantic_layer": "platform-native", "bi": "power-bi",
              "ai_consumption": "platform-native", "version_control": "github", "cicd": "github-actions",
              "iac": "terraform", "secrets": "aws-secrets-manager", "observability": "platform-native",
              "itsm": "servicenow", "approval_channel": "adef-console"}),
    _profile("example-b", "Azure + Databricks Lakehouse",
             "Lakehouse with pipeline and notebook tooling (spec Example Profile B).",
             {"cloud": "azure", "object_storage": "adls", "table_format": "delta", "compute_engine": "databricks",
              "ingestion": "azure-data-factory", "transformation": "spark-sql-pipelines",
              "orchestration": "platform-workflows", "data_quality": "pipeline-expectations",
              "catalog_governance": "unity-catalog", "lineage": "catalog-native", "virtualization": "none",
              "semantic_layer": "none", "bi": "power-bi", "ai_consumption": "none", "version_control": "azure-repos",
              "cicd": "azure-pipelines", "iac": "terraform", "secrets": "azure-key-vault",
              "observability": "platform-native", "itsm": "jira", "approval_channel": "adef-console"},
             standards=LAKE, secrets_prefix="kv/adef"),
    _profile("gcp-bigquery", "GCP + BigQuery + Dataform + Looker",
             "Serverless warehouse on Google Cloud with Dataform and Looker.",
             {"cloud": "gcp", "object_storage": "gcs", "table_format": "none", "compute_engine": "bigquery",
              "ingestion": "native-loader", "transformation": "dataform", "orchestration": "airflow",
              "data_quality": "dataform-assertions", "catalog_governance": "dataplex", "lineage": "catalog-native",
              "virtualization": "none", "semantic_layer": "platform-native", "bi": "looker",
              "ai_consumption": "platform-native", "version_control": "github", "cicd": "github-actions",
              "iac": "terraform", "secrets": "gcp-secret-manager", "observability": "platform-native",
              "itsm": "jira", "approval_channel": "adef-console"},
             standards=dict(LAKE, layers=["raw", "staging", "curated", "data_product"]), secrets_prefix="projects/adef/secrets"),
    _profile("azure-fabric", "Microsoft Fabric + Purview + Power BI",
             "Unified SaaS analytics on Microsoft Fabric with Purview governance.",
             {"cloud": "azure", "object_storage": "adls", "table_format": "delta", "compute_engine": "fabric",
              "ingestion": "azure-data-factory", "transformation": "dbt-core", "orchestration": "azure-data-factory",
              "data_quality": "dbt-tests", "catalog_governance": "purview", "lineage": "catalog-native",
              "virtualization": "none", "semantic_layer": "platform-native", "bi": "power-bi",
              "ai_consumption": "platform-native", "version_control": "azure-repos", "cicd": "azure-pipelines",
              "iac": "bicep", "secrets": "azure-key-vault", "observability": "platform-native", "itsm": "servicenow",
              "approval_channel": "adef-console"}, secrets_prefix="kv/adef"),
    _profile("aws-redshift", "AWS + Redshift + Glue + Tableau",
             "AWS-native warehouse with Glue ingestion, dbt and Tableau.",
             {"cloud": "aws", "object_storage": "s3", "table_format": "iceberg", "compute_engine": "redshift",
              "ingestion": "aws-glue", "transformation": "dbt-core", "orchestration": "airflow",
              "data_quality": "great-expectations", "catalog_governance": "datahub", "lineage": "openlineage",
              "virtualization": "none", "semantic_layer": "dbt-semantic-layer", "bi": "tableau",
              "ai_consumption": "none", "version_control": "gitlab", "cicd": "gitlab-ci", "iac": "terraform",
              "secrets": "aws-secrets-manager", "observability": "datadog", "itsm": "jira",
              "approval_channel": "adef-console"}, standards=dict(LAKE, naming_case="lower_snake")),
]

# compute engine -> SQL dialect used by the DDL exporter and code generator
DIALECT_FOR_ENGINE = {"snowflake": "snowflake", "databricks": "databricks", "bigquery": "bigquery",
                      "redshift": "redshift", "synapse": "tsql", "fabric": "tsql", "postgres": "postgres"}

# Which tools the built-in generators / exporters know how to target.
SUPPORTED_BY_GENERATOR = {
    "transformation": {"dbt-core", "dbt-cloud", "spark-sql-pipelines", "dataform", "native-sql"},
    "orchestration": {"airflow", "platform-workflows", "azure-data-factory", "snowflake-tasks", "dagster"},
    "cicd": {"github-actions", "gitlab-ci", "azure-pipelines", "jenkins"},
    "compute_engine": set(DIALECT_FOR_ENGINE),
}

COMPAT_RULES = [
    ("transformation", "spark-sql-pipelines", "compute_engine", {"databricks"},
     "Spark SQL pipelines need a Spark-based compute engine"),
    ("transformation", "dataform", "compute_engine", {"bigquery"}, "Dataform targets BigQuery"),
    ("orchestration", "snowflake-tasks", "compute_engine", {"snowflake"}, "Snowflake tasks need Snowflake"),
    ("orchestration", "platform-workflows", "compute_engine", {"databricks"}, "Platform workflows are Databricks Jobs"),
    ("data_quality", "pipeline-expectations", "transformation", {"spark-sql-pipelines"},
     "Pipeline expectations need Spark SQL pipelines"),
    ("data_quality", "dbt-tests", "transformation", {"dbt-core", "dbt-cloud"}, "dbt tests need dbt"),
    ("data_quality", "dataform-assertions", "transformation", {"dataform"}, "Dataform assertions need Dataform"),
    ("catalog_governance", "unity-catalog", "compute_engine", {"databricks"}, "Unity Catalog governs Databricks"),
    ("catalog_governance", "snowflake-horizon", "compute_engine", {"snowflake"}, "Horizon governs Snowflake"),
    ("table_format", "delta", "compute_engine", {"databricks", "fabric", "synapse"}, "Delta needs a Delta-capable engine"),
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
    for env, cfg in (profile.get("environments") or {}).items():
        ref = str(cfg.get("secrets_ref", ""))
        if not ref:
            blocking.append(f"Environment `{env}` has no secrets_ref")
        from ..guardrails.scanners import scan_secrets
        if scan_secrets(ref):
            blocking.append(f"Environment `{env}` secrets_ref looks like a literal credential")
    return {"rows": rows, "blocking": blocking, "warnings": warnings, "ok": not blocking}
