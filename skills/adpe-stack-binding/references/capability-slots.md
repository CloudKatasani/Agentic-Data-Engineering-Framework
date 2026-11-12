# Capability Slots

Agents speak in slots. The Stack Profile binds each slot to a tool. Tool names in the
last column are illustrations only; the profile decides.

| Slot | Required | Job to be done | Used by stage | Illustrative tools |
|---|---|---|---|---|
| `cloud` | yes | Hosting, identity, networking | all | AWS, Azure, GCP, on-premises |
| `object_storage` | yes | Landing and raw file storage | build, ops | S3, ADLS, GCS |
| `table_format` | no | Open table format for lakehouse tables | design, build | Iceberg, Delta, Hudi |
| `compute_engine` | yes | Warehouse or lakehouse engine that stores and queries data | design to consumption | Snowflake, Databricks, BigQuery, Redshift, Synapse, Fabric |
| `ingestion` | yes | Batch, CDC, and streaming extraction | design, build | Fivetran, Informatica, ADF, Glue, Kafka Connect, native loaders |
| `transformation` | yes | Modelled transformations | build, test | dbt, Spark, native SQL pipelines, Informatica, Matillion |
| `orchestration` | yes | Scheduling and dependencies | build, release, ops | Airflow, native tasks, ADF, Control-M, Dagster |
| `data_quality` | yes | Rule execution and scoring | test, ops | dbt tests, Great Expectations, Soda, native metrics |
| `catalog_governance` | yes | Glossary, ownership, classification, policies | all | Collibra, Purview, Unity Catalog, Alation, native catalog |
| `lineage` | no | Technical and business lineage | design, ops, consumption | OpenLineage, catalog-native |
| `virtualization` | no | Federated or virtual access layer | design, consumption | Denodo, Trino, Starburst |
| `semantic_layer` | no | Governed metrics and business definitions | consumption | Native semantic views, dbt semantic layer, AtScale |
| `bi` | yes | Reports and dashboards | consumption | Power BI, Tableau, Looker, Cognos |
| `ai_consumption` | no | Natural-language or agent access to governed data | consumption | Platform-native assistants and agents |
| `version_control` | yes | Source control and review | build onward | GitHub, GitLab, Azure Repos, Bitbucket |
| `cicd` | yes | Build, test, and deploy automation | build, release | GitHub Actions, GitLab CI, Azure Pipelines, Jenkins |
| `iac` | no | Infrastructure as code | release | Terraform, native IaC |
| `secrets` | yes | Credential storage and retrieval by reference | all | Cloud secret managers, Vault |
| `observability` | yes | Pipeline, data, and cost telemetry | ops | Platform telemetry, Datadog, Monte Carlo, native account usage |
| `itsm` | no | Tickets, incidents, change records | orchestrator, release, ops | ServiceNow, Jira |
| `approval_channel` | yes | Where humans grant approvals | all | Chat workflow, ticket workflow, pull-request review |

## Slot rules

- `yes` slots must be bound to a tool or the run cannot pass G0.
- A slot may be bound to `none` only if it is not marked required, with a reason.
- One tool can fill several slots (for example a platform's native tasks filling
  `orchestration`). Bind each slot explicitly anyway.
- A new slot needs Data Architect approval and an update to this file. Do not create
  ad hoc slots in a profile.
