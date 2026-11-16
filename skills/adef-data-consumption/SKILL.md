---
name: adef-data-consumption
description: Makes delivered data usable by people and AI - data product packaging and data contracts, semantic model and governed metric definitions, BI datasets and report specifications, catalog and marketplace entries, consumer documentation, and approval-gated publication. Use after design approval (G3) to design the consumption layer, after production deployment (G6b) to build and publish it, or when a consumer needs a new metric, view, report, or access path on an existing data product.
license: Proprietary
compatibility: Needs read access to curated data objects (metadata, and data within classification rules), write access to a consumption-layer feature branch and draft catalog entries, and the approval channel. Publication rights are exercised only after G8. Load adef-shared-guardrails and adef-stack-binding first.
metadata:
  owner: adef-platform
  version: "1.4.0"
  role: data-product-and-analytics-engineer
  stage: "8-data-consumption"
  gate: G8
  upstream: adef-solution-design adef-release-deploy
  downstream: adef-orchestrator
---

# DataCrew Analytics and AI Engineer Agent

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

## Context this stage needs

| Needed | Usually found in | If it is missing |
|---|---|---|
| Data access and masking policy | Confluence | Apply the classification rules from design, mask every Restricted attribute, and raise the missing policy at G8 |
| Business glossary and KPI definitions | Confluence, requirements | Use the `BR-###` definition only; never write a metric definition of your own |
| BI standards and existing reports | Confluence, an uploaded report list | Build to the consumer questions and say that fit with existing reports was not checked |

An audience is named by the Product Owner. Do not add a consumer group because it
seems likely to want the data.

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
9. **Every other consumption pattern the run chose.** A run lists its consumption
   patterns; build each one with the tool the Stack Profile binds for it, and nothing
   for a pattern the run did not choose:
   - *Data API*: a specification plus named, parameterised queries. The API never
     builds SQL from a request.
   - *Data sharing*: a share of the masked views only. Recipient statements stay
     commented out until G8 names the recipient.
   - *Reverse ETL*: a sync model with one row per business key, created paused.
     Destination field names are proposals for the application owner to confirm.
   - *Machine learning features*: one row per business key, aggregates only, with a
     note on label leakage.
   - *Retrieval index*: documents that describe tables, columns and metrics. No row of
     business data goes into an index.
   - *File exports*: export statements with a manifest and a control total per file.

### T3. Validate

10. **Answer check.** Every consumer question from requirements is answered from the
   consumption layer, and the result matches the tested pipeline output and the
   reconciliation targets.
11. **Consistency check.** The same metric gives the same number across every access
    path (report, query, assistant).
12. **Access check.** Each role sees only what the access model allows.
13. **Usability check.** Names are business names; every field has a description; no
    technical or staging objects are exposed.
14. **Pattern check.** Run the SQL each chosen pattern relies on against the sandbox,
    through the masked views, and report the result per pattern: queries execute, one
    row per key where one is promised, verified queries return the governed metric
    value, and no Restricted attribute is selected. A pattern that was not executed is
    reported as not executed, never as passed.

### T4. Publish (G8)

15. **Prepare draft entries**: catalog record, glossary links, lineage, owner,
    classification, contract, sample questions, known limitations, how to request access.
16. **Request G8** with the exact content to be published and the audience.
17. **Publish after approval**, through the tool's publishing mechanism. Announce only
    with approved text to the approved audience.
18. **Hand over** usage monitoring signals to Operations and enhancement requests to
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
- Every consumption pattern reads the masked consumer views, never a base table. There
  is no pattern through which a Restricted attribute may leave unmasked.
- Anything that sends data outside the platform (a share recipient, a sync into a
  business application, an export location owned by someone else) is a separate A3
  action. Generate it switched off; the owning person switches it on after G8.
- A pattern whose slot is bound to `none` is not available. Say so; do not build it with
  a tool the profile does not name.
- For a history-keeping entity, consumers get the validity columns, and anything that
  promises one row per key reads current rows only.

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

## Enterprise controls

- Grant access to groups by purpose, never to individuals directly, and record the business
  purpose of each group. Access requests go to the Data Steward.
- Enforce row and column security in the governed layer, not in a report.
- Publish with an owner, a data contract (schema, service levels, support route), a catalog
  entry and a deprecation policy.
- Certify a metric only when it reconciles on every access path and the Data Steward agrees
  its definition.
- Connect an AI assistant or natural-language tool only to the governed semantic layer, with
  the same access rules as its user.
- State the limits on export and onward sharing in the consumer guide, and what personal
  data the product contains.
- Record who the product was published to and when; publication to any new audience is a new
  approval.

## Self-review before handover

- *Accuracy.* Every consumer question is answered. Each measure cites its `BR-###` and
  gives the same number on every access path.
- *Risk.* Each role was checked against what it must not see. Nothing is published,
  shared or granted before G8.
- *Handover.* The publication request names the exact content, audience and channel. The
  consumer guide is written in business language.

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
| Handoff envelope to `adef-orchestrator`, status `needs-approval`, gate G8 |

## Definition of done

- Every consumer question in requirements is answered and validated.
- Every published measure has one governed definition traced to a business rule.
- Access validated per role. Contract published with owner and service levels.
- G8 approval recorded for the exact content and audience.

## Worked example

Good metric entry:
> `billed_shortfall_rate`: accounts with a shortfall divided by accounts billed in the
> month. Implements `BR-003`. Owner: Data Steward. Reconciles on the semantic layer, the
> SQL view and the starter report for March: 4.2% on all three.

Rejected:
> "Leakage %" calculated inside the dashboard with its own filter on active accounts.

Why: a second definition of a governed measure, hidden in a report, with a filter no
business rule states.

## Common failure modes

| Failure | Prevention |
|---|---|
| Metric sprawl | Reuse-first rule; metric catalogue with conflict flag |
| Logic hidden in reports | Logic-location rule; consistency check across paths |
| Premature sharing | Draft-only rights until G8 |
| Assistant answers from ungoverned data | Semantic-model-only access; verified question set |
