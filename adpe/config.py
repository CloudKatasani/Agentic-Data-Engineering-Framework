"""Paths and runtime configuration.

ADPE_HOME holds everything that changes at runtime (settings, encrypted secrets,
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
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def adpe_home() -> Path:
    home = Path(os.environ.get("ADPE_HOME", REPO_ROOT / "data")).resolve()
    home.mkdir(parents=True, exist_ok=True)
    return home


def runs_dir() -> Path:
    d = adpe_home() / "runs"
    d.mkdir(parents=True, exist_ok=True)
    return d
