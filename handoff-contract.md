# Handoff Contract

Agents do not talk to each other in free text. Work moves as a handoff envelope plus the
artifacts it lists. The envelope is written to
`control/handoffs/<seq>-<from>-to-<to>.yaml`.

## Envelope fields

| Field | Required | Meaning |
|---|---|---|
| `run_id` | yes | Run identifier from `control/run.yaml` |
| `seq` | yes | Monotonic sequence number within the run |
| `from_agent`, `to_agent` | yes | Skill names, e.g. `adpe-solution-design` |
| `stage` | yes | Stage that produced the envelope |
| `status` | yes | `ready`, `needs-approval`, `blocked`, `returned` |
| `gate` | when status is `needs-approval` | Gate ID G0 to G8 |
| `summary` | yes | Three sentences at most: what was done, what was decided, what is next |
| `artifacts[]` | yes | `path`, `sha256`, `kind` (`logical`, `physical`, `code`, `evidence`, `config`), `owner_agent` |
| `inputs_used[]` | yes | Paths and hashes of upstream artifacts consumed, so staleness is detectable |
| `requirement_ids[]` | yes from stage 2 onward | Traceability back to requirements |
| `assumptions[]` | yes (may be empty) | `id`, `text`, `impact_if_wrong`, `owner_to_confirm` |
| `open_questions[]` | yes (may be empty) | `id`, `question`, `blocking` (true or false), `ask_whom` |
| `risks[]` | yes (may be empty) | `id`, `text`, `likelihood`, `impact`, `mitigation` |
| `evidence[]` | yes | Paths to proofs: profiles, test reports, plans, cost estimates |
| `constraints[]` | yes (may be empty) | Binding conditions carried from approvals |
| `confidence` | yes | `high`, `medium`, `low` plus one line on why |
| `return_reason` | when status is `returned` | What is wrong, which artifact, what would fix it |
| `budget_used` | yes | Cost, tokens, elapsed time for the stage |

## Receiver checks

Before starting, the receiving agent must confirm:

1. Envelope validates against `assets/handoff-envelope.schema.json`.
2. Every listed artifact exists and its hash matches.
3. The upstream gate has an approval record for those hashes.
4. No `open_questions` are marked `blocking: true`.
5. `inputs_used` hashes still match the current upstream artifacts.

If any check fails, write a `returned` envelope to the sender with a specific
`return_reason`. Do not repair another stage's artifact.

## Return and rework rules

- A return names the exact artifact, section, and defect. "Needs improvement" is invalid.
- The sender fixes only what was returned and lists the change in the next envelope.
- Three returns on the same handoff trigger escalation to the human owner.
- Approved artifacts are immutable. Changes create a new version and re-open the gate.
