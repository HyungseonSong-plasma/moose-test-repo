# MOOSE/Physics Operating System Binding

**Status:** consumer binding / compatibility entry point; not the canonical OS registry  
**Consumer:** `HyungseonSong-plasma/moose-test-repo`  
**Canonical OS repository:** `HyungseonSong-plasma/chatgpt-operation`  
**Pinned central revision:** `51763866518a58dc5a1b65e1e579e8f255442931`  
**Canonical OS index:** `docs/operating_system/README.md`  
**Current named OS at this pin:** Calvin

Named operating-system identity, version lifecycle, immutable baseline records, and successor management are no longer owned by this repository.

## Authority

Resolve OS authority from exactly:

```text
repository = HyungseonSong-plasma/chatgpt-operation
revision   = 51763866518a58dc5a1b65e1e579e8f255442931
path       = docs/operating_system/README.md
```

Do not replace the exact revision with `main`, `latest`, or another floating ref during an active operating decision cycle.

## Local ownership retained here

This repository continues to own MOOSE/Physics-specific operating meaning:

```text
BOOTSTRAP.md
OPERATING_CORE.md
PROTOCOL_INDEX.md
docs/protocols/**
docs/metrics/**
docs/rules/**
active issue / bounded-work STATE
scientific/runtime/validation semantics
```

Central OS ownership does not allow central documents to redefine Physics scientific validity, runtime evidence, repository-specific acceptance, or local work state.

## Bootstrap use

`moose-test-init` must:

```text
1. read this binding;
2. resolve the exact central revision;
3. read the central OS index at that revision;
4. then load this repository's local operating core, state, routing, and metrics context.
```

If the exact central OS revision or index cannot be established, OS identity is unresolved and initialization must not claim completion.

## Migration provenance

The Calvin historical baseline and Paul successor contract were originally stored under this directory. Canonical ownership moved to `chatgpt-operation` under central issue #16 / PR #17 and consumer issue #297.

The historical Calvin file was copied byte-for-byte before local removal; its git blob SHA remains:

```text
2a13a112ca29f7eaee220e837611556786747fc5
```

Canonical central locations:

```text
docs/operating_system/versions/2026-09-01_calvin.md
docs/operating_system/PAUL_CANDIDATE.md
```

Do not recreate local canonical copies. A future OS upgrade is adopted here by explicitly changing this exact central revision after consumer validation.
