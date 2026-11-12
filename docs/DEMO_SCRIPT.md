# Client demo script (about 15 minutes)

Before the demo:

```bash
make install
```

```bash
ADEF_API_TOKEN=<choose-one> make run
```

Optionally add a real provider key on **Providers & API keys** and test it. The demo works fully
offline with the Demo Simulator.

## 1. Frame it (1 min) - Dashboard

"Nine specialist agents, one per lifecycle stage, coordinated by an orchestrator. Agents do the work.
Named humans approve at ten gates. Nothing risky happens without an approval tied to the exact
artifact."

## 2. Their models, their keys (2 min) - Agents & models, Providers & API keys

- Show the per-agent table. The default **Multi-vendor enterprise team** gives each agent a different
  provider and model (Claude, GPT, Gemini, Azure OpenAI, Bedrock, a local Ollama model). Switch presets
  to show *All Claude* or *Cost-optimised*. Point out effort and max tokens.
- The *Key* column shows which providers have keys. Without keys, the demo fallback simulates those
  stages and says so; the run's *Agents & cost* tab shows "bound to" versus "served by".
- On Providers, add a key. It is encrypted, shown only as `••••1234`, and never reaches artifacts,
  logs or prompts. Click **Test**.

## 3. Their stack (2 min) - Technology stacks

- Click through the five reference stacks. Change one slot, for example `catalog_governance` to
  `purview`, then **Validate**. Show an incompatible choice, such as Spark pipelines on BigQuery, being
  blocked.
- Key message: "The logical design never names a product. Switching stack means switching profile,
  not rewriting agents."

## 4. Their requirements (2 min) - New run

- Pick the client's industry Domain Pack.
- Requirements source → **Read from Jira** → *Fetch issues*, or *Use sample export* to load the
  bundled Jira CSV export (`demo-data/<domain>/jira/`). Point out the issue flagged
  "instruction-like text" (`UTIL-8` asks the automation to grant access to everyone and deploy to
  production). It is treated as data and reported, never acted on.
- Stack → choose one. Source metadata → *Use sample source catalog*, or upload the client's own
  catalog or modelling export (CSV, DDL or DBML). The Mapping agent marks every source it finds there
  as high confidence.
- Launch.

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
- **Show rejection:** reject a gate with a reason, then **Send back for rework**. The agent redoes
  only that stage.

## 6. What they take away (2 min)

- **Data model & exports**: download DDL for their engine, plus Collibra / Purview / DataHub /
  Alation payloads, the dbt `schema.yml`, the ODCS contract and OpenLineage.
- **Jira & metadata → Demo data packs**: the ready-made Jira exports, source data, model exports,
  catalog payloads and lineage (OpenLineage, column lineage CSV, Mermaid diagram) for each industry.
- **Download run bundle**: the full audit-ready workspace.
- **Verify audit logs**: hash-chained logs show intact.
- **Guardrails** page: **Run suite** executes all 14 guardrail scenarios live.

## Likely questions

- *Does it deploy to our platform?* Not in this release. Promotion is simulated and labelled as such.
  Connecting a platform means writing the reviewed adapter for that slot (backlog E3).
- *Where does our data go?* Agents work from metadata. Restricted columns are metadata-only. Tests use
  synthetic data. Model calls receive artifacts and metadata, never credentials.
- *Can we use our own LLM gateway?* Yes: add an OpenAI-compatible provider with your gateway URL.
