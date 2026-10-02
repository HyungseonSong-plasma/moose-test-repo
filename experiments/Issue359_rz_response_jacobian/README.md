# Issue #359 real-QVT RZ response-Jacobian diagnostic

This experiment measures the electron-map response on the actual ICP RZ mesh
instead of importing the qualified 1D bandwidth-5 shell magnitudes.

The governed first pass:

1. runs an 8-electron-step accepted coupled operating point;
2. reconstructs the canonical `log_e` and conservative `c_epsilon` states on
   the Gummel driver and writes an Exodus state fixture;
3. builds the plasma-cell face-adjacency graph from the pinned QVT mesh;
4. colors the column-intersection graph for graph radius 3;
5. runs central +/-1e-4 V perturbations per color with Poisson disabled and one
   physical electron step;
6. reconstructs a sparse `d(ne)/d(phi)` operator;
7. reports R1/R2/R3 hold-out errors, finite-difference linearity, shell
   Frobenius fractions, and the measured uniform-potential response `J*1`.

No production sparse correction is created or promoted by this experiment.
The same diagnostic must later be repeated at another accepted physical-time
checkpoint to establish whether the dimensionless diagnostic response `W` is
sufficiently stationary for a frozen production operator. This response scaling
is diagnostic only; the solved electron state is not reference-normalized.
