---
name: adef-stack-binding
description: Resolves technology-neutral data engineering designs to a concrete technology stack using a configurable Stack Profile, capability slots, tool adapters, and industry Domain Packs. Use when selecting or validating tools for a run, translating logical artifacts into platform-specific ones, adding support for a new cloud, data platform, ETL, governance, or BI tool, or switching a run to a different stack or industry.
license: Proprietary
compatibility: Runtime-neutral. Needs read access to the run workspace and to the adapter library. Load adef-shared-guardrails first.
metadata:
  owner: adef-platform
  version: "1.1.0"
  scope: shared
  used-by: orchestrator design build test release operations consumption
---

# DataCrew Stack Binding

This skill is what keeps the team platform, cloud, and vendor agnostic. Agents reason in
**capabilities**. A **Stack Profile** says which tool fills each capability for this run.
An **adapter** teaches an agent how to use that tool. A **Domain Pack** adds industry
vocabulary and controls. Change the profile, and the same logical design lands on a
different stack.

## Concepts

| Concept | What it is | Where it lives |
|---|---|---|
| Capability slot | A tool-neutral job to be done, e.g. `transformation`, `orchestration` | [references/capability-slots.md](references/capability-slots.md) |
| Stack Profile | Per-run YAML that binds each slot to a tool, version, environment, and limits | `control/stack-profile.yaml`; examples in `assets/` |
| Adapter | Reference file describing how one tool fulfils one slot | Adapter library; contract in [references/adapter-contract.md](references/adapter-contract.md) |
| Domain Pack | Industry entities, glossary, classification, and regulatory controls | `control/domain-pack.yaml`; examples in `assets/` |

## Tasks

### T1. Validate the Stack Profile (at G0, and whenever it changes)

1. Check every required slot in `capability-slots.md` is bound or explicitly `none`.
2. Check an adapter exists for each bound tool and version. A missing adapter is a
   blocking gap: report it, do not improvise from general knowledge.
3. Check slot compatibility using each adapter's `works_with` list (for example the
   transformation tool can target the compute engine).
4. Check each environment has a secrets reference, never a literal credential.
5. Write `00-intake/stack-validation.md`: slot, tool, adapter version, status, gaps.

### T2. Recommend a stack (only when the user has no fixed stack)

1. Derive needs from requirements: volume, latency, sources, consumers, governance,
   existing licences, team skills, budget.
2. Score at most three candidate profiles against those needs. Show the scoring.
3. Prefer what the client already owns and operates. New tooling needs a stated reason.
4. Present options with trade-offs. The Data Architect chooses at G0 or G3.

### T3. Bind logical to physical (called by Solution Design)

1. For each logical component, pick the slot, then read only that slot's adapter.
2. Apply the adapter's type map, naming rules, and patterns (incremental, history,
   merge, partitioning, access control).
3. Where the adapter offers several patterns, choose by the decision rules in the adapter
   and record the choice as an ADR.
4. If a logical requirement has no physical equivalent, record a **binding gap** with
   options. Do not silently drop or approximate the requirement.

### T4. Add a new adapter

1. Copy the template in `adapter-contract.md`. Fill every section from vendor
   documentation for the stated version. Cite the source for each claim.
2. Add a conformance test: the reference logical model must bind and its generated code
   must pass the standard test suite on that tool.
3. Adapter changes are reviewed by the Data Architect before use in any run.

### T5. Apply a Domain Pack

1. Load the pack named in `control/run.yaml`.
2. Use its glossary for naming, its entities as modelling hints, and its classification
   and controls as mandatory inputs to every stage.
3. A control in the pack is a requirement, not a suggestion. Trace it like one.

## Decision rules

- The Stack Profile is the only source of truth for tool choice. A tool not in the
  profile is not used, even if it would be better.
- Agents never switch tools mid-run. A profile change returns the run to G3.
- One tool per slot per run, unless the profile declares a documented migration pair.
- Use the lowest common denominator only when portability is a stated requirement.
  Otherwise use the platform's native strengths and record the lock-in in an ADR.
- Unknown version behaviour: read the adapter, then vendor docs. If still unknown, mark
  it an assumption and add a test that would expose it.

## Do

- Keep vendor names out of logical artifacts.
- Record every binding choice with its reason.
- Treat the profile's limits (warehouse size, concurrency, cost caps) as hard constraints.

## Do not

- Hard-code account names, hosts, regions, or object prefixes. Use profile variables.
- Invent adapter content or tool capabilities.
- Put credentials, tokens, or connection strings in a profile. Reference names only.
- Copy a client-specific profile or pack into another client's run.

## Enterprise controls

- Bind only to tools, versions and regions the client has approved. Record the region of
  every slot and check it against the residency requirement.
- Record for every slot who operates it, how it authenticates (service identity, never a
  personal account) and where its audit logs go.
- A capability the stack lacks is recorded as a binding gap with options. Never substitute
  an unapproved tool or a manual step.

## Outputs

| File | Content |
|---|---|
| `00-intake/stack-validation.md` | Slot coverage, adapter versions, gaps |
| `03-design/physical/binding-map.md` | Logical component to slot to tool to pattern, with ADR links |
| `03-design/physical/binding-gaps.md` | Requirements with no clean physical equivalent, with options |

## Definition of done

- Every required slot is bound or explicitly `none` with a reason.
- Every bound tool has a reviewed adapter at the stated version.
- No literal secrets or environment-specific constants in any artifact.
- Swapping to a second example profile requires no change to logical artifacts.

## Examples

- [assets/stack-profile.example-a.yaml](assets/stack-profile.example-a.yaml) - cloud data platform with SQL-first transformation
- [assets/stack-profile.example-b.yaml](assets/stack-profile.example-b.yaml) - lakehouse with notebook and pipeline tooling
- [assets/domain-pack.utilities.yaml](assets/domain-pack.utilities.yaml)
- [assets/domain-pack.telco.yaml](assets/domain-pack.telco.yaml)
