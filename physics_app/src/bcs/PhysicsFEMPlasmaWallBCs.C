#include "PhysicsFEMPlasmaWallBCs.h"
#include "Physics.h"

#include <cmath>

registerMooseObject("PhysicsApp", PhysicsFEMLogMolarIonWallBC);

InputParameters
PhysicsFEMLogMolarIonWallBC::validParams()
{
  auto params = ADIntegratedBC::validParams();
  params.addClassDescription("O2+ wall loss for a FEM log-molar ion concentration.");
  params.addRequiredCoupledVar("potential", "Electrostatic potential [V].");
  params.addRequiredParam<Real>("mobility", "Fixed positive-ion mobility [m^2/(V s)].");
  params.addRequiredParam<Real>("gas_temperature", "Fixed ion/gas temperature [K].");
  params.addRequiredParam<Real>("molar_mass", "Ion molar mass [kg/mol].");
  params.addRequiredParam<Real>("charge_number", "Signed ion charge number.");
  params.addParam<Real>("sticking", 1.0, "Surface sticking/neutralization probability.");
  params.addParam<Real>("migration_gate_smoothing_width", 1.0e-3, "Smoothing width [V/m].");
  return params;
}

PhysicsFEMLogMolarIonWallBC::PhysicsFEMLogMolarIonWallBC(
    const InputParameters & parameters)
  : ADIntegratedBC(parameters),
    _grad_potential(adCoupledGradient("potential")),
    _mobility(getParam<Real>("mobility")),
    _gas_temperature(getParam<Real>("gas_temperature")),
    _molar_mass(getParam<Real>("molar_mass")),
    _charge_number(getParam<Real>("charge_number")),
    _sticking(getParam<Real>("sticking")),
    _migration_gate_smoothing_width(getParam<Real>("migration_gate_smoothing_width"))
{
  if (_mobility <= 0.0)
    paramError("mobility", "mobility must be positive.");
  if (_gas_temperature <= 0.0)
    paramError("gas_temperature", "gas_temperature must be positive.");
  if (_molar_mass <= 0.0)
    paramError("molar_mass", "molar_mass must be positive.");
  if (_charge_number == 0.0)
    paramError("charge_number", "charge_number must be nonzero.");
}

ADReal
PhysicsFEMLogMolarIonWallBC::computeQpResidual()
{
  using std::exp;
  using std::sqrt;
  using std::tanh;

  const ADReal c_i = exp(_u[_qp]);

  const Real v_th =
      sqrt(8.0 * PHYSICS_CONSTANTS::R * _gas_temperature /
           (PHYSICS_CONSTANTS::pi * _molar_mass));
  const ADReal surface_molar_flux = _sticking * 0.25 * c_i * v_th;

  const ADRealVectorValue electric_field = -_grad_potential[_qp];
  const ADReal directed_field = _charge_number * (electric_field * _normals[_qp]);
  ADReal outward_field;
  if (_migration_gate_smoothing_width > 0.0)
    outward_field =
        0.5 * directed_field *
        (1.0 + tanh(directed_field / _migration_gate_smoothing_width));
  else
    outward_field = MetaPhysicL::raw_value(directed_field) > 0.0
                        ? directed_field
                        : ADReal(0.0) * directed_field;

  const ADReal migration_molar_flux = c_i * _mobility * outward_field;
  return _test[_i][_qp] * (surface_molar_flux + migration_molar_flux);
}
