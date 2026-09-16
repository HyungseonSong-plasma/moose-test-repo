#include "PhysicsFVTwoPointDiffusionControl.h"

registerMooseObject("PhysicsApp", PhysicsFVTwoPointDiffusionControl);

InputParameters
PhysicsFVTwoPointDiffusionControl::validParams()
{
  auto params = FVDiffusion::validParams();
  params.addClassDescription(
      "Diagnostic-only Issue-228 diffusion control using the two-cell internal-face normal "
      "gradient while preserving framework boundary handling and coefficient interpolation.");
  return params;
}

PhysicsFVTwoPointDiffusionControl::PhysicsFVTwoPointDiffusionControl(
    const InputParameters & params)
  : FVDiffusion(params)
{
}

ADReal
PhysicsFVTwoPointDiffusionControl::computeQpResidual()
{
  const auto state = determineState();

  // Preserve framework boundary semantics exactly; only internal-face
  // non-orthogonal reconstruction is removed in this diagnostic control.
  if (!_var.isInternalFace(*_face_info))
    return FVDiffusion::computeQpResidual();

  const ADReal u_elem = _var(elemArg(), state);
  const ADReal u_neighbor = _var(neighborArg(), state);
  const Real projection = _face_info->eCN() * _normal;
  const ADReal dudn = (u_neighbor - u_elem) / _face_info->dCNMag() * projection;

  const ADReal coeff_elem = _coeff(elemArg(), state);
  const ADReal coeff_neighbor = _coeff(neighborArg(), state);
  if (!coeff_elem.value() && !coeff_neighbor.value())
    return 0;

  ADReal coeff;
  interpolate(_coeff_interp_method, coeff, coeff_elem, coeff_neighbor, *_face_info, true);
  return -coeff * dudn;
}
