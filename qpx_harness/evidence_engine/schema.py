"""Dynamic column contracts for numerical face/cell evidence.

The evidence engine separates stable canonical column names from the external
telemetry names used by individual probes. A contract resolves aliases into the
canonical namespace before numerical transforms run. New diagnostic quantities
can be added as string-keyed roles without modifying an enum or the transform
core.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from enum import Enum

import polars as pl
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ColumnRole(str, Enum):
    """Stable roles used by the built-in face/Green-Gauss evidence pipeline."""

    RUN_ID = "run_id"
    CASE_ID = "case_id"
    ELEM_ID = "elem_id"
    FACE_ID = "face_id"
    CELL_X = "cell_x"
    CELL_Y = "cell_y"
    FACE_X = "face_x"
    FACE_Y = "face_y"
    NORMAL_X = "normal_x"
    NORMAL_Y = "normal_y"
    FACE_AREA = "face_area"
    COORD_FACTOR = "coord_factor"
    MOOSE_SURFACE_X = "moose_surface_x"
    MOOSE_SURFACE_Y = "moose_surface_y"
    N_CELL = "n_cell"
    N_FACE = "n_face"
    CELL_VOLUME = "cell_volume"
    RADIAL_COORDINATE = "radial_coordinate"
    QPX_GRAD_X = "qpx_grad_x"
    QPX_GRAD_Y = "qpx_grad_y"


class ColumnSpec(BaseModel):
    """One logical evidence role and the external names allowed to provide it."""

    model_config = ConfigDict(frozen=True)

    canonical: str = Field(min_length=1)
    aliases: tuple[str, ...] = ()
    required: bool = True

    @property
    def candidates(self) -> tuple[str, ...]:
        """Return canonical name first, followed by unique aliases."""
        return tuple(dict.fromkeys((self.canonical, *self.aliases)))


class SchemaResolution(BaseModel):
    """Resolved mapping from an external telemetry schema to canonical columns."""

    model_config = ConfigDict(frozen=True)

    rename_map: dict[str, str]
    resolved_roles: set[str]
    missing_roles: set[str]
    source_by_role: dict[str, str]


class DynamicSchemaContract(BaseModel):
    """Alias-aware, extensible schema contract.

    ``roles`` is keyed by arbitrary logical role names. Built-in roles use
    ``ColumnRole.value``, but future diagnostics may inject additional roles
    without changing this module. Candidate names must be globally unambiguous;
    one source column may not silently satisfy multiple physical roles.
    """

    model_config = ConfigDict(frozen=True)

    roles: dict[str, ColumnSpec]
    preserve_extra_columns: bool = True

    @model_validator(mode="after")
    def _validate_candidate_namespace(self) -> "DynamicSchemaContract":
        canonical_owner: dict[str, str] = {}
        candidate_owner: dict[str, str] = {}
        for role, spec in self.roles.items():
            if spec.canonical in canonical_owner:
                raise ValueError(
                    f"canonical column {spec.canonical!r} is assigned to both "
                    f"{canonical_owner[spec.canonical]!r} and {role!r}"
                )
            canonical_owner[spec.canonical] = role
            for candidate in spec.candidates:
                previous = candidate_owner.get(candidate)
                if previous is not None and previous != role:
                    raise ValueError(
                        f"schema alias {candidate!r} is ambiguous between roles "
                        f"{previous!r} and {role!r}"
                    )
                candidate_owner[candidate] = role
        return self

    @property
    def required_roles(self) -> set[str]:
        return {role for role, spec in self.roles.items() if spec.required}

    @property
    def required_columns(self) -> tuple[str, ...]:
        return tuple(
            spec.canonical for role, spec in self.roles.items() if role in self.required_roles
        )

    def extend(
        self,
        additions: Mapping[str, ColumnSpec],
        *,
        preserve_extra_columns: bool | None = None,
    ) -> "DynamicSchemaContract":
        """Return a validated contract containing additional diagnostic roles."""
        merged = dict(self.roles)
        merged.update(dict(additions))
        return DynamicSchemaContract(
            roles=merged,
            preserve_extra_columns=(
                self.preserve_extra_columns
                if preserve_extra_columns is None
                else preserve_extra_columns
            ),
        )

    def resolve_columns(self, present_columns: Iterable[str]) -> SchemaResolution:
        """Resolve external columns without silently choosing ambiguous aliases."""
        present = set(present_columns)
        rename_map: dict[str, str] = {}
        resolved_roles: set[str] = set()
        source_by_role: dict[str, str] = {}

        for role, spec in self.roles.items():
            matches = [candidate for candidate in spec.candidates if candidate in present]
            if len(matches) > 1:
                raise ValueError(
                    f"role {role!r} has multiple matching columns {matches}; "
                    "remove the duplicate alias or normalize upstream"
                )
            if not matches:
                continue
            source = matches[0]
            target = spec.canonical
            if source != target:
                rename_map[source] = target
            resolved_roles.add(role)
            source_by_role[role] = source

        return SchemaResolution(
            rename_map=rename_map,
            resolved_roles=resolved_roles,
            missing_roles=self.required_roles - resolved_roles,
            source_by_role=source_by_role,
        )


_DEFAULT_FACE_SPECS: dict[str, ColumnSpec] = {
    ColumnRole.RUN_ID.value: ColumnSpec(canonical="run_id", aliases=("run",)),
    ColumnRole.CASE_ID.value: ColumnSpec(canonical="case_id", aliases=("sim_id",)),
    ColumnRole.ELEM_ID.value: ColumnSpec(
        canonical="elem_id", aliases=("cell_id", "element_id")
    ),
    ColumnRole.FACE_ID.value: ColumnSpec(canonical="face_id", aliases=("side_id",)),
    ColumnRole.CELL_X.value: ColumnSpec(
        canonical="cell_x", aliases=("cell_r", "x_C", "centroid_x")
    ),
    ColumnRole.CELL_Y.value: ColumnSpec(
        canonical="cell_y", aliases=("cell_z", "y_C", "centroid_y")
    ),
    ColumnRole.FACE_X.value: ColumnSpec(canonical="face_x", aliases=("face_r", "x_f")),
    ColumnRole.FACE_Y.value: ColumnSpec(canonical="face_y", aliases=("face_z", "y_f")),
    ColumnRole.NORMAL_X.value: ColumnSpec(canonical="normal_x", aliases=("nx",)),
    ColumnRole.NORMAL_Y.value: ColumnSpec(canonical="normal_y", aliases=("ny",)),
    ColumnRole.FACE_AREA.value: ColumnSpec(canonical="face_area", aliases=("A_f",)),
    ColumnRole.COORD_FACTOR.value: ColumnSpec(
        canonical="coord_factor", aliases=("rz_factor", "2pi_r")
    ),
    ColumnRole.MOOSE_SURFACE_X.value: ColumnSpec(
        canonical="moose_surface_x", aliases=("S_x", "surface_vector_x")
    ),
    ColumnRole.MOOSE_SURFACE_Y.value: ColumnSpec(
        canonical="moose_surface_y", aliases=("S_y", "surface_vector_y")
    ),
    ColumnRole.N_CELL.value: ColumnSpec(canonical="n_cell", aliases=("rho_cell", "u_cell")),
    ColumnRole.N_FACE.value: ColumnSpec(canonical="n_face", aliases=("rho_face", "u_face")),
    ColumnRole.CELL_VOLUME.value: ColumnSpec(canonical="cell_volume", aliases=("V_rz",)),
    ColumnRole.RADIAL_COORDINATE.value: ColumnSpec(
        canonical="radial_coordinate", aliases=("r_coord", "radius")
    ),
    ColumnRole.QPX_GRAD_X.value: ColumnSpec(canonical="qpx_grad_x", aliases=("grad_x",)),
    ColumnRole.QPX_GRAD_Y.value: ColumnSpec(canonical="qpx_grad_y", aliases=("grad_y",)),
}

DEFAULT_FACE_CONTRACT = DynamicSchemaContract(roles=_DEFAULT_FACE_SPECS)

FACE_REQUIRED_COLUMNS = DEFAULT_FACE_CONTRACT.required_columns
CELL_KEY_COLUMNS = (
    ColumnRole.RUN_ID.value,
    ColumnRole.CASE_ID.value,
    ColumnRole.ELEM_ID.value,
)


def normalize_and_project(
    frame: pl.DataFrame | pl.LazyFrame,
    contract: DynamicSchemaContract = DEFAULT_FACE_CONTRACT,
    *,
    strict: bool = True,
    context: str = "Evidence DataFrame",
    preserve_extra_columns: bool | None = None,
) -> pl.DataFrame | pl.LazyFrame:
    """Normalize external telemetry names into the contract's canonical namespace.

    Extra columns are preserved by default so later diagnostics may consume new
    parameters without changing this function. Set ``preserve_extra_columns`` to
    false for a canonical-only projection.
    """
    columns = (
        frame.columns if isinstance(frame, pl.DataFrame) else frame.collect_schema().names()
    )
    resolution = contract.resolve_columns(columns)
    if strict and resolution.missing_roles:
        missing = sorted(resolution.missing_roles)
        raise ValueError(
            f"{context} validation failed; missing required roles: {', '.join(missing)}"
        )

    normalized = frame.rename(resolution.rename_map)
    preserve = (
        contract.preserve_extra_columns
        if preserve_extra_columns is None
        else preserve_extra_columns
    )
    if preserve:
        return normalized

    selected = [
        spec.canonical
        for role, spec in contract.roles.items()
        if role in resolution.resolved_roles
    ]
    return normalized.select(selected)


def missing_columns(columns: Iterable[str], required: Iterable[str]) -> tuple[str, ...]:
    """Return required canonical columns absent from *columns*, preserving order."""
    present = set(columns)
    return tuple(name for name in required if name not in present)


def require_columns(columns: Iterable[str], required: Iterable[str], *, context: str) -> None:
    """Raise a compact contract error when canonical evidence columns are incomplete."""
    missing = missing_columns(columns, required)
    if missing:
        raise ValueError(f"{context} missing required columns: {', '.join(missing)}")
