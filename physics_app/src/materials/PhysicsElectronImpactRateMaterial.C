#include "PhysicsElectronImpactRateMaterial.h"

#include <stdexcept>

registerMooseObject("PhysicsApp", PhysicsElectronImpactRateMaterial);

InputParameters
PhysicsElectronImpactRateMaterial::validParams()
{
  auto params = FunctorMaterial::validParams();
  params.addClassDescription(
      "Computes one electron-impact molar reaction progress from a mean-energy rate table. "
      "The optional clamp policy is intended as a nonlinear-iteration continuation outside "
      "the table; converged states should still be validated against the physical table range.");
  params.addRequiredParam<FileName>("rate_table_file",
                                    "Two-column table: mean energy [eV], k_raw [m^3/(mol s)].");
  params.addRequiredParam<MooseFunctorName>("mean_energy", "Solved mean electron energy [eV].");
  params.addRequiredParam<MooseFunctorName>("electron_number_density",
                                            "Physical electron number density [1/m^3].");
  params.addRequiredParam<MooseFunctorName>("target_molar_concentration",
                                            "Target-species molar concentration [mol/m^3].");
  params.addRequiredParam<std::string>("reaction_progress",
                                       "Name of the published molar reaction-progress functor.");
  params.addParam<std::string>(
      "bounds_policy",
      "error",
      "Lookup behavior outside the tabulated mean-energy range: 'error' or 'clamp'.");
  return params;
}

PhysicsElectronImpactRateMaterial::PhysicsElectronImpactRateMaterial(
    const InputParameters & parameters)
  : FunctorMaterial(parameters),
    _mean_energy(getFunctor<ADReal>("mean_energy")),
    _electron_number_density(getFunctor<ADReal>("electron_number_density")),
    _target_molar_concentration(getFunctor<ADReal>("target_molar_concentration")),
    _rate_table_file(getParam<FileName>("rate_table_file")),
    _reaction_progress_name(getParam<std::string>("reaction_progress")),
    _table(_rate_table_file, 1, {2}),
    _bounds_policy(parseBoundsPolicy(getParam<std::string>("bounds_policy")))
{
  constexpr Real N_A = 6.02214076e23;

  if (_reaction_progress_name.empty())
    paramError("reaction_progress", "The reaction-progress functor name must not be empty.");

  addFunctorProperty<ADReal>(
      _reaction_progress_name,
      [this, N_A](const auto & r, const auto & state) -> ADReal
      {
        const ADReal n_e = _electron_number_density(r, state);
        const ADReal c_target = _target_molar_concentration(r, state);
        if (n_e.value() < 0.0)
          mooseError("PhysicsElectronImpactRateMaterial requires n_e >= 0 for '",
                     _reaction_progress_name,
                     "'.");
        if (c_target.value() < 0.0)
          mooseError("PhysicsElectronImpactRateMaterial requires c_target >= 0 for '",
                     _reaction_progress_name,
                     "'.");

        const ADReal k_raw = interpolate(_mean_energy(r, state));
        if (k_raw.value() < 0.0)
          mooseError("PhysicsElectronImpactRateMaterial encountered a negative tabulated rate for '",
                     _reaction_progress_name,
                     "'.");
        return k_raw * (n_e / N_A) * c_target;
      });
}

PhysicsElectronImpactRateMaterial::BoundsPolicy
PhysicsElectronImpactRateMaterial::parseBoundsPolicy(const std::string & value)
{
  if (value == "error")
    return BoundsPolicy::Error;
  if (value == "clamp")
    return BoundsPolicy::Clamp;

  throw std::runtime_error(
      "PhysicsElectronImpactRateMaterial bounds_policy must be 'error' or 'clamp'.");
}

ADReal
PhysicsElectronImpactRateMaterial::interpolate(const ADReal & coordinate) const
{
  const auto & x = _table.coordinate();
  const auto & y = _table.values(0);
  const Real raw = coordinate.value();

  if (raw < x.front())
  {
    if (_bounds_policy == BoundsPolicy::Error)
      mooseError("Electron-impact progress '",
                 _reaction_progress_name,
                 "' mean electron energy ",
                 raw,
                 " eV is below lookup minimum ",
                 x.front(),
                 " eV.");
    return y.front();
  }

  if (raw > x.back())
  {
    if (_bounds_policy == BoundsPolicy::Error)
      mooseError("Electron-impact progress '",
                 _reaction_progress_name,
                 "' mean electron energy ",
                 raw,
                 " eV is above lookup maximum ",
                 x.back(),
                 " eV.");
    return y.back();
  }

  if (raw == x.front())
    return y.front();
  if (raw == x.back())
    return y.back();

  const std::size_t i = _table.lowerBracket(raw);
  return y[i] + (coordinate - x[i]) * (y[i + 1] - y[i]) / (x[i + 1] - x[i]);
}
