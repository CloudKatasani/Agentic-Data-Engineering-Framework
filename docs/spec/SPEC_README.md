# Agentic Data Engineering Framework (ADEF) - Specification Pack

> **Naming.** This pack was first written as ADPE ("Autonomous Data Platform Engineering"). It was
> renamed to ADEF to match the project name; agent and skill IDs changed from `adpe-*` to `adef-*`.
> `adpe-framework-spec-pack.zip` is the original upload, kept unchanged for reference.
> The product built from this pack is shown to users as *DataCrew- BuildWithAI*; the
> framework, agent and skill identifiers keep the name ADEF.

> **Status.** `BUILD_SPEC.md` is at version 2.0 and describes the product as built: what is
> built, partly built and not built, the capabilities added since version 1.0, and the
> known limits. The skills are at version 1.3.0. In the repository the agent files live in
> `agents/` and the skills in `skills/` at the top level.

A platform-agnostic, approval-gated team of nine AI agents that automates the data
engineering lifecycle:

Business Intent -> Requirements -> Mapping -> Design -> Coding -> Testing -> Deployment
-> Operations -> Data Consumption

The specifications are written as Agent Skills (`SKILL.md` with YAML frontmatter, plus
`references/` and `assets/`), so any skills-compatible agent runtime can load them.

## What is in this pack

```
adef-framework/
├── README.md                     # this file
├── BUILD_SPEC.md                 # what to build, backlog, QA plan, 7-day launch plan
├── agents/                       # one short production prompt per agent (9)
│   └── adef-<agent>.md
└── skills/
    ├── adef-shared-guardrails/   # SHARED: action classes, gates, prohibited actions, handoffs
    │   ├── SKILL.md
    │   ├── references/approval-matrix.md
    │   ├── references/handoff-contract.md
    │   ├── references/artifact-layout.md
    │   └── assets/handoff-envelope.schema.json
    ├── adef-stack-binding/       # SHARED: capability slots, Stack Profile, adapters, Domain Packs
    │   ├── SKILL.md
    │   ├── references/capability-slots.md
    │   ├── references/adapter-contract.md
    │   └── assets/ (2 example Stack Profiles, Utilities and Telco Domain Packs)
    ├── adef-orchestrator/              # 0  intake, routing, gates, assembly      G0
    ├── adef-intent-requirements/       # 1  business intent -> requirements       G1
    ├── adef-source-target-mapping/     # 2  mapping, profiling, quality rules     G2
    ├── adef-solution-design/           # 3  logical then physical design          G3
    ├── adef-pipeline-build/            # 4  code on feature branch                G4
    ├── adef-test-quality/              # 5  independent verification              G5
    ├── adef-release-deploy/            # 6  promotion and rollback                G6a/G6b
    ├── adef-operations-observability/  # 7  monitoring, incidents, cost           G7
    └── adef-data-consumption/          # 8  semantic layer, BI, publication       G8
```

## How each skill is structured

Every stage skill uses the same sections, so they are easy to compare and audit:

| Section | Answers |
|---|---|
| Mission | What this agent is for, in one or two sentences |
| Use when / Do not use for | Scope boundary with neighbouring agents |
| Inputs | What must exist before it starts, and when to reject the handoff |
| Context this stage needs | What the agent needs beyond upstream work, where it usually lives, and what to do when it is missing |
| Tasks | Numbered procedure |
| Decision rules | How to choose when there is a choice |
| Do / Do not | Positive and negative instructions |
| Escalate to the human when | Approval and escalation triggers |
| Enterprise controls | Controls for client environments |
| Self-review before handover | Stage checks under the review council's three lenses |
| Outputs | Files and their required content |
| Definition of done | Success criteria; the review council judges against it |
| Worked example | One accepted and one rejected example, with the reason |
| Common failure modes | What goes wrong and how it is prevented |

## Three design ideas to keep hold of

1. **Logical first, technology last.** Stages 1 to 3A never name a product. Technology
   enters only in Design step B through the Stack Profile and adapters. Switching stack
   means switching profile, not rewriting agents.
2. **Nothing risky without a human.** Every action is classed A0 to A4. Publishing,
   sending, deleting, spending, access changes, and anything irreversible need an
   explicit approval tied to the exact artifact. Secrets never enter chat.
3. **Agents hand over files, not chat.** Work moves as a validated handoff envelope plus
   artifacts with hashes. Each folder has one writer. Everything traces back to a
   requirement ID.

## Conformance notes

- Skill names are lowercase with hyphens, match their folder names, and are under 64
  characters. Descriptions state what the skill does and when to use it, under 1024
  characters. Each `SKILL.md` is under 500 lines with detail pushed to one-level-deep
  reference files.
- Validate with the reference validator (`skills-ref validate ./skills/<name>`) when you
  install the pack.
- The `agents/` files use a sub-agent definition layout (`name`, `description`, `model`,
  `skills`, then the prompt, plus a published profile: `title`, `expects`, `produces`,
  `does`, `does_not`). Adjust the frontmatter keys to your runtime; the prompt body is
  runtime-neutral. In this product each agent's model provider and model are chosen in the
  console, per agent and per run.
- Tool names in the Stack Profiles are illustrations. No separate adapter library is
  included: code generation for the reference stacks is built into the product, and
  deployment to a client platform is still open (see `BUILD_SPEC.md`, section 7, open
  backlog, and section 20, known limits).
- The Domain Packs are starters. Their control lists are not legal or compliance advice
  and need review by the client's Security and Compliance owner before use.

## START HERE FIRST

Open `BUILD_SPEC.md` and go to the last section, **START HERE FIRST**: start the product,
run the guardrail suite, complete one run, then answer six questions for a real run.
