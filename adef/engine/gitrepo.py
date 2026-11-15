"""Run-local git repository standing in for the client's version-control slot.

Agents commit only to feature branches; `main` is protected: only the merge performed by
the runtime after a recorded G4 approval can change it.
"""
from __future__ import annotations

import base64
import os
import re
import subprocess
from pathlib import Path

ENV = {"GIT_AUTHOR_NAME": "adef-pipeline-build", "GIT_AUTHOR_EMAIL": "adef-pipeline-build@adef.local",
       "GIT_COMMITTER_NAME": "adef-runtime", "GIT_COMMITTER_EMAIL": "adef-runtime@adef.local", "HOME": "/tmp",
       "PATH": "/usr/bin:/bin:/usr/local/bin", "GIT_CONFIG_NOSYSTEM": "1"}


PROTECTED = ("main", "master")


def network_env(token: str | None = None, username: str = "x-access-token") -> dict:
    """Environment for git commands that talk to a remote. The token travels in an HTTP header set through the
    environment: it never appears in the command line, the repository config or the logs."""
    env = {**ENV, "GIT_TERMINAL_PROMPT": "0"}
    for k in ("HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "https_proxy", "http_proxy", "no_proxy", "GIT_SSL_CAINFO", "SSL_CERT_FILE"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    if token:
        basic = base64.b64encode(f"{username or 'x-access-token'}:{token}".encode()).decode()
        env.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="http.extraheader", GIT_CONFIG_VALUE_0=f"Authorization: Basic {basic}")
    return env


def scrub(text: str) -> str:
    return re.sub(r"(Authorization: \w+ )\S+", r"\1[redacted]", re.sub(r"://[^/@\s]+@", "://", text or ""))


class Repo:
    def __init__(self, path: Path):
        self.path = path

    def git(self, *args: str, env: dict | None = None, timeout: int = 60) -> str:
        r = subprocess.run(["git", "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main", *args], cwd=self.path,
                           env=env or ENV, capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            raise RuntimeError(scrub(f"git {args[0]} failed: {r.stderr.strip()}"))
        return r.stdout.strip()

    def init(self, remote: tuple[str, dict] | None = None) -> bool:
        """Create the repository. With a remote, start from its main branch so that the branches pushed later share
        history with the client's repository and open as normal pull requests. Returns True when based on the remote."""
        if (self.path / ".git").exists():
            return (self.path / ".git" / "datacrew-remote-base").exists()
        self.path.mkdir(parents=True, exist_ok=True)
        self.git("init", "-q")
        if remote:
            try:
                self.git("fetch", "-q", "--depth", "50", remote[0], "main", env=remote[1], timeout=120)
                self.git("checkout", "-q", "-B", "main", "FETCH_HEAD")
                (self.path / ".git" / "datacrew-remote-base").write_text(scrub(remote[0]))
                return True
            except (RuntimeError, subprocess.TimeoutExpired):
                pass        # empty or unreachable remote: start a fresh history
        (self.path / "README.md").write_text("# Data product repository\n\nProtected branch: main.\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "Initial commit")
        return False

    def branches(self) -> list[str]:
        return [b.strip().lstrip("* ").strip() for b in self.git("branch", "--list").splitlines() if b.strip()]

    def files(self, ref: str = "HEAD") -> list[str]:
        return [f for f in self.git("ls-tree", "-r", "--name-only", ref).splitlines() if f]

    def show(self, ref: str, path: str) -> str:
        return subprocess.run(["git", "show", f"{ref}:{path}"], cwd=self.path, env=ENV, capture_output=True, text=True,
                              timeout=60, check=True).stdout

    def archive(self, ref: str) -> bytes:
        return subprocess.run(["git", "archive", "--format=zip", ref], cwd=self.path, env=ENV, capture_output=True,
                              timeout=120, check=True).stdout

    def push(self, url: str, refs: list[str], env: dict) -> str:
        """Push branches to the remote. Never the protected branch, never forced."""
        bad = [r for r in refs if r in PROTECTED or r.startswith(("+", "-")) or ":" in r]
        if bad or not refs:
            raise RuntimeError(f"refusing to push {', '.join(bad) or 'nothing'}: protected branches change only through a pull request")
        r = subprocess.run(["git", "push", "--porcelain", url, *[f"refs/heads/{b}:refs/heads/{b}" for b in refs]], cwd=self.path,
                           env=env, capture_output=True, text=True, timeout=180)
        if r.returncode != 0:
            raise RuntimeError(scrub(f"git push failed: {(r.stderr or r.stdout).strip()[-600:]}"))
        return scrub(r.stdout.strip())

    def branch(self, name: str) -> None:
        existing = self.git("branch", "--list", name)
        self.git("checkout", "-q", "main")
        if existing:
            self.git("branch", "-q", "-D", name)
        self.git("checkout", "-q", "-b", name)

    def write_files(self, files: dict[str, str], keep_existing: bool = False) -> list[str]:
        """Write generated files. With keep_existing (a repository that started from the client's main branch), a file
        that already exists with other content is left alone and reported, so nothing of theirs is overwritten."""
        kept = []
        for rel, content in files.items():
            p = self.path / rel
            if keep_existing and p.exists() and p.read_text(errors="replace") != content:
                kept.append(rel)
                continue
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
        return kept

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
