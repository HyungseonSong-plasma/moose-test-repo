# Test layout

`test.json` is the canonical discovery unit used by the reusable regression harness.

## Local QPX workspace convention

New local runtime work must use one issue-centric workspace under the QPX root:

```text
<QPX_ROOT>/temp/test_workspace/
  Issue{number}_{short_goal}/
    test.json
    <input>.i
    <runtime dependencies>
```

Examples:

```text
temp/test_workspace/Issue15_heavy_mixture_transport/
temp/test_workspace/Issue16_charge_poisson/
temp/test_workspace/Issue32_performance_localization/
temp/test_workspace/Issue33_reusable_qpx_harness/
```

Naming rule:

```text
Issue{number}_{short_goal}
```

Use a short `snake_case` goal. Do not introduce physics/category directory layers such as `flow/...`, `geometry/...`, or `heavy_transport/...` for new local work.

If one issue requires multiple independent execution units, one optional subcase level is allowed:

```text
Issue32_performance_localization/
  T2_heavy/
  T3_heavy_drift/
  T4_heavy_electron/
```

Do not create deeper taxonomies unless the issue itself is decomposed.

Canonical versus diagnostic status belongs in `test.json`, not in the directory name. Therefore `regression_workspace` and `diagnostic_workspace` are not separate long-term namespaces.

Existing historical workspaces remain readable during migration so accepted runtime evidence is not invalidated by a path-only change. New work should use `temp/test_workspace/Issue{#}_{goal}`.

## Manifest

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
- `diagnostic`: an investigation case used to isolate a failure mechanism. It may intentionally FAIL while an incident is open and may later be promoted to canonical.

If `type` is omitted it defaults to `canonical` for backward compatibility.

The checker path and arguments are evaluated relative to the case directory.

## Running tests

Repository-local default suite:

```bash
python3 scripts/run_all.py --type canonical
```

Local QPX issue workspace:

```bash
python3 temp/scripts/run_all.py \
  --type canonical \
  --tests-root temp/test_workspace
```

The reusable harness also accepts multiple `--tests-root` arguments during migration:

```bash
python3 temp/scripts/run_all.py \
  --type canonical \
  --tests-root temp/test_workspace \
  --tests-root temp/regression_workspace/tests
```

Run diagnostics with `--type diagnostic`; use `--type all` only when both classes are intentionally required.

## Rules

- Keep each test reproducible from its case assets plus the selected user-local `qpx-opt` executable.
- Canonical tests encode invariants and must not be weakened to make new code pass.
- Diagnostic tests isolate one hypothesis at a time and should state what PASS and FAIL mean.
- Promote a diagnostic to canonical when a fixed mechanism becomes a permanent regression requirement.
- Include required meshes, data tables, and reference CSVs near the case or verify external assets by hash/provenance.
- Do not commit generated `*_out.csv`, Exodus output, or run logs.
- Record important PASS/FAIL interpretation in the owning issue and relevant incident/development documentation.
- A passing solver exit code is not sufficient; the checker defines the physical/numerical acceptance gates.
- GitHub static checks do not substitute for user-local P2/P3 physics runtime evidence.
