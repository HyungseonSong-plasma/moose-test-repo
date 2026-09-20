# MOOSE/Physics Operating System Binding

**Status:** consumer binding / compatibility entry point; not the canonical OS registry  
**Consumer:** `HyungseonSong-plasma/moose-test-repo`  
**Canonical OS repository:** `HyungseonSong-plasma/chatgpt-operation`  
**Pinned central revision:** `a41481936daca8280936d8cc70517662b50cbcac`  
**Canonical OS index:** `docs/operating_system/README.md`  
**Current named OS at this pin:** Calvin — Rule-Optimized  
**Reserved successor:** Paul — Rule-Minimal / Skill-Optimized

Named operating-system identity, version lifecycle, immutable baseline records, successor management, and the cross-generation optimization model are no longer owned by this repository.

The current generation interpretation is:

```text
Calvin
  = optimize the active prompt-visible rule working set

Paul
  = minimize prompt-visible procedural rules
  + delegate reusable deterministic mechanics to tested/versioned skills
```

Skills may be used under Calvin; Paul remains RESERVED until the central promotion gate is explicitly passed.

## Authority

Resolve OS authority from exactly:

```text
repository = HyungseonSong-plasma/chatgpt-operation
revision   = a41481936daca8280936d8cc70517662b50cbcac
path       = docs/operating_system/README.md
evolution  = docs/operating_system/EVOLUTION.md
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
3. read the central OS index and evolution model at that revision;
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
docs/operating_system/EVOLUTION.md
```

Do not recreate local canonical copies. A future OS upgrade is adopted here by explicitly changing this exact central revision after consumer validation.
