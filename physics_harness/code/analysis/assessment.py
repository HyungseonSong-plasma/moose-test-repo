"""Fail-closed generic Evidence → conditional assessment, never auto-approval."""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..graph import Claim, GraphSnapshot


@dataclass(frozen=True, slots=True)
class Assessment:
    claim: Claim
    disposition: str
    blockers: tuple[str, ...]
    verification_obligations: tuple[str, ...]

    @property
    def actionable_without_verification(self) -> bool:
        """Never authorize mutations from static or mixed evidence alone."""
        return False


def assess_finding(
    graph: GraphSnapshot,
    claim: Claim,
    *,
    required_evidence_kinds: tuple[str, ...] = (),
    verification_obligations: tuple[str, ...] = (),
) -> Assessment:
    """Rank review candidates; only a separate verification gate can approve.

    COMPLETE is limited to graph Scope, and source declarations are not
    runtime observations. Unsupported/missing evidence always means HOLD.
    """
    if not isinstance(graph, GraphSnapshot) or not isinstance(claim, Claim):
        raise TypeError("assess_finding requires GraphSnapshot and Claim")
    if claim.scope_id != graph.scope.id:
        raise ValueError("CROSS_SCOPE_FINDING")
    if not isinstance(required_evidence_kinds, tuple) or not isinstance(
        verification_obligations, tuple
    ):
        raise TypeError("requirements must be tuples")

    subject_ids = {n.id for n in graph.nodes} | {e.id for e in graph.edges}
    if any(s not in subject_ids for s in claim.subject_refs):
        raise ValueError("UNKNOWN_FINDING_SUBJECT")

    source_evidence = graph.evidence_by_id()
    supporting = []
    refuting = []
    qualifying = []
    for link in claim.evidence_refs:
        if link.evidence_id not in source_evidence:
            raise ValueError(f"UNKNOWN_FINDING_EVIDENCE:{link.evidence_id}")
        ev = source_evidence[link.evidence_id]
        if link.role == "SUPPORTS":
            supporting.append(ev)
        elif link.role == "REFUTES":
            refuting.append(ev)
        else:
            qualifying.append(ev)

    blockers: set[str] = set(graph.scope.unresolved)
    if graph.scope.completeness != "COMPLETE":
        blockers.add(f"INCOMPLETE_GRAPH_SCOPE:{graph.scope.completeness}")
    if not supporting:
        blockers.add("NO_SUPPORTING_EVIDENCE")
    if not required_evidence_kinds:
        blockers.add("REQUIRED_EVIDENCE_CONTRACT_MISSING")
    present_kinds = {ev.kind for ev in supporting}
    for kind in required_evidence_kinds:
        if kind not in present_kinds:
            blockers.add(f"REQUIRED_EVIDENCE_MISSING:{kind}")
    if qualifying:
        blockers.add("QUALIFYING_EVIDENCE_REQUIRES_REVIEW")
    if claim.conditions:
        blockers.add("CONDITIONAL_ASSUMPTIONS_NOT_VERIFIED")

    for ev in (*supporting, *refuting, *qualifying):
        if ev.observation_status == "UNRESOLVED":
            blockers.add(f"UNRESOLVED_EVIDENCE:{ev.id}")
        if ev.observation_status == "RUNTIME_OBSERVED":
            if ev.attributes.get("source_sha") != graph.scope.revision:
                blockers.add(f"CROSS_HEAD_RUNTIME_EVIDENCE:{ev.id}")

    if refuting:
        status, disposition = "REFUTED", "BLOCKED"
        blockers.add("REFUTING_EVIDENCE")
    elif blockers:
        status, disposition = "UNRESOLVED", "HOLD"
    else:
        status, disposition = "QUALIFIED", "CANDIDATE_FOR_VERIFICATION"

    updated_claim = replace(claim, assessment_status=status)
    return Assessment(
        claim=updated_claim, disposition=disposition,
        blockers=tuple(sorted(blockers)),
        verification_obligations=tuple(sorted(set(verification_obligations))),
    )


@dataclass(frozen=True, slots=True)
class ParameterBlockAssessment:
    """Source-only comparison for one MOOSE .i block."""

    block_id: str
    invalid_enum_values: tuple[str, ...]
    unknown: tuple[str, ...]

    @property
    def disposition(self) -> str:
        if self.invalid_enum_values:
            return "BLOCKED"
        if self.unknown:
            return "HOLD"
        return "CANDIDATE_FOR_VERIFICATION"


