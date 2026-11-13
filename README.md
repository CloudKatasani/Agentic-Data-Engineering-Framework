# ADEF - Agentic Data Engineering Framework

An approval-gated team of nine AI agents that takes a business request to a governed data product:

**Business intent → Requirements → Mapping → Design → Build → Test → Release → Operations → Consumption**

The agents design and build the modern enterprise data path, then prove it by running it:

```
 Oracle / Db2 / SQL Server        AWS S3 · Azure ADLS · GCS · OneLake                  Snowflake · Databricks
 source database ──Pipeline 1──▶ bronze ──Pipeline 2──▶ silver ──▶ gold ──Pipeline 3──▶ BigQuery · Redshift · Fabric
       (incremental, watermark)   Iceberg or Delta, in the lake catalog                 (zero-copy where possible)
```

- **Three pipelines, generated for your stack.** Pipeline 1 is a PySpark JDBC extract, plus AWS DMS,
  Azure Data Factory or Datastream configuration. Pipeline 2 is Spark SQL `MERGE` from bronze to
  silver to gold (or Lakeflow, dbt, Dataform). Pipeline 3 publishes to Snowflake Iceberg tables,
  Databricks SQL, BigQuery BigLake, Redshift Spectrum or Fabric, with orchestration chaining all three.
- **Proved on real data.** Every run rehearses all three pipelines on a synthetic source database:
  real Delta or Iceberg tables, real gold built by the generated SQL, quality rules on real rows, and
  metrics reconciled between the lake and the analytics layer. On the **Local lakehouse** stack the
  G6a/G6b releases really deploy to `test` and `prod`.
- **Source databases with synthetic data.** Built-in SQLite sources for four industries, plus Oracle
  and Db2 schemas and data that run on real Oracle Database Free and Db2 Community containers.
- **Bring your own model, per agent.** Anthropic, OpenAI, Azure OpenAI, Gemini, Bedrock or any
  OpenAI-compatible endpoint. Pass keys as environment variables; the agent team is chosen from them.
  The offline **Demo Simulator** runs everything without a key.
- **Jira, data modelling and catalogs.** Jira Cloud/Data Center or exported files; imports from
  modelling tools and catalogs; 16 model, catalog and lineage export formats.
- **Guardrails enforced in code.** Action classes A0-A4, hash-bound approvals, one writer per folder,
  secret and prompt-injection scanning, hash-chained audit logs, and 14 executable guardrail scenarios.

See [docs/PRODUCT_REVIEW.md](docs/PRODUCT_REVIEW.md) for the product review behind this release.

## Quick start

```bash
./run.sh
```

That creates a virtual environment, installs dependencies and opens the console on
http://127.0.0.1:8000 in demo mode. To use real models, pass a key (one or several):

```bash
ANTHROPIC_API_KEY=sk-ant-... ./run.sh
```

