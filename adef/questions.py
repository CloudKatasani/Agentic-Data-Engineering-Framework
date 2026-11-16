"""Open questions: what the agents asked, and what people answered.

An agent that is missing a fact must ask instead of inventing. Asking is only useful if someone can
answer: this module collects every open question from the run's handoffs, lets a named person answer
it, and attaches the answer as context for every stage, so the answer reaches the agents that follow
and the asking agent if its stage is re-run.
"""
from __future__ import annotations

import json

from . import context_hub
from .util import load_yaml, now_iso

ANSWERS = "control/answers.json"


def _answers(ws) -> dict:
    return ws.read_json(ANSWERS) if ws.has(ANSWERS) else {}


def collect(ws) -> list[dict]:
    """Every open question from the latest handoff of each stage, with its answer if there is one."""
    latest: dict[str, dict] = {}
    hdir = ws.root / "control" / "handoffs"
    for p in sorted(hdir.glob("*.yaml")) if hdir.exists() else []:
        env = load_yaml(p.read_text())
        if env.get("status") != "returned":
            latest[env.get("stage", "")] = env
    answers = _answers(ws)
    out = []
    for stage, env in latest.items():
        seen: dict[str, int] = {}
        for q in env.get("open_questions") or []:
            qid = str(q.get("id") or "OQ")
            seen[qid] = seen.get(qid, 0) + 1
            key = f"{stage}:{qid}" + (f":{seen[qid]}" if seen[qid] > 1 else "")
            out.append({"key": key, "stage": stage, "id": qid, "question": q.get("question", ""),
                        "blocking": bool(q.get("blocking")), "ask_whom": q.get("ask_whom", ""), "from_agent": env.get("from_agent"),
                        "answer": answers.get(key)})
    return out


def answer(ws, key: str, text: str, by: str) -> dict:
    """Record a named person's answer and hand it to the agents as context."""
    text, by = (text or "").strip(), (by or "").strip()
    q = next((x for x in collect(ws) if x["key"] == key), None)
    if not q:
        raise KeyError(key)
    if by not in set((ws.run.get("approvers") or {}).values()):
        raise ValueError("Questions are answered by a named approver of this run")
    if len(text) < 2:
        raise ValueError("Write the answer")
    previous = (_answers(ws).get(key) or {}).get("context_id")
    if previous:
        try:
            context_hub.remove(ws, previous, by)       # a corrected answer replaces the earlier one
        except KeyError:
            pass
    item = context_hub.add(ws, "all", "answer", f"Answer to {q['id']} ({q['stage']})",
                           f"Question raised at the {q['stage']} stage for the {q['ask_whom']}:\n{q['question']}\n\n"
                           f"Answer from {by}:\n{text}", added_by=by, ref=key)
    rec = {"answer": context_hub.text_of(ws, item).split("Answer from", 1)[-1].split("\n", 1)[-1].strip(),
           "by": by, "at": now_iso(), "context_id": item["id"]}
    with ws.lock:
        data = _answers(ws)
        data[key] = rec
        ws._raw_write(ANSWERS, json.dumps(data, indent=2))
    ws.log_decision(f"Open question {q['id']} answered", ["answer", "leave open"], [ANSWERS], by)
    return {**q, "answer": rec}


def summary(ws) -> dict:
    qs = collect(ws)
    return {"total": len(qs), "open": sum(1 for q in qs if not q["answer"]),
            "blocking_open": sum(1 for q in qs if q["blocking"] and not q["answer"])}
