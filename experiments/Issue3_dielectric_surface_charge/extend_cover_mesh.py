#!/usr/bin/env python3
"""Extend the accepted plasma-only contour mesh with the original QVT cover thickness.

The plasma nodes/elements and the plasma_cover interface are preserved exactly.  Five
4.5 mm layers are added above y=0.3195 m, reaching the original QVT cover outer
surface y=0.342 m.  This keeps the accepted plasma discretization fixed for a clean
baseline-vs-dielectric discriminator.
"""
from __future__ import annotations

import argparse
from pathlib import Path

Y_INTERFACE = 0.3195
Y_OUTER = 0.342
LAYER_DZ = 0.0045
N_LAYERS = 5
PLASMA_COVER_PHYS = 7
AXIS_PHYS = 1
COVER_OUTER_GROUND_PHYS = 11
COVER_OUTER_RIGHT_PHYS = 12
COVER_BLOCK_PHYS = 20


def section(lines: list[str], start: str, end: str):
    i = lines.index(start)
    j = lines.index(end)
    return i, j, lines[i + 1 : j]


def parse_physical_names(lines: list[str]):
    i, j, body = section(lines, "$PhysicalNames", "$EndPhysicalNames")
    count = int(body[0])
    entries = body[1:]
    if len(entries) != count:
        raise RuntimeError("invalid PhysicalNames count")
    return i, j, entries


def parse_nodes(lines: list[str]):
    i, j, body = section(lines, "$Nodes", "$EndNodes")
    count = int(body[0])
    entries = body[1:]
    if len(entries) != count:
        raise RuntimeError("invalid Nodes count")
    nodes = {}
    for line in entries:
        fields = line.split()
        nodes[int(fields[0])] = (float(fields[1]), float(fields[2]), float(fields[3]))
    return i, j, entries, nodes


