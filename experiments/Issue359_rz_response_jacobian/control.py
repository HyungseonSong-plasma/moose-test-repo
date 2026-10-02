#!/usr/bin/env python3
"""Issue #359: measure the real-QVT RZ electron-response Jacobian.

The diagnostic follows the qualified Issue #310 mechanism rather than importing
1D shell weights into RZ.  It creates an accepted coupled RZ operating state,
freezes that state into an Exodus fixture, advances the electron subsystem by
one physical electron step under compressed central-difference potential
perturbations, and reconstructs a sparse d(ne)/d(phi) operator on the actual
plasma-cell adjacency graph.

The first governed run measures one checkpoint (8 electron steps).  The harness
is parameterized so later checkpoints can repeat the exact measurement for
time-stationarity evidence before any production sparse correction is promoted.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict, deque
from pathlib import Path
from typing import Iterable

from experiments.Issue359_qualified_gummel_icp import run as q359
from experiments.R3_fv_internal_completion.rz_decomposition import parse_gmsh41_plasma
from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp
from physics_harness.execution.runtime import resolve_executable, run_physics, validate_executable

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DEFAULT_MESH = q359.ICP_SOURCE / "qvt.msh"
MESH_SHA256 = "a98521af2c106137f9635fe7e2c5ba9b0fd408e17c62eb7c6d3f7c1fff65a03e"
DELTA_PHI_V = 1.0e-4
MAX_RADIUS = 2


class RZResponseError(RuntimeError):
    pass


def _insert(text: str, parent: str, block: str) -> str:
    if mb.has_block(text, parent):
        return mb.insert_child_block(text, parent, block)
    return text + f"\n[{parent}]\n{block}\n[]\n"


def _inject_source_state_output(driver: str) -> str:
    driver = _insert(
        driver,
        "AuxVariables",
        """  [issue359_log_e_state]
    type = MooseVariableFVReal
  []
  [issue359_c_epsilon_state]
    type = MooseVariableFVReal
  []""",
    )
    driver = _insert(
        driver,
        "FunctorMaterials",
        f"""  [issue359_log_e_state_functor]
    type = ADParsedFunctorMaterial
    property_name = issue359_log_e_state_value
    functor_names = 'electron_density_out'
    functor_symbols = 'ne'
    expression = 'log(ne/{q359.AVOGADRO:.17g})'
  []
  [issue359_c_epsilon_state_functor]
    type = ADParsedFunctorMaterial
    property_name = issue359_c_epsilon_state_value
    functor_names = 'electron_density_out mean_energy_out'
    functor_symbols = 'ne mean_ev'
    expression = '(ne/{q359.AVOGADRO:.17g})*mean_ev'
  []""",
    )
    driver = _insert(
        driver,
        "AuxKernels",
        """  [issue359_log_e_state_copy]
    type = FunctorAux
    variable = issue359_log_e_state
    functor = issue359_log_e_state_value
    execute_on = 'TIMESTEP_END'
  []
  [issue359_c_epsilon_state_copy]
    type = FunctorAux
    variable = issue359_c_epsilon_state
    functor = issue359_c_epsilon_state_value
    execute_on = 'TIMESTEP_END'
  []""",
    )
    driver = _insert(
        driver,
        "VectorPostprocessors",
        """  [issue359_state_profile]
    type = ElementValueSampler
    variable = 'issue359_log_e_state issue359_c_epsilon_state potential_from_poisson electron_density_out mean_energy_out p_gas_h T_g_h'
    sort_by = id
    execute_on = 'FINAL'
  []""",
    )
    driver = _insert(
        driver,
        "Outputs",
        """  [issue359_state_exodus]
    type = Exodus
    execute_on = 'FINAL'
  []""",
    )
    return driver


def _source_case(exe: Path, root: Path, timeout: float) -> tuple[Path, Path, float]:
    case = root / "source_case"
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)

    q359._stage(
        case,
        relaxation_factor=0.90,
        fixed_point_algorithm="steffensen",
        fixed_point_rel_tol=1.0e-2,
        potential_predictor_alpha=0.50,
        reuse_preconditioner=True,
        reuse_preconditioner_max_linear_its=20,
        response_strength=0.50,
        response_radius=1,
        response_mode="graph",
        electron_substeps=4,
        heavy_steps=1,
    )
    driver_path = case / "gummel_driver.i"
    driver_path.write_text(
        _inject_source_state_output(driver_path.read_text()),
        encoding="utf-8",
    )

    for name in ("electron_sub.i", "poisson_sub.i", "gummel_driver.i", "input.i"):
        check = run_physics(
            exe,
            cwd=case,
            input_name=name,
            log_path=logs / f"source_check_{name.replace('.i', '')}.log",
            extra_args=("--check-input",),
            timeout_seconds=timeout,
        )
        if check.returncode != 0:
            raise RZResponseError(f"source check-input failed for {name}")

    runtime = run_physics(
        exe,
        cwd=case,
        input_name="input.i",
        log_path=logs / "source_runtime.log",
        extra_args=(),
        timeout_seconds=timeout,
    )
    if runtime.returncode != 0:
        raise RZResponseError(
            f"source coupled operating-point run failed rc={runtime.returncode}"
        )

    exodus = sorted(case.glob("*gummel_driver0*state_exodus*.e"))
    if len(exodus) != 1:
        raise RZResponseError(f"expected one state Exodus file, found {len(exodus)}")
    return case, exodus[0], runtime.wall_seconds


def _read_profile(path: Path) -> list[dict[str, float]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise RZResponseError(f"empty profile: {path}")
    out: list[dict[str, float]] = []
    for row in rows:
        out.append({key: float(value) for key, value in row.items() if value != ""})
    out.sort(key=lambda row: int(row["id"]))
    return out


def _edge_key(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def _mesh_graph(mesh_path: Path, state_rows: list[dict[str, float]]) -> tuple[dict[int, set[int]], dict[int, tuple[float, float]]]:
    if hashlib.sha256(mesh_path.read_bytes()).hexdigest() != MESH_SHA256:
        raise RZResponseError("real-QVT mesh SHA changed")
    mesh = parse_gmsh41_plasma(mesh_path)

    sample_by_xy: dict[tuple[float, float], int] = {}
    coords: dict[int, tuple[float, float]] = {}
    for row in state_rows:
        sid = int(row["id"])
        xy = (float(row["x"]), float(row["y"]))
        key = (round(xy[0], 12), round(xy[1], 12))
        if key in sample_by_xy:
            raise RZResponseError("duplicate sampled centroid")
        sample_by_xy[key] = sid
        coords[sid] = xy

    tag_to_id: dict[int, int] = {}
    elem_nodes: dict[int, tuple[int, ...]] = {}
    for elem in mesh.elements:
        xy = [
            (mesh.nodes[node][0], mesh.nodes[node][1])
            for node in elem.node_tags
        ]
        centroid = (
            sum(x for x, _ in xy) / len(xy),
            sum(y for _, y in xy) / len(xy),
        )
        key = (round(centroid[0], 12), round(centroid[1], 12))
        sid = sample_by_xy.get(key)
        if sid is None:
            best = min(
                state_rows,
                key=lambda row: (float(row["x"]) - centroid[0]) ** 2
                + (float(row["y"]) - centroid[1]) ** 2,
            )
            distance = math.hypot(float(best["x"]) - centroid[0], float(best["y"]) - centroid[1])
            if distance > 1.0e-10:
                raise RZResponseError(
                    f"cannot map Gmsh element {elem.tag} centroid to sampled element"
                )
            sid = int(best["id"])
        tag_to_id[elem.tag] = sid
        elem_nodes[elem.tag] = elem.node_tags

    if len(tag_to_id) != len(state_rows):
        raise RZResponseError(
            f"state/mesh element-count mismatch: mesh={len(tag_to_id)} state={len(state_rows)}"
        )

    owners: dict[tuple[int, int], list[int]] = defaultdict(list)
    for tag, nodes in elem_nodes.items():
        for i, a in enumerate(nodes):
            owners[_edge_key(a, nodes[(i + 1) % len(nodes)])].append(tag)

    graph: dict[int, set[int]] = {sid: set() for sid in tag_to_id.values()}
    for tags in owners.values():
        if len(tags) == 2:
            a, b = tag_to_id[tags[0]], tag_to_id[tags[1]]
            graph[a].add(b)
            graph[b].add(a)
    return graph, coords


def _within(graph: dict[int, set[int]], start: int, cutoff: int) -> dict[int, int]:
    distance = {start: 0}
    queue: deque[int] = deque([start])
    while queue:
        node = queue.popleft()
        depth = distance[node]
        if depth >= cutoff:
            continue
        for nxt in graph[node]:
            if nxt not in distance:
                distance[nxt] = depth + 1
                queue.append(nxt)
    return distance


def _conflict_graph(graph: dict[int, set[int]], radius: int) -> dict[int, set[int]]:
    return {
        node: set(_within(graph, node, 2 * radius)) - {node}
        for node in graph
    }


def _dsatur(graph: dict[int, set[int]]) -> dict[int, int]:
    colors: dict[int, int] = {}
    saturation = {node: set() for node in graph}
    uncolored = set(graph)
    while uncolored:
        node = max(
            uncolored,
            key=lambda item: (
                len(saturation[item]),
                len(graph[item]),
                -item,
            ),
        )
        used = {colors[nbr] for nbr in graph[node] if nbr in colors}
        color = 0
        while color in used:
            color += 1
        colors[node] = color
        uncolored.remove(node)
        for nbr in graph[node]:
            if nbr in uncolored:
                saturation[nbr].add(color)
    return colors


def _color_plan(graph: dict[int, set[int]], radius: int) -> tuple[dict[int, int], dict[int, dict[int, int]]]:
    supports = {node: _within(graph, node, radius) for node in graph}
    colors = _dsatur(_conflict_graph(graph, radius))
    for row, support in supports.items():
        seen: dict[int, int] = {}
        for column in support:
            color = colors[column]
            if color in seen:
                raise RZResponseError(
                    f"invalid compressed coloring in row {row}: columns {seen[color]} and {column}"
                )
            seen[color] = column
    return colors, supports


def _simple_state_mesh(text: str) -> str:
    if mb.has_block(text, "Mesh"):
        text = mb.remove_block(text, "Mesh")
    return """[Mesh]
  type = FileMesh
  file = '../../fixture/state.e'
  coord_type = RZ
  rz_coord_axis = Y
