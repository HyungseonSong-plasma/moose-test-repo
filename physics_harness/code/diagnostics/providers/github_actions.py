"""Read-only GitHub Actions Run/Attempt/Job/Step observation provider.

Unlike file collectors, this consumes authenticated external API snapshots,
not Git blobs. The caller injects an API GET function. Its FactBatch may be
assembled alongside exact-HEAD file facts without fabricating a source file.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
import re

from ...graph import Edge, Evidence, Node
from ..collector import CollectionResult, FactBatch, graph_edge_id, scan_scope_id, stable_id
from ..request import ScanRequest


_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")


class GitHubActionsRunProvider:
    version = "github-actions-rest-v0.1"

    def __init__(self, fetch_json: Callable[[str], Mapping],
                 *, max_pages: int = 10) -> None:
        if not callable(fetch_json):
            raise TypeError("fetch_json must be a read-only JSON GET callable")
        if type(max_pages) is not int or not 1 <= max_pages <= 100:
            raise ValueError("max_pages must be in [1,100]")
        self.fetch_json = fetch_json
        self.max_pages = max_pages

    def collect_run(self, request: ScanRequest, run_id: int,
                    attempt: int = 1) -> CollectionResult:
        """Return runtime facts; never synthesize PASS from workflow SUCCESS.

        APIs:
          GET /actions/runs/{run_id}/attempts/{attempt}
          GET /actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100&page=N
        Each observation has a source SHA, run ID, attempt and source URL.
        """
        if not isinstance(request, ScanRequest):
            raise TypeError("request must be a ScanRequest")
        if not _REPOSITORY.fullmatch(request.repository):
            raise ValueError("INVALID_GITHUB_REPOSITORY")
        if type(run_id) is not int or run_id < 1:
            raise ValueError("INVALID_RUN_ID")
        if type(attempt) is not int or attempt < 1:
            raise ValueError("INVALID_RUN_ATTEMPT")

        root = (
            f"https://api.github.com/repos/{request.repository}"
            f"/actions/runs/{run_id}/attempts/{attempt}"
        )
        try:
            metadata = self.fetch_json(root)
        except Exception as exc:
            return CollectionResult(
                FactBatch(unresolved=("ACTIONS_RUN_METADATA_UNAVAILABLE",)),
                "FAILED", (f"RUN_FETCH_FAILED:{type(exc).__name__}",),
            )
        if not isinstance(metadata, Mapping):
            raise ValueError("INVALID_ACTIONS_RUN_METADATA")
        if metadata.get("id") != run_id or metadata.get("run_attempt") != attempt:
            raise ValueError("ACTIONS_RUN_ATTEMPT_MISMATCH")
        if metadata.get("head_sha") != request.revision:
            raise ValueError("CROSS_HEAD_RUNTIME_EVIDENCE")

        unresolved: set[str] = set()
        if not metadata.get("updated_at"):
            unresolved.add("RUN_UPDATED_AT_MISSING")
        if metadata.get("status") != "completed":
            unresolved.add("RUN_NOT_COMPLETED")
        if metadata.get("conclusion") is None:
            unresolved.add("RUN_CONCLUSION_UNKNOWN")

        fetched_jobs: list[Mapping] = []
        total: int | None = None
        pages_read = 0
        for page in range(1, self.max_pages + 1):
            page_url = f"{root}/jobs?per_page=100&page={page}"
            try:
                payload = self.fetch_json(page_url)
            except Exception:
                unresolved.add(f"JOB_PAGE_UNAVAILABLE:{page}")
                break
            if not isinstance(payload, Mapping):
                unresolved.add(f"JOB_PAGE_INVALID:{page}")
                break
            count = payload.get("total_count")
            jobs = payload.get("jobs")
            if (type(count) is not int or count < 0
                    or not isinstance(jobs, list)):
                unresolved.add(f"JOB_PAGE_INVALID:{page}")
                break
            if total is not None and count != total:
                unresolved.add("JOB_PAGE_TOTAL_CHANGED")
                break
            total = count
            if any(not isinstance(j, Mapping) for j in jobs):
                unresolved.add(f"JOB_PAGE_INVALID:{page}")
                break
            fetched_jobs.extend(jobs)
            pages_read += 1
            if len(fetched_jobs) >= total:
                break
            if not jobs:
                unresolved.add(f"JOB_PAGE_EMPTY_BEFORE_TOTAL:{page}")
                break

        if total is None or len(fetched_jobs) != total:
            unresolved.add("JOB_PAGINATION_INCOMPLETE")
        # Detect a mutable Run/Attempt changed while paginating.
        try:
            after = self.fetch_json(root)
        except Exception:
            unresolved.add("RUN_RECHECK_UNAVAILABLE")
        else:
            if not isinstance(after, Mapping) or (
                after.get("head_sha") != request.revision
                or after.get("run_attempt") != attempt
                or after.get("updated_at") != metadata.get("updated_at")
            ):
                unresolved.add("RUN_CHANGED_DURING_OBSERVATION")

        nodes: list[Node] = []
        edges: list[Edge] = []
        evidence: list[Evidence] = []
        scope_id = scan_scope_id(request)

        def emit(kind: str, key: str, url: str, attributes: Mapping) -> str:
            eid = stable_id(
                "evidence", request.repository, request.revision,
                "ACTIONS", run_id, attempt, kind, key,
                attributes.get("updated_at") or attributes.get("completed_at")
                or attributes.get("status"),
            )
            evidence.append(Evidence(
                id=eid, kind="RUNTIME", source_ref=url, method=self.version,
                scope_id=scope_id, observation_status="RUNTIME_OBSERVED",
                attributes={
                    "source_sha": request.revision,
                    "run_id": run_id, "attempt": attempt,
                    "url": url, "api_url": root,
                    "collector_version": self.version,
                },
            ))
            return eid

        def link(parent: str, child: str, relation: str,
                 eid: str, label: str) -> None:
            edges.append(Edge(
                id=graph_edge_id(parent, child, relation, label),
                source_id=parent, target_id=child, relation=relation,
                discriminator=label, evidence_ids=(eid,),
            ))

        run_url = metadata.get("html_url") or root
        run_node_id = stable_id(
            "node", request.repository, "github_actions_run_attempt",
            run_id, attempt,
        )
        run_eid = emit("run", str(run_id), run_url, metadata)
        nodes.append(Node(
            id=run_node_id, kind="github_actions_run_attempt",
            name=f"run:{run_id}:attempt:{attempt}",
            attributes={
                "status": metadata.get("status"),
                "conclusion": metadata.get("conclusion"),
                "event": metadata.get("event"),
                "workflow_path": metadata.get("path"),
                "created_at": metadata.get("created_at"),
                "updated_at": metadata.get("updated_at"),
                "job_total_count": total, "pages_read": pages_read,
            },
            evidence_ids=(run_eid,),
        ))

        seen_jobs: set[int] = set()
        for job in fetched_jobs:
            job_id = job.get("id")
            if type(job_id) is not int or job_id < 1:
                unresolved.add("JOB_ID_INVALID")
                continue
            if job_id in seen_jobs:
                unresolved.add(f"DUPLICATE_JOB_ID:{job_id}")
                continue
            seen_jobs.add(job_id)
            if job.get("run_id") not in {None, run_id}:
                raise ValueError("ACTIONS_JOB_RUN_ID_MISMATCH")
            if job.get("head_sha") not in {None, request.revision}:
                raise ValueError("CROSS_HEAD_ACTIONS_JOB")
            if job.get("head_sha") is None:
                unresolved.add(f"JOB_SOURCE_SHA_UNVERIFIED:{job_id}")
            if job.get("status") != "completed":
                unresolved.add(f"JOB_NOT_COMPLETED:{job_id}")
            if job.get("conclusion") is None:
                unresolved.add(f"JOB_CONCLUSION_UNKNOWN:{job_id}")

            job_url = job.get("html_url") or job.get("url") or root
            job_node_id = stable_id(
                "node", request.repository, "github_actions_job",
                run_id, attempt, job_id,
            )
            job_eid = emit("job", str(job_id), job_url, job)
            nodes.append(Node(
                id=job_node_id, kind="github_actions_job",
                name=str(job.get("name") or f"job:{job_id}"),
                attributes={
                    "job_id": job_id, "status": job.get("status"),
                    "conclusion": job.get("conclusion"),
                    "runner_name": job.get("runner_name"),
                    "started_at": job.get("started_at"),
                    "completed_at": job.get("completed_at"),
                },
                evidence_ids=(job_eid,),
            ))
            link(run_node_id, job_node_id, "OBSERVED_JOB", job_eid, str(job_id))

            steps = job.get("steps")
            if not isinstance(steps, list):
                unresolved.add(f"JOB_STEPS_UNAVAILABLE:{job_id}")
                continue
            seen_steps: set[int] = set()
            for step in steps:
                if not isinstance(step, Mapping):
                    unresolved.add(f"STEP_INVALID:{job_id}")
                    continue
                number = step.get("number")
                if type(number) is not int or number < 1:
                    unresolved.add(f"STEP_NUMBER_INVALID:{job_id}")
                    continue
                if number in seen_steps:
                    unresolved.add(f"DUPLICATE_STEP_NUMBER:{job_id}:{number}")
                    continue
                seen_steps.add(number)
                if step.get("status") != "completed":
                    unresolved.add(f"STEP_NOT_COMPLETED:{job_id}:{number}")
                if step.get("conclusion") is None:
                    unresolved.add(f"STEP_CONCLUSION_UNKNOWN:{job_id}:{number}")
                step_id = stable_id(
                    "node", request.repository, "github_actions_step",
                    run_id, attempt, job_id, number,
                )
                step_eid = emit("step", f"{job_id}:{number}", job_url, step)
                nodes.append(Node(
                    id=step_id, kind="github_actions_step",
                    name=str(step.get("name") or f"step:{number}"),
                    attributes={
                        "number": number, "status": step.get("status"),
                        "conclusion": step.get("conclusion"),
                        "started_at": step.get("started_at"),
                        "completed_at": step.get("completed_at"),
                    },
                    evidence_ids=(step_eid,),
                ))
                link(job_node_id, step_id, "OBSERVED_STEP", step_eid,
                     str(number))

        return CollectionResult(
            FactBatch(
                nodes=tuple(nodes), edges=tuple(edges), evidence=tuple(evidence),
                unresolved=tuple(sorted(unresolved)),
            ),
            "PARTIAL" if unresolved else "COMPLETE",
        )


__all__ = ["GitHubActionsRunProvider"]
