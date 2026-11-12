#include "ChemistryAction.h"

InputParameters
ChemistryAction::validParams()
{
  InputParameters params = Action::validParams();
  params.addParam<std::vector<FileName>>(
      "files", {}, "Ordered JSON mechanism files shared by plasma Chemistry, Continuity and Poisson.");
  return params;
}

ChemistryAction::ChemistryAction(const InputParameters & params)
  : Action(params),
    _data([this]() {
      std::vector<std::string> paths;
      for (const auto & filename : getParam<std::vector<FileName>>("files"))
        paths.emplace_back(filename);
      return paths;
    }())
{
}

registerMooseAction("PhysicsApp", ChemistryAction, "check_integrity");
