# Incident: FunctionParser reserved-symbol collision

**Incident ID:** `INC-FP-VARS-001`  
**Status:** CLOSED — root cause isolated and canonical P0 prevention added  
**First historical recurrence evidence:** Issue #8  
**Current recurrence:** Issue #21 `qvt six-species bulk-advection integration`  
**Failure class:** `HARNESS_OR_CONSTRUCTION_FAIL`; P2 parser construction, physics not evaluated

## Symptom family

Observed historical/current signatures include:

```text
Invalid function
abs(x)
Syntax error in parameter 'Vars' given to FunctionParser::Parse()
```

and

```text
Invalid function
r*y
Error:
Syntax error in parameter 'Vars' given to FunctionParser::Parse()
```

The expression text can look valid. The failure can instead come from the parser-variable namespace supplied through `functor_symbols` or implicit symbols from `functor_names`.

## Root cause

For MOOSE `ParsedFunctorMaterial` / `ADParsedFunctorMaterial`, the parser variable list is built from user functor symbols and then extended with spatial/time symbols:

```text
x,y,z,t
```

The parser also registers constants:

```text
pi,e
```

Issue #21 used:

```text
functor_symbols = 'r y'
expression = 'r*y'
```

which caused the generated parser namespace to contain `y` twice after MOOSE appended the coordinate symbols. FunctionParser rejected the `Vars` list before any nonlinear solve or physics residual evaluation.

The Issue #21 repair was purely symbolic:

```text
functor_symbols = 'rho_s wf_s'
expression = 'rho_s*wf_s'
```

No mesh, transport coefficient, SCCM contract, solver tolerance, or physics model change was required.

## Historical recurrence

Issue #8 previously produced the same `Syntax error in parameter 'Vars'` family and required a corrected parser-symbol batch. That history means this is not a one-off typo; it is a recurring harness-construction class that should be prevented mechanically.

This incident is distinct from `INC-ADF-JIT-001`. A `Vars` parse error is a parser-namespace construction defect unless evidence shows otherwise; `ADFParser::JITCompile() failed` remains environment/JIT-sensitive and follows its own incident procedure.

## Permanent prevention

Canonical enforcement is now owned by `docs/protocols/validation.md` VAL-03 / VAL-19.

Machine-enforced checker:

```text
scripts/validate_parser_symbols.py
```

Hard checks before P2:

```text
reject custom parser symbols x,y,z,t,pi,e
check implicit symbols from functor_names when functor_symbols is omitted
reject duplicate parser symbols
reject invalid identifiers
```

Repository `scripts/run_test.py` invokes the parser-symbol preflight automatically before QPX execution.

External overlay bundles that do not carry the repository `scripts/` tree must embed or invoke an equivalent guard in the case `prepare.py` before `qpx-opt --check-input`.

## Decision rule

For

```text
Syntax error in parameter 'Vars' given to FunctionParser::Parse()
```

classify first as:

```text
HARNESS_OR_CONSTRUCTION_FAIL
```

Then inspect parser-symbol declarations before changing physics, data, timestep, nonlinear solver, or environment.

## Closure evidence

Root cause is source-consistent, the #21 candidate was repaired without physics changes, the local overlay now includes a reserved-symbol guard, and canonical repository validation has been upgraded from a checklist item to machine-enforced P0 prevention.
