"""Dynamic column contracts for numerical evidence.

The evidence engine keeps a very small stable core namespace for identity and
spatial topology. Diagnostic quantities live in plugin contracts and are
normalized into solver-agnostic canonical names before numerical transforms run.
Probe/application-specific names such as MOOSE/QPX variables remain aliases, not
core roles.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from enum import Enum

import polars as pl
from pydantic import BaseModel, ConfigDict, Field, model_validator


class CoreColumnRole(str, Enum):
    """Stable identity/topology roles shared by numerical diagnostics."""

    RUN_ID = "run_id"
    CASE_ID = "case_id"
    ELEM_ID = "elem_id"
    FACE_ID = "face_id"
    CELL_X = "cell_x"
    CELL_Y = "cell_y"
    FACE_X = "face_x"
    FACE_Y = "face_y"


# Backward-compatible import name. The enum itself is now intentionally limited
# to stable core roles; diagnostic quantities belong in plugin contracts.
ColumnRole = CoreColumnRole


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

    ``roles`` is keyed by arbitrary logical role names. Core roles use
    ``CoreColumnRole.value``. Diagnostic plugins use string roles so new physics
    quantities can be added without modifying this module or an enum.
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


_CORE_FACE_SPECS: dict[str, ColumnSpec] = {
    CoreColumnRole.RUN_ID.value: ColumnSpec(canonical="run_id", aliases=("run",)),
    CoreColumnRole.CASE_ID.value: ColumnSpec(canonical="case_id", aliases=("sim_id",)),
    CoreColumnRole.ELEM_ID.value: ColumnSpec(
        canonical="elem_id", aliases=("cell_id", "element_id")
    ),
    CoreColumnRole.FACE_ID.value: ColumnSpec(canonical="face_id", aliases=("side_id",)),
    CoreColumnRole.CELL_X.value: ColumnSpec(
        canonical="cell_x", aliases=("cell_r", "x_C", "centroid_x")
    ),
    CoreColumnRole.CELL_Y.value: ColumnSpec(
        canonical="cell_y", aliases=("cell_z", "y_C", "centroid_y")
    ),
    CoreColumnRole.FACE_X.value: ColumnSpec(canonical="face_x", aliases=("face_r", "x_f")),
    CoreColumnRole.FACE_Y.value: ColumnSpec(canonical="face_y", aliases=("face_z", "y_f")),
}

CORE_FACE_CONTRACT = DynamicSchemaContract(roles=_CORE_FACE_SPECS)

# Green-Gauss/RZ is a diagnostic plugin. Canonical names describe numerical
# roles rather than the application that emitted them. MOOSE/QPX-specific names
# are retained as aliases for existing telemetry.
_GREEN_GAUSS_SPECS: dict[str, ColumnSpec] = {
    "normal_x": ColumnSpec(canonical="normal_x", aliases=("nx",)),
    "normal_y": ColumnSpec(canonical="normal_y", aliases=("ny",)),
    "face_area": ColumnSpec(canonical="face_area", aliases=("A_f",)),
    "coord_factor": ColumnSpec(
        canonical="coord_factor", aliases=("rz_factor", "2pi_r")
    ),
    "runtime_surface_x": ColumnSpec(
        canonical="runtime_surface_x",
        aliases=("moose_surface_x", "S_x", "surface_vector_x"),
    ),
    "runtime_surface_y": ColumnSpec(
        canonical="runtime_surface_y",
        aliases=("moose_surface_y", "S_y", "surface_vector_y"),
    ),
    "field_cell": ColumnSpec(
        canonical="field_cell", aliases=("n_cell", "rho_cell", "u_cell")
    ),
    "field_face": ColumnSpec(
        canonical="field_face", aliases=("n_face", "rho_face", "u_face")
    ),
    "cell_volume": ColumnSpec(canonical="cell_volume", aliases=("V_rz",)),
    "radial_coordinate": ColumnSpec(
        canonical="radial_coordinate", aliases=("r_coord", "radius")
    ),
    "runtime_grad_x": ColumnSpec(
        canonical="runtime_grad_x", aliases=("qpx_grad_x", "grad_x")
    ),
    "runtime_grad_y": ColumnSpec(
        canonical="runtime_grad_y", aliases=("qpx_grad_y", "grad_y")
    ),
}

GREEN_GAUSS_FACE_CONTRACT = CORE_FACE_CONTRACT.extend(_GREEN_GAUSS_SPECS)

# Existing callers may continue to use DEFAULT_FACE_CONTRACT; semantically it is
# the built-in Green-Gauss plugin contract, not the global core schema.
DEFAULT_FACE_CONTRACT = GREEN_GAUSS_FACE_CONTRACT

FACE_REQUIRED_COLUMNS = GREEN_GAUSS_FACE_CONTRACT.required_columns
CELL_KEY_COLUMNS = (
    CoreColumnRole.RUN_ID.value,
    CoreColumnRole.CASE_ID.value,
    CoreColumnRole.ELEM_ID.value,
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
