#include "NVTransport.h"
#include "Chemistry.h"

namespace Plasma
{
InputParameters
NVTransport::validParams()
{
  auto params = PlasmaInterface::validParams();
  params.addClassDescription(
      "NavierStokes collision/mixture transport from [Plasmas]/files; "
      "no material table path or species options in MOOSE input.");
  return params;
}

NVTransport::NVTransport(const InputParameters & parameters)
  : PlasmaInterface(parameters)
{
  if (!chemistryData().nvTransport())
    mooseError("Activated [Transport]/[NavierStokes] requires "
               "transport_coefficients.navier_stokes in [Plasmas]/files");
}

void
NVTransport::addFunctorMaterials()
{
  const auto * config = chemistryData().nvTransport();
  if (!config)
    mooseError("Missing navier_stokes transport configuration");
  const std::string type = "NVTransportMaterial";
  auto params = getFactory().getValidParams(type);
  params.set<FileName>("transport_data_file") = config->transport_data_file;
  params.set<MooseFunctorName>("temperature") = config->temperature;
  params.set<MooseFunctorName>("pressure") = config->pressure;
  params.set<std::vector<std::string>>("species") = config->species;
  params.set<std::vector<MooseFunctorName>>("mass_fractions") =
      std::vector<MooseFunctorName>(config->mass_fractions.begin(),
                                    config->mass_fractions.end());
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
