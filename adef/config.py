"""Paths and runtime configuration.

ADEF_HOME holds everything that changes at runtime (settings, encrypted secrets,
run workspaces). The repository itself holds the read-only framework content:
skills, agent definitions, adapters and domain packs.
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
AGENTS_DIR = REPO_ROOT / "agents"
ADAPTERS_DIR = REPO_ROOT / "adapters"
WEB_DIR = REPO_ROOT / "web"
DEMO_DATA_DIR = REPO_ROOT / "demo-data"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def env(name: str, default: str | None = None) -> str | None:
    """Read ADEF_<name>, falling back to the pre-rename ADPE_<name> so existing deployments keep working."""
    return os.environ.get(f"ADEF_{name}") or os.environ.get(f"ADPE_{name}") or default


def adef_home() -> Path:
    home = Path(env("HOME") or REPO_ROOT / "data").resolve()
    home.mkdir(parents=True, exist_ok=True)
    return home


def runs_dir() -> Path:
    d = adef_home() / "runs"
    d.mkdir(parents=True, exist_ok=True)
    return d
