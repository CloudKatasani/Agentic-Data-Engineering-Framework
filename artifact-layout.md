# Run Workspace Layout

One run delivers one use case for one client. Runs never share a workspace.

```
runs/<run_id>/
├── control/
│   ├── run.yaml               # scope, client, named approvers, budget, limits
│   ├── stack-profile.yaml     # active technology bindings (see adpe-stack-binding)
│   ├── domain-pack.yaml       # active industry pack
│   ├── decision-log.md        # append-only
│   ├── approvals.jsonl        # append-only
│   ├── action-log.jsonl       # every A2 and A3 action, before and after
│   └── handoffs/              # handoff envelopes
├── 00-intake/                 # owner: adpe-orchestrator
├── 01-requirements/           # owner: adpe-intent-requirements
├── 02-mapping/                # owner: adpe-source-target-mapping
├── 03-design/                 # owner: adpe-solution-design
│   ├── logical/               # technology-neutral
│   └── physical/              # bound to the Stack Profile
├── 04-build/                  # owner: adpe-pipeline-build (pointer to repo branch + manifest)
├── 05-test/                   # owner: adpe-test-quality
├── 06-release/                # owner: adpe-release-deploy
├── 07-operations/             # owner: adpe-operations-observability
├── 08-consumption/            # owner: adpe-data-consumption
└── final/                     # assembled delivery pack (owner: adpe-orchestrator)
```

## Rules

- An agent writes only inside its own stage folder and appends to `control/` logs.
- Files under `logical/`, `01-requirements/`, and `02-mapping/` contain no vendor or
  product names and no dialect-specific syntax.
- Code lives in version control, not in the run workspace. `04-build/` holds the branch
  name, commit hash, and build manifest.
- No secrets, no restricted data values, no client data extracts anywhere in the workspace.
- File names are lowercase-kebab-case. IDs are stable: `REQ-###`, `BR-###`, `MAP-###`,
  `ADR-###`, `DQ-###`, `TC-###`, `REL-###`, `INC-###`.

## `control/run.yaml` minimum content

```yaml
run_id: RUN-2026-001
client_code: CLIENT-A            # isolation boundary
use_case: "one sentence"
domain_pack: utilities
stack_profile: stack-profile.yaml
approvers:
  product_owner: "<name>"
  data_architect: "<name>"
  data_steward: "<name>"
  tech_lead: "<name>"
  release_manager: "<name>"
  platform_owner: "<name>"
  security_compliance: "<name>"
budget:
  compute_cost_cap: 0            # currency units; 0 means every paid action needs approval
  max_stage_loops: 3
  max_run_days: 10
limits:
  profiling_row_cap: 10000
  query_timeout_seconds: 120
```
