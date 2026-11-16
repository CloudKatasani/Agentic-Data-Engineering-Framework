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
    {"slot": "source_database", "required": True, "job": "Source system of record: a database, an application, files or a stream",
     "options": ["oracle", "db2", "sqlserver", "postgres", "mysql", "teradata", "sap-hana", "netezza", "mongodb", "dynamodb",
                 "cosmosdb", "salesforce", "sap-s4hana", "workday", "servicenow", "dynamics-365", "files", "kafka-topics",
                 "mainframe-db2-zos", "sqlite-local"]},
    {"slot": "source_pattern", "required": False, "job": "How the source data arrives",
     "options": ["database-batch", "database-cdc", "files", "saas-api", "event-stream"]},
    {"slot": "streaming", "required": False, "job": "Event streaming platform",
     "options": ["none", "kafka", "confluent-cloud", "msk", "kinesis", "event-hubs", "pubsub"]},
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
                 "airbyte", "spark-files", "auto-loader", "spark-structured-streaming", "api-extract", "aws-appflow",
                 "qlik-replicate", "informatica", "adef-local-extract"]},
    # --- hop 2: curate bronze -> silver -> gold in the lake
    {"slot": "lakehouse_compute", "required": True, "job": "Pipeline 2: engine that curates silver and gold",
     "options": ["aws-glue", "emr-spark", "databricks", "dataproc", "synapse-spark", "fabric-spark", "duckdb-local"]},
    {"slot": "transformation", "required": True, "job": "How silver and gold transformations are written",
     "options": ["spark-sql", "spark-sql-pipelines", "dbt-core", "dbt-cloud", "dataform", "duckdb-sql", "native-sql",
                 "matillion", "informatica"]},
    # --- hop 3: serve from the analytics layer
    {"slot": "compute_engine", "required": True, "job": "Pipeline 3: analytics engine that serves gold",
     "options": ["snowflake", "databricks", "bigquery", "redshift", "athena", "synapse", "fabric", "trino", "starburst",
                 "postgres", "duckdb-local"]},
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
     "options": ["power-bi", "tableau", "looker", "qlik", "quicksight", "thoughtspot", "sigma", "cognos",
                 "adef-console"]},
    {"slot": "ai_consumption", "required": False, "job": "Natural-language access to governed data",
     "options": ["platform-native", "snowflake-cortex-analyst", "databricks-genie", "bigquery-conversational-analytics",
                 "amazon-q", "fabric-copilot", "none"]},
    # --- other ways the product is consumed (each is optional; a run chooses its consumption patterns)
    {"slot": "data_api", "required": False, "job": "Serve governed data to applications over an API",
     "options": ["rest-openapi", "graphql", "none"]},
    {"slot": "data_sharing", "required": False, "job": "Share live data with other accounts or organisations",
     "options": ["snowflake-secure-share", "delta-sharing", "analytics-hub", "redshift-datashare", "onelake-shortcut",
                 "none"]},
    {"slot": "reverse_etl", "required": False, "job": "Sync curated data back into business applications",
     "options": ["hightouch", "census", "none"]},
    {"slot": "feature_store", "required": False, "job": "Features for machine learning",
     "options": ["databricks-feature-store", "snowflake-feature-store", "vertex-feature-store",
                 "sagemaker-feature-store", "azure-ml-feature-store", "feast", "none"]},
    {"slot": "vector_store", "required": False, "job": "Embeddings and retrieval for AI applications",
     "options": ["databricks-vector-search", "snowflake-cortex-search", "bigquery-vector-search", "opensearch",
                 "azure-ai-search", "pgvector", "none"]},
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
              "bi": "power-bi", "ai_consumption": "snowflake-cortex-analyst", "data_sharing": "snowflake-secure-share",
              "data_api": "rest-openapi", "reverse_etl": "hightouch", "feature_store": "snowflake-feature-store",
              "vector_store": "snowflake-cortex-search", "version_control": "github", "cicd": "github-actions", "iac": "terraform",
              "secrets": "aws-secrets-manager", "observability": "platform-native", "itsm": "servicenow"},
             standards=dict(MEDALLION, naming_case="upper_snake")),
    _profile("example-b", "DB2 → Azure ADLS Delta → Databricks",
             "IBM Db2 to ADLS with Azure Data Factory, Delta tables in Unity Catalog curated with Lakeflow "
             "declarative pipelines, served from Databricks SQL.",
             {**COMMON, "source_database": "db2", "cloud": "azure", "object_storage": "adls", "table_format": "delta",
              "lake_catalog": "unity-catalog", "ingestion": "azure-data-factory", "lakehouse_compute": "databricks",
              "transformation": "spark-sql-pipelines", "compute_engine": "databricks", "orchestration": "platform-workflows",
              "data_quality": "pipeline-expectations", "catalog_governance": "unity-catalog", "semantic_layer": "none",
              "bi": "power-bi", "ai_consumption": "databricks-genie", "data_sharing": "delta-sharing",
              "data_api": "rest-openapi", "feature_store": "databricks-feature-store",
              "vector_store": "databricks-vector-search", "version_control": "azure-repos", "cicd": "azure-pipelines", "iac": "terraform",
              "secrets": "azure-key-vault", "observability": "platform-native"}, secrets_prefix="kv/adef"),
    _profile("gcp-bigquery", "Oracle → GCS Iceberg → BigQuery",
             "Oracle to GCS with Datastream, Iceberg tables in the BigLake metastore curated on Dataproc, served "
             "from BigQuery as BigLake Iceberg tables.",
             {**COMMON, "source_database": "oracle", "cloud": "gcp", "object_storage": "gcs", "table_format": "iceberg",
              "lake_catalog": "biglake-metastore", "ingestion": "gcp-datastream", "lakehouse_compute": "dataproc",
              "transformation": "spark-sql", "compute_engine": "bigquery", "orchestration": "airflow",
              "data_quality": "great-expectations", "catalog_governance": "dataplex", "semantic_layer": "platform-native",
              "bi": "looker", "ai_consumption": "bigquery-conversational-analytics", "data_sharing": "analytics-hub",
              "data_api": "rest-openapi", "feature_store": "vertex-feature-store", "vector_store": "bigquery-vector-search",
              "version_control": "github", "cicd": "github-actions", "iac": "terraform",
              "secrets": "gcp-secret-manager", "observability": "platform-native"}, secrets_prefix="projects/adef/secrets"),
    _profile("azure-fabric", "DB2 → OneLake Delta → Microsoft Fabric",
             "IBM Db2 to OneLake with Data Factory, Delta tables curated with Fabric Spark, served from the Fabric "
             "Warehouse with Purview governance.",
             {**COMMON, "source_database": "db2", "cloud": "azure", "object_storage": "onelake", "table_format": "delta",
              "lake_catalog": "onelake", "ingestion": "azure-data-factory", "lakehouse_compute": "fabric-spark",
              "transformation": "spark-sql", "compute_engine": "fabric", "orchestration": "azure-data-factory",
              "data_quality": "great-expectations", "catalog_governance": "purview", "semantic_layer": "platform-native",
              "bi": "power-bi", "ai_consumption": "fabric-copilot", "data_sharing": "onelake-shortcut",
              "data_api": "graphql", "feature_store": "azure-ml-feature-store", "vector_store": "azure-ai-search",
              "version_control": "azure-repos", "cicd": "azure-pipelines", "iac": "bicep",
              "secrets": "azure-key-vault", "observability": "platform-native", "itsm": "servicenow"},
             secrets_prefix="kv/adef"),
    _profile("aws-redshift", "DB2 → AWS S3 Iceberg → Redshift",
             "IBM Db2 to S3 with Spark JDBC on EMR, Iceberg tables in the Glue catalog, served from Redshift "
             "through Spectrum external schemas.",
             {**COMMON, "source_database": "db2", "cloud": "aws", "object_storage": "s3", "table_format": "iceberg",
              "lake_catalog": "aws-glue-catalog", "ingestion": "spark-jdbc", "lakehouse_compute": "emr-spark",
              "transformation": "spark-sql", "compute_engine": "redshift", "orchestration": "airflow",
              "data_quality": "great-expectations", "catalog_governance": "datahub", "semantic_layer": "dbt-semantic-layer",
              "bi": "tableau", "ai_consumption": "amazon-q", "data_sharing": "redshift-datashare",
              "data_api": "rest-openapi", "reverse_etl": "census", "feature_store": "sagemaker-feature-store",
              "vector_store": "opensearch", "version_control": "gitlab", "cicd": "gitlab-ci", "iac": "terraform",
              "secrets": "aws-secrets-manager", "observability": "datadog"}),
    _profile("aws-databricks", "PostgreSQL (CDC) → AWS S3 Delta → Databricks",
             "Change data capture from PostgreSQL with AWS DMS, Delta tables in Unity Catalog curated with Lakeflow "
             "declarative pipelines, served from Databricks SQL with Delta Sharing, features and vector search.",
             {**COMMON, "source_database": "postgres", "source_pattern": "database-cdc", "cloud": "aws", "object_storage": "s3",
              "table_format": "delta", "lake_catalog": "unity-catalog", "ingestion": "aws-dms", "lakehouse_compute": "databricks",
              "transformation": "spark-sql-pipelines", "compute_engine": "databricks", "orchestration": "platform-workflows",
              "data_quality": "pipeline-expectations", "catalog_governance": "unity-catalog", "semantic_layer": "platform-native",
              "bi": "tableau", "ai_consumption": "databricks-genie", "data_sharing": "delta-sharing", "data_api": "rest-openapi",
              "feature_store": "databricks-feature-store", "vector_store": "databricks-vector-search",
              "version_control": "github", "cicd": "github-actions", "iac": "terraform", "secrets": "aws-secrets-manager",
              "observability": "platform-native"}),
    _profile("azure-snowflake", "SQL Server → Azure ADLS Iceberg → Snowflake",
             "SQL Server to ADLS with Azure Data Factory, Iceberg tables in an open (Polaris) catalog curated on Synapse "
             "Spark, served zero-copy from Snowflake on Azure with secure shares and Cortex Analyst.",
             {**COMMON, "source_database": "sqlserver", "source_pattern": "database-batch", "cloud": "azure",
              "object_storage": "adls", "table_format": "iceberg", "lake_catalog": "polaris", "ingestion": "azure-data-factory",
              "lakehouse_compute": "synapse-spark", "transformation": "spark-sql", "compute_engine": "snowflake",
              "orchestration": "azure-data-factory", "data_quality": "great-expectations", "catalog_governance": "purview",
              "semantic_layer": "platform-native", "bi": "power-bi", "ai_consumption": "snowflake-cortex-analyst",
              "data_sharing": "snowflake-secure-share", "data_api": "rest-openapi", "reverse_etl": "hightouch",
              "feature_store": "snowflake-feature-store", "vector_store": "snowflake-cortex-search",
              "version_control": "azure-repos", "cicd": "azure-pipelines", "iac": "terraform", "secrets": "azure-key-vault",
              "observability": "platform-native", "itsm": "servicenow"}, secrets_prefix="kv/adef",
             standards=dict(MEDALLION, naming_case="upper_snake")),
    _profile("azure-synapse", "SQL Server → Azure ADLS Delta → Synapse",
             "SQL Server to ADLS with Azure Data Factory, Delta tables curated on Synapse Spark, served from Synapse "
             "serverless SQL with Purview governance and Power BI.",
             {**COMMON, "source_database": "sqlserver", "source_pattern": "database-batch", "cloud": "azure",
              "object_storage": "adls", "table_format": "delta", "lake_catalog": "hive-metastore",
              "ingestion": "azure-data-factory", "lakehouse_compute": "synapse-spark", "transformation": "spark-sql",
              "compute_engine": "synapse", "orchestration": "azure-data-factory", "data_quality": "great-expectations",
              "catalog_governance": "purview", "semantic_layer": "platform-native", "bi": "power-bi",
              "data_api": "rest-openapi", "feature_store": "azure-ml-feature-store", "vector_store": "azure-ai-search",
              "version_control": "azure-repos", "cicd": "azure-pipelines", "iac": "bicep", "secrets": "azure-key-vault",
              "observability": "platform-native", "itsm": "servicenow"}, secrets_prefix="kv/adef"),
    _profile("saas-snowflake", "Salesforce (API) → AWS S3 Iceberg → Snowflake",
             "Salesforce objects landed by Fivetran, Iceberg tables in the Glue catalog curated with Glue Spark, served "
             "zero-copy from Snowflake and synced back to business applications with reverse ETL.",
             {**COMMON, "source_database": "salesforce", "source_pattern": "saas-api", "cloud": "aws", "object_storage": "s3",
              "table_format": "iceberg", "lake_catalog": "aws-glue-catalog", "ingestion": "fivetran",
              "lakehouse_compute": "aws-glue", "transformation": "spark-sql", "compute_engine": "snowflake",
              "orchestration": "airflow", "data_quality": "great-expectations", "catalog_governance": "atlan",
              "semantic_layer": "platform-native", "bi": "sigma", "ai_consumption": "snowflake-cortex-analyst",
              "data_sharing": "snowflake-secure-share", "reverse_etl": "census", "version_control": "github",
              "cicd": "github-actions", "iac": "terraform", "secrets": "aws-secrets-manager", "observability": "monte-carlo"},
             standards=dict(MEDALLION, naming_case="upper_snake")),
    _profile("gcp-databricks-streaming", "Kafka events → GCS Delta → Databricks",
             "Events from Confluent Cloud read with Spark Structured Streaming, Delta tables in Unity Catalog on GCS, "
             "curated with Lakeflow declarative pipelines and served from Databricks SQL.",
             {**COMMON, "source_database": "kafka-topics", "source_pattern": "event-stream", "streaming": "confluent-cloud",
              "cloud": "gcp", "object_storage": "gcs", "table_format": "delta", "lake_catalog": "unity-catalog",
              "ingestion": "spark-structured-streaming", "lakehouse_compute": "databricks",
              "transformation": "spark-sql-pipelines", "compute_engine": "databricks", "orchestration": "platform-workflows",
              "data_quality": "pipeline-expectations", "catalog_governance": "unity-catalog", "semantic_layer": "platform-native",
              "bi": "looker", "ai_consumption": "databricks-genie", "data_sharing": "delta-sharing",
              "feature_store": "databricks-feature-store", "vector_store": "databricks-vector-search",
              "version_control": "github", "cicd": "github-actions", "iac": "terraform", "secrets": "gcp-secret-manager",
              "observability": "datadog"}, secrets_prefix="projects/adef/secrets"),
    _profile("files-athena", "Files (CSV, JSON, Parquet) → AWS S3 Iceberg → Athena",
             "Files dropped by partners and applications, loaded once each into Iceberg tables in the Glue catalog, "
             "curated with Glue Spark and queried in place from Athena with QuickSight.",
             {**COMMON, "source_database": "files", "source_pattern": "files", "cloud": "aws", "object_storage": "s3",
              "table_format": "iceberg", "lake_catalog": "aws-glue-catalog", "ingestion": "spark-files",
              "lakehouse_compute": "aws-glue", "transformation": "spark-sql", "compute_engine": "athena",
              "orchestration": "airflow", "data_quality": "great-expectations", "catalog_governance": "datahub",
              "semantic_layer": "none", "bi": "quicksight", "ai_consumption": "amazon-q", "data_api": "rest-openapi",
              "feature_store": "sagemaker-feature-store", "vector_store": "opensearch", "version_control": "github",
              "cicd": "github-actions", "iac": "cloudformation", "secrets": "aws-secrets-manager",
              "observability": "platform-native"}),
    _profile("teradata-bigquery", "Teradata → GCS Iceberg → BigQuery (warehouse migration)",
             "Teradata tables extracted with Spark JDBC on Dataproc, Iceberg tables in the BigLake metastore, served "
             "from BigQuery with Analytics Hub sharing and Looker.",
             {**COMMON, "source_database": "teradata", "source_pattern": "database-batch", "cloud": "gcp",
              "object_storage": "gcs", "table_format": "iceberg", "lake_catalog": "biglake-metastore", "ingestion": "spark-jdbc",
              "lakehouse_compute": "dataproc", "transformation": "spark-sql", "compute_engine": "bigquery",
              "orchestration": "airflow", "data_quality": "great-expectations", "catalog_governance": "dataplex",
              "semantic_layer": "platform-native", "bi": "looker", "ai_consumption": "bigquery-conversational-analytics",
              "data_sharing": "analytics-hub", "data_api": "rest-openapi", "feature_store": "vertex-feature-store",
              "vector_store": "bigquery-vector-search", "version_control": "gitlab", "cicd": "gitlab-ci", "iac": "terraform",
              "secrets": "gcp-secret-manager", "observability": "platform-native"}, secrets_prefix="projects/adef/secrets"),
    _profile("local-lakehouse", "Local lakehouse (runs on this machine)",
             "Synthetic source database (SQLite, or a real Oracle/Db2 container) to Delta tables on local disk, "
             "curated with DuckDB and served from a DuckDB analytics database. Every pipeline really executes.",
             {**COMMON, "source_database": "sqlite-local", "cloud": "local", "object_storage": "local-filesystem",
              "table_format": "delta", "lake_catalog": "sqlite-catalog", "ingestion": "adef-local-extract",
              "lakehouse_compute": "duckdb-local", "transformation": "duckdb-sql", "compute_engine": "duckdb-local",
              "orchestration": "adef-runner", "data_quality": "native-metrics", "catalog_governance": "adef-local-catalog",
              "semantic_layer": "none", "bi": "adef-console", "data_api": "rest-openapi", "feature_store": "feast",
              "vector_store": "pgvector", "version_control": "github", "cicd": "github-actions",
              "iac": "none", "secrets": "adef-vault", "observability": "adef-console", "itsm": "none"},
             secrets_prefix="adef-vault", executable=True),
]

