# Issue 234 branch-prune provenance

Date: 2026-09-18

Purpose: remove completed/superseded Issue #234 experiment branches while retaining only the branches still needed as direct or upstream provenance for active #253/#254 work.

Retention policy:
- keep main;
- keep the accepted 1D electron drift/surface control used by #253;
- keep the Poisson observer and scaling A/B branches that motivate #253 G1-A;
- keep the two accepted dielectric-relaxation baseline/replication branches used by #253 G1-D;
- keep the fixed-chi branch that reproduces #254's validator defect;
- delete completed, superseded, or no-longer-active #234 experiment branches;
- delete only when the live remote SHA exactly matches the pre-prune inventory.

The exact pre/post refs and deletion results are preserved in this directory.
