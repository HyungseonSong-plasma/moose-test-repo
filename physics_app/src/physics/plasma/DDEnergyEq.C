#include "DDEnergyEq.h"
#include "Chemistry.h"

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
      "Checks existing energy inputs without creating or modifying solver equations.");
  params.addParam<std::vector<std::string>>(
      "fem_species", {}, "Electron species solved with finite-element variables.");
  params.addParam<std::vector<std::string>>(
      "fvm_species", {}, "Electron species solved with finite-volume variables.");
  params.addParam<MaterialPropertyName>(
      "rf_heating_material", "Existing electron-energy heating source in the equation's units.");
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
registerMooseAction("PhysicsApp", DDEnergyEq, "check_integrity");
registerMooseAction("PhysicsApp", DDEnergyEq, "add_kernel");
