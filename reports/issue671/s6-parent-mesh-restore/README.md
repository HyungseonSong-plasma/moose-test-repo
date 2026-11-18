# S6-417 / S6-941 original main plasma mesh — public L1 restoration

**Source-only PASS. Native / scientific gates remain HOLD.**

## Original-geometry provenance (do not substitute the Maxwell mesh)

The S6 main `[Mesh]/[main]` `FileMeshGenerator` requests:
`experiments/Issue395_powered_chemistry_ladder/baseline_plasma_plus_unstructured_cover_plus_wafer.msh`.

The S6 historical 400W ZIPs carry checkpoint **components** `0459/0460-mesh.cpa.gz` but **do not contain the raw parent `.msh`**. The correct official source chain is the [Issue #397 canonical L1 geometry](../../../experiments/Issue395_powered_chemistry_ladder/issue397_baseline_mesh.json), materialized using `issue397_materialize_l1_baseline.py`. The historical `issue397_l1_power_scan_replay.sh` verifies this exact L1 and copies it to the target S6 basename.

Immutable public original:
- [Actions run #39575896519, Artifact #12349847563](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/39575896519/artifacts/12349847563)
- Original ZIP SHA-256: `f07f082267e159ad87ce1cdab79c95fcd8d78cdc6ed1a6168c4fa09ae1f132a2`
- Member `results_rf_elastic_diss_ion_ei20_ei01_200w_adjacent_sheath_wall_closed_100us_dt1000ns/prep/graded_level_1.msh`
- Raw Gmsh ASCII 2.2 L1 SHA-256: `ac70642df75bf7b4bc4ec0d92511e545f0942f9e07a1361618fb9eb5696b83fc` (174,352 bytes)
- Validated geometry: **1,739 nodes**, **3,155 triangles**, **440 line elements**, **24 physical names**, **27 plasma_wafer faces**, and all nine mandatory plasma/inlet/outlet/wall sideset names.

**Provenance limit:** this is the same officially pinned **materializer output** used by the historical S6 workflow, not a byte-level claim that raw parent `.msh` was contained in original S6-417/941 ZIPs. Never rename/copy Maxwell child `Issue18_qvt_plasma_mapping/qvt.msh` to this path or fabricate `.msh-mesh.cpa.gz` output.

## Executed offline restoration

1. Independently downloaded and rehashed source Artifact #12349847563; extracted the *exact* `graded_level_1.msh` source ZIP member.
2. Independently verified the actual P3-X dual-case artifact #14406746397 ZIP SHA `592a7c82834bab841f6a2e1807db305d0eff1e953f50a0dcc6d7e21ff8820111`; read 11 staged `.i` per case and separate New-only JSONs.
3. In **disposable copies** reproduced the exact seven P4-X C0 owner edits (same SHA as merged PR #677): C0 before `d78a084434eca25b9ece07138c49bf93800845f5947f5ec327bfc81334daa17a`; after `2c3bab8a8e28b360dcd54775d91ba13c97401364c709944bc21d6bf0b6d79490`. Other 10/10 inputs remained byte-identical.
4. Wrote raw L1 bytes to `experiments/Issue395_powered_chemistry_ladder/baseline_plasma_plus_unstructured_cover_plus_wafer.msh` in each **case-local** Scratch and rehashed them after write.
5. Packaged two case-local **23-member**, public-only source ZIPs. 417 ZIP SHA `94702ac59c6766a57db8987a36b172583d9cabdd93f72ade7a5bc7bd0fbdac63`; 941 ZIP SHA `7f157614d3ecffb4358b5f04ac3a6886e1f9b2fe950c9c2488e0ca82b3843631`. ZIP CRC/member hashes/JSON/Maxwell child and both 11-layer SHA checked independently. No protected private EI tables included.
6. **Six of six** negative checks rejected altered mesh byte, wrong Gmsh version, missing physical names, truncation, or wrong historical ZIP pin.

Full immutable values: [verified restoration receipt](verified_restoration_receipt.json).

## P5-0 / Native work remaining

The historical failed `--check-input` complained of missing `baseline_plasma_plus_unstructured_cover_plus_wafer.msh-mesh.cpa.gz`; this is a **derived MOOSE cache name**, not a second original mesh to reconstruct. Only the raw canonical `.msh` is staged; do not pre-create a fabricated checkpoint. In final exact-HEAD P5-0:

- Stage canonical parent `.msh` and independently check SHA before any Native call.
- Independently source-check and stage other public neutral-transport/elastic files.
- In the same trusted job securely stage 417/941-specific original EI private rates (P5-A3) without exporting protected bytes.
- Build one exact final HEAD PhysicsApp binary and run 417/941 `--check-input` with private scratch, logs, and real Warehouse/Factory inventory; separately run Native P05 negative cases with **the same binary**.
- Keep `P5_NATIVE_P2=HOLD`, `Native_P3/P4=NOT_RUN`, `SCIENCE_HOLD` until authoritative runtime evidence.

No original S6 archive, PR #665, main, shared workflows, private EI data or scientific input were modified by the restoration.