# analytics engine -> SQL dialect used by the DDL exporter and serving-layer code
DIALECT_FOR_ENGINE = {"snowflake": "snowflake", "databricks": "databricks", "bigquery": "bigquery",
                      "redshift": "redshift", "athena": "trino", "trino": "trino", "starburst": "trino",
                      "synapse": "tsql", "fabric": "tsql", "postgres": "postgres", "duckdb-local": "duckdb"}

# Which tools the built-in generators know how to target.
SUPPORTED_BY_GENERATOR = {
    "source_database": {"oracle", "db2", "sqlserver", "postgres", "mysql", "teradata", "sap-hana", "netezza",
                        "mainframe-db2-zos", "mongodb", "dynamodb", "cosmosdb", "salesforce", "sap-s4hana", "workday",
                        "servicenow", "dynamics-365", "files", "kafka-topics", "sqlite-local"},
    "source_pattern": {"database-batch", "database-cdc", "files", "saas-api", "event-stream"},
    "streaming": {"kafka", "confluent-cloud", "msk", "kinesis", "event-hubs", "pubsub"},
    "ingestion": {"spark-jdbc", "aws-dms", "azure-data-factory", "gcp-datastream", "debezium-kafka", "fivetran", "airbyte",
                  "spark-files", "auto-loader", "spark-structured-streaming", "api-extract", "adef-local-extract"},
    "ai_consumption": {"platform-native", "snowflake-cortex-analyst", "databricks-genie",
                       "bigquery-conversational-analytics", "amazon-q", "fabric-copilot"},
    "data_api": {"rest-openapi", "graphql"},
    "data_sharing": {"snowflake-secure-share", "delta-sharing", "analytics-hub", "redshift-datashare", "onelake-shortcut"},
    "reverse_etl": {"hightouch", "census"},
    "feature_store": {"databricks-feature-store", "snowflake-feature-store", "vertex-feature-store",
                      "sagemaker-feature-store", "azure-ml-feature-store", "feast"},
    "vector_store": {"databricks-vector-search", "snowflake-cortex-search", "bigquery-vector-search", "opensearch",
                     "azure-ai-search", "pgvector"},
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
            "duckdb-local": "local", "msk": "aws", "kinesis": "aws", "event-hubs": "azure", "pubsub": "gcp",
            "aws-appflow": "aws"}

