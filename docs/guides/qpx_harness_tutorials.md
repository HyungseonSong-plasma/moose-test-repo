# Physics Harness Tutorial — compatibility path

**Status:** compatibility redirect only  
**Current guide:** `docs/guides/physics_harness_tutorials.md`

This filename retains the former QPX product name only so historical links do not break. The old schema-v1 protocol-dispatch tutorial previously stored here is retired and must not be used as an operational execution guide.

Current rules are:

- the canonical experiment control plane is schema-v2 `ExperimentSpec`;
- the stable CLI entrypoint is `python3 bin/physics.py`;
- historical schema-v1 fixtures are provenance/characterization only;
- generic semantic `run` currently prepares target execution but does not silently fall back to a campaign/protocol runner;
- closure-grade scientific runtime uses an explicitly approved governed acceptance surface.

Use `docs/guides/physics_harness_tutorials.md` for current commands and workflow semantics.
