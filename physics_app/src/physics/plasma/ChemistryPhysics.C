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

  params.addParam<std::vector<FileName>>(
      "rate_table_files", "Electron-impact rate tables, one per reaction.");
  params.addParam<MooseFunctorName>("mean_energy", "Mean electron energy in eV.");
  params.addParam<MooseFunctorName>(
      "electron_number_density", "Physical electron number density [1/m^3].");
  params.addParam<std::vector<MooseFunctorName>>(
      "target_molar_concentrations", "Target concentration [mol/m^3], one per reaction.");
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
  const bool tables = isParamValid("rate_table_files");
  const bool energy = isParamValid("mean_energy");
  const bool density = isParamValid("electron_number_density");
  const bool targets = isParamValid("target_molar_concentrations");
  if (tables || energy || density || targets)
  {
    if (!tables || !energy || !density || !targets)
      paramError("rate_table_files",
                 "Provide rate tables, mean energy, electron density and target concentrations.");
    if (getParam<std::vector<FileName>>("rate_table_files").size() != reaction_ids.size() ||
        getParam<std::vector<MooseFunctorName>>("target_molar_concentrations").size() !=
            reaction_ids.size())
      paramError("rate_table_files", "Provide one rate table and target concentration per reaction.");
  }
}

void
ChemistryPhysics::checkIntegrity() const
{
  // Reaction rates and source terms remain defined by existing simulation objects.
  // This action checks reaction names without creating or modifying those objects.
}

void
ChemistryPhysics::addFunctorMaterials()
{
  if (!isParamValid("rate_table_files"))
    return;
  const auto & reactions = getParam<std::vector<std::string>>("reaction_ids");
  const auto & tables = getParam<std::vector<FileName>>("rate_table_files");
  const auto & targets =
      getParam<std::vector<MooseFunctorName>>("target_molar_concentrations");
  const auto & outputs = getParam<std::vector<MooseFunctorName>>("reaction_progress");
  const std::string type = "PhysicsElectronImpactRateMaterial";
  for (std::size_t i = 0; i < reactions.size(); ++i)
  {
    auto params = getFactory().getValidParams(type);
    params.set<FileName>("rate_table_file") = tables[i];
    params.set<MooseFunctorName>("mean_energy") =
        getParam<MooseFunctorName>("mean_energy");
    params.set<MooseFunctorName>("electron_number_density") =
        getParam<MooseFunctorName>("electron_number_density");
    params.set<MooseFunctorName>("target_molar_concentration") = targets[i];
    params.set<std::string>("reaction_progress") = outputs[i];
    assignBlocks(params, _blocks);
    getProblem().addFunctorMaterial(type, name() + "_" + reactions[i] + "_rate", params);
  }
}

}

using Plasma::ChemistryPhysics;
registerPhysicsBaseTasks("PhysicsApp", ChemistryPhysics);
registerMooseAction("PhysicsApp", ChemistryPhysics, "check_integrity");
registerMooseAction("PhysicsApp", ChemistryPhysics, "add_functor_material");
