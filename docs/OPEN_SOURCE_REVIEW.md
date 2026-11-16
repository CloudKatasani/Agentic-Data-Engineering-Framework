# Open-source review: how comparable projects work, and what we changed

Reviewed November 2026. This compares DataCrew- BuildWithAI with open-source projects that
solve a similar problem, and records what was changed in the product as a result.

**How the review was done.** Each project was assessed from its repository README, its
documentation and published write-ups. None of them was installed or run, so this compares
*approaches*, not measured quality. Star counts and version details are left out because
they go stale.

## 1. The projects

| Project | What it is | Its central idea |
|---|---|---|
| [Datus-agent](https://github.com/Datus-ai/Datus-agent) | Data engineering agent (CLI, chat, API) | Sub-agents that each carry their own context, tools and rules; user corrections feed back into that context |
| [ktx](https://github.com/Kaelio/ktx) | Context layer for data agents | Context is a maintained, executable asset, not a prompt |
| [Wren AI](https://github.com/Canner/WrenAI) | Open-source GenBI | A semantic model as code, so every answer uses the same definitions |
| [nao](https://github.com/getnao/nao) | Framework for analytics agents | Context is tested: question-and-expected-answer tests are run against the agent, and usage audits propose context fixes |
| [GitHub Spec Kit](https://github.com/github/spec-kit) | Spec-driven development toolkit | A fixed sequence: constitution, specify, **clarify**, plan, checklist, tasks, **analyze**, implement |
| [BMAD-METHOD](https://github.com/bmad-code-org/BMAD-METHOD) | Agile multi-agent method | Role agents (analyst, product manager, architect, developer, QA) that hand over through documents |
| [MetaGPT](https://github.com/geekan/MetaGPT) | Multi-agent framework | "Code = SOP(Team)": roles follow standard operating procedures and exchange structured documents, not chat |

## 2. How the approaches compare

| Question | Data-agent projects (Datus, ktx, Wren AI, nao) | Method projects (Spec Kit, BMAD, MetaGPT) | DataCrew- BuildWithAI before this review |
|---|---|---|---|
| Who is it for? | An analyst or engineer asking questions of data | A developer building software | A managed-service team delivering a data product end to end |
| Unit of work | A question or a SQL task | A feature | A run through nine stages and ten approval gates |
| Where does accuracy come from? | A curated context or semantic layer | A specification the code is checked against | Context attached per stage, plus a council of three reviewers |
| Does it learn from corrections? | **Yes**: feedback improves the context | Partly: a project constitution holds standing rules | **No**: rework feedback died with the run |
| What happens when the agent lacks a fact? | Varies | **A clarify step** asks before planning | Agents recorded open questions, but nobody could answer them in the product |
| Cross-artifact consistency | Not the focus | **An analyze step** checks spec, plan and tasks agree | Checked by model reviewers and by people reading |
| Human approval | Light (review a plan or a query) | Light (developer in the loop) | **Strong**: named approvers, hash-bound approvals, segregation of duties |
| Audit trail | Not the focus | Git history | **Strong**: four hash-chained logs |

**Where this product was already ahead:** governance. None of the reviewed projects has
named-approver gates bound to artifact hashes, enforced segregation of duties, or
tamper-evident logs. Those stay as they are.

**Where it was behind:** three things the other projects do and this one did not.

## 3. What was changed

### 3.1 Team standards: corrections are learned once

*Pattern from:* Datus-agent's feedback loop, nao's context recommendations, Spec Kit's
constitution.

A reviewer who rejects a gate can now tick **Also keep this as a team standard**. The
instruction is stored as `STD-###` and given to that stage's agent in every new run, as
context it must apply and cite. Standards can also be written by hand on **Agents &
models**. They are added only by a named person, are scanned for credentials, and reach
the agent as reference data inside the same boundary as all other attached context.

### 3.2 Open questions can be answered

*Pattern from:* Spec Kit's clarify step.

The agents were already told to ask instead of invent. Now the questions are collected on
the **Approvals** tab, each with who should answer and whether it blocks. A named approver
answers in a sentence; the answer is attached as context for every stage, so later agents
treat it as a fact and cite it. Changing an answer replaces the earlier one.

### 3.3 Consistency check at every gate

*Pattern from:* Spec Kit's analyze step.

Twelve deterministic checks (`C01` to `C12`) follow the chain requirement, mapping, logical
model, code, test and release: unique identifiers, every requirement covered, every
business rule implemented, every quality rule in the code and tested, tests run on the
merged commit, blocking questions answered. No model is called, so a finding is a fact
about the artifacts. Checks whose inputs do not exist yet show as "not yet".

The check earned its place immediately: run against the four built-in scenarios it found
that two of them (retail and financial services) each had a requirement and a business
rule that nothing implemented, and one (utilities) had an entity no requirement asked for.
Those scenarios are fixed and a test now keeps them traceable.

### 3.4 Skill changes

The shared guardrails skill (section 11, grounding) now tells every agent to apply team
standards and say so when it cannot, to treat an answer as settled and not ask again, and
to write questions that name who can answer and can be answered in a sentence.

### 3.5 A defect found on the way

Crash recovery could wrongly mark a stage that had just finished as "interrupted by a
server restart" (about one run in eight in a tight loop). Recovery now re-reads the stage's
state before acting.

## 4. Considered and not adopted

| Idea | From | Why not now |
|---|---|---|
| A full semantic layer as code | Wren AI, ktx | The logical model and metric definitions already play this role inside a run. A cross-run semantic layer is a product of its own |
| Question-and-expected-answer test suites for agents | nao | Valuable, but needs live model keys to mean anything. The golden tests cover the runtime; model quality remains unmeasured (see Known limits) |
| Automatic learning from every rejection | Datus-agent | A standard changes every future run, so a named person must choose to keep it |
| Free-form agent-to-agent chat | Common in agent frameworks | Structured handoffs are easier to audit; MetaGPT and BMAD reach the same conclusion |

## 5. Limits of this review

- The other projects were read, not run.
- The new features are tested with the built-in simulator and in the browser. Whether live
  models follow a team standard reliably has not been measured.
- The consistency check reads the structured files the stages write. If a live model
  leaves out a field such as `req_ids`, the check reports the gap; it cannot infer the link.
