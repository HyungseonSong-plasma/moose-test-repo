#include "ContinuityPhysics.h"

namespace Plasma
{

InputParameters
ContinuityPhysics::validParams()
{
  InputParameters params = PlasmaInterface::validParams();
  params.addClassDescription(
      "Checks each plasma species against an existing solver variable of the correct type. "
      "Does not create variables or equations.");
  params.addParam<std::vector<std::string>>(
      "fem_species", {}, "Species using finite-element variables.");
  params.addParam<std::vector<std::string>>(
      "fvm_species", {}, "Species using finite-volume variables.");
  params.addRequiredParam<std::vector<VariableName>>(
      "variables", "Existing solver variables in fem_species order followed by fvm_species order.");
  return params;
}

ContinuityPhysics::ContinuityPhysics(const InputParameters & parameters)
  : PlasmaInterface(parameters)
{
  validateSpeciesInputs(getParam<std::vector<std::string>>("fem_species"),
                        getParam<std::vector<std::string>>("fvm_species"),
                        getParam<std::vector<VariableName>>("variables"));
}

void
ContinuityPhysics::checkIntegrity() const
{
  validateExistingSpeciesVariables(getParam<std::vector<std::string>>("fem_species"),
                                   getParam<std::vector<std::string>>("fvm_species"),
                                   getParam<std::vector<VariableName>>("variables"));
}

}

// MOOSE registers this action by its short name.
using Plasma::ContinuityPhysics;
registerPhysicsBaseTasks("PhysicsApp", ContinuityPhysics);
registerMooseAction("PhysicsApp", ContinuityPhysics, "check_integrity");
