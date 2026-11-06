# Boltzmann Controller cycle 8: exact reconstructed EEPF mean-energy moment (2026-10-29)

## Provenance and scope

Tracking issue #412; child Draft PR #413 targets parent Draft PR #408's
development branch, not main. All new calculations use **first-party
synthetic** cross sections and manufactured EEPFs. No private LXCat
tables or genuine BOLSIG+ EEPF arrays were committed. Science HOLD remains.

The previous P0-3 reconstructed ionization/attachment Q used the frozen
subcell EEPF shape but still reported a **piecewise-constant** mean energy.
This made the reported energy moment inconsistent with the collision
integrals. This cycle corrects the moment and adds an independent
energy-convergence gate to the nonlinear Picard driver.

## Derivation

Within cell `[a_i,b_i]`, define the sqrt(E)-weighted number mass and
centroid:

```text
M_i  = (2/3) * (b_i^(3/2) - a_i^(3/2))
J1_i = (2/5) * (b_i^(5/2) - a_i^(5/2))
mu_i = J1_i / M_i
J2_i = (2/7) * (b_i^(7/2) - a_i^(7/2))
f_i(E) = f_i * [1 + s_i * (E - mu_i)]
```

The slope `s_i` is positivity-limited and frozen from the preceding
Picard EEPF. The new current eigenvector supplies `f_i`. The exact
number and first-energy moments of the *same* reconstructed shape are

```text
N = sum_i f_i * M_i
U = sum_i f_i * [J1_i + s_i * (J2_i - mu_i*J1_i)]
mean_energy_eV = U/N
```

Because `mu_i=J1_i/M_i`, reconstruction preserves the electron-number
mass exactly while correctly changing the first energy moment. It
rejects nonfinite/negative EEPF, nonunit normalization, mismatched
geometry, and energy outside `[0,Emax]`. The legacy constant-cell
M6b path is unchanged when no reconstruction reference is supplied.

The Picard convergence gate now requires **three** independent
observables to stabilize on successive eigen re-solves: normalized
EEPF L1, maximum ionization/attachment rate relative change, and
reconstructed mean-energy relative change. A failed criterion returns
`HOLD_PICARD_MAX_UPDATES` with history. Excitation and superelastic
rates are still not part of this reconstructed Q or convergence check.

## Actual compiled C++ evidence

- Source commit: `28aafcc5c4aa0ae4f871405b4a86161115c230ab`.
- GitHub Repository CI run:
  https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/40896625103
- `Native Boltzmann EEPF development controls`: **SUCCESS**, including
  `P0-3 conservative reconstructed growth operator and actual M6b Picard
  eigen re-solves (synthetic)`, compiled under strict C++17 flags.
- `Public immutable Physics runtime smoke`: **SUCCESS**.
- Full `validate` status must be verified independently; success of
  the C++ job does not imply the whole workflow passed.

Manufactured positive EEPF, intentionally very broad cell
`[2,15.71321743]` eV and narrow last cell `[15.71321743,15.8367]`:

| Observable | Actual C++ |
|---|---:|
| Reconstructed number mass | 1 |
| Exact reconstructed mean energy | 5.27739 eV |
| Legacy constant-cell mean energy, same cell averages | 6.57199 eV |
| Independent 50,000-midpoint-per-cell energy oracle | PASS (<1e-6 relative) |
| Synthetic 15.8 eV threshold rate ratio | 0.649606 (NOT real C3) |
| Growth operator number balance | 0 |
| Coupled eigen residual | 2.41177e-14 |
| Nominal Picard iterations | 3 |
| Nominal final EEPF L1 change | 2.1556e-14 |
| Nominal final growth-rate relative change | 6.62992e-12 |
| Nominal final reconstructed mean-energy relative change | 8.13059e-12 |
| One-update energy-only strict gate | HOLD as expected |
| One-update L1/rate strict gate | HOLD as expected |

The 1.2946 eV difference is **deliberately manufactured** with a very
wide cell to amplify the missed moment; it is **not** an error estimate
for BOLSIG+ Example 4 or the real Ar C3 ionization process.

An initial CI run
https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/40896537411
failed because the new helper declaration was not included by the M6b
translation unit; commit `28aafcc5c4aa` added the missing header.
The corrected run above compiles and passes the actual C++ tests.

## Remaining blockers and next implementation

- Reconstruct excitation and inverse superelastic gain/loss consistently
  with positivity and detailed balance; compare the corresponding
  energy-loss rates to Q using the same subcell integrals.
- Couple reconstructed Picard with strict independent Emax/mesh
  convergence; the previous 11.12% synthetic grid-to-grid EEPF L1
  remains a HOLD.
- Implement scalable 400–1000+ cell temporal-growth eigensolver.
- Verify 151 genuine BOLSIG+ Example 1–4 conditions using independently
  selected Emax and rights-safe native reference data. The original
  Example 4 C3 +13.02%, Example 2 R5 DC mobility ~10%,
  Example 1 400 Td ~4%, and O2 three-body density semantics are not
  resolved by this synthetic test.

**Verdict:** reconstructed mean-energy moment and energy convergence
guard are implemented and C++ tested. P0-3 remains PARTIAL;
PRs #408/#413 remain Draft, Science HOLD, no main merge or
production Oxygen ICP change.
