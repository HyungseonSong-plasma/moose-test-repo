#include "PlasmaMechanismAction.h"

InputParameters
PlasmaMechanismAction::validParams()
{
  InputParameters params = Action::validParams();
  params.addParam<std::vector<FileName>>(
      "files", {}, "Ordered JSON mechanism files shared by plasma Chemistry, Continuity and Poisson.");
  return params;
}

PlasmaMechanismAction::PlasmaMechanismAction(const InputParameters & params)
  : Action(params),
    _mechanism(getParam<std::vector<FileName>>("files"))
{
}

registerMooseAction("PhysicsApp", PlasmaMechanismAction, "check_integrity");
