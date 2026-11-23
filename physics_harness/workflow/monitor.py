"""Observe exact GitHub Actions run and job outcomes, never assume P3 success."""
from __future__ import annotations


def snapshot(provider, run_id: int) -> dict:
    workflow = provider.run(run_id)
    jobs = provider.jobs(run_id)
    return {
        "run_id": run_id,
        "head_sha": workflow.get("head_sha"),
        "event": workflow.get("event"),
        "status": workflow.get("status"),
        "conclusion": workflow.get("conclusion"),
        "html_url": workflow.get("html_url"),
        "jobs": [
            {"id": job.get("id"), "name": job.get("name"),
             "status": job.get("status"), "conclusion": job.get("conclusion")}
            for job in jobs
        ],
        "scientific_status": "UNVERIFIED",
    }
