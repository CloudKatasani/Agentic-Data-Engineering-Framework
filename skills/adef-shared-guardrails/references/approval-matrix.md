# Approval Matrix

Approver roles are bound to named people in `control/run.yaml` at gate G0. In a
one-person setup the same person may hold several roles, but an agent never holds one.

## Roles

| Role | Accountable for |
|---|---|
| Product Owner | Business intent, scope, acceptance criteria, publication |
| Data Architect | Logical and physical design, standards, stack choices |
| Data Steward | Classification, mappings of governed attributes, quality rules, glossary |
| Tech Lead | Code, tests, merge |
| Release Manager | Environment promotion, change windows, rollback |
| Platform Owner | Production operations, cost, access |
| Security and Compliance | Restricted data, access changes, regulatory controls |

## Gate approvers

| Gate | Required approver | Also required when |
|---|---|---|
| G0 Intake | Product Owner + Data Architect | Platform Owner if a budget is set |
| G1 Requirements | Product Owner | Data Steward if governed data is in scope |
| G2 Mapping | Data Steward | Product Owner if business rules changed |
| G3 Design | Data Architect | Security and Compliance if Restricted data or new access paths; Platform Owner if the cost estimate exceeds budget |
| G4 Merge | Tech Lead | - |
| G5 Release readiness | Tech Lead + Product Owner (acceptance tests) | Data Steward if quality thresholds were waived |
| G6a Shared environment | Release Manager | - |
| G6b Production | Release Manager + Platform Owner | Security and Compliance for Restricted data |
| G7 Operational change | Platform Owner | Release Manager if it is a redeploy |
| G8 Publication | Product Owner + Data Steward | Security and Compliance if consumers are outside the owning domain |

## Per-action approvals (A3)

These always need their own approval, even inside an approved gate:

| Action | Approver | Must be attached |
|---|---|---|
| Drop, truncate, overwrite, or delete of any persisted object or file | Platform Owner | Object list, backup or time-travel reference, restore steps |
| Backfill or reprocess of history | Platform Owner | Row and cost estimate, window, idempotency proof |
| Grant, revoke, role or policy change | Security and Compliance | Before and after access diff |
| Breaking schema or contract change | Data Architect + affected consumer owners | Impact list from lineage, migration plan |
| Spend above the run budget, new paid resource, resize | Platform Owner | Estimate, duration, auto-suspend or teardown plan |
| Send or publish outside the team (email, chat, share, listing, export) | Product Owner | Exact content and recipient list |
| Waiver of a failed test or quality threshold | Tech Lead + Data Steward | Failing evidence, risk, expiry date of waiver |

## Approval record

One JSON line per decision in `control/approvals.jsonl`:

```json
{"approval_id":"APR-0007","run_id":"RUN-2026-001","gate":"G3","action_class":"A2",
 "subject":"03-design/physical-design.md","artifact_sha256":"<hash>",
 "decision":"approved","approver":"<name>","role":"Data Architect",
 "conditions":["cap compute at size S"],"expires":"2026-12-01","timestamp":"<iso8601>"}
```

Rules:

- `decision` is `approved`, `rejected`, or `approved-with-conditions`. Conditions become
  binding constraints for downstream stages.
- An approval covers one artifact hash. Any edit invalidates it.
- Approvals expire. Default 14 days for gates, 24 hours for A3 actions.
- Agents append requests; only the approval channel appends decisions.
