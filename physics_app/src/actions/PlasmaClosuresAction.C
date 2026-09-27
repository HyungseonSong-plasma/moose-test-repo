#include "PlasmaClosuresAction.h"

#include "FEProblemBase.h"
#include "Factory.h"

#include <string>

registerMooseAction("PhysicsApp", PlasmaClosuresAction, "add_functor_material");

InputParameters
PlasmaClosuresAction::validParams()
{
  InputParameters params = Action::validParams();
  params.addClassDescription(
      "Composes electron closure, electron-impact kinetics, heavy-particle transport, "
      "and plasma charge-density materials from one user-facing block.");

  params.addParam<bool>(
      "create_electron_closure",
      true,
      "Create PhysicsElectronClosureMaterial.");
  params.addParam<bool>(
      "create_electron_kinetics",
      false,
      "Create PhysicsElectronKineticsMaterial.");
  params.addParam<bool>(
      "create_heavy_transport",
      false,
      "Create PhysicsHeavyTransportMaterial.");
  params.addParam<bool>(
      "create_charge_density",
      false,
      "Create PhysicsPlasmaChargeDensityMaterial.");

  // Electron closure inputs.
  params.addParam<MooseFunctorName>(
      "normalized_electron_density",
      "Normalized electron number-density state used by the electron closure.");
  params.addParam<MooseFunctorName>(
      "normalized_electron_energy_density",
      "Normalized electron energy-density state used by the electron closure.");
  params.addParam<Real>(
      "electron_energy_reference_eV",
      "Electron-energy normalization scale [eV].");
  params.addParam<MooseFunctorName>("gas_pressure", "Neutral-gas pressure [Pa].");
  params.addParam<MooseFunctorName>("gas_temperature", "Neutral-gas temperature [K].");
  params.addParam<FileName>(
      "electron_transport_table_file",
      "Three-column electron transport table: mean energy, mu_e*N_n, D_e*N_n.");
  params.addParam<std::string>(
      "electron_transport_bounds_policy",
      "error",
      "Electron transport lookup behavior: 'error' or 'clamp'.");

  // Electron closure output names.
  params.addParam<MooseFunctorName>(
      "electron_mean_energy_output",
      "electron_mean_energy_eV",
      "Published mean electron energy [eV].");
  params.addParam<MooseFunctorName>(
      "electron_temperature_output",
      "electron_temperature_K",
      "Published electron temperature [K].");
  params.addParam<MooseFunctorName>(
      "neutral_number_density_output",
      "neutral_number_density",
      "Published neutral number density [1/m^3].");
  params.addParam<MooseFunctorName>(
      "electron_reduced_mobility_output",
      "electron_reduced_mobility",
      "Published reduced electron mobility.");
  params.addParam<MooseFunctorName>(
      "electron_reduced_diffusion_output",
      "electron_reduced_diffusion",
      "Published reduced electron diffusion.");
  params.addParam<MooseFunctorName>(
      "electron_mobility_output",
      "electron_mobility",
      "Published electron mobility [m^2/(V s)].");
  params.addParam<MooseFunctorName>(
      "electron_diffusion_output",
      "electron_diffusion",
      "Published electron diffusion coefficient [m^2/s].");
  params.addParam<MooseFunctorName>(
      "electron_energy_mobility_output",
      "electron_energy_mobility",
      "Published electron-energy mobility [m^2/(V s)].");
  params.addParam<MooseFunctorName>(
      "electron_energy_diffusion_output",
      "electron_energy_diffusion",
      "Published electron-energy diffusion coefficient [m^2/s].");

  // Optional externally supplied electron state for configurations that do not
  // create the electron closure in this Action.
  params.addParam<MooseFunctorName>(
      "electron_mean_energy",
      "External mean-electron-energy functor [eV]. Used when create_electron_closure=false.");
  params.addParam<MooseFunctorName>(
      "electron_temperature",
      "External electron-temperature functor [K]. Used by heavy transport when needed.");
  params.addParam<MooseFunctorName>(
      "electron_number_density",
      "Physical electron number density [1/m^3] used by kinetics, heavy transport, and charge.");

  // Electron kinetics.
  params.addParam<std::vector<FileName>>(
      "electron_impact_rate_table_files",
      "Electron-impact rate tables, one per reaction.");
  params.addParam<std::vector<MooseFunctorName>>(
      "electron_impact_target_molar_concentrations",
      "Target molar concentration functors, one per electron-impact reaction.");
  params.addParam<std::vector<std::string>>(
      "electron_impact_reaction_progress_names",
      "Published reaction-progress functor names, one per electron-impact reaction.");

  // Heavy-particle transport.
  params.addParam<MooseFunctorName>(
      "heavy_species_temperature",
      "Heavy-species temperature [K]. Defaults to gas_temperature.");
  params.addParam<MooseFunctorName>(
      "heavy_species_pressure",
      "Heavy-species absolute pressure [Pa]. Defaults to gas_pressure.");
  params.addParam<FileName>(
      "heavy_transport_data_file",
      "Heavy-species transport database.");
  params.addParam<std::vector<std::string>>(
      "heavy_species",
      "Ordered active heavy-species names.");
  params.addParam<std::vector<MooseFunctorName>>(
      "heavy_mass_fractions",
      "Heavy-species mass-fraction functors in heavy_species order.");
  params.addParam<std::vector<MooseFunctorName>>(
      "heavy_thermal_diffusion_names",
      "Optional D_T output names in heavy_species order.");
  params.addParam<std::vector<MooseFunctorName>>(
      "heavy_thermal_diffusion_ratio_names",
      "Optional kT output names in heavy_species order.");
  params.addParam<std::vector<MooseFunctorName>>(
      "heavy_mixture_diffusion_names",
      "Optional D_mix output names in heavy_species order.");

  // Charge-density closure.
  params.addParam<MooseFunctorName>(
      "mixture_density", "Heavy-mixture mass density [kg/m^3].");
  params.addParam<std::vector<std::string>>(
      "charged_species_ids",
      "Solver-safe charged-heavy-species identifiers.");
  params.addParam<std::vector<MooseFunctorName>>(
      "charged_species_mass_fractions",
      "Charged-heavy-species mass-fraction functors.");
  params.addParam<std::vector<Real>>(
      "charged_species_molar_masses",
      "Charged-heavy-species molar masses [kg/mol].");
  params.addParam<std::vector<Real>>(
      "charged_species_charge_numbers",
      "Signed charged-heavy-species charge numbers.");

  return params;
}

