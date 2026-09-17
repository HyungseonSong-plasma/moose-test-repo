#include "PhysicsFVHeavyMassDiffusionCorrection.h"

registerMooseObject("PhysicsApp", PhysicsFVHeavyMassDiffusionCorrection);

InputParameters
PhysicsFVHeavyMassDiffusionCorrection::validParams()
{
  auto params = FVFluxKernel::validParams();

  params.addClassDescription(
      "Adds the mass-average correction to mixture-averaged heavy-species diffusion.");

  params.addRequiredParam<MooseFunctorName>(
      "rho", "Mixture density rho [kg/m^3].");

  params.addRequiredParam<MooseFunctorName>(
      "mean_molar_mass", "Mixture mean molar mass Mn [kg/mol].");

  params.addRequiredParam<std::vector<MooseFunctorName>>(
      "mass_fractions", "All heavy-species mass-fraction functors, including constrained species.");

  params.addRequiredParam<std::vector<MooseFunctorName>>(
      "diffusivities", "Mixture-averaged diffusivities D_km [m^2/s] in the same order.");

  return params;
}

PhysicsFVHeavyMassDiffusionCorrection::PhysicsFVHeavyMassDiffusionCorrection(
    const InputParameters & parameters)
  : FVFluxKernel(parameters),
    _rho(getFunctor<ADReal>("rho")),
    _mean_molar_mass(getFunctor<ADReal>("mean_molar_mass")),
    _mass_fraction_names(getParam<std::vector<MooseFunctorName>>("mass_fractions")),
    _diffusivity_names(getParam<std::vector<MooseFunctorName>>("diffusivities"))
{
  if (_mass_fraction_names.empty())
    paramError("mass_fractions", "At least two heavy species are required.");

  if (_mass_fraction_names.size() != _diffusivity_names.size())
    mooseError(
        "PhysicsFVHeavyMassDiffusionCorrection: mass_fractions and diffusivities "
        "must have identical lengths.");

  _mass_fractions.reserve(_mass_fraction_names.size());
  _diffusivities.reserve(_diffusivity_names.size());

  for (std::size_t i = 0; i < _mass_fraction_names.size(); ++i)
  {
    _mass_fractions.push_back(getFunctorByName<ADReal>(_mass_fraction_names[i]));
    _diffusivities.push_back(getFunctorByName<ADReal>(_diffusivity_names[i]));
  }
}

ADReal
PhysicsFVHeavyMassDiffusionCorrection::computeQpResidual()
{
  const auto state = determineState();

  const auto & limiter_time =
      _subproblem.isTransient()
          ? Moose::StateArg(1, Moose::SolutionIterationType::Time)
          : Moose::StateArg(1, Moose::SolutionIterationType::Nonlinear);

  const auto face =
      makeFace(*_face_info,
               Moose::FV::LimiterType::CentralDifference,
               true,
               false,
               &limiter_time);

  const ADReal rho_face = _rho(face, state);
  const ADReal Mn_face = _mean_molar_mass(face, state);
  const ADRealVectorValue grad_Mn = _mean_molar_mass.gradient(face, state);
  const ADReal dMndn = grad_Mn * _normal;

  ADReal raw_total_mass_flux_normal = 0.0;

  for (std::size_t i = 0; i < _mass_fractions.size(); ++i)
  {
    const ADReal w_face = (*_mass_fractions[i])(face, state);
    const ADReal D_face = (*_diffusivities[i])(face, state);
    const ADRealVectorValue grad_w = _mass_fractions[i]->gradient(face, state);
    const ADReal dwdn = grad_w * _normal;

    raw_total_mass_flux_normal +=
        -rho_face * D_face * (dwdn + (w_face / Mn_face) * dMndn);
  }

  const ADReal current_species_mass_fraction = _var(face, state);

  return -current_species_mass_fraction * raw_total_mass_flux_normal;
}
