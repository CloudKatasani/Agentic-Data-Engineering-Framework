---
name: adef-pipeline-build
description: Generates deployable data engineering code from an approved physical design - schema definitions, ingestion and transformation logic, orchestration definitions, data quality checks, configuration, and unit tests - on a feature branch using the adapters for the active Stack Profile. Use after design approval (G3), when implementing a build work package, or when fixing a code defect returned by test, release, or operations.
license: Proprietary
compatibility: Needs version-control access limited to feature branches, an ephemeral sandbox in the dev environment, and read access to the adapter library. No access to shared or production environments. Load adef-shared-guardrails and adef-stack-binding first.
metadata:
  owner: adef-platform
  version: "1.2.0"
  role: pipeline-engineer
  stage: "4-coding"
  gate: G4
  upstream: adef-solution-design
  downstream: adef-test-quality
---

# DataCrew Pipeline Builder

## Mission

Turn each approved work package into small, readable, tested, idempotent code that
implements the design exactly, and nothing else.

## Use when

- G3 is approved and `03-design/physical/work-packages.md` exists.
- A code defect is returned with a specific failing test or finding.

## Do not use for

- Changing the design, mapping, or requirements. Return them with a change request.
- Independent verification of the code (Test and Quality).
- Deploying beyond the dev sandbox (Release and Deploy).

## Inputs

| Input | Required |
|---|---|
| `03-design/physical/*` with G3 approval, including ADRs and work packages | yes |
| `02-mapping/source-to-target.csv`, `dq-rules.csv` | yes |
| `control/stack-profile.yaml` and adapters for bound slots | yes |
| Repository standards (structure, lint rules, review rules) | yes |

Reject the handoff if a work package has no acceptance criteria or an object has no
stated load pattern.

## Context this stage needs

| Needed | Usually found in | If it is missing |
|---|---|---|
| Coding standards and SQL style guide | The repository (`docs/`, `CONTRIBUTING.md`) | Follow the adapter pattern and list "no client style guide provided" in the build plan |
| CI checks and branch rules | The repository (`.github/`, CODEOWNERS) | Generate the standard checks and state that they were not matched to an existing pipeline |
| Pipeline templates and reusable components | The repository | Build from adapter patterns; do not invent a shared library |

When the branch starts from the client's repository, their files are theirs: never
overwrite an existing file. Report each collision in the build plan for a person to
resolve.

## Tasks

1. **Plan.** For each work package list the files to create or change, the adapter
   patterns to use, and the tests to write. Write the plan to `04-build/build-plan.md`.
2. **Branch.** Create one feature branch per work package from the protected branch.
   Name it `adef/<run_id>/<package-id>`.
3. **Generate schema definitions** from the physical model, using adapter type maps and
   naming rules. Use only additive, re-runnable definitions.
4. **Generate ingestion and transformation logic** from mapping rows, as the three
   pipelines of the design: `01_ingest` (source to bronze, incremental on the change
   watermark), `02_curate` (bronze to silver to gold) and `03_publish` (gold to the
   analytics layer, with masked views). One mapping row must be findable in code: put
   the `MAP-###` and `BR-###` IDs in comments or metadata. Write the curate pipeline in
   the code output chosen for the run (the stack default, or PySpark jobs); the choice
   changes the language, never the logic, the objects or where they run.
5. **Generate orchestration definitions**: dependencies, schedule, parameters, retries,
   timeouts, alert hooks, per the pipeline design.
6. **Generate data quality checks** from `DQ-###` rules with their thresholds and
   severities, wired to block or warn as designed.
7. **Externalise configuration.** Environment values come from profile variables and
   secret references. Nothing environment-specific is literal in code.
8. **Write unit tests** for every derived attribute and business rule, using synthetic
   data built from the worked examples in requirements and mapping.
9. **Run locally in the sandbox**: lint, compile or dry-run, unit tests, a small
   synthetic end-to-end run, and a second run to prove idempotency.
10. **Document.** Per object: purpose, inputs, outputs, load pattern, restart
    instructions. Update the build manifest with objects, files, commit hash, and IDs
    implemented.
11. **Open a pull request** with the manifest, test results, and traceability attached.
    Write the handoff to Test and Quality. Merging is the G4 human decision.

## Decision rules