# analytics engines that exist on one cloud only (Snowflake, Databricks, Trino and Postgres run on any)
ENGINE_CLOUDS = {"redshift": {"aws"}, "athena": {"aws"}, "bigquery": {"gcp"}, "synapse": {"azure"}, "fabric": {"azure"},
                 "duckdb-local": {"local"}}

# how each kind of source arrives, and which ingestion tools fit it
PATTERN_LABELS = {"database-batch": "database, batch extract", "database-cdc": "database, change data capture",
                  "files": "files", "saas-api": "application API", "event-stream": "event stream"}
PATTERN_TOOLS = {
    "database-batch": {"spark-jdbc", "azure-data-factory", "fivetran", "airbyte", "informatica", "adef-local-extract"},
    "database-cdc": {"aws-dms", "gcp-datastream", "debezium-kafka", "azure-data-factory", "fivetran", "airbyte",
                     "qlik-replicate"},
    "files": {"spark-files", "auto-loader", "azure-data-factory"},
    "saas-api": {"fivetran", "airbyte", "api-extract", "aws-appflow", "azure-data-factory"},
    "event-stream": {"spark-structured-streaming", "debezium-kafka"},
}
SOURCE_PATTERNS = {"files": {"files"}, "kafka-topics": {"event-stream"},
                   **{s: {"saas-api"} for s in ("salesforce", "sap-s4hana", "workday", "servicenow", "dynamics-365")}}


