# R14 EVR1-B

Purpose: independent production-runtime validation of the seven-species
mixture-averaged diffusion coefficients.

State A:
- T = 600 K
- p = 13.332 Pa
- Te = 20000 K
- ne = 1e16 m^-3

State B:
- same state except ne = 1e18 m^-3

Acceptance:
- 14 production Dmix outputs finite and positive.
- 7/7 Dmix in each state match the independent oracle within 2e-5 relative.
- O2, O2s, O and Os are invariant to ne within 1e-12 relative.
- O2p, Om and Op each change by at least 5% between A and B.
- PREPARE source/data hashes and oracle self-test PASS.

Transport candidate SHA-256:
2fa7988c79f6ea23ebdd50e6d1d7fc5018dc8854a27459511ec95c94ebe7ff3d

Run from qpx/temp:

    ./run_test.sh heavy_transport/r14_dmix_evr1b
