#include "PhysicsO2IonizationSourceMaterial.h"

registerMooseObject("PhysicsApp", PhysicsO2IonizationSourceMaterial);

InputParameters
PhysicsO2IonizationSourceMaterial::validParams()
{
  auto params = FunctorMaterial::validParams();
  params.addClassDescription(
      "Projects one canonical O2 ionization molar progress into O2/O2p mass and net electron number sources.");
  params.addRequiredParam<MooseFunctorName>("reaction_progress",
                                            "Canonical R_ion_O2 [mol/(m^3 s)].");
  params.addParam<Real>("o2_molar_mass", 31.998e-3, "O2 molar mass [kg/mol].");
  return params;
}

PhysicsO2IonizationSourceMaterial::PhysicsO2IonizationSourceMaterial(const InputParameters & parameters)
  : FunctorMaterial(parameters),
    _reaction_progress(getFunctor<ADReal>("reaction_progress")),
    _o2_molar_mass(getParam<Real>("o2_molar_mass"))
{
  constexpr Real N_A = 6.02214076e23;

  addFunctorProperty<ADReal>(
      "O2_ionization_mass_source",
      [this](const auto & r, const auto & state) -> ADReal
      {
        const ADReal R = _reaction_progress(r, state);
        if (R.value() < 0.0)
          mooseError("PhysicsO2IonizationSourceMaterial requires R_ion_O2 >= 0.");
        return -_o2_molar_mass * R;
      });

  addFunctorProperty<ADReal>(
      "O2p_ionization_mass_source",
      [this](const auto & r, const auto & state) -> ADReal
      { return _o2_molar_mass * _reaction_progress(r, state); });

  addFunctorProperty<ADReal>(
      "electron_ionization_number_source",
      [this](const auto & r, const auto & state) -> ADReal
      { return N_A * _reaction_progress(r, state); });
}
