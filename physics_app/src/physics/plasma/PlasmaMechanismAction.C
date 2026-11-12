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
    _mechanism([this]() {
      std::vector<std::string> paths;
      for (const auto & filename : getParam<std::vector<FileName>>("files"))
        paths.emplace_back(filename);
      return paths;
    }())
{
}

registerMooseAction("PhysicsApp", PlasmaMechanismAction, "check_integrity");
