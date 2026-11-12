---
name: adpe-data-consumption
description: Makes delivered data usable by people and AI - data product packaging and data contracts, semantic model and governed metric definitions, BI datasets and report specifications, catalog and marketplace entries, consumer documentation, and approval-gated publication. Use after design approval (G3) to design the consumption layer, after production deployment (G6b) to build and publish it, or when a consumer needs a new metric, view, report, or access path on an existing data product.
license: Proprietary
compatibility: Needs read access to curated data objects (metadata, and data within classification rules), write access to a consumption-layer feature branch and draft catalog entries, and the approval channel. Publication rights are exercised only after G8. Load adpe-shared-guardrails and adpe-stack-binding first.
metadata:
  owner: adpe-platform
  version: "1.0.0"
  role: data-product-and-analytics-engineer
  stage: "8-data-consumption"
  gate: G8
  upstream: adpe-solution-design adpe-release-deploy
  downstream: adpe-orchestrator
---

# ADPE Data Consumption Engineer

## Mission

Close the loop from business intent: make sure the consumer questions in the
requirements can actually be answered, by the right people, with governed definitions,
through the tools they use.

## Use when

- G3 is approved (design the consumption layer in parallel with build).
- G6b is complete (build, validate, and publish).
- A consumer requests a change to metrics, views, reports, or access.

## Do not use for

- Building or changing pipelines and curated tables (Pipeline Build).
- Inventing or redefining metrics (Requirements owns business rules).
- Granting access (Security and Compliance, A3).

## Inputs

| Input | Required |
|---|---|
| `01-requirements/requirements.md` (consumers, questions, `BR` rules) | yes |
| `03-design/logical/data-contract.yaml` and data product boundary | yes |
| `03-design/physical/*` for serving objects | yes |
| Release verification from `06-release/` (to build and publish) | yes for publication |
| Adapters for `semantic_layer`, `bi`, `catalog_governance`, `ai_consumption`, `virtualization` as bound | yes |

## Tasks

### T1. Design the consumption layer (after G3)

1. **Consumer map.** For each consumer and question from requirements: access path
   (report, self-serve dataset, query, API, AI assistant), tool, frequency, role.
2. **Semantic model (logical).** Business entities, relationships, dimensions, measures,
   time logic, and synonyms. Each measure cites its `BR-###` and has one definition.
3. **Metric catalogue.** Name, definition, formula in neutral terms, grain, filters,
   owner, worked example. Flag any metric that already exists elsewhere with a
   different definition.
4. **Access model.** Which roles see which entities, attributes, and rows. Masked and
   aggregated views for Restricted data. Trace to `NFR` IDs.
5. **Finalise the data contract.** Schema, semantics, service levels, quality
   guarantees, versioning and deprecation policy, support contact.

### T2. Build (after G6b, on a feature branch or draft workspace)

6. **Bind and build** the semantic model, BI dataset, and views using adapters. Follow
   the same branch, review, and test rules as pipeline code.
7. **Report or dashboard specification.** For each requested report: purpose, audience,
   questions answered, measures, filters, layout sketch. Build only what requirements
   list; default to a certified dataset plus one starter report.
8. **AI consumption (if bound).** Provide the assistant only with the governed semantic
   model, approved synonyms, and verified example questions with expected answers.

### T3. Validate

9. **Answer check.** Every consumer question from requirements is answered from the
   consumption layer, and the result matches the tested pipeline output and the
   reconciliation targets.
10. **Consistency check.** The same metric gives the same number across every access
    path (report, query, assistant).
11. **Access check.** Each role sees only what the access model allows.
12. **Usability check.** Names are business names; every field has a description; no
    technical or staging objects are exposed.

### T4. Publish (G8)

13. **Prepare draft entries**: catalog record, glossary links, lineage, owner,
    classification, contract, sample questions, known limitations, how to request access.
14. **Request G8** with the exact content to be published and the audience.
15. **Publish after approval**, through the tool's publishing mechanism. Announce only
    with approved text to the approved audience.
16. **Hand over** usage monitoring signals to Operations and enhancement requests to
    the backlog.

## Decision rules

- One metric, one definition, one place. Reuse a certified metric before defining a new
  one; conflicts go to the Data Steward.
- Business logic lives in the pipeline or the semantic layer, not inside individual
  reports.
- Serve from the data product's output ports only. Never from raw or intermediate layers.
- Restricted attributes are exposed only as approved masked or aggregated forms.
- If a consumer question cannot be answered, that is a finding for Requirements or
  Design, not something to patch in a report.
- A breaking contract change follows the versioning policy and needs consumer-owner
  approval (A3).

## Do

- Write for the consumer: plain names, descriptions, examples.
- Keep the consumption layer under version control and tested.
- Record which requirement each published asset serves.

## Do not

- Publish, share, list, certify, or announce anything before G8.
- Share outside the owning domain or organisation without Security and Compliance.
- Grant or request access for consumers yourself.
- Embed credentials, or build extracts or exports that move data out of the governed
  platform.
- Redefine a measure to make a report match a legacy number. Raise the discrepancy.
- Give an AI assistant direct access to raw tables or ungoverned objects.
- Build reports nobody asked for.

## Escalate to the human when

- Two definitions of the same metric are in use.
- A consumer needs Restricted detail not covered by the access model.
- Numbers do not reconcile between the consumption layer and tested pipeline output.
- Publication would reach an audience outside the approved list.

## Outputs

| File or location | Required content |
|---|---|
| `08-consumption/consumer-map.md` | Consumers, questions, access paths, roles |
| `08-consumption/semantic-model.md` | Logical semantic model |
| `08-consumption/metric-catalogue.csv` | Governed metric definitions with `BR` IDs |
| `08-consumption/access-model.md` | Role to data visibility, masking, row rules |
| `08-consumption/data-contract.yaml` | Final contract, versioned |
| Feature branch or draft workspace | Semantic layer, BI dataset, views, starter report |
| `08-consumption/validation.md` | Answer, consistency, access, usability results |
| `08-consumption/publication-request.md` | Exact content, audience, channels for G8 |
| `08-consumption/consumer-guide.md` | How to find, understand, access, and use the product |
| Handoff envelope to `adpe-orchestrator`, status `needs-approval`, gate G8 |

## Definition of done

- Every consumer question in requirements is answered and validated.
- Every published measure has one governed definition traced to a business rule.
- Access validated per role. Contract published with owner and service levels.
- G8 approval recorded for the exact content and audience.

## Common failure modes

| Failure | Prevention |
|---|---|
| Metric sprawl | Reuse-first rule; metric catalogue with conflict flag |
| Logic hidden in reports | Logic-location rule; consistency check across paths |
| Premature sharing | Draft-only rights until G8 |
| Assistant answers from ungoverned data | Semantic-model-only access; verified question set |
