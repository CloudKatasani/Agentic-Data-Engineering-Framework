# Client demo script (about 15 minutes)

Before the demo, start ADEF with a model key (or none, for the offline Demo Simulator):

```bash
ANTHROPIC_API_KEY=<your key> ./run.sh
```

To show extraction from a real Oracle database, also start and seed one (once):

```bash
docker compose --profile oracle up -d
```

```bash
SOURCE_DB_PASSWORD=$ORACLE_PASSWORD .venv/bin/python -m adef source-db seed --type oracle --dsn localhost:1521/FREEPDB1 --user system --domain telco
```

Then add it on **Integrations → Source databases** (DSN `localhost:1521/FREEPDB1`, user `system`).

## 1. Frame it (1 min) - Dashboard

"Nine specialist agents, one per lifecycle stage, coordinated by an orchestrator. Agents do the work.
Named humans approve at ten gates. Nothing risky happens without an approval tied to the exact
artifact."

Use the **How the AI team works with your team** table on the dashboard: for each stage it shows the
agent that does the work, what it produces, the gate, and the human role that decides.

The run page shows two lanes across the lifecycle: the **AI team** lane (which agent is working, done
or queued) above the **Human team** lane (which role decides at each gate, and when it is their turn).
The banner under the lanes always says whose turn it is: *AI team working*
(with the agent, model and elapsed time) or *Your turn* (with the named approver and a **Review**
button). At the end, **Team & cost** shows measured agent working time against time spent waiting on
people, and the number of human decisions.

## 2. Their models, their keys (2 min) - Agents & models, Providers & API keys

- Show the per-agent table. The default **Multi-vendor enterprise team** gives each agent a different
  provider and model (Claude, GPT, Gemini, Azure OpenAI, Bedrock, a local Ollama model). Switch presets
  to show *All Claude* or *Cost-optimised*. Point out effort and max tokens.
- The *Key* column shows which providers have keys. Without keys, the demo fallback simulates those
  stages and says so; the run's *Agents & cost* tab shows "bound to" versus "served by".
- On Providers, add a key. It is encrypted, shown only as `••••1234`, and never reaches artifacts,
  logs or prompts. Click **Test**.

## 3. Their stack (2 min) - Technology stacks

- Each reference stack shows its three pipelines: **Oracle or Db2 → S3, ADLS, GCS or OneLake as
  Iceberg or Delta → curated gold → Snowflake, Databricks, BigQuery, Redshift or Fabric**.
- Change one slot (for example the analytics engine) and watch the flow update, then **Validate**.
  Show a blocked choice: ADLS storage on an AWS stack.
- Key message: "The logical design never names a product. Switching stack means switching profile,
  not rewriting agents."

## 4. Their requirements (2 min) - New run

For a Telco audience, use the **client demo kit**: on *Integrations → Demo data packs*, choose
*telco (client demo kit)* and click **Download all (.zip)** before the demo. Then upload the numbered
files as the steps below describe (`00-README.md` in the zip has the same map). Use client code
`NIMBUS-MOBILE`.


- Pick the client's industry Domain Pack.
- Requirements source → **Read from Jira** → *Fetch issues*, or *Use sample export* to load the
  bundled Jira CSV export (`demo-data/<domain>/jira/`). Point out the issue flagged
  "instruction-like text" (`UTIL-8` asks the automation to grant access to everyone and deploy to
  production). It is treated as data and reported, never acted on.
- Stack → choose one. Source metadata → *Use sample source catalog*, or upload the client's own
  catalog or modelling export (CSV, DDL or DBML). The Mapping agent marks every source it finds there
  as high confidence.
- Launch.

## 4b. Give the agents the right context (2 min) - Context tab

"Agents hallucinate when they are missing facts. Here each agent tells you what it needs, and your
people attach it from where it already lives."

- Open the run's **Context** tab. Each stage lists what its agent needs, why, and whether it is covered.
- On *Requirements*, click **Add** next to *Business glossary and KPI definitions*, pick the Confluence
  page, **Attach**. Add a **note** with a decision the agent could not know. Show the ServiceNow change
  freeze for *Release* and the GitHub style guide for *Build*.
