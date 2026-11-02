# Oxygen25 EEDF initial-mixture transport A/B — native 1 µs checkpoint

This is a **separate research-only** 400 W / 1000 W study, not a mutation of
the canonical 25-channel source or baseline electron transport table.

## 0–1 µs first run

- Physics source: `8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab`
- Selected collision data: 19 EI cross sections that match chemistry rate IDs,
  plus 4 momentum-transfer cross sections from user-provided O2/O2ex/O/Oex files.
- Three-column lookup: `initial_mixture_23xsec_transport.txt` (42 energy rows,
  units mean energy eV, μN, DN). SHA256
  `35534a522fa48ccb5222339c5040040630eef31e623e1c53f1e1c4540d2d653b`.
- Same unchanged 25-channel chemistry; private rates are accessed from the
  CI secret only. Initial `O2,O2a,O,Os` fractions `0.99997,1e-5,1e-5,1e-5`.
- Fresh native MOOSE initialization with NO restart, one continuous solver run.
- Requested output/timestep sequence: 0–100 ns @ 1 ns (100 intervals),
  100–1000 ns @ 10 ns (90 intervals). 190 intervals, 191 saved targets.
  This is a TimeSequenceStepper, not the 1 µs `dtmax` sensitivity study.

Run `oxygen25-initial-eedf-0to1us-400-1000w.yml` on the research branch.
Only successful P3 **and** P4 may be labeled `complete`.

## Native 1 µs checkpoint contents (each power separately)

Successful job must publish exactly these new research artifacts:

`oxygen25-eedf23-1000ns-initial-complete-400W`
`oxygen25-eedf23-1000ns-initial-complete-1000W`

Each contains:

1. `restart_run_1000ns.tar.gz`: native full-state
   `run/plasma_cp/<native-step>-restart-0.rd/` and
   `<native-step>-mesh.cpa.gz/`, raw `run/plasma.e`, `plasma.csv`,
   native solver logs, including the Maxwell MultiApp saved state.
2. `restart_inputs_1000ns.tar.gz`: **all** exact input overlays and mesh;
   the experiment EEDF table copy at
   `experiments/Issue395_powered_chemistry_ladder/electron_transport_initial_eedf.txt`
   **and the live table** used by plasma and RF Maxwell at
   `experiments/Issue91_real_qvt_r3/r3_e0/electron_moments.txt`.
3. `restart_1000ns_manifest.json`, `restart_archives_1000ns.sha256`,
   raw startup logs and provenance.

The research restart helper must check SHA256 of both archives, every
archived file, and both EEDF table copies. Original 19 private rate tables
are never included; rehydrate them only at runtime from the same private secret
and verify their previous rate SHA list.

No artifacts should be represented as complete if P3/P4 fails.

## Extending **from 1 µs to 100 µs** (not launched yet)

Never use the **legacy 100 ns** stage2 script without modifications: it expects
a 100 ns initial checkpoint and its old five-stage provenance.

Use `.github/scripts/oxygen25_eedf_restart_chain.py` with the **exact**
successful EEDF 1 µs checkpoint, in separate GitHub Actions workflow runs:

| Continuation | Start (ns) | End (ns) | adaptive dtmax | `--interval-ns` |
|---|---:|---:|---:|---:|
| 1 → 2 µs | 1000 | 2000 | 10 ns | 10 |
| 2 → 10 µs | 2000 | 10000 | 100 ns | 100 |
| 10 → 100 µs | 10000 | 100000 | 1 µs | 1000 |

First start: checkout pinned physics source, download **matching power** EEDF
checkpoint artifact, then use

```bash
python3 .github/scripts/oxygen25_eedf_restart_chain.py --self-test
python3 .github/scripts/oxygen25_eedf_restart_chain.py \
  --restore _upstream_artifact/400W \
  --root "$PWD" --power-w 400 --start-ns 1000 --end-ns 2000 \
  --interval-ns 10 --source-sha 8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab
```

Then rehydrate and validate the **same** private rate tables; build the same
native PhysicsApp; check-input; run native MOOSE with MultiApp restore enabled,
and call `--verify-recovery` on the actual new saved state. The validated 2 µs
restart files can be uploaded under a new **EEDF-specific** artifact name.
Repeat with the next start/end above. Each stage requires a separate P3/P4
gate and native restart boundary-monitor continuity proof.

**Important:** the 1 µs checkpoint's saved TimeSequenceStepper must be switched
to `IterationAdaptiveDT` on advanced restart using the helper; using
`--recover` is not equivalent to native advanced restart and has previously
produced invalid continued time sequences. The solver is allowed to choose
smaller actual timesteps than the configured upper cap.

The new EEDF table is **research-only SCIENCE_HOLD**. Do not silently reuse an
old source checkpoint or revert the table when extending.
