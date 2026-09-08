#include "PhysicsElectronImpactIonizationMaterial.h"

registerMooseObject("PhysicsApp", PhysicsElectronImpactIonizationMaterial);

InputParameters
PhysicsElectronImpactIonizationMaterial::validParams()
{
  auto params = FunctorMaterial::validParams();
  params.addClassDescription(
      "Computes the single strict-lookup molar reaction progress R_ion_O2 for "
      "e + O2 -> 2e + O2p. Particle source projection is owned separately and "
      "must consume this functor; electron-energy coupling remains deferred to #26 E8.");
  params.addRequiredParam<FileName>("rate_table_file",
                                    "Two-column table: mean energy [eV], k_raw [m^3/(mol s)].");
  params.addRequiredParam<MooseFunctorName>("mean_energy", "Solved mean electron energy [eV].");
  params.addRequiredParam<MooseFunctorName>("electron_number_density",
                                            "Physical electron number density [1/m^3].");
  params.addRequiredParam<MooseFunctorName>("o2_molar_concentration",
                                            "O2 molar concentration [mol/m^3].");
  return params;
}

PhysicsElectronImpactIonizationMaterial::PhysicsElectronImpactIonizationMaterial(
    const InputParameters & parameters)
  : FunctorMaterial(parameters),
    _mean_energy(getFunctor<ADReal>("mean_energy")),
    _electron_number_density(getFunctor<ADReal>("electron_number_density")),
    _o2_molar_concentration(getFunctor<ADReal>("o2_molar_concentration")),
    _rate_table_file(getParam<FileName>("rate_table_file")),
    _table(_rate_table_file, 1, {2})
{
  constexpr Real N_A = 6.02214076e23;

  addFunctorProperty<ADReal>(
      "R_ion_O2",
      [this](const auto & r, const auto & state) -> ADReal
      {
        const ADReal n_e = _electron_number_density(r, state);
        const ADReal c_o2 = _o2_molar_concentration(r, state);
        if (n_e.value() < 0.0)
          mooseError("PhysicsElectronImpactIonizationMaterial requires n_e >= 0.");
        if (c_o2.value() < 0.0)
          mooseError("PhysicsElectronImpactIonizationMaterial requires c_O2 >= 0.");
        return interpolateStrict(_mean_energy(r, state)) * (n_e / N_A) * c_o2;
      });
}

ADReal
PhysicsElectronImpactIonizationMaterial::interpolateStrict(const ADReal & coordinate) const
{
  const auto & x = _table.coordinate();
  const auto & y = _table.values(0);
  const Real raw = coordinate.value();

  if (raw < x.front() || raw > x.back())
    mooseError("O2 ionization mean electron energy ", raw,
               " eV is outside lookup range [", x.front(), ", ", x.back(),
               "] eV; strict R2 policy forbids clamp/floor.");
  if (raw == x.front())
    return y.front();
  if (raw == x.back())
    return y.back();

  const std::size_t i = _table.lowerBracket(raw);
  return y[i] + (coordinate - x[i]) * (y[i + 1] - y[i]) / (x[i + 1] - x[i]);
}
