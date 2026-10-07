#include "PhysicsFEMPlasmaWallBCs.h"
#include "PhysicsGroundedElectronSheathFlux.h"
#include "Physics.h"

#include <cmath>

registerMooseObject("PhysicsApp", PhysicsFEMElectronGroundedSheathBC);
registerMooseObject("PhysicsApp", PhysicsFEMElectronGroundedSheathEnergyBC);
registerMooseObject("PhysicsApp", PhysicsFEMIonWallBC);

InputParameters
PhysicsFEMElectronGroundedSheathBC::validParams()
{
  auto params = ADIntegratedBC::validParams();
  params.addRequiredCoupledVar("electron_energy_density", "Electron energy density [eV/m^3].");
  params.addRequiredCoupledVar("potential", "Plasma potential [V].");
  return params;
}

PhysicsFEMElectronGroundedSheathBC::PhysicsFEMElectronGroundedSheathBC(
    const InputParameters & parameters)
  : ADIntegratedBC(parameters),
    _electron_energy_density(adCoupledValue("electron_energy_density")),
    _potential(adCoupledValue("potential"))
{
}

ADReal
PhysicsFEMElectronGroundedSheathBC::computeQpResidual()
{
  const ADReal n_e = _u[_qp];
  const ADReal energy = _electron_energy_density[_qp];
  if (MetaPhysicL::raw_value(n_e) <= 0.0)
    mooseError("FEM grounded electron sheath requires n_e > 0.");
  if (MetaPhysicL::raw_value(energy) <= 0.0)
    mooseError("FEM grounded electron sheath requires electron energy density > 0.");

  const ADReal mean_energy = energy / n_e;
  const ADReal drop = PhysicsGroundedElectronSheath::smoothPositiveDropV(_potential[_qp]);
  const ADReal flux = PhysicsGroundedElectronSheath::primaryParticleFluxHat(n_e, mean_energy, drop);
  return _test[_i][_qp] * flux;
}

InputParameters
PhysicsFEMElectronGroundedSheathEnergyBC::validParams()
{
  auto params = ADIntegratedBC::validParams();
  params.addRequiredCoupledVar("electron_density", "Electron number density [1/m^3].");
  params.addRequiredCoupledVar("potential", "Plasma potential [V].");
  return params;
}

PhysicsFEMElectronGroundedSheathEnergyBC::PhysicsFEMElectronGroundedSheathEnergyBC(
    const InputParameters & parameters)
  : ADIntegratedBC(parameters),
    _electron_density(adCoupledValue("electron_density")),
    _potential(adCoupledValue("potential"))
{
}

ADReal
PhysicsFEMElectronGroundedSheathEnergyBC::computeQpResidual()
{
  const ADReal n_e = _electron_density[_qp];
  const ADReal energy = _u[_qp];
  if (MetaPhysicL::raw_value(n_e) <= 0.0)
    mooseError("FEM grounded sheath energy BC requires n_e > 0.");
  if (MetaPhysicL::raw_value(energy) <= 0.0)
    mooseError("FEM grounded sheath energy BC requires electron energy density > 0.");

  const ADReal mean_energy = energy / n_e;
  const ADReal drop = PhysicsGroundedElectronSheath::smoothPositiveDropV(_potential[_qp]);
  const ADReal Te = PhysicsGroundedElectronSheath::electronTemperatureEV(mean_energy);
  const ADReal particle_flux =
      PhysicsGroundedElectronSheath::primaryParticleFluxHat(n_e, mean_energy, drop);
  const ADReal energy_flux = particle_flux * (2.5 * Te + drop);
  return _test[_i][_qp] * energy_flux;
}

InputParameters
PhysicsFEMIonWallBC::validParams()
{
  auto params = ADIntegratedBC::validParams();
  params.addRequiredCoupledVar("potential", "Electrostatic potential [V].");
  params.addRequiredParam<Real>("mobility", "Fixed positive-ion mobility [m^2/(V s)].");
  params.addRequiredParam<Real>("gas_temperature", "Fixed ion/gas temperature [K].");
  params.addRequiredParam<Real>("molar_mass", "Ion molar mass [kg/mol].");
  params.addRequiredParam<Real>("charge_number", "Signed ion charge number.");
  params.addParam<Real>("sticking", 1.0, "Surface sticking/neutralization probability.");
  params.addParam<Real>("migration_gate_smoothing_width", 1.0e-3, "Smoothing width [V/m].");
  return params;
}

PhysicsFEMIonWallBC::PhysicsFEMIonWallBC(const InputParameters & parameters)
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
PhysicsFEMIonWallBC::computeQpResidual()
{
  using std::sqrt;
  using std::tanh;

  const ADReal n_i = _u[_qp];
  if (MetaPhysicL::raw_value(n_i) < 0.0)
    mooseError("FEM ion wall BC requires n_i >= 0.");

  const Real v_th =
      std::sqrt(8.0 * PHYSICS_CONSTANTS::R * _gas_temperature /
                (PHYSICS_CONSTANTS::pi * _molar_mass));
  const ADReal surface_flux = _sticking * 0.25 * n_i * v_th;

  const ADRealVectorValue electric_field = -_grad_potential[_qp];
  const ADReal directed_field = _charge_number * (electric_field * _normals[_qp]);
  ADReal outward_field;
  if (_migration_gate_smoothing_width > 0.0)
    outward_field = 0.5 * directed_field *
                    (1.0 + tanh(directed_field / _migration_gate_smoothing_width));
  else
    outward_field = MetaPhysicL::raw_value(directed_field) > 0.0
                        ? directed_field
                        : ADReal(0.0) * directed_field;

  const ADReal migration_flux = n_i * _mobility * outward_field;
  return _test[_i][_qp] * (surface_flux + migration_flux);
}
