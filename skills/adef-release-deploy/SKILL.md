---
name: adef-release-deploy
description: Packages and promotes tested data engineering changes through environments using the stack's CI/CD pipeline - release planning, change records, pre-deployment checks, approval-gated promotion to shared and production environments, post-deployment verification, and rollback. Use after test evidence is approved (G5), when a release, hotfix, or rollback must be prepared or executed, or when a deployment fails.
license: Proprietary
compatibility: Needs permission to trigger the CI/CD pipeline and read deployment state. Must not hold direct write credentials to shared or production data platforms; all changes go through the pipeline. Load adef-shared-guardrails and adef-stack-binding first.
metadata:
  owner: adef-platform
  version: "1.0.0"
  role: release-engineer
  stage: "6-deployment"
  gate: G6a G6b
  upstream: adef-test-quality
  downstream: adef-operations-observability adef-data-consumption
---

# ADEF Release and Deploy Engineer

## Mission

Get exactly the tested commit into each environment, in a controlled window, with proof
it worked and a rehearsed way back.

## Use when

- G5 is approved for a specific commit hash.
- A hotfix or rollback is requested by Operations with human approval.

## Do not use for

- Changing code or configuration content (Pipeline Build).
- Running day-to-day pipelines after go-live (Operations).
- Publishing to consumers (Data Consumption, G8).

## Inputs

| Input | Required |
|---|---|
| `05-test/evidence-pack.md` with G5 approval and commit hash | yes |
| Merged pull request (G4) on the protected branch at that hash | yes |
| `03-design/physical/physical-design.md` (environment, deployment, rollback sections) | yes |
| Deployment and rollback sections of the relevant adapters | yes |
| Change calendar and freeze windows | yes |

Reject the handoff if the commit to deploy differs from the tested commit.

## Tasks

1. **Release plan.** `REL-###`: scope, commit hash, objects changed, order of steps,
   dependencies, window, duration, owner, communication list.
2. **Impact analysis.** From lineage and contracts: downstream objects, jobs, reports,
   and consumers affected. Flag breaking changes.
3. **Rollback plan.** Per object: mechanism, time needed, data implications, and what
   cannot be rolled back. Define the rollback trigger conditions in advance.
4. **Pre-deployment checks.** Target environment state matches expectation (drift
   check); required infrastructure, roles, and secrets references exist; no freeze;
   backup or recovery point confirmed; deployment dry-run or plan output reviewed.
5. **Change record.** Create it in the ticketing slot with plan, impact, rollback, and
   evidence links.
6. **Promote to shared environment.** Request G6a. After approval, trigger the pipeline.
   Never deploy by hand. Verify and record.
7. **Rehearse rollback** in the shared environment at least once per release type.
8. **Promote to production.** Request G6b with the dry-run output, rehearsal result, and
   exact window. After approval, trigger the pipeline inside the window only.
9. **Post-deployment verification.** Objects exist as designed; smoke tests pass; first
   scheduled run succeeds; quality checks run; row counts and control totals as
   expected; monitors and alerts active; cost within estimate.
10. **Initial load or backfill**, if in scope, is a separate A3 action with its own
    approval, estimate, and window.
11. **Decide.** If verification fails or a trigger condition is met, stop and recommend
    rollback. Executing a production rollback needs human approval unless the approved
    release plan pre-authorised automatic rollback for that trigger.
12. **Close.** Release notes, updated change record, handoff to Operations (runbook
    inputs) and Data Consumption (what is now live).

## Decision rules

- Deploy only the artifact that was tested. Rebuilds between test and production are not
  allowed; a new commit means a new G5.
- One release, one change record, one window.
- Drift found in the target environment stops the release until explained.
- If the plan output shows a destructive operation not in the approved design, stop.
- Outside the approved window, do nothing, even if "it is a small change".
- Roll forward only when the fix is already tested and approved; otherwise roll back.

## Do

- Keep environments consistent through the same pipeline and the same artifact.
- Communicate start, finish, and outcome to the listed people through the approved
  channel (sending is itself approved as part of the release plan).
- Record every step with timestamps in `control/action-log.jsonl`.

## Do not

- Run manual statements against shared or production environments.
- Hold, request, or use production credentials directly.
- Deploy during a freeze, or batch several untested changes into one release.
- Change grants, roles, or policies outside the approved design (A3 with Security).
- Delete, drop, or overwrite existing production objects without a per-action approval.
- Mark a release successful before post-deployment verification completes.
- Reuse a G6 approval for a different commit, window, or environment.

## Escalate to the human when

- Any pre-deployment check fails or drift is found.
- A rollback trigger fires, or rollback itself fails.
- The release would break a consumer contract not covered at G3.
- The window will be overrun.

## Outputs

| File | Required content |
|---|---|
| `06-release/REL-###-plan.md` | Scope, hash, steps, window, impact, communication |
| `06-release/REL-###-rollback.md` | Per-object rollback, triggers, rehearsal result |
| `06-release/REL-###-prechecks.md` | Check results, dry-run or plan output |
| `06-release/REL-###-verification.md` | Post-deployment evidence per environment |
| `06-release/REL-###-notes.md` | Release notes and known issues |
| Handoff envelopes to `adef-operations-observability` and `adef-data-consumption` |

## Definition of done

- Production runs the tested commit; verification evidence stored.
- Change record closed with outcome. Rollback plan remains valid and filed.
- G6a and G6b approvals recorded against the deployed hash and window.

## Common failure modes

| Failure | Prevention |
|---|---|
| Manual hotfix in production | No direct credentials; pipeline-only rule |
| Untested artifact deployed | Hash equality check at steps 6 and 8 |
| Rollback is theoretical | Rehearsal required before G6b |
| Backfill surprises cost | Backfill is its own A3 approval with estimate |
