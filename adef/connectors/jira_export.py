"""Import Jira export files (no Jira connection needed).

- CSV: Jira's "Export > CSV (all fields / current fields)". Repeated columns such as "Labels"
  are merged; acceptance criteria come from any column whose name contains "Acceptance",
  otherwise from an "Acceptance Criteria" section in the description.
- JSON: a REST search response (`{"issues": [...]}`, v2 text or v3 ADF descriptions) or a bare
  list of issues.

Issues are normalised to the same shape as the live connector and scanned as untrusted text.
"""
from __future__ import annotations

import csv
import io
import json

from .jira import adf_to_text, normalize_issue, scan_issue, split_acceptance


def _clean_ac(text: str) -> list[str]:
    return [line.strip().lstrip("*-# ").strip() for line in (text or "").splitlines() if line.strip().lstrip("*-# ").strip()]


def from_csv(text: str) -> list[dict]:
    reader = csv.reader(io.StringIO(text))
    header = next(reader, [])
    idx: dict[str, list[int]] = {}
    for i, h in enumerate(header):
        idx.setdefault(h.strip().lower(), []).append(i)

    def get(row, *names):
        for n in names:
            for i in idx.get(n, []):
                if i < len(row) and row[i].strip():
                    return row[i].strip()
        return ""

    ac_cols = [i for h, ii in idx.items() if "acceptance" in h for i in ii]
    out = []
    for row in reader:
        key = get(row, "issue key", "key")
        if not key:
            continue
        body, ac = split_acceptance(get(row, "description"))
        ac_field = next((row[i] for i in ac_cols if i < len(row) and row[i].strip()), "")
        out.append(scan_issue({
            "key": key, "type": get(row, "issue type", "issuetype", "type"), "summary": get(row, "summary"),
            "description": body, "acceptance_criteria": _clean_ac(ac_field) or ac,
            "status": get(row, "status"), "priority": get(row, "priority"),
            "labels": [row[i].strip() for i in idx.get("labels", []) if i < len(row) and row[i].strip()],
            "parent": get(row, "parent", "parent id", "parent key", "custom field (epic link)") or None, "url": ""}))
    return out


def from_json(text: str) -> list[dict]:
    d = json.loads(text)
    raw = d.get("issues", []) if isinstance(d, dict) else d
    out = []
    for r in raw:
        if "fields" in r:
            issue = normalize_issue(r, "", "")
            for k, v in r["fields"].items():
                if k.startswith("customfield_") and v and not issue["acceptance_criteria"]:
                    names = (d.get("names") or {}) if isinstance(d, dict) else {}
                    if "acceptance" in names.get(k, "").lower():
                        issue["acceptance_criteria"] = _clean_ac(adf_to_text(v) if isinstance(v, dict) else str(v))
        else:  # already-normalised list (e.g. saved from the ADEF console)
            issue = {"key": r["key"], "type": r.get("type", ""), "summary": r.get("summary", ""),
                     "description": r.get("description", ""), "acceptance_criteria": r.get("acceptance_criteria", []),
                     "status": r.get("status", ""), "priority": r.get("priority", ""), "labels": r.get("labels", []),
                     "parent": r.get("parent"), "url": r.get("url", "")}
        out.append(scan_issue(issue))
    return out


def parse(filename: str, text: str) -> list[dict]:
    if filename.lower().endswith(".json") or text.lstrip().startswith(("{", "[")):
        issues = from_json(text)
    else:
        issues = from_csv(text)
    if not issues:
        raise ValueError("no issues found (expected a Jira CSV export with an 'Issue key' column, or a JSON search response)")
    return issues
