#!/usr/bin/env bash
# One-command start for ADEF on a laptop or a VM (EC2, Azure VM, GCE).
#
#   ./run.sh                                   # demo mode: no keys needed
#   ANTHROPIC_API_KEY=... ./run.sh             # agents run on Claude
#   OPENAI_API_KEY=... GEMINI_API_KEY=... ./run.sh
#   ADEF_API_TOKEN=$(openssl rand -hex 24) ./run.sh --host 0.0.0.0   # reachable from other machines
#
# Keys are read from the environment at runtime; they are never written to disk by ADEF.
set -euo pipefail
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
if [ ! -x .venv/bin/python ]; then
  echo "Creating virtual environment..."
  "$PY" -m venv .venv
fi
if [ ! -f .venv/.deps-installed ] || [ requirements.txt -nt .venv/.deps-installed ]; then
  echo "Installing dependencies..."
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements.txt
  if [ "${WITH_DB2:-false}" = "true" ]; then .venv/bin/pip install -q -r requirements-db2.txt; fi
  touch .venv/.deps-installed
fi
exec .venv/bin/python -m adef serve "$@"
