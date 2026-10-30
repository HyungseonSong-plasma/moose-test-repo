#include "PhysicsElectronImpactO2Ex1ExcitationMaterial.h"

#include <cmath>

registerMooseObject("PhysicsApp", PhysicsElectronImpactO2Ex1ExcitationMaterial);

InputParameters
PhysicsElectronImpactO2Ex1ExcitationMaterial::validParams()
{
  auto params = FunctorMaterial::validParams();
  params.addClassDescription(
      "Computes one canonical formula-based molar reaction progress for 4.5 eV "
      "O2(ex1) electronic excitation (Reaction 411); does not create heavy/charge sources.");
  params.addRequiredParam<MooseFunctorName>(
      "electron_number_density", "Physical electron number density [1/m^3].");
  params.addRequiredParam<MooseFunctorName>(
      "o2_molar_concentration", "Ground-state O2 concentration [mol/m^3].");
  params.addRequiredParam<MooseFunctorName>(
      "mean_energy", "Current solved mean electron energy [eV], not the energy density.");
  return params;
}

PhysicsElectronImpactO2Ex1ExcitationMaterial::PhysicsElectronImpactO2Ex1ExcitationMaterial(
    const InputParameters & parameters)
  : FunctorMaterial(parameters),
    _electron_number_density(getFunctor<ADReal>("electron_number_density")),
    _o2_molar_concentration(getFunctor<ADReal>("o2_molar_concentration")),
    _mean_energy(getFunctor<ADReal>("mean_energy"))
{
  addFunctorProperty<ADReal>(
      "R_O2_ex1_411",
      [this](const auto & r, const auto & state) -> ADReal
      {
        constexpr Real N_A = 6.02214076e23;
        constexpr Real K_PREF_M3_S = 1.07e-15;
        constexpr Real BETA_EV = 3.43;
        const ADReal n_e = _electron_number_density(r, state);
        const ADReal c_o2 = _o2_molar_concentration(r, state);
        const ADReal T_e = (2.0 / 3.0) * _mean_energy(r, state);

        if (!std::isfinite(n_e.value()) || n_e.value() < 0.0)
          mooseError("Reaction 411 requires finite n_e >= 0 [1/m^3].");
        if (!std::isfinite(c_o2.value()) || c_o2.value() < 0.0)
          mooseError("Reaction 411 requires finite c_O2 >= 0 [mol/m^3].");
        if (!std::isfinite(T_e.value()) || T_e.value() < 1.0 || T_e.value() > 7.0)
          mooseError("Reaction 411 Gudmundsson Maxwellian fit requires 1 <= Te <= 7 eV; "
                     "Te = ", T_e.value(), " eV.");

        using std::exp;
        const ADReal k_molar = (N_A * K_PREF_M3_S) * exp(-BETA_EV / T_e);
        return k_molar * (n_e / N_A) * c_o2;
      });
}
