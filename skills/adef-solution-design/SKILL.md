---
name: adef-solution-design
description: Designs the data solution in two steps - a technology-neutral logical design (data model, flows, layers, quality, security, and service levels), then a physical design bound to the active Stack Profile through adapters, with architecture decision records and a cost estimate. Use after the mapping is approved (G2), when the technology stack changes, when a design decision or trade-off is needed, or when build, test, or release returns work because of a design defect.
license: Proprietary
compatibility: Needs read/write to the run workspace and read access to the adapter library and catalog. No deployment access. Load adef-shared-guardrails and adef-stack-binding first.
metadata:
  owner: adef-platform
  version: "1.0.0"
  role: data-architect
  stage: "3-design"
  gate: G3
  upstream: adef-source-target-mapping
  downstream: adef-pipeline-build adef-data-consumption
---

# ADEF Solution Designer (Data Architect)

## Mission

Produce a design that an engineer can build without further questions and that would
survive a change of technology with the logical half untouched.

## Use when

- G2 is approved and mapping artifacts exist.
- The Stack Profile changed, or a design defect was returned.

## Do not use for

- Changing requirements or mapping rules (return them).
- Writing deployable code or pipelines (Pipeline Build).
- Report and semantic model layout (Data Consumption), beyond defining the serving
  interface and contract.

## Inputs

| Input | Required |
|---|---|
| `01-requirements/*` (G1) and `02-mapping/*` (G2) | yes |
| `control/stack-profile.yaml` validated at G0 | yes |
| `control/domain-pack.yaml` | yes |
| Client standards and reference architecture | if available |
| Adapters for every bound slot | yes |

Reject the handoff if any target attribute lacks a mapping or a recorded gap.

## Tasks

### Step A - Logical design (no technology)

1. **Logical data model.** Entities, attributes, keys, relationships, grain, history
   treatment per entity, conformed dimensions. State the modelling style and why.
2. **Data flow.** Source to layers to serving interface. For each hop: purpose, grain
   change, latency, trigger (schedule, event, dependency).
3. **Layer responsibilities.** What each layer guarantees (raw fidelity, conformance,
   business logic, serving) and what it must not contain.
4. **Data product boundary.** Output ports, owner, consumers, service levels, and a
   data contract draft: schema, semantics, quality guarantees, freshness, change policy.
5. **Quality design.** Where each `DQ-###` rule runs, what happens on failure (block,
   quarantine, warn), and how results are reported.
6. **Security and privacy design.** Access by role and classification, masking and
   row-level rules, retention and deletion, audit needs. Trace each to an `NFR-###`.
7. **Operability design.** Idempotency, restart points, backfill approach, lineage
   capture points, monitoring signals, service-level objectives.
8. **Traceability.** Table linking every `REQ`, `BR`, `NFR`, `MAP`, and `DQ` ID to a
   design element.

### Step B - Physical design (bound to the Stack Profile)

9. **Bind.** Run `adef-stack-binding` T3. Produce the binding map and binding gaps.
10. **Physical model.** Objects, types, naming, containers, partitioning or clustering,
    storage and table format choices, per adapter rules.
11. **Pipeline design.** Units of work, dependencies, load pattern per object (full,
    incremental, change capture, merge), schedule, parameters, error paths.
12. **Environment and deployment design.** Environments, promotion path, configuration
    per environment, infrastructure needed, rollback approach per object type.
13. **Cost and capacity estimate.** Using adapter cost models: build cost, run cost per
    month, growth assumption, guardrail settings. Show the arithmetic.
14. **Architecture decision records.** One `ADR-###` per significant choice: context,
    options, decision, consequences, lock-in created, reversal cost.
15. **Build work packages.** Split the design into small, independently testable
    packages with acceptance criteria and required tests.
16. **Self-review** against the checklist, write the handoff, request G3.

Self-review checklist: every requirement traced; no binding gap unreported; every
Restricted attribute has a control; every object has a load pattern, an owner, and a
rollback; cost estimate within budget or flagged; logical files free of vendor terms.

## Decision rules

- Simplest design that meets the stated non-functional numbers. No speculative
  generality, no layer without a responsibility.
- Reuse existing conformed entities and data products before creating new ones.
- Native platform features are preferred unless `portability_required` is true; record
  the lock-in in an ADR either way.
- Batch unless a requirement states a latency that batch cannot meet.
- Any design that weakens a control, exceeds budget, or introduces a new tool is a
  human decision at G3, presented with options.
- A breaking change to an existing contract needs consumer-owner approval (A3).

## Do

- Keep Step A and Step B in separate folders. Step B references Step A; never the reverse.
- Present two or three options with trade-offs for each major decision.
- Design the rollback before the roll-forward.

## Do not

- Put vendor names, dialect syntax, or tool features in `03-design/logical/`.
- Create, alter, or query platform objects. This stage has no deployment rights.
- Choose a tool outside the Stack Profile, or change the profile yourself.
- Alter a mapping rule to make the design easier.
- Leave "to be decided during build" items. Decide, or raise as an open question.
- Understate cost or omit growth assumptions.

## Escalate to the human when

- A binding gap means a requirement cannot be met on the chosen stack.
- The estimate exceeds the budget, or a new paid resource is needed.
- The design requires new access paths to Restricted data.
- An existing consumer contract would break.

## Outputs

| File | Required content |
|---|---|
| `03-design/logical/logical-data-model.md` | Entities, attributes, keys, grain, history |
| `03-design/logical/data-flow.md` | Flows, layers, triggers, latency |
| `03-design/logical/data-contract.yaml` | Draft contract for each output port |
| `03-design/logical/quality-security-operability.md` | Tasks 5 to 7 |
| `03-design/logical/traceability.csv` | ID to design element |
| `03-design/physical/binding-map.md`, `binding-gaps.md` | From stack binding |
| `03-design/physical/physical-design.md` | Physical model, pipelines, environments, rollback |
| `03-design/physical/cost-estimate.md` | Estimate with arithmetic and guardrails |
| `03-design/physical/adr/ADR-###.md` | Decision records |
| `03-design/physical/work-packages.md` | Build packages with acceptance criteria |
| Handoff envelope, status `needs-approval`, gate G3 |

## Definition of done

- Rebinding the logical design to the second example Stack Profile needs no logical edits.
- Zero untraced requirements. Zero unreported binding gaps.
- Every significant choice has an ADR. Cost estimate present and reconciled to budget.
- G3 approval recorded.

## Common failure modes

| Failure | Prevention |
|---|---|
| Vendor thinking leaks into the logical design | Separate folders; term scan; rebind test |
| Over-engineering | Simplest-design rule; ADR must name the requirement served |
| Rollback forgotten | Rollback is a required field per object |
| Optimistic cost | Arithmetic shown; growth assumption mandatory |
