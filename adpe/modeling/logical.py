"""Technology-neutral logical data model, the backbone that every export renders from.

Shape:
{
  "name": str, "version": str, "domain": str, "description": str,
  "entities": [{
     "name": "customer_account", "label": "Customer Account", "kind": "dimension|fact|reference|bridge",
     "subject_area": str, "description": str, "grain": str, "history": "type2|type1|snapshot|none",
     "attributes": [{
        "name": str, "label": str, "type": "string|string(n)|integer|bigint|decimal(p,s)|boolean|date|timestamp",
        "nullable": bool, "pk": bool, "fk": {"entity": str, "attribute": str} | null,
        "classification": "public|internal|confidential|restricted", "description": str,
        "business_rule": "BR-###" | null, "req_ids": [str]
     }]
  }],
  "metrics": [{"name", "label", "definition", "expression", "business_rule", "grain", "unit"}]
}
"""
from __future__ import annotations

import re

LOGICAL_TYPES = ("string", "integer", "bigint", "decimal", "boolean", "date", "timestamp")
CLASSIFICATIONS = ("public", "internal", "confidential", "restricted")


def parse_type(t: str) -> tuple[str, list[int]]:
    m = re.match(r"^\s*([a-z]+)\s*(?:\(([\d,\s]+)\))?\s*$", (t or "string").lower())
    if not m:
        return "string", []
    base = m.group(1)
    args = [int(x) for x in (m.group(2) or "").split(",") if x.strip()]
    aliases = {"varchar": "string", "text": "string", "char": "string", "int": "integer", "number": "decimal",
               "numeric": "decimal", "float": "decimal", "double": "decimal", "bool": "boolean",
               "datetime": "timestamp", "timestamp_ntz": "timestamp", "long": "bigint"}
    base = aliases.get(base, base)
    if base not in LOGICAL_TYPES:
        base = "string"
    return base, args


def validate_model(model: dict) -> list[str]:
    problems = []
    names = {e["name"] for e in model.get("entities", [])}
    if not model.get("entities"):
        problems.append("model has no entities")
    for e in model.get("entities", []):
        if not re.match(r"^[a-z][a-z0-9_]*$", e.get("name", "")):
            problems.append(f"entity name `{e.get('name')}` must be lower_snake")
        attrs = e.get("attributes") or []
        if not attrs:
            problems.append(f"{e.get('name')}: no attributes")
        if not any(a.get("pk") for a in attrs):
            problems.append(f"{e.get('name')}: no primary/business key")
        for a in attrs:
            if a.get("classification", "restricted") not in CLASSIFICATIONS:
                problems.append(f"{e['name']}.{a.get('name')}: bad classification")
            fk = a.get("fk")
            if fk and fk.get("entity") not in names:
                problems.append(f"{e['name']}.{a['name']}: FK to unknown entity {fk.get('entity')}")
    return problems


def normalize(model: dict) -> dict:
    """Fill defaults so exporters can rely on every key."""
    model.setdefault("version", "1.0.0")
    model.setdefault("metrics", [])
    for e in model.get("entities", []):
        e.setdefault("label", e["name"].replace("_", " ").title())
        e.setdefault("kind", "dimension")
        e.setdefault("history", "type1")
        e.setdefault("description", "")
        e.setdefault("grain", "")
        e.setdefault("subject_area", model.get("domain", ""))
        for a in e.get("attributes", []):
            a.setdefault("label", a["name"].replace("_", " ").title())
            a.setdefault("type", "string")
            a.setdefault("nullable", not a.get("pk", False))
            a.setdefault("pk", False)
            a.setdefault("fk", None)
            a.setdefault("classification", "internal")
            a.setdefault("description", "")
            a.setdefault("business_rule", None)
            a.setdefault("req_ids", [])
    return model


def relationships(model: dict) -> list[dict]:
    out = []
    for e in model["entities"]:
        for a in e["attributes"]:
            if a.get("fk"):
                out.append({"from_entity": e["name"], "from_attribute": a["name"],
                            "to_entity": a["fk"]["entity"], "to_attribute": a["fk"]["attribute"],
                            "cardinality": "many-to-one"})
    return out


def entity(model: dict, name: str) -> dict | None:
    return next((e for e in model["entities"] if e["name"] == name), None)
