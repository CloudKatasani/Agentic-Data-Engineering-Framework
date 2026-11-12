# Adapter Contract

An adapter is one Markdown file that teaches agents how one tool, at one major version,
fulfils one capability slot. Adapters are the only place tool-specific knowledge lives.

Location: `adapters/<slot>/<tool>-<major-version>.md`

Build adapters only for the stack you are launching with. Add the next one when a real
engagement needs it.

## Required sections

```markdown
---
adapter: <tool>
slot: <capability slot>
tool_version: "<tested version range>"
adapter_version: "1.0.0"
works_with: [<slot>:<tool>, ...]      # compatible bindings in other slots
reviewed_by: "<Data Architect>"
reviewed_on: "<date>"
sources: [<vendor documentation URLs for the stated version>]
---

## 1. Capabilities
What this tool can and cannot do for this slot. State hard limits.

## 2. Logical-to-physical map
- Type map: logical type -> physical type, with precision and timezone rules.
- Naming: case, length limits, reserved words, layer prefixes, environment variables.
- Structure: how layers, domains, and data products map to containers
  (databases, schemas, catalogs, workspaces, folders).

## 3. Patterns
For each, give when to use it, a minimal template, and its trade-offs:
full load, incremental, change data capture, history (type 2), late-arriving data,
deduplication, merge/upsert, partitioning or clustering, schema evolution.

## 4. Access and governance
Role model, least-privilege grants, masking and row-level controls, tagging or
classification hooks, lineage emission.

## 5. Quality and testing
How unit, data-quality, and reconciliation tests are expressed and run. How results
are exported as evidence.

## 6. Deployment and rollback
Deployable unit, promotion mechanism, state handling, idempotency, zero-downtime
options, exact rollback mechanism and its limits (what cannot be rolled back).

## 7. Operations
Telemetry sources, key health metrics, common failure signatures, safe restart rules.

## 8. Cost model
What drives cost, how to estimate before running, guardrail settings
(auto-suspend, timeouts, quotas, budgets).

## 9. Agent tool permissions
Which tool commands or APIs are A0, A1, A2, A3 for this tool. List anything destructive
explicitly. Default for unlisted commands is A3.

## 10. Known pitfalls
Version-specific behaviour, anti-patterns, things agents commonly get wrong.
```

## Rules for adapter authors

- Every factual claim cites vendor documentation for the stated version. No citation,
  no claim.
- Section 9 is mandatory. An adapter without an explicit destructive-command list is
  rejected.
- Keep each adapter under about 300 lines. Split by slot, not by tool.
- No client names, account identifiers, or credentials.

## Conformance test (before first use)

1. Bind the reference logical model (one fact, two dimensions, one history table, one
   incremental feed) using only the adapter.
2. Generated code deploys to a sandbox and passes the standard test suite.
3. Rollback is executed once and verified.
4. Cost estimate is within 30 percent of actual sandbox cost.

Record results in `adapters/<slot>/<tool>-<major-version>.conformance.md`.
