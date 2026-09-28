# PlasmaClosures Action

`[PlasmaClosures]` is the user-facing composition layer for PhysicsApp plasma closure
materials. The preferred API is role-based: each MultiApp creates only the closure
owned by its local physics state.

## Roles

```text
role = electron
  -> PhysicsElectronClosureMaterial
  -> PhysicsElectronKineticsMaterial only when reaction-table inputs are supplied

role = heavy_transport
  -> PhysicsHeavyTransportMaterial

role = electrostatic_charge
  -> PhysicsPlasmaChargeDensityMaterial
```

The old `create_electron_closure`, `create_electron_kinetics`,
`create_heavy_transport`, and `create_charge_density` switches remain available
under the default `role = custom` for backward compatibility. Do not combine an
explicit non-custom role with the legacy switches.

## MultiApp placement

```text
input.i
  [PlasmaClosures]
    [heavy]
      role = heavy_transport

fast_sub.i
  [PlasmaClosures]
    [electron]
      role = electron

poisson_sub.i
  [PlasmaClosures]
    [charge]
      role = electrostatic_charge
```

This is not duplicate closure work. Each block belongs to a different FEProblem /
MultiApp instance and consumes local state.

## Electron example

```text
[PlasmaClosures]
  [electron]
    role = electron

    normalized_electron_density = electron_density_hat
    normalized_electron_energy_density = n_epsilon
    electron_energy_reference_eV = 5.73276

    gas_pressure = p_gas
    gas_temperature = T_g
    electron_transport_table_file = electron_moments.txt

    electron_number_density = electron_density_m3
    electron_impact_rate_table_files = 'ionization.txt attachment.txt'
    electron_impact_target_molar_concentrations = 'c_O2 c_O2'
    electron_impact_reaction_progress_names = 'R_ionization R_attachment'
  []
[]
```

If no electron-impact table parameters are supplied, `role = electron` creates only
the electron state/transport closure.

## Heavy transport example

```text
[PlasmaClosures]
  [heavy]
    role = heavy_transport

    heavy_species_temperature = T_g
    heavy_species_pressure = p_gas
    electron_temperature = electron_temperature_K
    electron_number_density = electron_density_fast

    heavy_transport_data_file = transport_data.txt
    heavy_species = 'O2 O2s O2p O Om Op Os'
    heavy_mass_fractions = 'w_O2 w_O2s w_O2p w_O w_Om w_Op w_Os'
  []
[]
```

## Electrostatic charge example

```text
[PlasmaClosures]
  [charge]
    role = electrostatic_charge

    mixture_density = rho_const
    electron_number_density = electron_density_m3
    charged_species_ids = 'O2p Om Op'
    charged_species_mass_fractions = 'w_O2p_frozen w_Om_frozen w_Op_frozen'
    charged_species_molar_masses = '0.032 0.016 0.016'
    charged_species_charge_numbers = '1 -1 1'
  []
[]
```

The C++ materials remain separate internally; the role API only simplifies
user-facing composition.
