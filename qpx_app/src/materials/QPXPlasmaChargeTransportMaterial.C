#include "QPXPlasmaChargeTransportMaterial.h"
#include "QPX.h"

#include <cmath>
#include <set>

registerMooseObject("qpxApp", QPXPlasmaChargeTransportMaterial);

InputParameters
QPXPlasmaChargeTransportMaterial::validParams()
{
  auto params = FunctorMaterial::validParams();

  params.addClassDescription(
      "Builds electric-field, charge-density, heavy-ion drift, electron drift, "
      "and heavy mass-average electromigration correction functors.");

  params.addRequiredParam<MooseFunctorName>(
      "potential", "Electrostatic potential phi [V].");

  params.addRequiredParam<MooseFunctorName>(
      "density", "Heavy-mixture mass density rho [kg/m^3].");

  params.addRequiredParam<MooseFunctorName>(
      "electron_density", "Electron number density n_e [1/m^3].");

  params.addRequiredParam<MooseFunctorName>(
      "electron_mobility", "Electron mobility magnitude mu_e [m^2/(V s)].");

  params.addRequiredParam<std::vector<std::string>>(
      "ion_ids",
      "Solver-safe identifiers used to construct output functor names.");

  params.addRequiredParam<std::vector<MooseFunctorName>>(
      "ion_mass_fractions",
      "Heavy-ion mass-fraction functors in the same order as ion_ids.");

  params.addRequiredParam<std::vector<Real>>(
      "ion_molar_masses",
      "Heavy-ion molar masses [kg/mol] in the same order as ion_ids.");

  params.addRequiredParam<std::vector<Real>>(
      "ion_charges",
      "Signed integer charge numbers z_k in the same order as ion_ids.");

  params.addRequiredParam<std::vector<MooseFunctorName>>(
      "ion_mobilities",
      "Positive mobility magnitudes [m^2/(V s)] in the same order as ion_ids.");

  params.addRequiredParam<std::vector<MooseFunctorName>>(
      "ion_diffusions",
      "Ion diffusion coefficients [m^2/s] in the same order as ion_ids. "
      "These are exposed as rho*D_k functors for FV mass-fraction diffusion.");

  return params;
}