@dataclass(frozen=True, slots=True)
class ParameterContractAssessment:
    target_id: str
    blocks: tuple[ParameterBlockAssessment, ...]
    blockers: tuple[str, ...]
    disposition: str
    verification_obligations: tuple[str, ...]

    @property
    def actionable_without_verification(self) -> bool:
        return False


def assess_input_parameter_contract(
    graph: GraphSnapshot, target_id: str,
) -> ParameterContractAssessment:
    """Compare literal .i values with exact-source C++ validParams declarations.

    This checks only explicitly declared enum choices and parameter names.
    Inherited parameters, default injection, generated inputs and runtime
    values cannot be inferred from these source facts.
    """
    if not isinstance(graph, GraphSnapshot):
        raise TypeError("graph must be a GraphSnapshot")
    nodes = graph.nodes_by_id()
    target = nodes.get(target_id)
    if target is None or target.kind != "moose_type":
        raise ValueError("UNKNOWN_PARAMETER_CONTRACT_TYPE")

    contracts = {}
    inputs = set()
    for edge in graph.edges:
        if edge.source_id == target_id and edge.relation == "DECLARES_PARAM_CONTRACT":
            contract = nodes[edge.target_id]
            if contract.kind != "moose_param_contract":
                raise ValueError("INVALID_PARAMETER_CONTRACT_NODE")
            contracts[contract.name] = contract
        if edge.target_id == target_id and edge.relation == "DECLARES_TYPE_USE":
            block = nodes[edge.source_id]
            if block.kind != "moose_input_block":
                raise ValueError("INVALID_PARAMETER_INPUT_NODE")
            inputs.add(edge.source_id)

    global_blockers: set[str] = set(graph.scope.unresolved)
    if graph.scope.completeness != "COMPLETE":
        global_blockers.add("INCOMPLETE_SOURCE_SCOPE")
    if not contracts:
        global_blockers.add("CPP_VALIDPARAMS_CONTRACT_NOT_OBSERVED")
    if not inputs:
        global_blockers.add("INPUT_CONSUMER_NOT_OBSERVED")

    checks = []
    for block_id in sorted(inputs):
        block = nodes[block_id]
        raw_values = block.attributes.get("parameter_values")
        if not isinstance(raw_values, tuple):
            checks.append(ParameterBlockAssessment(
                block_id, (), ("INPUT_PARAMETER_VALUES_NOT_COLLECTED",),
            ))
            continue
        values = dict(raw_values)
        invalid = set()
        unknown = set()
        for name, contract in sorted(contracts.items()):
            cpp_type = contract.attributes.get("parameter_type")
            if name not in values:
                if contract.attributes.get("required"):
                    unknown.add(f"REQUIRED_PARAM_NOT_EXPLICIT:{name}")
                continue
            raw = values[name].strip()
            value = raw[1:-1] if (
                len(raw) >= 2 and raw[0] in {"'", '"'} and raw[-1] == raw[0]
            ) else raw
            if "$" in value or "{" in value or "}" in value:
                unknown.add(f"DYNAMIC_PARAMETER_VALUE:{name}")
                continue
            if cpp_type == "MooseEnum":
                options = contract.attributes.get("enum_options", ())
                if not options:
                    unknown.add(f"ENUM_OPTIONS_NOT_OBSERVED:{name}")
                elif value not in options:
                    invalid.add(f"INVALID_DECLARED_ENUM:{name}:{value}")
        checks.append(ParameterBlockAssessment(
            block_id, tuple(sorted(invalid)), tuple(sorted(unknown)),
        ))

    if any(c.invalid_enum_values for c in checks):
        disposition = "BLOCKED"
    elif global_blockers or any(c.unknown for c in checks):
        disposition = "HOLD"
    else:
        disposition = "CANDIDATE_FOR_VERIFICATION"

    return ParameterContractAssessment(
        target_id=target_id, blocks=tuple(checks),
        blockers=tuple(sorted(global_blockers)),
        disposition=disposition,
        verification_obligations=(
            "INHERITED_DEFAULT_PARAMETERS_UNVERIFIED",
            "NATIVE_RUNTIME_INPUT_VALIDATION",
            "SEMANTIC_UNIT_COMPATIBILITY_UNVERIFIED",
        ),
    )


__all__ = [
    "Assessment", "assess_finding",
    "ParameterBlockAssessment", "ParameterContractAssessment",
    "assess_input_parameter_contract",
]

