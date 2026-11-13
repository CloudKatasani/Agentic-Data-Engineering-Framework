# Capability Slots

Agents speak in slots. The Stack Profile binds each slot to a tool. Tool names in the
last column are illustrations only; the profile decides.

The first nine slots describe the three pipelines: `source_database` → Pipeline 1 (`ingestion`) → bronze in `object_storage` as `table_format`, registered in `lake_catalog` → Pipeline 2 (`transformation` on `lakehouse_compute`) → silver and gold → Pipeline 3 → `compute_engine`, the analytics layer.

| Slot | Required | Job to be done | Used by stage | Illustrative tools |
|---|---|---|---|---|
| `source_database` | yes | Operational source database (system of record) | mapping, build, test | oracle, db2, sqlserver, postgres, mysql, teradata, sap-hana, sqlite-local |
| `cloud` | yes | Hyperscaler hosting the lake, identity, networking | all | aws, azure, gcp, local |
| `object_storage` | yes | Lake storage for bronze, silver and gold | build, ops | s3, adls, gcs, onelake, local-filesystem |
| `table_format` | yes | Open table format for every lake layer | design, build | iceberg, delta, hudi |
| `lake_catalog` | yes | Table catalog for the open table format | design, build, consumption | aws-glue-catalog, unity-catalog, polaris, biglake-metastore, hive-metastore, onelake, sqlite-catalog |
| `ingestion` | yes | Pipeline 1: extract from the source database into bronze | design, build | spark-jdbc, aws-dms, azure-data-factory, gcp-datastream, debezium-kafka, fivetran, airbyte, informatica, adef-local-extract |
| `lakehouse_compute` | yes | Pipeline 2: engine that curates silver and gold | design, build, test | aws-glue, emr-spark, databricks, dataproc, synapse-spark, fabric-spark, duckdb-local |
| `transformation` | yes | How silver and gold transformations are written | build, test | spark-sql, spark-sql-pipelines, dbt-core, dbt-cloud, dataform, duckdb-sql, native-sql, matillion, informatica |
| `compute_engine` | yes | Pipeline 3: analytics engine that serves gold | design to consumption | snowflake, databricks, bigquery, redshift, synapse, fabric, postgres, duckdb-local |
| `orchestration` | yes | Schedules and chains the three pipelines | see stage skills | airflow, platform-workflows, azure-data-factory, snowflake-tasks, dagster, control-m, adef-runner |
| `data_quality` | yes | Rule execution and scoring | see stage skills | great-expectations, dbt-tests, soda, pipeline-expectations, dataform-assertions, native-metrics |
| `catalog_governance` | yes | Glossary, ownership, classification, policies | see stage skills | collibra, purview, unity-catalog, alation, datahub, atlan, dataplex, snowflake-horizon, adef-local-catalog |
| `lineage` | no | Technical and business lineage | see stage skills | catalog-native, openlineage |
| `virtualization` | no | Federated access layer | see stage skills | denodo, trino, starburst |
| `semantic_layer` | no | Governed metrics | see stage skills | platform-native, dbt-semantic-layer, atscale, cube |
| `bi` | yes | Reports and dashboards | see stage skills | power-bi, tableau, looker, qlik, cognos, adef-console |
| `ai_consumption` | no | Natural-language access to governed data | see stage skills | platform-native |
| `version_control` | yes | Source control and review | see stage skills | github, gitlab, azure-repos, bitbucket |
| `cicd` | yes | Build, test, deploy automation | see stage skills | github-actions, gitlab-ci, azure-pipelines, jenkins |
| `iac` | no | Infrastructure as code | see stage skills | terraform, bicep, cloudformation |
| `secrets` | yes | Credential storage by reference | see stage skills | aws-secrets-manager, azure-key-vault, gcp-secret-manager, hashicorp-vault, adef-vault |
| `observability` | yes | Pipeline, data and cost telemetry | see stage skills | platform-native, datadog, monte-carlo, grafana, adef-console |
| `itsm` | no | Tickets, incidents, change records | see stage skills | jira, servicenow |
| `approval_channel` | yes | Where humans grant approvals | see stage skills | adef-console, pull-request-and-ticket, chat-workflow |

## Slot rules

- `yes` slots must be bound to a tool or the run cannot pass G0.
- A slot may be bound to `none` only if it is not marked required, with a reason.
- One tool can fill several slots (for example a platform's native tasks filling
  `orchestration`). Bind each slot explicitly anyway.
- A new slot needs Data Architect approval and an update to this file. Do not create
  ad hoc slots in a profile.
