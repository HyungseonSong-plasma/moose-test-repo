# O2 electron-impact dissociation rate table

Reaction:

`e + O2 -> e + O + O`

Energy loss used by the COMSOL oxygen chemistry model: 6.0 eV/event.

## Cross-section source

Phelps-compatible O2 electron-collision data for the 6.0 eV dissociation channel:

| Electron energy (eV) | sigma (m^2) |
|---:|---:|
| 6.0 | 0.0 |
| 7.0 | 1.50e-21 |
| 7.8 | 2.30e-21 |
| 9.0 | 2.30e-21 |
| 10.0 | 2.10e-21 |
| 12.0 | 1.65e-21 |
| 15.0 | 1.05e-21 |
| 17.0 | 6.50e-22 |
| 20.0 | 4.75e-22 |
| 45.0 | 1.90e-22 |
| 100.0 | 0.0 |

COMSOL Plasma Module 6.4 Ar/O2 ICP/CCP examples identify this channel as oxygen electron-impact reaction 13, dissociative excitation, with 6.0 eV energy loss. The COMSOL oxygen electron-impact set cites the Phelps oxygen collision data.

Public Phelps-compatible numerical cross sections were cross-checked against the Cantera example-data mechanism `methane-plasma-pavan-2023.yaml`, which contains the same `O2 + e => e + O + O` collision data.

## Conversion to the table used by Physics

The table `o2_dissociation.txt` uses the same first-column mean-electron-energy grid as `o2_ionization.txt`.

For each mean electron energy `eps_bar` the Maxwellian temperature is

`Te = (2/3) eps_bar`  [eV].

The number-density rate coefficient is

`k_num = integral sigma(E) v(E) f_M(E; Te) dE`  [m^3/s],

where

`v(E) = sqrt(2 e E / m_e)`

and the normalized Maxwellian energy distribution is

`f_M(E;Te) = 2/sqrt(pi) * sqrt(E) / Te^(3/2) * exp(-E/Te)`.

Cross sections are linearly interpolated between the tabulated collision-energy points and set to zero outside 6--100 eV. The integral is evaluated piecewise over the source cross-section intervals.

The Physics reaction material currently expects a molar bimolecular coefficient, so the stored second column is

`k_molar = N_A k_num`  [m^3/(mol s)].

Checks:

- eps_bar = 3.0 eV (Te = 2 eV): k_num = 2.9554867e-16 m^3/s, k_molar = 1.7798352e8 m^3/(mol s)
- eps_bar = 6.0 eV (Te = 4 eV): k_num = 1.1022027e-15 m^3/s, k_molar = 6.6376200e8 m^3/(mol s)

This file records provenance and conversion only. Adding the table does not activate the reaction in any input file.