Keys are read from the environment and never written to disk by ADEF. Supported variables:
`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `AZURE_OPENAI_API_KEY` +
`AZURE_OPENAI_ENDPOINT`, `AWS_BEARER_TOKEN_BEDROCK` + `AWS_REGION`, `OLLAMA_BASE_URL`.

Then: **New run** → pick an industry → *Use sample export* (Jira) → choose a stack (try **Local
lakehouse**) → launch and approve the gates. The **Lakehouse** tab shows the data moving through each layer.

### Host it for others (EC2, any VM, Docker)

```bash
ADEF_API_TOKEN=$(openssl rand -hex 24) ANTHROPIC_API_KEY=sk-ant-... ./run.sh --host 0.0.0.0
```

The server refuses to listen beyond localhost without `ADEF_API_TOKEN`. With Docker
(copy `.env.example` to `.env` first):

```bash
docker compose up -d --build
```

Optional profiles: `--profile oracle` and `--profile db2` start synthetic source databases, and
`--profile https` adds Caddy with automatic TLS for `DOMAIN`. For AWS, see
[deploy/ec2/README.md](deploy/ec2/README.md): a user-data script that pulls keys from SSM Parameter
Store. For a VM without Docker, use [deploy/systemd/adef.service](deploy/systemd/adef.service).

### Source databases

```bash
docker compose --profile oracle up -d
```

```bash
SOURCE_DB_PASSWORD=$ORACLE_PASSWORD .venv/bin/python -m adef source-db seed --type oracle --dsn localhost:1521/FREEPDB1 --user system --domain telco
```

Db2 works the same way (`--profile db2`, `--type db2 --user db2inst1`; install the driver with
`WITH_DB2=true ./run.sh`). Then add the connection on **Integrations → Source databases** and pick
it in the run wizard. Seed scripts for every industry are also in `demo-data/<domain>/source-database/`.

### Tests and headless demo

```bash
make test
```

84 tests, including the full lifecycle for every industry and stack, real three-pipeline execution in
Delta and Iceberg, incremental extraction, all 14 guardrail scenarios and the live-LLM path.

```bash
.venv/bin/python -m adef demo --domain telco --stack local-lakehouse
```

See [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) for a 15-minute client demo walkthrough.

## Using real models

1. **Providers & API keys** → add a provider (for example Anthropic), paste the key once (it is
   encrypted and shown only as `••••1234` from then on), then **Test**.
2. **Agents & models** → bind each agent: for example `claude-opus-5-5` for Design and Build,
   `claude-haiku-5-5` for Operations, or a different vendor per agent. Model names are free text;
   **Discover models** lists what your key can access. Effort maps to the provider's reasoning-depth
   control.
3. New runs snapshot these bindings into `control/run.yaml`.

With a live model, the agents produce the requirements, mapping and logical design as JSON that is
checked against a schema. Output that is invalid, or that names a vendor product in a logical
artifact, is sent back to the model once with the validator's errors. Build, Test, Release, Operations
and Consumption use the model for review notes, risk assessments, runbook guidance and the consumer
guide. Code generation and test execution are deterministic and stack-bound.

The Claude provider uses the official `anthropic` SDK with streaming, `output_config.effort`, and
server-side refusal fallbacks for the models that support them. The other providers use their REST
APIs directly.

## Default agent team: a different provider and model per agent

New installations start with the **Multi-vendor enterprise team** preset:

| Agent | Provider | Model | Effort |
|---|---|---|---|
| adef-orchestrator | Anthropic | `claude-opus-5-5` | high |
| adef-intent-requirements | OpenAI | `gpt-5.6-sol` | high |
| adef-source-target-mapping | Google Gemini | `gemini-4-argon` | high |
| adef-solution-design | Anthropic | `claude-fable-5-2` | high |
| adef-pipeline-build | Azure OpenAI | deployment `gpt-5-6-terra-prod` | medium |
| adef-test-quality | Amazon Bedrock | `anthropic.claude-sonnet-5-5` | medium |
| adef-release-deploy | Anthropic | `claude-sonnet-5-5` | medium |
| adef-operations-observability | Ollama (local, open-weight) | `llama3.3` | low |
| adef-data-consumption | Google Gemini | `gemini-3.8-flash` | medium |

Other presets on **Agents & models**: *All Claude (tiered)*, *All OpenAI*, *Cost-optimised mix* and
*Demo Simulator only*. Every value can still be edited per agent. Model names were current when written;
confirm the ones your account can use with **Discover models**. The Azure value is a deployment name,
so replace it with your own.

**Demo fallback** (on by default): if an agent's provider has no key, can't be reached or rejects the key,
that stage runs on the Demo Simulator. The fallback is recorded in the activity feed and the decision log,
and the run's *Agents & cost* tab shows both the bound model and what actually served each stage. Turn it
off on **Agents & models** for real client work; a missing key then stops the stage with a clear error.

## Context for every agent (optional integrations)

An agent that lacks a fact tends to invent one. So each stage declares what its agent needs, and a
person can attach more at any time from an integration, a file or a note. Open a run's **Context** tab.

| Stage | What the agent needs | Usually kept in |
|---|---|---|
| Intake | Project charter or SOW; epic and backlog; budget and constraints | Confluence, Jira, upload, note |
| Requirements | Stories with acceptance criteria; business glossary and KPI definitions; workshop decisions | Jira, Confluence, upload |
| Mapping | Source data dictionary or catalog export; rules for derived fields; known data quality issues | Upload, Confluence, Jira, ServiceNow |
| Design | Architecture and naming standards; existing models; cost guardrails | Confluence, GitHub |
| Build | Coding standards and SQL style guide; CI checks and branch rules; pipeline templates | GitHub, Confluence |
| Test | Test strategy and quality thresholds; known defects and incidents; figures to reconcile against | Confluence, Jira, ServiceNow, upload |
| Release | Change policy; change calendar and freeze windows; deployment configuration | Confluence, ServiceNow, GitHub |
| Operations | On-call runbook and service levels; past incidents | Confluence, ServiceNow, Jira |
| Consumption | Access and masking policy; glossary; BI standards | Confluence, upload |

- **Integrations** (all read-only, all optional): Confluence (Cloud or Data Center), Jira, GitHub (or GitHub
  Enterprise) and ServiceNow. Configure them on the **Integrations** page; tokens go in the encrypted vault.
  Each works in demo mode, with sample content for the run's industry, until you connect it.
- **Uploads and notes**: text, Markdown, CSV, JSON, YAML, SQL, HTML or Word (.docx), up to 5 MB.
- **How the agent uses it**: every item gets an id (`CTX-001`) and is passed to the stage's model calls as
  reference data, never as instructions. The agent is told to prefer it over assumptions, cite the ids it
  relies on, and raise an open question rather than invent a missing fact.
- **What the approver sees**: the stage writes `context-pack.md` listing every item the agent was given
  (source, who attached it, hash, whether it was cited) and the recommended context that was not provided.
  It is one of the artifacts reviewed at the gate.
- **Adding context later**: attach it, then use **Re-run with the new context** on the stage.
- **Safeguards**: secrets are redacted, instruction-like text is flagged and still treated as data, only a
  named person can attach, and every attach or removal is in the action log. Each item is capped at 20,000
  characters and each stage at 60,000.
- The Demo Simulator does not read attached context; the context pack says so. Use a live model key to see
  context change the output.

## Demo data packs

`demo-data/` holds synthetic, deterministic files for each industry. Regenerate them with
`python -m adef demo-data`.

**Telco client demo kit** (`demo-data/telco/client-demo-kit/`): only the *input* files a client hands
over, numbered in upload order, for a fictional client (Nimbus Mobile). Download it as one zip from
**Integrations → Demo data packs → Download all (.zip)**; `00-README.md` says where each file goes.

| File | Upload it in |
|---|---|
| `01-business-request.md` | New run → step 2 (*Both*), paste into *Business request* |
| `02-jira-export-TEL.csv` / `03-jira-export-TEL.json` | New run → step 2 → *Upload a Jira export* |
| `04-catalog-export-source-systems.csv` (Collibra-style) | New run → step 4 *Source metadata* |
| `05-source-model-erwin.sql` / `06-source-model.dbml` | Alternatives for step 4, or Model & catalog studio |
| `07-legacy-warehouse-model.sql` (Oracle as-is mart) | Model & catalog studio → export to the target stack |

The packs below also include ADEF's *outputs* (model, catalog and lineage exports) for reference:

| Folder | Contents |
|---|---|
| `jira/` | Jira CSV export (the "all fields" layout) and REST/JSON export (ADF descriptions): epic, stories with acceptance criteria, NFR stories, a task, a parked phase-2 story, and one ticket with planted instruction-like text |
| `source-metadata/` | Source-system catalog export (CSV) and source DDL |
| `source-data/` | Synthetic rows for every source table, with keys that join and documented anomalies (e.g. an orphan bill for DQ-003) |
| `model/` | DDL for Snowflake, Databricks, BigQuery and T-SQL; DBML; Mermaid and PlantUML ERDs; logical model JSON; dbt schema; ODCS contract; data dictionary |
| `catalog/` | Collibra import, Purview/Atlas entities, DataHub MCPs, Alation bulk CSV, business glossary, Unity Catalog and Snowflake governance SQL |
| `lineage/` | OpenLineage events, column- and table-level lineage CSV, Mermaid lineage diagram |

In the console: **New run** has *Use sample export* (Jira) and *Use sample source catalog* buttons;
**Integrations** lists every pack with download, preview and import actions; **Model & catalog
studio** loads a sample model. A Jira export from your own Jira can be uploaded in the same places.
No connection is needed. The data contains no real people: names come from fixed word lists, phone
numbers use the fictional 555 range, and emails use example.com.

## What each stage really does

| Stage | Agent | Real work performed | Gate |
|---|---|---|---|
| 0 Intake | orchestrator | Intake brief, stack validation (T1), untrusted-content report | G0 |
| 1 Requirements | intent-requirements | REQ/BR/NFR baseline from Jira and the request; Domain Pack controls become NFRs; technology-term scan | G1 |
| 2 Mapping | source-target-mapping | MAP rows, DQ rules, keys, gaps; reconciled against imported catalog metadata | G2 |
| 3 Design | solution-design | Logical model, data flow, contract, physical binding, DDL, ADRs, cost estimate with arithmetic | G3 |
| 4 Build | pipeline-build | Stack-specific code committed to a git feature branch, with lint, sandbox unit tests, run-twice idempotency check and a pull request | G4 → merge |
| 5 Test | test-quality | Executes every DQ rule on synthetic data, seeds a defect for each rule (mutation check), reconciles metrics two independent ways, verifies masking and requirement coverage | G5 |
| 6 Release | release-deploy | Tested-commit = deployed-commit check, rollback rehearsal, promotion to test then production | G6a, G6b |
| 7 Operations | operations-observability | Monitors from rules and NFRs, runbook with action classes, pre-approved actions, incident drill | G7 |
| 8 Consumption | data-consumption | Semantic model (Power BI TMDL / LookML / dbt semantic layer), masked views, metric consistency check, catalog entry, contract | G8 → publish |
| Assembly | orchestrator | Delivery pack, traceability matrix, run metrics, all 16 exports | - |

Generated code targets dbt, Spark SQL pipelines, Dataform or portable SQL, plus Airflow, Databricks
Workflows, ADF, Snowflake tasks or Dagster, CI for GitHub Actions, GitLab, Azure Pipelines or Jenkins,
and Terraform. The choice follows the Stack Profile.

## Guardrails: rule → mechanism

| Rule | Mechanism (code) |
|---|---|
| One writer per stage folder | `RunWorkspace.write` allowlist |
| A0-A4 action classes | `ActionGuard.execute` pre-call hook; unknown actions default to A3 |
| No secrets anywhere | Vault plus scanners on every write, request and ticket |
| Approval tied to artifact hash | `request_gate` / `decide` / `gate_status`: any edit makes the approval stale |
| Agents never approve | Approver must be the named human holding the role in `run.yaml` |
| Tested commit = deployed commit | Release refuses (A4) on mismatch |
| Instructions inside data are ignored | Injection scanner, `<untrusted_data>` wrapping, findings reported at intake |
| Logical before physical | Technology-term scan on `01-`, `02-`, `03-design/logical/` |
| Audit | Hash-chained `approvals`, `action-log`, `decision-log` and `events` logs, with a verify button |
| Loops and escalation | 3 returns or 2 rejections escalate to the human owner |

## Upgrading from the ADPE name

The framework was first called ADPE ("Autonomous Data Platform Engineering"). It is now ADEF, matching
the project name. The package is `adef` (`python -m adef …`) and agent and skill IDs are `adef-*`.
Older installations keep working: `ADPE_HOME`, `ADPE_MASTER_KEY` and `ADPE_API_TOKEN` are still read
when the `ADEF_*` variables are unset, saved per-agent settings are migrated on load, and runs started
before the rename can be viewed and continued.

## Project layout

```
adef/                 runtime (Python package)
  api/app.py          REST API + console host
  engine/             orchestrator, stage agents, codegen, SQLite sandbox, golden scenarios
  llm/                providers: anthropic SDK, OpenAI, Azure OpenAI, Gemini, Bedrock, OpenAI-compatible, simulator
  guardrails/         scanners, action-class hook, GT-01..14 suite
  workspace/          run workspace, approvals, hash-chained logs, handoff envelopes
  modeling/           logical model, physical binding, 16 exporters, importers
  connectors/jira.py  Jira Cloud / Data Center / demo
  catalog/            capability slots, Stack Profile presets, providers, Domain Packs
