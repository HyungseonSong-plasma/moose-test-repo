#include "ChemistryPhysics.h"
#include "PlasmaMechanism.h"

#include <iomanip>
#include <map>
#include <set>
#include <sstream>

namespace Plasma
{
namespace
{
struct SourceExpression
{
  std::vector<MooseFunctorName> names;
  std::vector<std::string> symbols;
  std::vector<std::string> parts;

  std::string expression() const
  {
    std::string result;
    for (const auto & part : parts)
      result += (result.empty() ? "" : "+") + part;
    return result;
  }

  std::string symbol(const MooseFunctorName & name)
  {
    const auto result = "f" + std::to_string(names.size());
    names.push_back(name);
    symbols.push_back(result);
    return result;
  }
};

std::string
realLiteral(double value)
{
  std::ostringstream stream;
  stream << std::setprecision(17) << value;
  return stream.str();
}

} // namespace

InputParameters
ChemistryPhysics::validParams()
{
  InputParameters params = PlasmaInterface::validParams();
  params.addClassDescription(
      "Generates one source Functor per species and one electron-energy source "
      "from validated [Plasmas]/files reaction channels; kinetic progress remains separately owned.");
  return params;
}

ChemistryPhysics::ChemistryPhysics(const InputParameters & parameters)
  : PlasmaInterface(parameters)
{
  if (plasmaMechanism().reactions().empty())
    mooseError("Activated [Transport]/[Chemistry] requires reactions in [Plasmas]/files");
}

void
ChemistryPhysics::checkIntegrity() const
{
  // The shared PlasmaMechanism constructor validates all ID <-> equation,
  // elemental and charge conservation, unique rate owners, signed energy
  // changes, and referenced species before any generated source is used.
}

void
ChemistryPhysics::addFunctorMaterials()
{
  const auto & mechanism = plasmaMechanism();
  std::map<std::string, SourceExpression> particle;
  SourceExpression energy;

  for (const auto & reaction : mechanism.reactions())
  {
    std::set<std::string> touched;
    for (const auto & [id, coefficient] : reaction.reactants)
      touched.insert(id);
    for (const auto & [id, coefficient] : reaction.products)
      touched.insert(id);

    for (const auto & id : touched)
    {
      const auto coefficient = reaction.net(id);
      if (coefficient == 0)
        continue;
      auto & source = particle[id];
      const auto symbol = source.symbol(reaction.progress);
      source.parts.push_back("(" + std::to_string(coefficient) + ")*" + symbol);
    }

    if (reaction.contributes_electron_energy)
    {
      const auto progress = energy.symbol(reaction.progress);
      if (!reaction.electron_energy_change_functor.empty())
      {
        // The energy-change functor itself has the signed eV/event contract.
        const auto delta = energy.symbol(reaction.electron_energy_change_functor);
        energy.parts.push_back("(" + delta + ")*" + progress);
      }
      else
        energy.parts.push_back("(" + realLiteral(reaction.electron_energy_change_eV) +
                               ")*" + progress);
    }
  }

  const std::string type = "ADParsedFunctorMaterial";
  for (const auto & [id, source] : particle)
  {
    auto params = getFactory().getValidParams(type);
    params.set<MooseFunctorName>("property_name") = "S_" + id + "_molar";
    params.set<std::vector<MooseFunctorName>>("functor_names") = source.names;
    params.set<std::vector<std::string>>("functor_symbols") = source.symbols;
    params.set<std::string>("expression") = source.expression();
    assignBlocks(params, _blocks);
    getProblem().addFunctorMaterial(type, "chemistry_" + id + "_source", params);
  }

  if (!energy.parts.empty())
  {
    auto params = getFactory().getValidParams(type);
    params.set<MooseFunctorName>("property_name") = "Q_e_molar_eV";
    params.set<std::vector<MooseFunctorName>>("functor_names") = energy.names;
    params.set<std::vector<std::string>>("functor_symbols") = energy.symbols;
    params.set<std::string>("expression") = energy.expression();
    assignBlocks(params, _blocks);
    getProblem().addFunctorMaterial(type, "chemistry_e_energy_source", params);
  }
}
} // namespace Plasma

using Plasma::ChemistryPhysics;
registerPhysicsBaseTasks("PhysicsApp", ChemistryPhysics);
registerMooseAction("PhysicsApp", ChemistryPhysics, "check_integrity");
registerMooseAction("PhysicsApp", ChemistryPhysics, "add_functor_material");
