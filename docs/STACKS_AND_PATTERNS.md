# Technology stacks, sources, data types and consumption patterns

What the product supports today, generated from the code (`adef/catalog/stacks.py`,
`adef/engine/ingest_patterns.py`, `adef/modeling/physical.py`, `adef/engine/consume.py`).

**Read this first.** Only the local stack executes its pipelines for real. For every cloud
stack the agents hand over code, configuration and SQL in that stack's own syntax, which is
checked for syntax and rehearsed against a local copy of the model. None of it has been run
on a real Snowflake, Databricks, BigQuery, Redshift, Athena, Synapse or Fabric account, or
against a real Kafka, Fivetran or SharePoint. Treat the generated code as a reviewed starting
point for the client's engineers, not as a finished deployment.

## 1. Reference stacks

Thirteen stacks ship ready to use. Each follows the same three pipelines: ingest into an open
table format in the lake, curate bronze to silver to gold, publish to the analytics engine.

| Stack | Cloud | Source | Arrives as | Ingestion | Lake | Curated on | Served from |
|---|---|---|---|---|---|---|---|
| `example-a` | aws | oracle | database, change data capture | aws-dms | iceberg on s3 | aws-glue | snowflake |
| `example-b` | azure | db2 | database, batch extract | azure-data-factory | delta on adls | databricks | databricks |
| `gcp-bigquery` | gcp | oracle | database, change data capture | gcp-datastream | iceberg on gcs | dataproc | bigquery |
| `azure-fabric` | azure | db2 | database, batch extract | azure-data-factory | delta on onelake | fabric-spark | fabric |
| `aws-redshift` | aws | db2 | database, batch extract | spark-jdbc | iceberg on s3 | emr-spark | redshift |
| `aws-databricks` | aws | postgres | database, change data capture | aws-dms | delta on s3 | databricks | databricks |
| `azure-snowflake` | azure | sqlserver | database, batch extract | azure-data-factory | iceberg on adls | synapse-spark | snowflake |
| `azure-synapse` | azure | sqlserver | database, batch extract | azure-data-factory | delta on adls | synapse-spark | synapse |
| `saas-snowflake` | aws | salesforce | application API | fivetran | iceberg on s3 | aws-glue | snowflake |
| `gcp-databricks-streaming` | gcp | kafka-topics | event stream | spark-structured-streaming | delta on gcs | databricks | databricks |
| `files-athena` | aws | files | files | spark-files | iceberg on s3 | aws-glue | athena |
| `teradata-bigquery` | gcp | teradata | database, batch extract | spark-jdbc | iceberg on gcs | dataproc | bigquery |
| `local-lakehouse` | local | sqlite-local | database, batch extract | adef-local-extract | delta on local-filesystem | duckdb-local | duckdb-local |

## 2. Any other stack: the composer

On **Technology stacks**, choose a cloud, an analytics engine and a source. Every other slot is
filled with that cloud's and that engine's usual tool, and the result is validated.

| Cloud | Analytics engines |
|---|---|
| AWS | Snowflake, Databricks, Redshift, Athena, Trino, Starburst, PostgreSQL |
| Azure | Snowflake, Databricks, Synapse, Microsoft Fabric, Trino, Starburst, PostgreSQL |
| Google Cloud | Snowflake, Databricks, BigQuery, Trino, Starburst, PostgreSQL |

| Source | Can arrive as |
|---|---|
| Oracle | database, batch extract, database, change data capture |
| IBM Db2 | database, batch extract, database, change data capture |
| SQL Server | database, batch extract, database, change data capture |
| PostgreSQL | database, batch extract, database, change data capture |
| MySQL | database, batch extract, database, change data capture |
| Teradata | database, batch extract, database, change data capture |
| SAP HANA | database, batch extract, database, change data capture |
| Netezza | database, batch extract, database, change data capture |
| MongoDB | database, batch extract, database, change data capture |
| DynamoDB | database, batch extract, database, change data capture |
| Azure Cosmos DB | database, batch extract, database, change data capture |
| Salesforce | application API |
| SAP S/4HANA | application API |
| Workday | application API |
| ServiceNow | application API |
| Dynamics 365 | application API |
| Files (CSV, JSON, Parquet, Avro, XML) | files |
| Event topics | event stream |
| Mainframe Db2 for z/OS | database, batch extract, database, change data capture |

