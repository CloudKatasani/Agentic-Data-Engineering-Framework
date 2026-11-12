# Autonomous Data Platform Engineering (ADPE) Framework - Specification Pack

A platform-agnostic, approval-gated team of nine AI agents that automates the data
engineering lifecycle:

Business Intent -> Requirements -> Mapping -> Design -> Coding -> Testing -> Deployment
-> Operations -> Data Consumption

The specifications are written as Agent Skills (`SKILL.md` with YAML frontmatter, plus
`references/` and `assets/`), so any skills-compatible agent runtime can load them.

## What is in this pack

```
adpe-framework/
├── README.md                     # this file
├── BUILD_SPEC.md                 # what to build, backlog, QA plan, 7-day launch plan
├── agents/                       # one short production prompt per agent (9)
│   └── adpe-<agent>.md
└── skills/
    ├── adpe-shared-guardrails/   # SHARED: action classes, gates, prohibited actions, handoffs
    │   ├── SKILL.md
    │   ├── references/approval-matrix.md
    │   ├── references/handoff-contract.md
    │   ├── references/artifact-layout.md
    │   └── assets/handoff-envelope.schema.json
    ├── adpe-stack-binding/       # SHARED: capability slots, Stack Profile, adapters, Domain Packs
    │   ├── SKILL.md
    │   ├── references/capability-slots.md
    │   ├── references/adapter-contract.md
    │   └── assets/ (2 example Stack Profiles, Utilities and Telco Domain Packs)
    ├── adpe-orchestrator/              # 0  intake, routing, gates, assembly      G0
    ├── adpe-intent-requirements/       # 1  business intent -> requirements       G1
    ├── adpe-source-target-mapping/     # 2  mapping, profiling, quality rules     G2
    ├── adpe-solution-design/           # 3  logical then physical design          G3
    ├── adpe-pipeline-build/            # 4  code on feature branch                G4
    ├── adpe-test-quality/              # 5  independent verification              G5
    ├── adpe-release-deploy/            # 6  promotion and rollback                G6a/G6b
    ├── adpe-operations-observability/  # 7  monitoring, incidents, cost           G7
    └── adpe-data-consumption/          # 8  semantic layer, BI, publication       G8
```

## How each skill is structured

Every stage skill uses the same sections, so they are easy to compare and audit:

| Section | Answers |
|---|---|
| Mission | What this agent is for, in one or two sentences |
| Use when / Do not use for | Scope boundary with neighbouring agents |
| Inputs | What must exist before it starts, and when to reject the handoff |
| Tasks | Numbered procedure |
| Decision rules | How to choose when there is a choice |
| Do / Do not | Positive and negative instructions |
| Escalate to the human when | Approval and escalation triggers |
| Outputs | Files and their required content |
| Definition of done | Success criteria |
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
  `skills`, then the prompt). Adjust the frontmatter keys to your runtime; the prompt
  body is runtime-neutral. Set the model to Claude Fable 5.2 (`claude-fable-5-2`) where
  your runtime does not inherit it.
- Tool names in the example Stack Profiles are illustrations. No adapter content is
  included: adapters must be written and conformance-tested for your launch stack
  (backlog Epic E3).
- The Domain Packs are starters. Their control lists are not legal or compliance advice
  and need review by the client's Security and Compliance owner before use.

## START HERE FIRST

Open `BUILD_SPEC.md` and go to the last section, **START HERE FIRST**: five questions
to answer, then the first five backlog tasks.
