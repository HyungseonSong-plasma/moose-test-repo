#include "PhysicsSurfaceChargeStatePostprocessor.h"

#include "PhysicsSurfaceChargeState.h"

registerMooseObject("PhysicsApp", PhysicsSurfaceChargeStatePostprocessor);

InputParameters
PhysicsSurfaceChargeStatePostprocessor::validParams()
{
  InputParameters params = GeneralPostprocessor::validParams();

  params.addClassDescription(
      "Reports total charge, surface area, or average surface charge from "
      "PhysicsSurfaceChargeState.");

  params.addRequiredParam<UserObjectName>(
      "surface_charge_state",
      "PhysicsSurfaceChargeState that owns the dielectric surface-charge state.");

  MooseEnum quantity("total_charge surface_area average_surface_charge", "total_charge");
  params.addParam<MooseEnum>(
      "quantity",
      quantity,
      "Surface-state quantity to report: " + quantity.getRawNames());

  return params;
}

PhysicsSurfaceChargeStatePostprocessor::PhysicsSurfaceChargeStatePostprocessor(
    const InputParameters & parameters)
  : GeneralPostprocessor(parameters),
    _surface_charge_state(
        getUserObject<PhysicsSurfaceChargeState>("surface_charge_state")),
    _quantity(getParam<MooseEnum>("quantity"))
{
}

PostprocessorValue
PhysicsSurfaceChargeStatePostprocessor::getValue() const
{
  if (_quantity == "total_charge")
    return _surface_charge_state.totalCharge();

  if (_quantity == "surface_area")
    return _surface_charge_state.surfaceArea();

  if (_quantity == "average_surface_charge")
    return _surface_charge_state.averageSurfaceCharge();

  mooseError("Unsupported PhysicsSurfaceChargeStatePostprocessor quantity '",
             _quantity,
             "'.");
}