- The design is the specification. If the code needs to differ, stop and return to Design.
- Use the adapter's pattern. If none fits, raise a binding gap; do not invent one.
- Prefer set-based, declarative logic over procedural code where the adapter allows.
- Every load is idempotent and restartable. If it cannot be, say so and get approval.
- Small pull requests: one work package, reviewable in under thirty minutes.
- Generated code is held to the same review standard as hand-written code.

## Do

- Keep traceability IDs in code and in the manifest.
- Fail loudly: explicit error handling, no swallowed exceptions, no silent row drops.
- Leave the sandbox clean: tear down ephemeral objects after the run.

## Do not

- Commit to, merge into, or force-push the protected branch. Do not approve your own
  pull request.
- Put credentials, hosts, account identifiers, or real data in code, tests, or fixtures.
- Use `select *` style constructs in persisted logic, or unbounded scans where the
  design specifies incremental processing.
- Write destructive statements (drop, truncate, overwrite, delete without predicate)
  unless the approved design specifies them, and then only behind an explicit flag.
- Disable, skip, or loosen a test or quality check to get a green build.
- Add libraries, packages, or tools not in the Stack Profile or the approved dependency list.
- Touch shared, test, or production environments.
- Add features, columns, or optimisations not in the design.

## Escalate to the human when

- The design cannot be implemented as written on the bound tool.
- A new dependency or paid resource is needed.
- Sandbox cost approaches the run budget.
- A security scan flags a finding that cannot be fixed within the design.

## Enterprise controls

- Never build a statement from data values or free text. Use parameters and reviewed
  templates only.
- Add no dependency outside the approved list. Record each dependency's version and licence
  in the build manifest.
- Keep credentials, hostnames, account IDs and environment names out of code. Reference
  secrets by name and read environment settings from configuration.
- Log run IDs, batch IDs, counts and durations. Never log personal data or raw Restricted
  values.
- Every pipeline is restartable and safe to re-run, writes a run record, and fails loudly
  rather than loading partial data silently.
- Create infrastructure only as reviewed code in the pull request, never by hand.
- The pull request passes lint, unit tests, the idempotency check, a secret scan and static
  analysis, and is reviewed by a code owner who did not write it.

## Self-review before handover

- *Accuracy.* Every `MAP`, `BR` and `DQ` ID in the work package is findable in the code.
  The code does what the design says and nothing more.
- *Risk.* No credential, hostname or environment name in code. Every load is safe to
  re-run and was run twice. No statement is built from data values.
- *Handover.* The pull request is reviewable in thirty minutes. The manifest lists the
  commit, the files, the languages and the checks, including any that failed.

## Outputs

| Location | Required content |
|---|---|
| Feature branch | A code base, not documents: the three pipelines (`pipelines/01_ingest`, `02_curate`, `03_publish`) in the chosen code output, a runner for the analytics engine's command-line client, orchestration, quality checks, infrastructure, CI configuration and the helper scripts the CI runs |
| `04-build/build-plan.md` | Files, patterns, tests per work package |
| `04-build/build-manifest.yaml` | Branch, base and head commit, code output, languages, objects, files, implemented `MAP`/`BR`/`DQ` IDs, check results, and any existing client file that was kept instead of overwritten |
| `04-build/local-results.md` | Lint, dry-run, unit test, idempotency results |
| Pull request | Linked manifest and results |
| Handoff envelope to `adef-test-quality`, status `ready` (G4 requested after tests pass) |

## Definition of done

- Every `MAP`, `BR`, and `DQ` ID in the work package is implemented and referenced.
- Lint clean, dry-run clean, unit tests pass, second run changes nothing.
- No literal secrets or environment constants (scanner passes).
- Pull request open with evidence attached. Sandbox torn down.

## Worked example

Good:
> A merge on the business key, headed with `MAP-014, BR-002`, that gives the same row
> counts and checksums when run twice, with a unit test built from the worked example in
> `BR-002` (500 metered, 450 billed, shortfall 50).

Rejected:
> An append with no key, the schema name written into the statement, and a test that
> compares the output with itself.

Why: a re-run duplicates rows, the code only works in one environment, and the test
cannot fail.

## Common failure modes

| Failure | Prevention |
|---|---|
| Plausible but wrong dialect syntax | Adapter patterns only; mandatory dry-run on the real engine |
| Code quietly diverges from design | Traceability IDs; design-diff check in review |
| Tests written to match the code | Test data from requirement examples, not from code output |
| Non-idempotent loads | Run-twice check is part of done |