[]

""" + text


def _from_file(text: str, path: str, source_name: str) -> str:
    text = mp.remove_parameter(text, path, "initial_condition")
    text = mp.upsert_parameter(text, path, "initial_from_file_var", source_name)
    text = mp.upsert_parameter(text, path, "initial_from_file_timestep", "LATEST")
    return text


def _standalone_input(
    base: str,
    *,
    element_ids: list[int] | None,
    scales: list[float] | None,
    amplitude: float,
) -> str:
    text = _simple_state_mesh(base)
    text = mp.upsert_parameter(
        text,
        "Problem",
        "allow_initial_conditions_with_restart",
        "true",
    )
    text = _from_file(text, "Variables/log_e", "issue359_log_e_state")
    text = _from_file(text, "Variables/c_epsilon", "issue359_c_epsilon_state")
    text = _from_file(text, "AuxVariables/potential_from_poisson", "potential_from_poisson")
    text = _from_file(text, "AuxVariables/p_gas_from_heavy", "p_gas_h")
    text = _from_file(text, "AuxVariables/T_g_from_heavy", "T_g_h")

    if element_ids:
        text = _insert(
            text,
            "AuxVariables",
            """  [issue359_potential_base]
    type = MooseVariableFVReal
    initial_from_file_var = potential_from_poisson
    initial_from_file_timestep = LATEST
  []""",
        )
        id_text = " ".join(str(value) for value in element_ids)
        scale_values = scales if scales is not None else [1.0] * len(element_ids)
        scale_text = " ".join(f"{value:.17g}" for value in scale_values)
        text = _insert(
            text,
            "AuxKernels",
            f"""  [issue359_response_perturbation]
    type = PhysicsElementFieldPerturbationAux
    variable = potential_from_poisson
    base = issue359_potential_base
    element_ids = '{id_text}'
    element_scales = '{scale_text}'
    amplitude = {amplitude:.17g}
    execute_on = 'INITIAL'
  []""",
        )

    text = mp.upsert_parameter(text, "Executioner", "dt", f"{q359.ELECTRON_DT_S:.17g}")
    text = mp.upsert_parameter(text, "Executioner", "dtmin", f"{q359.ELECTRON_DT_S:.17g}")
    text = mp.upsert_parameter(text, "Executioner", "dtmax", f"{q359.ELECTRON_DT_S:.17g}")
    text = mp.upsert_parameter(text, "Executioner", "end_time", f"{q359.ELECTRON_DT_S:.17g}")
    text = mp.upsert_parameter(text, "Executioner", "num_steps", "1")
    if mb.has_block(text, "Outputs/final_exodus"):
        text = mb.remove_block(text, "Outputs/final_exodus")
    return text


def _case_name(prefix: str, sign: int | None = None) -> str:
    if sign is None:
        return prefix
    return f"{prefix}_{'plus' if sign > 0 else 'minus'}"


def _copy_inputs(source_case: Path, case_dir: Path) -> None:
    for name in ("electron_moments.txt", "o2_elastic.txt", "transport_data.txt"):
        shutil.copy2(source_case / name, case_dir / name)


def _write_case(
    case_root: Path,
    source_case: Path,
    base_input: str,
    name: str,
    ids: list[int] | None,
    scales: list[float] | None,
    amplitude: float,
) -> None:
    case_dir = case_root / name
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "input.i").write_text(
        _standalone_input(
            base_input,
            element_ids=ids,
            scales=scales,
            amplitude=amplitude,
        ),
        encoding="utf-8",
    )
    _copy_inputs(source_case, case_dir)


def _patterns(ids: list[int], coords: dict[int, tuple[float, float]]) -> dict[str, list[float]]:
    r_values = [coords[item][0] for item in ids]
    z_values = [coords[item][1] for item in ids]
    rmax = max(max(r_values), 1.0e-30)
    zmin, zmax = min(z_values), max(z_values)
    zspan = max(zmax - zmin, 1.0e-30)
    random = [
        1.0 if ((item * 1103515245 + 12345) & 1) else -1.0
        for item in ids
    ]
    smooth = [
        math.sin(math.pi * coords[item][0] / rmax)
        * math.cos(math.pi * (coords[item][1] - zmin) / zspan)
        for item in ids
    ]
    scale = max(abs(value) for value in smooth)
    smooth = [value / scale for value in smooth]
    return {"random": random, "smooth": smooth}


def _prepare_reference_fixture(
    root: Path,
    source_case: Path,
    state_exodus: Path,
) -> None:
    fixture = root / "fixture"
    cases = root / "cases"
    fixture.mkdir(parents=True, exist_ok=True)
    cases.mkdir(parents=True, exist_ok=True)
    shutil.copy2(state_exodus, fixture / "state.e")
    shutil.copy2(source_case / "qvt.msh", fixture / "qvt.msh")
    base_input = (source_case / "electron_sub.i").read_text(encoding="utf-8")
    _write_case(cases, source_case, base_input, "reference", None, None, 0.0)


def _run_reference(exe: Path, root: Path, timeout: float) -> float:
    case = root / "cases" / "reference"
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    check = run_physics(
        exe,
        cwd=case,
        input_name="input.i",
        log_path=logs / "check_reference.log",
        extra_args=("--check-input",),
        timeout_seconds=timeout,
    )
    if check.returncode != 0:
        raise RZResponseError("standalone reference check-input failed")
    result = run_physics(
        exe,
        cwd=case,
        input_name="input.i",
        log_path=logs / "reference.log",
        extra_args=(),
        timeout_seconds=timeout,
    )
    if result.returncode != 0:
        raise RZResponseError("standalone reference response case failed")
    return result.wall_seconds


def _prepare_cases_from_reference(
    root: Path,
    source_case: Path,
    radius: int,
    delta: float,
    source_info: dict[str, object],
) -> dict[str, object]:
    cases = root / "cases"
    state_rows = _energy_profile(cases / "reference")
    graph, coords = _mesh_graph(source_case / "qvt.msh", state_rows)
    colors, supports = _color_plan(graph, radius)
    ids = sorted(graph)
    groups: dict[int, list[int]] = defaultdict(list)
    for element_id, color in colors.items():
        groups[color].append(element_id)

    base_input = (source_case / "electron_sub.i").read_text(encoding="utf-8")
    for color in sorted(groups):
        color_ids = sorted(groups[color])
        for sign in (-1, 1):
            _write_case(
                cases,
                source_case,
                base_input,
                _case_name(f"color{color:02d}", sign),
                color_ids,
                None,
                sign * delta,
            )

    for sign in (-1, 1):
        _write_case(
            cases,
            source_case,
            base_input,
            _case_name("uniform", sign),
            ids,
            [1.0] * len(ids),
            sign * delta,
        )

    patterns = _patterns(ids, coords)
    for label, values in patterns.items():
        for sign in (-1, 1):
            _write_case(
                cases,
                source_case,
                base_input,
                _case_name(f"holdout_{label}", sign),
                ids,
                values,
                sign * delta,
            )

    plan = {
        "mesh_sha256": MESH_SHA256,
        "plasma_cells": len(ids),
        "max_radius": radius,
        "delta_phi_V": delta,
        "color_count": max(colors.values()) + 1,
        "colors": {str(item): colors[item] for item in ids},
        "coordinates": {str(item): list(coords[item]) for item in ids},
        "adjacency": {str(item): sorted(graph[item]) for item in ids},
        "support_size": {
            "min": min(len(value) for value in supports.values()),
            "max": max(len(value) for value in supports.values()),
            "mean": sum(len(value) for value in supports.values()) / len(supports),
        },
        "source_fixture": source_info,
        "cases": sorted(path.name for path in cases.iterdir() if path.is_dir()),
    }
    (root / "coloring_plan.json").write_text(
        json.dumps(plan, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return plan


def _run_cases(
    exe: Path,
    root: Path,
    timeout: float,
    workers: int,
) -> tuple[dict[str, float], float]:
    cases = root / "cases"
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    names = sorted(
        path.name
        for path in cases.iterdir()
        if path.is_dir() and path.name != "reference"
    )
    first_color = next(
        value for value in names if value.startswith("color") and value.endswith("_plus")
    )
    check = run_physics(
        exe,
        cwd=cases / first_color,
        input_name="input.i",
        log_path=logs / f"check_{first_color}.log",
        extra_args=("--check-input",),
        timeout_seconds=timeout,
    )
    if check.returncode != 0:
        raise RZResponseError(f"standalone check-input failed for {first_color}")

    if workers < 1:
        raise RZResponseError("workers must be positive")

    def execute(name: str) -> tuple[str, float, int]:
        result = run_physics(
            exe,
            cwd=cases / name,
            input_name="input.i",
            log_path=logs / f"{name}.log",
            extra_args=(),
            timeout_seconds=timeout,
        )
        return name, result.wall_seconds, result.returncode

    elapsed: dict[str, float] = {}
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = {pool.submit(execute, name): name for name in names}
        completed = 0
        for future in as_completed(pending):
            name, wall_seconds, returncode = future.result()
            completed += 1
            elapsed[name] = wall_seconds
            print(
                "ISSUE359_RZ_JACOBIAN_CASE "
                + json.dumps(
                    {
                        "index": completed,
                        "count": len(names),
                        "case": name,
                        "returncode": returncode,
                        "wall_seconds": wall_seconds,
                    },
                    sort_keys=True,
                )
            )
            if returncode != 0:
                for other in pending:
                    other.cancel()
                raise RZResponseError(f"standalone response case failed: {name}")
    return elapsed, time.perf_counter() - started


def _energy_profile(case_dir: Path) -> list[dict[str, float]]:
    files = sorted(case_dir.glob("*energy_profile*.csv"))
    if not files:
        raise RZResponseError(f"missing energy profile in {case_dir}")
    return _read_profile(files[-1])


def _l2(values: Iterable[float]) -> float:
    return math.sqrt(sum(value * value for value in values))


def _central(
    plus: list[dict[str, float]],
    minus: list[dict[str, float]],
    delta: float,
    field: str,
) -> list[float]:
    return [
        (plus[i][field] - minus[i][field]) / (2.0 * delta)
        for i in range(len(plus))
    ]


def _relative_error(actual: list[float], predicted: list[float]) -> float:
    diff = _l2(a - b for a, b in zip(actual, predicted))
    return diff / max(_l2(actual), 1.0e-300)


def _analyse(root: Path, plan: dict[str, object], source_wall: float, case_elapsed: dict[str, float], diagnostic_wall: float) -> dict[str, object]:
    cases = root / "cases"
    reference = _energy_profile(cases / "reference")
    ids = [int(row["id"]) for row in reference]
    index = {item: pos for pos, item in enumerate(ids)}
    colors = {int(key): int(value) for key, value in dict(plan["colors"]).items()}
    adjacency = {int(key): set(value) for key, value in dict(plan["adjacency"]).items()}
    radius = int(plan["max_radius"])
    delta = float(plan["delta_phi_V"])
    color_count = int(plan["color_count"])

    supports = {item: _within(adjacency, item, radius) for item in ids}
    color_derivatives: dict[int, list[float]] = {}
    nonlinearity: list[float] = []
    ref_ne = [row["electron_density_out"] for row in reference]
    for color in range(color_count):
        plus = _energy_profile(cases / _case_name(f"color{color:02d}", 1))
        minus = _energy_profile(cases / _case_name(f"color{color:02d}", -1))
        color_derivatives[color] = _central(plus, minus, delta, "electron_density_out")
        odd = [plus[i]["electron_density_out"] - minus[i]["electron_density_out"] for i in range(len(ids))]
        even = [plus[i]["electron_density_out"] + minus[i]["electron_density_out"] - 2.0 * ref_ne[i] for i in range(len(ids))]
        nonlinearity.append(_l2(even) / max(_l2(odd), 1.0))

    row_offsets = [0]
    columns: list[int] = []
    distances: list[int] = []
    values: list[float] = []
    normalized: list[float] = []
    frob2 = 0.0
    shell_frob2 = {depth: 0.0 for depth in range(radius + 1)}
    for row_id in ids:
        row_pos = index[row_id]
        mean_e = reference[row_pos]["mean_energy_out"]
        ne = reference[row_pos]["electron_density_out"]
        thermal_scale = ne / max((2.0 / 3.0) * mean_e, 1.0e-300)
        for column_id, depth in sorted(supports[row_id].items()):
            value = color_derivatives[colors[column_id]][row_pos]
            columns.append(column_id)
            distances.append(depth)
            values.append(value)
            normalized.append(value / thermal_scale)
            frob2 += value * value
            shell_frob2[depth] += value * value
        row_offsets.append(len(values))

    def predict(pattern: dict[int, float], max_depth: int) -> list[float]:
        result = []
        cursor = 0
        for _row in ids:
            total = 0.0
            stop = row_offsets[len(result) + 1]
            while cursor < stop:
                if distances[cursor] <= max_depth:
                    total += values[cursor] * pattern[columns[cursor]]
                cursor += 1
            result.append(total)
        return result

    patterns: dict[str, dict[int, float]] = {}
    raw_patterns = _patterns(
        ids,
        {int(key): tuple(value) for key, value in dict(plan["coordinates"]).items()},
    )
    for label, raw in raw_patterns.items():
        patterns[label] = {item: raw[pos] for pos, item in enumerate(ids)}

    holdout_errors: dict[str, dict[str, float]] = {}
    for label, pattern in patterns.items():
        plus = _energy_profile(cases / _case_name(f"holdout_{label}", 1))
        minus = _energy_profile(cases / _case_name(f"holdout_{label}", -1))
        actual = _central(plus, minus, delta, "electron_density_out")
        holdout_errors[label] = {
            f"radius_{depth}": _relative_error(actual, predict(pattern, depth))
            for depth in range(1, radius + 1)
        }

    uniform_plus = _energy_profile(cases / _case_name("uniform", 1))
    uniform_minus = _energy_profile(cases / _case_name("uniform", -1))
    uniform_actual = _central(
        uniform_plus, uniform_minus, delta, "electron_density_out"
    )
    uniform_pattern = {item: 1.0 for item in ids}
    uniform_pred = predict(uniform_pattern, radius)
    eta_constant_mode = _l2(uniform_actual) / max(math.sqrt(frob2) * math.sqrt(len(ids)), 1.0e-300)

    summary = {
        "schema_version": 1,
        "issue": 359,
        "diagnostic": "compressed central-difference real-QVT electron response",
        "source_operating_point": {
            "electron_steps": plan.get("source_fixture", {}).get("electron_steps"),
            "electron_dt_s": q359.ELECTRON_DT_S,
            "physical_time_s": plan.get("source_fixture", {}).get("physical_time_s"),
            "source_wall_seconds": source_wall,
            "fixture": plan.get("source_fixture", {}),
            "fixed_point_rel_tol": 1.0e-2,
            "delta_phi_contract_V": 1.0e-6,
            "response_correction": "graph R1 strength 0.5 (iteration-only; vanishes at fixed point)",
            "reuse_preconditioner_max_linear_its": 20,
        },
        "mesh": {
            "sha256": plan["mesh_sha256"],
            "plasma_cells": len(ids),
        },
        "compression": {
            "max_graph_radius": radius,
            "color_count": color_count,
            "central_difference_cases": 2 * color_count,
            "delta_phi_V": delta,
            "support_size": plan["support_size"],
        },
        "linearity": {
            "max_even_to_odd_ratio": max(nonlinearity),
            "median_even_to_odd_ratio": sorted(nonlinearity)[len(nonlinearity) // 2],
        },
        "holdout_relative_l2_error": holdout_errors,
        "constant_mode": {
            "eta_J1_over_JsqrtN": eta_constant_mode,
            f"radius_{radius}_uniform_prediction_relative_error": _relative_error(
                uniform_actual, uniform_pred
            ),
        },
        "shell_frobenius_fraction": {
            str(depth): math.sqrt(value / frob2) if frob2 else None
            for depth, value in shell_frob2.items()
        },
        "stationarity": {
            "status": "NOT_YET_MEASURED",
            "next_checkpoint": "repeat the identical diagnostic at a later accepted electron-step state before production promotion",
        },
        "runtime": {
            "standalone_total_wall_seconds": diagnostic_wall,
            "case_wall_seconds": case_elapsed,
        },
        "sparse_response": {
            "row_ids": ids,
            "row_offsets": row_offsets,
            "column_ids": columns,
            "graph_distances": distances,
            "dn_e_dphi_m3_per_V": values,
            "normalized_W": normalized,
        },
        "guard": (
            "Diagnostic evidence only. No sparse response kernel is promoted by this run. "
            "R1/R2 fidelity, constant-mode response, finite-difference linearity, and "
            "time-stationarity must be inspected before production coupling changes."
        ),
    }
    (root / "sparse_response.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    compact = {
        "plasma_cells": len(ids),
        "color_count": color_count,
        "max_fd_nonlinearity": summary["linearity"]["max_even_to_odd_ratio"],
        "holdout_errors": holdout_errors,
        "constant_mode_eta": eta_constant_mode,
        "uniform_prediction_error": summary["constant_mode"]["radius_3_uniform_prediction_relative_error"],
        "shell_frobenius_fraction": summary["shell_frobenius_fraction"],
        "source_wall_seconds": source_wall,
        "standalone_wall_seconds": diagnostic_wall,
    }
    (root / "summary.json").write_text(
        json.dumps(compact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("ISSUE359_RZ_JACOBIAN_SUMMARY " + json.dumps(compact, sort_keys=True))
    return summary


def plan_only(mesh_path: Path, radius: int) -> dict[str, object]:
    mesh = parse_gmsh41_plasma(mesh_path)
    owners: dict[tuple[int, int], list[int]] = defaultdict(list)
    for elem in mesh.elements:
        nodes = elem.node_tags
        for i, a in enumerate(nodes):
            owners[_edge_key(a, nodes[(i + 1) % len(nodes)])].append(elem.tag)
    graph = {elem.tag: set() for elem in mesh.elements}
    for tags in owners.values():
        if len(tags) == 2:
            a, b = tags
            graph[a].add(b)
            graph[b].add(a)
    colors, supports = _color_plan(graph, radius)
    out = {
        "mesh_sha256": hashlib.sha256(mesh_path.read_bytes()).hexdigest(),
        "plasma_cells": len(graph),
        "max_radius": radius,
        "color_count": max(colors.values()) + 1,
        "support_min": min(len(value) for value in supports.values()),
        "support_max": max(len(value) for value in supports.values()),
        "support_mean": sum(len(value) for value in supports.values()) / len(supports),
    }
    print("ISSUE359_RZ_JACOBIAN_PLAN " + json.dumps(out, sort_keys=True))
    return out


def run(args: argparse.Namespace) -> int:
    if args.max_radius < 1 or args.max_radius > 2:
        raise RZResponseError("max radius must lie in [1, 2] for the fast discriminator")
    if args.delta_phi <= 0.0:
        raise RZResponseError("delta phi must be positive")
    if args.plan_only:
        plan = plan_only(DEFAULT_MESH, args.max_radius)
        if plan["mesh_sha256"] != MESH_SHA256:
            raise RZResponseError("plan mesh SHA changed")
        return 0

    exe = resolve_executable(args.physics)
    validate_executable(exe)
    root = args.results_root
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    source_case, state_exodus, source_wall = _source_case(
        exe, root, args.source_timeout
    )
    source_info = {
        "mode": "fresh_coupled_source_same_run_snapshot",
        "electron_steps": 4,
        "physical_time_s": 4 * q359.ELECTRON_DT_S,
    }

    _prepare_reference_fixture(root, source_case, state_exodus)
    reference_wall = _run_reference(exe, root, args.case_timeout)
    plan = _prepare_cases_from_reference(
        root,
        source_case,
        args.max_radius,
        args.delta_phi,
        source_info,
    )
    case_elapsed, perturbation_wall = _run_cases(
        exe,
        root,
        args.case_timeout,
        args.workers,
    )
    _analyse(
        root,
        plan,
        source_wall,
        case_elapsed,
        reference_wall + perturbation_wall,
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--physics")
    parser.add_argument("--results-root", type=Path, default=Path("issue359-rz-jacobian"))
    parser.add_argument("--source-timeout", type=float, default=360.0)
    parser.add_argument("--case-timeout", type=float, default=30.0)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--max-radius", type=int, default=MAX_RADIUS)
    parser.add_argument("--delta-phi", type=float, default=DELTA_PHI_V)
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()
    if not args.plan_only and not args.physics:
        parser.error("--physics is required unless --plan-only is used")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
