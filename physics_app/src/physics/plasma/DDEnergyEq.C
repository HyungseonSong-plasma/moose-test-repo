#include "DDEnergyEq.h"
#include "Chemistry.h"

#include <cmath>

namespace Plasma
{
namespace
{
// Every drift-diffusion species uses one internally resolved energy state.
// The MOOSE [Energy] block deliberately exposes no "variable" option.
VariableName
energyStateName(const std::string & species)
{
  return "log_" + species + "_energy";
}
} // namespace

InputParameters
DDEnergyEq::validParams()
{
  InputParameters params = PlasmaInterface::validParams();
  params.addClassDescription(
      "Create or reuse the FEM electron log-molar energy state.");
  params.addParam<std::vector<std::string>>(
      "fem_species", {}, "Electron species solved with finite-element variables.");
  params.addParam<std::vector<std::string>>(
      "fvm_species", {}, "Electron species solved with finite-volume variables.");
  params.addParam<MaterialPropertyName>(
      "rf_heating_material", "Existing electron-energy heating source in the equation's units.");
  params.addParam<Real>(
      "initial_molar_energy_density_eV",
      "Required when auto-creating log_e_energy: exp(log_e_energy) [eV mol/m^3], >0.");
  return params;
}

DDEnergyEq::DDEnergyEq(const InputParameters & parameters)
  : PlasmaInterface(parameters)
{
  const auto & finite_element_species = getParam<std::vector<std::string>>("fem_species");
  const auto & finite_volume_species = getParam<std::vector<std::string>>("fvm_species");
  if (!finite_volume_species.empty())
    paramError("fvm_species",
               "Finite-volume electron energy is not supported by this input check yet.");

  if (finite_element_species.size() != 1 || finite_element_species.front() != "e")
    paramError("fem_species", "Electron energy requires fem_species = 'e'.");

  validateSpeciesInputs(finite_element_species,
                        finite_volume_species,
                        {energyStateName(finite_element_species.front())});
  if (isParamValid("initial_molar_energy_density_eV"))
  {
    const Real initial = getParam<Real>("initial_molar_energy_density_eV");
    if (!std::isfinite(initial) || initial <= 0.0)
      paramError("initial_molar_energy_density_eV",
                 "Initial molar energy density must be finite and strictly positive.");
  }
  saveSolverVariableName(energyStateName("e"));
  addRequiredPhysicsTask("add_variables_physics");
  addRequiredPhysicsTask("add_ics_physics");
}

void
DDEnergyEq::addSolverVariables()
{
  const auto variable = energyStateName("e");
  if (variableExists(variable, /*error_if_aux=*/true))
  {
    if (isParamValid("initial_molar_energy_density_eV"))
      paramError("initial_molar_energy_density_eV",
                 "An externally declared log_e_energy retains its own initial condition.");
    return;
  }
  if (!isParamValid("initial_molar_energy_density_eV"))
    paramError("initial_molar_energy_density_eV",
               "Auto-created log_e_energy requires an explicit positive initial molar "
               "energy density [eV mol/m^3].");

  const std::string type = "MooseVariable";
  auto params = getFactory().getValidParams(type);
  assignBlocks(params, _blocks);
  params.set<SolverSystemName>("solver_sys") = getSolverSystem(variable);
  getProblem().addVariable(type, variable, params);
  _created_energy_variable = true;
}

void
DDEnergyEq::addInitialConditions()
{
  if (!_created_energy_variable)
    return;
  const auto variable = energyStateName("e");
  if (!shouldCreateIC(variable, _blocks, /*default IC*/ false, /*duplicate error*/ true))
    return;
  const std::string type = "ConstantIC";
  auto params = getFactory().getValidParams(type);
  params.set<VariableName>("variable") = variable;
  // The solved state is log of molar energy density, not log(number density).
  params.set<Real>("value") = std::log(getParam<Real>("initial_molar_energy_density_eV"));
  assignBlocks(params, _blocks);
  getProblem().addInitialCondition(type, name() + "_initial_energy", params);
}

void
DDEnergyEq::checkIntegrity() const
{
  const auto variable = energyStateName(getParam<std::vector<std::string>>("fem_species").front());
  validateExistingSpeciesVariables(getParam<std::vector<std::string>>("fem_species"),
                                   getParam<std::vector<std::string>>("fvm_species"),
                                   {variable});
  if (isParamValid("rf_heating_material"))
    requireUniqueFEKernel("MatBodyForce", variable);
  if (chemistryEnabled() && chemistryData().hasElectronEnergySource())
    requireUniqueFEKernel("FunctorKernel", variable);
}

void
DDEnergyEq::addFEKernels()
{
  const auto variable = energyStateName(getParam<std::vector<std::string>>("fem_species").front());
  if (isParamValid("rf_heating_material"))
  {
    const std::string type = "MatBodyForce";
    auto params = getFactory().getValidParams(type);
    params.set<NonlinearVariableName>("variable") = variable;
    params.set<MaterialPropertyName>("material_property") =
        getParam<MaterialPropertyName>("rf_heating_material");
    assignBlocks(params, _blocks);
    getProblem().addKernel(type, name() + "_rf_heating", params);
  }

  if (chemistryEnabled() && chemistryData().hasElectronEnergySource())
  {
    // Chemistry first collects all reaction channels from [Plasmas]/files,
    // preserving a separate progress R_k and signed electron energy change
    // delta_epsilon_k for each reaction ID (including identical equations).
    // It sums delta_epsilon_k * R_k into the single Q_e_molar_eV Functor.
    // Connect that total once on the RHS: never create per-reaction Kernels,
    // reverse its sign, or apply an implicit energy-unit conversion here.
    const std::string type = "FunctorKernel";
    auto params = getFactory().getValidParams(type);
    params.set<NonlinearVariableName>("variable") = variable;
    params.set<MooseFunctorName>("functor") = "Q_e_molar_eV";
    params.set<bool>("functor_on_rhs") = true;
    assignBlocks(params, _blocks);
    getProblem().addKernel(type, name() + "_chemistry_energy", params);
  }

}

}

using Plasma::DDEnergyEq;
registerPhysicsBaseTasks("PhysicsApp", DDEnergyEq);
registerMooseAction("PhysicsApp", DDEnergyEq, "add_variables_physics");
registerMooseAction("PhysicsApp", DDEnergyEq, "add_ics_physics");
registerMooseAction("PhysicsApp", DDEnergyEq, "check_integrity");
registerMooseAction("PhysicsApp", DDEnergyEq, "add_kernel");
