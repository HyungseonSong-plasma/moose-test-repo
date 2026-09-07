#include "QPXPlasmaChargeDensityMaterial.h"
#include "QPX.h"

#include <set>

registerMooseObject("qpxApp", QPXPlasmaChargeDensityMaterial);

InputParameters
QPXPlasmaChargeDensityMaterial::validParams()
{
  auto params = FunctorMaterial::validParams();

  params.addClassDescription(
      "Converts heavy-ion mass fractions and electron number density into "
      "charge density and the epsilon_0-scaled FV Poisson source.");

  params.addRequiredParam<MooseFunctorName>(
      "density", "Heavy-mixture mass density rho [kg/m^3].");

  params.addRequiredParam<MooseFunctorName>(
      "electron_density", "Electron number density n_e [1/m^3].");

  params.addRequiredParam<std::vector<std::string>>(
      "ion_ids", "Solver-safe ion identifiers used in output functor names.");

  params.addRequiredParam<std::vector<MooseFunctorName>>(
      "ion_mass_fractions", "Heavy-ion mass-fraction functors.");

  params.addRequiredParam<std::vector<Real>>(
      "ion_molar_masses", "Heavy-ion molar masses [kg/mol].");

  params.addRequiredParam<std::vector<Real>>(
      "ion_charges", "Signed ion charge numbers z_k.");

  return params;
}

QPXPlasmaChargeDensityMaterial::QPXPlasmaChargeDensityMaterial(
    const InputParameters & parameters)
  : FunctorMaterial(parameters),
    _density(getFunctor<ADReal>("density")),
    _electron_density(getFunctor<ADReal>("electron_density")),
    _ion_ids(getParam<std::vector<std::string>>("ion_ids")),
    _ion_mass_fraction_names(
        getParam<std::vector<MooseFunctorName>>("ion_mass_fractions")),
    _ion_molar_masses(getParam<std::vector<Real>>("ion_molar_masses")),
    _ion_charges(getParam<std::vector<Real>>("ion_charges"))
{
  const auto n = _ion_ids.size();

  if (n == 0)
    mooseError("QPXPlasmaChargeDensityMaterial requires at least one ion.");

  if (_ion_mass_fraction_names.size() != n ||
      _ion_molar_masses.size() != n ||
      _ion_charges.size() != n)
    mooseError("QPXPlasmaChargeDensityMaterial: all ion vectors must have "
               "the same length.");

  std::set<std::string> ids;
  _ion_mass_fractions.resize(n);

  for (std::size_t i = 0; i < n; ++i)
  {
    if (!ids.insert(_ion_ids[i]).second)
      mooseError("Duplicate ion_id '", _ion_ids[i], "'.");

    if (_ion_molar_masses[i] <= 0.0)
      mooseError("Ion molar masses must be positive.");

    _ion_mass_fractions[i] =
        &getFunctorByName<ADReal>(_ion_mass_fraction_names[i]);

    const auto id = _ion_ids[i];

    addFunctorProperty<ADReal>(
        "ion_number_density_" + id,
        [this, i](const auto & r, const auto & state) -> ADReal
        {
          return _density(r, state) *
                 (*_ion_mass_fractions[i])(r, state) *
                 QPX_CONSTANTS::N_A /
                 _ion_molar_masses[i];
        });
  }

  addFunctorProperty<ADReal>(
      "charge_number_density",
      [this](const auto & r, const auto & state) -> ADReal
      {
        ADReal n_charge = -_electron_density(r, state);

        for (std::size_t i = 0; i < _ion_ids.size(); ++i)
          n_charge +=
              _ion_charges[i] *
              _density(r, state) *
              (*_ion_mass_fractions[i])(r, state) *
              QPX_CONSTANTS::N_A /
              _ion_molar_masses[i];

        return n_charge;
      });

  addFunctorProperty<ADReal>(
      "charge_density",
      [this](const auto & r, const auto & state) -> ADReal
      {
        ADReal n_charge = -_electron_density(r, state);

        for (std::size_t i = 0; i < _ion_ids.size(); ++i)
          n_charge +=
              _ion_charges[i] *
              _density(r, state) *
              (*_ion_mass_fractions[i])(r, state) *
              QPX_CONSTANTS::N_A /
              _ion_molar_masses[i];

        return QPX_CONSTANTS::e * n_charge;
      });

  addFunctorProperty<ADReal>(
      "poisson_charge_source",
      [this](const auto & r, const auto & state) -> ADReal
      {
        ADReal n_charge = -_electron_density(r, state);

        for (std::size_t i = 0; i < _ion_ids.size(); ++i)
          n_charge +=
              _ion_charges[i] *
              _density(r, state) *
              (*_ion_mass_fractions[i])(r, state) *
              QPX_CONSTANTS::N_A /
              _ion_molar_masses[i];

        return QPX_CONSTANTS::e * n_charge / QPX_CONSTANTS::eps_0;
      });
}
