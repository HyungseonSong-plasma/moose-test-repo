# Issue54 final-guard import-path false FAIL — 2026-09-01

## Incident

Issue54 close-level local validation returned:

```text
ISSUE54_FINAL_IMPORT_IDENTITY: FAIL (No module named 'qpx_harness')
ISSUE54_FINAL_GUARD: FAIL
```

while all production behavior checks in the same user-local batch remained green, including:

```text
ISSUE45_INVENTORY_NULLSPACE_SELFTEST: PASS
ISSUE45_INVENTORY_CLOSURE_RUNTIME_SELFTEST: PASS
ISSUE45_FIRST_LINEAR_SELFTEST: PASS
QPX_HARNESS_SELFTEST: PASS
```

The refactor therefore did not present evidence of a production import/runtime regression. The failure was isolated to the final validator.

## Root cause

`tests/Issue54_electron_inventory_decomposition/final_guard.py` is intentionally invoked as a file:

```text
python3 tests/Issue54_electron_inventory_decomposition/final_guard.py
```

Under this invocation Python places the script directory on `sys.path`; the repository root is not guaranteed to be importable as a package root. The guard nevertheless called:

```python
importlib.import_module("qpx_harness.electron_inventory_nullspace")
```

without first establishing the repository root on `sys.path`.

Thus the gate rejected a valid decomposed tree because its own import bootstrap was incompatible with the declared disposable-ZIP local execution contract.

## MET-20

```text
Root-cause class: final validation import bootstrap/path defect
Learning status: GATE_DEFECT
```

Evidence for `GATE_DEFECT`:

- the final guard existed and was invoked;
- the gate produced the failing decision;
- production module self-tests and the full QPX harness self-test passed in the same environment;
- the declared local contract explicitly uses a GitHub ZIP workspace and file-invoked diagnostic scripts;
- the guard, not the production package, failed to establish the package import root.

This is not classified as `ENVIRONMENT_ESCAPE`: the user environment matched the declared workflow. The validator was defective for that declared environment.

## MET-22 / prevention decision

This is not established as the second recurrence of the same narrow semantic failure class, so a mandatory EPR is not triggered solely by this incident.

Targeted remediation:

```text
REPAIR_GATE_AND_SELFTEST
```

The guard now derives `ROOT` from `__file__` and explicitly inserts that repository root into `sys.path` before the import-identity check. This keeps the check independent of current working directory and does not modify production code.

Prevention maturity before local revalidation:

```text
DOCUMENTED
```

Promote to `MACHINE_CHECKED` only after the repaired final guard passes through the same documented local invocation path.

## Scientific / production impact

```text
Issue45 EVR consumed by incident: 0
Issue45 EVR3: preserved / not authorized
scientific interpretation changed: no
production owner changed by remediation: no
validator only: yes
Issue54 closure: blocked pending repaired guard rerun
```
