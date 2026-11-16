# Capability Slots

Agents speak in slots. The Stack Profile binds each slot to a tool. Tool names in the
last column are illustrations only; the profile decides.

The first slots describe the three pipelines: `source_database` → Pipeline 1 (`ingestion`) → bronze in `object_storage` as `table_format`, registered in `lake_catalog` → Pipeline 2 (`transformation` on `lakehouse_compute`) → silver and gold → Pipeline 3 → `compute_engine`, the analytics layer.

| Slot | Required | Job to be done | Used by stage | Illustrative tools |
|---|---|---|---|---|
| `source_database` | yes | Source system of record: a database, an application, files or a stream | mapping, build, test | oracle, db2, sqlserver, postgres, mysql, teradata, sap-hana, netezza, mainframe-db2-zos, mongodb, dynamodb, cosmosdb, salesforce, sap-s4hana, workday, servicenow, dynamics-365, files, kafka-topics |
| `source_pattern` | no | How the source data arrives (see Source patterns below) | design, build, test | database-batch, database-cdc, files, saas-api, event-stream |
| `streaming` | no | Event streaming platform; required for an event-stream source | design, build, ops | kafka, confluent-cloud, msk, kinesis, event-hubs, pubsub |
| `cloud` | yes | Hyperscaler hosting the lake, identity, networking | all | aws, azure, gcp, local |
| `object_storage` | yes | Lake storage for bronze, silver and gold | build, ops | s3, adls, gcs, onelake, local-filesystem |
| `table_format` | yes | Open table format for every lake layer | design, build | iceberg, delta, hudi |
| `lake_catalog` | yes | Table catalog for the open table format | design, build, consumption | aws-glue-catalog, unity-catalog, polaris, biglake-metastore, hive-metastore, onelake, sqlite-catalog |
| `ingestion` | yes | Pipeline 1: bring the source into bronze | design, build | spark-jdbc, aws-dms, azure-data-factory, gcp-datastream, debezium-kafka, fivetran, airbyte, spark-files, auto-loader, spark-structured-streaming, api-extract |
| `lakehouse_compute` | yes | Pipeline 2: engine that curates silver and gold | design, build, test | aws-glue, emr-spark, databricks, dataproc, synapse-spark, fabric-spark, duckdb-local |
| `transformation` | yes | How silver and gold transformations are written | build, test | spark-sql, spark-sql-pipelines, dbt-core, dbt-cloud, dataform, duckdb-sql, native-sql, matillion, informatica |
| `compute_engine` | yes | Pipeline 3: analytics engine that serves gold | design to consumption | snowflake, databricks, bigquery, redshift, athena, synapse, fabric, trino, starburst, postgres |
| `orchestration` | yes | Schedules and chains the three pipelines | see stage skills | airflow, platform-workflows, azure-data-factory, snowflake-tasks, dagster, control-m, adef-runner |
| `data_quality` | yes | Rule execution and scoring | see stage skills | great-expectations, dbt-tests, soda, pipeline-expectations, dataform-assertions, native-metrics |
| `catalog_governance` | yes | Glossary, ownership, classification, policies | see stage skills | collibra, purview, unity-catalog, alation, datahub, atlan, dataplex, snowflake-horizon, adef-local-catalog |
| `lineage` | no | Technical and business lineage | see stage skills | catalog-native, openlineage |
| `virtualization` | no | Federated access layer | see stage skills | denodo, trino, starburst |
| `semantic_layer` | no | Governed metrics | see stage skills | platform-native, dbt-semantic-layer, atscale, cube |
| `bi` | yes | Reports and dashboards | consumption | power-bi, tableau, looker, qlik, quicksight, thoughtspot, sigma, cognos, adef-console |
| `ai_consumption` | no | Natural-language access to governed data | consumption | snowflake-cortex-analyst, databricks-genie, bigquery-conversational-analytics, amazon-q, fabric-copilot, platform-native |
| `data_api` | no | Serve governed data to applications over an API | consumption | rest-openapi, graphql |
| `data_sharing` | no | Share live data with other accounts or organisations | consumption | snowflake-secure-share, delta-sharing, analytics-hub, redshift-datashare, onelake-shortcut |
| `reverse_etl` | no | Sync curated data back into business applications | consumption | hightouch, census |
| `feature_store` | no | Features for machine learning | consumption | databricks-feature-store, snowflake-feature-store, vertex-feature-store, sagemaker-feature-store, azure-ml-feature-store, feast |
| `vector_store` | no | Embeddings and retrieval for AI applications | consumption | databricks-vector-search, snowflake-cortex-search, bigquery-vector-search, opensearch, azure-ai-search, pgvector |
| `version_control` | yes | Source control and review | see stage skills | github, gitlab, azure-repos, bitbucket |
| `cicd` | yes | Build, test, deploy automation | see stage skills | github-actions, gitlab-ci, azure-pipelines, jenkins |
| `iac` | no | Infrastructure as code | see stage skills | terraform, bicep, cloudformation |
| `secrets` | yes | Credential storage by reference | see stage skills | aws-secrets-manager, azure-key-vault, gcp-secret-manager, hashicorp-vault, adef-vault |
| `observability` | yes | Pipeline, data and cost telemetry | see stage skills | platform-native, datadog, monte-carlo, grafana, adef-console |
| `itsm` | no | Tickets, incidents, change records | see stage skills | jira, servicenow |
| `approval_channel` | yes | Where humans grant approvals | see stage skills | adef-console, pull-request-and-ticket, chat-workflow |

## Source patterns

How data arrives decides what Pipeline 1 must guarantee. The pattern is part of the
design and is approved at G3; it is never chosen by the Build agent.

| Pattern | What arrives | Pipeline 1 must guarantee |
|---|---|---|
| `database-batch` | Rows read from tables on a schedule | Incremental on a change watermark; a re-run replaces only its own batch |
| `database-cdc` | Insert, update and delete events from a replication tool | Every event keeps its operation; a delete at the source removes the row from silver |
| `files` | CSV, JSON, Parquet, Avro or XML files in a landing folder | Each file is loaded exactly once, against a declared schema; rows that do not fit are quarantined, not dropped |
| `saas-api` | Objects from an application, landed by a connector or pulled over its API | Incremental on the object's change cursor; throttling is respected; the cursor moves only after a successful write |
| `event-stream` | Messages on topics | A checkpoint gives exactly-once delivery into bronze; messages that do not parse are quarantined with their offset |

Whatever the pattern, bronze has the same contract (`_ingested_at`, `_batch_id`,
`_source_system`), so Pipelines 2 and 3 do not depend on how the data arrived.

## Composing a stack

A client's stack that is not a reference stack is composed from three choices: the
cloud, the analytics engine and the source. Every other slot takes that cloud's and
that engine's usual tool, and validation (T1) reports any pair of tools that do not fit
together: an engine on the wrong cloud, an ingestion tool that cannot handle the source
pattern, a consumption tool that needs a different engine. A composed stack is a
starting point. Confirm each slot with the Platform Owner before G0.

## Slot rules

- `yes` slots must be bound to a tool or the run cannot pass G0.
- A slot may be bound to `none` only if it is not marked required, with a reason.
- One tool can fill several slots (for example a platform's native tasks filling
  `orchestration`). Bind each slot explicitly anyway.
- An optional consumption slot (`data_api`, `data_sharing`, `reverse_etl`, `feature_store`,
  `vector_store`, `ai_consumption`) bound to `none` means that consumption pattern is not
  offered on this stack. Agents do not offer it, and do not substitute another tool.
- A new slot needs Data Architect approval and an update to this file. Do not create
  ad hoc slots in a profile.
