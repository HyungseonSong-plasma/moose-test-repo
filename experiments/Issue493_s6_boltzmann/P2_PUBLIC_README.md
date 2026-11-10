# Issue #493: native P2 check-input with public Boltzmann rates

**Scope:** exact S6-417 / S6-941 400 W, 0–100 µs inputs for two research
variants **B** (legacy template, new rates) and **C** (partial continuity
migration, same new rates). Stage/validate all four and run the immutable
PR #491 `physics-opt --check-input` executable against each. **No 460-step
P3 solve or P4 scientific comparison is initiated. SCIENCE_HOLD.**

Inputs: `public_p2_decks.tar.xz.b64` contains **only public text MOOSE input
decks**, their orders and SHA-pinned manifest. It does **not** contain rate
table content, the protected historical lookup tables, MCS.OUT, original
user ZIP, archived Exodus output or new generated results. Before native run,
`public_p2_check.py` authenticates the input archive, validates every deck
against its SHA, and verifies that the 19 individual rate files it reads from
`physics_app/data/electron_impact/boltz/` match the original new-only
experiment manifest. The case/variant workspace copies just its active five
public `.txt` files into `private_rates/` (the path name expected by the
original archived deck, **not** a source of private data).

The experiment is isolated to the same-repository PR #495 in canonical
`.github/workflows/ci.yml`, preserving the existing governed workflow
allowlist. The CI Job reads no repository secrets and uses only `contents:
read`. It checks out the pinned historical source SHA
`29d1acc6ef7969908b86719e4b95c73a1565136d` and exact reviewed PhysicsApp
candidate SHA `bebaf47a33ff5ee1d6b933d9691bf48f5ec0f947`, builds against
the immutable `physics-build-base` OCI digest with scoped PhysicsApp non-Unity
`src/utils` configuration, prepares the public S6 400 W mesh, then checks each
input deck natively.

P2 PASS requires four **successful native `--check-input` process exit codes**
(417/B, 417/C, 941/B, 941/C), in addition to hash-proven public P0.
Only after the actual CI Job terminates can any P2 result be claimed.
Status output has explicit P3/P4 `NOT_RUN`; full solver logs remain separate
from the published statuses, and no original private data are used.

Offline structural preflight (no OCI needed):

```bash
python3 experiments/Issue493_s6_boltzmann/public_p2_check.py \
  --control . --mode preflight
```
