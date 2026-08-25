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
  "type": "canonical",
  "input": "case_name.i",
  "checker": "check.py",
  "checker_args": ["case_name_out.csv"]
}
```

`type` is one of:

- `canonical`: a permanent regression that must remain PASS as the code evolves.
- `diagnostic`: an investigation case used to isolate a failure mechanism. A diagnostic may intentionally FAIL while an incident is open, and may later be promoted to canonical after the mechanism is fixed.

If `type` is omitted it defaults to `canonical` for backward compatibility.

The checker path and arguments are evaluated relative to the case directory. A group-level checker can therefore be referenced as `../check.py`.

## Running tests

Run the permanent regression suite:

```bash
python3 scripts/run_all.py
```

or explicitly:

```bash
python3 scripts/run_all.py --type canonical
```

Run investigation cases only:

```bash
python3 scripts/run_all.py --type diagnostic
```

Run everything:

```bash
python3 scripts/run_all.py --type all
```

## Rules

- Keep each test reproducible from repository files plus the selected `qpx-opt` executable.
- Canonical tests encode invariants and must not be weakened to make new code pass.
- Diagnostic tests isolate one hypothesis at a time and should state what PASS and FAIL mean.
- Promote a diagnostic to canonical when a fixed mechanism becomes a permanent regression requirement.
- Include required meshes, data tables, and reference CSVs near the test.
- Do not commit generated `*_out.csv`, Exodus output, or run logs.
- Record important PASS/FAIL interpretation in `docs/incidents/` or `docs/development/`.
- A passing solver exit code is not sufficient; the checker defines the physical/numerical acceptance gates.