That is 620 combinations of cloud, engine, source and arrival pattern. All of them validate, and
code generation has no gaps for any of them (tested). Any slot can then be changed by hand;
validation reports tools that do not fit together, for example Redshift on Azure, an ingestion
tool that cannot read files, or a Snowflake share on a Synapse stack.

## 3. How data arrives: five source patterns

Pipeline 1 is generated for the way the source really delivers data. Bronze has the same
columns whatever the pattern, so pipelines 2 and 3 do not change.

| Pattern | Generated | What it guarantees |
|---|---|---|
| Database, batch extract | Spark JDBC job (or the connector job for MongoDB, DynamoDB, Cosmos DB) | Incremental on a change watermark; a re-run replaces only its own batch |
| Database, change data capture | Replication tool configuration (AWS DMS, Datastream, Debezium, Data Factory, Fivetran, Airbyte) and a fold job | Each event keeps its operation; a source delete removes the row from silver |
| Files | A file loader (Spark, or Auto Loader on Databricks) for CSV, JSON, Parquet, Avro, XML | Each file loaded once; rows that do not fit the declared schema are quarantined |
| Application API | Fivetran or Airbyte connection, or a paginated REST extractor, and a fold job | Incremental on the object's cursor; throttling respected; the cursor moves only after a successful write |
| Event stream | Spark Structured Streaming job for Kafka, Confluent Cloud, MSK, Event Hubs, Kinesis or Pub/Sub | Checkpointed, exactly-once into bronze; messages that do not parse are quarantined with their offset |

## 4. Data types beyond flat tables

The logical model accepts seven more types. Each maps to the engine's native type where one
exists; where it does not, the value is kept as text so nothing is lost.

| Logical type | Snowflake | Databricks (Delta) | BigQuery | Redshift | Trino | Synapse / Fabric | PostgreSQL |
|---|---|---|---|---|---|---|---|
| `timestamp_tz` | `TIMESTAMP_TZ` | `TIMESTAMP` | `TIMESTAMP` | `TIMESTAMPTZ` | `TIMESTAMP(6) WITH TIME ZONE` | `DATETIMEOFFSET(6)` | `TIMESTAMPTZ` |
| `time` | `TIME` | `STRING` | `TIME` | `TIME` | `TIME(6)` | `TIME(6)` | `TIME` |
| `json` | `VARIANT` | `VARIANT` | `JSON` | `SUPER` | `VARCHAR` | `NVARCHAR(MAX)` | `JSONB` |
| `array` | `ARRAY` | `ARRAY<STRING>` | `ARRAY<STRING>` | `SUPER` | `ARRAY(VARCHAR)` | `NVARCHAR(MAX)` | `JSONB` |
| `binary` | `BINARY` | `BINARY` | `BYTES` | `VARBYTE` | `VARBINARY` | `VARBINARY(MAX)` | `BYTEA` |
| `uuid` | `VARCHAR(36)` | `STRING` | `STRING` | `VARCHAR(36)` | `UUID` | `UNIQUEIDENTIFIER` | `UUID` |
| `geography` | `GEOGRAPHY` | `STRING` | `GEOGRAPHY` | `GEOGRAPHY` | `VARCHAR` | `NVARCHAR(MAX)` | `TEXT` |