QPXPlasmaChargeTransportMaterial::QPXPlasmaChargeTransportMaterial(
    const InputParameters & parameters)
  : FunctorMaterial(parameters),
    _potential(getFunctor<ADReal>("potential")),
    _density(getFunctor<ADReal>("density")),
    _electron_density(getFunctor<ADReal>("electron_density")),
    _electron_mobility(getFunctor<ADReal>("electron_mobility")),
    _ion_ids(getParam<std::vector<std::string>>("ion_ids")),
    _ion_mass_fraction_names(
        getParam<std::vector<MooseFunctorName>>("ion_mass_fractions")),
    _ion_molar_masses(getParam<std::vector<Real>>("ion_molar_masses")),
    _ion_charges(getParam<std::vector<Real>>("ion_charges")),
    _ion_mobility_names(getParam<std::vector<MooseFunctorName>>("ion_mobilities")),
    _ion_diffusion_names(getParam<std::vector<MooseFunctorName>>("ion_diffusions"))
{
  const auto n = _ion_ids.size();

  if (_ion_mass_fraction_names.size() != n ||
      _ion_molar_masses.size() != n ||
      _ion_charges.size() != n ||
      _ion_mobility_names.size() != n ||
      _ion_diffusion_names.size() != n)
    mooseError("QPXPlasmaChargeTransportMaterial: all ion parameter vectors "
               "must have the same length.");

  if (n == 0)
    mooseError("QPXPlasmaChargeTransportMaterial requires at least one ion.");

  std::set<std::string> unique_ids;
  for (const auto & id : _ion_ids)
    if (!unique_ids.insert(id).second)
      mooseError("QPXPlasmaChargeTransportMaterial duplicate ion_id '", id, "'.");

  _ion_mass_fractions.resize(n);
  _ion_mobilities.resize(n);
  _ion_diffusions.resize(n);

  for (std::size_t i = 0; i < n; ++i)
  {
    if (_ion_molar_masses[i] <= 0.0)
      mooseError("Ion molar masses must be positive.");

    if (_ion_mobilities.size() != n)
      mooseError("Internal ion mobility vector sizing error.");

    _ion_mass_fractions[i] =
        &getFunctorByName<ADReal>(_ion_mass_fraction_names[i]);
    _ion_mobilities[i] =
        &getFunctorByName<ADReal>(_ion_mobility_names[i]);
    _ion_diffusions[i] =
        &getFunctorByName<ADReal>(_ion_diffusion_names[i]);
  }

  addFunctorProperty<ADRealVectorValue>(
      "electric_field",
      [this](const auto & r, const auto & state) -> ADRealVectorValue
      { return -_potential.gradient(r, state); });

  for (std::size_t i = 0; i < n; ++i)
  {
    const auto id = _ion_ids[i];

    addFunctorProperty<ADReal>(
        "rho_w_" + id,
        [this, i](const auto & r, const auto & state) -> ADReal
        { return _density(r, state) * (*_ion_mass_fractions[i])(r, state); });

    addFunctorProperty<ADReal>(
        "ion_number_density_" + id,
        [this, i](const auto & r, const auto & state) -> ADReal
        {
          return _density(r, state) *
                 (*_ion_mass_fractions[i])(r, state) *
                 QPX_CONSTANTS::N_A / _ion_molar_masses[i];
        });

    addFunctorProperty<ADReal>(
        "rho_diffusivity_" + id,
        [this, i](const auto & r, const auto & state) -> ADReal
        { return _density(r, state) * (*_ion_diffusions[i])(r, state); });

    addFunctorProperty<ADRealVectorValue>(
        "ion_drift_velocity_" + id,
        [this, i](const auto & r, const auto & state) -> ADRealVectorValue
        {
          const auto E = -_potential.gradient(r, state);
          return _ion_charges[i] *
                 (*_ion_mobilities[i])(r, state) * E;
        });
  }

  addFunctorProperty<ADRealVectorValue>(
      "heavy_mass_correction_velocity",
      [this](const auto & r, const auto & state) -> ADRealVectorValue
      {
        const auto E = -_potential.gradient(r, state);

        ADReal signed_mass_weighted_mobility = 0.0;
        for (std::size_t i = 0; i < _ion_ids.size(); ++i)
          signed_mass_weighted_mobility +=
              (*_ion_mass_fractions[i])(r, state) *
              _ion_charges[i] *
              (*_ion_mobilities[i])(r, state);

        return -signed_mass_weighted_mobility * E;
      });

  addFunctorProperty<ADRealVectorValue>(
      "electron_drift_velocity",
      [this](const auto & r, const auto & state) -> ADRealVectorValue
      {
        const auto E = -_potential.gradient(r, state);
        return -_electron_mobility(r, state) * E;
      });

  addFunctorProperty<ADReal>(
      "ion_mass_fraction_sum",
      [this](const auto & r, const auto & state) -> ADReal
      {
        ADReal sum = 0.0;
        for (const auto * w : _ion_mass_fractions)
          sum += (*w)(r, state);
        return sum;
      });

  addFunctorProperty<ADReal>(
      "neutral_remainder_mass_fraction",
      [this](const auto & r, const auto & state) -> ADReal
      {
        ADReal sum = 0.0;
        for (const auto * w : _ion_mass_fractions)
          sum += (*w)(r, state);
        return 1.0 - sum;
      });

  addFunctorProperty<ADReal>(
      "charge_number_density",
      [this](const auto & r, const auto & state) -> ADReal
      {
        ADReal charge_number = -_electron_density(r, state);

        for (std::size_t i = 0; i < _ion_ids.size(); ++i)
          charge_number +=
              _ion_charges[i] *
              _density(r, state) *
              (*_ion_mass_fractions[i])(r, state) *
              QPX_CONSTANTS::N_A / _ion_molar_masses[i];

        return charge_number;
      });

  addFunctorProperty<ADReal>(
      "charge_density",
      [this](const auto & r, const auto & state) -> ADReal
      {
        ADReal charge_number = -_electron_density(r, state);

        for (std::size_t i = 0; i < _ion_ids.size(); ++i)
          charge_number +=
              _ion_charges[i] *
              _density(r, state) *
              (*_ion_mass_fractions[i])(r, state) *
              QPX_CONSTANTS::N_A / _ion_molar_masses[i];

        return QPX_CONSTANTS::e * charge_number;
      });

  addFunctorProperty<ADReal>(
      "electric_field_magnitude",
      [this](const auto & r, const auto & state) -> ADReal
      {
        using std::sqrt;
        const auto E = -_potential.gradient(r, state);
        return sqrt(E * E);
      });
}