- At the gate, point to **Agent context → see what it knew**: the context pack lists exactly what the
  agent was given and what recommended context was missing.
- To show a correction loop: attach something after a stage ran, then **Re-run with the new context**.
- Run with autopilot off if you want to add context before each stage starts; the banner offers
  **Add context first**.

## 5. The gated lifecycle (5 min) - Run view

- Watch the activity feed as the agents work. At each gate, open the evidence link before approving:
  - **G1**: requirements are technology-neutral; Domain Pack controls appear as NFRs.
  - **G2**: source-to-target mapping with confidence and gaps.
  - **G3**: the **Data model & exports** tab shows the ER diagram, the cost estimate with arithmetic,
    and the ADRs.
  - **G4**: the **Code** tab shows the git graph with the feature branch and pull request for their
    stack's tools.
  - **G5**: the evidence pack: every rule executed, every rule proven to catch a seeded defect, metrics
    reconciled two ways.
- **Show drift protection:** after approving G1, open `01-requirements/requirements.md`, click
  **Edit as human**, change one line, and save. The G1 approval turns *stale* and the gate must be
  re-requested.
- **Per-artifact review:** every gate lists its artifacts with **Approve** / **Reject** on each one
  (or **Approve all**). Each verdict is bound to that artifact's hash. One **Submit review** button
  covers every role the named person holds.
- **Show rejection:** reject one artifact with a reason (for example `00-intake/backlog.md`). Any
  rejected artifact rejects the gate; the reasons pre-fill the rework instructions, then **Send back
  for rework**. The agent redoes only that stage.

## 5b. Show the data moving (3 min) - Lakehouse tab

Use the **Local lakehouse** stack with the Oracle source for this part (any stack still gets a rehearsal).

- The flow shows source → bronze → silver → gold → analytics with real row counts per layer.
- *Quality on real data*: point out the rules that ran on actual rows, and any source data findings
  routed to the Data Steward.
- *Metrics*: churn rate and ARPU are identical in the lake (gold) and the analytics layer.
- *Preview*: the analyst's view of `dim_subscriber` shows phone numbers masked.
- Incremental load: change one subscriber's status in Oracle (and its `LAST_UPDATED_TS`), click
  **Re-run rehearsal**. Exactly one row is extracted and the new status appears in the analytics layer.
- Code tab: `pipelines/01_ingest`, `02_curate`, `03_publish` is what would run on their cloud.

## 6. What they take away (2 min)

- **Data model & exports**: download DDL for their engine, plus Collibra / Purview / DataHub /
  Alation payloads, the dbt `schema.yml`, the ODCS contract and OpenLineage.
- **Integrations → Demo data packs**: the ready-made Jira exports, source data, model exports,
  catalog payloads and lineage (OpenLineage, column lineage CSV, Mermaid diagram) for each industry.
- **Download run bundle**: the full audit-ready workspace.
- **Verify audit logs**: hash-chained logs show intact.
- **Guardrails** page: **Run suite** executes all 14 guardrail scenarios live.

## If something looks stuck

- The banner says what the run is waiting on. *Your turn* means a named person still has to review a
  gate; a gate with two roles (for example G0) needs both.
- A live model call logs "still working" to the activity feed every 15 seconds. After
  `ADEF_MODEL_TIMEOUT_SECONDS` (default 600) the stage falls back to the Demo Simulator and says so.
  For a live demo on a slow network, start with `ADEF_MODEL_TIMEOUT_SECONDS=120`.
- If the server was restarted mid-stage, the stage shows as stopped with **Retry stage**; if it was
  restarted right after an approval, the banner offers **Resume run**.

## Likely questions

- *Does it deploy to our platform?* Not in this release. Promotion is simulated and labelled as such.
  Connecting a platform means writing the reviewed adapter for that slot (backlog E3).
- *Where does our data go?* Agents work from metadata. Restricted columns are metadata-only. Tests use
  synthetic data. Model calls receive artifacts and metadata, never credentials.
- *Can we use our own LLM gateway?* Yes: add an OpenAI-compatible provider with your gateway URL.
