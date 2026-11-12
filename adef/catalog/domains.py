"""Domain Packs: industry entities, glossary, classification and controls."""
from __future__ import annotations

from ..config import SKILLS_DIR
from ..util import load_yaml

PACK_DIR = SKILLS_DIR / "adef-stack-binding" / "assets"


def list_packs() -> list[dict]:
    out = []
    for f in sorted(PACK_DIR.glob("domain-pack.*.yaml")):
        d = load_yaml(f.read_text())
        out.append({"pack_id": d["pack_id"], "status": d.get("status"), "version": d.get("pack_version"),
                    "subdomains": d.get("subdomains", []), "typical_use_cases": d.get("typical_use_cases", []),
                    "file": f.name})
    return out


def load_pack(pack_id: str) -> dict:
    f = PACK_DIR / f"domain-pack.{pack_id}.yaml"
    if not f.exists():
        raise KeyError(f"unknown domain pack {pack_id}")
    return load_yaml(f.read_text())


def load_pack_text(pack_id: str) -> str:
    return (PACK_DIR / f"domain-pack.{pack_id}.yaml").read_text()
