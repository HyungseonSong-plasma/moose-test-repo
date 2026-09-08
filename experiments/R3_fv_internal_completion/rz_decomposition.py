"""Pinned-MOOSE RZ Green-Gauss constant-state arithmetic reconstruction.

This is a read-only numerical reproducer for the interior-cell branch of
GreenGaussGradient.h at MOOSE commit 9f388366ccf. It does not alter geometry.
Boundary cells are excluded so two-term extrapolated-boundary equations do not
enter the comparison.

For the accepted qvt input, ``rz_coord_axis = Y`` names the symmetry/axial
axis. MOOSE therefore uses X (component 0) as the radial coordinate. The
reproducer defaults to that same radial axis.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class Element2D:
    tag: int
    node_tags: tuple[int, ...]


@dataclass(frozen=True)
class ParsedMesh2D:
    nodes: dict[int, tuple[float, float, float]]
    elements: tuple[Element2D, ...]


_ELEMENT_CORNERS = {
    2: 3,
    3: 4,
    9: 3,
    10: 4,
    16: 4,
}


def _section(lines: list[str], name: str) -> list[str]:
    start_token = f"${name}"
    end_token = f"$End{name}"
    try:
        start = lines.index(start_token) + 1
        end = lines.index(end_token, start)
    except ValueError as exc:
        raise ValueError(f"missing Gmsh section {name}") from exc
    return lines[start:end]


def _parse_physical_names(lines: list[str]) -> dict[tuple[int, int], str]:
    section = _section(lines, "PhysicalNames")
    count = int(section[0])
    result: dict[tuple[int, int], str] = {}
    for line in section[1 : 1 + count]:
        head, quoted = line.split('"', 1)
        name = quoted.rsplit('"', 1)[0]
        dim_s, tag_s = head.split()[:2]
        result[(int(dim_s), int(tag_s))] = name
    return result


def _parse_surface_entities(lines: list[str]) -> dict[int, tuple[int, ...]]:
    section = _section(lines, "Entities")
    n_points, n_curves, n_surfaces, n_volumes = map(int, section[0].split())
    cursor = 1 + n_points + n_curves
    result: dict[int, tuple[int, ...]] = {}
    for line in section[cursor : cursor + n_surfaces]:
        tokens = line.split()
        tag = int(tokens[0])
        num_physical = int(tokens[7])
        physical = tuple(int(value) for value in tokens[8 : 8 + num_physical])
        result[tag] = physical
    cursor += n_surfaces + n_volumes
    return result


def _parse_nodes(lines: list[str]) -> dict[int, tuple[float, float, float]]:
    section = _section(lines, "Nodes")
    num_blocks, num_nodes, _min_tag, _max_tag = map(int, section[0].split())
    cursor = 1
    nodes: dict[int, tuple[float, float, float]] = {}
    seen = 0
    for _ in range(num_blocks):
        entity_dim, _entity_tag, parametric, block_count = map(int, section[cursor].split())
        cursor += 1
        tags: list[int] = []
        while len(tags) < block_count:
            tags.extend(int(token) for token in section[cursor].split())
            cursor += 1
        if len(tags) != block_count:
            raise ValueError("unexpected Gmsh node-tag packing")
        for tag in tags:
            coords = [float(token) for token in section[cursor].split()]
            cursor += 1
            if len(coords) < 3:
                raise ValueError(f"node {tag} has fewer than 3 coordinates")
            nodes[tag] = (coords[0], coords[1], coords[2])
            if parametric and len(coords) < 3 + entity_dim:
                raise ValueError(f"node {tag} missing parametric coordinates")
        seen += block_count
    if seen != num_nodes:
        raise ValueError(f"node count mismatch: parsed={seen}, header={num_nodes}")
    return nodes


def _parse_elements(lines: list[str], plasma_entities: set[int]) -> tuple[Element2D, ...]:
    section = _section(lines, "Elements")
    num_blocks, _num_elements, _min_tag, _max_tag = map(int, section[0].split())
    cursor = 1
    result: list[Element2D] = []
    for _ in range(num_blocks):
        entity_dim, entity_tag, element_type, block_count = map(int, section[cursor].split())
        cursor += 1
        corner_count = _ELEMENT_CORNERS.get(element_type)
        for _element in range(block_count):
            tokens = [int(token) for token in section[cursor].split()]
            cursor += 1
            if entity_dim != 2 or entity_tag not in plasma_entities:
                continue
            if corner_count is None:
                raise ValueError(f"unsupported plasma element type {element_type}")
            if len(tokens) < 1 + corner_count:
                raise ValueError("malformed Gmsh element row")
            result.append(Element2D(tokens[0], tuple(tokens[1 : 1 + corner_count])))
    if not result:
        raise ValueError("no plasma surface elements found")
    return tuple(result)


def parse_gmsh41_plasma(path: Path, physical_name: str = "plasma") -> ParsedMesh2D:
    lines = [line.strip() for line in path.read_text().splitlines()]
    mesh_format = _section(lines, "MeshFormat")
    if not mesh_format or not mesh_format[0].startswith("4.1 0 "):
        raise ValueError("only ASCII Gmsh 4.1 meshes are supported")
    physical = _parse_physical_names(lines)
    surface_entities = _parse_surface_entities(lines)
    plasma_tags = {tag for (dim, tag), name in physical.items() if dim == 2 and name == physical_name}
    if not plasma_tags:
        raise ValueError(f"missing 2D physical group {physical_name!r}")
    plasma_entities = {
        entity_tag
        for entity_tag, tags in surface_entities.items()
        if any(tag in plasma_tags for tag in tags)
    }
    if not plasma_entities:
        raise ValueError(f"physical group {physical_name!r} has no surface entities")
    nodes = _parse_nodes(lines)
    elements = _parse_elements(lines, plasma_entities)
    return ParsedMesh2D(nodes=nodes, elements=elements)


def _polygon_geometry(node_tags: Iterable[int], nodes: dict[int, tuple[float, float, float]]) -> tuple[list[tuple[float, float]], float, tuple[float, float]]:
    xy = [(nodes[tag][0], nodes[tag][1]) for tag in node_tags]
    twice_area = 0.0
    for index, (x0, y0) in enumerate(xy):
        x1, y1 = xy[(index + 1) % len(xy)]
        twice_area += x0 * y1 - x1 * y0
    signed_area = 0.5 * twice_area
    if signed_area == 0.0:
        raise ValueError("zero-area plasma element")
    centroid = (sum(x for x, _ in xy) / len(xy), sum(y for _, y in xy) / len(xy))
    return xy, signed_area, centroid


def _edge_key(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def _interior_element_tags(mesh: ParsedMesh2D) -> set[int]:
    owners: dict[tuple[int, int], list[int]] = {}
    for elem in mesh.elements:
        tags = elem.node_tags
        for index, a in enumerate(tags):
            b = tags[(index + 1) % len(tags)]
            owners.setdefault(_edge_key(a, b), []).append(elem.tag)
    interior: set[int] = set()
    for elem in mesh.elements:
        tags = elem.node_tags
        if all(len(owners.get(_edge_key(a, tags[(index + 1) % len(tags)]), [])) == 2 for index, a in enumerate(tags)):
            interior.add(elem.tag)
    return interior


def _decompose_element(elem: Element2D, nodes: dict[int, tuple[float, float, float]], *, n0: float, radial_axis: int) -> dict[str, object]:
    xy, signed_area, centroid = _polygon_geometry(elem.node_tags, nodes)
    orientation = 1.0 if signed_area > 0.0 else -1.0
    area = abs(signed_area)
    radius = centroid[radial_axis]
    if radius <= 0.0:
        raise ValueError(f"element {elem.tag} has non-positive RZ centroid radius {radius}")
    contributions_x: list[float] = []
    contributions_y: list[float] = []
    for index, (x0, y0) in enumerate(xy):
        x1, y1 = xy[(index + 1) % len(xy)]
        dx, dy = x1 - x0, y1 - y0
        length = math.hypot(dx, dy)
        if length == 0.0:
            raise ValueError(f"element {elem.tag} has zero-length edge")
        nx = orientation * dy / length
        ny = orientation * -dx / length
        face_centroid = ((x0 + x1) * 0.5, (y0 + y1) * 0.5)
        face_radius = face_centroid[radial_axis]
        coord = 2.0 * math.pi * face_radius
        contributions_x.append(nx * length * coord * n0)
        contributions_y.append(ny * length * coord * n0)
    naive_x = 0.0
    naive_y = 0.0
    for value in contributions_x:
        naive_x += value
    for value in contributions_y:
        naive_y += value
    fsum_x = math.fsum(contributions_x)
    fsum_y = math.fsum(contributions_y)
    volume = area * (2.0 * math.pi * radius)
    pre_rz_naive = [naive_x / volume, naive_y / volume]
    pre_rz_fsum = [fsum_x / volume, fsum_y / volume]
    rz_term = n0 / radius
    final_naive = list(pre_rz_naive)
    final_fsum = list(pre_rz_fsum)
    final_naive[radial_axis] -= rz_term
    final_fsum[radial_axis] -= rz_term
    return {
        "element_tag": elem.tag,
        "centroid": [centroid[0], centroid[1]],
        "radius": radius,
        "area": area,
        "face_sum_naive": [naive_x, naive_y],
        "face_sum_fsum": [fsum_x, fsum_y],
        "pre_rz_gradient_naive": pre_rz_naive,
        "pre_rz_gradient_fsum": pre_rz_fsum,
        "rz_subtraction": rz_term,
        "final_gradient_naive": final_naive,
        "final_gradient_fsum": final_fsum,
        "final_norm_naive": math.hypot(*final_naive),
        "final_norm_fsum": math.hypot(*final_fsum),
    }


def decompose_rz_constant_state(path: Path, *, n0: float, physical_name: str = "plasma", radial_axis: int = 0) -> dict[str, object]:
    mesh = parse_gmsh41_plasma(path, physical_name=physical_name)
    interior = _interior_element_tags(mesh)
    rows = [
        _decompose_element(elem, mesh.nodes, n0=n0, radial_axis=radial_axis)
        for elem in mesh.elements
        if elem.tag in interior
    ]
    if not rows:
        raise ValueError("no interior plasma elements available for RZ decomposition")
    worst_naive = max(rows, key=lambda row: float(row["final_norm_naive"]))
    worst_fsum = max(rows, key=lambda row: float(row["final_norm_fsum"]))
    max_naive = float(worst_naive["final_norm_naive"])
    max_fsum = float(worst_fsum["final_norm_fsum"])
    return {
        "physical_name": physical_name,
        "radial_axis": radial_axis,
        "symmetry_axis": 1 if radial_axis == 0 else 0,
        "n0": float(n0),
        "plasma_element_count": len(mesh.elements),
        "interior_element_count": len(rows),
        "max_abs_final_naive": max_naive,
        "max_abs_final_fsum": max_fsum,
        "normalized_max_abs_final_naive": max_naive / abs(n0) if n0 else 0.0,
        "normalized_max_abs_final_fsum": max_fsum / abs(n0) if n0 else 0.0,
        "worst_naive": worst_naive,
        "worst_fsum": worst_fsum,
        "rows": rows,
    }
