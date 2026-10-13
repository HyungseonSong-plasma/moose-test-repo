#include "PhysicsADSurfaceChargePoissonBC.h"

#include "Physics.h"

registerMooseObject("PhysicsApp", PhysicsADSurfaceChargePoissonBC);

InputParameters
PhysicsADSurfaceChargePoissonBC::validParams()
{
  auto params = ADIntegratedBC::validParams();
  params.addClassDescription(
      "Couples a lower-dimensional dielectric surface-charge variable into the continuous-FEM "
      "Poisson weak form as -sigma_s/epsilon_0.");
  params.addRequiredCoupledVar(
      "surface_charge",
      "Lower-dimensional nonlinear surface-charge density sigma_s [C/m^2].");
  return params;
}

PhysicsADSurfaceChargePoissonBC::PhysicsADSurfaceChargePoissonBC(
    const InputParameters & parameters)
  : ADIntegratedBC(parameters),
    _surface_charge(adCoupledLowerValue("surface_charge"))
{
}

ADReal
PhysicsADSurfaceChargePoissonBC::computeQpResidual()
{
  return -_test[_i][_qp] * _surface_charge[_qp] / PHYSICS_CONSTANTS::eps_0;
}
