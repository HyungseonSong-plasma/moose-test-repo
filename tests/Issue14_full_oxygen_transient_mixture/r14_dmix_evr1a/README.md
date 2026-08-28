# R14 EVR1-A — seven-species transport-data candidate + runtime probe

Included data SHA-256:

    2fa7988c79f6ea23ebdd50e6d1d7fc5018dc8854a27459511ec95c94ebe7ff3d  transport_data.txt

Static pairs included (9):
- neutral-neutral: O|O, O|O2, O2|O2
- positive-ion-neutral: O|O+, O|O2+, O+|O2, O2|O2+
- negative-ion-neutral: O|O-, O-|O2

Charged-charged pairs are intentionally absent from the text database and are evaluated
dynamically by QPXThermalDiffusionMaterial using T, Te and ne.

Run from qpx/temp:

    ./run_test.sh heavy_transport/r14_dmix_evr1a

PREPARE independently validates schema, species aliases, exhaustive 7-species pair
resolution, B*/C*, Langevin formula nodes, <1% midpoint interpolation error, and the
historical 300 K O-/O2 reduced-mobility signature.
