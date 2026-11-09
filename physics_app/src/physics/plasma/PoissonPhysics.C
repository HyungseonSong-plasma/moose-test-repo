#include "PoissonPhysics.h"

namespace Plasma
{

InputParameters
PoissonPhysics::validParams()
{
  InputParameters params = PlasmaInterface::validParams();
  params.addClassDescription(
      "Checks existing poisson inputs without creating or modifying solver equations.");
  params.addRequiredParam<VariableName>(
      "potential_variable", "Existing solver variable for the electric potential.");
  return params;
}

PoissonPhysics::PoissonPhysics(const InputParameters & parameters)
  : PlasmaInterface(parameters)
{
  if (getParam<VariableName>("potential_variable").empty())
    paramError("potential_variable", "Specify an electric potential variable.");
}

void
PoissonPhysics::checkIntegrity() const
{
  const auto & potential = getParam<VariableName>("potential_variable");
  if (!solverVariableExists(potential))
    paramError("potential_variable", "Electric potential variable was not found: ", potential);
}

}

using Plasma::PoissonPhysics;
registerPhysicsBaseTasks("PhysicsApp", PoissonPhysics);
registerMooseAction("PhysicsApp", PoissonPhysics, "check_integrity");
