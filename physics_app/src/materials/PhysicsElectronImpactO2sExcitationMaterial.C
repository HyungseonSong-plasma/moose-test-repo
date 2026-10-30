#include "PhysicsElectronImpactO2sExcitationMaterial.h"

#include <cmath>

registerMooseObject("PhysicsApp", PhysicsElectronImpactO2sExcitationMaterial);

InputParameters
PhysicsElectronImpactO2sExcitationMaterial::validParams()
{
  auto params = FunctorMaterial::validParams();
  params.addClassDescription(
      "Computes the single frozen-surrogate molar reaction progress R_O2s for "
      "e + O2 -> e + O2(a1Delta_g). Source projection consumes this functor; "
      "electron-energy coupling remains deferred to #26 E8.");
  params.addRequiredParam<MooseFunctorName>("electron_number_density",
                                            "Physical electron number density [1/m^3].");
  params.addRequiredParam<MooseFunctorName>("o2_molar_concentration",
                                            "O2 molar concentration [mol/m^3].");
  params.addParam<MooseEnum>(
      "rate_model",
      MooseEnum("constant_surrogate temperature_dependent", "constant_surrogate"),
      "Explicit legacy constant-surrogate or Maxwellian Te-dependent EI10 rate law.");
  params.addParam<MooseFunctorName>(
      "mean_energy", "mean_en_solved", "Canonical solved mean electron energy [eV]; required in Te-dependent mode.");
  return params;
}

PhysicsElectronImpactO2sExcitationMaterial::PhysicsElectronImpactO2sExcitationMaterial(
    const InputParameters & parameters)
  : FunctorMaterial(parameters),
    _electron_number_density(getFunctor<ADReal>("electron_number_density")),
    _o2_molar_concentration(getFunctor<ADReal>("o2_molar_concentration")),
    _rate_model(getParam<MooseEnum>("rate_model")),
    _mean_energy(nullptr)
{
  if (_rate_model == "temperature_dependent")
    _mean_energy = &getFunctor<ADReal>("mean_energy");

  addFunctorProperty<ADReal>(
      "R_O2s",
      [this](const auto & r, const auto & state) -> ADReal
      {
        constexpr Real N_A = 6.02214076e23;
        constexpr Real K_O2S = 4.71e8;
        const ADReal n_e = _electron_number_density(r, state);
        const ADReal c_o2 = _o2_molar_concentration(r, state);
        if (n_e.value() < 0.0)
          mooseError("PhysicsElectronImpactO2sExcitationMaterial requires n_e >= 0.");
        if (c_o2.value() < 0.0)
          mooseError("PhysicsElectronImpactO2sExcitationMaterial requires c_O2 >= 0.");
        if (_rate_model == "constant_surrogate")
          return K_O2S * (n_e / N_A) * c_o2;

        // Gudmundsson et al., J. Phys. D 33 (2000) 1323, Table 3:
        // Maxwellian O2(X3Sigma_g-) -> O2(a1Delta_g) fit, valid at Te = 1-7 eV.
        using std::exp;
        const ADReal T_e = (2.0 / 3.0) * (*_mean_energy)(r, state);
        if (!std::isfinite(T_e.value()) || T_e.value() < 1.0 || T_e.value() > 7.0)
          mooseError("PhysicsElectronImpactO2sExcitationMaterial Te-dependent EI10 requires "
                     "1 <= Te <= 7 eV; got Te = ", T_e.value(), " eV.");
        return (N_A * 1.37e-15 * exp(-2.14 / T_e)) * (n_e / N_A) * c_o2;
      });
}
