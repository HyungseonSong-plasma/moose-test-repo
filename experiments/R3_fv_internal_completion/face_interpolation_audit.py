"""QPX-free audit of constant-face interpolation in the pinned MOOSE Green-Gauss path.

The existing RZ decomposer intentionally assumes ``field_face == field_cell``.
This module tests that assumption on the accepted qvt mesh by replaying the
pinned MOOSE formulas for ``FaceInfo::gC`` and average ``linearInterpolation``.
It is evidence production only: no scientific owner is assigned here.

Pinned source contract (MOOSE 9f388366ccf):

* ``ElemInfo::centroid()`` is ``elem->vertex_average()``;
* ``FaceInfo::faceCentroid()`` is the side vertex average;
* same-level internal ``FaceInfo`` ownership goes to the lower element id;
* ``FaceInfo::gC`` is built from the owner-cell line / face-plane intersection;
* central face value is ``gC * elem + (1 - gC) * neighbor``;
* RZ face surface vector is ``normal * faceArea * 2*pi*r_face``;
* RZ cell volume is ``elemVolume * 2*pi*r_cell``;
* the radial Green-Gauss component finally subtracts ``field_cell / r_cell``.

The accepted qvt audit is restricted to linear TRI3/QUAD4 plasma element
blocks.  A future higher-order/curved plasma mesh fails closed instead of being
silently reduced to corner geometry.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from .rz_decomposition import (
    Element2D,
    ParsedMesh2D,
    _edge_key,
    _parse_physical_names,
    _parse_surface_entities,
    _polygon_geometry,
    _section,
    parse_gmsh41_plasma,
)

_LINEAR_2D_GMSH_TYPES = {2, 3}  # TRI3, QUAD4


def moose_constant_linear_interpolation(value: float, gc: float) -> float:
    """Replay the pinned MOOSE arithmetic order for equal cell values."""
    return gc * value + (1.0 - gc) * value


def _assert_linear_plasma_blocks(path: Path, physical_name: str) -> tuple[int, ...]:
    lines = [line.strip() for line in path.read_text().splitlines()]
    physical = _parse_physical_names(lines)
    surfaces = _parse_surface_entities(lines)
    physical_tags = {
        tag for (dim, tag), name in physical.items() if dim == 2 and name == physical_name
    }
    plasma_entities = {
        entity_tag
        for entity_tag, tags in surfaces.items()
        if any(tag in physical_tags for tag in tags)
    }
    if not plasma_entities:
        raise ValueError(f"physical group {physical_name!r} has no surface entities")

    section = _section(lines, "Elements")
    num_blocks = int(section[0].split()[0])
    cursor = 1
    element_types: set[int] = set()
    for _ in range(num_blocks):
        entity_dim, entity_tag, element_type, block_count = map(int, section[cursor].split())
        cursor += 1
        if entity_dim == 2 and entity_tag in plasma_entities:
            element_types.add(element_type)
        cursor += block_count

    if not element_types:
        raise ValueError(f"no element blocks found for physical group {physical_name!r}")
    unsupported = element_types - _LINEAR_2D_GMSH_TYPES
    if unsupported:
        raise ValueError(
            "face interpolation audit only supports linear TRI3/QUAD4 plasma blocks; "
            f"found Gmsh element types {sorted(unsupported)}"
        )
    return tuple(sorted(element_types))


def _cell_geometry(mesh: ParsedMesh2D) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for elem in mesh.elements:
        xy, signed_area, centroid = _polygon_geometry(elem.node_tags, mesh.nodes)
        result[elem.tag] = {
            "element": elem,
            "xy": xy,
            "signed_area": signed_area,
            "area": abs(signed_area),
            "centroid": centroid,
        }
    return result


def _edge_owners(mesh: ParsedMesh2D) -> dict[tuple[int, int], list[tuple[int, int]]]:
    owners: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for elem in mesh.elements:
        tags = elem.node_tags
        for local_side, node_a in enumerate(tags):
            node_b = tags[(local_side + 1) % len(tags)]
            owners.setdefault(_edge_key(node_a, node_b), []).append((elem.tag, local_side))
    return owners


def _internal_cell_tags(
    mesh: ParsedMesh2D,
    owners: dict[tuple[int, int], list[tuple[int, int]]],
) -> set[int]:
    result: set[int] = set()
    for elem in mesh.elements:
        tags = elem.node_tags
        if all(
            len(owners.get(_edge_key(node_a, tags[(side + 1) % len(tags)]), ())) == 2
            for side, node_a in enumerate(tags)
        ):
            result.add(elem.tag)
    return result


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _dot(a: tuple[float, float], b: tuple[float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _side_geometry(
    elem: Element2D,
    local_side: int,
    geometry: dict[int, dict[str, Any]],
    nodes: dict[int, tuple[float, float, float]],
) -> dict[str, Any]:
    cell = geometry[elem.tag]
    orientation = 1.0 if float(cell["signed_area"]) > 0.0 else -1.0
    node_a = elem.node_tags[local_side]
    node_b = elem.node_tags[(local_side + 1) % len(elem.node_tags)]
    x0, y0 = nodes[node_a][0], nodes[node_a][1]
    x1, y1 = nodes[node_b][0], nodes[node_b][1]
    dx, dy = x1 - x0, y1 - y0
    face_area = math.hypot(dx, dy)
    if face_area == 0.0:
        raise ValueError(f"element {elem.tag} side {local_side} has zero face area")
    return {
        "node_a": node_a,
        "node_b": node_b,
        "face_area": face_area,
        "face_centroid": ((x0 + x1) * 0.5, (y0 + y1) * 0.5),
        "normal": (orientation * dy / face_area, orientation * -dx / face_area),
    }


def _face_info_gc(
    *,
    face_info_elem: Element2D,
    face_info_side: int,
    face_info_neighbor_tag: int,
    geometry: dict[int, dict[str, Any]],
    nodes: dict[int, tuple[float, float, float]],
) -> tuple[float, dict[str, Any]]:
    side = _side_geometry(face_info_elem, face_info_side, geometry, nodes)
    centroid = geometry[face_info_elem.tag]["centroid"]
    neighbor_centroid = geometry[face_info_neighbor_tag]["centroid"]
    normal = side["normal"]
    face_centroid = side["face_centroid"]

    d_cn = (
        neighbor_centroid[0] - centroid[0],
        neighbor_centroid[1] - centroid[1],
    )
    d_cn_mag = math.hypot(*d_cn)
    if d_cn_mag == 0.0:
        raise ValueError(
            f"elements {face_info_elem.tag}/{face_info_neighbor_tag} have coincident centroids"
        )
    e_cn = (d_cn[0] / d_cn_mag, d_cn[1] / d_cn_mag)
    denominator = _dot(e_cn, normal)
    if denominator == 0.0:
        raise ValueError(
            f"FaceInfo owner {face_info_elem.tag} side {face_info_side} has eCN dot normal == 0"
        )

    centroid_to_face = (
        face_centroid[0] - centroid[0],
        face_centroid[1] - centroid[1],
    )
    intersection_distance = _dot(centroid_to_face, normal) / denominator
    r_intersection = (
        centroid[0] + intersection_distance * e_cn[0],
        centroid[1] + intersection_distance * e_cn[1],
    )
    gc = _distance(neighbor_centroid, r_intersection) / d_cn_mag
    return gc, side


def _face_row(
    *,
    elem: Element2D,
    local_side: int,
    neighbor_tag: int,
    shared: list[tuple[int, int]],
    element_by_tag: dict[int, Element2D],
    geometry: dict[int, dict[str, Any]],
    nodes: dict[int, tuple[float, float, float]],
    n0: float,
    radial_axis: int,
) -> dict[str, Any]:
    # On the accepted, unrefined qvt mesh the pinned elemHasFaceInfo rule chooses
    # the lower same-level element id. Gmsh element tags preserve that ordering.
    face_info_elem_tag, face_info_side = min(shared, key=lambda pair: pair[0])
    face_info_neighbor_tag = next(tag for tag, _side in shared if tag != face_info_elem_tag)
    gc, canonical_side = _face_info_gc(
        face_info_elem=element_by_tag[face_info_elem_tag],
        face_info_side=face_info_side,
        face_info_neighbor_tag=face_info_neighbor_tag,
        geometry=geometry,
        nodes=nodes,
    )

    current_side = _side_geometry(elem, local_side, geometry, nodes)
    face_centroid = current_side["face_centroid"]
    normal = current_side["normal"]
    face_area = float(current_side["face_area"])
    face_value = moose_constant_linear_interpolation(n0, gc)
    face_delta = face_value - n0

    face_radius = face_centroid[radial_axis]
    if face_radius < 0.0:
        raise ValueError(
            f"element {elem.tag} side {local_side} has negative RZ face radius {face_radius}"
        )
    coord_factor = 2.0 * math.pi * face_radius
    surface_x = normal[0] * face_area * coord_factor
    surface_y = normal[1] * face_area * coord_factor
    centroid = geometry[elem.tag]["centroid"]
    neighbor_centroid = geometry[neighbor_tag]["centroid"]

    return {
        "element_tag": elem.tag,
        "neighbor_tag": neighbor_tag,
        "local_side": local_side,
        "face_info_elem_tag": face_info_elem_tag,
        "face_info_neighbor_tag": face_info_neighbor_tag,
        "face_info_side": face_info_side,
        "node_a": current_side["node_a"],
        "node_b": current_side["node_b"],
        "cell_x": centroid[0],
        "cell_y": centroid[1],
        "neighbor_x": neighbor_centroid[0],
        "neighbor_y": neighbor_centroid[1],
        "face_x": face_centroid[0],
        "face_y": face_centroid[1],
        "normal_x": normal[0],
        "normal_y": normal[1],
        "face_area": face_area,
        "canonical_face_area": canonical_side["face_area"],
        "gc": gc,
        "gc_below_zero": gc < 0.0,
        "gc_above_one": gc > 1.0,
        "field_cell": n0,
        "field_face": face_value,
        "field_face_delta": face_delta,
        "coord_factor": coord_factor,
        "surface_x": surface_x,
        "surface_y": surface_y,
        "weighted_x": face_value * surface_x,
        "weighted_y": face_value * surface_y,
    }


def audit_constant_face_interpolation(
    path: Path,
    *,
    n0: float,
    physical_name: str = "plasma",
    radial_axis: int = 0,
) -> dict[str, Any]:
    """Replay constant-face interpolation and RZ Green-Gauss arithmetic on qvt.

    Final-gradient reconstruction is restricted to cells whose every side is
    internal to the selected physical block, excluding boundary expansion from
    the mechanism under test.
    """
    if radial_axis not in (0, 1):
        raise ValueError("radial_axis must be 0 or 1")
    if not math.isfinite(n0):
        raise ValueError("n0 must be finite")

    element_types = _assert_linear_plasma_blocks(path, physical_name)
    mesh = parse_gmsh41_plasma(path, physical_name=physical_name)
    geometry = _cell_geometry(mesh)
    element_by_tag = {elem.tag: elem for elem in mesh.elements}
    owners = _edge_owners(mesh)
    interior = _internal_cell_tags(mesh, owners)
    if not interior:
        raise ValueError("no fully interior plasma cells available for interpolation audit")

    face_rows: list[dict[str, Any]] = []
    cell_rows: list[dict[str, Any]] = []

    for elem in mesh.elements:
        if elem.tag not in interior:
            continue
        weighted_x = 0.0
        weighted_y = 0.0
        start = len(face_rows)
        for local_side, node_a in enumerate(elem.node_tags):
            node_b = elem.node_tags[(local_side + 1) % len(elem.node_tags)]
            shared = owners[_edge_key(node_a, node_b)]
            if len(shared) != 2:
                raise ValueError(
                    f"interior element {elem.tag} side {local_side} does not have exactly two owners"
                )
            neighbor_tag = next(tag for tag, _side in shared if tag != elem.tag)
            row = _face_row(
                elem=elem,
                local_side=local_side,
                neighbor_tag=neighbor_tag,
                shared=shared,
                element_by_tag=element_by_tag,
                geometry=geometry,
                nodes=mesh.nodes,
                n0=float(n0),
                radial_axis=radial_axis,
            )
            weighted_x += float(row["weighted_x"])
            weighted_y += float(row["weighted_y"])
            face_rows.append(row)

        centroid = geometry[elem.tag]["centroid"]
        radius = centroid[radial_axis]
        if radius <= 0.0:
            raise ValueError(f"element {elem.tag} has non-positive RZ cell radius {radius}")
        volume = float(geometry[elem.tag]["area"]) * (2.0 * math.pi * radius)
        pre_rz_x = weighted_x / volume
        pre_rz_y = weighted_y / volume
        final_x, final_y = pre_rz_x, pre_rz_y
        rz_subtraction = float(n0) / radius
        if radial_axis == 0:
            final_x -= rz_subtraction
        else:
            final_y -= rz_subtraction
        cell_rows.append(
            {
                "element_tag": elem.tag,
                "cell_x": centroid[0],
                "cell_y": centroid[1],
                "radius": radius,
                "area": float(geometry[elem.tag]["area"]),
                "volume": volume,
                "weighted_sum_x": weighted_x,
                "weighted_sum_y": weighted_y,
                "pre_rz_gradient_x": pre_rz_x,
                "pre_rz_gradient_y": pre_rz_y,
                "rz_subtraction": rz_subtraction,
                "final_gradient_x": final_x,
                "final_gradient_y": final_y,
                "final_norm": math.hypot(final_x, final_y),
                "face_row_start": start,
                "face_row_count": len(elem.node_tags),
            }
        )

    if not face_rows or not cell_rows:
        raise ValueError("interpolation audit produced no rows")

    outside = [row for row in face_rows if row["gc_below_zero"] or row["gc_above_one"]]
    nonzero_delta = [row for row in face_rows if float(row["field_face_delta"]) != 0.0]
    worst_delta = max(face_rows, key=lambda row: abs(float(row["field_face_delta"])))
    worst_cell = max(cell_rows, key=lambda row: float(row["final_norm"]))
    max_gc_overshoot = max(
        max(-float(row["gc"]), float(row["gc"]) - 1.0, 0.0)
        for row in face_rows
    )
    max_abs_face_delta = abs(float(worst_delta["field_face_delta"]))
    max_abs_final_gradient = float(worst_cell["final_norm"])

    return {
        "physical_name": physical_name,
        "radial_axis": radial_axis,
        "symmetry_axis": 1 if radial_axis == 0 else 0,
        "n0": float(n0),
        "plasma_gmsh_element_types": list(element_types),
        "plasma_element_count": len(mesh.elements),
        "interior_element_count": len(interior),
        "face_evaluation_count": len(face_rows),
        "gc_outside_unit_count": len(outside),
        "max_gc_overshoot": max_gc_overshoot,
        "nonzero_face_delta_count": len(nonzero_delta),
        "max_abs_face_delta": max_abs_face_delta,
        "max_abs_face_delta_over_n": (
            max_abs_face_delta / abs(float(n0)) if n0 != 0.0 else 0.0
        ),
        "max_abs_final_gradient": max_abs_final_gradient,
        "normalized_max_abs_final_gradient": (
            max_abs_final_gradient / abs(float(n0)) if n0 != 0.0 else 0.0
        ),
        "worst_face_delta": worst_delta,
        "worst_cell": worst_cell,
        "faces": face_rows,
        "cells": cell_rows,
        "interpretation": "EVIDENCE_ONLY_NO_OWNER_ASSIGNMENT",
    }


__all__ = ["audit_constant_face_interpolation", "moose_constant_linear_interpolation"]
