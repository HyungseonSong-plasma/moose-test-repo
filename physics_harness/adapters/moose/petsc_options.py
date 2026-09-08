"""Experiment-agnostic PETSc option manipulation for MOOSE Executioner blocks."""
from __future__ import annotations

from collections.abc import Iterable

from .parameters import get_parameter, unquote, upsert_parameter, words


class PetscOptionsError(RuntimeError):
    """Raised when PETSc option representation is ambiguous or inconsistent."""


def _ordered_unique(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        if value not in out:
            out.append(value)
    return out


def get_flags(
    text: str,
    *,
    path: str = "Executioner",
    parameter: str = "petsc_options",
) -> list[str]:
    raw = unquote(get_parameter(text, path, parameter))
    return raw.split() if raw else []


def set_flags(
    text: str,
    flags: Iterable[str],
    *,
    path: str = "Executioner",
    parameter: str = "petsc_options",
) -> str:
    normalized = _ordered_unique(str(flag).strip() for flag in flags if str(flag).strip())
    return upsert_parameter(text, path, parameter, "'" + " ".join(normalized) + "'")


def add_flags(
    text: str,
    flags: Iterable[str],
    *,
    path: str = "Executioner",
    parameter: str = "petsc_options",
) -> str:
    return set_flags(
        text,
        [*get_flags(text, path=path, parameter=parameter), *flags],
        path=path,
        parameter=parameter,
    )


def remove_flags(
    text: str,
    flags: Iterable[str],
    *,
    path: str = "Executioner",
    parameter: str = "petsc_options",
) -> str:
    remove = set(flags)
    return set_flags(
        text,
        [flag for flag in get_flags(text, path=path, parameter=parameter) if flag not in remove],
        path=path,
        parameter=parameter,
    )


def get_name_value_pairs(
    text: str,
    *,
    path: str = "Executioner",
    names_parameter: str = "petsc_options_iname",
    values_parameter: str = "petsc_options_value",
) -> list[tuple[str, str]]:
    names = words(get_parameter(text, path, names_parameter))
    values = words(get_parameter(text, path, values_parameter))
    if len(names) != len(values):
        raise PetscOptionsError(
            f"PETSc option name/value length mismatch: {len(names)} != {len(values)}"
        )
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise PetscOptionsError("duplicate PETSc option names: " + ", ".join(duplicates))
    return list(zip(names, values))


def set_name_value_pairs(
    text: str,
    pairs: Iterable[tuple[str, str]],
    *,
    path: str = "Executioner",
    names_parameter: str = "petsc_options_iname",
    values_parameter: str = "petsc_options_value",
) -> str:
    normalized = [(str(name).strip(), str(value).strip()) for name, value in pairs]
    if any(not name or not value for name, value in normalized):
        raise PetscOptionsError("PETSc option names and values must be non-empty")
    names = [name for name, _ in normalized]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise PetscOptionsError("duplicate PETSc option names: " + ", ".join(duplicates))
    out = upsert_parameter(
        text,
        path,
        names_parameter,
        "'" + " ".join(names) + "'",
    )
    return upsert_parameter(
        out,
        path,
        values_parameter,
        "'" + " ".join(value for _, value in normalized) + "'",
    )


def upsert_name_value(
    text: str,
    name: str,
    value: str,
    *,
    path: str = "Executioner",
    names_parameter: str = "petsc_options_iname",
    values_parameter: str = "petsc_options_value",
) -> str:
    pairs = get_name_value_pairs(
        text,
        path=path,
        names_parameter=names_parameter,
        values_parameter=values_parameter,
    )
    replaced = False
    out: list[tuple[str, str]] = []
    for existing_name, existing_value in pairs:
        if existing_name == name:
            out.append((name, value))
            replaced = True
        else:
            out.append((existing_name, existing_value))
    if not replaced:
        out.append((name, value))
    return set_name_value_pairs(
        text,
        out,
        path=path,
        names_parameter=names_parameter,
        values_parameter=values_parameter,
    )


def remove_name_value(
    text: str,
    name: str,
    *,
    path: str = "Executioner",
    names_parameter: str = "petsc_options_iname",
    values_parameter: str = "petsc_options_value",
) -> str:
    pairs = [
        pair
        for pair in get_name_value_pairs(
            text,
            path=path,
            names_parameter=names_parameter,
            values_parameter=values_parameter,
        )
        if pair[0] != name
    ]
    return set_name_value_pairs(
        text,
        pairs,
        path=path,
        names_parameter=names_parameter,
        values_parameter=values_parameter,
    )