web/                  console (no build step, no external assets; fonts/ bundles Carlito, OFL 1.1)
skills/ agents/       the specification pack (agent prompts and skills)
docs/spec/            original build spec and spec-pack archive
adapters/ evals/      adapter library (to be reviewed per client), evaluation notes
tests/                pytest suite
```

Run workspaces live under `$ADEF_HOME/runs/<run_id>/` (default `./data`) and follow
`skills/adef-shared-guardrails/references/artifact-layout.md`. Each run also has a local git
repository (`repo/`) standing in for the client's version-control slot.

## Honest limits of this release

- **Cloud pipelines are generated, not executed here.** The PySpark, Spark SQL, DMS, ADF, Datastream
  and publish code is syntax-checked, and its gold SQL is executed by the local rehearsal, but nothing
  runs against a real AWS, Azure or GCP account from this tool yet. Cloud promotion at G6a/G6b is
  labelled *simulated*. The **Local lakehouse** stack really executes end to end.
- **Local type-2 dimensions are current versions only.** The generated cloud code implements full SCD2
  `MERGE`; the local runner rebuilds gold from silver on each run.
- **Adapters still need review.** Built-in templates are flagged as such by stack validation until a
  reviewed adapter is added under `adapters/`.
- **Domain Packs are starters.** Their controls are not legal or compliance advice.
- **Single tenant.** One console per environment, file-based state, bearer-token auth (`ADEF_API_TOKEN`)
  and TLS via Caddy. Use your SSO proxy for shared use.
