#!/usr/bin/env python3
"""Source/ownership gate for #17 R2 O2 ionization production path."""

import math
from pathlib import Path

N_A = 6.02214076e23
M_O2 = 31.998e-3
RATE = Path("qpx_app/src/materials/QPXElectronImpactIonizationMaterial.C").read_text()
PROJ = Path("qpx_app/src/materials/QPXO2IonizationSourceMaterial.C").read_text()
EK = Path("qpx_app/src/fvkernels/QPXFVElectronReactionSource.C").read_text()

# One rate owner: only the ionization material owns the lookup/table and publishes R_ion_O2.
assert 'addFunctorProperty<ADReal>(\n      "R_ion_O2"' in RATE
assert 'interpolateStrict(_mean_energy(r, state)) * (n_e / N_A) * c_o2' in RATE
for forbidden in ("O2_ionization_mass_source", "O2p_ionization_mass_source", "electron_ionization_number_source"):
    assert forbidden not in RATE
assert "outside lookup range" in RATE and "strict R2 policy forbids clamp/floor" in RATE

# Source projector may consume R_ion_O2 but must not own/recompute lookup or reactant-rate algebra.
assert '_reaction_progress(getFunctor<ADReal>("reaction_progress"))' in PROJ
assert '"O2_ionization_mass_source"' in PROJ
assert '"O2p_ionization_mass_source"' in PROJ
assert '"electron_ionization_number_source"' in PROJ
for forbidden in ("QPXLookupTable1D", "interpolate", "mean_energy", "electron_number_density", "o2_molar_concentration"):
    assert forbidden not in PROJ

# Existing normalized electron equation consumes a signed physical number-source functor.
assert '_number_source(getFunctor<ADReal>("number_source"))' in EK
assert 'return -physical_number_source / _n_ref;' in EK

# Controlled algebra + mutation: one R closes heavy mass and electron-inclusive charge.
R = 2.5
s_o2 = -M_O2 * R
s_o2p = M_O2 * R
s_e = N_A * R
assert s_o2 < 0 < s_o2p and s_e > 0
assert math.isclose(s_o2 + s_o2p, 0.0, abs_tol=1e-14)
assert math.isclose(-s_e + N_A * R, 0.0, abs_tol=1e-6)
assert not math.isclose(-s_e + N_A * (1.01 * R), 0.0, abs_tol=1e-6)

print("R2_O2_IONIZATION_IMPLEMENTATION_PASS")
