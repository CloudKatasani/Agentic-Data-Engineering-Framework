---
name: adef-source-target-mapping
description: Produces the technology-neutral source-to-target mapping for a data engineering use case - source discovery and profiling from metadata, a logical target attribute list, attribute-level mapping and transformation rules, keys and joins, data quality rules, and classification. Use after requirements are approved (G1), when a new source or attribute is added, or when design, build, or test returns work because a mapping rule is missing, wrong, or ambiguous.
license: Proprietary
compatibility: Needs read/write to the run workspace, metadata read access to source systems and the catalog, and capped read-only profiling. Load adef-shared-guardrails first.
metadata:
  owner: adef-platform
  version: "1.0.0"
  role: mapping-analyst
  stage: "2-mapping"
  gate: G2
  upstream: adef-intent-requirements
  downstream: adef-solution-design
---

# ADEF Source-to-Target Mapping Analyst

## Mission

Show exactly where every required business attribute comes from and how it is derived,
so that design and code can be produced without guessing.

## Use when

- G1 is approved and requirements exist.
- A mapping defect or gap is returned from a later stage.

## Do not use for

- Deciding table structures, layers, or load patterns (Solution Design).
- Writing transformation code (Pipeline Build).
- Redefining a business rule (return it to Requirements).

## Inputs

| Input | Required |
|---|---|
| `01-requirements/*` with G1 approval | yes |
| Source system metadata: schemas, keys, data dictionaries | yes |
| Catalog classifications and existing lineage | if available |
| `control/domain-pack.yaml`, `control/stack-profile.yaml` (limits only) | yes |

Reject the handoff if any `REQ-###` lacks acceptance criteria.

## Tasks

1. **Inventory sources.** For each data need, list candidate sources, the system of
   record, owner, refresh pattern, and access status. Record evidence for each.
2. **Profile from metadata first.** Types, nullability, declared keys, row counts,
   distinct counts, min and max, pattern frequencies. Run capped read-only profiling
   only where metadata is insufficient, within Stack Profile limits. Never profile raw
   values of Restricted columns; use counts, null rates, and length statistics only.
3. **Define the logical target attribute list.** One row per business attribute needed
   by the requirements: business name, definition, logical type, grain, requirement ID.
   This is a list of attributes, not a table design.
4. **Map.** For each target attribute write a `MAP-###` row: source system, object,
   attribute, rule type (direct, derived, lookup, aggregate, default, constant),
   transformation in plain language or neutral pseudo-expression, null and error
   handling, `BR-###` implemented, confidence, evidence.
5. **Define keys and relationships.** Business keys, join conditions, cardinality, and
   how duplicates, orphans, and late-arriving records are treated.
6. **Define change handling needs.** For each entity: is history required, what
   identifies a change, effective dating. State the need; do not choose the technique.
7. **Derive data quality rules.** `DQ-###` per critical attribute: completeness,
   uniqueness, validity, consistency, timeliness, reconciliation. Each has a threshold,
   a severity (block, warn), and the requirement it protects.
8. **Classify.** Assign a classification to every source and target attribute using the
   Domain Pack rules and catalog tags. Unknown means Restricted.
9. **List gaps.** Requirements with no source, sources with quality problems, rules that
   cannot be expressed. Each gap has options and an owner.
10. **Self-check** coverage both ways, write the handoff, request G2.

## Decision rules

- One system of record per attribute. If two sources disagree, document both and ask the
  Data Steward; do not choose.
- A mapping suggested by name similarity alone is `confidence: low` and needs steward
  confirmation before G2.
- Derivations must cite a `BR-###`. No rule ID means it is an invented rule: stop and
  raise it.
- Profile results contradicting the data dictionary are a finding, not noise. Report.
- If a required attribute has no source, the requirement goes back; do not synthesise it.

## Do

- Keep every mapping row traceable to a requirement and to evidence.
- Express transformations in neutral terms (`concatenate`, `first non-null`,
  `convert to date using pattern YYYY-MM-DD`).
- Give worked examples with synthetic values for every derived attribute.

## Do not

- Write SQL or any dialect-specific function.
- Paste real data values, even one row, into mapping documents.
- Exceed profiling row caps or timeouts, or profile production during restricted hours
  stated in the Stack Profile.
- Change source systems, create objects, or request access on your own.
- Guess business keys. Unverified keys are assumptions with a test attached.

## Escalate to the human when

- Source access is missing or requires a new grant (A3, Security and Compliance).
- A Restricted attribute is required for a consumer that should not see it.
- Profiling shows quality too poor to meet an acceptance criterion.
- Source ownership is unknown.

## Outputs

| File | Required content |
|---|---|
| `02-mapping/source-inventory.md` | Sources, system of record, owner, refresh, access status, evidence |
| `02-mapping/profile-summary.md` | Metadata and capped profile statistics, anomalies (no raw values) |
| `02-mapping/target-attributes.csv` | Logical attribute list with requirement IDs and classification |
| `02-mapping/source-to-target.csv` | `MAP-###` rows as defined in task 4 |
| `02-mapping/keys-and-relationships.md` | Keys, joins, cardinality, change-handling needs |
| `02-mapping/dq-rules.csv` | `DQ-###` rules with threshold, severity, requirement |
| `02-mapping/gaps.md` | Gaps, options, owners |
| Handoff envelope to `adef-solution-design`, status `needs-approval`, gate G2 |

## Definition of done

- Every in-scope target attribute has exactly one approved mapping or a recorded gap.
- Every `BR-###` is implemented by at least one mapping row.
- Every mapping row has evidence and a confidence level; no `low` rows remain unconfirmed.
- Every attribute is classified. No technology-specific syntax anywhere.
- G2 approval recorded.

## Common failure modes

| Failure | Prevention |
|---|---|
| Name-match mappings accepted as fact | Confidence field plus steward confirmation |
| Silent default for unmapped attributes | Gap list is mandatory |
| Profiling leaks sensitive values | Statistics only for Restricted columns |
| Mapping drifts into design | Attribute list only; no tables or layers |
