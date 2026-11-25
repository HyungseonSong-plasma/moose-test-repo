# Physics material databases

Canonical data location for new Physics/Plasmas inputs (#896).

- `neutral_transport.txt`: seven heavy species, nine static collision pairs; original Issue21 Git blob `bcbb0a5939ca77a9c3b718fc1cc2ef7f2d45820f`, with only obsolete QPX candidate header removed. Physical data unchanged.
- `electron_moments.txt`: exact original Issue91/r3_e0 electron transport table (Git blob `bedcaf17fb3ef93ba8973cc6b32aa6e783e2292a`).
- Seven reference electron-impact tables relocated byte-for-byte from physics_app/data/electron_impact.
- `EI-*.txt`: 19 independently calculated research candidate EI tables, directly in this directory. Not original protected S6 rates or scientifically accepted substitutes. See `EI_TABLE_PROVENANCE.md`.

Old experiment-local transport/electron files remain only until exact consumer and scratch staging migration; do not treat them as alternate New-only canonical databases. Historical receipts retain their original paths and hashes. Heavy-reaction data/H25 are outside this migration. No coefficient changes or private-rate replacement are implied by moving files.
