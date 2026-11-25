#include "NVTransport.h"
#include "Chemistry.h"
#include "FEProblemBase.h"

#include <cmath>
#include <iomanip>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>

namespace Plasma
{
InputParameters
NVTransport::validParams()
{
  auto params = PlasmaInterface::validParams();
  params.addClassDescription(
      "NavierStokes collision/mixture transport from [Plasmas]/files; "
      "named .i species masses can own the alias-only collision-data path.");
  params.addParam<std::vector<std::string>>(
      "species_molar_mass", "Named neutral masses (species:kg/mol); exact coverage of the "
                            "active mixture, no JSON or database mass owner.");
  return params;
}

NVTransport::NVTransport(const InputParameters & parameters)
  : PlasmaInterface(parameters)
{
}

void
NVTransport::addFunctorMaterials()
{
  const auto * config = chemistryData().nvTransport();
  if (!config)
    mooseError("Activated [Transport]/[NavierStokes] requires "
               "transport_coefficients.navier_stokes in [Plasmas]/files");
  const std::string type = "NVTransportMaterial";
  auto params = getFactory().getValidParams(type);
  params.set<FileName>("transport_data_file") = config->transport_data_file;
  params.set<MooseFunctorName>("temperature") = rootGasStateEnabled() ? "temperature" : config->temperature;
  params.set<MooseFunctorName>("pressure") = rootGasStateEnabled() ? "pressure" : config->pressure;
  params.set<std::vector<std::string>>("species") = config->species;
  std::vector<MooseFunctorName> fractions;
  const bool input_mass_owner = isParamValid("species_molar_mass");
  if (input_mass_owner)
  {
    // This first .i ownership cut uses the existing solved-pressure EOS.
    // Fixed-pressure root JSON composition remains a separate legacy lane.
    if (!rootGasStateEnabled() || !getProblem().hasVariable("pressure"))
      paramError("species_molar_mass", "Named neutral masses require the solved-pressure mixture.");
    const std::set<std::string> selected(config->species.begin(), config->species.end());
    if (selected.size() != config->species.size())
      paramError("species_molar_mass", "Repeated active neutral species.");
    std::map<std::string, Real> masses;
    for (const auto & entry : getParam<std::vector<std::string>>("species_molar_mass"))
    {
      const auto colon = entry.find(':');
      if (colon == std::string::npos || colon == 0 || colon + 1 == entry.size() ||
          entry.find(':', colon + 1) != std::string::npos)
        paramError("species_molar_mass", "Expected species:positive_mass, found ", entry);
      const auto id = entry.substr(0, colon);
      const auto value = entry.substr(colon + 1);
      if (!selected.count(id) || masses.count(id))
        paramError("species_molar_mass", "Unknown or repeated neutral mass: ", id);
      std::size_t consumed = 0;
      Real mass = 0.0;
      try
      {
        mass = std::stod(value, &consumed);
      }
      catch (const std::exception &)
      {
        paramError("species_molar_mass", "Invalid neutral molar mass: ", entry);
      }
      if (consumed != value.size() || !std::isfinite(mass) || mass <= 0.0)
        paramError("species_molar_mass", "Neutral molar mass must be finite and positive: ", id);
      const auto & record = chemistryData().species(id);
      if (record.charge_number != 0 || record.molar_mass > 0.0 ||
          record.molar_mass_kg_mol > 0.0 || record.ion_wall)
        paramError("species_molar_mass", "Neutral .i mass conflicts with charge or JSON mass owner: ", id);
      masses.emplace(id, mass);
    }
    if (masses.size() != selected.size())
      paramError("species_molar_mass", "Named neutral masses must cover every active species.");
    for (const auto & reaction : chemistryData().reactions())
      if (reaction.rate.model == "lookup" && !selected.count(reaction.rate.lookup_target))
        paramError("species_molar_mass", "EI lookup target is not an active neutral: ",
                   reaction.rate.lookup_target);

    std::vector<Real> ordered_masses;
    for (std::size_t i = 0; i < config->species.size(); ++i)
    {
      const auto & id = config->species[i];
      const Real mass = masses.at(id);
      ordered_masses.push_back(mass);
      // During the staged migration the existing EOS owns rho_neutral and
      // the existing validated mixture bindings own live mass fractions.
      // Each species has exactly one concentration, shared by every EI rate.
      auto concentration = getFactory().getValidParams("ADParsedFunctorMaterial");
      concentration.set<std::string>("property_name") = "c_" + id + "_molar";
      concentration.set<std::vector<std::string>>("functor_names") =
          {"rho_neutral", config->mass_fractions[i]};
      concentration.set<std::vector<std::string>>("functor_symbols") = {"rho", "Y"};
      std::ostringstream expression;
      expression << std::setprecision(17) << "rho*Y/" << mass;
      concentration.set<std::string>("expression") = expression.str();
      assignBlocks(concentration, _blocks);
      getProblem().addFunctorMaterial("ADParsedFunctorMaterial",
                                      name() + "_" + id + "_molar_concentration",
                                      concentration);
    }
    params.set<std::vector<Real>>("molar_masses") = ordered_masses;
    fractions.assign(config->mass_fractions.begin(), config->mass_fractions.end());
  }
  else if (rootGasStateEnabled())
    for (const auto & id : config->species)
      fractions.emplace_back("Y_" + id); // live JSON species-state aliases
  else
    fractions.assign(config->mass_fractions.begin(), config->mass_fractions.end());
  params.set<std::vector<MooseFunctorName>>("mass_fractions") = fractions;
  if (!config->electron_temperature.empty())
  {
    params.set<MooseFunctorName>("electron_temperature") = config->electron_temperature;
    params.set<MooseFunctorName>("electron_number_density") = config->electron_number_density;
  }
  assignBlocks(params, _blocks);
  getProblem().addFunctorMaterial(type, name() + "_mixture_transport_coefficients", params);
}
} // namespace Plasma

using Plasma::NVTransport;
registerPhysicsBaseTasks("PhysicsApp", NVTransport);
registerMooseAction("PhysicsApp", NVTransport, "add_functor_material");