PlasmaClosuresAction::PlasmaClosuresAction(const InputParameters & parameters)
  : Action(parameters)
{
  validateConfiguration();
}

void
PlasmaClosuresAction::validateConfiguration() const
{
  auto require = [this](const std::string & parameter, const std::string & owner)
  {
    if (!isParamValid(parameter))
      paramError(parameter, parameter, " is required when ", owner, " is enabled.");
  };

  if (getParam<bool>("create_electron_closure"))
  {
    require("normalized_electron_density", "create_electron_closure");
    require("normalized_electron_energy_density", "create_electron_closure");
    require("electron_energy_reference_eV", "create_electron_closure");
    require("gas_pressure", "create_electron_closure");
    require("gas_temperature", "create_electron_closure");
    require("electron_transport_table_file", "create_electron_closure");
  }

  if (getParam<bool>("create_electron_kinetics"))
  {
    require("electron_number_density", "create_electron_kinetics");
    require("electron_impact_rate_table_files", "create_electron_kinetics");
    require("electron_impact_target_molar_concentrations", "create_electron_kinetics");
    require("electron_impact_reaction_progress_names", "create_electron_kinetics");

    if (!getParam<bool>("create_electron_closure") && !isParamValid("electron_mean_energy"))
      paramError("electron_mean_energy",
                 "electron_mean_energy is required for electron kinetics when "
                 "create_electron_closure=false.");
  }

  if (getParam<bool>("create_heavy_transport"))
  {
    require("heavy_transport_data_file", "create_heavy_transport");
    require("heavy_species", "create_heavy_transport");
    require("heavy_mass_fractions", "create_heavy_transport");

    if (!isParamValid("heavy_species_temperature") && !isParamValid("gas_temperature"))
      paramError("heavy_species_temperature",
                 "Provide heavy_species_temperature or gas_temperature when "
                 "create_heavy_transport=true.");

    if (!isParamValid("heavy_species_pressure") && !isParamValid("gas_pressure"))
      paramError("heavy_species_pressure",
                 "Provide heavy_species_pressure or gas_pressure when "
                 "create_heavy_transport=true.");
  }

  if (getParam<bool>("create_charge_density"))
  {
    require("mixture_density", "create_charge_density");
    require("electron_number_density", "create_charge_density");
    require("charged_species_ids", "create_charge_density");
    require("charged_species_mass_fractions", "create_charge_density");
    require("charged_species_molar_masses", "create_charge_density");
    require("charged_species_charge_numbers", "create_charge_density");
  }
}

