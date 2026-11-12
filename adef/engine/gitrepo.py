"""Run-local git repository standing in for the client's version-control slot.

Agents commit only to feature branches; `main` is protected: only the merge performed by
the runtime after a recorded G4 approval can change it.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

ENV = {"GIT_AUTHOR_NAME": "adef-pipeline-build", "GIT_AUTHOR_EMAIL": "adef-pipeline-build@adef.local",
       "GIT_COMMITTER_NAME": "adef-runtime", "GIT_COMMITTER_EMAIL": "adef-runtime@adef.local", "HOME": "/tmp",
       "PATH": "/usr/bin:/bin:/usr/local/bin", "GIT_CONFIG_NOSYSTEM": "1"}


class Repo:
    def __init__(self, path: Path):
        self.path = path

    def git(self, *args: str) -> str:
        r = subprocess.run(["git", "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main", *args], cwd=self.path,
                           env=ENV, capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
        return r.stdout.strip()

    def init(self) -> None:
        if (self.path / ".git").exists():
            return
        self.path.mkdir(parents=True, exist_ok=True)
        self.git("init", "-q")
        (self.path / "README.md").write_text("# Data product repository\n\nProtected branch: main.\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "Initial commit")

    def branch(self, name: str) -> None:
        existing = self.git("branch", "--list", name)
        self.git("checkout", "-q", "main")
        if existing:
            self.git("branch", "-q", "-D", name)
        self.git("checkout", "-q", "-b", name)

    def write_files(self, files: dict[str, str]) -> None:
        for rel, content in files.items():
            p = self.path / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)

    def commit(self, message: str) -> str:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")

    def merge_to_main(self, branch: str, message: str) -> str:
        self.git("checkout", "-q", "main")
        self.git("merge", "-q", "--no-ff", branch, "-m", message)
        return self.git("rev-parse", "HEAD")

    def head(self, ref: str = "main") -> str:
        return self.git("rev-parse", ref)

    def diffstat(self, base: str, head: str) -> str:
        return self.git("diff", "--stat", base, head)

    def tag(self, name: str, ref: str) -> None:
        self.git("tag", "-f", name, ref)
