#include "ADIntegratedBC.h"
#include "MooseFunctorArguments.h"
#include "Physics.h"

class PhysicsFEMLogMolarDielectricFluxBC : public ADIntegratedBC
{
public:
  static InputParameters validParams();
  PhysicsFEMLogMolarDielectricFluxBC(const InputParameters & parameters);

  // The plasma species is intentionally defined only on the plasma side of the
  // internal plasma-dielectric sideset. The mesh may carry that sideset on both
  // adjacent elements, so suppress the generic whole-sideset coverage check and
  // explicitly skip non-plasma invocations in computeQpResidual().
  bool checkVariableBoundaryIntegrity() const override { return false; }

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
      "ledger. The species may be restricted to the plasma side of the internal sideset.");
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
  // An internal sideset can be present on both higher-dimensional neighbors.
  // Only the plasma-side variable/functor owner is physical for this loss term.
  const auto block = _current_elem->subdomain_id();
  if (!_var.activeOnSubdomain(block) || !_signed_number_flux.hasBlocks(block))
    return ADReal(0.0);

  const Moose::ElemQpArg qp_arg = {_current_elem, _qp, _qrule, _q_point[_qp]};
  const ADReal gamma_signed = _signed_number_flux(qp_arg, Moose::currentState());
  return _test[_i][_qp] * gamma_signed / PHYSICS_CONSTANTS::N_A;
}
