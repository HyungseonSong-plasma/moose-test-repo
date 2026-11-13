#include "PlasmaDriftDiffusionBoundaryAction.h"

#include "ActionWarehouse.h"
#include "Chemistry.h"
#include "FEProblemBase.h"

#include <cmath>

registerMooseAction("PhysicsApp", PlasmaDriftDiffusionBoundaryAction, "add_functor_material");
registerMooseAction("PhysicsApp", PlasmaDriftDiffusionBoundaryAction, "add_bc");

InputParameters
PlasmaDriftDiffusionBoundaryAction::validParams()
{
  auto params = Action::validParams();
  params.addClassDescription(
      "Opt-in JSON-owned DriftDiffusion plasma electron wall boundaries. "
      "Reuses existing mean-energy, adjacent-sheath flux Materials and paired FEM BCs.");
  params.addParam<MooseEnum>(
      "plasma_boundary", MooseEnum("none json", "none"),
      "none: retain legacy explicit input. json: use [Plasmas]/files "
      "drift_diffusion_boundary entries and generate only adjacent_sheath walls.");
  params.addParam<VariableName>(
      "plasma_boundary_particle_variable", "log_ne",
      "Existing FEM log-molar electron particle solver variable.");
  params.addParam<VariableName>(
      "plasma_boundary_energy_variable", "log_energy",
      "Existing FEM log-molar electron energy solver variable.");
  params.addParam<MooseFunctorName>(
      "plasma_boundary_electron_density", "n_e_physical",
      "Existing physical electron number density Functor [1/m^3].");
  params.addParam<MooseFunctorName>(
      "plasma_boundary_potential", "potential",
      "Existing electrostatic potential Functor [V].");
  params.addParam<MooseEnum>(
      "plasma_boundary_mean_energy_owner", MooseEnum("generated external", "generated"),
      "generated: create log-molar mean-energy bridge; external: reuse existing Functor.");
  params.addParam<MooseFunctorName>(
      "plasma_boundary_mean_energy", "mean_en_solved",
      "Existing or generated mean-energy Functor [eV].");
  params.addParam<MooseEnum>(
      "plasma_boundary_wall_flux_owner", MooseEnum("generated external", "generated"),
      "generated: create canonical adjacent-sheath flux; external: reuse existing flux.");
  params.addParam<MooseFunctorName>(
      "plasma_boundary_wall_number_flux", "electron_wall_number_flux",
      "One positive outward electron number-flux Functor [1/(m^2 s)] shared by both BCs.");
  params.addParam<Real>(
      "plasma_boundary_sticking", 1.0, "Shared electron wall sticking probability [0,1].");
  params.addParam<bool>(
      "plasma_boundary_use_element_gradient_for_potential", true,
      "Use adjacent-element -grad(phi) for a continuous FEM potential.");
  return params;
}

PlasmaDriftDiffusionBoundaryAction::PlasmaDriftDiffusionBoundaryAction(
    const InputParameters & params)
  : Action(params)
{
  if (getParam<MooseEnum>("plasma_boundary") == "none")
  {
    // An opt-out must not silently discard a partially migrated configuration.
    for (const auto * key : {"plasma_boundary_particle_variable",
                             "plasma_boundary_energy_variable",
                             "plasma_boundary_electron_density",
                             "plasma_boundary_potential",
                             "plasma_boundary_mean_energy_owner",
                             "plasma_boundary_mean_energy",
                             "plasma_boundary_wall_flux_owner",
                             "plasma_boundary_wall_number_flux",
                             "plasma_boundary_sticking",
                             "plasma_boundary_use_element_gradient_for_potential"})
      if (isParamSetByUser(key))
        paramError("plasma_boundary", "Inactive plasma_boundary=none cannot configure ", key);
    return;
  }

  const auto & particle = getParam<VariableName>("plasma_boundary_particle_variable");
  const auto & energy = getParam<VariableName>("plasma_boundary_energy_variable");
  if (particle.empty() || energy.empty() || particle == energy)
    paramError("plasma_boundary_particle_variable",
               "FEM electron continuity and energy variables must be distinct and nonempty.");

  const auto sticking = getParam<Real>("plasma_boundary_sticking");
  if (!std::isfinite(sticking) || sticking < 0.0 || sticking > 1.0)
    paramError("plasma_boundary_sticking", "Wall sticking must be finite and in [0,1].");

  if (getParam<MooseEnum>("plasma_boundary_wall_flux_owner") == "generated" &&
      getParam<MooseFunctorName>("plasma_boundary_wall_number_flux") !=
          "electron_wall_number_flux")
    paramError("plasma_boundary_wall_number_flux",
               "Generated adjacent-sheath Material owns electron_wall_number_flux. "
               "Select plasma_boundary_wall_flux_owner=external for a different name.");
  if (getParam<MooseEnum>("plasma_boundary_wall_flux_owner") == "external" &&
      (isParamSetByUser("plasma_boundary_sticking") ||
       isParamSetByUser("plasma_boundary_use_element_gradient_for_potential")))
    paramError("plasma_boundary_wall_flux_owner",
               "External flux retains its own sticking and gradient law.");

  for (const auto * key : {"plasma_boundary_electron_density",
                            "plasma_boundary_mean_energy",
                            "plasma_boundary_potential",
                            "plasma_boundary_wall_number_flux"})
    if (getParam<MooseFunctorName>(key).empty())
      paramError("plasma_boundary", "Empty required wall Functor name: ", key);
}

