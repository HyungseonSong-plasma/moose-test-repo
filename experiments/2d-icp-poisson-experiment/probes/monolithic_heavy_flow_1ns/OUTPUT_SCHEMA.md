# Plasma state output schema v1

Canonical saved fields for monolithic ICP plasma cases:

| Field | Unit | Meaning |
|---|---|---|
| `n_e` | 1/m^3 | electron number density |
| `n_O2` | 1/m^3 | O2 number density (constrained species) |
| `n_O2s` | 1/m^3 | O2* number density |
| `n_O2p` | 1/m^3 | O2+ number density |
| `n_O` | 1/m^3 | O number density |
| `n_Om` | 1/m^3 | O- number density |
| `n_Op` | 1/m^3 | O+ number density |
| `n_Os` | 1/m^3 | O* number density |
| `u` | m/s | radial velocity |
| `v` | m/s | axial velocity |
| `p` | Pa | gas pressure |
| `T_e_eV` | eV | electron temperature |
| `phi` | V | electrostatic potential |

Heavy-species output is always number density, computed from the nonlinear mass-fraction state as `n_k = rho*w_k*N_A/M_k`. Internal solver variables (`w_*`, `log_e`, `c_epsilon`) are not part of the standard Exodus schema.
