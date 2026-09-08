#include "PhysicsElectronDiffusionSurfaceCharge.h"

registerADMooseObject("PhysicsApp", PhysicsElectronDiffusionSurfaceCharge);

InputParameters
PhysicsElectronDiffusionSurfaceCharge::validParams()
{
  InputParameters params = ADMaterial::validParams();
  params.addRequiredCoupledVar("coupled_variable0",
                               "The mean electron energy in log");
  params.addRequiredCoupledVar("coupled_variable1",
                               "The electron density in log");
  params.addClassDescription("");
  return params;
}

PhysicsElectronDiffusionSurfaceCharge::PhysicsElectronDiffusionSurfaceCharge(const InputParameters & parameters)
  : ADMaterial(parameters),
  _sigma(declareADProperty<Real>("surface_e")),
  _sigma_old(getMaterialPropertyOld<Real>("surface_e")),
  _mean_en(adCoupledValue("coupled_variable0")),
  _e(adCoupledValue("coupled_variable1")),
  _mass(getMaterialProperty<Real>("masse"))
{
  // Precalculate constant values
  _q_times_NA = PHYSICS_CONSTANTS::e * PHYSICS_CONSTANTS::N_A;
}

void
PhysicsElectronDiffusionSurfaceCharge::initQpStatefulProperties()
{
  _sigma[_qp] = 0;
}

void
PhysicsElectronDiffusionSurfaceCharge::computeQpProperties()
{
  if (_material_data_type == Moose::FACE_MATERIAL_DATA || boundaryRestricted())
  {
    using std::exp;
    
    ADReal _v_thermal = sqrt(8 * PHYSICS_CONSTANTS::e * 2.0 / 3.0 * exp(_mean_en[_qp] - _e[_qp])
                        / (libMesh::pi * _mass[_qp]));
    

    _sigma[_qp] = _sigma_old[_qp] + 0.25 * _v_thermal * exp(_e[_qp]) * _q_times_NA * _dt;
  }
  else
    _sigma[_qp] = 0.;
}
