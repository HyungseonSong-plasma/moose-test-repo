#include "PhysicsElectronImpactO2sExcitationMaterial.h"

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
  return params;
}

PhysicsElectronImpactO2sExcitationMaterial::PhysicsElectronImpactO2sExcitationMaterial(
    const InputParameters & parameters)
  : FunctorMaterial(parameters),
    _electron_number_density(getFunctor<ADReal>("electron_number_density")),
    _o2_molar_concentration(getFunctor<ADReal>("o2_molar_concentration"))
{
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
        return K_O2S * (n_e / N_A) * c_o2;
      });
}
