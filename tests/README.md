# Test layout

Tests are grouped by physics/development area and case name.

```text
tests/
  <area>/
    <group>/
      <shared checker/reference files>
      <case>/
        test.json
        <input>.i
        <runtime dependencies>
```

A `test.json` manifest is the discovery unit used by `scripts/run_all.py`.

Minimal manifest:

```json
{
  "name": "case_name",
  "input": "case_name.i",
  "checker": "check.py",
  "checker_args": ["case_name_out.csv"]
}
```

The checker path and arguments are evaluated relative to the case directory. A group-level checker can therefore be referenced as `../check.py`.

## Rules

- Keep each test reproducible from repository files plus the selected `qpx-opt` executable.
- Include required meshes, data tables, and reference CSVs near the test.
- Do not commit generated `*_out.csv`, Exodus output, or run logs.
- Record important PASS/FAIL interpretation in `docs/incidents/` or `docs/development/`.
- A passing solver exit code is not sufficient; the checker defines the physical/numerical acceptance gates.
