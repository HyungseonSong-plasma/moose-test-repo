# Issue #27 — Stage-6 wall / SEE integration surface

**Status:** current controller documentation  
**Controller:** #27  
**Immediate child:** #193 — A8 finite-SEE particle runtime acceptance  
**Current claim state:** Stage-6 NOT ACCEPTED; Integrated Physics Accuracy NOT ESTABLISHED

## Current execution authority

The Phase-A directories below contain schema-v1 historical experiment fixtures. They are retained for provenance and characterization, but the schema-v1 protocol-dispatch control plane has been retired. These JSON files are **not current executable experiment entrypoints**.

Current repository/harness work uses the schema-v2 semantic control plane through `python3 bin/physics.py`. Closure-grade Stage-6 scientific runtime is established only through an explicitly governed exact-head `physics-opt` acceptance runner/workflow owned by the active issue.

For the current Stage-6 sequence:

```text
#176 Stage-5 volumetric chemistry
    CLOSED / ACCEPTED [bounded pre-Maxwell]
            ↓
#193 A8 finite SEE particle runtime
    OPEN / READY / NEXT
            ↓ after explicit #193 PASS
#27 final wall + SEE + energy + chemistry regression
            ↓
Stage-6 acceptance decision
```

Do not infer #193 or Stage-6 PASS from any historical schema-v1 fixture or README.

## Accepted upstream wall chemistry

The accepted wall set is exactly:

```text
plasma_electrode
plasma_metal
plasma_right
plasma_cover
plasma_wafer
plasma_focus_ring
```

`inlet` and `outlet` are excluded from wall chemistry.

Accepted reactions remain:

| reaction | sticking | finite-SEE coefficient |
|---|---:|---:|
| `O -> 0.5 O2` | 0.2 | 0 |
| `O2+ -> O2` | 1 | 0.05 |
| `O- -> O` | 1 | 0 |
| `O2(a1Delta_g) -> O2` | 1 | 0 |
| `O(1D) -> 0.5 O2` | 0.2 | 0 |
| `O+ -> O` | 1 | 0.05 |

`O2` remains the constrained N-1 species:

```text
w_O2 = 1 - (w_O2s + w_O2p + w_O + w_Om + w_Op + w_Os)
```

No independent seventh heavy-species `O2` equation is introduced.

## Frozen Stage-6 particle and energy contracts

Charged-heavy wall transport:

```text
J_i,wall = J_i,surface + J_i,migration
```

Thermal electron particle loss:

```text
Gamma_e,thermal,out = 0.5 * n_e * v_e,th
```

Finite SEE particle source:

```text
Gamma_e,SEE = 0.05 * (Gamma_O2+,wall + Gamma_O+,wall)
gamma_O2+ = 0.05
gamma_O+  = 0.05
gamma_O-  = 0
```

Accepted electron-energy mapping from completed #26:

```text
Gamma_epsilon,thermal,out = (5/6) * v_e,th * n_epsilon
epsilon_SEE = 4 eV
Gamma_epsilon,SEE,in = 4 eV * Gamma_e,SEE
```

The particle source and 4 eV mapping are frozen inputs to #193/#27 acceptance. They must not be weakened merely to obtain PASS.

## Historical Phase-A provenance

The following directories preserve the development sequence and characterization fixtures used to establish earlier wall behavior:

```text
A1_o_recombination/
A1b_o_sticking/
A1c_o_sticking_all_walls/
A2_om_neutralization/
A3_positive_ion_neutralization/
A3e_charged_wall_ledger/
A4_excited_neutral_quenching/
A6_combined_wall_integration/
A7_comsol_electron_wall/
A8_finite_see/
```

Their schema-v1 `experiment.json` files and historical scientific descriptions may be read as provenance or characterization oracles. They do not select a current production protocol and must never be promoted back into a parallel experiment control plane.

The detailed chronology is preserved in Git history and in #27 issue comments. Current scheduling/acceptance authority is the #27/#193 issue state plus exact-head governed runtime evidence.

## Current acceptance boundary

#193 must establish the finite conducting-wall SEE particle path on the real exact-head production path, including:

- zero-SEE control behavior;
- SEE source sign and magnitude;
- O2+ and O+ contributions exactly once;
- no O- SEE contribution;
- electron particle inventory closure;
- wall-current/sign consistency;
- charge/Gauss consistency;
- consistency with the accepted 4 eV-per-emitted-electron mapping;
- convergence and positivity;
- ordinary CI plus governed real-`physics-opt` evidence.

Only after #193 is explicitly PASS/CLOSED may #27 run the final wall + SEE + energy + chemistry compatibility regression.

Dynamic dielectric `sigma_s`, dielectric SEE, A7 anomaly work, and Maxwell/RF work remain separately scoped.
