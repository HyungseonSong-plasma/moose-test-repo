# Physics material databases

`transport_data.txt` is the canonical heavy-species collision-integral
database for new Physics/Plasmas Navier–Stokes integration (#896).
It retains the seven species and nine static collision pairs from
`experiments/Issue21_qvt_six_species_bulk_advection/transport_data.txt`.
Only the obsolete QPX candidate header comment was removed; all remaining
bytes are identical to the historical source (Git blob
`bcbb0a5939ca77a9c3b718fc1cc2ef7f2d45820f`).
The old file is retained solely as a hash-pinned experiment fixture.
Do not change archived experiment manifests to point here.

The New-only JSON binding and Scratch staging are a separate integration
step. Existing Native inputs and frozen experiments continue to use their
original paths until their owning contracts explicitly migrate.
This is a location/provenance change, not a scientific coefficient update.
