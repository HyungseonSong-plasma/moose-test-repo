#include "ADIntegratedBC.h"
#include "MooseFunctorArguments.h"
#include "Physics.h"

class PhysicsFEMLogMolarDielectricFluxBC : public ADIntegratedBC
{
public:
  static InputParameters validParams();
  PhysicsFEMLogMolarDielectricFluxBC(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const Moose::Functor<ADReal> & _signed_number_flux;
};

registerMooseObject("PhysicsApp", PhysicsFEMLogMolarDielectricFluxBC);

InputParameters
PhysicsFEMLogMolarDielectricFluxBC::validParams()
{
  auto params = ADIntegratedBC::validParams();
  params.addClassDescription(
      "Applies a signed particle-number flux to a FEM log-molar plasma species on a "
      "plasma-dielectric interface. Positive flux is outward from the plasma/species domain. "
      "The supplied functor can therefore be shared exactly with the dielectric surface-current "
      "ledger.");
  params.addRequiredParam<MooseFunctorName>(
      "signed_number_flux",
      "Signed particle-number flux [1/(m^2 s)]; positive outward from the plasma/species domain.");
  return params;
}

PhysicsFEMLogMolarDielectricFluxBC::PhysicsFEMLogMolarDielectricFluxBC(
    const InputParameters & parameters)
  : ADIntegratedBC(parameters),
    _signed_number_flux(getFunctor<ADReal>("signed_number_flux"))
{
}

ADReal
PhysicsFEMLogMolarDielectricFluxBC::computeQpResidual()
{
  const Moose::ElemQpArg qp_arg = {_current_elem, _qp, _qrule, _q_point[_qp]};
  const ADReal gamma_signed = _signed_number_flux(qp_arg, Moose::currentState());
  return _test[_i][_qp] * gamma_signed / PHYSICS_CONSTANTS::N_A;
}
