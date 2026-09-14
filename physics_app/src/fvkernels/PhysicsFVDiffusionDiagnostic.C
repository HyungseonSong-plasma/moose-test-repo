#include "PhysicsFVDiffusionDiagnostic.h"

#include "metaphysicl/raw_type.h"

#include <algorithm>
#include <iostream>

registerMooseObject("PhysicsApp", PhysicsFVDiffusionDiagnostic);

InputParameters
PhysicsFVDiffusionDiagnostic::validParams()
{
  auto params = FVDiffusion::validParams();
  params.addClassDescription(
      "Diagnostic-only FVDiffusion wrapper that reports exact internal-face diffusive flux "
      "quantities for selected element IDs.");
  params.addRequiredParam<std::vector<unsigned int>>(
      "diagnostic_element_ids",
      "Element IDs defining the small internal-face cluster to report.");
  return params;
}

PhysicsFVDiffusionDiagnostic::PhysicsFVDiffusionDiagnostic(const InputParameters & params)
  : FVDiffusion(params),
    _diagnostic_element_ids(getParam<std::vector<unsigned int>>("diagnostic_element_ids"))
{
}

bool
PhysicsFVDiffusionDiagnostic::probeFace() const
{
  if (!_face_info || !_face_info->neighborPtr())
    return false;

  const auto elem_id = static_cast<unsigned int>(_face_info->elem().id());
  const auto neighbor_id = static_cast<unsigned int>(_face_info->neighbor().id());
  const auto selected = [this](const unsigned int id)
  {
    return std::find(_diagnostic_element_ids.begin(), _diagnostic_element_ids.end(), id) !=
           _diagnostic_element_ids.end();
  };
  return selected(elem_id) && selected(neighbor_id);
}

ADReal
PhysicsFVDiffusionDiagnostic::computeQpResidual()
{
  const ADReal parent_residual = FVDiffusion::computeQpResidual();
  if (!probeFace())
    return parent_residual;

  const auto state = determineState();
  const ADReal dudn = gradUDotNormal(state, _correct_skewness);
  const ADReal u_elem = _var(elemArg(), state);
  const ADReal u_neighbor = _var(neighborArg(), state);

  const Real central_dudn =
      (MetaPhysicL::raw_value(u_neighbor) - MetaPhysicL::raw_value(u_elem)) /
      _face_info->dCNMag() * (_face_info->eCN() * _normal);
  const Real actual_dudn = MetaPhysicL::raw_value(dudn);
  const auto & fc = _face_info->faceCentroid();

  std::cout << "ISSUE228_DIFF"
            << " elem=" << _face_info->elem().id()
            << " neighbor=" << _face_info->neighbor().id()
            << " face_x=" << fc(0)
            << " face_y=" << fc(1)
            << " u_elem=" << MetaPhysicL::raw_value(u_elem)
            << " u_neighbor=" << MetaPhysicL::raw_value(u_neighbor)
            << " central_dudn=" << central_dudn
            << " actual_dudn=" << actual_dudn
            << " nonorth_corr_dudn=" << actual_dudn - central_dudn
            << " residual=" << MetaPhysicL::raw_value(parent_residual)
            << std::endl;

  return parent_residual;
}
