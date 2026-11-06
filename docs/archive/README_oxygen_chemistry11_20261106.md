# Chemistry, MCS and Oxygen25: 11 branch retirement evidence (2026-11-06)

This directory contains a snapshot of exactly **11 requested old chemistry/MCS/Oxygen branches**:

- [11 exact branch heads, Git archive tags, and Actions run provenance](oxygen_chemistry11_20261106.json).
- [Named ZIP artifacts, artifact IDs, sizes and retention dates](oxygen_chemistry11_actions_artifacts_20261106.json).

The existing pinned Samuel `samuel-branch-delete.yml` supports an `archive_tag` field. Before deletion, this creates and verifies a lightweight immutable Git tag named `archive/oxygen-cleanup-20261106/<branch-slug>-<SHA12>`. Samuel deletes only if the live branch matches the expected full commit SHA. To restore a deleted branch: `git fetch --tags origin` and `git switch -c restored '<full-archive-tag>'`.

**WARNING: Git tags preserve committed source, configs, inputs, documentation, and history, NOT Actions ZIP contents.** The artifact inventory includes 19 files totaling **803,253,499 bytes** from 11 reference workflow runs. Some diagnostics expire **2026-11-23** and others **2026-12-04**; complete native archives have later expiration. The archival index does not constitute a permanent copy of those ZIPs; durable independent backup remains necessary. No private/controlled rate/cross-section data is copied to new storage by this operation.

The older 61-branch archive remains separately indexed in [oxygen_legacy61_20261106.json](oxygen_legacy61_20261106.json). Oxygen14 research BASE and Boltzmann core are not in this 11-branch deletion scope. Close/delete here is **administrative**; `SCIENCE_HOLD` and security permissions remain effective.