def source_pattern(profile: dict) -> str:
    """The source pattern of a stack: what it declares, or what its source and ingestion tool imply."""
    declared = tool(profile, "source_pattern")
    if declared in PATTERN_LABELS:
        return declared
    src, ing = tool(profile, "source_database"), tool(profile, "ingestion")
    if src in SOURCE_PATTERNS:
        return next(iter(SOURCE_PATTERNS[src]))
    return "database-cdc" if ing in ("aws-dms", "gcp-datastream", "debezium-kafka", "qlik-replicate") else "database-batch"

# analytics engine -> table formats it reads in place (zero-copy); otherwise gold is copied in
ZERO_COPY_FORMATS = {"snowflake": {"iceberg"}, "databricks": {"delta", "iceberg"}, "bigquery": {"iceberg", "delta"},
                     "redshift": {"iceberg", "hudi", "delta"}, "athena": {"iceberg", "hudi", "delta"},
                     "trino": {"iceberg", "delta", "hudi"}, "starburst": {"iceberg", "delta", "hudi"},
                     "synapse": {"delta"}, "fabric": {"delta", "iceberg"},
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
    ("ingestion", "auto-loader", "lakehouse_compute", {"databricks"}, "Auto Loader is a Databricks feature"),
    ("ai_consumption", "snowflake-cortex-analyst", "compute_engine", {"snowflake"}, "Cortex Analyst needs Snowflake"),
    ("ai_consumption", "databricks-genie", "compute_engine", {"databricks"}, "Genie needs Databricks"),
    ("ai_consumption", "bigquery-conversational-analytics", "compute_engine", {"bigquery"}, "It runs in BigQuery"),
    ("ai_consumption", "fabric-copilot", "compute_engine", {"fabric"}, "Copilot in Fabric needs Fabric"),
    ("ai_consumption", "amazon-q", "cloud", {"aws"}, "Amazon Q runs on AWS"),
    ("data_sharing", "snowflake-secure-share", "compute_engine", {"snowflake"}, "Secure shares are a Snowflake feature"),
    ("data_sharing", "delta-sharing", "table_format", {"delta"}, "Delta Sharing shares Delta tables"),
    ("data_sharing", "analytics-hub", "compute_engine", {"bigquery"}, "Analytics Hub shares BigQuery datasets"),
    ("data_sharing", "redshift-datashare", "compute_engine", {"redshift"}, "Datashares are a Redshift feature"),
    ("data_sharing", "onelake-shortcut", "compute_engine", {"fabric"}, "Shortcuts are a OneLake feature"),
    ("feature_store", "databricks-feature-store", "lakehouse_compute", {"databricks"}, "It is part of Databricks"),
    ("feature_store", "snowflake-feature-store", "compute_engine", {"snowflake"}, "It is part of Snowflake"),
    ("feature_store", "vertex-feature-store", "cloud", {"gcp"}, "Vertex AI runs on Google Cloud"),
    ("feature_store", "sagemaker-feature-store", "cloud", {"aws"}, "SageMaker runs on AWS"),
    ("feature_store", "azure-ml-feature-store", "cloud", {"azure"}, "Azure Machine Learning runs on Azure"),
    ("vector_store", "databricks-vector-search", "lakehouse_compute", {"databricks"}, "It is part of Databricks"),
    ("vector_store", "snowflake-cortex-search", "compute_engine", {"snowflake"}, "Cortex Search needs Snowflake"),
    ("vector_store", "bigquery-vector-search", "compute_engine", {"bigquery"}, "It runs in BigQuery"),
    ("vector_store", "azure-ai-search", "cloud", {"azure"}, "Azure AI Search runs on Azure"),
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
    for sl in ("object_storage", "lake_catalog", "ingestion", "lakehouse_compute", "streaming"):
        need = CLOUD_OF.get(tool(profile, sl))
        if need and cloud not in ("none", need):
            blocking.append(f"Incompatible: {sl}={tool(profile, sl)} runs on {need}, but cloud={cloud}")
    eng_clouds = ENGINE_CLOUDS.get(tool(profile, "compute_engine"))
    if eng_clouds and cloud not in eng_clouds:
        blocking.append(f"Incompatible: compute_engine={tool(profile, 'compute_engine')} runs on "
                        f"{' or '.join(sorted(eng_clouds))}, but cloud={cloud}")
    pattern, src, ing = source_pattern(profile), tool(profile, "source_database"), tool(profile, "ingestion")
    if src in SOURCE_PATTERNS and pattern not in SOURCE_PATTERNS[src]:
        blocking.append(f"Incompatible: source {src} arrives as {' or '.join(sorted(SOURCE_PATTERNS[src]))}, "
                        f"not as {pattern}")
    if pattern in ("files", "saas-api", "event-stream") and src not in SOURCE_PATTERNS and src != "none":
        if not (pattern == "event-stream" and tool(profile, "streaming") not in ("none", "")):
            blocking.append(f"Incompatible: source_pattern={pattern} does not fit the source {src}")
    if ing not in PATTERN_TOOLS[pattern]:
        blocking.append(f"Incompatible: ingestion={ing} does not handle the source pattern `{pattern}` "
                        f"(use one of {', '.join(sorted(PATTERN_TOOLS[pattern]))})")
    if pattern == "event-stream" and tool(profile, "streaming") in ("none", ""):
        blocking.append("An event-stream source needs the `streaming` slot bound to a streaming platform")
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
        {"pipeline": 1, "name": "Ingest", "from": f"{t('source_database')} ({PATTERN_LABELS[source_pattern(profile)]})",
         "to": f"bronze ({t('table_format')} on {t('object_storage')}, {t('lake_catalog')})", "tool": t("ingestion")},
        {"pipeline": 2, "name": "Curate", "from": "bronze", "to": f"silver and gold ({t('table_format')})",
         "tool": f"{t('transformation')} on {t('lakehouse_compute')}"},
        {"pipeline": 3, "name": "Publish", "from": "gold", "to": f"{t('compute_engine')} analytics layer",
         "tool": "zero-copy external tables" if zero else "copy into the analytics engine"},
    ]