def parse_elements(lines: list[str]):
    i, j, body = section(lines, "$Elements", "$EndElements")
    count = int(body[0])
    entries = body[1:]
    if len(entries) != count:
        raise RuntimeError("invalid Elements count")
    return i, j, entries


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()

    lines = args.source.read_text(encoding="utf-8").splitlines()
    phys_i, phys_j, physical_names = parse_physical_names(lines)
    nodes_i, nodes_j, node_lines, nodes = parse_nodes(lines)
    elems_i, elems_j, element_lines = parse_elements(lines)

    used_ids = {int(line.split(maxsplit=2)[1]) for line in physical_names}
    for physical_id in (COVER_OUTER_GROUND_PHYS, COVER_OUTER_RIGHT_PHYS, COVER_BLOCK_PHYS):
        if physical_id in used_ids:
            raise RuntimeError(f"physical id already used: {physical_id}")

    cover_edges = []
    max_element_id = 0
    for line in element_lines:
        fields = line.split()
        element_id = int(fields[0])
        max_element_id = max(max_element_id, element_id)
        element_type = int(fields[1])
        n_tags = int(fields[2])
        tags = list(map(int, fields[3 : 3 + n_tags]))
        element_nodes = list(map(int, fields[3 + n_tags :]))
        if element_type == 1 and tags and tags[0] == PLASMA_COVER_PHYS:
            if len(element_nodes) != 2:
                raise RuntimeError("plasma_cover element is not a 2-node line")
            cover_edges.append(tuple(element_nodes))

    if not cover_edges:
        raise RuntimeError("no plasma_cover edges found")

    interface_nodes = sorted(
        {node for edge in cover_edges for node in edge}, key=lambda node: nodes[node][0]
    )
    xs = [nodes[node][0] for node in interface_nodes]
    ys = [nodes[node][1] for node in interface_nodes]

    # Freeze the exact accepted contour-interface identity before extension.
    if len(interface_nodes) != 54 or len(cover_edges) != 53:
        raise RuntimeError(
            f"unexpected plasma_cover discretization: nodes={len(interface_nodes)} "
            f"edges={len(cover_edges)}"
        )
    if (
        max(abs(y - Y_INTERFACE) for y in ys) > 1.0e-12
        or abs(xs[0]) > 1.0e-12
        or abs(xs[-1] - 0.234) > 1.0e-12
    ):
        raise RuntimeError("plasma_cover geometry does not match the accepted contour baseline")

    expected_pairs = {
        tuple(sorted((interface_nodes[k], interface_nodes[k + 1])))
        for k in range(len(interface_nodes) - 1)
    }
    if {tuple(sorted(edge)) for edge in cover_edges} != expected_pairs:
        raise RuntimeError("plasma_cover connectivity is not one ordered chain")

    max_node_id = max(nodes)
    layer_nodes = [interface_nodes]
    new_node_lines = []
    for layer in range(1, N_LAYERS + 1):
        y = Y_INTERFACE + layer * LAYER_DZ
        row = []
        for x in xs:
            max_node_id += 1
            row.append(max_node_id)
            new_node_lines.append(f"{max_node_id} {x:.16g} {y:.16g} 0")
        layer_nodes.append(row)

    if abs(Y_INTERFACE + N_LAYERS * LAYER_DZ - Y_OUTER) > 1.0e-12:
        raise RuntimeError("cover layer stack does not reach the original QVT outer surface")

    new_element_lines = []
    element_id = max_element_id

    def add_line(physical_id: int, a: int, b: int) -> None:
        nonlocal element_id
        element_id += 1
        new_element_lines.append(
            f"{element_id} 1 2 {physical_id} {physical_id} {a} {b}"
        )

    def add_triangle(physical_id: int, a: int, b: int, c: int) -> None:
        nonlocal element_id
        element_id += 1
        new_element_lines.append(
            f"{element_id} 2 2 {physical_id} {physical_id} {a} {b} {c}"
        )

    for layer in range(N_LAYERS):
        lower = layer_nodes[layer]
        upper = layer_nodes[layer + 1]
        for k in range(len(interface_nodes) - 1):
            # Counter-clockwise triangles in the (r,z) plane.
            add_triangle(COVER_BLOCK_PHYS, lower[k], lower[k + 1], upper[k + 1])
            add_triangle(COVER_BLOCK_PHYS, lower[k], upper[k + 1], upper[k])
        add_line(AXIS_PHYS, lower[0], upper[0])
        add_line(COVER_OUTER_RIGHT_PHYS, lower[-1], upper[-1])

    top = layer_nodes[-1]
    for k in range(len(interface_nodes) - 1):
        add_line(COVER_OUTER_GROUND_PHYS, top[k], top[k + 1])

    new_physical_names = physical_names + [
        f'1 {COVER_OUTER_GROUND_PHYS} "cover_outer_ground"',
        f'1 {COVER_OUTER_RIGHT_PHYS} "cover_outer_right"',
        f'2 {COVER_BLOCK_PHYS} "cover"',
    ]

    output = []
    output.extend(lines[:phys_i])
    output += ["$PhysicalNames", str(len(new_physical_names)), *new_physical_names, "$EndPhysicalNames"]
    output.extend(lines[phys_j + 1 : nodes_i])
    output += ["$Nodes", str(len(node_lines) + len(new_node_lines)), *node_lines, *new_node_lines, "$EndNodes"]
    output.extend(lines[nodes_j + 1 : elems_i])
    output += [
        "$Elements",
        str(len(element_lines) + len(new_element_lines)),
        *element_lines,
        *new_element_lines,
        "$EndElements",
    ]
    output.extend(lines[elems_j + 1 :])

    args.target.write_text("\n".join(output) + "\n", encoding="utf-8")
    print(
        "COVER_MESH_EXTENSION_PASS "
        f"source_nodes={len(node_lines)} target_nodes={len(node_lines) + len(new_node_lines)} "
        f"source_elements={len(element_lines)} "
        f"target_elements={len(element_lines) + len(new_element_lines)} "
        f"cover_segments={len(cover_edges)} layers={N_LAYERS}"
    )


if __name__ == "__main__":
    main()
