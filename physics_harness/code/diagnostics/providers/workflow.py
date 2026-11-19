"""Static GitHub Actions Workflow → Job → Step source-fact collector.

No edge in this module implies that a declared step, condition or trigger
actually ran. Actual attempts, statuses and costs require a runtime provider.
"""

from __future__ import annotations

from pathlib import PurePosixPath

import yaml
from yaml.nodes import MappingNode, ScalarNode, SequenceNode

from ...graph import Edge, Evidence, Node, SourceLocation
from ..collector import (
    CollectionResult, FactBatch, SourceInput, SourceRecord, UnresolvedTarget,
    file_node_id, graph_edge_id, stable_id,
)
from ..request import ScanRequest


def _mapping(node) -> dict[str, object]:
    if not isinstance(node, MappingNode):
        raise ValueError("WORKFLOW_EXPECTED_MAPPING")
    result: dict[str, object] = {}
    for key, value in node.value:
        if not isinstance(key, ScalarNode):
            raise ValueError("WORKFLOW_NONSCALAR_KEY")
        if key.value == "<<":
            raise ValueError("WORKFLOW_MERGE_KEY_UNSUPPORTED")
        if key.value in result:
            raise ValueError("WORKFLOW_DUPLICATE_KEY:" + key.value)
        result[key.value] = value
    return result


def _scalar(node) -> str:
    if not isinstance(node, ScalarNode):
        raise ValueError("WORKFLOW_EXPECTED_SCALAR")
    return node.value


def _strings(node) -> tuple[str, ...]:
    if isinstance(node, ScalarNode):
        return (_scalar(node),)
    if isinstance(node, SequenceNode):
        return tuple(_scalar(v) for v in node.value)
    raise ValueError("WORKFLOW_EXPECTED_STRING_OR_SEQUENCE")


def _literal(node, ancestors: frozenset[int] = frozenset()):
    """Preserve source-declared YAML structure, not interpreted runtime semantics."""
    if id(node) in ancestors or len(ancestors) > 32:
        raise ValueError("WORKFLOW_YAML_RECURSION_OR_DEPTH")
    parents = ancestors | {id(node)}
    if isinstance(node, ScalarNode):
        return node.value
    if isinstance(node, SequenceNode):
        return [_literal(item, parents) for item in node.value]
    if isinstance(node, MappingNode):
        return {key: _literal(value, parents)
                for key, value in _mapping(node).items()}
    raise ValueError("WORKFLOW_UNSUPPORTED_YAML_NODE")


