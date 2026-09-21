#include "PhysicsO2sExcitationSourceMaterial.h"

registerMooseObject("PhysicsApp", PhysicsO2sExcitationSourceMaterial);

InputParameters
PhysicsO2sExcitationSourceMaterial::validParams()
{
  auto params = FunctorMaterial::validParams();
  params.addClassDescription(
      "Projects one canonical O2(a1Delta_g) excitation molar progress into equal-and-opposite O2/O2s mass sources.");
  params.addRequiredParam<MooseFunctorName>("reaction_progress",
                                            "Canonical R_O2s [mol/(m^3 s)].");
  params.addParam<Real>("o2_molar_mass", 31.998e-3, "O2 molar mass [kg/mol].");
  return params;
}

PhysicsO2sExcitationSourceMaterial::PhysicsO2sExcitationSourceMaterial(
    const InputParameters & parameters)
  : FunctorMaterial(parameters),
    _reaction_progress(getFunctor<ADReal>("reaction_progress")),
    _o2_molar_mass(getParam<Real>("o2_molar_mass"))
{
  addFunctorProperty<ADReal>(
      "O2_o2s_excitation_mass_source",
      [this](const auto & r, const auto & state) -> ADReal
      {
        const ADReal R = _reaction_progress(r, state);
        if (R.value() < 0.0)
          mooseError("PhysicsO2sExcitationSourceMaterial requires R_O2s >= 0.");
        return -_o2_molar_mass * R;
      });

  addFunctorProperty<ADReal>(
      "O2s_excitation_mass_source",
      [this](const auto & r, const auto & state) -> ADReal
      {
        const ADReal R = _reaction_progress(r, state);
        if (R.value() < 0.0)
          mooseError("PhysicsO2sExcitationSourceMaterial requires R_O2s >= 0.");
        return _o2_molar_mass * R;
      });
}
