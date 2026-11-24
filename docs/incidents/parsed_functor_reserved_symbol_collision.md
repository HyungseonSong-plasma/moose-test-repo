# Incident: Parsed functor reserved coordinate-symbol collision

**Incident ID:** `INC-PARSED-SYMBOL-001`  
**Status:** HISTORICAL — original Issue #8 hypothesis and planned discriminator; see the later [closed recurring incident](functionparser_reserved_symbol_collision.md) for canonical prevention  
**Associated work:** Issue #8 `Charged heavy-species mixture diffusion + Poisson coupling`  
**Failure class:** input/parser construction; physics solve not reached

## Symptom

Step-3 H3B fallback produced:

```text
*** ERROR ***
Invalid function
abs(x)
Error:
Syntax error in parameter 'Vars' given to FunctionParser::Parse()
```

The same H3B primary input used the identical parsed-functor block and exited before producing output.

## Root-cause candidate

The failing material used:

```text
[abs_drho_composition]
  type = ADParsedFunctorMaterial
  property_name = abs_drho_composition_dt
  functor_names = 'drho_composition_dt'
  functor_symbols = 'x'
  expression = 'abs(x)'
[]
```

`ParsedFunctorMaterial` appends the spatial/time symbols `x,y,z,t` to the parser variable list after the user-supplied `functor_symbols`. Therefore using `x` as a user functor symbol duplicates a reserved coordinate symbol and makes the FunctionParser variable list invalid.

This also explains why the message points at `Vars` rather than proving that `abs()` itself is unsupported. In the same Step-3 batch, H3A successfully evaluated an AD parsed expression containing `abs(model-exact)`, so `abs()` is already known-good in this QPX/MOOSE build.

## Original planned fix (historical)

Rename the user symbol from `x` to a non-reserved identifier such as `compdot`:

```text
functor_symbols = 'compdot'
expression = 'abs(compdot)'
```

Add a static preflight that rejects user `functor_symbols` equal to `x`, `y`, `z`, or `t` before launching QPX.

## Decision rule

- corrected H3B `--check-input` PASS -> root-cause candidate supported;
- corrected H3B runtime PASS -> incident fix verified;
- corrected check still FAIL with the same `Vars` signature -> candidate rejected and parser-symbol set must be inspected again.

## Current guidance

The recurring parser-namespace mechanism and current P0 prevention are documented in [INC-FP-VARS-001](functionparser_reserved_symbol_collision.md) and the [Troubleshooting Index](../knowledge/TROUBLESHOOTING_INDEX.md). Issue #8 is closed; this record does not independently establish that its original H3B runtime discriminator passed. Retain the original symptom and proposed fix as historical evidence, not an active queue.
