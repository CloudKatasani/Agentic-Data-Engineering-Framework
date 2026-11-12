import os
import sys
import tempfile
from pathlib import Path

_HOME = tempfile.mkdtemp(prefix="adpe-test-")
os.environ["ADPE_HOME"] = _HOME
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import time  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def engine():
    from adpe.engine.orchestrator import get_engine
    return get_engine()


def drive(engine, run_id, timeout=120):
    """Approve every pending gate as the named approver until the run completes."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = engine.status(run_id)
        if st["status"] == "completed":
            return st
        bad = {k: v for k, v in st["stages"].items() if v["status"] in ("failed", "blocked")}
        assert not bad, bad
        if any(v["status"] == "running" for v in st["stages"].values()):
            time.sleep(0.05)
            continue
        acted = False
        for g, gd in st["gates_detail"].items():
            if gd["state"] == "pending":
                for role in gd["pending_roles"]:
                    engine.decide(run_id, g, st["run"]["approvers"][role], role, "approved")
                    acted = True
        if not acted:
            time.sleep(0.05)
    raise AssertionError("run did not complete in time")