void
PlasmaClosuresAction::act()
{
  const std::string prefix = name();

  if (getParam<bool>("create_electron_closure"))
  {
    auto material_params = _factory.getValidParams("PhysicsElectronClosureMaterial");

    material_params.set<MooseFunctorName>("normalized_electron_density") =
        getParam<MooseFunctorName>("normalized_electron_density");
    material_params.set<MooseFunctorName>("normalized_electron_energy_density") =
        getParam<MooseFunctorName>("normalized_electron_energy_density");
    material_params.set<Real>("electron_energy_reference_eV") =
        getParam<Real>("electron_energy_reference_eV");
    material_params.set<MooseFunctorName>("gas_pressure") =
        getParam<MooseFunctorName>("gas_pressure");
    material_params.set<MooseFunctorName>("gas_temperature") =
        getParam<MooseFunctorName>("gas_temperature");
    material_params.set<FileName>("transport_table_file") =
        getParam<FileName>("electron_transport_table_file");
    material_params.set<std::string>("lookup_bounds_policy") =
        getParam<std::string>("electron_transport_bounds_policy");

    for (const auto & parameter :
         {"electron_mean_energy_output",
          "electron_temperature_output",
          "neutral_number_density_output",
          "electron_reduced_mobility_output",
          "electron_reduced_diffusion_output",
          "electron_mobility_output",
          "electron_diffusion_output",
          "electron_energy_mobility_output",
          "electron_energy_diffusion_output"})
      material_params.set<MooseFunctorName>(parameter) =
          getParam<MooseFunctorName>(parameter);

    _problem->addFunctorMaterial(
        "PhysicsElectronClosureMaterial", prefix + "_electron_closure", material_params);
  }

  if (getParam<bool>("create_electron_kinetics"))
  {
    auto material_params = _factory.getValidParams("PhysicsElectronKineticsMaterial");

    const MooseFunctorName mean_energy =
        isParamValid("electron_mean_energy")
            ? getParam<MooseFunctorName>("electron_mean_energy")
            : getParam<MooseFunctorName>("electron_mean_energy_output");

    material_params.set<MooseFunctorName>("electron_mean_energy") = mean_energy;
    material_params.set<MooseFunctorName>("electron_number_density") =
        getParam<MooseFunctorName>("electron_number_density");
    material_params.set<std::vector<FileName>>("rate_table_files") =
        getParam<std::vector<FileName>>("electron_impact_rate_table_files");
    material_params.set<std::vector<MooseFunctorName>>("target_molar_concentrations") =
        getParam<std::vector<MooseFunctorName>>(
            "electron_impact_target_molar_concentrations");
    material_params.set<std::vector<std::string>>("reaction_progress_names") =
        getParam<std::vector<std::string>>(
            "electron_impact_reaction_progress_names");

    _problem->addFunctorMaterial(
        "PhysicsElectronKineticsMaterial", prefix + "_electron_kinetics", material_params);
  }

  if (getParam<bool>("create_heavy_transport"))
  {
    auto material_params = _factory.getValidParams("PhysicsHeavyTransportMaterial");

    material_params.set<MooseFunctorName>("temperature") =
        isParamValid("heavy_species_temperature")
            ? getParam<MooseFunctorName>("heavy_species_temperature")
            : getParam<MooseFunctorName>("gas_temperature");

    material_params.set<MooseFunctorName>("pressure") =
        isParamValid("heavy_species_pressure")
            ? getParam<MooseFunctorName>("heavy_species_pressure")
            : getParam<MooseFunctorName>("gas_pressure");

    material_params.set<FileName>("transport_data_file") =
        getParam<FileName>("heavy_transport_data_file");
    material_params.set<std::vector<std::string>>("species") =
        getParam<std::vector<std::string>>("heavy_species");
    material_params.set<std::vector<MooseFunctorName>>("mass_fractions") =
        getParam<std::vector<MooseFunctorName>>("heavy_mass_fractions");

    if (isParamValid("electron_temperature"))
      material_params.set<MooseFunctorName>("electron_temperature") =
          getParam<MooseFunctorName>("electron_temperature");
    else if (getParam<bool>("create_electron_closure"))
      material_params.set<MooseFunctorName>("electron_temperature") =
          getParam<MooseFunctorName>("electron_temperature_output");

    if (isParamValid("electron_number_density"))
      material_params.set<MooseFunctorName>("electron_number_density") =
          getParam<MooseFunctorName>("electron_number_density");

    if (isParamValid("heavy_thermal_diffusion_names"))
      material_params.set<std::vector<MooseFunctorName>>("D_T_names") =
          getParam<std::vector<MooseFunctorName>>("heavy_thermal_diffusion_names");

    if (isParamValid("heavy_thermal_diffusion_ratio_names"))
      material_params.set<std::vector<MooseFunctorName>>("kT_names") =
          getParam<std::vector<MooseFunctorName>>(
              "heavy_thermal_diffusion_ratio_names");

    if (isParamValid("heavy_mixture_diffusion_names"))
      material_params.set<std::vector<MooseFunctorName>>("D_mix_names") =
          getParam<std::vector<MooseFunctorName>>("heavy_mixture_diffusion_names");

    _problem->addFunctorMaterial(
        "PhysicsHeavyTransportMaterial", prefix + "_heavy_transport", material_params);
  }

  if (getParam<bool>("create_charge_density"))
  {
    auto material_params = _factory.getValidParams("PhysicsPlasmaChargeDensityMaterial");

    material_params.set<MooseFunctorName>("density") =
        getParam<MooseFunctorName>("mixture_density");
    material_params.set<MooseFunctorName>("electron_density") =
        getParam<MooseFunctorName>("electron_number_density");
    material_params.set<std::vector<std::string>>("ion_ids") =
        getParam<std::vector<std::string>>("charged_species_ids");
    material_params.set<std::vector<MooseFunctorName>>("ion_mass_fractions") =
        getParam<std::vector<MooseFunctorName>>("charged_species_mass_fractions");
    material_params.set<std::vector<Real>>("ion_molar_masses") =
        getParam<std::vector<Real>>("charged_species_molar_masses");
    material_params.set<std::vector<Real>>("ion_charges") =
        getParam<std::vector<Real>>("charged_species_charge_numbers");

    _problem->addFunctorMaterial(
        "PhysicsPlasmaChargeDensityMaterial", prefix + "_charge_density", material_params);
  }
}
