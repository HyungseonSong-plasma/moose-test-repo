#!/usr/bin/env python3
"""Materialize the versioned catalog as SQLite and ingest failed GitHub job logs.

The canonical source is catalog.json; SQLite is a derived database.
Requires only the Python standard library. Optional GITHUB_TOKEN for ingestion.
No raw logs or credentials are committed to the catalog.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from urllib.request import Request, urlopen
from urllib.error import URLError

HOME = Path(__file__).resolve().parent
DEFAULT_CATALOG = HOME / "catalog.json"

# Known signatures map to already-curated incidents, retaining their triage.
PATTERNS = {
    "checkpoint_verifier_legacy_extension_only": r"checkpoint restartable state \(.cpr/.cp\) absent",
    "checkpoint_verifier_rd_directory_as_file": r"checkpoint restartable state \(.rd/.cpr/.cp\) absent",
    "recover_option_consumed_overlay_paths": r"Using .*\.i .*\.i .*\.i .*\.i for recovery",
    "multiapp_no_restore_during_recovery": r"restoration cannot be disabled",
    "oxygen24_100us_p3_timeout_exit_124": r"Process completed with exit code 124",
    "h25_temperature_functor_missing_t_g": r"No functor ever provided with name .T_g.",
    "parser_reserved_symbol_t_in_h25": r"Syntax error in parameter .Vars.",
    "lookup_table_relative_path_duplicated": r"PhysicsLookupTable1D could not open",
    "canonical_inlet_mdot_conversion_missing": r"canonical inlet mass-flow conversion not present",
    "pytest_not_installed_in_selected_venv": r"No module named pytest",
    "h25_formula_test_outdated_assertion": r"test_source_projection_one_source_per_variable_and_heavy_units",
    "charged_wall_sticking_preflight_empty": r"cannot verify all charged sticking=1.0",
    "full24_replay_mode_missing_in_test": r"test_power_replay_research_mode_must_skip_legacy_chemistry",
}
SENSITIVE = re.compile(r"(?i)(authorization:\s*(?:bearer|token)\s+|"
                       r"(?:GITHUB_TOKEN|GH_TOKEN|PRIVATE_RATES_B64)\s*=\s*)\S+")


def validate(data):
    if data["schema_version"] != 1:
        raise ValueError("unknown schema version")
    ids = [i["id"] for i in data["incidents"]]
    entries = [o["occurrence_id"] for o in data["occurrences"]]
    if len(set(ids)) != len(ids) or len(set(entries)) != len(entries):
        raise ValueError("duplicate database identities")
    for o in data["occurrences"]:
        if o["incident_id"] not in ids:
            raise ValueError("orphan occurrence " + o["occurrence_id"])
        if o["power_w"] not in (None, 400, 1000):
            raise ValueError("invalid RF power")
        if not o["log_url"].startswith("https://github.com/"):
            raise ValueError("missing GitHub log provenance")


def build(data, dest):
    validate(data)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    with sqlite3.connect(dest) as db:
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript("""
          CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
          CREATE TABLE incidents(
            id TEXT PRIMARY KEY, fingerprint TEXT UNIQUE NOT NULL,
            category TEXT NOT NULL, component TEXT NOT NULL,
            title TEXT NOT NULL, root_cause TEXT NOT NULL,
            confidence TEXT NOT NULL, status TEXT NOT NULL,
            fix_commit TEXT, verification_run INTEGER, notes TEXT NOT NULL
          );
          CREATE TABLE occurrences(
            occurrence_id TEXT PRIMARY KEY,
            incident_id TEXT NOT NULL REFERENCES incidents(id),
            run_id INTEGER NOT NULL, job_id INTEGER NOT NULL,
            power_w INTEGER, step TEXT NOT NULL, source_sha TEXT NOT NULL,
            observed_at_utc TEXT NOT NULL, log_url TEXT NOT NULL,
            exit_code INTEGER, evidence_excerpt TEXT NOT NULL,
            UNIQUE(job_id,incident_id),
            CHECK(power_w IS NULL OR power_w IN(400,1000))
          );
          CREATE INDEX idx_run ON occurrences(run_id);
          CREATE INDEX idx_incident ON occurrences(incident_id);
          CREATE INDEX idx_date ON occurrences(observed_at_utc);
          CREATE INDEX idx_status ON incidents(status);
          CREATE VIEW incident_overview AS
            SELECT i.id,i.category,i.title,i.status,i.confidence,
              COUNT(o.occurrence_id) AS occurrences,
              COUNT(DISTINCT o.run_id) AS runs,
              MIN(o.observed_at_utc) AS first_seen,
              MAX(o.observed_at_utc) AS last_seen,
              i.fix_commit,i.verification_run
            FROM incidents i LEFT JOIN occurrences o ON o.incident_id=i.id
            GROUP BY i.id;
        """)
        for key in ("title", "repo", "schema_version"):
            db.execute("INSERT INTO metadata VALUES (?,?)", (key, str(data[key])))
        db.executemany(
            "INSERT INTO incidents VALUES (:id,:fingerprint,:category,:component,:title,"
            ":root_cause,:confidence,:status,:fix_commit,:verification_run,:notes)",
            data["incidents"])
        db.executemany(
            "INSERT INTO occurrences VALUES (:occurrence_id,:incident_id,:run_id,:job_id,"
            ":power_w,:step,:source_sha,:observed_at_utc,:log_url,:exit_code,:evidence_excerpt)",
            data["occurrences"])
        check = db.execute("PRAGMA integrity_check").fetchone()[0]
        if check != "ok":
            raise ValueError("SQLite integrity_check failed: " + check)
        db.commit()
    return {"database": str(dest), "incident_count": len(data["incidents"]),
            "occurrence_count": len(data["occurrences"]), "bytes": dest.stat().st_size}


def github_json(repo, path, token):
    url = "https://api.github.com/repos/" + repo + "/" + path
    headers = {"Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": "moose-oxygen-error-db"}
    if token:
        headers["Authorization"] = "Bearer " + token
    with urlopen(Request(url, headers=headers), timeout=40) as response:
        return json.load(response)


def github_job_log(repo, job_id, token):
    url = "https://api.github.com/repos/" + repo + "/actions/jobs/" + str(job_id) + "/logs"
    headers = {"Accept": "application/vnd.github+json",
               "User-Agent": "moose-oxygen-error-db"}
    if token:
        headers["Authorization"] = "Bearer " + token
    with urlopen(Request(url, headers=headers), timeout=45) as response:
        return response.read(64_000_000).decode("utf-8", errors="replace")


def scrub(s):
    return SENSITIVE.sub(r"\1[REDACTED]", re.sub(r"\x1b\[[0-9;]*m", "", s))


def excerpt(log):
    lines = scrub(log).splitlines()
    important = [i for i, l in enumerate(lines)
                 if any(x in l for x in (
                     "*** ERROR ***", "ValueError:", "AssertionError:",
                     "No module named", "Syntax error in parameter",
                     "could not open", "No functor ever provided",
                     "restoration cannot be disabled", "FAILED tests/",
                     "Process completed with exit code"))]
    matched = next((i for i in reversed(important)
                    if "Process completed with exit code" not in lines[i]),
                   important[-1] if important else len(lines)-1)
    return " | ".join(s.strip() for s in lines[max(0,matched-2):matched+3]
                    if s.strip())[:1200]


def fingerprint(log, stage):
    for name, expr in PATTERNS.items():
        if re.search(expr, log, re.IGNORECASE):
            return name
    cleaned = re.sub(r"0x[0-9a-f]+|\b[0-9]{6,}\b", "[ID]", excerpt(log), flags=re.I)
    return "unclassified_" + hashlib.sha256((stage + "|" + cleaned).encode()).hexdigest()[:16]


def ingest(data, run_ids, recent, token):
    repo = data["repo"]
    if not run_ids:
        result = github_json(repo, "actions/runs?per_page=" + str(recent), token)
        run_ids = [x["id"] for x in result.get("workflow_runs", [])
                   if x.get("status") == "completed" and x.get("conclusion") == "failure"]
    incidents = {x["fingerprint"]: x for x in data["incidents"]}
    existing_jobs = {x["job_id"] for x in data["occurrences"]}
    next_id = max([int(x["id"].rsplit("-", 1)[1]) for x in data["incidents"]] + [0])
    added = 0
    for run_id in dict.fromkeys(run_ids):
        run = github_json(repo, "actions/runs/" + str(run_id), token)
        if run.get("status") != "completed" or run.get("conclusion") != "failure":
            print("Skipping unfinished/nonfailed workflow", run_id, file=sys.stderr)
            continue
        job_data = github_json(repo, "actions/runs/" + str(run_id) + "/jobs?per_page=100", token)
        for job in job_data.get("jobs", []):
            if job.get("conclusion") != "failure" or job["id"] in existing_jobs:
                continue
            try:
                log = github_job_log(repo, job["id"], token)
            except (URLError, TimeoutError) as err:
                print("Log unavailable:", job["id"], type(err).__name__, file=sys.stderr)
                continue
            failed = [s.get("name", "UNKNOWN") for s in job.get("steps", [])
                      if s.get("conclusion") == "failure"]
            stage = failed[-1] if failed else "UNKNOWN"
            key = fingerprint(log, stage)
            if key not in incidents:
                next_id += 1
                issue = {
                    "id": "OXY-ERR-%03d" % next_id,
                    "fingerprint": key,
                    "category": "unclassified",
                    "component": "needs_triage",
                    "title": "Untriaged CI failure: " + stage,
                    "root_cause": "Not diagnosed; inspect linked CI logs",
                    "confidence": "unknown", "status": "open",
                    "fix_commit": None, "verification_run": None,
                    "notes": "Auto-collected; confirmation required."
                }
                data["incidents"].append(issue)
                incidents[key] = issue
            match = re.search(r"\b(400|1000)\s*W\b", job.get("name", ""), re.I)
            power = int(match.group(1)) if match else None
            job_id = job["id"]
            data["occurrences"].append({
                "occurrence_id": incidents[key]["id"]+"-"+str(run_id)+"-"+str(job_id),
                "incident_id": incidents[key]["id"], "run_id": run_id, "job_id": job_id,
                "power_w": power, "step": stage, "source_sha": run.get("head_sha") or "unknown",
                "observed_at_utc": run.get("created_at") or datetime.now(timezone.utc).isoformat(),
                "log_url": "https://github.com/"+repo+"/actions/runs/"+str(run_id)+"/job/"+str(job_id),
                "exit_code": None, "evidence_excerpt": excerpt(log),
            })
            existing_jobs.add(job_id)
            added += 1
    data.setdefault("scope", {})["last_refreshed_utc"] = datetime.now(timezone.utc).isoformat()
    validate(data)
    return {"added": added, "incidents": len(data["incidents"]),
            "occurrences": len(data["occurrences"])}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    sub = p.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="Generate a queryable SQLite file")
    b.add_argument("--output", type=Path, default=HOME/"ci_errors.sqlite")
    sub.add_parser("stats", help="Count incidents and failed jobs")
    g = sub.add_parser("ingest", help="Incrementally fetch failed GitHub Actions job logs")
    g.add_argument("--run-id", type=int, action="append", default=[])
    g.add_argument("--recent", type=int, default=25)
    g.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    data = json.loads(a.catalog.read_text(encoding="utf-8"))
    validate(data)
    if a.command == "build":
        print(json.dumps(build(data, a.output), indent=2))
    elif a.command == "stats":
        print(json.dumps({
            "incidents": len(data["incidents"]), "occurrences": len(data["occurrences"]),
            "by_status": dict(Counter(x["status"] for x in data["incidents"])),
            "by_category": dict(Counter(x["category"] for x in data["incidents"]))
        }, indent=2))
    else:
        if not 1 <= a.recent <= 100:
            p.error("--recent must be 1..100")
        summary = ingest(data, a.run_id, a.recent,
                         os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"))
        if not a.dry_run:
            a.catalog.write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n",
                                 encoding="utf-8")
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
