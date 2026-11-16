"""The skill files are the product's instructions: keep their structure and what each agent receives under test."""
import re

import pytest
import yaml

from adef.config import AGENTS_DIR, SKILLS_DIR
from adef.engine.agent_runtime import declared_skills, system_prompt
from adef.engine.council import definition_of_done
from adef.engine.stages import STAGES

AGENTS = sorted(p.stem for p in AGENTS_DIR.glob("adef-*.md"))
STAGE_SKILLS = sorted({s["agent"] for s in STAGES})
SECTIONS = ["## Mission", "## Inputs", "## Context this stage needs", "## Tasks", "## Decision rules", "## Do not",
            "## Escalate to the human when", "## Enterprise controls", "## Self-review before handover", "## Outputs",
            "## Definition of done", "## Worked example", "## Common failure modes"]


def _skill(name):
    return (SKILLS_DIR / name / "SKILL.md").read_text()


@pytest.mark.parametrize("agent", AGENTS)
def test_agent_receives_every_skill_it_declares(agent):
    front = yaml.safe_load((AGENTS_DIR / f"{agent}.md").read_text().split("---")[1])
    declared = [s.strip() for s in front["skills"].split(",")]
    assert declared_skills(agent)[0] == "adef-shared-guardrails" and set(declared_skills(agent)) == set(declared)
    prompt = system_prompt(agent)
    for name in declared:
        assert f"# Skill: {name}" in prompt, f"{agent} declares {name} but does not receive it"
    assert prompt.index("# Skill: adef-shared-guardrails") < prompt.index(f"# Skill: {agent}")
    assert "## 11. Grounding" in prompt and "## 13. Review and rework" in prompt and "# Runtime contract" in prompt
    assert "---\nname:" not in prompt                                          # frontmatter is not sent to the model


@pytest.mark.parametrize("name", STAGE_SKILLS)
def test_stage_skill_has_the_full_structure_in_order(name):
    text = _skill(name)
    positions = [text.find(f"\n{h}\n") for h in SECTIONS]
    assert all(p >= 0 for p in positions), [h for h, p in zip(SECTIONS, positions) if p < 0]
    assert positions == sorted(positions), "sections out of order"
    assert len(definition_of_done(name)) > 60                                  # the review council reads this section
    review = text.split("## Self-review before handover")[1].split("\n## ")[0]
    assert all(lens in review for lens in ("*Accuracy.*", "*Risk.*", "*Handover.*"))
    example = text.split("## Worked example")[1].split("\n## ")[0]
    assert "Rejected" in example and "Why:" in example
    assert len(text.splitlines()) < 260, "keep a skill short enough to be read in full"


def test_shared_guardrails_define_grounding_ids_confidence_and_rework():
    text = _skill("adef-shared-guardrails")
    numbers = [int(n) for n in re.findall(r"^## (\d+)\. ", text, flags=re.M)]
    assert numbers == list(range(1, 14))
    assert "never the source of a\nclient fact" in text and "Identifiers are permanent" in text
    for level in ("`high`", "`medium`", "`low`"):
        assert level in text
    assert "Fix exactly what was reported" in text and "Never cite its approval as an approval" in text


def test_skills_are_versioned_together_and_free_of_the_old_name():
    for d in sorted(SKILLS_DIR.iterdir()):
        text = (d / "SKILL.md").read_text()
        front = yaml.safe_load(text.split("---")[1])
        assert front["name"] == d.name and front["metadata"]["version"] == "1.4.0", d.name
        assert not re.search(r"\bADEF\b", text), d.name


def test_release_tasks_are_numbered_without_gaps():
    tasks = _skill("adef-release-deploy").split("## Tasks")[1].split("## Decision rules")[0]
    assert [int(n) for n in re.findall(r"^(\d+)\. \*\*", tasks, flags=re.M)] == list(range(1, 14))
    assert "Release as code" in tasks


def test_agents_are_named_for_managed_service_roles():
    fronts = {a: yaml.safe_load((AGENTS_DIR / f"{a}.md").read_text().split("---")[1]) for a in AGENTS}
    titles = [f["title"] for f in fronts.values()]
    assert len(set(titles)) == 9 and all(t.endswith(" Agent") for t in titles)        # never confused with a human role
    assert {f["phase"] for f in fronts.values()} == {"Plan", "Design", "Build", "Assure", "Transition", "Run", "Enable"}
    for agent, f in fronts.items():
        assert f"You are the DataCrew {f['title']}" in (AGENTS_DIR / f"{agent}.md").read_text()
        assert f"# DataCrew {f['title']}" in _skill(agent)
