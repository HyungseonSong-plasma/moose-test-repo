#include "PhysicsSpeciesTransportAliasMaterial.h"

#include <cctype>

registerMooseObject("PhysicsApp", PhysicsSpeciesTransportAliasMaterial);

InputParameters
PhysicsSpeciesTransportAliasMaterial::validParams()
{
  auto params = FunctorMaterial::validParams();
  params.addClassDescription(
      "Publishes species-owned drift-diffusion coefficient aliases from "
      "existing trusted AD Functors, without rescaling or default values.");
  params.addRequiredParam<std::string>(
      "species_id", "Solver-safe ID, used verbatim in the generated Functor names.");
  params.addRequiredParam<MooseFunctorName>(
      "mobility_source", "Existing mobility Functor [m^2/(V s)].");
  params.addRequiredParam<MooseFunctorName>(
      "diffusivity_source", "Existing diffusion Functor [m^2/s].");
  return params;
}

PhysicsSpeciesTransportAliasMaterial::PhysicsSpeciesTransportAliasMaterial(
    const InputParameters & parameters)
  : FunctorMaterial(parameters),
    _mobility(getFunctor<ADReal>("mobility_source")),
    _diffusivity(getFunctor<ADReal>("diffusivity_source"))
{
  const auto & species = getParam<std::string>("species_id");
  if (species.empty() || !std::isalpha(static_cast<unsigned char>(species.front())))
    paramError("species_id", "Species name must start with a letter.");
  for (const auto c : species)
    if (!std::isalnum(static_cast<unsigned char>(c)) && c != '_')
      paramError("species_id", "Species name contains an invalid character.");

  const auto mobility_name = species + "_mobility";
  const auto diffusivity_name = species + "_diffusivity";
  if (getParam<MooseFunctorName>("mobility_source") == mobility_name ||
      getParam<MooseFunctorName>("diffusivity_source") == diffusivity_name)
    paramError("species_id",
               "Canonical coefficient sources must be consumed directly; "
               "do not create cyclic or duplicate aliases.");

  addFunctorProperty<ADReal>(
      mobility_name,
      [this](const auto & r, const auto & state) -> ADReal
      { return _mobility(r, state); });
  addFunctorProperty<ADReal>(
      diffusivity_name,
      [this](const auto & r, const auto & state) -> ADReal
      { return _diffusivity(r, state); });
}
