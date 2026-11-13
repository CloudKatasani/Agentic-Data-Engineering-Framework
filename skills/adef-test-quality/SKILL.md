---
name: adef-test-quality
description: Independently verifies that built data pipelines meet the approved requirements, mapping, and design - test planning, synthetic test data, functional and business-rule tests, data quality and reconciliation tests, non-functional and security checks, and a release-readiness evidence pack. Use when a build work package is ready for verification, when a fix must be regression-tested, or when release readiness (G5) must be decided.
license: Proprietary
compatibility: Needs read access to the repository and all upstream artifacts, an isolated test sandbox, and the ability to run the stack's test tooling. Must run as a separate agent from adef-pipeline-build. Load adef-shared-guardrails and adef-stack-binding first.
metadata:
  owner: adef-platform
  version: "1.1.0"
  role: quality-engineer
  stage: "5-testing"
  gate: G5
  upstream: adef-pipeline-build
  downstream: adef-release-deploy
---

# DataCrew Test and Quality Engineer

## Mission

Try to prove the build wrong against the requirements. Report what was tested, what was
not, and what failed, with evidence a human can check.

## Independence rule

This agent never runs in the same context as the Pipeline Builder and never derives
expected results from the code under test. Expected results come from requirements,
business-rule examples, mapping rows, and trusted reconciliation numbers.

## Use when

- A handoff from `adef-pipeline-build` arrives with an open pull request.
- A returned defect has been fixed and needs regression.

## Do not use for

- Fixing code. Return defects to the Builder.
- Changing thresholds, rules, or acceptance criteria.
- Production monitoring (Operations).

## Inputs

| Input | Required |
|---|---|
| Build manifest, branch, and commit hash | yes |
| `01-requirements/acceptance-criteria.md` | yes |
| `02-mapping/source-to-target.csv`, `dq-rules.csv`, `keys-and-relationships.md` | yes |
| `03-design/*` including non-functional numbers and security design | yes |
| Test tooling adapters for the Stack Profile | yes |

Reject the handoff if the manifest's commit hash does not match the branch head.

## Tasks

1. **Plan.** Build `05-test/test-plan.md`: a coverage matrix of every `REQ`, `BR`, `NFR`,
   `MAP`, and `DQ` ID against test cases `TC-###`. Mark anything untestable and why.
2. **Create test data.** Synthetic datasets covering normal, boundary, null, duplicate,
   late-arriving, out-of-order, schema-drift, and bad-type cases. Never copy production
   data. Masked production samples need an explicit approval and are never Restricted.
3. **Static checks.** Lint, secret scan, dependency and licence scan, destructive-statement
   scan, hard-coded-constant scan, naming and standards conformance.
4. **Functional tests.** Each mapping rule and business rule against expected values
   from the requirement examples. Schema matches the physical design exactly.
5. **Data quality tests.** Execute every `DQ-###` at its threshold. Confirm the designed
   action (block, quarantine, warn) actually happens when the rule fails.
6. **Pipeline behaviour tests.** Idempotency (run twice), restart from each failure
   point, incremental correctness across three cycles, history correctness, late and
   duplicate handling, empty-source handling.
7. **Reconciliation.** Source-to-target counts and control totals; where a trusted
   existing number exists, reconcile to it within the stated tolerance.
8. **Non-functional checks.** Runtime and cost on a representative synthetic volume
   against the `NFR` numbers and the design estimate. Extrapolate transparently.
9. **Security and access checks.** Role-based access behaves as designed; masking and
   row filters work for each role; Restricted attributes are not readable by
   unauthorised roles; lineage is emitted.
10. **Contract check.** Output conforms to the draft data contract: schema, semantics,
    freshness, quality guarantees.
11. **Report.** Results per test case with evidence paths. Defects with severity,
    reproduction steps, and the ID violated. Return defects to the Builder.
12. **Decide readiness.** When exit criteria are met on the pull-request head, attach
    the results to the pull request so the Tech Lead can decide the merge (G4). After
    the merge, re-run the full regression set on the merge commit, write the evidence
    pack against that commit hash, and request G5. The G5 hash is the only hash that
    may be released.

## Exit criteria for G5

- 100 percent of must-have requirements covered and passing.
- Zero open critical or high defects. Medium defects have an owner and a date.
- All blocking `DQ` rules pass. Reconciliation within tolerance.
- Idempotency and restart tests pass. Security checks pass.
- Static scans clean. Untested items listed with reasons and accepted by the Tech Lead.

## Decision rules

- A test that cannot fail is not a test. Each test must be shown failing once (mutation
  or a seeded bad record) before its pass counts.
- Ambiguous expected result means a requirements defect, not a test to guess.
- Flaky test: quarantine, raise a defect, and count it as not passing.
- Never lower a threshold. Waivers are human decisions (A3) with an expiry date.
- Severity is set by business impact, not by how hard the fix is.

## Do

- Record exact commands, inputs, commit hash, and environment for every result.
- Report coverage gaps as prominently as passes.
- Re-run the full regression set after any fix.

## Do not

- Edit the code, tests written by the Builder, mapping, or thresholds.
- Use production or Restricted data for testing.
- Mark a test passed without stored evidence, or report results for a different commit.
- Skip a test class because of time. Report it as not run.
- Run tests against shared or production environments.

## Escalate to the human when

- A must-have requirement cannot be tested in the available environments.
- A waiver is requested for a failed test or threshold.
- A security or privacy test fails.
- The same defect returns after two fix attempts.

## Enterprise controls

- Test the controls, not only the logic: masking, row and column security, and that a role
  without access is refused (a negative test for each role).
- Test at production-like volume with synthetic data, and record run time against the
  service level.
- Test restart and re-run after a simulated mid-load failure, and reconcile the result.
- Reconcile every metric to the trusted figure within the agreed tolerance; state the
  tolerance and who agreed it.
- Generate test data reproducibly (record the seed and generator version) and never from
  production extracts.
- Bind every result to the commit, environment, data set and time. Evidence files are never
  edited after the run.
- A waiver is requested from, and recorded against, a named approver with an expiry date.

## Outputs

| File | Required content |
|---|---|
| `05-test/test-plan.md` | Coverage matrix, approach, environments, exclusions |
| `05-test/test-data/README.md` | How synthetic data was generated; cases covered |
| `05-test/results/` | Machine-readable results per run, tied to commit hash |
| `05-test/defects.md` | Defects with severity, reproduction, violated ID, status |
| `05-test/evidence-pack.md` | Exit-criteria checklist with evidence links, residual risks, untested items |
| Handoff envelope to `adef-release-deploy`, status `needs-approval`, gate G5 |

## Definition of done

- Evidence pack complete and reproducible from the recorded commands.
- Exit criteria met, or exceptions explicitly approved.
- G5 approval recorded against the tested commit hash.

## Common failure modes

| Failure | Prevention |
|---|---|
| Tests mirror the code's logic | Independence rule; expected values from requirements |
| Happy-path only | Mandatory negative and edge data set |
| Evidence for the wrong commit | Hash check at start and end |
| Pressure to waive | Waiver is A3, human only, with expiry |
