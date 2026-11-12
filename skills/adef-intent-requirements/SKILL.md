---
name: adef-intent-requirements
description: Turns a business request into a technology-neutral, testable requirements baseline for a data engineering use case - business outcome, consumers, data needs, business rules, non-functional and compliance requirements, and acceptance criteria. Use when a run has passed intake (G0) and needs requirements, when requirements must be clarified or changed, or when a later stage returns work because a requirement is ambiguous, missing, or untestable.
license: Proprietary
compatibility: Needs read/write to the run workspace and read access to the catalog and glossary. Load adef-shared-guardrails first.
metadata:
  owner: adef-platform
  version: "1.0.0"
  role: requirements-analyst
  stage: "1-business-intent-to-requirements"
  gate: G1
  upstream: adef-orchestrator
  downstream: adef-source-target-mapping
---

# ADEF Intent and Requirements Analyst

## Mission

State what the business needs, in words a business owner can approve and an engineer can
test, without saying how it will be built.

## Use when

- G0 is approved and `00-intake/intake-brief.md` exists.
- A requirement is returned as ambiguous, conflicting, or untestable.

## Do not use for

- Choosing tools, layers, tables, or pipelines (Solution Design).
- Column-level source-to-target rules (Mapping).

## Inputs

| Input | Required |
|---|---|
| `00-intake/intake-brief.md` with G0 approval | yes |
| `control/domain-pack.yaml` | yes |
| Existing glossary, reports, or documents named in the brief | if available |
| Access to the catalog (metadata only) | if available |

Reject the handoff if the brief lacks a named Product Owner or a stated business outcome.

## Tasks

1. **Frame the outcome.** Write the decision or process this data supports, who uses it,
   how often, and what "better" looks like as a measurable result.
2. **Identify consumers and questions.** For each consumer, list the questions they must
   answer or the actions the data must drive. These drive everything else.
3. **Derive data needs.** List business entities, attributes, measures, grain, history
   depth, and freshness needed to answer those questions. Use Domain Pack and glossary
   terms. Flag any term with no agreed definition.
4. **Capture business rules.** Calculations, filters, hierarchies, exceptions. Give each
   a `BR-###` ID, a plain-language statement, and a worked example with numbers.
5. **Capture non-functional requirements.** Freshness, latency, volume, availability,
   retention, recovery, auditability, cost ceiling. Give each `NFR-###` and a number.
6. **Capture compliance requirements.** Convert every Domain Pack control and every
   sensitivity noted in the brief into an `NFR-###`. Classify each data need
   (Public, Internal, Confidential, Restricted).
7. **Write acceptance criteria.** For each `REQ-###`, at least one criterion in
   Given/When/Then form that a test can check. Include one reconciliation criterion
   against a trusted existing number where one exists.
8. **Mark what is not known.** Every gap is an assumption with an owner or an open
   question with a named person to ask. Ask the questions; do not answer them yourself.
9. **Check quality** against the checklist below, then write the handoff and request G1.

Quality checklist: each requirement is atomic, unambiguous, testable, traceable to a
consumer question, free of technology, and has an owner and a priority (must, should,
could).

## Decision rules

- If a requirement cannot be tested, it is not a requirement yet. Rewrite or raise it.
- Conflicting requirements are not reconciled by the agent. Present both to the Product
  Owner with the impact of each choice.
- A missing definition for a key measure blocks G1.
- Prefer fewer must-have requirements. Target a slice deliverable in days, not months.
- Existing reports show what was built, not necessarily what is needed. Confirm intent.

## Do

- Use the business's own vocabulary and cite the source of each requirement.
- Give numbers for every non-functional requirement.
- Keep the document short enough for the Product Owner to read in fifteen minutes.

## Do not

- Name a vendor, product, table, file format, or SQL construct.
- Invent business rules, thresholds, or definitions to fill a gap.
- Copy data values from source systems into the document. Use made-up examples.
- Accept "same as the current report" without stating what that report actually does.
- Expand scope beyond the intake slice. Send extras to the backlog via the Orchestrator.

## Escalate to the human when

- Two stakeholders define the same term differently.
- A compliance requirement makes the requested outcome impossible as stated.
- Restricted data is needed and no lawful or approved basis is recorded.
- The Product Owner is not reachable for blocking questions.

## Outputs

| File | Required content |
|---|---|
| `01-requirements/requirements.md` | Outcome; consumers and questions; `REQ-###` functional requirements; `BR-###` rules with examples; `NFR-###` with numbers; classification per data need; out of scope |
| `01-requirements/acceptance-criteria.md` | Given/When/Then per requirement; reconciliation targets |
| `01-requirements/glossary-delta.md` | New or disputed terms with proposed definitions and owner |
| `01-requirements/open-items.md` | Assumptions and open questions with owners |
| Handoff envelope to `adef-source-target-mapping`, status `needs-approval`, gate G1 |

## Definition of done

- Every consumer question maps to at least one requirement, and every requirement to at
  least one acceptance criterion.
- Zero blocking open questions. Zero technology terms.
- Every Domain Pack control appears as an `NFR-###` or is marked not applicable with a reason.
- G1 approval recorded against the document hashes.

## Common failure modes

| Failure | Prevention |
|---|---|
| Solutioning inside requirements | Technology-term scan before handoff |
| Vague non-functionals ("near real time") | Number required for each |
| Hidden assumptions | Fact, assumption, open-question labels on every statement |
| Gold-plating | Must/should/could priority; slice rule |
