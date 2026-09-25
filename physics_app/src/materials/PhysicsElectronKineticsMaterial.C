#include "PhysicsElectronKineticsMaterial.h"
#include "Physics.h"

#include <set>

registerMooseObject("PhysicsApp", PhysicsElectronKineticsMaterial);

InputParameters
PhysicsElectronKineticsMaterial::validParams()
{
  auto params = FunctorMaterial::validParams();

  params.addClassDescription(
      "Owns multiple strict mean-energy electron-impact rate tables and publishes one "
      "molar reaction-progress functor per reaction.");

  params.addRequiredParam<MooseFunctorName>(
      "electron_mean_energy", "Mean electron energy [eV].");
  params.addRequiredParam<MooseFunctorName>(
      "electron_number_density", "Physical electron number density [1/m^3].");
  params.addRequiredParam<std::vector<FileName>>(
      "rate_table_files",
      "One two-column mean-energy/rate table for each electron-impact reaction.");
  params.addRequiredParam<std::vector<MooseFunctorName>>(
      "target_molar_concentrations",
      "Target-species molar concentration functors [mol/m^3], one per reaction.");
  params.addRequiredParam<std::vector<std::string>>(
      "reaction_progress_names",
      "Published molar reaction-progress functor names, one per reaction.");

  return params;
}

PhysicsElectronKineticsMaterial::PhysicsElectronKineticsMaterial(
    const InputParameters & parameters)
  : FunctorMaterial(parameters),
    _electron_mean_energy(getFunctor<ADReal>("electron_mean_energy")),
    _electron_number_density(getFunctor<ADReal>("electron_number_density")),
    _rate_table_files(getParam<std::vector<FileName>>("rate_table_files")),
    _target_molar_concentration_names(
        getParam<std::vector<MooseFunctorName>>("target_molar_concentrations")),
    _reaction_progress_names(getParam<std::vector<std::string>>("reaction_progress_names"))
{
  const std::size_t n = _rate_table_files.size();

  if (n == 0)
    paramError("rate_table_files", "At least one electron-impact reaction is required.");

  if (_target_molar_concentration_names.size() != n ||
      _reaction_progress_names.size() != n)
    mooseError("PhysicsElectronKineticsMaterial requires rate_table_files, "
               "target_molar_concentrations, and reaction_progress_names to have equal length.");

  std::set<std::string> unique_names;
  _target_molar_concentrations.reserve(n);
  _tables.reserve(n);

  for (std::size_t i = 0; i < n; ++i)
  {
    if (_reaction_progress_names[i].empty())
      paramError("reaction_progress_names", "Reaction-progress names must not be empty.");

    if (!unique_names.insert(_reaction_progress_names[i]).second)
      paramError("reaction_progress_names",
                 "Duplicate reaction-progress name '",
                 _reaction_progress_names[i],
                 "'.");

    _target_molar_concentrations.push_back(
        &getFunctorByName<ADReal>(_target_molar_concentration_names[i]));

    _tables.emplace_back(_rate_table_files[i], 1, std::vector<std::size_t>{2});

    addFunctorProperty<ADReal>(
        _reaction_progress_names[i],
        [this, i](const auto & r, const auto & state) -> ADReal
        {
          const ADReal n_e = _electron_number_density(r, state);
          const ADReal c_target = (*_target_molar_concentrations[i])(r, state);

          if (n_e.value() < 0.0)
            mooseError("PhysicsElectronKineticsMaterial requires electron_number_density >= 0 "
                       "for reaction '",
                       _reaction_progress_names[i],
                       "'.");

          if (c_target.value() < 0.0)
            mooseError("PhysicsElectronKineticsMaterial requires target molar concentration >= 0 "
                       "for reaction '",
                       _reaction_progress_names[i],
                       "'.");

          const ADReal k_raw = interpolateStrict(_electron_mean_energy(r, state), i);

          if (k_raw.value() < 0.0)
            mooseError("PhysicsElectronKineticsMaterial encountered a negative tabulated rate "
                       "for reaction '",
                       _reaction_progress_names[i],
                       "'.");

          return k_raw * (n_e / PHYSICS_CONSTANTS::N_A) * c_target;
        });
  }
}

ADReal
PhysicsElectronKineticsMaterial::interpolateStrict(const ADReal & coordinate,
                                                    std::size_t reaction_index) const
{
  const auto & table = _tables.at(reaction_index);
  const auto & x = table.coordinate();
  const auto & y = table.values(0);
  const Real raw = coordinate.value();

  if (raw < x.front() || raw > x.back())
    mooseError("Electron-impact reaction '",
               _reaction_progress_names.at(reaction_index),
               "' mean electron energy ",
               raw,
               " eV is outside lookup range [",
               x.front(),
               ", ",
               x.back(),
               "] eV.");

  if (raw == x.front())
    return y.front();

  if (raw == x.back())
    return y.back();

  const std::size_t i = table.lowerBracket(raw);
  return y[i] +
         (coordinate - x[i]) * (y[i + 1] - y[i]) / (x[i + 1] - x[i]);
}