# ----------------------------------------------------------------------------- compose a stack from a few choices
CLOUD_DEFAULTS = {
    "aws": {"object_storage": "s3", "lake_catalog": "aws-glue-catalog", "lakehouse_compute": "aws-glue",
            "streaming": "msk", "orchestration": "airflow", "secrets": "aws-secrets-manager", "version_control": "github",
            "cicd": "github-actions", "iac": "terraform", "catalog_governance": "datahub", "bi": "quicksight",
            "cdc": "aws-dms", "feature_store": "sagemaker-feature-store", "vector_store": "opensearch",
            "ai_consumption": "amazon-q"},
    "azure": {"object_storage": "adls", "lake_catalog": "hive-metastore", "lakehouse_compute": "synapse-spark",
              "streaming": "event-hubs", "orchestration": "azure-data-factory", "secrets": "azure-key-vault",
              "version_control": "azure-repos", "cicd": "azure-pipelines", "iac": "bicep", "catalog_governance": "purview",
              "bi": "power-bi", "cdc": "azure-data-factory", "feature_store": "azure-ml-feature-store",
              "vector_store": "azure-ai-search", "ai_consumption": "none"},
    "gcp": {"object_storage": "gcs", "lake_catalog": "biglake-metastore", "lakehouse_compute": "dataproc",
            "streaming": "pubsub", "orchestration": "airflow", "secrets": "gcp-secret-manager", "version_control": "github",
            "cicd": "github-actions", "iac": "terraform", "catalog_governance": "dataplex", "bi": "looker",
            "cdc": "gcp-datastream", "feature_store": "vertex-feature-store", "vector_store": "pgvector",
            "ai_consumption": "none"},
}
ENGINE_DEFAULTS = {
    "snowflake": {"table_format": "iceberg", "semantic_layer": "platform-native", "ai_consumption": "snowflake-cortex-analyst",
                  "data_sharing": "snowflake-secure-share", "feature_store": "snowflake-feature-store",
                  "vector_store": "snowflake-cortex-search"},
    "databricks": {"table_format": "delta", "lake_catalog": "unity-catalog", "lakehouse_compute": "databricks",
                   "transformation": "spark-sql-pipelines", "orchestration": "platform-workflows",
                   "data_quality": "pipeline-expectations", "catalog_governance": "unity-catalog",
                   "semantic_layer": "platform-native", "ai_consumption": "databricks-genie", "data_sharing": "delta-sharing",
                   "feature_store": "databricks-feature-store", "vector_store": "databricks-vector-search"},
    "bigquery": {"table_format": "iceberg", "semantic_layer": "platform-native",
                 "ai_consumption": "bigquery-conversational-analytics", "data_sharing": "analytics-hub",
                 "vector_store": "bigquery-vector-search"},
    "redshift": {"table_format": "iceberg", "data_sharing": "redshift-datashare"},
    "athena": {"table_format": "iceberg"},
    "synapse": {"table_format": "delta"},
    "fabric": {"table_format": "delta", "object_storage": "onelake", "lake_catalog": "onelake",
               "lakehouse_compute": "fabric-spark", "semantic_layer": "platform-native", "ai_consumption": "fabric-copilot",
               "data_sharing": "onelake-shortcut"},
    "trino": {"table_format": "iceberg"}, "starburst": {"table_format": "iceberg"}, "postgres": {"table_format": "iceberg"},
}
ENGINE_LABELS = {"snowflake": "Snowflake", "databricks": "Databricks", "bigquery": "BigQuery", "redshift": "Redshift",
                 "athena": "Athena", "synapse": "Synapse", "fabric": "Microsoft Fabric", "trino": "Trino",
                 "starburst": "Starburst", "postgres": "PostgreSQL"}