Source types are recognised by their usual names (`VARCHAR2`, `NVARCHAR`, `VARIANT`, `SUPER`,
`JSONB`, `UNIQUEIDENTIFIER`, `DATETIMEOFFSET`, `TIMESTAMP WITH TIME ZONE`, `BLOB` and others).
JSON and array values are kept whole in bronze and validated in silver; the mapping names the
paths that become columns.

## 5. How the product is consumed: nine patterns

A run chooses its consumption patterns on **Review & launch**. A pattern is available when the
stack binds a tool for it.

| Pattern | For | What is handed over | Delivered with |
|---|---|---|---|
| **Dashboards and reports** | Business users and analysts | A semantic model for the BI tool, with the governed metrics. | cognos, looker, power-bi, qlik, quicksight, sigma, tableau, thoughtspot |
| **Governed SQL access** | Analysts and data scientists | Masked consumer views and the access model for direct queries. | the analytics engine itself |
| **Ask in plain language** | Business users | A semantic model and verified queries that ground a natural-language assistant. | amazon-q, bigquery-conversational-analytics, databricks-genie, fabric-copilot, snowflake-cortex-analyst |
| **Data API for applications** | Application teams | An API specification over named, parameterised queries. | graphql, rest-openapi |
| **Share with other organisations** | Partners and other business units | A live share of the masked views, with no copies. | analytics-hub, delta-sharing, onelake-shortcut, redshift-datashare, snowflake-secure-share |
| **Sync back to business applications** | Sales, service and marketing teams | Sync definitions that push curated attributes into operational tools. | census, hightouch |
| **Features for machine learning** | Data scientists and ML engineers | A feature set with one row per business key, and its registration. | azure-ml-feature-store, databricks-feature-store, feast, sagemaker-feature-store, snowflake-feature-store, vertex-feature-store |
| **Search index for AI applications** | AI application teams | Documents that describe the product, and a vector index over them. | azure-ai-search, bigquery-vector-search, databricks-vector-search, opensearch, pgvector, snowflake-cortex-search |
| **Scheduled file exports** | Downstream systems and regulators | Export statements with a manifest and a control total. | the analytics engine itself |

For every pattern:

- It reads the masked consumer views, never a base table.
- The SQL it relies on is executed against the sandbox copy of the model before G8, and the
  result is in `08-consumption/validation.md`.
- Its files are approved by hash at G8 with the rest of the stage.
- Anything that sends data outside the platform is generated switched off: share recipients are
  commented out, and reverse ETL syncs are created paused.

To finish by hand: registering features in Vertex AI or Azure Machine Learning is described,
not scripted; and the embedding dimension of an OpenSearch or Azure AI Search index must be set
to match the embedding model.

## 6. Where project knowledge comes from: eight integrations

All optional and read-only, each with a demo mode. Attach items from them to any stage on a
run's **Context** tab.

| System | What it holds |
|---|---|
| Confluence | Project charters, business glossary, standards, runbooks, meeting decisions |
| Jira | Epics, stories, defects, test plans, change tickets |
| GitHub | Coding standards, existing pipeline code, CI configuration, CODEOWNERS |
| ServiceNow | Change calendar and freeze windows, incidents, CAB policy, knowledge articles |
| Azure DevOps | Epics, user stories, bugs and test plans in Azure Boards |
| GitLab | Coding standards, existing pipeline code, CI configuration, CODEOWNERS |
| SharePoint | Charters, standards, policies and meeting decisions kept as documents |
| Collibra | Business glossary, data dictionary, data owners and classifications |

## 7. Limits

- Cloud code is generated and syntax-checked, not executed. Connector and SDK calls are written
  from the vendors' documented interfaces and have not been run against live services.
- Curation is written in Spark SQL (or PySpark, dbt, Dataform or Lakeflow pipelines). A stack
  that curates inside the warehouse with no Spark engine is not generated yet.
- The built-in demo scenarios are relational. File, API and stream ingestion is generated for
  them, but the local rehearsal always reads the synthetic database.
- The four new integrations were tested against mocked responses, not live systems.