void
PlasmaDriftDiffusionBoundaryAction::act()
{
  if (getParam<MooseEnum>("plasma_boundary") != "json")
    return;

  // The exact JSON mechanism is owned by the root PlasmasAction, not read
  // again or copied from the .i. One root catalogue avoids inconsistent
  // names when multiple chemistry files are supplied.
  const auto roots = _awh.getActions<PlasmasAction>();
  if (roots.size() != 1)
    paramError("plasma_boundary",
               "Exactly one [Physics]/[Plasmas] JSON mechanism owner is required.");
  const auto & data = roots.front()->data();
  if (!data.hasDriftDiffusionBoundary())
    paramError("plasma_boundary",
               "plasma_boundary=json requires drift_diffusion_boundary in [Plasmas]/files.");

  const auto & entries = data.driftDiffusionBoundaries();
  bool has_sheath = false;
  for (const auto & [alias, config] : entries)
    if (config.electron_model == "adjacent_sheath")
      has_sheath = true;
  if (!has_sheath)
    paramError("plasma_boundary",
               "No adjacent_sheath electron wall is declared in drift_diffusion_boundary. "
               "Use plasma_boundary=none for fully external/open boundaries.");

  const auto & mean = getParam<MooseFunctorName>("plasma_boundary_mean_energy");
  const auto & flux = getParam<MooseFunctorName>("plasma_boundary_wall_number_flux");

  if (_current_task == "add_functor_material")
  {
    if (getParam<MooseEnum>("plasma_boundary_mean_energy_owner") == "generated")
    {
      const std::string type = "PhysicsElectronMeanEnergyMaterial";
      auto params = _factory.getValidParams(type);
      params.set<MooseEnum>("state_form") = "log_molar_eV";
      params.set<MooseFunctorName>("electron_energy_density") =
          getParam<VariableName>("plasma_boundary_energy_variable");
      params.set<MooseFunctorName>("electron_density") =
          getParam<VariableName>("plasma_boundary_particle_variable");
      params.set<MooseFunctorName>("mean_energy_output") = mean;
      _problem->addFunctorMaterial(type, "plasma_boundary_mean_energy_bridge", params);
    }
    if (getParam<MooseEnum>("plasma_boundary_wall_flux_owner") == "generated")
    {
      const std::string type = "PhysicsElectronAdjacentSheathWallFluxMaterial";
      auto params = _factory.getValidParams(type);
      params.set<MooseFunctorName>("electron_density") =
          getParam<MooseFunctorName>("plasma_boundary_electron_density");
      params.set<MooseFunctorName>("mean_energy") = mean;
      params.set<MooseFunctorName>("potential") =
          getParam<MooseFunctorName>("plasma_boundary_potential");
      params.set<Real>("sticking") = getParam<Real>("plasma_boundary_sticking");
      params.set<bool>("use_element_gradient_for_potential") =
          getParam<bool>("plasma_boundary_use_element_gradient_for_potential");
      _problem->addFunctorMaterial(type, "plasma_boundary_electron_wall_flux", params);
    }
    return;
  }

  if (_current_task == "add_bc")
  {
    // Existing BCs read precisely the same positive plasma-side number flux
    // with a sided FaceArg. open and external entries are never given these BCs.
    for (const auto & [alias, config] : entries)
    {
      if (config.electron_model != "adjacent_sheath")
        continue;
      {
        const std::string type = "FEMElectronSheathBC";
        auto params = _factory.getValidParams(type);
        params.set<NonlinearVariableName>("variable") =
            getParam<VariableName>("plasma_boundary_particle_variable");
        params.set<MooseFunctorName>("wall_number_flux") = flux;
        params.set<std::vector<BoundaryName>>("boundary") = {config.mesh_boundary};
        _problem->addBoundaryCondition(type, "plasma_boundary_particle_" + alias, params);
      }
      {
        const std::string type = "FEMElectronEnergySheathBC";
        auto params = _factory.getValidParams(type);
        params.set<NonlinearVariableName>("variable") =
            getParam<VariableName>("plasma_boundary_energy_variable");
        params.set<MooseFunctorName>("wall_number_flux") = flux;
        params.set<MooseFunctorName>("mean_energy") = mean;
        params.set<std::vector<BoundaryName>>("boundary") = {config.mesh_boundary};
        _problem->addBoundaryCondition(type, "plasma_boundary_energy_" + alias, params);
      }
    }
  }
}
