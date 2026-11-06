# Issue 419 — existing C++ native Boltzmann oxygen run (private-input experiment)

Source branch: `boltzmann-controller-p0-emax-20261029` / draft PR #413, distinct from reaction inventory PR #420. User requested to execute **the existing native solver**, not an unrelated BOLOS implementation.

Execution interface: `physics_app/ci/boltzmann_candidate_export.C` with C++ `PhysicsBoltzmannCrossSections.C`, `PhysicsBoltzmannElasticSolver.C`, `PhysicsBoltzmannGrowth.C`, `PhysicsBoltzmannTemporalGrowth.C`, `PhysicsBoltzmannTransport.C`.

**Mixture (number fraction of total neutrals):** O2(X)=0.99996, O2(a1Delta)=1e-5, O(3P)=1e-5, O(1D)=1e-5, O(1S)=1e-5. Charged species excluded from neutral sum. O(1S) has no listed collision channels in frozen 33 and its elastic collision proxy requires explicit scientific disclosure if supplied to the native solver.

**Source:** User-provided `air-plasma-Phelps.yaml`, `Cross section.txt`, `supplimental data_O2.xlsx`, and private 6-curve approximation archive. These must remain **private** and are not added to public GitHub. Require original SHA256 per file.

**Required execution:** 300 K gas and a pilot E/N scan (10, 30, 50, 100 Td) are explicitly **screening assumptions**, not user-specified plasma conditions or 400/1000W mapping. The existing C++ importer requires a BOLSIG collision text file; conversion must explicitly choose independent O2 elastic MTCS vs Phelps EFFECTIVE Qm and not double count. Include available O(3P) elastic, O(1D)/O(1S) surrogate collision targets only if labelled approximate. **No artificial extrapolation** of EI-411 (ends 15 eV), 2058 (ends 9.95 eV), 2067 (ends 44.023 eV); full energy domain audit required.

No field/energy scan output in this document. Merely building/running CI's *synthetic* Boltzmann controls is not a real oxygen run. The scientific BOLSIG+ parity, source identity and chemistry branching gates remain HOLD. Evaluate actual private data only and report any gate failure without silently dropping enabled processes or inventing sigma tails.
