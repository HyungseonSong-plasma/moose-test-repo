#include "PhysicsFVGummelLaplacianCorrection.h"

registerMooseObject("PhysicsApp", PhysicsFVGummelLaplacianCorrection);

InputParameters
PhysicsFVGummelLaplacianCorrection::validParams()
{
  auto params = FVFluxKernel::validParams();
  params.addClassDescription(
      "Conservative Gummel Poisson correction -div(kappa grad(phi-phi_anchor)) "
      "on internal FV faces.");
  params.addRequiredParam<MooseFunctorName>(
      "anchor", "Frozen entering-Gummel potential phi_anchor [V].");
  params.addRequiredParam<MooseFunctorName>(
      "coeff", "Dimensionless face coefficient kappa for the Laplacian-like correction.");
  params.set<unsigned short>("ghost_layers") = 2;
  return params;
}

PhysicsFVGummelLaplacianCorrection::PhysicsFVGummelLaplacianCorrection(
    const InputParameters & parameters)
  : FVFluxKernel(parameters),
    _anchor(getFunctor<ADReal>("anchor")),
    _coeff(getFunctor<ADReal>("coeff"))
{
}

ADReal
PhysicsFVGummelLaplacianCorrection::computeQpResidual()
{
  if (!_var.isInternalFace(*_face_info))
    return 0.0;

  const auto state = determineState();

  const ADReal phi_elem = _var(elemArg(), state);
  const ADReal phi_neighbor = _var(neighborArg(), state);
  const ADReal anchor_elem = _anchor(elemArg(), state);
  const ADReal anchor_neighbor = _anchor(neighborArg(), state);

  const ADReal coeff_elem = _coeff(elemArg(), state);
  const ADReal coeff_neighbor = _coeff(neighborArg(), state);
  const ADReal coeff_face = 0.5 * (coeff_elem + coeff_neighbor);

  const ADReal delta_elem = phi_elem - anchor_elem;
  const ADReal delta_neighbor = phi_neighbor - anchor_neighbor;

  return -coeff_face * (delta_neighbor - delta_elem) / _face_info->dCNMag();
}
