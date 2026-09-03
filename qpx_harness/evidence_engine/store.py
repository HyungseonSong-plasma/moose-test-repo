"""DuckDB-backed persistent query layer for numerical evidence."""
from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Sequence

import duckdb
import polars as pl

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _identifier(name: str) -> str:
    if not _IDENTIFIER.fullmatch(name):
        raise ValueError(f"invalid SQL identifier: {name!r}")
    return name


class EvidenceStore:
    """Small DuckDB facade for Parquet/Polars evidence.

    Tables are materialized deliberately: a run bundle can disappear from the
    filesystem later while the diagnostic database remains queryable.
    """

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self.connection = duckdb.connect(self.path)

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "EvidenceStore":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def ingest_parquet(self, table: str, path: str | Path, *, replace: bool = True) -> None:
        """Materialize a Parquet artifact into a persistent DuckDB table."""
        table_name = _identifier(table)
        verb = "CREATE OR REPLACE TABLE" if replace else "CREATE TABLE"
        self.connection.execute(
            f"{verb} {table_name} AS SELECT * FROM read_parquet(?)",
            [str(Path(path))],
        )

    def ingest_frame(self, table: str, frame: pl.DataFrame, *, replace: bool = True) -> None:
        """Materialize a Polars DataFrame into DuckDB via Arrow integration."""
        table_name = _identifier(table)
        view_name = "_qpx_evidence_incoming"
        self.connection.register(view_name, frame)
        try:
            verb = "CREATE OR REPLACE TABLE" if replace else "CREATE TABLE"
            self.connection.execute(f"{verb} {table_name} AS SELECT * FROM {view_name}")
        finally:
            self.connection.unregister(view_name)

    def query(self, sql: str, parameters: Sequence[Any] | None = None) -> pl.DataFrame:
        """Execute SQL and return a Polars DataFrame."""
        relation = self.connection.execute(sql, list(parameters or ()))
        return relation.pl()

    def worst_cells(
        self,
        *,
        table: str = "cell_evidence",
        metric: str = "gradient_delta_norm",
        limit: int = 20,
    ) -> pl.DataFrame:
        """Return the largest cell-level discrepancies across all stored runs."""
        if limit <= 0:
            raise ValueError("limit must be positive")
        table_name = _identifier(table)
        metric_name = _identifier(metric)
        return self.query(
            f"""
            SELECT *
            FROM {table_name}
            ORDER BY abs({metric_name}) DESC
            LIMIT ?
            """,
            [limit],
        )

    def compare_cases(
        self,
        left_case: str,
        right_case: str,
        *,
        table: str = "cell_evidence",
    ) -> pl.DataFrame:
        """Join two cases by element id for deterministic cell-by-cell comparison."""
        table_name = _identifier(table)
        return self.query(
            f"""
            SELECT
                l.run_id AS left_run_id,
                r.run_id AS right_run_id,
                l.elem_id,
                l.cell_x,
                l.cell_y,
                l.runtime_grad_x AS left_runtime_grad_x,
                l.runtime_grad_y AS left_runtime_grad_y,
                r.runtime_grad_x AS right_runtime_grad_x,
                r.runtime_grad_y AS right_runtime_grad_y,
                l.reconstructed_grad_x AS left_reconstructed_grad_x,
                l.reconstructed_grad_y AS left_reconstructed_grad_y,
                r.reconstructed_grad_x AS right_reconstructed_grad_x,
                r.reconstructed_grad_y AS right_reconstructed_grad_y
            FROM {table_name} AS l
            JOIN {table_name} AS r USING (elem_id)
            WHERE l.case_id = ? AND r.case_id = ?
            ORDER BY l.elem_id
            """,
            [left_case, right_case],
        )
