#include "PhysicsFVHeavyMassCorrectedDiffusion.h"

registerMooseObject("PhysicsApp", PhysicsFVHeavyMassCorrectedDiffusion);

InputParameters
PhysicsFVHeavyMassCorrectedDiffusion::validParams()
{
  auto params = FVFluxKernel::validParams();
  params.addClassDescription(
      "Conservative mass-average corrected mixture-averaged heavy-species diffusion flux.");
  params.addRequiredParam<MooseFunctorName>("rho", "Mixture density [kg/m^3].");
  params.addRequiredParam<MooseFunctorName>("mean_molar_mass", "Mixture mean molar mass [kg/mol].");
  params.addRequiredParam<std::vector<MooseFunctorName>>(
      "mass_fractions", "All heavy-species mass fractions, including the constrained species.");
  params.addRequiredParam<std::vector<MooseFunctorName>>(
      "diffusivities", "Mixture-averaged diffusivities in the same order as mass_fractions.");
  params.addRequiredParam<unsigned int>(
      "species_index", "Index of the solved species in mass_fractions/diffusivities.");
  return params;
}

PhysicsFVHeavyMassCorrectedDiffusion::PhysicsFVHeavyMassCorrectedDiffusion(
    const InputParameters & parameters)
  : FVFluxKernel(parameters),
    _rho(getFunctor<ADReal>("rho")),
    _mean_molar_mass(getFunctor<ADReal>("mean_molar_mass")),
    _mass_fraction_names(getParam<std::vector<MooseFunctorName>>("mass_fractions")),
    _diffusivity_names(getParam<std::vector<MooseFunctorName>>("diffusivities")),
    _species_index(getParam<unsigned int>("species_index"))
{
  if (_mass_fraction_names.size() < 2)
    paramError("mass_fractions", "At least two heavy species are required.");
  if (_mass_fraction_names.size() != _diffusivity_names.size())
    mooseError("PhysicsFVHeavyMassCorrectedDiffusion: mass_fractions and diffusivities must have identical lengths.");
  if (_species_index >= _mass_fraction_names.size())
    paramError("species_index", "species_index is outside the supplied heavy-species list.");

  _mass_fractions.reserve(_mass_fraction_names.size());
  _diffusivities.reserve(_diffusivity_names.size());
  for (std::size_t i = 0; i < _mass_fraction_names.size(); ++i)
  {
    _mass_fractions.push_back(&getFunctorByName<ADReal>(_mass_fraction_names[i]));
    _diffusivities.push_back(&getFunctorByName<ADReal>(_diffusivity_names[i]));
  }
}

ADReal
PhysicsFVHeavyMassCorrectedDiffusion::computeQpResidual()
{
  if (!_var.isInternalFace(*_face_info))
    return 0.0;

  const auto state = determineState();
  const auto & limiter_time =
      _subproblem.isTransient()
          ? Moose::StateArg(1, Moose::SolutionIterationType::Time)
          : Moose::StateArg(1, Moose::SolutionIterationType::Nonlinear);

  const auto face = makeFace(*_face_info,
                             Moose::FV::LimiterType::CentralDifference,
                             true,
                             false,
                             &limiter_time);

  const ADReal rho_face = _rho(face, state);
  const ADReal Mn_face = _mean_molar_mass(face, state);
  const ADReal dMndn = _mean_molar_mass.gradient(face, state) * _normal;

  ADReal raw_sum = 0.0;
  ADReal raw_k = 0.0;

  for (std::size_t i = 0; i < _mass_fractions.size(); ++i)
  {
    const ADReal w_face = (*_mass_fractions[i])(face, state);
    const ADReal D_face = (*_diffusivities[i])(face, state);
    const ADReal dwdn = _mass_fractions[i]->gradient(face, state) * _normal;
    const ADReal J_raw = -rho_face * D_face * (dwdn + (w_face / Mn_face) * dMndn);
    raw_sum += J_raw;
    if (i == _species_index)
      raw_k = J_raw;
  }

  const ADReal w_k = (*_mass_fractions[_species_index])(face, state);
  return raw_k - w_k * raw_sum;
}
