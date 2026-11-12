"""Handoff envelopes: write, validate against the JSON Schema, and receiver checks."""
from __future__ import annotations

import json
from functools import lru_cache

import jsonschema

from ..config import SKILLS_DIR
from ..util import dump_yaml

SCHEMA_PATH = SKILLS_DIR / "adef-shared-guardrails" / "assets" / "handoff-envelope.schema.json"


@lru_cache(maxsize=1)
def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


class EnvelopeInvalid(Exception):
    pass


def validate(envelope: dict) -> None:
    v = jsonschema.Draft202012Validator(schema())
    errors = sorted(v.iter_errors(envelope), key=lambda e: list(e.path))
    if errors:
        e = errors[0]
        where = "/".join(str(p) for p in e.path) or "(root)"
        raise EnvelopeInvalid(f"Envelope invalid at {where}: {e.message}")


def write_envelope(ws, envelope: dict) -> str:
    validate(envelope)
    rel = f"control/handoffs/{envelope['seq']:03d}-{envelope['from_agent']}-to-{envelope['to_agent']}.yaml"
    ws._raw_write(rel, dump_yaml(envelope))
    ws.log_action({"agent": envelope["from_agent"], "action": "write_handoff", "class": "A1", "target": rel,
                   "phase": "done", "status": envelope["status"]})
    return rel


def next_seq(ws) -> int:
    return len(list((ws.root / "control" / "handoffs").glob("*.yaml"))) + 1


def _legacy(name):
    return "adef-" + name[5:] if isinstance(name, str) and name.startswith("adpe-") else name


def upgrade_legacy(envelope: dict) -> dict:
    """Envelopes written before the ADPE -> ADEF rename name agents adpe-*; read them as adef-*."""
    env = {**envelope, "from_agent": _legacy(envelope.get("from_agent")), "to_agent": _legacy(envelope.get("to_agent"))}
    env["artifacts"] = [{**a, "owner_agent": _legacy(a.get("owner_agent"))} for a in envelope.get("artifacts", [])]
    return env


def receiver_checks(ws, envelope: dict, upstream_gate: str | None) -> list[str]:
    """Return failures; empty list means the receiver may start."""
    problems = []
    envelope = upgrade_legacy(envelope)
    try:
        validate(envelope)
    except EnvelopeInvalid as e:
        problems.append(str(e))
    for a in envelope.get("artifacts", []):
        h = ws.sha(a["path"])
        if h is None:
            problems.append(f"Artifact missing: {a['path']}")
        elif h != a["sha256"]:
            problems.append(f"Artifact hash changed since handoff: {a['path']}")
    for i in envelope.get("inputs_used", []):
        h = ws.sha(i["path"])
        if h is not None and h != i["sha256"]:
            problems.append(f"Upstream input is stale: {i['path']}")
    if upstream_gate and not ws.gate_passed(upstream_gate):
        problems.append(f"Upstream gate {upstream_gate} has no valid approval for the current hashes")
    for q in envelope.get("open_questions", []):
        if q.get("blocking"):
            problems.append(f"Blocking open question {q['id']}: {q['question']}")
    return problems
