# ADEF product review

A review through the lens a top product company applies before putting something in front of
customers: what does a first-time evaluator experience, does the core promise hold up when
poked, and what would stop a pilot from going ahead. Findings are ranked by impact on a client
demo or pilot. Each "Done" item was implemented and tested in this release.

## The promise, restated

> Approval-gated AI agents take a business request from Jira to a governed data product: they
> design it, write the pipelines from the client's Oracle or Db2 source into an open-table-format
> lake on their cloud, and through to their analytics platform, with evidence at every step.

## Findings and actions

| # | Finding | Impact | Action | Status |
|---|---|---|---|---|
| 1 | **Nothing actually ran.** Code was generated and tests ran on generated rows, but no data moved from a source to a target. A data engineering buyer asks "show me the data" within minutes. | Critical | Added a local lakehouse runner that really executes the three pipelines: source DB → bronze → silver → gold (Delta or Iceberg) → DuckDB analytics. Gold is built by executing the **same SQL the Build agent generated**. | Done |
| 2 | **The architecture did not match how enterprises modernise.** One "compute engine" slot cannot express *Oracle/Db2 → cloud lake in an open table format → curated gold → Snowflake/Databricks/BigQuery*. | Critical | Stack Profiles now model the full path: `source_database`, `object_storage`, `table_format`, `lake_catalog`, `ingestion`, `lakehouse_compute`, `transformation`, `compute_engine`. Six presets cover AWS, Azure, GCP and Fabric, plus a local stack that executes. Validation blocks mismatched clouds and warns when an engine cannot read the format zero-copy. | Done |
| 3 | **No source system.** Without a source database there is no ingestion story. | Critical | Synthetic source databases for every industry: built-in SQLite (zero setup), plus Oracle and Db2 seed scripts and a one-command seeder. Verified on real Oracle Database Free 23ai and IBM Db2 11.5 containers. | Done |
| 4 | **Getting real agents running took too many clicks.** Keys had to be pasted into a UI before anything used a real model. | High | `ANTHROPIC_API_KEY=… ./run.sh` (or OpenAI, Gemini, Azure OpenAI, Bedrock) is enough. Keys are referenced from the environment, never written to disk, and the agent team is chosen from the keys present. | Done |
| 5 | **Not deployable as-is.** No guidance or hardening for hosting outside a laptop. | High | `run.sh`, a hardened Dockerfile, compose profiles (Oracle, Db2, HTTPS via Caddy), an EC2 user-data script that reads secrets from SSM Parameter Store, and a systemd unit. The server refuses to listen publicly without an access token. | Done |
| 6 | **Generated code was not proven.** Lint and sandbox tests passed while a real defect hid in the generated SQL. | High | Real execution found two bugs that static checks missed: (1) a derived column referencing another derived column in the same SELECT; (2) Iceberg rejecting all-NULL columns. Both are fixed, and the Test stage now rehearses all three pipelines for every run, whatever the target stack. | Done |
| 7 | **Data issues and code defects were conflated.** A planted orphan row would have failed the release as if the code were wrong. | Medium | Quality failures on source data are reported as *source data findings* routed to the Data Steward; generated-code failures remain test failures. | Done |
| 8 | **First screen did not orient a newcomer.** | Medium | Dashboard "Getting started" checklist shows live keys, agent team, source databases and stack. The run view gets a Lakehouse tab with the three-pipeline flow, row counts per layer, quality on real data, metric reconciliation and a masked data preview. | Done |
| 9 | **Incremental loading was claimed but not shown.** | Medium | Pipeline 1 is incremental on a `LAST_UPDATED_TS` watermark with per-batch idempotency. Shown live: change one row in Oracle or Db2, re-run, exactly one row is extracted and the analytics layer reflects it. | Done |
| 10 | Cloud execution is generated, not executed. | High (for pilots) | Generated PySpark/SQL/DMS/ADF/Datastream/publish code is syntax-checked and its gold SQL is executed locally, but nothing is run against a real AWS/Azure/GCP account from this environment. | Open: needs a sandbox cloud account per hyperscaler (backlog E3-3) |
| 11 | Local gold rebuilds type-2 dimensions as current versions only. | Low | The cloud code implements full SCD2 MERGE; the local runner keeps history out of scope for speed. | Open |
| 12 | Single-tenant, file-based state; no SSO. | Medium (for enterprise rollout) | Bearer token plus TLS via Caddy today. | Open: OIDC/SSO and a database-backed control plane for multi-user use |
| 13 | Model names for non-Anthropic providers drift quickly. | Low | "Discover models" lists what a key can use; presets are editable. | Mitigated |

## What a demo now shows, end to end

1. Start with a key: `ANTHROPIC_API_KEY=… ./run.sh`. The dashboard shows live agents.
2. New run → Telco → upload the Jira export from the client demo kit → stack **Local lakehouse**
   with **Oracle** as source (or any cloud stack: the code is generated for it and rehearsed locally).
3. Approve gates. Test rehearses the three pipelines on real data; G6a and G6b deploy to `test`
   and `prod` environments that really run.
4. Lakehouse tab: source → bronze → silver → gold → analytics with counts, quality findings,
   reconciled metrics and masked consumer data.
5. Change a row in the source, click **Re-run rehearsal**: one row flows through.

## Recommended next investments

1. Cloud sandbox accounts and a "deploy to cloud" adapter per hyperscaler, starting with AWS
   (Glue + Iceberg + Snowflake), proving the generated code the same way the local runner does.
2. SSO (OIDC) and role-based approvals mapped to the client's identity provider.
3. Full SCD2 in the local runner, and data contracts enforced at publish.
4. Evaluation harness for live-model runs: golden scenarios scored per provider and model, to
   choose team presets from evidence rather than defaults.