class WorkflowCollector:
    name = "workflow"
    version = "github-actions-static-v0.1"

    def supports(self, record: SourceRecord) -> bool:
        return (record.path.startswith(".github/workflows/")
                and PurePosixPath(record.path).suffix.lower() in {".yml", ".yaml"})

    def collect(
        self, source: SourceInput, request: ScanRequest, scope_id: str
    ) -> CollectionResult:
        record = source.record
        if not self.supports(record):
            return CollectionResult(FactBatch(), "UNSUPPORTED",
                                    ("NOT_WORKFLOW_SOURCE",))
        try:
            text = source.content.decode("utf-8", "strict")
        except UnicodeDecodeError as exc:
            raise ValueError("WORKFLOW_NOT_UTF8") from exc
        document = yaml.compose(text, Loader=yaml.BaseLoader)
        if document is None:
            raise ValueError("EMPTY_WORKFLOW")
        root = _mapping(document)
        nodes: list[Node] = []
        edges: list[Edge] = []
        evidence: list[Evidence] = []
        unknown: list[UnresolvedTarget] = []
        unresolved: list[str] = []

        def witness(kind: str, line: int, statement: str,
                    *, unresolved_observation: bool = False) -> str:
            marker = stable_id(
                "evidence", request.repository, request.revision,
                record.path, record.blob_sha, self.version, kind,
                line, statement,
            )
            evidence.append(Evidence(
                id=marker, kind="STRUCTURAL",
                source_ref=f"{record.path}:{line}@{record.blob_sha}",
                method=self.version, scope_id=scope_id,
                observation_status=("UNRESOLVED" if unresolved_observation
                                    else "SOURCE_DECLARED"),
                attributes={
                    "blob_sha": record.blob_sha, "revision": request.revision,
                    "path": record.path, "line": line,
                    "parser": "PyYAML.BaseLoader", "schema_version": self.version,
                },
            ))
            return marker

        def make_node(kind: str, path_key: tuple[str, ...], name: str,
                      line: int, eid: str, *, attributes=None) -> str:
            uid = stable_id("node", request.repository, kind, *path_key)
            nodes.append(Node(
                id=uid, kind=kind, name=name,
                qualified_name=":".join((record.path, *path_key)),
                location=SourceLocation(record.path, line),
                attributes=attributes or {}, evidence_ids=(eid,),
            ))
            return uid

        def make_edge(src: str, dst: str, relation: str,
                      eid: str, discriminator: str = "",
                      *, attributes=None) -> None:
            edges.append(Edge(
                id=graph_edge_id(src, dst, relation, discriminator),
                source_id=src, target_id=dst, relation=relation,
                discriminator=discriminator or None,
                attributes=attributes or {}, evidence_ids=(eid,),
            ))

        def unresolved_target(kind: str, identity: tuple[str, ...], name: str,
                              line: int, message: str):
            eid = witness(kind, line, name, unresolved_observation=True)
            target_id = stable_id("node", request.repository, kind, *identity)
            unknown.append(UnresolvedTarget(target_id, name, eid))
            unresolved.append(message)
            return target_id, eid

        workflow_eid = witness("workflow", document.start_mark.line + 1, record.path)
        workflow_id = make_node(
            "workflow", ("workflow", record.path), PurePosixPath(record.path).name,
            document.start_mark.line + 1, workflow_eid,
        )
        make_edge(
            file_node_id(request.repository, record.path), workflow_id,
            "DECLARES_WORKFLOW", workflow_eid,
        )
        events = root.get("on")
        if events is None:
            unresolved.append("MISSING_WORKFLOW_EVENTS")
        else:
            event_configs = (
                _mapping(events) if isinstance(events, MappingNode)
                else {event: None for event in _strings(events)}
            )
            event_key_lines = (
                {key.value: key.start_mark.line + 1 for key, _ in events.value}
                if isinstance(events, MappingNode) else {}
            )
            if not event_configs:
                unresolved.append("NO_DECLARED_WORKFLOW_EVENTS")
            for event, config_node in event_configs.items():
                line = event_key_lines.get(event, events.start_mark.line + 1)
                eid = witness("event", line, event)
                event_id = stable_id("node", request.repository, "event", event)
                nodes.append(Node(id=event_id, kind="workflow_event", name=event,
                                  evidence_ids=(eid,)))
                config = _literal(config_node) if config_node is not None else None
                make_edge(
                    workflow_id, event_id, "DECLARES_TRIGGER", eid, event,
                    attributes={"filter_declaration": config},
                )
                if config is not None and "${{" in str(config):
                    unresolved.append(f"DYNAMIC_EVENT_FILTER:{event}")

        jobs_node = root.get("jobs")
        if jobs_node is None:
            unresolved.append("MISSING_WORKFLOW_JOBS")
            jobs = {}
        else:
            jobs = _mapping(jobs_node)
            if not jobs:
                unresolved.append("NO_DECLARED_WORKFLOW_JOBS")
        job_key_lines = (
            {key.value: key.start_mark.line + 1 for key, _ in jobs_node.value}
            if isinstance(jobs_node, MappingNode) else {}
        )
        job_ids = {
            key: stable_id("node", request.repository, "workflow_job", record.path, key)
            for key in jobs
        }
        for job_name, job_spec in jobs.items():
            job_data = _mapping(job_spec)
            line = job_key_lines[job_name]
            job_eid = witness("job", line, job_name)
            job_id = make_node(
                "workflow_job", (record.path, job_name), job_name, line,
                job_eid, attributes={"static_config": {
                    key: _literal(value) for key, value in job_data.items()
                    if key not in {"steps", "needs"}
                }},
            )
            if job_id != job_ids[job_name]:
                raise ValueError("INTERNAL_JOB_ID_DISAGREEMENT")
            make_edge(workflow_id, job_id, "DECLARES_JOB", job_eid, job_name)

            needs_node = job_data.get("needs")
            if needs_node is not None:
                for dependency in _strings(needs_node):
                    dep_line = needs_node.start_mark.line + 1
                    if "${{" in dependency or dependency not in job_ids:
                        target, eid = unresolved_target(
                            "external_job", (record.path, dependency),
                            dependency, dep_line,
                            f"UNRESOLVED_JOB_DEPENDENCY:{job_name}:{dependency}",
                        )
                        make_edge(job_id, target, "NEEDS_JOB_CANDIDATE",
                                  eid, dependency)
                    else:
                        eid = witness("needs", dep_line,
                                      f"{job_name}->{dependency}")
                        make_edge(job_id, job_ids[dependency], "NEEDS_JOB",
                                  eid, dependency)

            if_node = job_data.get("if")
            if if_node is not None:
                unresolved.append(f"DYNAMIC_JOB_CONDITION:{job_name}"
                                  if "${{" in _scalar(if_node)
                                  else f"JOB_CONDITION_NOT_EVALUATED:{job_name}")
            strategy = job_data.get("strategy")
            if strategy is not None:
                if "matrix" in _mapping(strategy):
                    unresolved.append(f"MATRIX_EXPANSION_NOT_OBSERVED:{job_name}")

            value = job_data.get("uses")
            if value is not None:
                val = _scalar(value)
                line = value.start_mark.line + 1
                eid = witness("reusable", line, val)
                target = stable_id("node", request.repository,
                                   "reusable_workflow", val)
                nodes.append(Node(id=target, kind="declared_reusable",
                                  name=val, evidence_ids=(eid,)))
                make_edge(job_id, target, "DECLARES_REUSABLE_WORKFLOW",
                          eid, val)
                if "${{" in val:
                    unresolved.append(f"DYNAMIC_REUSABLE_WORKFLOW:{job_name}")

            steps_node = job_data.get("steps")
            if steps_node is None:
                if "uses" not in job_data:
                    unresolved.append(f"JOB_HAS_NO_STATIC_STEPS:{job_name}")
                continue
            if not isinstance(steps_node, SequenceNode):
                raise ValueError("WORKFLOW_STEPS_MUST_BE_SEQUENCE")
            for idx, raw_step in enumerate(steps_node.value, start=1):
                step_data = _mapping(raw_step)
                step_line = raw_step.start_mark.line + 1
                explicit_id = _scalar(step_data["id"]) if "id" in step_data else f"index:{idx}"
                step_name = (
                    _scalar(step_data["name"]) if "name" in step_data else explicit_id
                )
                eid = witness("step", step_line, f"{job_name}:{explicit_id}")
                step_id = make_node(
                    "workflow_step", (record.path, job_name, explicit_id),
                    step_name, step_line, eid, attributes={"static_config": {
                        key: _literal(value) for key, value in step_data.items()
                        if key not in {"run", "uses"}
                    }},
                )
                make_edge(job_id, step_id, "DECLARES_STEP", eid, explicit_id)
                step_if = step_data.get("if")
                if step_if is not None:
                    unresolved.append(
                        f"DYNAMIC_STEP_CONDITION:{job_name}:{explicit_id}"
                        if "${{" in _scalar(step_if)
                        else f"STEP_CONDITION_NOT_EVALUATED:{job_name}:{explicit_id}"
                    )
                for key, relation, kind in (
                    ("run", "DECLARES_RUN_COMMAND", "declared_command"),
                    ("uses", "DECLARES_ACTION_USE", "declared_action"),
                ):
                    item = step_data.get(key)
                    if item is None:
                        continue
                    val = _scalar(item)
                    item_line = item.start_mark.line + 1
                    value_eid = witness(key, item_line,
                                        f"{job_name}:{explicit_id}:{val}")
                    target = stable_id(
                        "node", request.repository, kind,
                        record.path, job_name, explicit_id, key,
                    )
                    nodes.append(Node(
                        id=target, kind=kind, name=val.splitlines()[0][:120] if val else "(empty)",
                        qualified_name=f"{record.path}:{job_name}:{explicit_id}:{key}",
                        location=SourceLocation(record.path, item_line),
                        attributes={"declaration": val},
                        evidence_ids=(value_eid,),
                    ))
                    make_edge(step_id, target, relation, value_eid, key)
                    if "${{" in val:
                        unresolved.append(f"DYNAMIC_{key.upper()}:{job_name}:{explicit_id}")

        batch = FactBatch(
            nodes=tuple(nodes), edges=tuple(edges), evidence=tuple(evidence),
            unresolved_targets=tuple(unknown),
            unresolved=tuple(sorted(set(unresolved))),
        )
        return CollectionResult(
            batch,
            status="PARTIAL" if unresolved else "COMPLETE",
        )


__all__ = ["WorkflowCollector"]
