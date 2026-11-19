# Functional Dependency Evidence Graph — Structural Evidence v0.1

**Status:** P0 structural extraction only; no retirement authorization  
**Owner:** FDEG Structural module, issue #691  
**Implementation:** `ci/guards/fdeg_structural.py`

## Purpose

Record source-bound, directed structural relationships from an exact repository checkout to a specified MOOSE C++ class. This is the first independently developed FDEG module; the Functional, Transition, and Coverage Evidence modules are **not** implied by its output.

## Read-only invocation

```bash
python3 ci/guards/fdeg_structural.py \
  --target PhysicsFVThermalDiffusion \
  --expected-head "$(git rev-parse HEAD)" \
  --output /tmp/fdeg-structural.json
python3 -m unittest discover -s tests -p test_fdeg_structural.py -v
```

The exact-head option requires a Git checkout at that SHA with no tracked changes. Without Git metadata the scanner can run on a fixture directory, but the report's repository head is null and it **cannot** be used for SHA-bound repository claims.

## Evidence contract

Schema: `fdeg.structural.v0.1`. Each relationship includes `from`, `to`, `relation`, `strength`, `detail`, and a source `evidence` object with `path`, 1-based `line`, Git-format `blob_sha`, and an excerpt. All paths are repository-relative. A node is either a `class:<name>` or a `file:<relative path>`.

Structural relationships:

| Edge | Meaning | Does NOT prove |
| --- | --- | --- |
| `REGISTERS` | Factory registration, including AD and explicit alias | actual instantiation |
| `DECLARES` | C++ class declaration | operational use |
| `REGISTERS_ACTION` | MOOSE Action task registration | task execution |
| `REGISTERS_PHYSICS_TASKS` | Physics base task registration | task execution |
| `REGISTERS_ACTION_SYNTAX` | Input syntax path assigned to Action | enabled input |
| `INPUT_MATCHES_ACTION_SYNTAX` | Declared .i block path matches registered syntax | Action actually ran |
| `ACTION_CREATES` | Literal object-type argument to C++ add* call | physics runtime success |
| `ACTION_CREATES_VIA_LOCAL_LITERAL` | Candidate local C++ literal variable -> add* call | correct scope/dataflow |
| `CPP_CONSTRUCTS` | Literal C++ new/make_unique/make_shared of target | executed code |
| `INCLUDES_TARGET_HEADER` | C++ file includes matching target header | runtime consumer |
| `INPUT_INSTANTIATES` | Literal .i type equals Factory name/alias | successful MOOSE P2 |
| `INCLUDES_INPUT` | One in-scope .i file includes another | included block active |
| `PYTHON_DECLARES_TYPE` | Static Python type field or keyword | generated .i execution |
| `PYTHON_WRITES_INPUT` | Python statically names an in-scope .i write target | output generated in the run |
| `JSON_DECLARES_TYPE` | Static JSON type field | JSON consumed by Physics |
| `WORKFLOW_RUNS_SCRIPT` | Workflow contains static command for tracked script | CI job always triggers |
| `WORKFLOW_CALLS` | Workflow contains local reusable workflow call | workflow trigger satisfied |
| `MENTIONS_SYMBOL` | Source contains target class token | any functional dependency |

The graph includes **incoming transitive paths** reaching the specified class; e.g. `Workflow -> test script -> class` and `.i wrapper -> included .i -> class`. Relations marked `LEXICAL_ONLY`, `LEXICAL_FLOW_CANDIDATE`, or `DECLARED_INPUT_ONLY` must not be promoted to real runtime calls.

## Scan boundary and safety

- Scans Git tracked files of supported C++/Python/.i/JSON/YAML extensions; excludes generated untracked outputs on real checkouts. The synthetic-fixture mode scans those extensions below the requested fixture root.
- Detects a subset of **static** Factory, Action, syntax, C++ creation, input include, Python/JSON type, and Workflow command patterns. Macro expansions, indirect factory calls, runtime-generated objects, shell control flow, missing generated outputs and caller context are not resolved.
- Dynamic .i types, dynamic Python/JSON types, missing includes, untracked generated .i outputs, unresolved Workflow script/callee paths, and parse/read errors are recorded as separate `unresolved` or `scan_errors` entries with source identity.
- A `STRUCTURAL_RECORDED` result means the supported syntax was extracted without reported scanner errors; it **does not prove complete coverage, zero callers, functional equivalence, or deletion safety**. A repository may have unobserved dynamic/external consumers regardless of this status.
- When unresolved items/errors are present, `INCOMPLETE` is returned; CLI uses nonzero exit code 2 and prints `FDEG_STRUCTURAL_P0=HOLD`. An exact-head or identity failure is exit code 1.
- Static source identity is not a P1 build, P2 MOOSE input acceptance, P3 native physical runtime, or historical replay proof. No workflow is dispatched by the scanner.
- Cross-branch consumers and external controllers are outside v0.1's automated scan. Do not infer caller-zero from their absence.

The Functional module may enrich class->physical-capability edges; Transition may add replacement/rewire evidence; Coverage must define the claim scope and explicitly certify or reject completeness. None of these roles are silently implemented by Structural.
