"""Content scanners used on every write, prompt and inbound document.

- scan_secrets: blocks credentials in chat, artifacts, commits (GT-01, E2-4)
- scan_injection: flags instructions hidden in data, tickets, comments (GT-04)
- scan_tech_terms: flags vendor names in logical artifacts (GT-13, failure mode
  "technology leaking into logical artifacts")
"""
from __future__ import annotations

import re

SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("anthropic-key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{16,}")),
    ("openai-key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{20,}")),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("atlassian-token", re.compile(r"\bATATT[A-Za-z0-9_\-=]{20,}")),
    ("slack-token", re.compile(r"\bxox[abpr]-[A-Za-z0-9\-]{10,}")),
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")),
    ("connection-string-password", re.compile(
        r"(?i)\b(?:password|pwd|passwd)\s*[=:]\s*['\"]?(?!\$\{|<|\*{3}|secret:|env:)[^\s'\";]{4,}")),
    ("url-credentials", re.compile(r"\b[a-z][a-z0-9+.\-]*://[^/\s:@]+:[^/\s:@]{3,}@[^\s]+", re.I)),
    ("generic-api-key-assignment", re.compile(
        r"(?i)\b(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret)\s*[=:]\s*['\"]?"
        r"(?!\$\{|<|secret:|env:|\{\{)[A-Za-z0-9_\-/+=]{16,}")),
]


def scan_secrets(text: str) -> list[dict]:
    findings = []
    for name, pat in SECRET_PATTERNS:
        for m in pat.finditer(text or ""):
            findings.append({"type": name, "offset": m.start()})
    return findings


def redact_secrets(text: str) -> str:
    for _, pat in SECRET_PATTERNS:
        text = pat.sub("[REDACTED-SECRET]", text)
    return text


INJECTION_PATTERNS = [
    r"ignore (?:all |any |your |the )?(?:previous |prior |above )?(?:rules|instructions|guardrails|policies)",
    r"disregard (?:all |any |your |the )?(?:previous |prior )?(?:rules|instructions)",
    r"you are now\b", r"new instructions?:", r"system prompt", r"act as (?:an? )?(?:admin|administrator|root)",
    r"grant (?:access|all|admin|select)\b.*\b(?:to all|to everyone|public)",
    r"(?:skip|bypass|disable) (?:the )?(?:review|approval|gate|tests?|guardrails?|masking|audit)",
    r"deploy (?:straight |directly )?to prod(?:uction)? now",
    r"exfiltrate|send (?:the )?data to\b",
    r"drop (?:table|schema|database)\b",
]
_INJ = [re.compile(p, re.I) for p in INJECTION_PATTERNS]


def scan_injection(text: str) -> list[dict]:
    out = []
    for p in _INJ:
        for m in p.finditer(text or ""):
            s = max(0, m.start() - 40)
            out.append({"pattern": p.pattern, "excerpt": (text[s:m.end() + 40]).replace("\n", " ")})
    return out


TECH_TERMS = [
    "snowflake(?! schema)", "databricks", "bigquery", "redshift", "synapse", "microsoft fabric", "dbt",
    "airflow", "dagster", "spark", "pyspark", "informatica", "matillion", "fivetran", "airbyte",
    "azure data factory", "aws glue", "kafka", "collibra", "purview", "unity catalog", "alation", "datahub",
    "atlan", "dataplex", "power ?bi", "tableau", "looker", "qlik", "cognos", "s3", "adls", "gcs",
    "delta lake", "iceberg tables?", "terraform", "github actions", "gitlab", "azure devops",
    "varchar", "nvarchar", "number\\(\\d", "create table", "merge into", "t-sql", "pl/sql",
]
_TECH = re.compile(r"\b(" + "|".join(TECH_TERMS) + r")\b", re.I)


def scan_tech_terms(text: str) -> list[str]:
    return sorted({m.group(1).lower() for m in _TECH.finditer(text or "")})
