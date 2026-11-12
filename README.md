# ADPE - Agentic Data Engineering Framework

An approval-gated team of nine AI agents that delivers a data product end to end:

**Business intent → Requirements → Mapping → Design → Build → Test → Release → Operations → Consumption**

This repository is the runtime for the ADPE specification pack (`skills/`, `agents/`, `docs/spec/`).
It adds an enterprise web console and API with:

- **Bring your own model, per agent.** Pick a provider and model for each of the nine agents:
  Anthropic (Claude), OpenAI, Azure OpenAI, Google Gemini, Amazon Bedrock, or any OpenAI-compatible
  endpoint (Ollama, vLLM, Mistral, Groq, LiteLLM, enterprise gateways). There is also an offline
  **Demo Simulator**, so a full lifecycle runs with no API key at all.
- **API keys handled properly.** Keys go into an encrypted vault and are referenced by name. They are
  never returned by the API, never written to run artifacts or logs, and never sent to a model.
- **Choose the technology stack.** Five reference Stack Profiles (Snowflake/dbt/Airflow on AWS,
  Databricks lakehouse on Azure, BigQuery/Dataform/Looker on GCP, Microsoft Fabric/Purview, and
  Redshift/Glue/Tableau), or build your own slot by slot with validation. The same logical design
  binds to any of them.
- **Jira integration.** Read epics and stories (Cloud or Data Center) by JQL and turn them into a
  traceable requirements baseline. A built-in demo Jira (projects UTIL, TEL, FIN, RET) works offline.
- **Data modelling and data catalog imports and exports.** Import CSV dictionaries, JSON models, DBML or
  DDL from modelling tools and catalogs. Export 16 formats: physical DDL in 7 dialects, DBML, Mermaid,
  PlantUML, dbt `schema.yml`, an ODCS data contract, a data dictionary, Collibra, Purview/Atlas,
  DataHub, Alation, a business glossary, Unity Catalog and Snowflake governance SQL, and OpenLineage.
- **Guardrails enforced in code, not just in prompts.** Action classes A0-A4, approvals bound to
  artifact hashes, one writer per folder, secret and prompt-injection scanning, hash-chained audit
  logs, and the 14 guardrail scenarios from the build spec, all executable.

## Quick start

```bash
make install
```

```bash
make run
```

Open http://127.0.0.1:8000, choose **New run**, accept the defaults, and launch. The Demo Simulator
produces the whole lifecycle. You approve each gate as the named approver.

A headless run that auto-approves every gate:

```bash
.venv/bin/python -m adpe demo --domain telco --stack gcp-bigquery
```

To run with Docker, put `ADPE_API_TOKEN` and `ADPE_MASTER_KEY` in `.env` first:

```bash
docker compose up --build
```

Tests (52, including the full lifecycle for 4 domains and stacks, all 14 guardrail scenarios, and the
live-LLM path):

```bash
make test
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

## Project layout

```
adpe/                 runtime (Python package)
  api/app.py          REST API + console host
  engine/             orchestrator, stage agents, codegen, SQLite sandbox, golden scenarios
  llm/                providers: anthropic SDK, OpenAI, Azure OpenAI, Gemini, Bedrock, OpenAI-compatible, simulator
  guardrails/         scanners, action-class hook, GT-01..14 suite
  workspace/          run workspace, approvals, hash-chained logs, handoff envelopes
  modeling/           logical model, physical binding, 16 exporters, importers
  connectors/jira.py  Jira Cloud / Data Center / demo
  catalog/            capability slots, Stack Profile presets, providers, Domain Packs
web/                  console (no build step, no external assets)
skills/ agents/       the specification pack (agent prompts and skills)
docs/spec/            original build spec and spec-pack archive
adapters/ evals/      adapter library (to be reviewed per client), evaluation notes
tests/                pytest suite
```

Run workspaces live under `$ADPE_HOME/runs/<run_id>/` (default `./data`) and follow
`skills/adpe-shared-guardrails/references/artifact-layout.md`. Each run also has a local git
repository (`repo/`) standing in for the client's version-control slot.

## Honest limits of this release

- **Deployments are simulated.** There is no connection to a client platform, so G6a/G6b promotion,
  verification and publication run against the in-memory sandbox and are labelled as simulated in
  every artifact. Connecting a platform means implementing the reviewed adapter for that slot (E3-2/E3-3).
- **Tests run on synthetic data in SQLite.** They are real executions with recorded SQL, but they do not
  replace platform tests on the bound engine.
- **Adapters still need review.** Built-in templates are flagged as such by stack validation until a
  reviewed adapter is added under `adapters/`.
- **Domain Packs are starters.** Their controls are not legal or compliance advice.
- **Single tenant.** One console per environment, file-based state, optional bearer-token auth
  (`ADPE_API_TOKEN`). Put it behind your SSO proxy for shared use.
