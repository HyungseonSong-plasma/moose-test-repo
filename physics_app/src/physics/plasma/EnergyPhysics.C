#include "EnergyPhysics.h"

namespace Plasma
{

InputParameters
EnergyPhysics::validParams()
{
  InputParameters params = PlasmaInterface::validParams();
  params.addClassDescription(
      "Checks existing energy inputs without creating or modifying solver equations.");
  params.addParam<std::vector<std::string>>(
      "fem_species", {}, "Electron species solved with finite-element variables.");
  params.addParam<std::vector<std::string>>(
      "fvm_species", {}, "Electron species solved with finite-volume variables.");
  params.addRequiredParam<VariableName>(
      "variable", "Existing solver variable for the electron energy equation.");
  return params;
}

EnergyPhysics::EnergyPhysics(const InputParameters & parameters)
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
                        {getParam<VariableName>("variable")});
}

void
EnergyPhysics::checkIntegrity() const
{
  validateExistingSpeciesVariables(getParam<std::vector<std::string>>("fem_species"),
                                   getParam<std::vector<std::string>>("fvm_species"),
                                   {getParam<VariableName>("variable")});
}

}

using Plasma::EnergyPhysics;
registerPhysicsBaseTasks("PhysicsApp", EnergyPhysics);
registerMooseAction("PhysicsApp", EnergyPhysics, "check_integrity");
