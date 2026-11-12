# Issue #402 S6-417 Chemistry cutover overlay; use ONLY with the staged S6
# native layers after the listed legacy electron-particle and energy Kernels
# have been removed in scratch. See chemistry/README.md; not a standalone deck.
# This overlay replaces (not supplements) migrated_continuity.i.
[Physics]
  [Plasmas]
    files = 'chemistry/oxygen_s6_common.json chemistry/oxygen_s6_417.json'
    [Transport]
      [Chemistry]
        block = plasma
      []
      [DriftDiffusion]
        [Continuity]
          block = plasma
          fem_species = 'e'
          fvm_species = 'O2p Om Op'
          fem_potential = potential
        []
        [Energy]
          block = plasma
          fem_species = 'e'
          variable = log_energy
        []
      []
    []
  []
[]
[FunctorMaterials]
  # Native EI-02/EI-17 delta_epsilon_* give a POSITIVE loss magnitude;
  # the Chemistry JSON functor contract requires signed energy change.
  [ei02_signed_energy_change]
    type = ADParsedFunctorMaterial
    property_name = signed_delta_epsilon_EI02_eV
    functor_names = 'delta_epsilon_EI02_eV'
    functor_symbols = 'loss'
    expression = '-loss'
    block = plasma
  []
  [ei17_signed_energy_change]
    type = ADParsedFunctorMaterial
    property_name = signed_delta_epsilon_EI17_eV
    functor_names = 'delta_epsilon_EI17_eV'
    functor_symbols = 'loss'
    expression = '-loss'
    block = plasma
  []
  [O2p_species_transport_alias]
    type = SpeciesTransportAliasMaterial
    species_id = O2p
    mobility_source = ion_mobility
    diffusivity_source = ion_diffusion
  []
  [Om_species_transport_alias]
    type = SpeciesTransportAliasMaterial
    species_id = Om
    mobility_source = negative_ion_mobility
    diffusivity_source = negative_ion_diffusion
  []
  [Op_species_transport_alias]
    type = SpeciesTransportAliasMaterial
    species_id = Op
    mobility_source = atomic_positive_ion_mobility
    diffusivity_source = atomic_positive_ion_diffusion
  []
[]