CLOUD_LABELS = {"aws": "AWS", "azure": "Azure", "gcp": "Google Cloud"}
STORAGE_LABELS = {"s3": "S3", "adls": "ADLS", "gcs": "GCS", "onelake": "OneLake"}


def compose_options() -> dict:
    """What the stack composer offers: clouds, engines valid on each cloud, sources and how each can arrive."""
    engines = {c: [e for e in ENGINE_LABELS if c in ENGINE_CLOUDS.get(e, {c})] for c in CLOUD_LABELS}
    src = next(s for s in SLOTS if s["slot"] == "source_database")["options"]
    sources = {s: sorted(SOURCE_PATTERNS.get(s, {"database-batch", "database-cdc"})) for s in src if s != "sqlite-local"}
    return {"clouds": CLOUD_LABELS, "engines": engines, "engine_labels": ENGINE_LABELS, "sources": sources,
            "patterns": PATTERN_LABELS, "table_formats": ["iceberg", "delta"],
            "bi": next(s for s in SLOTS if s["slot"] == "bi")["options"][:-1]}


def compose(cloud: str, engine: str, source: str, pattern: str | None = None, table_format: str | None = None,
            bi: str | None = None) -> dict:
    """Build a complete, valid Stack Profile from a cloud, an analytics engine and a source.

    Every other slot is filled with that cloud's and that engine's usual choice, so a client's stack
    that is not one of the presets is a few clicks away. The result is a starting point: every slot can
    still be changed, and `validate` says what does not fit.
    """
    if cloud not in CLOUD_DEFAULTS:
        raise ValueError(f"Unknown cloud `{cloud}`")
    if engine not in ENGINE_DEFAULTS:
        raise ValueError(f"Unknown analytics engine `{engine}`")
    if cloud not in ENGINE_CLOUDS.get(engine, {cloud}):
        raise ValueError(f"{ENGINE_LABELS[engine]} runs on {' or '.join(sorted(ENGINE_CLOUDS[engine]))}, not on {cloud}")
    opts = compose_options()
    if source not in opts["sources"]:
        raise ValueError(f"Unknown source `{source}`")
    pattern = pattern or opts["sources"][source][0]
    if pattern not in opts["sources"][source]:
        raise ValueError(f"A {source} source arrives as {' or '.join(opts['sources'][source])}, not as {pattern}")
    c, e = CLOUD_DEFAULTS[cloud], ENGINE_DEFAULTS[engine]
    s = {**COMMON, "cloud": cloud, "source_database": source, "source_pattern": pattern, "compute_engine": engine,
         "transformation": "spark-sql", "data_quality": "great-expectations", "semantic_layer": "none",
         "data_api": "rest-openapi", "data_sharing": "none", "reverse_etl": "none", "observability": "platform-native",
         **{k: v for k, v in c.items() if k != "cdc"}, **e}
    if table_format:
        s["table_format"] = table_format
    if bi:
        s["bi"] = bi
    if engine == "snowflake" and cloud != "aws":
        s["lake_catalog"] = "polaris"                   # an open Iceberg catalog Snowflake reads on any cloud
    if s.get("data_sharing") == "delta-sharing" and s["table_format"] != "delta":
        s["data_sharing"] = "none"
    databricks = s["lakehouse_compute"] == "databricks"
    s["ingestion"] = {"database-batch": "azure-data-factory" if cloud == "azure" else "spark-jdbc",
                      "database-cdc": c["cdc"], "files": "auto-loader" if databricks else "spark-files",
                      "saas-api": "fivetran", "event-stream": "spark-structured-streaming"}[pattern]
    if pattern != "event-stream":
        s["streaming"] = "none"
    pid = f"{cloud}-{engine}-{source}".replace("_", "-")
    label = (f"{source.replace('-', ' ').title()} → {CLOUD_LABELS[cloud]} {STORAGE_LABELS[s['object_storage']]} "
             f"{s['table_format'].title()} → {ENGINE_LABELS[engine]}")
    prefix = {"aws": "secrets/adef", "azure": "kv/adef", "gcp": "projects/adef/secrets"}[cloud]
    prof = _profile(pid, label, f"Composed stack: {source} ({PATTERN_LABELS[pattern]}) into {s['table_format']} tables on "
                                f"{STORAGE_LABELS[s['object_storage']]}, served from {ENGINE_LABELS[engine]}. "
                                "Review each slot before first use.", s, secrets_prefix=prefix)
    prof["composed"] = True
    return prof
