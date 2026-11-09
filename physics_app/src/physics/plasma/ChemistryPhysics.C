#include "ChemistryPhysics.h"
#include <set>

namespace Plasma
{

InputParameters
ChemistryPhysics::validParams()
{
  InputParameters params = PlasmaInterface::validParams();
  params.addClassDescription(
      "Checks existing chemistry inputs without creating or modifying solver equations.");
  params.addRequiredParam<std::vector<std::string>>(
      "reaction_ids", "Names of the reactions already configured in the simulation.");
  params.addRequiredParam<std::vector<MooseFunctorName>>(
      "reaction_progress", "Existing reaction progress names in reaction_ids order.");
  return params;
}

ChemistryPhysics::ChemistryPhysics(const InputParameters & parameters)
  : PlasmaInterface(parameters)
{
  const auto & reaction_ids = getParam<std::vector<std::string>>("reaction_ids");
  const auto & reaction_progress = getParam<std::vector<MooseFunctorName>>("reaction_progress");
  if (reaction_ids.empty())
    paramError("reaction_ids", "List at least one chemical reaction.");
  if (reaction_ids.size() != reaction_progress.size())
    paramError("reaction_progress", "Provide one reaction progress name per reaction.");

  std::set<std::string> unique_reactions;
  std::set<MooseFunctorName> unique_progress;
  for (std::size_t index = 0; index < reaction_ids.size(); ++index)
  {
    if (reaction_ids[index].empty() || !unique_reactions.insert(reaction_ids[index]).second)
      paramError("reaction_ids", "Repeated or empty reaction name: ", reaction_ids[index]);
    if (reaction_progress[index].empty() ||
        !unique_progress.insert(reaction_progress[index]).second)
      paramError("reaction_progress",
                 "Repeated or empty reaction progress name: ",
                 reaction_progress[index]);
  }
}

void
ChemistryPhysics::checkIntegrity() const
{
  // Reaction rates and source terms remain defined by existing simulation objects.
  // This action checks reaction names without creating or modifying those objects.
}

}

using Plasma::ChemistryPhysics;
registerPhysicsBaseTasks("PhysicsApp", ChemistryPhysics);
registerMooseAction("PhysicsApp", ChemistryPhysics, "check_integrity");
