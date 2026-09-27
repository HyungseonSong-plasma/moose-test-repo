# PlasmaClosures Action

`[PlasmaClosures]` is the user-facing composition layer for PhysicsApp plasma closure
materials. It intentionally does **not** merge all closure physics into one large C++
class.

The default architecture is:

```text
PlasmaClosuresAction
├── PhysicsElectronClosureMaterial
├── PhysicsElectronKineticsMaterial       (optional)
├── PhysicsHeavyTransportMaterial         (optional)
└── PhysicsPlasmaChargeDensityMaterial    (optional)
```

## Electron closure

`PhysicsElectronClosureMaterial` owns both solved mean-energy reconstruction and
electron transport lookup:

```text
normalized electron density
normalized electron energy density
            │
            ▼
  electron_mean_energy_eV
            │
            ├── electron_temperature_K
            ├── electron_mobility
            ├── electron_diffusion
            ├── electron_energy_mobility
            └── electron_energy_diffusion
```

This replaces the need to configure separate mean-energy and transport-lookup
materials in new inputs.

## Electron kinetics

`PhysicsElectronKineticsMaterial` accepts vectors of rate-table files, target
molar concentrations, and output reaction-progress names. One material therefore
owns all configured electron-impact lookup tables.

## Heavy transport

`PhysicsHeavyTransportMaterial` is a semantic production wrapper around the
already-qualified `PhysicsThermalDiffusionMaterial`. The underlying implementation
continues to own mixture-averaged diffusion, thermal diffusion, and charged-charged
collision transport.

## Charge density

`PhysicsPlasmaChargeDensityMaterial` remains separate because electrostatic charge
closure is a distinct responsibility from transport closure.

## Example

```text
[PlasmaClosures]
  [plasma]
    normalized_electron_density = electron_density_normalized
    normalized_electron_energy_density = electron_energy_density_normalized
    electron_energy_reference_eV = 1.0
    gas_pressure = p_gas
    gas_temperature = T_g
    electron_transport_table_file = electron_moments.txt

    create_electron_kinetics = true
    electron_number_density = electron_density_m3
    electron_impact_rate_table_files = 'ionization.txt attachment.txt'
    electron_impact_target_molar_concentrations = 'c_O2 c_O2'
    electron_impact_reaction_progress_names = 'R_ionization R_attachment'

    create_heavy_transport = true
    heavy_transport_data_file = transport_data.txt
    heavy_species = 'O2 O2s O2p O Om Op Os'
    heavy_mass_fractions = 'w_O2 w_O2s w_O2p w_O w_Om w_Op w_Os'

    create_charge_density = true
    mixture_density = rho
    charged_species_ids = 'O2p Om Op'
    charged_species_mass_fractions = 'w_O2p w_Om w_Op'
    charged_species_molar_masses = '0.032 0.016 0.016'
    charged_species_charge_numbers = '1 -1 1'
  []
[]
```

Legacy material classes are retained while the new composition path is qualified.
